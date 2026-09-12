"""DEV-0176b — 实践域评测语料结构测试 (Workbench Focus PRD P0.2)。

关闭 v1.0 T00 悬置裁决"标注集 60-80": 最终形态 80 =
  60 admission 标注 (dev_data 本地资产, 不入仓) +
  20 practice_domain 评测条目 (本 fixture, 入仓, 每域 ≥2)。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from backend.services.auto_classifier import PRACTICE_DOMAINS

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "practice_domain_eval.json"


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["entries"]


class TestPracticeDomainEvalCorpus:
    def test_exactly_24_entries(self, corpus: list[dict]):
        assert len(corpus) == 24

    def test_every_domain_covered_at_least_twice(self, corpus: list[dict]):
        coverage = Counter(e["practice_domain"] for e in corpus)
        for domain in PRACTICE_DOMAINS:
            assert coverage.get(domain, 0) >= 2, f"域 {domain} 覆盖不足 2 条"

    def test_truth_domains_valid_and_required_fields_present(self, corpus: list[dict]):
        for e in corpus:
            assert e["practice_domain"] in PRACTICE_DOMAINS, e["material_id"]
            assert e.get("title"), e["material_id"]
            assert isinstance(e.get("tags"), list), e["material_id"]

    def test_material_ids_unique(self, corpus: list[dict]):
        ids = [e["material_id"] for e in corpus]
        assert len(ids) == len(set(ids))
