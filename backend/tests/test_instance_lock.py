"""单实例锁测试 (v0.8.8 dev即生产; DEV-0293 双实例事故防线)。

不变量: 同进程组残留 (含不持端口的 uvicorn 子进程) 必须被拒绝启动 —
端口检查对此类僵尸失效, pgid 存活探测是唯一可靠闸。
"""
from __future__ import annotations

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
