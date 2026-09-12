#!/usr/bin/env python3
"""audit_practice_domain_sample — 实践域词表无偏人评采样 (审计类, DB 只读).

PRD P0.2 收敛: check_practice_domain_lexicon.py 是同源回归护栏 (不可证伪);
本脚本补上**无偏**一半 —— 从真实库采样近期资讯, 词表预打标, 交 owner 人工
标注真值后回读计算真实准确率。两段式:

  1) 采样   python scripts/audit_practice_domain_sample.py --sample 40
            → 只读采样 hotspots 近一周条目 (走 HotspotRepository, SELECT only),
              写 reports/practice_domain_review_<ts>.md (truth 列留空)

  2) 评分   owner 在报告中把 truth 列填上 (实践域 id 或 none), 然后:
            python scripts/audit_practice_domain_sample.py --grade <report.md>
            → 输出逐域准确率; < --min-accuracy (默认 0.8) exit 1 (PRD P0 口径)

采样走 repo 层 (SELECT only, 绝不写库)。报告含真实标题, 存 reports/
(与 dead_source_triage 等既有人工评审工件同级), 不入 dev_data。
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.domain.enums import TimeRange  # noqa: E402
from backend.repository.hotspot_repo import HotspotRepository  # noqa: E402
from backend.services.auto_classifier import (  # noqa: E402
    PRACTICE_DOMAINS,
    classify_practice_domain,
)

_REPORT_DIR = REPO_ROOT / "reports"
_NONE = "none"
_WINDOW_MAP = {"24h": TimeRange.H24, "3d": TimeRange.D3, "7d": TimeRange.D7, "30d": TimeRange.D30}


def sample(n: int, window: str) -> Path:
    time_range = _WINDOW_MAP[window]
    items, _cursor = HotspotRepository().query(
        category=None, time_range=time_range, limit=int(n),
    )

    ts = time.strftime("%Y%m%dT%H%M%S")
    out = _REPORT_DIR / f"practice_domain_review_{ts}.md"
    lines = [
        "# practice_domain 词表人评采样 (owner 专用)",
        "",
        f"- 采样时间: {time.strftime('%Y-%m-%d %H:%M')} · 窗口: {window} · 样本: {len(items)}",
        f"- 词表: 8 实践域 id = {', '.join(PRACTICE_DOMAINS)}; 非安全内容填 `{_NONE}`",
        "- 用法: 给每行 truth 列填入真值后, 运行 "
        "`python scripts/audit_practice_domain_sample.py --grade <本文件>`",
        "",
        "| id | title | predicted | truth |",
        "|---|---|---|---|",
    ]
    for it in items:
        predicted = classify_practice_domain([], title=it.title or "") or _NONE
        lines.append(f"| {it.id} | {it.title} | {predicted} |  |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"采样报告已写: {out} ({len(items)} 条, truth 列留空待标注)")
    return out


def grade(report_path: Path, min_accuracy: float) -> int:
    text = report_path.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("id",) or set(cells[0]) <= {"-"}:
            continue
        rows.append((cells[0], cells[1], cells[2], cells[3]))

    labeled = [(mid, title, pred, truth) for mid, title, pred, truth in rows if truth]
    if not labeled:
        print("ERROR: 报告中没有任何已标注的 truth 行; 请先人工填写 truth 列", file=sys.stderr)
        return 1

    hits: Counter = Counter()
    total: Counter = Counter()
    misses = []
    for mid, _title, pred, truth in labeled:
        total[truth] += 1
        if pred == truth:
            hits[truth] += 1
        else:
            misses.append((mid, truth, pred))
    accuracy = sum(hits.values()) / len(labeled)

    print("=== practice_domain 无偏人评结果 ===")
    print(f"已标注: {len(labeled)} / 共 {len(rows)} 行")
    for domain in sorted(total):
        print(f"  {domain:<22} {hits[domain]}/{total[domain]}")
    print(f"真实准确率: {sum(hits.values())}/{len(labeled)} = {accuracy:.0%}  (门槛 {min_accuracy:.0%})")
    if misses:
        print("不一致:")
        for mid, truth, pred in misses:
            print(f"  {mid}: truth={truth} predicted={pred}")
    if accuracy < min_accuracy:
        print("FAIL: 低于门槛 → 按 PRD P0 升级 LLM 分类或修订词表")
        return 1
    print("PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="实践域词表无偏人评采样 (DB 只读)")
    parser.add_argument("--sample", type=int, default=0, help="采样条数 (0=不采样)")
    parser.add_argument("--window", choices=sorted(_WINDOW_MAP), default="7d", help="采样窗口")
    parser.add_argument("--grade", type=Path, default=None, help="对已标注报告评分")
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    args = parser.parse_args()

    if args.grade:
        return grade(args.grade, args.min_accuracy)
    if args.sample > 0:
        sample(args.sample, args.window)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
