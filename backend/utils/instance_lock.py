"""单实例锁 (v0.8.8 dev即生产: 单实例硬不变量)。

背景 (DEV-0293 事故教训): run.py 父进程被 SIGTERM 后 uvicorn 子进程
(调度器线程所在) 可单独存活且不持端口 — lsof 端口检查完全测不出,
曾致双实例共写 SQLite 2h+ (账本污染 + 调度器双跑 + 冻结)。

机制: 锁文件记录启动进程组 (pgid)。启动时若锁内 pgid 的进程组仍有
存活成员 (含同组子进程) → 拒绝启动并给出清理命令; 进程组全灭 →
视为陈旧锁直接覆写。SIGKILL 场景锁文件残留由存活探测兜底, 无需
退出钩子。``HOTSPOT_IGNORE_LOCK=1`` 为知情逃生口。

DEV-0303 R4: 冲突进程组**安全自动收割** — 父进程被 SIGKILL 后 dsh/pi
等子进程成孤儿, pgid 探活能发现但此前只给手工指引。现在冲突时枚举
组成员做安全裁决 (全员同用户 + 存在 hotspot 后端签名), 通过则
TERM → 有界等待 → KILL 后继续启动; 组内有陌生进程则维持拒绝
(宁拒勿错杀, 防 pgid 复用误伤无关进程组)。
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# 后端进程签名: 组内至少一个成员命中才允许自动收割。
# dsh/pi 等子进程命令形态不定, 不进白名单 — 它们随组接收 killpg,
# 签名只用于裁决「这个组是不是我们的」。
_BACKEND_SIGNATURES = ("backend.main", "uvicorn", "run.py")


def default_lock_path() -> Path:
    """锁文件位置: 与 DB 同目录 (同生命周期, SQLite 双写防护语义一致)。"""
    from backend.config import config

    return Path(config.db_path).parent / "hotspot.lock"


def _pgid_alive(pgid: int) -> bool:
    """进程组是否仍有存活成员 (killpg signal=0 探测, 不实际发信号)。"""
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 组存在但不可探 (异主) — 按存活处理, 宁拒勿双写


def acquire_instance_lock(lock_path: Path | None = None) -> int | None:
    """获取单实例锁。

    Returns:
        None — 锁获取成功 (或 HOTSPOT_IGNORE_LOCK=1 逃生);
        int — 冲突的存活进程组 pgid (调用方应拒绝启动)。
    """
    if os.getenv("HOTSPOT_IGNORE_LOCK") == "1":
        return None

    path = lock_path or default_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            old_pgid = int(path.read_text().strip())
        except (ValueError, OSError):
            old_pgid = 0
        if old_pgid > 0 and _pgid_alive(old_pgid):
            return old_pgid
        # 陈旧锁 (进程组全灭 / 内容损坏) → 覆写

    try:
        path.write_text(str(os.getpgid(0)))
    except OSError:
        pass  # 锁不可写不阻断启动 (fail-open; 单实例靠运维纪律兜底)
    return None


def _port_held(port: int, host: str = "127.0.0.1") -> bool:
    """端口是否已有监听者 (connect 探活; 兜底覆盖无锁记录的在跑实例)。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


# ---------------------------------------------------------------------------
# DEV-0303 R4: 冲突进程组安全自动收割
# ---------------------------------------------------------------------------
def _group_members(pgid: int) -> list[tuple[int, str, str]]:
    """枚举进程组成员 → [(pid, user, command)]。ps 不可用时返回空表。

    用 ``ps -axo pid=,user=,pgid=,command=`` 全表解析后过滤 (macOS/BSD 与
    Linux 均支持头部抑制形式, 避开 ``ps -g`` 的 BSD 语义歧义)。
    """
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,user=,pgid=,command="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []
    members: list[tuple[int, str, str]] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid, user, member_pgid = int(parts[0]), parts[1], int(parts[2])
        except ValueError:
            continue
        if member_pgid == pgid:
            members.append((pid, user, parts[3]))
    return members


def _looks_backend(command: str) -> bool:
    """命令是否命中后端签名 (backend.main / uvicorn / run.py)。"""
    return any(sig in command for sig in _BACKEND_SIGNATURES)


def reap_conflict_group(
    pgid: int, *, term_wait: float = 6.0, kill_wait: float = 3.0
) -> tuple[bool, str]:
    """安全收割冲突进程组: TERM → 有界等待 → 逃逸 KILL。

    安全裁决 (任一不过 → 不动手):
    - 组内至少一个成员命中后端签名 (防 pgid 复用错杀无关组);
    - 组内成员全部属于当前用户。

    Returns:
        (True, detail)  — 组已灭 (收割成功或竞态自灭);
        (False, reason) — 裁决不过/收割失败, 调用方走拒绝路径。
    """
    if not _pgid_alive(pgid):
        return True, "group already dead"
    members = _group_members(pgid)
    if not members:
        # ps 枚举不到但 killpg 探活存活: 宁拒勿错杀
        return False, "group alive but members not enumerable via ps"
    if not any(_looks_backend(cmd) for _, _, cmd in members):
        return False, "no hotspot backend signature in group"
    import getpass

    current = {getpass.getuser(), str(os.getuid())}
    strangers = sorted({u for _, u, _ in members} - current)
    if strangers:
        return False, f"foreign users in group: {', '.join(strangers)}"

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as e:
        return _post_signal_settle(pgid, term_wait, kill_wait, f"TERM({e})")
    deadline = time.monotonic() + term_wait
    while time.monotonic() < deadline:
        if not _pgid_alive(pgid):
            return True, "reaped after SIGTERM"
        time.sleep(0.3)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + kill_wait
    while time.monotonic() < deadline:
        if not _pgid_alive(pgid):
            return True, "reaped after SIGKILL escalation"
        time.sleep(0.3)
    return False, "group survived SIGKILL — manual investigation required"


def _post_signal_settle(
    pgid: int, term_wait: float, kill_wait: float, detail: str
) -> tuple[bool, str]:
    """TERM 发送失败 (组可能刚灭) 后的兜底结算。"""
    deadline = time.monotonic() + min(term_wait, 3.0)
    while time.monotonic() < deadline:
        if not _pgid_alive(pgid):
            return True, f"group dead ({detail})"
        time.sleep(0.3)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return False, f"unreapable ({detail})"


def refuse_if_locked(lock_path: Path | None = None, port: int = 8000) -> None:
    """run.py 启动闸: 进程组锁 + 端口探活双检, 冲突时收割或拒绝启动。

    双检互补 (DEV-0293): pgid 锁抓「不持端口的僵尸调度器子进程」,
    端口探活抓「守卫部署前启动的无锁实例」。
    DEV-0303 R4: pgid 冲突先尝试安全自动收割 (孤儿自愈, 单命令重启),
    收割失败才打印清理指引并 exit 2。
    """
    conflict = acquire_instance_lock(lock_path)
    if conflict is not None:
        reaped, detail = reap_conflict_group(conflict)
        if not reaped:
            print(
                f"[instance-lock] 已有实例在运行 (进程组 {conflict}, 目标端口 {port}), "
                f"自动收割未通过安全裁决: {detail}。\n"
                f"  dev 即生产, 单实例硬约束 — 先清理再启动:\n"
                f"    kill -TERM -- -{conflict}   # 终止整个进程组 (含 uvicorn 子进程)\n"
                f"  确认清理: ps -o pid,pgid,command -g {conflict}\n"
                f"  知情强制启动: HOTSPOT_IGNORE_LOCK=1 (不推荐)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        print(f"[instance-lock] 冲突进程组 {conflict} 已自动收割: {detail}")
        # 组灭后重新取锁 (陈旧锁覆写为当前 pgid); 二次冲突按拒绝处理
        conflict = acquire_instance_lock(lock_path)
        if conflict is not None:
            print(
                f"[instance-lock] 收割后仍存在存活进程组 {conflict}, 放弃启动。",
                file=sys.stderr,
            )
            raise SystemExit(2)
    if _port_held(port):
        print(
            f"[instance-lock] 端口 {port} 已被监听 (该实例早于单实例守卫部署, 无锁记录)。\n"
            f"  dev 即生产, 单实例硬约束 — 定位并清理后再启动:\n"
            f"    lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
            f"  知情强制启动: HOTSPOT_IGNORE_LOCK=1 (不推荐)",
            file=sys.stderr,
        )
        raise SystemExit(2)


__all__ = [
    "acquire_instance_lock",
    "default_lock_path",
    "reap_conflict_group",
    "refuse_if_locked",
]
