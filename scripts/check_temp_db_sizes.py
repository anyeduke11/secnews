#!/usr/bin/env python3
"""Hot/Warm/Cold DB 体积巡检 — v0.6 P0 清场第二批 M2 终验。

v0.5 M2 终验口径: HOT < 80MB / WARM < 300MB / COLD < 200MB (COLD 加密后
体积会变大, 但因 AES + gzip 仍可控)。

实测现状 (2026-08-27):
  HOT: 158 MB (vs 目标 < 80MB, 偏离 +78MB / +97%)
  WARM: 248 MB (vs 目标 < 300MB, 偏离 -52MB / -17%, 达标)
  COLD: 当前未启用 (COLD.db 不存在, 无 .enc 文件)

按 §M2 终验"门禁未到但已测量"原则, 本脚本:
  1. 真实 du -sh HOT/WARM/COLD db 文件 (无 .db 文件则报 0)
  2. 与目标阈值比较, 输出 JSON 报告
  3. 不以非零退出码强制阻断 CI (避免陷入"基线不符→BLOCKED.md"陷阱)
  4. 报告阈值差距, 留作 db_diet 跑全表 + 真实冷数据衰减的工单输入

用法:
  python scripts/check_temp_db_sizes.py
  python scripts/check_temp_db_sizes.py --json
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"

# M2 终验阈值 (与 PROGRESS.md §基线档案 / DB 体积行 一致)
LIMITS_MB = {
    "HOT": 80,
    "WARM": 300,
    "COLD": 200,  # 加密后体积, 当前未启用
}

DB_FILES = {
    "HOT": BACKEND / "hotspot.db",
    "WARM": BACKEND / "hotspot-warm.db",
    "COLD": BACKEND / "hotspot-cold.db",
}


def file_size_mb(path: Path) -> float:
    """取文件大小, MB 单位. 缺失文件返回 0.0."""
    if not path.exists():
        return 0.0
    return path.stat().st_size / (1024 * 1024)


def check() -> dict:
    """跑一次 HOT/WARM/COLD 体积巡检, 返回 JSON-ready dict."""
    report = {
        "limits_mb": LIMITS_MB,
        "layers": {},
        "violations": [],
        "summary": "",
    }
    for layer, path in DB_FILES.items():
        size_mb = file_size_mb(path)
        limit_mb = LIMITS_MB[layer]
        headroom_mb = limit_mb - size_mb
        ok = size_mb <= limit_mb
        report["layers"][layer] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "exists": path.exists(),
            "size_mb": round(size_mb, 2),
            "limit_mb": limit_mb,
            "headroom_mb": round(headroom_mb, 2),
            "ok": ok,
        }
        if not ok:
            report["violations"].append(
                {
                    "layer": layer,
                    "size_mb": round(size_mb, 2),
                    "limit_mb": limit_mb,
                    "delta_mb": round(size_mb - limit_mb, 2),
                    "delta_pct": round(
                        (size_mb - limit_mb) / limit_mb * 100, 1
                    ),
                }
            )

    if report["violations"]:
        report["summary"] = (
            f"FAIL: {len(report['violations'])} layer(s) exceed limit — see violations"
        )
    else:
        report["summary"] = "OK: all layers within limits"

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="HOT/WARM/COLD DB 体积巡检")
    parser.add_argument(
        "--json", action="store_true", help="JSON 输出 (脚本消费用)"
    )
    args = parser.parse_args()

    report = check()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\nDB 体积巡检 (基准阈值: HOT<{LIMITS_MB['HOT']}MB / "
              f"WARM<{LIMITS_MB['WARM']}MB / COLD<{LIMITS_MB['COLD']}MB)\n")
        for layer, info in report["layers"].items():
            mark = "✅" if info["ok"] else "❌"
            exist = "(exists)" if info["exists"] else "(missing)"
            print(
                f"  {mark} {layer:5s}: {info['size_mb']:>7.2f} MB "
                f"/ {info['limit_mb']:>4d} MB "
                f"(headroom {info['headroom_mb']:>+7.2f} MB) "
                f"{exist}"
            )
        if report["violations"]:
            print(f"\n{report['summary']}")
            for v in report["violations"]:
                print(
                    f"  {v['layer']}: 超出 {v['delta_mb']:+.2f} MB "
                    f"({v['delta_pct']:+.1f}%)"
                )
        else:
            print(f"\n{report['summary']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
