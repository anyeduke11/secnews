"""KL 管线入口复活 — 端到端回归测试 (治理 T4)。

意图锚定 (为什么这个测试必须存在):
2026-09-13 起知识入管断供 13 天, 根因是 warm.knowledge_items 表缺失
(所有 upsert/T1-T4 SELECT 静默抛 "no such table")。本文件把"一条知识
从入管到发布全程流动"锁成回归契约, 表缺失类断供将在此立即红灯:

场景 A: hotspot 采集产物 → knowledge_items(kl:raw) → T1→T2→T3→T4
        → kl:publish + md 落盘 lifecycle 正确 + wiki_events 留痕
场景 B: wiki URL 导入 → kickoff → kl_queue 挂 kl:refine 任务 (45s 延迟)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.config import config
from backend.kl_pipeline import KLPipeline
from backend.metrics.kl_metrics import kl_metrics
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.retry_policy import RetryPolicy
from backend.services.triggers import T1Trigger, T2Trigger, T3Trigger, T4Trigger
from backend.wiki_fs import WikiFs


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """单库模式临时 DB — 全链迁移 + 治理 T4 自愈后初始化。"""
    monkeypatch.setattr(config, "db_path", tmp_path / "e2e.db")
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "absent-warm.db")
    db_module.close_db()
    db_module.init_db()
    yield tmp_path
    db_module.close_db()


@pytest.fixture
def fresh_metrics():
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    yield kl_metrics
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()


@pytest.fixture
def md_items_dir(monkeypatch: pytest.MonkeyPatch, temp_db: Path):
    """md 落盘指向临时目录 — 不触碰生产 llm-wiki-2.0 (md 真源不可污染)。"""
    items_dir = temp_db / "wiki-items"
    items_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("backend.services.knowledge_sync.ITEMS_DIR", items_dir)
    return items_dir


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch):
    """mock LLM 评分/NER (治理约束: 测试不真调 ai_hub; 高分让 T4 门槛放行)。"""
    from backend.services import ai_hub

    def _fake_score(content: str, item_id: str) -> float:
        return 8.5

    def _fake_entities(content: str) -> list[str]:
        return []

    monkeypatch.setattr(ai_hub.llm_service, "score", _fake_score)
    monkeypatch.setattr(ai_hub.llm_service, "extract_entities", _fake_entities)
    return ai_hub


def _ingest_hotspot_as_knowledge(
    hotspot_id: str, title: str, *, hours_ago: int = 6
) -> None:
    """采集侧转化: hotspot → knowledge_items 入管 (lifecycle=kl:raw)。

    时间回拨: T1 有 5min debounce (ingested_at 必须早于 now-5min)。
    """
    conn = get_connection()
    now = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    conn.execute(
        """
        INSERT INTO knowledge_items
            (id, title, source, source_url, concepts, tags,
             mastery, compiled, ingested_at, updated_at, lifecycle)
        VALUES (?, ?, 'secnews', ?, '[]', '[]', 0, 0, ?, ?, 'kl:raw')
        """,
        (
            hotspot_id,
            title,
            f"https://example.test/{hotspot_id}",
            now.isoformat(),
            now.isoformat(),
        ),
    )


def _backdate_updated(item_id: str, hours: int = 25) -> None:
    """T4 稳定窗口 (updated_at ≥24h 前) — 推进链每跳都会 bump now, T4 前回拨。"""
    stale = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    get_connection().execute(
        "UPDATE knowledge_items SET updated_at = ? WHERE id = ?", (stale, item_id)
    )


def _lifecycle_of(item_id: str) -> str:
    row = get_connection().execute(
        "SELECT lifecycle FROM knowledge_items WHERE id = ?", (item_id,)
    ).fetchone()
    assert row is not None, f"{item_id} 不在管线中 (入管断供回归!)"
    return row["lifecycle"]


class TestIngestToPublishE2E:
    """场景 A: 一条知识流经 raw→refine→link→structure→publish 全阶段。"""

    def test_full_pipeline_revival(
        self, temp_db, md_items_dir, fresh_metrics, mock_llm
    ):
        item_id = "e2e-hotspot-001"
        _ingest_hotspot_as_knowledge(item_id, "治理 T4 端到端样例")

        t1 = T1Trigger(metrics=fresh_metrics, retry_policy=RetryPolicy(metrics=fresh_metrics))
        t2 = T2Trigger(metrics=fresh_metrics, retry_policy=RetryPolicy(metrics=fresh_metrics))
        t3 = T3Trigger(metrics=fresh_metrics, retry_policy=RetryPolicy(metrics=fresh_metrics))
        t4 = T4Trigger(metrics=fresh_metrics, retry_policy=RetryPolicy(metrics=fresh_metrics))

        assert t1.run_once()["advanced"] == 1
        assert _lifecycle_of(item_id) == "kl:refine"

        assert t2.run_once()["advanced"] == 1
        assert _lifecycle_of(item_id) == "kl:link"

        assert t3.run_once()["advanced"] == 1
        assert _lifecycle_of(item_id) == "kl:structure"

        _backdate_updated(item_id)  # 满足 T4 24h 稳定窗口
        assert t4.run_once()["advanced"] == 1
        assert _lifecycle_of(item_id) == "kl:publish"

        # md 真源落盘: lifecycle 正确、正文文件存在 (断供期间这一步从未发生)
        md_path = md_items_dir / f"{item_id}.md"
        assert md_path.exists(), "T4 发布必须落 md (md 真源哲学)"
        text = md_path.read_text(encoding="utf-8")
        assert 'lifecycle: "kl:publish"' in text

        # wiki_events 留痕: T4 发布的 agent_write (项目里唯一发布侧痕迹)
        row = get_connection().execute(
            "SELECT agent FROM wiki_events WHERE kind = 'agent_write' "
            "AND wiki_path = ?",
            (f"items/{item_id}.md",),
        ).fetchone()
        assert row is not None and row["agent"] == "trigger:t4"


class TestWikiImportKickoff:
    """场景 B: wiki URL 导入动作 → kickoff 入队 (kl_queue 链集成锚定)。"""

    def test_import_url_enqueues_refine_task(self, tmp_path, temp_db):
        root = str(tmp_path / "wiki")
        Path(root).mkdir(parents=True, exist_ok=True)
        wiki_fs = WikiFs(root)
        conn = get_connection()

        pipeline = KLPipeline(wiki_fs=wiki_fs, db_session=conn)
        result = wiki_fs.ingest_url("https://example.test/revive", title="R", text="body")
        pipeline.kickoff(result["id"])

        row = conn.execute(
            "SELECT item_id, stage, status, next_run_at FROM kl_queue "
            "WHERE item_id = ?",
            (result["id"],),
        ).fetchone()
        assert row is not None, "导入后必须挂起 kl:refine 任务 (kickoff 断供回归!)"
        assert row["stage"] == "kl:refine"
        assert row["status"] == "pending"
        # 45s 延迟防抖: next_run_at 晚于 now, 早于 now+60s
        next_run = datetime.fromisoformat(row["next_run_at"])
        now = datetime.now(timezone.utc)
        assert now < next_run < now + timedelta(seconds=60)
