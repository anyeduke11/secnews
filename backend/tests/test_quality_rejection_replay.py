"""P1-5 拒收回放测试 (审计 F1-3 / PRD 验收: 任一拒收可看原文)。

契约 (Rule 9 WHY):
- strict 拒绝 (hard gate fail / score 不足) 必须落 gate_name='pipeline'
  标记行 — 这是回放查询锚; loose 模式无拒绝不落 (语义精确, 非 passed=0 泛化);
- 回放查询 LEFT JOIN raw_items — 原文在则回放原文, 缺则诚实 raw=None;
- per-gate passed=0 行 (soft 扣分, 条目仍 accepted) 不混入拒收回放。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.config import config as app_config
from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.config import QualityConfig, QualityMode
from backend.quality.pipeline import QualityGatePipeline
from backend.repository.db import close_db, get_connection, init_db
from backend.repository.quality_repo import QualityLogRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_rejection_replay.db"
    monkeypatch.setattr(app_config, "db_path", test_db)
    close_db()
    init_db()
    yield test_db
    close_db()


class _HardFailGate(BaseGate):
    gate_type = "hard"
    name = "hard_nope"

    def check(self, item, context):
        return GateResult(
            gate_name=self.name, passed=False, score_deduction=100,
            flags=["hard_nope"], reason="硬门禁不过",
        )


class _SoftFailGate(BaseGate):
    gate_type = "soft"
    name = "soft_nope"

    def check(self, item, context):
        return GateResult(
            gate_name=self.name, passed=False, score_deduction=45,
            flags=["soft_nope"], reason="软门禁扣分",
        )


def _item(item_id: str = "rej-1") -> HotspotItem:
    now = datetime.now(timezone.utc).isoformat()
    return HotspotItem(
        id=item_id, title="hi", summary="", source="web",
        url=f"https://example.com/{item_id}", category="ai",
        published_at=now, fetched_at=now,
    )


def _ctx() -> GateContext:
    return GateContext(
        mode="strict",
        category_keywords={"ai": ["AI"]},
        source_reputation={},
    )


def _pipeline(mode: QualityMode, gates) -> QualityGatePipeline:
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = mode == QualityMode.STRICT
    cfg._cache["min_score"] = 30
    return QualityGatePipeline(cfg, log_repo=QualityLogRepository(), gates=gates)


def _insert_raw(item_id: str, title: str = "被拒条目原文") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO raw_items "
        "(item_id, source_id, title, url, summary, content_hash, "
        " published_at, fetched_at) "
        "VALUES (?, 'src-1', ?, ?, '被拒条目摘要', 'abc', "
        " '2026-10-01T00:00:00+00:00', datetime('now'))",
        (item_id, title, f"https://example.com/{item_id}"),
    )
    conn.commit()


# ── pipeline 标记行 ─────────────────────────────────────────────────

def test_strict_hard_gate_reject_writes_pipeline_marker(temp_db):
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_HardFailGate()]).run_all(_item(), _ctx())
    conn = get_connection()
    row = conn.execute(
        "SELECT gate_name, passed, reason FROM quality_check_logs "
        "WHERE gate_name = 'pipeline'"
    ).fetchone()
    assert row is not None, "strict hard 拒绝必须落 pipeline 标记行"
    assert row["passed"] == 0
    assert "hard_nope" in row["reason"]


def test_strict_low_score_reject_writes_pipeline_marker(temp_db):
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_SoftFailGate(), _SoftFailGate()]).run_all(
            _item(), _ctx(),
        )  # -90 → score 10 < 30
    conn = get_connection()
    rows = conn.execute(
        "SELECT reason FROM quality_check_logs WHERE gate_name = 'pipeline'"
    ).fetchall()
    assert len(rows) == 1
    assert "score" in rows[0]["reason"]


def test_loose_mode_no_pipeline_marker(temp_db):
    """loose 无拒绝语义 — 不落标记行 (拒收回放不被扣分行污染)。"""
    _pipeline(QualityMode.LOOSE, [_SoftFailGate()]).run_all(_item(), _ctx())
    conn = get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs WHERE gate_name = 'pipeline'"
    ).fetchone()[0]
    assert n == 0


def test_soft_gate_failures_not_in_rejection_replay(temp_db):
    """per-gate passed=0 (soft 扣分, 条目仍 accepted) 不进回放查询。"""
    _pipeline(QualityMode.LOOSE, [_SoftFailGate()]).run_all(_item(), _ctx())
    items, total = QualityLogRepository().list_rejections()
    assert total == 0 and items == []


# ── 回放查询 JOIN raw_items ─────────────────────────────────────────

def test_rejection_replay_joins_raw_data(temp_db):
    """验收主断言: 拒收行带原文 (title/url/summary) 与原因。"""
    _insert_raw("rej-raw")
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_HardFailGate()]).run_all(
            _item("rej-raw"), _ctx(),
        )
    items, total = QualityLogRepository().list_rejections()
    assert total == 1
    r = items[0]
    assert r["item_id"] == "rej-raw"
    assert "硬门禁不过" in (r["reason"] or "")
    assert r["raw"] is not None
    assert r["raw"]["title"] == "被拒条目原文"
    assert r["raw"]["url"] == "https://example.com/rej-raw"
    assert r["raw"]["summary"] == "被拒条目摘要"


def test_rejection_replay_without_raw_is_honest_none(temp_db):
    """raw_items 无此条 (旧数据/写入失败) → raw=None, 不伪造原文。"""
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_HardFailGate()]).run_all(
            _item("rej-noraw"), _ctx(),
        )
    items, _ = QualityLogRepository().list_rejections()
    assert items[0]["raw"] is None
    assert items[0]["reason"]  # 原因仍在


def test_rejection_replay_window_excludes_old(temp_db):
    _insert_raw("rej-old")
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_HardFailGate()]).run_all(
            _item("rej-old"), _ctx(),
        )
    # 把 checked_at 拨到 30 天前
    conn = get_connection()
    conn.execute(
        "UPDATE quality_check_logs SET checked_at = ? "
        "WHERE gate_name = 'pipeline'",
        ("2026-09-01T00:00:00+00:00",),
    )
    conn.commit()
    items, total = QualityLogRepository().list_rejections(hours=24)
    assert total == 0 and items == []


# ── HTTP 契约 ───────────────────────────────────────────────────────

def test_api_rejections_e2e(e2e_api_client, temp_db):
    _insert_raw("rej-api")
    with pytest.raises(Exception):
        _pipeline(QualityMode.STRICT, [_HardFailGate()]).run_all(
            _item("rej-api"), _ctx(),
        )
    r = e2e_api_client.get("/api/quality/rejections?hours=168&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["item_id"] == "rej-api"
    assert item["raw"]["title"] == "被拒条目原文"
    assert item["reason"]


def test_api_rejections_empty_ok(e2e_api_client, temp_db):
    r = e2e_api_client.get("/api/quality/rejections")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "window_hours": 168}
