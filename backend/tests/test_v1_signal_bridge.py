"""P1-2a v1_signal_bridge 测试 — hotspots → 语义门 → material/signal/kl:raw stub。

验收口径 (PRD P1-2): 桥跑通即 v1_signals 有增量 (≥120/30d 的流量来源),
kl:raw stub 喂 T1 → ai_scores>0。幂等/拒收/窗口三边界锁死, 防回潮。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.repository.db import get_connection
from backend.services.v1_signal_bridge import run_hotspot_signal_bridge


@pytest.fixture(autouse=True)
def _default_score_unavailable(monkeypatch):
    """DEV-0284 score-first 后桥流程依赖 score 值 — 未显式 mock 的用例默认
    score=None (fail-open 语义), 防本机真实 pi/sensenova provider 泄入测试流
    (LLM 输出非确定, 曾致 idempotent 用例随活 LLM 评分摇摆)。"""

    from backend.services.ai_hub import gateway as gw_mod

    async def _none(content: str, hotspot_id: str = "") -> float | None:
        return None

    monkeypatch.setattr(gw_mod.llm_service, "score", _none)


def _seed_hotspot(
    hotspot_id: str, *,
    title: str = "CVE-2026-1234 漏洞通告",
    url: str | None = None,
    fetched_hours_ago: float = 1.0,
) -> None:
    conn = get_connection()
    fetched = (datetime.now(timezone.utc) - timedelta(hours=fetched_hours_ago)).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO hotspots "
        "(id, title, summary, source, url, category, published_at, fetched_at) "
        "VALUES (?, ?, '正文摘要内容', '测试源', ?, 'security', ?, ?)",
        (hotspot_id, title, url or f"https://example.com/{hotspot_id}", fetched, fetched),
    )
    conn.commit()


def test_bridge_creates_material_signal_and_kl_raw(temp_db) -> None:
    """主路径: hotspot → admission(neutral) → material+signal(unverified)+kl:raw stub。"""
    _seed_hotspot("h_1", url="https://x/1")
    summary = run_hotspot_signal_bridge(window_hours=24)
    assert summary["candidates"] >= 1
    assert summary["signals_committed"] >= 1
    assert summary["kl_stubs"] >= 1
    assert summary["error"] is None

    conn = get_connection()
    row = conn.execute(
        "SELECT s.status, s.confidence, m.url, m.source_kind FROM v1_signals s "
        "JOIN v1_materials m ON m.id = s.material_id"
    ).fetchone()
    assert row is not None
    assert row[0] == "unverified" and row[1] == "unverified"
    assert row[2] == "https://x/1" and row[3] == "url"

    # kl:raw stub 喂 T1 (评分链入口)
    ki = conn.execute(
        "SELECT lifecycle, title, source_url FROM knowledge_items WHERE id LIKE 'kl-%'"
    ).fetchone()
    assert ki is not None
    assert ki[0] == "kl:raw" and "CVE-2026-1234" in ki[1] and ki[2] == "https://x/1"


def test_bridge_idempotent_on_rerun(temp_db) -> None:
    """重复轮: 镜像命中跳过, 不重放信号/不重复 stub (RSS 重复抓取常态)。"""
    _seed_hotspot("h_2", url="https://x/2")
    first = run_hotspot_signal_bridge()
    assert first["signals_committed"] == 1

    second = run_hotspot_signal_bridge()
    assert second["mirrored"] >= 1
    assert second["signals_committed"] == 0 and second["kl_stubs"] == 0

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM v1_signals").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM v1_materials").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0] == 1


def test_bridge_deny_produces_no_trace(temp_db, monkeypatch) -> None:
    """语义门 deny → quarantine 留痕, material/signal/kl stub 一概不产。"""
    _seed_hotspot("h_3", url="https://x/3")
    from backend.services import v1_admission_service as adm_mod
    from backend.services.v1_admission_service import (
        AdmissionResult,
        AdmissionVerdict,
    )

    def _deny(self, material, rules=None):
        return AdmissionResult(
            verdict=AdmissionVerdict.DENY,
            material_id=material.get("id", ""),
            matched_rule=None,
            reason="deny for test",
        )

    monkeypatch.setattr(adm_mod.V1AdmissionService, "evaluate", _deny)
    summary = run_hotspot_signal_bridge()
    assert summary["denied"] >= 1
    assert summary["signals_committed"] == 0 and summary["kl_stubs"] == 0

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM v1_materials").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM v1_signals").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0] == 0


def test_bridge_window_excludes_stale(temp_db) -> None:
    """窗口外 (48h) 条目不进候选 — 桥只分流增量, 不回扫全库。"""
    _seed_hotspot("h_old", url="https://x/old", fetched_hours_ago=48)
    summary = run_hotspot_signal_bridge(window_hours=24)
    assert summary["candidates"] == 0
    assert summary["signals_committed"] == 0


def test_bridge_scores_admitted_items_into_ai_scores(temp_db, monkeypatch) -> None:
    """评分链契约 (P1-2a 定稿): 放行条目桥内直接 gateway.score → ai_scores 落行。

    采集管线采集时已写 content_fingerprints → T1 dedup 对 hotspot 派生 stub 恒拦,
    T1 评分环节永不触达主流供米 — 评分必须与生命周期解耦, 在桥内完成。
    """
    _seed_hotspot("h_4", url="https://x/4")

    import asyncio

    from backend.services.ai_hub import gateway as gw_mod

    async def _fake_score(content: str, hotspot_id: str = "") -> float | None:
        return 8.0

    monkeypatch.setattr(gw_mod.llm_service, "score", _fake_score)
    summary = run_hotspot_signal_bridge()
    assert summary["scored"] >= 1
    assert summary["score_skipped"] == 0

    conn = get_connection()
    row = conn.execute(
        "SELECT hotspot_id, score, scorer FROM ai_scores WHERE hotspot_id LIKE 'kl-%'"
    ).fetchone()
    assert row is not None
    assert row[1] == 8.0 and row[2] == "gateway.score"
    # ai_scores.hotspot_id 与 knowledge_items.id 对得上 (回溯链)
    assert conn.execute(
        "SELECT COUNT(*) FROM knowledge_items WHERE id = ?", (row[0],)
    ).fetchone()[0] == 1
    asyncio.get_event_loop  # noqa: B018 — asyncio import 供 monkeypatch 作用域一致性


def test_bridge_score_unavailable_writes_nothing(temp_db, monkeypatch) -> None:
    """P0-6/E3: 评分失败 → None → 诚实不写 (不落 5.0 假成功, 只计数)。"""
    _seed_hotspot("h_5", url="https://x/5")

    from backend.services.ai_hub import gateway as gw_mod

    async def _fail_score(content: str, hotspot_id: str = "") -> float | None:
        return None

    monkeypatch.setattr(gw_mod.llm_service, "score", _fail_score)
    summary = run_hotspot_signal_bridge()
    assert summary["signals_committed"] >= 1  # 分流不受评分影响
    assert summary["scored"] == 0 and summary["score_skipped"] >= 1
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM ai_scores").fetchone()[0] == 0


def test_bridge_low_score_denied_by_score(temp_db, monkeypatch) -> None:
    """DEV-0284 轨②: score < X=2.5 → quarantine 留痕, 不产信号/stub (owner 三裁决)。

    评分前置于信号产出; 低分条目只落 admission_log (deny + score 理由),
    kl:raw 不建 (避免 T4 永不推进的死库存)。
    """
    _seed_hotspot("h_low", url="https://x/low")

    from backend.services.ai_hub import gateway as gw_mod

    async def _low_score(content: str, hotspot_id: str = "") -> float | None:
        return 2.0

    monkeypatch.setattr(gw_mod.llm_service, "score", _low_score)
    summary = run_hotspot_signal_bridge()
    assert summary["denied_by_score"] == 1
    assert summary["signals_committed"] == 0 and summary["kl_stubs"] == 0
    # score 已落 (评分先于门槛判定, ai_scores 是门槛的输入)
    assert summary["scored"] == 1

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM v1_signals").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0] == 0
    # quarantine 留痕带 score 理由 (可回放)
    q = conn.execute(
        "SELECT verdict, reason FROM admission_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert q is not None and q[0] == "deny"
    assert "score_below_threshold" in (q[1] or "")


def test_bridge_score_equal_threshold_passes(temp_db, monkeypatch) -> None:
    """边界: score == X → 放行 (>= 语义, 不吃等号)。"""
    _seed_hotspot("h_eq", url="https://x/eq")

    from backend.services.ai_hub import gateway as gw_mod

    async def _eq_score(content: str, hotspot_id: str = "") -> float | None:
        return 2.5

    monkeypatch.setattr(gw_mod.llm_service, "score", _eq_score)
    summary = run_hotspot_signal_bridge()
    assert summary["denied_by_score"] == 0
    assert summary["signals_committed"] == 1 and summary["kl_stubs"] == 1


def test_migration_132_ai_scores_accepts_kl_ids(temp_db) -> None:
    """DEV-0268 根因锁: ai_scores 剥跨域 FK 后 kl-* id 可评分落行 (原 FK→hotspots 恒炸)。"""
    from backend.services.ai_write_back import write_score

    conn = get_connection()
    assert conn.execute(
        "PRAGMA foreign_key_list(ai_scores)"
    ).fetchall() == []  # 无跨域 FK
    row_id = write_score("kl-nonexistent", 7.5, reason="t1 llm", scorer="llm_service")
    assert row_id is not None  # 原 FK 下恒 None (IntegrityError 被吞)
    row = conn.execute(
        "SELECT hotspot_id, score, scorer FROM ai_scores WHERE id = ?", (row_id,)
    ).fetchone()
    assert row[0] == "kl-nonexistent" and row[1] == 7.5
