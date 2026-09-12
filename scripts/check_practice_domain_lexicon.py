#!/usr/bin/env python3
"""check_practice_domain_lexicon — 实践域词表评测 (检查类, 只读).

读取 backend/tests/fixtures/practice_domain_eval.json (20 条带真值域的
评测条目, DEV-0176/PRD P0.2), 用 classify_practice_domain 对 title+tags
重新打标并与真值比对。

诚实口径: 该语料与词表同源 (tag 命中条目按构造即为正确), 作用是**回归护栏**
(词表改动后此脚本必须保持 100%), 不是无偏准确率评估; 无偏评估需对真实语料
人评 (PRD P1 词表运营机制)。

用法:
    python scripts/check_practice_domain_lexicon.py            # 报告模式
    python scripts/check_practice_domain_lexicon.py --check    # CI 模式: 违规 exit 1

检查项 (任一失败 exit 1):
  1. 语料存在且共 20 条
  2. 每个实践域 ≥2 条
  3. 真值域都在 PRACTICE_DOMAINS 内
  4. 词表重打标准确率 100% (同源回归护栏)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_SEED = REPO_ROOT / "backend" / "tests" / "fixtures" / "practice_domain_eval.json"
EXPECTED_EVAL_COUNT = 24
MIN_PER_DOMAIN = 2


def main() -> int:
    parser = argparse.ArgumentParser(description="实践域词表评测 (只读)")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--check", action="store_true", help="CI 模式: 违规 exit 1")
    args = parser.parse_args()

    from backend.services.auto_classifier import (
        PRACTICE_DOMAINS,
        classify_practice_domain,
    )

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    corpus = seed.get("entries") or []
    problems: list[str] = []

    # 1. 语料规模
    if len(corpus) != EXPECTED_EVAL_COUNT:
        problems.append(f"评测条目数 {len(corpus)} != {EXPECTED_EVAL_COUNT}")

    # 3. 真值域合法
    illegal = [e["material_id"] for e in corpus if e.get("practice_domain") not in PRACTICE_DOMAINS]
    if illegal:
        problems.append(f"真值域越界: {illegal}")

    # 2. 每域覆盖
    coverage = Counter(e["practice_domain"] for e in corpus)
    thin = [d for d in PRACTICE_DOMAINS if coverage.get(d, 0) < MIN_PER_DOMAIN]
    if thin:
        problems.append(f"域覆盖不足 (每域 ≥{MIN_PER_DOMAIN}): {thin}")

    # 4. 重打标比对
    hits: Counter = Counter()
    total_by_domain: Counter = Counter()
    misses: list[tuple[str, str, str]] = []
    for e in corpus:
        predicted = classify_practice_domain(e.get("tags") or [], title=e.get("title", ""))
        truth = e["practice_domain"]
        total_by_domain[truth] += 1
        if predicted == truth:
            hits[truth] += 1
        else:
            misses.append((e["material_id"], truth, predicted or "None"))
    accuracy = sum(hits.values()) / len(corpus) if corpus else 0.0

    # 报告
    print("=== practice_domain 词表评测 ===")
    print(f"语料: {len(corpus)} 条  (seed: {args.seed.name})")
    for domain in PRACTICE_DOMAINS:
        n, ok = total_by_domain[domain], hits[domain]
        mark = "OK " if n >= MIN_PER_DOMAIN and ok == n else ("THIN" if n < MIN_PER_DOMAIN else "MISS")
        print(f"  {domain:<22} {ok}/{n}  [{mark}]")
    print(f"准确率: {sum(hits.values())}/{len(corpus)} = {accuracy:.0%}")
    if misses:
        print("不一致条目:")
        for mid, truth, pred in misses:
            print(f"  {mid}: truth={truth} predicted={pred}")
    if accuracy < 1.0:
        problems.append(f"重打标准确率 {accuracy:.0%} < 100% (词表与语料漂移, 同源回归护栏被破坏)")

    if problems:
        print("\n问题:")
        for p in problems:
            print(f"  - {p}")
        if args.check:
            print("CHECK FAILED")
            return 1
    else:
        print("\n全部检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
