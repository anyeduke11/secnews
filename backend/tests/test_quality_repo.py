"""Phase 3.5 quality repo + base 模型单元测试。

- GateResult / PipelineResult / BaseGate 基础
- QualityLogRepository 写日志 / 24h 统计
- SourceReputationRepository 读写 / rebuild
- 002_quality.sql 迁移（自动 init_db 后应建表）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.domain.collection import GateResult, PipelineResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.config import (
    DEFAULT_CATEGORY_KEYWORDS,
    QualityConfig,
    QualityMode,
    default_category_keywords,
    get_category_keywords,
)
from backend.repository import db
from backend.repository.quality_repo import (
    QualityLogRepository,
    SourceReputationRepository,
)


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "quality.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


def _make_item(id_: str = "qr1", **kw) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=kw.get("title", "OpenAI releases new GPT agent"),
        summary=kw.get("summary", "OpenAI GPT new model"),
        source=kw.get("source", "src_a"),
        url=kw.get("url", f"https://e.com/{id_}"),
        category=kw.get("category", Category.AI),
        published_at=now,
        fetched_at=now,
    )


# ---------------------------------------------------------------------------
# 002_quality.sql 迁移
# ---------------------------------------------------------------------------
def test_migration_creates_quality_tables(temp_db):
    conn = db.get_connection()
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "quality_check_logs" in tables
    assert "source_reputation" in tables


def test_migration_creates_quality_indexes(temp_db):
    conn = db.get_connection()
    idx = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    ]
    for expected in ("idx_qcl_item", "idx_qcl_gate", "idx_qcl_time"):
        assert expected in idx, f"missing index: {expected}"


def test_migration_seeds_source_reputation(temp_db):
    """默认应写入 5 个 source（每个 collector 一个）。"""
    conn = db.get_connection()
    rows = conn.execute("SELECT source FROM source_reputation").fetchall()
    sources = {r["source"] for r in rows}
    assert "ai_collector_default" in sources
    assert "security_collector_default" in sources
    assert "finance_collector_default" in sources
    assert "startup_collector_default" in sources
    assert "bid_collector_default" in sources


def test_migration_seeds_quality_settings(temp_db):
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE 'quality.%'"
    ).fetchall()
    keys = {r["key"] for r in rows}
    for required in (
        "quality.strict_mode",
        "quality.min_score",
        "quality.url_check_sample_rate",
        "quality.url_check_concurrency",
        "quality.url_check_timeout",
        "quality.category_keywords.ai",
        "quality.category_keywords.security",
    ):
        assert required in keys, f"missing setting: {required}"


# ---------------------------------------------------------------------------
# GateResult / PipelineResult 模型
# ---------------------------------------------------------------------------
def test_gate_result_defaults():
    r = GateResult(gate_name="t")
    assert r.passed is True
    assert r.score_deduction == 0
    assert r.flags == []
    assert r.reason is None
    assert r.error_msg is None


def test_pipeline_result_defaults():
    r = PipelineResult(item_id="x")
    assert r.final_score == 100
    assert r.accepted is True
    assert r.mode == "loose"


# ---------------------------------------------------------------------------
# BaseGate 抽象
# ---------------------------------------------------------------------------
def test_base_gate_is_abstract():
    with pytest.raises(TypeError):
        BaseGate()


# ---------------------------------------------------------------------------
# QualityLogRepository
# ---------------------------------------------------------------------------
def test_quality_log_repo_write_log(temp_db):
    repo = QualityLogRepository()
    r = GateResult(
        gate_name="schema",
        passed=False,
        score_deduction=20,
        flags=["category_mismatch"],
        reason="no kw",
    )
    repo.write_log("item-1", r, mode="loose")

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT gate_name, passed, score_deduction, flags, mode "
        "FROM quality_check_logs WHERE item_id = ?",
        ("item-1",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["gate_name"] == "schema"
    assert rows[0]["passed"] == 0
    assert rows[0]["score_deduction"] == 20
    assert json.loads(rows[0]["flags"]) == ["category_mismatch"]


def test_quality_log_repo_list_for_item(temp_db):
    repo = QualityLogRepository()
    for i in range(3):
        repo.write_log(
            "item-x",
            GateResult(gate_name=f"g{i}", passed=True),
        )
    out = repo.list_for_item("item-x", limit=10)
    assert len(out) == 3
    assert {r["gate_name"] for r in out} == {"g0", "g1", "g2"}


def test_quality_log_repo_summary_24h(temp_db):
    repo = QualityLogRepository()
    repo.write_log("a", GateResult(gate_name="schema", passed=True, score_deduction=0))
    repo.write_log("b", GateResult(gate_name="schema", passed=False, score_deduction=20))
    summary = repo.summary_24h()
    assert "schema" in summary
    assert summary["schema"]["total"] == 2
    assert summary["schema"]["pass"] == 1


def test_quality_log_repo_write_log_does_not_throw(temp_db, monkeypatch):
    """写 log 失败不抛（不阻塞采集）。"""
    from backend.repository import quality_repo as qr_mod

    # 替换 get_connection，让 conn.execute 抛错
    class _BoomConn:
        def execute(self, *args, **kwargs):
            raise RuntimeError("simulated failure")

    monkeypatch.setattr(qr_mod, "get_connection", lambda: _BoomConn())
    repo = QualityLogRepository()
    # 不应抛
    try:
        repo.write_log("zzz", GateResult(gate_name="schema", passed=True))
    except Exception as e:
        pytest.fail(f"write_log should not raise, got {e}")


# ---------------------------------------------------------------------------
# SourceReputationRepository
# ---------------------------------------------------------------------------
def test_source_reputation_repo_get_many_includes_known_only(temp_db):
    repo = SourceReputationRepository()
    # 先 seed 几条
    repo.upsert("s1", score=80, blacklist=0, pass_count=5, fail_count=1)
    repo.upsert("s2", score=40, blacklist=0, pass_count=2, fail_count=3)
    out = repo.get_many(["s1", "s2", "s_unknown"])
    assert "s1" in out
    assert "s2" in out
    assert "s_unknown" not in out
    assert out["s1"]["score"] == 80


def test_source_reputation_rebuild_no_logs_returns_zero(temp_db):
    repo = SourceReputationRepository()
    n = repo.rebuild_all()
    assert n == 0


def test_source_reputation_rebuild_computes_score(temp_db):
    """有 4 pass 1 fail → score 接近 80。"""
    # 先写一条 hotspot
    from backend.repository.hotspot_repo import HotspotRepository

    hrepo = HotspotRepository()
    item = _make_item(id_="rb1", source="src_rb")
    hrepo.upsert_many([item])

    log_repo = QualityLogRepository()
    for i in range(5):
        log_repo.write_log(
            "rb1",
            GateResult(
                gate_name="content",
                passed=(i < 4),
                score_deduction=0 if i < 4 else 20,
            ),
        )

    repo = SourceReputationRepository()
    n = repo.rebuild_all()
    assert n == 1
    info = repo.get("src_rb")
    assert info is not None
    # fail=1, pass=4 → score = 100 - 100*1/(4+1+1) ≈ 83
    assert 70 <= info["score"] <= 90


# ---------------------------------------------------------------------------
# QualityConfig
# ---------------------------------------------------------------------------
def test_default_category_keywords_returns_copy():
    k1 = default_category_keywords()
    k2 = default_category_keywords()
    assert k1 is not k2
    k1["ai"].append("INJECTED")
    assert "INJECTED" not in default_category_keywords()["ai"]


def test_get_category_keywords_fallback(temp_db):
    """settings 表已有值时取之；缺失走默认。"""
    # 默认有
    kws = get_category_keywords(Category.AI)
    assert isinstance(kws, list)
    assert "OpenAI" in kws or "AI" in kws


def test_quality_config_mode_default_loose(temp_db):
    cfg = QualityConfig()
    assert cfg.mode == QualityMode.LOOSE


def test_quality_config_strict_when_set(temp_db):
    from backend.repository.settings_repo import SettingsRepository

    SettingsRepository().set("quality.strict_mode", True)
    cfg = QualityConfig()
    assert cfg.mode == QualityMode.STRICT


def test_default_category_keywords_contains_all_7():
    """Phase 25 P1: 'tech' 加入 → 7 个分类关键词。"""
    kws = default_category_keywords()
    assert set(kws.keys()) == {
        "ai",
        "security",
        "finance",
        "startup",
        "bid",
        "github",
        "tech",
    }
