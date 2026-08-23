#!/usr/bin/env python3
"""CI 校验 llm-wiki-2.0/retention.json 健康度 (v0.5 M3.5 Task12/13)。

规则 (wiki v2 §11 / SPEC M3.5): current_score > 0.7 的条目占比 ≥ 80%。
空条目 (知识库尚未填充) 视为通过。

用法::

    python scripts/check_retention_decay.py      # exit 0 = 通过, 1 = 失败
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETENTION_PATH = ROOT / "llm-wiki-2.0" / "retention.json"

# 轻量 import (retention_engine 顶层只依赖 stdlib, 无后端副作用)
sys.path.insert(0, str(ROOT))
from backend.services.retention_engine import (
    RETENTION_HEALTHY_MIN_RATIO,
    RETENTION_HEALTHY_THRESHOLD,
    check_retention_health,
)


def main() -> int:
    if not RETENTION_PATH.exists():
        print(f"SKIP: {RETENTION_PATH} 不存在, 通过")
        return 0
    result = check_retention_health(RETENTION_PATH)
    total = result["total"]
    healthy = result["healthy"]
    ratio = result["ratio"]
    if not result["ok"]:
        print(
            f"FAIL: retention 健康度不达标 — {healthy}/{total} entries > "
            f"{RETENTION_HEALTHY_THRESHOLD} (ratio {ratio}, 要求 ≥ "
            f"{RETENTION_HEALTHY_MIN_RATIO})",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: retention 健康度达标 — {healthy}/{total} entries > "
        f"{RETENTION_HEALTHY_THRESHOLD} (ratio {ratio})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
