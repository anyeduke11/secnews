"""v0.8.8 R-17 C2.3 只写阶段: ``hotspots`` → ``llm-wiki-2.0/feed/{yyyy-mm}.md``。

测试意图 (WHY, 而非 WHAT):
- 沉降阶段**不得删 DB 行** —— 删行必须等 C2.4 重建管道通过「删库 → 重建 →
  行数一致」验收后才能开启 (RA-14)。只断言「md 写出来了」拦不住误删,
  必须同时断言行仍在。
- 收藏永不下沉 + 30 天窗口是 owner 裁决的口径; 断言这两个过滤条件,
  防止后续调参把用户收藏或近期热点搬走。
- 每日 job 重复运行必须幂等, 否则 feed 膨胀且重建出重复行。
- feed 记录必须逐列保真 (C2.4 唯一输入): 除行数一致外还需数据一致。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services.wiki_archiver import (
    _parse_feed_records,
    sink_hotspots_to_feed,
)

_HOTSPOT_COLUMNS = (
    "id, title, summary, source, url, category, published_at, score, fetched_at, "
    "is_fallback, quality_score, quality_flags, quality_checked_at, url_check_status, "
    "ingested_at, tags, last_read_at, lifecycle, is_hidden, pick_score"
)


@pytest.fixture
def temp_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB (tmp SQLite) + 隔离 wiki 根目录。"""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    wiki_root = tmp_path / "wiki"
    (wiki_root / "feed").mkdir(parents=True)
    yield test_db, wiki_root
    db.close_db()


def _insert_hotspot(
    hotspot_id: str,
    *,
    ingested_at: datetime,
    summary: str = "摘要",
    tags: str = '["phishing"]',
) -> None:
    ts = ingested_at.isoformat()
    db.get_connection().execute(
        f"INSERT INTO hotspots ({_HOTSPOT_COLUMNS}) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            hotspot_id,
            f"标题-{hotspot_id}",
            summary,
            "unit-test",
            f"https://example.com/{hotspot_id}",
            "security",
            ts,
            8.0,
            ts,
            0,
            81.5,
            '["ok"]',
            None,
            "ok",
            ts,
            tags,
            None,
            "active",
            0,
            0.0,
        ),
    )


def _add_tag(hotspot_id: str, tag_id: str, label: str, confidence: float) -> None:
    conn = db.get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO tags (id, label, type, weight, created_at) "
        "VALUES (?, ?, 'technique', 1.0, ?)",
        (tag_id, label, datetime.now(tz=timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) "
        "VALUES (?, ?, ?, ?)",
        (hotspot_id, tag_id, confidence, datetime.now(tz=timezone.utc).isoformat()),
    )


def _feed_path(wiki_root, ts: datetime):
    return wiki_root / "feed" / f"{ts.strftime('%Y-%m')}.md"


def test_sink_writes_feed_and_keeps_db_row(temp_env):
    _, wiki_root = temp_env
    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    _insert_hotspot("h-old", ingested_at=old)
    _add_tag("h-old", "phishing", "钓鱼", 0.9)

    stats = sink_hotspots_to_feed(wiki_root=wiki_root, days=30)

    assert stats == {"selected": 1, "sunk": 1, "skipped": 0, "errors": 0, "months": 1}
    records = _parse_feed_records(
        _feed_path(wiki_root, old).read_text(encoding="utf-8")
    )
    assert [r["id"] for r in records] == ["h-old"]
    # RA-14: 本阶段只写不删 —— DB 行必须仍在
    assert db.get_connection().execute(
        "SELECT COUNT(*) FROM hotspots WHERE id = 'h-old'"
    ).fetchone()[0] == 1


def test_sink_excludes_favorites_and_recent(temp_env):
    _, wiki_root = temp_env
    now = datetime.now(tz=timezone.utc)
    old = now - timedelta(days=60)
    _insert_hotspot("h-fav", ingested_at=old)
    _insert_hotspot("h-old", ingested_at=old)
    _insert_hotspot("h-recent", ingested_at=now - timedelta(days=1))
    db.get_connection().execute(
        "INSERT INTO favorites (hotspot_id, category, title, source, url, favorited_at) "
        "VALUES ('h-fav', 'security', 'T', 'S', 'https://example.com/f', ?)",
        (now.isoformat(),),
    )

    stats = sink_hotspots_to_feed(wiki_root=wiki_root, days=30)

    assert stats["selected"] == 1 and stats["sunk"] == 1
    ids = [r["id"] for r in _parse_feed_records(
        _feed_path(wiki_root, old).read_text(encoding="utf-8")
    )]
    assert ids == ["h-old"]


def test_sink_is_idempotent(temp_env):
    _, wiki_root = temp_env
    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    _insert_hotspot("h-old", ingested_at=old)

    first = sink_hotspots_to_feed(wiki_root=wiki_root, days=30)
    second = sink_hotspots_to_feed(wiki_root=wiki_root, days=30)

    assert first["sunk"] == 1
    # 已记账 → 第二轮不再入选; 即便入选也会被 md 内 id 去重
    assert second["selected"] == 0
    path = _feed_path(wiki_root, old)
    assert len(_parse_feed_records(path.read_text(encoding="utf-8"))) == 1


def test_sink_dry_run_writes_nothing(temp_env):
    _, wiki_root = temp_env
    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    _insert_hotspot("h-old", ingested_at=old)

    stats = sink_hotspots_to_feed(wiki_root=wiki_root, days=30, dry_run=True)

    assert stats["selected"] == 1 and stats["sunk"] == 0
    assert not _feed_path(wiki_root, old).exists()


def test_feed_record_roundtrip_fidelity(temp_env):
    """C2.4 只能读 feed, 故每列都必须能原样还原。"""
    _, wiki_root = temp_env
    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    _insert_hotspot("h-old", ingested_at=old, summary="带逗号, 冒号: 与引号\"的摘要")
    _add_tag("h-old", "phishing", "钓鱼", 0.9)

    sink_hotspots_to_feed(wiki_root=wiki_root, days=30)
    rec = _parse_feed_records(
        _feed_path(wiki_root, old).read_text(encoding="utf-8")
    )[0]

    row = dict(db.get_connection().execute(
        "SELECT * FROM hotspots WHERE id = 'h-old'"
    ).fetchone())
    for col in ("title", "summary", "source", "url", "category", "published_at",
                "score", "fetched_at", "ingested_at", "quality_score",
                "quality_checked_at", "url_check_status", "lifecycle",
                "pick_score", "last_read_at"):
        assert rec[col] == row[col], col
    assert rec["is_fallback"] == row["is_fallback"]
    assert rec["is_hidden"] == row["is_hidden"]
    assert rec["quality_flags"] == json.loads(row["quality_flags"])
    assert rec["tags"] == json.loads(row["tags"])
    assert rec["tag_links"] == [
        {"tag_id": "phishing", "label": "钓鱼", "confidence": 0.9}
    ]


def test_sink_logs_wiki_event(temp_env):
    """账是重建对账的唯一依据 (设计 §3 LEDGER), 缺账无法核验。"""
    _, wiki_root = temp_env
    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    _insert_hotspot("h-old", ingested_at=old)

    sink_hotspots_to_feed(wiki_root=wiki_root, days=30)

    row = db.get_connection().execute(
        "SELECT kind, wiki_path, db_table, db_row_id, agent FROM wiki_events "
        "WHERE kind = 'sink'"
    ).fetchone()
    assert row is not None
    assert row["wiki_path"] == f"feed/{old.strftime('%Y-%m')}.md"
    assert (row["db_table"], row["db_row_id"]) == ("hotspots", "h-old")