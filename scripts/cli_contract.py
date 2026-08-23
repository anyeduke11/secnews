"""v0.5 M2-Task5: CLI 契约统一包装 (SPEC §6.1)。

8 个批处理子命令的 --json 输出统一为:
    { ok: bool, code: int, duration_ms: int, data: {...} }

子命令清单 (SPEC §1 M2-Task5):
    collect_all, map_rebuild, sm2_daily_push, db_diet,
    knowledge_classify, manual_collect, extract, verify_health

设计
----
- 不强制子命令存在: 没实现的子命令返 status=not_yet_implemented,
  ok=true (SPEC §6.1 关心契约形状, 不是要求今天全做完)
- 输出走 ``print`` + ``sys.exit(code)``; 子命令自己调 ``emit_envelope()``
- ``started_at`` 用 ``time.monotonic`` 防时钟漂移; duration_ms = 整数毫秒
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

# 退出码 (与 db_diet.py 对齐)
EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FATAL = 2


def emit_envelope(
    ok: bool,
    data: dict[str, Any],
    started_at: float,
    *,
    code: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """统一 --json 输出契约, 然后 sys.exit。

    Args:
        ok: 是否成功 (前端可据此走 fast path)。
        data: 业务数据 (子命令自定义 payload)。
        started_at: ``time.monotonic()`` 起始点 (传 ``time.monotonic()`` 即可)。
        code: 退出码 (默认 ok ? EXIT_OK : EXIT_PARTIAL; 可覆盖)。
        extra: 顶层追加字段 (如 warnings/notes)。
    """
    envelope: dict[str, Any] = {
        "ok": ok,
        "code": code if code is not None else (EXIT_OK if ok else EXIT_PARTIAL),
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "data": data,
    }
    if extra:
        envelope.update(extra)
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    sys.exit(envelope["code"])


def emit_not_implemented(command: str, started_at: float, notes: str = "") -> None:
    """SPEC §6.1 契约: 子命令不存在/未实现时也走 envelope 形状 (ok=true)。

    目的: 未来子命令一旦实现, 不破坏 front/back 端契约解析。
    """
    emit_envelope(
        ok=True,
        data={
            "command": command,
            "status": "not_yet_implemented",
            "notes": notes or f"{command} 子命令在 v0.4 通过 scheduler jobs / HTTP API 触发, 不需独立 CLI",
        },
        started_at=started_at,
        code=EXIT_OK,
    )


# 8 个 SPEC 列出的子命令注册表
# value: (已实现?, 模块路径, 实现函数)
# 实现函数签名为 ``run(args: list[str]) -> tuple[ok: bool, data: dict]``
SUBCOMMANDS: dict[str, dict[str, Any]] = {
    "collect_all": {
        "implemented": False,
        "notes": "v0.4 由 scheduler collect_all_job 触发; HTTP: POST /api/refresh",
    },
    "map_rebuild": {
        "implemented": False,
        "notes": "v0.4 由 map_rebuild_daily_job 触发",
    },
    "sm2_daily_push": {
        "implemented": False,
        "notes": "v0.4 由 sm2_daily_push_job 触发",
    },
    "db_diet": {
        "implemented": True,
        "notes": "scripts/db_diet.py — 按 retention.json 清理表",
    },
    "knowledge_classify": {
        "implemented": False,
        "notes": "v0.4 由 knowledge_classify_job 触发",
    },
    "manual_collect": {
        "implemented": True,
        "notes": "scripts/manual_collect.py — 一次性采集全部",
    },
    "extract": {
        "implemented": False,
        "notes": "v0.4 通过 POST /api/extract/hotspot/{id} 或 /api/extract/knowledge/{id} 触发",
    },
    "verify_health": {
        "implemented": False,
        "notes": "v0.4 通过 GET /api/maintenance/health 触发",
    },
}


__all__ = [
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_FATAL",
    "SUBCOMMANDS",
    "emit_envelope",
    "emit_not_implemented",
]