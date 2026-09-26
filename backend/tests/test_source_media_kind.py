"""source media_kind (治理 T1) — 介质维度迁移 + 搜狗归档 + 多媒体首批源.

意图 (docs/superpowers/specs/2026-09-26-source-governance-design.md §3.1/§3.4):
- media_kind 是「介质」维度 (web/wechat/multimedia), 与 kind (采集方式 html/rss)
  正交; 前端源矩阵按它分组, 微信通道归档待替代。
- 归档只动 crawler_sources 注册层 (幂等防御, 实测 2026-09-26 当前 0 行搜狗);
  source_stats 统计层的搜狗行不删不 retire — 有历史产出, 属可复活候选。
- 多媒体首批源 (YouTube 安全频道公开 RSS) probe 失败 (无代理直连 reset)
  → enabled=0 + notes 落库, 待 owner 配置代理后激活。

测试策略:
- slim fixture: 手工建三表核心列 + 直接执行 121 SQL 全文, 精确验证回填/
  归档/注册语义 (不依赖前 120 个迁移, 避免全链耗时放大)。
- 全量 fixture: apply_migrations 空库跑全链 ×2, 验证 runner 幂等契约下
  告警不重复 + 多媒体源种子落库 (与 CI/真实启动同路径)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.repository.db import apply_migrations

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[1] / "repository" / "migrations"
)
MIGRATION_121 = MIGRATIONS_DIR / "121_source_media_kind.sql"

# 121 SQL 实际引用的列子集 (列缺失会让迁移失败, 因此 slim schema 与
# 迁移文件的列契约漂移会被测试即时暴露)。
SLIM_SCHEMA = """
CREATE TABLE crawler_sources (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'html',
    url TEXT,
    feed_url TEXT,
    cadence_seconds INTEGER NOT NULL DEFAULT 300,
    priority INTEGER NOT NULL DEFAULT 50,
    max_items INTEGER NOT NULL DEFAULT 50,
    enabled INTEGER NOT NULL DEFAULT 1,
    use_proxy TEXT NOT NULL DEFAULT 'auto',
    status TEXT NOT NULL DEFAULT 'active',
    network_zone TEXT NOT NULL DEFAULT 'domestic',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE source_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    total_items INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE source_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _exec_migration_121(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_121.read_text(encoding="utf-8"))


@pytest.fixture()
def pre_migration_conn(tmp_path: Path) -> sqlite3.Connection:
    """slim schema (未迁移): 测试先预置存量行, 再自行执行 121 验证回填。"""
    conn = sqlite3.connect(str(tmp_path / "slim_media.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(SLIM_SCHEMA)
    yield conn
    conn.close()


@pytest.fixture()
def full_migration_conn(tmp_path: Path) -> sqlite3.Connection:
    """空库全链迁移 (与真实启动同路径), 供 runner 幂等断言。"""
    conn = sqlite3.connect(str(tmp_path / "full.db"))
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    yield conn
    conn.close()


def _add_crawler_source(conn: sqlite3.Connection, **fields) -> None:
    cols = {
        "id": "t:default",
        "category": "security",
        "name": "default",
        "kind": "rss",
        "url": "https://example.com/",
        "enabled": 1,
        "status": "active",
    }
    cols.update(fields)
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO crawler_sources ({names}) VALUES ({marks})",
        list(cols.values()),
    )


def _add_stat(conn: sqlite3.Connection, **fields) -> None:
    cols = {
        "category": "security",
        "source_name": "default",
        "source_url": "https://example.com/",
        "status": "active",
        "total_items": 100,
    }
    cols.update(fields)
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO source_stats ({names}) VALUES ({marks})",
        list(cols.values()),
    )


# ---------------------------------------------------------------------------
# 列存在性与默认值
# ---------------------------------------------------------------------------


def test_media_kind_columns_added_with_web_default(
    pre_migration_conn: sqlite3.Connection,
) -> None:
    """迁移后两表有 media_kind, crawler_sources 有 notes; 缺省介质=web。

    web 是缺省介质: 未识别的存量源不得被误分组到微信/多媒体。
    """
    _exec_migration_121(pre_migration_conn)
    cs_cols = {
        r[1]
        for r in pre_migration_conn.execute(
            "PRAGMA table_info(crawler_sources)"
        )
    }
    ss_cols = {
        r[1] for r in pre_migration_conn.execute("PRAGMA table_info(source_stats)")
    }
    assert {"media_kind", "notes"} <= cs_cols
    assert {"media_kind"} <= ss_cols

    _add_crawler_source(pre_migration_conn, id="t:plain", name="普通源")
    row = pre_migration_conn.execute(
        "SELECT media_kind, notes FROM crawler_sources WHERE id='t:plain'"
    ).fetchone()
    assert row["media_kind"] == "web"
    assert row["notes"] is None


# ---------------------------------------------------------------------------
# 存量回填推断 (§3.1: name 含 (搜狗)→wechat; url/name 含 youtube/bilibili→multimedia)
# ---------------------------------------------------------------------------


def test_backfill_wechat_marks_sogou_stats_rows(
    pre_migration_conn: sqlite3.Connection,
) -> None:
    """source_stats 搜狗行标 wechat (统计层状态/数据不动 — 可复活候选)。"""
    _add_stat(pre_migration_conn, source_name="微步在线(搜狗)", status="dead", total_items=1526)
    _add_stat(pre_migration_conn, source_name="FreeBuf(搜狗)", status="active")
    _add_stat(pre_migration_conn, source_name="TheHackerNews")
    _exec_migration_121(pre_migration_conn)
    pre_migration_conn.commit()

    rows = {
        r["source_name"]: r["media_kind"]
        for r in pre_migration_conn.execute(
            "SELECT source_name, media_kind FROM source_stats"
        )
    }
    assert rows["微步在线(搜狗)"] == "wechat"
    assert rows["FreeBuf(搜狗)"] == "wechat"
    assert rows["TheHackerNews"] == "web"

    # 统计层不被归档动作改状态 (与 crawler_sources 层的关键区别)
    kept = pre_migration_conn.execute(
        "SELECT status, total_items FROM source_stats WHERE source_name='微步在线(搜狗)'"
    ).fetchone()
    assert kept["status"] == "dead"
    assert kept["total_items"] == 1526


def test_backfill_wechat_marks_and_archives_sogou_registry_rows(
    pre_migration_conn: sqlite3.Connection,
) -> None:
    """crawler_sources 搜狗注册行: media_kind=wechat + retired + enabled=0 + P2 告警。

    owner 裁决 §2: 微信通道归档待替代, 保留审计; 告警恰一条。
    """
    _add_crawler_source(
        pre_migration_conn, id="security:安全客(搜狗)", name="安全客(搜狗)", kind="html"
    )
    _add_crawler_source(pre_migration_conn, id="security:嘶吼", name="嘶吼")
    _exec_migration_121(pre_migration_conn)
    pre_migration_conn.commit()

    sogou = pre_migration_conn.execute(
        "SELECT media_kind, status, enabled FROM crawler_sources WHERE id='security:安全客(搜狗)'"
    ).fetchone()
    assert sogou["media_kind"] == "wechat"
    assert sogou["status"] == "retired"
    assert sogou["enabled"] == 0

    normal = pre_migration_conn.execute(
        "SELECT status, enabled FROM crawler_sources WHERE id='security:嘶吼'"
    ).fetchone()
    assert normal["status"] == "active"
    assert normal["enabled"] == 1

    alerts = pre_migration_conn.execute(
        "SELECT level FROM source_alerts WHERE alert_type='source_archived_wechat'"
    ).fetchall()
    assert len(alerts) == 1
    assert alerts[0]["level"] == "P2"


def test_backfill_multimedia_by_url_or_name(
    pre_migration_conn: sqlite3.Connection,
) -> None:
    """url/feed_url 含 youtube 或 name/url 含 bilibili → multimedia。"""
    _add_crawler_source(
        pre_migration_conn,
        id="security:YT",
        name="YT 频道",
        url="https://www.youtube.com/feeds/videos.xml?channel_id=UCx",
    )
    _add_crawler_source(
        pre_migration_conn,
        id="security:Bili",
        name="B 站 UP",
        url="https://www.bilibili.com/video/BVxx",
    )
    _add_stat(pre_migration_conn, source_name="某YouTube精选", source_url=None)
    _exec_migration_121(pre_migration_conn)
    pre_migration_conn.commit()

    kinds = {
        r["id"]: r["media_kind"]
        for r in pre_migration_conn.execute(
            "SELECT id, media_kind FROM crawler_sources"
        )
    }
    assert kinds["security:YT"] == "multimedia"
    assert kinds["security:Bili"] == "multimedia"

    stat_kind = pre_migration_conn.execute(
        "SELECT media_kind FROM source_stats WHERE source_name='某YouTube精选'"
    ).fetchone()
    assert stat_kind["media_kind"] == "multimedia"


# ---------------------------------------------------------------------------
# 多媒体首批源注册 (§3.4) — probe 失败 → enabled=0 待 owner 激活
# ---------------------------------------------------------------------------


def test_multimedia_seed_rows_registered_disabled(
    full_migration_conn: sqlite3.Connection,
) -> None:
    """全链迁移后存在 2 个 multimedia 源: rss/security/international, enabled=0。

    probe 2026-09-26 直连失败 (无代理 Connection reset), 按设计落库为
    disabled + notes 指引, 不假装可采。
    """
    rows = full_migration_conn.execute(
        """
        SELECT id, name, kind, category, media_kind, enabled, status,
               use_proxy, network_zone, notes, url, feed_url
        FROM crawler_sources WHERE media_kind='multimedia' ORDER BY id
        """
    ).fetchall()
    assert len(rows) == 2

    for r in rows:
        assert r["kind"] == "rss"
        assert r["category"] == "security"
        assert r["enabled"] == 0
        assert r["status"] == "disabled"
        assert r["use_proxy"] == "required"
        assert r["network_zone"] == "international"
        assert r["notes"] and "代理" in r["notes"]
        assert "youtube.com/feeds/videos.xml?channel_id=" in r["url"]
        assert r["feed_url"] == r["url"]

    ids = {r["id"] for r in rows}
    assert ids == {
        "security:John Hammond (YouTube)",
        "security:LiveOverflow (YouTube)",
    }


def test_migration_runner_idempotent_no_duplicate_alert(
    full_migration_conn: sqlite3.Connection,
) -> None:
    """二次 init (apply_migrations no-op) 不得重复归档告警或改写源。

    121 的 ALTER 非幂等, 幂等契约由 schema_version 单次执行保证 —
    这里验证的正是该 runner 契约下的最终态稳定。
    """
    version_before = apply_migrations(full_migration_conn)
    version_after = apply_migrations(full_migration_conn)
    assert version_before == version_after

    alerts = full_migration_conn.execute(
        "SELECT COUNT(*) AS c FROM source_alerts WHERE alert_type='source_archived_wechat'"
    ).fetchone()
    assert alerts["c"] == 1

    mm = full_migration_conn.execute(
        "SELECT COUNT(*) AS c FROM crawler_sources WHERE media_kind='multimedia'"
    ).fetchone()
    assert mm["c"] == 2


def test_archive_alert_survives_registry_without_sogou_rows(
    full_migration_conn: sqlite3.Connection,
) -> None:
    """实测 crawler_sources 0 搜狗行: 归档为防御性空转, 但告警仍须落一条。

    通道级事实 (搜狗镜像被封) 不依赖注册层是否存在行 — 运维仍需被告知。
    """
    alert = full_migration_conn.execute(
        """
        SELECT source_id, level, message FROM source_alerts
        WHERE alert_type='source_archived_wechat'
        """
    ).fetchone()
    assert alert is not None
    assert alert["level"] == "P2"
    assert "搜狗" in alert["message"]
