"""单实例锁测试 (v0.8.8 dev即生产; DEV-0293 双实例事故防线)。

不变量: 同进程组残留 (含不持端口的 uvicorn 子进程) 必须被拒绝启动 —
端口检查对此类僵尸失效, pgid 存活探测是唯一可靠闸。
"""
from __future__ import annotations

import getpass
import os

import pytest

from backend.utils import instance_lock as il


@pytest.fixture(autouse=True)
def _escape_valve_off(monkeypatch):
    """测试默认关掉 HOTSPOT_IGNORE_LOCK 逃生口 (防外泄 env 穿透)。"""
    monkeypatch.delenv("HOTSPOT_IGNORE_LOCK", raising=False)


def _fake_pgid(monkeypatch, pgid: int) -> None:
    monkeypatch.setattr(il.os, "getpgid", lambda pid: pgid)


def test_fresh_acquire_writes_own_pgid(tmp_path, monkeypatch):
    lock = tmp_path / "hotspot.lock"
    _fake_pgid(monkeypatch, 4242)
    assert il.acquire_instance_lock(lock) is None  # 无冲突
    assert lock.read_text().strip() == "4242"


def test_alive_pgid_conflict_refuses(tmp_path, monkeypatch):
    """锁内 pgid 进程组存活 (本测试进程组即活体) → 返回冲突 pgid。"""
    lock = tmp_path / "hotspot.lock"
    live = os.getpgid(0)  # 真实存活进程组
    lock.write_text(str(live))
    assert il.acquire_instance_lock(lock) == live
    # 拒绝时不得覆写锁 (现场保留供运维定位)
    assert lock.read_text().strip() == str(live)


def test_stale_lock_overwritten(tmp_path, monkeypatch):
    """进程组全灭的陈旧锁 (kill -9 后残留) → 覆写并成功获取。"""
    lock = tmp_path / "hotspot.lock"
    lock.write_text("999999999")  # 不可能存活的 pgid
    _fake_pgid(monkeypatch, 4242)
    assert il.acquire_instance_lock(lock) is None
    assert lock.read_text().strip() == "4242"


def test_corrupt_lock_treated_stale(tmp_path, monkeypatch):
    lock = tmp_path / "hotspot.lock"
    lock.write_text("not-a-number")
    _fake_pgid(monkeypatch, 4242)
    assert il.acquire_instance_lock(lock) is None


# ---------------------------------------------------------------------------
# DEV-0310 — mkdir fail-open 一致性 (锁目录不可建: 降级不阻断启动)
# ---------------------------------------------------------------------------
def test_mkdir_blocked_fails_open(tmp_path, monkeypatch, capsys):
    """锁父路径被同名文件阻塞 (比 chmod 稳的 POSIX 通用失败注入, root 安全):
    acquire 不抛 → 返回 None 放行 + stderr 降级提示 (与 write_text 容忍同取舍,
    声明与行为一致: 锁链路任何 OSError 都不阻断启动)。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    lock = blocker / "hotspot.lock"  # parent = blocker 是文件 → mkdir FileExistsError
    _fake_pgid(monkeypatch, 4242)
    assert il.acquire_instance_lock(lock) is None
    err = capsys.readouterr().err
    assert "锁目录不可建" in err and "端口探活仍执行" in err


def test_refuse_if_locked_degrades_to_port_probe(tmp_path):
    """锁检降级后端口探活仍守住单实例 (fail-open ≠ 放弃守护)。"""
    import socket
    from contextlib import closing

    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    with closing(socket.socket()) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        with pytest.raises(SystemExit) as ei:
            il.refuse_if_locked(lock_path=blocker / "hotspot.lock", port=port)
        assert ei.value.code == 2  # 端口持有者照样拒启动


def test_escape_valve(monkeypatch, tmp_path):
    """HOTSPOT_IGNORE_LOCK=1 → 不读不写锁, 直接放行 (知情逃生口)。"""
    monkeypatch.setenv("HOTSPOT_IGNORE_LOCK", "1")
    lock = tmp_path / "hotspot.lock"
    lock.write_text(str(os.getpgid(0)))  # 明明有活实例
    assert il.acquire_instance_lock(lock) is None
    assert lock.read_text().strip() != ""  # 锁文件原样 (未参与)


def test_refuse_port_probe_covers_lockless_instance(tmp_path):
    """端口探活兜底: 守卫部署前的无锁在跑实例也被拒 (DEV-0293 现实场景)。"""
    import socket
    from contextlib import closing

    with closing(socket.socket()) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        with pytest.raises(SystemExit) as ei:
            il.refuse_if_locked(lock_path=tmp_path / "hotspot.lock", port=port)
        assert ei.value.code == 2


def test_refuse_passes_when_all_clear(tmp_path):
    """无锁无监听 → 正常放行 (写锁), 不抛 SystemExit。"""
    lock = tmp_path / "hotspot.lock"
    il.refuse_if_locked(lock_path=lock, port=0)  # port 0 不可 connect → 未持有
    assert lock.exists()


# ---------------------------------------------------------------------------
# DEV-0303 R4: 冲突进程组安全自动收割
# ---------------------------------------------------------------------------
_CURRENT_USER = getpass.getuser()


def _ps_rows(rows: list[str], monkeypatch):
    """mock ps 输出 (pid user pgid command)。"""

    class _Out:
        stdout = "\n".join(rows)

    monkeypatch.setattr(il.subprocess, "run", lambda *a, **k: _Out())


def test_group_members_parses_ps_output(monkeypatch):
    _ps_rows(
        [
            "  101  duke   4242  /usr/local/bin/python run.py",
            "  102  duke   4242  dsh --serve",
            "   77  duke      1  launchd",
        ],
        monkeypatch,
    )
    members = il._group_members(4242)
    assert [(p, u) for p, u, _ in members] == [(101, "duke"), (102, "duke")]
    assert "run.py" in members[0][2]


def test_looks_backend_signature():
    assert il._looks_backend(".venv/bin/python -m uvicorn backend.main:app")
    assert il._looks_backend("python run.py")
    assert not il._looks_backend("/bin/picom --daemon")  # 陌生进程不算
    assert not il._looks_backend("vim notes.txt")


def test_reap_dead_group_is_noop(monkeypatch):
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: False)
    assert il.reap_conflict_group(999) == (True, "group already dead")


def test_reap_refuses_without_backend_signature(monkeypatch):
    """组内全是陌生进程 → 不动手 (防 pgid 复用错杀)。"""
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(il, "_group_members", lambda pgid: [(100, _CURRENT_USER, "vim notes.txt")])
    ok, reason = il.reap_conflict_group(4242)
    assert ok is False
    assert "signature" in reason


def test_reap_refuses_foreign_user(monkeypatch):
    """组内有异主进程 → 不动手 (宁拒勿错杀)。"""
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(
        il,
        "_group_members",
        lambda pgid: [(100, _CURRENT_USER, "python run.py"), (101, "root", "dsh --serve")],
    )
    ok, reason = il.reap_conflict_group(4242)
    assert ok is False
    assert "foreign users" in reason and "root" in reason


def test_reap_refuses_unenumerable_alive_group(monkeypatch):
    """killpg 探活存活但 ps 枚举为空 → 不动手。"""
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(il, "_group_members", lambda pgid: [])
    ok, reason = il.reap_conflict_group(4242)
    assert ok is False
    assert "not enumerable" in reason


def test_reap_term_success(monkeypatch):
    """TERM 后组灭 → 收割成功, 只发 TERM。"""
    signals: list[int] = []
    alive_iters = iter([True, False])  # 首次探活: 活; TERM 后轮询: 灭
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: next(alive_iters))
    monkeypatch.setattr(il.os, "killpg", lambda pgid, sig: signals.append(sig))
    monkeypatch.setattr(il.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        il, "_group_members", lambda pgid: [(100, _CURRENT_USER, "python run.py")]
    )
    ok, detail = il.reap_conflict_group(4242)
    assert ok is True and "SIGTERM" in detail
    assert signals == [il.signal.SIGTERM]


def test_reap_escalates_to_kill(monkeypatch):
    """TERM 超时 → 逃逸 SIGKILL。"""
    signals: list[int] = []
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)  # 一直活着
    monkeypatch.setattr(il.os, "killpg", lambda pgid, sig: signals.append(sig))
    monkeypatch.setattr(il, "_group_members", lambda pgid: [(100, _CURRENT_USER, "python run.py")])
    ok, detail = il.reap_conflict_group(4242, term_wait=0.2, kill_wait=0.2)
    assert ok is False and "SIGKILL" in detail
    assert signals == [il.signal.SIGTERM, il.signal.SIGKILL]


def test_refuse_if_locked_autoreaps_then_proceeds(tmp_path, monkeypatch):
    """锁冲突 → 自动收割成功 → 重新取锁放行 (单命令重启语义)。"""
    results = iter([111, None])  # 首次 acquire: 冲突; 收割后 acquire: 通过
    monkeypatch.setattr(il, "acquire_instance_lock", lambda lock_path=None: next(results))
    reap_calls: list[int] = []
    monkeypatch.setattr(
        il,
        "reap_conflict_group",
        lambda pgid, **kw: reap_calls.append(pgid) or (True, "reaped after SIGTERM"),
    )
    monkeypatch.setattr(il, "_port_held", lambda port, host="127.0.0.1": False)
    il.refuse_if_locked(lock_path=tmp_path / "hotspot.lock", port=0)  # 不抛
    assert reap_calls == [111]


def test_refuse_if_locked_reap_refusal_exits(tmp_path, monkeypatch):
    """收割裁决不过 → 维持拒绝 (exit 2) 并保留清理指引。"""
    results = iter([111])
    monkeypatch.setattr(il, "acquire_instance_lock", lambda lock_path=None: next(results))
    monkeypatch.setattr(
        il, "reap_conflict_group", lambda pgid, **kw: (False, "no hotspot backend signature")
    )
    with pytest.raises(SystemExit) as ei:
        il.refuse_if_locked(lock_path=tmp_path / "hotspot.lock", port=0)
    assert ei.value.code == 2


# ---------------------------------------------------------------------------
# DEV-0306 R11: 锁产权 — 无后端签名的自家孤儿组也可收割
# ---------------------------------------------------------------------------
def test_reap_allows_unsigned_own_group_via_lock_ownership(monkeypatch):
    """父进程已被 SIGKILL, 组内只剩 dsh/pi 等无签名孤儿: 锁文件 pgid 匹配 +
    全员同用户 → 视为自家组放行收割 (防孤儿残留拒绝启动死锁)。"""
    signals: list[int] = []
    alive_iters = iter([True, False])
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: next(alive_iters))
    monkeypatch.setattr(il.os, "killpg", lambda pgid, sig: signals.append(sig))
    monkeypatch.setattr(il.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        il, "_group_members",
        lambda pgid: [(100, _CURRENT_USER, "node dsh/dev.mjs"),
                      (101, _CURRENT_USER, "chromium --headless")],
    )
    ok, detail = il.reap_conflict_group(4242, lock_pgid=4242)
    assert ok is True and "SIGTERM" in detail
    assert signals == [il.signal.SIGTERM]


def test_reap_unsigned_group_without_ownership_still_refused(monkeypatch):
    """无签名 + 锁不匹配 (pgid 复用给无关组) → 依旧拒绝 (防错杀不 Relax)。"""
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(
        il, "_group_members", lambda pgid: [(100, _CURRENT_USER, "node some_app.js")],
    )
    ok, reason = il.reap_conflict_group(4242, lock_pgid=9999)
    assert ok is False and "signature" in reason


def test_reap_own_group_foreign_user_still_refused(monkeypatch):
    """锁匹配但组内出现异主进程 → 用户裁决先于产权, 拒绝。"""
    monkeypatch.setattr(il, "_pgid_alive", lambda pgid: True)
    monkeypatch.setattr(
        il, "_group_members",
        lambda pgid: [(100, "root", "node dsh/dev.mjs")],
    )
    ok, reason = il.reap_conflict_group(4242, lock_pgid=4242)
    assert ok is False and "foreign users" in reason


def test_refuse_if_locked_passes_lock_pgid_ownership(tmp_path, monkeypatch):
    """refuse_if_locked 把锁文件 pgid 作为产权凭证传给收割 (R11 接线)。"""
    captured: dict = {}

    def _fake_reap(pgid, **kw):
        captured.update(kw, pgid=pgid)
        return False, "stub refuse"

    monkeypatch.setattr(il, "acquire_instance_lock", lambda lock_path=None: 777)
    monkeypatch.setattr(il, "reap_conflict_group", _fake_reap)
    with pytest.raises(SystemExit):
        il.refuse_if_locked(lock_path=tmp_path / "hotspot.lock", port=0)
    assert captured == {"pgid": 777, "lock_pgid": 777}
