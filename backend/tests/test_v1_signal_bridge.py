"""P1-2a v1_signal_bridge 测试 — hotspots → 语义门 → material/signal/kl:raw stub。

验收口径 (PRD P1-2): 桥跑通即 v1_signals 有增量 (≥120/30d 的流量来源),
kl:raw stub 喂 T1 → ai_scores>0。幂等/拒收/窗口三边界锁死, 防回潮。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.repository.db import get_connection
from backend.services.v1_signal_bridge import run_hotspot_signal_bridge


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
