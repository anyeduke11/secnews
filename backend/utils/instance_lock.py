"""单实例锁 (v0.8.8 dev即生产: 单实例硬不变量)。

背景 (DEV-0293 事故教训): run.py 父进程被 SIGTERM 后 uvicorn 子进程
(调度器线程所在) 可单独存活且不持端口 — lsof 端口检查完全测不出,
曾致双实例共写 SQLite 2h+ (账本污染 + 调度器双跑 + 冻结)。

机制: 锁文件记录启动进程组 (pgid)。启动时若锁内 pgid 的进程组仍有
存活成员 (含同组子进程) → 拒绝启动并给出清理命令; 进程组全灭 →
视为陈旧锁直接覆写。SIGKILL 场景锁文件残留由存活探测兜底, 无需
退出钩子。``HOTSPOT_IGNORE_LOCK=1`` 为知情逃生口。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


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


def refuse_if_locked(lock_path: Path | None = None, port: int = 8000) -> None:
    """run.py 启动闸: 进程组锁 + 端口探活双检, 冲突时打印清理指引并 exit 2。

    双检互补 (DEV-0293): pgid 锁抓「不持端口的僵尸调度器子进程」,
    端口探活抓「守卫部署前启动的无锁实例」。
    """
    conflict = acquire_instance_lock(lock_path)
    if conflict is not None:
        print(
            f"[instance-lock] 已有实例在运行 (进程组 {conflict}, 目标端口 {port})。\n"
            f"  dev 即生产, 单实例硬约束 — 先清理再启动:\n"
            f"    kill -TERM -- -{conflict}   # 终止整个进程组 (含 uvicorn 子进程)\n"
            f"  确认清理: ps -o pid,pgid,command -g {conflict}\n"
            f"  知情强制启动: HOTSPOT_IGNORE_LOCK=1 (不推荐)",
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


__all__ = ["acquire_instance_lock", "default_lock_path", "refuse_if_locked"]
