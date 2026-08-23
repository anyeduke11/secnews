"""Tests for v0.5 M3.5 Task13 — graph.json 6 边运行时填入 + CI 校验。

覆盖:
- concept_linker.update_graph_from_item / update_graph_from_batch:
  uses 边共现累积 (weight + source_observation_count)、幂等、保留人工标注边
- concept_linker.validate_graph_schema: 6 种边类型 / weight / 节点引用 / 重复边
- batch_link_items 副作用: 处理后累积进 graph.json
- retention_engine.check_retention_health: >0.7 占比 ≥ 80% 健康检查
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import concept_linker as cl
from backend.services.retention_engine import check_retention_health


@pytest.fixture
def tmp_graph(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """把 GRAPH_PATH 重定向到临时目录 (避免污染真实 llm-wiki-2.0/graph.json)。"""
    graph_path = tmp_path / "llm-wiki-2.0" / "graph.json"
    monkeypatch.setattr(cl, "GRAPH_PATH", graph_path)
    return graph_path


def _load(graph_path: Path) -> dict:
    return json.loads(graph_path.read_text(encoding="utf-8"))


# ===================================================================
# update_graph_from_item / update_graph_from_batch
# ===================================================================

class TestGraphAccumulate:
    def test_single_item_creates_uses_edges(self, tmp_graph):
        """单个含 2 概念的条目 → 1 条 uses 边 (weight=1, source_observation_count=1)。"""
        stats = cl.update_graph_from_item("item-a", ["ai-agent", "ai-coding"])
        assert stats["nodes"] == 2
        assert stats["edges"] == 1
        assert stats["updated"] == 1
        g = _load(tmp_graph)
        edge = g["edges"][0]
        assert edge["type"] == "uses"
        assert edge["weight"] == 1
        assert edge["source_observation_count"] == 1

    def test_multi_item_accumulates_weight_and_count(self, tmp_graph):
        """两个条目共享同一概念对 → weight=2, source_observation_count=2。"""
        cl.update_graph_from_batch([
            {"id": "a", "concepts": ["ai-agent", "ai-coding"]},
            {"id": "b", "concepts": ["ai-agent", "ai-coding", "llm-security"]},
        ])
        g = _load(tmp_graph)
        assert len(g["edges"]) == 3  # a-b, a-c, b-c 三条 uses
        shared = next(
            e for e in g["edges"]
            if e["source"] == "ai-agent" and e["target"] == "ai-coding"
        )
        assert shared["weight"] == 2
        assert shared["source_observation_count"] == 2
        # 节点含全部 3 个概念
        assert {n["id"] for n in g["nodes"]} == {"ai-agent", "ai-coding", "llm-security"}

    def test_idempotent_replay_increments_not_duplicates(self, tmp_graph):
        """重复跑同一条目 → 同一条边 weight 递增, 不产生重复边。"""
        cl.update_graph_from_item("a", ["ai-agent", "ai-coding"])
        cl.update_graph_from_item("a", ["ai-agent", "ai-coding"])
        g = _load(tmp_graph)
        assert len(g["edges"]) == 1
        assert g["edges"][0]["weight"] == 2

    def test_single_concept_item_no_edge(self, tmp_graph):
        """概念数 < 2 的条目不产生边。"""
        tmp_graph.parent.mkdir(parents=True, exist_ok=True)
        tmp_graph.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
        stats = cl.update_graph_from_item("a", ["ai-agent"])
        assert stats["updated"] == 0
        assert _load(tmp_graph)["edges"] == []

    def test_preserves_manually_typed_edges(self, tmp_graph):
        """预先存在的人工标注边 (depends 等) 不被覆盖, 保留在结果中。"""
        tmp_graph.parent.mkdir(parents=True, exist_ok=True)
        tmp_graph.write_text(
            json.dumps({
                "$schema_version": "0.5.0",
                "nodes": [{"id": "x"}, {"id": "y"}],
                "edges": [{
                    "source": "x", "target": "y", "weight": 1,
                    "type": "depends", "source_observation_count": 1,
                }],
            }),
            encoding="utf-8",
        )
        cl.update_graph_from_item("a", ["x", "y", "z"])
        g = _load(tmp_graph)
        types = {e["type"] for e in g["edges"]}
        assert "depends" in types
        assert "uses" in types

    def test_batch_link_items_updates_graph_side_effect(self, tmp_graph, monkeypatch, tmp_path):
        """batch_link_items 处理后自动累积 graph (uses 边)。"""
        # 隔离概念 md 写入, 避免污染真实 knowledge/ 目录
        monkeypatch.setattr(cl, "CONCEPTS_DIR", tmp_path / "concepts")
        monkeypatch.setattr(cl, "ITEMS_DIR", tmp_path / "items")
        items = [
            {"id": "x1", "tags": ["Agent", "AI编程"]},
            {"id": "x2", "tags": ["Agent", "AI编程", "渗透测试"]},
        ]
        cl.batch_link_items(items)
        g = _load(tmp_graph)
        assert g["nodes"]  # 非空
        assert g["edges"]
        assert all(e["type"] == "uses" for e in g["edges"])
        # 所有边 source/target 都落在 nodes 里 (schema 可过)
        assert cl.validate_graph_schema(g) == []


# ===================================================================
# validate_graph_schema
# ===================================================================

class TestValidateGraphSchema:
    def test_empty_graph_valid(self):
        """空 nodes/edges → 通过。"""
        assert cl.validate_graph_schema({"nodes": [], "edges": []}) == []

    def test_unknown_edge_type_rejected(self):
        """v0.4 的 related 类型在 v0.5 规范中非法 (应归类为 uses)。"""
        graph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b", "weight": 1, "type": "related"}],
        }
        errors = cl.validate_graph_schema(graph)
        assert any("related" in e for e in errors)

    def test_all_six_types_accepted(self):
        """6 种边类型全部合法。"""
        nodes = [{"id": f"c{i}"} for i in range(7)]
        edges = [
            {"source": "c0", "target": "c1", "weight": 1, "type": t,
             "source_observation_count": 1}
            for t in ("uses", "depends", "contradicts", "caused", "fixed", "supersedes")
        ]
        assert cl.validate_graph_schema({"nodes": nodes, "edges": edges}) == []

    def test_missing_weight_rejected(self):
        """缺 weight → 报错。"""
        graph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b", "type": "uses"}],
        }
        assert cl.validate_graph_schema(graph)

    def test_missing_observation_count_rejected(self):
        """缺 source_observation_count → 报错。"""
        graph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b", "weight": 1, "type": "uses"}],
        }
        assert cl.validate_graph_schema(graph)

    def test_dangling_node_reference_rejected(self):
        """边指向不存在的节点 → 报错。"""
        graph = {
            "nodes": [{"id": "a"}],
            "edges": [{"source": "a", "target": "nope", "weight": 1,
                       "type": "uses", "source_observation_count": 1}],
        }
        errors = cl.validate_graph_schema(graph)
        assert any("nope" in e for e in errors)

    def test_duplicate_edge_rejected(self):
        """重复 (source,target,type) → 报错。"""
        edge = {"source": "a", "target": "b", "weight": 1, "type": "uses",
                "source_observation_count": 1}
        graph = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [edge, dict(edge)]}
        assert cl.validate_graph_schema(graph)


# ===================================================================
# retention_engine.check_retention_health
# ===================================================================

class TestCheckRetentionHealth:
    def _write(self, tmp_path: Path, entries: list[dict]) -> Path:
        p = tmp_path / "retention.json"
        p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        return p

    def test_empty_ok(self, tmp_path):
        """空 entries → ok (空知识库不算失败)。"""
        result = check_retention_health(self._write(tmp_path, []))
        assert result["ok"] is True
        assert result["total"] == 0

    def test_all_fresh_ok(self, tmp_path):
        """全 1.0 (刚迁移) → ok。"""
        entries = [{"id": f"i{i}", "current_score": 1.0} for i in range(10)]
        result = check_retention_health(self._write(tmp_path, entries))
        assert result["ok"] is True
        assert result["ratio"] == 1.0

    def test_mostly_healthy_ok(self, tmp_path):
        """9/10 > 0.7 → ok (≥80%)。"""
        entries = [{"id": f"i{i}", "current_score": 1.0 if i < 9 else 0.2}
                   for i in range(10)]
        result = check_retention_health(self._write(tmp_path, entries))
        assert result["ok"] is True
        assert result["ratio"] == 0.9

    def test_below_80_percent_fails(self, tmp_path):
        """6/10 > 0.7 → 失败 (<80%)。"""
        entries = [{"id": f"i{i}", "current_score": 1.0 if i < 6 else 0.1}
                   for i in range(10)]
        result = check_retention_health(self._write(tmp_path, entries))
        assert result["ok"] is False

    def test_stale_entries_ignored_by_decay_formula(self, tmp_path):
        """按 Ebbinghaus 衰减后的 current_score 判健康 (非 initial)。"""
        entries = [{"id": "i0", "initial_score": 1.0, "current_score": 0.65}]
        result = check_retention_health(self._write(tmp_path, entries))
        assert result["ok"] is False  # 0.65 < 0.7
