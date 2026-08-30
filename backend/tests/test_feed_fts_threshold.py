"""P3-1: get_feed 关键词搜索 5 万行阈值惰性 trigram FTS 化。

锁定卡顿审计 2026-08-30 裁决 "feed 数据量到 5 万行再 FTS 化" 的自执行机制:
- 未达标: 与旧 LIKE 路径行为一致 (零语义漂移), 不建任何 FTS 对象
- 达标: worker 线程内一次性建 hotspots_trigram_fts + 回填 + 同步触发器,
  ≥3 字符查询词切 MATCH (子串语义 = LIKE 等价), <3 字符维持 LIKE
- 激活持久化在 DB (触发器存在即视为已激活), 进程重启后自动恢复
- 响应以 search_engine / feed_rows 标注实际口径
"""
from __future__ import annotations

import sqlite3

import pytest

import backend.secnews_dashboard as sd
from backend.secnews_dashboard import SecNewsDashboard


@pytest.fixture
def fts_db(tmp_path):
    """与 test_secnews_dashboard 同构的最小 hotspots 库 (落盘以便重开模拟重启)。"""
    db_path = tmp_path / "fts.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE hotspots ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, url TEXT UNIQUE NOT NULL, source TEXT,"
        " category TEXT, summary TEXT, published_at TEXT,"
        " ingested_at TEXT DEFAULT (datetime('now')))"
    )
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def reset_feed_fts_state():
    """模块级探针/激活状态 + 阈值在每个用例前后复位 (防跨文件泄漏)。"""
    sd._feed_fts_state.update(rows=0, checked_at=0.0, activated=False)
    yield
    sd._feed_fts_state.update(rows=0, checked_at=0.0, activated=False)


def _seed(conn, n, prefix="条目"):
    for i in range(n):
        conn.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES (?, ?, 'src', 'security', ?)",
            (f"{prefix} {i}", f"https://example.com/{prefix}/{i}", f"正文 {i}"),
        )


class TestFeedFtsThreshold:
    def test_below_threshold_keeps_like_and_builds_nothing(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 100)
        _seed(fts_db, 3)
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed(keyword="条目")
        assert r["search_engine"] == "like"
        assert r["total"] == 3
        assert r["feed_rows"] == 3
        objects = fts_db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%trigram%'"
        ).fetchone()[0]
        assert objects == 0

    def test_at_threshold_activates_trigram_with_like_equivalent_recall(
        self, fts_db, monkeypatch
    ):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 4)
        _seed(fts_db, 2)
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('零日漏洞利用预警', 'u1', 'src', 'security', 'APT 勒索软件活动')"
        )
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('常规更新', 'u2', 'src', 'security', '与漏洞无关的例行公告')"
        )
        d = SecNewsDashboard(db=fts_db)

        like = d.get_feed(keyword="漏洞利用")  # 首次调用: 探针发现达标 → 激活
        assert like["search_engine"] == "fts5_trigram"
        assert like["feed_rows"] == 4
        # 子串语义 = LIKE 等价: 命中 "零日漏洞利用预警", 不命中 "与漏洞无关"
        assert like["total"] == 1
        assert like["items"][0]["title"] == "零日漏洞利用预警"
        # 对照组: 同库同词 LIKE 路径结果一致
        sd._feed_fts_state["activated"] = False
        fts_db.execute("DROP TRIGGER hotspots_tft_ai")
        fts_db.execute("DROP TRIGGER hotspots_tft_ad")
        fts_db.execute("DROP TRIGGER hotspots_tft_au")
        fts_db.execute("DROP TABLE hotspots_trigram_fts")
        sd._feed_fts_state.update(rows=0, checked_at=0.0)
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 10**9)
        baseline = d.get_feed(keyword="漏洞利用")
        assert baseline["total"] == like["total"]
        assert [i["id"] for i in baseline["items"]] == [i["id"] for i in like["items"]]

    def test_activation_persists_across_process_restart(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 5)
        _seed(fts_db, 6, prefix="测试条目")
        d = SecNewsDashboard(db=fts_db)
        first = d.get_feed(keyword="测试条目")
        assert first["search_engine"] == "fts5_trigram"

        # 模拟进程重启: 模块状态清零 + 换一条新连接 (同 DB 文件)
        sd._feed_fts_state.update(rows=0, checked_at=0.0, activated=False)
        db_path = fts_db.execute("PRAGMA database_list").fetchone()[2]
        fts_db.close()
        conn2 = sqlite3.connect(db_path, isolation_level=None)
        conn2.row_factory = sqlite3.Row
        try:
            d2 = SecNewsDashboard(db=conn2)
            second = d2.get_feed(keyword="测试条目")
            assert second["search_engine"] == "fts5_trigram"
            assert second["total"] == first["total"]
            # 触发器只建一次 (幂等, IF NOT EXISTS 不报重名)
            n = conn2.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'hotspots_tft_%'"
            ).fetchone()[0]
            assert n == 3
        finally:
            conn2.close()

    def test_short_keyword_falls_back_to_like(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 5)
        _seed(fts_db, 6, prefix="漏洞")
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed(keyword="漏洞")  # 2 字符: trigram 无可用 trigram → LIKE
        assert r["search_engine"] == "like"
        assert r["total"] == 6

    def test_ascii_keyword_substring_case_insensitive(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 3)
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('OpenSSL3 发行', 'u1', 'src', 'security', 'note')"
        )
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('openssl 漏洞', 'u2', 'src', 'security', 'CVE-2024-1234')"
        )
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('无关条目', 'u3', 'src', 'security', 'nothing')"
        )
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed(keyword="openssl")
        assert r["search_engine"] == "fts5_trigram"
        assert r["total"] == 2  # 大小写不敏感子串 = LIKE %openssl% 等价

    def test_triggers_keep_index_synced_after_activation(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 3)
        _seed(fts_db, 3, prefix="测试条目")
        d = SecNewsDashboard(db=fts_db)
        assert d.get_feed(keyword="测试条目")["search_engine"] == "fts5_trigram"

        # INSERT → 新行立即可检索
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('供应链投毒事件', 'u9', 'src', 'security', 'npm 恶意包')"
        )
        assert d.get_feed(keyword="供应链投毒")["total"] == 1

        # UPDATE → 新值可检索, 旧值不再命中
        fts_db.execute(
            "UPDATE hotspots SET title = '勒索软件复盘' WHERE url = 'u9'"
        )
        assert d.get_feed(keyword="勒索软件复盘")["total"] == 1
        assert d.get_feed(keyword="供应链投毒")["total"] == 0

        # DELETE → 从索引消失
        fts_db.execute("DELETE FROM hotspots WHERE url = 'u9'")
        assert d.get_feed(keyword="勒索软件复盘")["total"] == 0

    def test_double_quote_in_keyword_is_escaped(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 3)
        fts_db.execute(
            "INSERT INTO hotspots (title, url, source, category, summary) "
            "VALUES ('say \"hi\" ok', 'u1', 'src', 'security', 'x')"
        )
        _seed(fts_db, 3)
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed(keyword='say "hi" ok')
        assert r["search_engine"] == "fts5_trigram"
        assert r["total"] == 1

    def test_no_keyword_skips_probe_and_annotation(self, fts_db, monkeypatch):
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 5)
        _seed(fts_db, 2)
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed()
        assert "search_engine" not in r
        assert "feed_rows" not in r
        assert sd._feed_fts_state["checked_at"] == 0.0  # 探针未运行

    def test_partial_backfill_resumes_without_duplicates(self, fts_db, monkeypatch):
        """崩溃可续: 表已建但触发器未齐时, 重入只补缺口不重复回填。"""
        monkeypatch.setattr(sd, "_FEED_FTS_ROW_THRESHOLD", 5)
        _seed(fts_db, 6, prefix="测试条目")
        # 模拟中断现场: 只建表 + 回填 3 行, 无触发器
        fts_db.execute(
            "CREATE VIRTUAL TABLE hotspots_trigram_fts "
            "USING fts5(title, summary, content='', tokenize='trigram')"
        )
        fts_db.execute(
            "INSERT INTO hotspots_trigram_fts(rowid, title, summary) "
            "SELECT rowid, title, IFNULL(summary,'') FROM hotspots LIMIT 3"
        )
        d = SecNewsDashboard(db=fts_db)
        r = d.get_feed(keyword="测试条目")
        assert r["search_engine"] == "fts5_trigram"
        assert r["total"] == 6
        idx_rows = fts_db.execute(
            "SELECT COUNT(*) FROM hotspots_trigram_fts"
        ).fetchone()[0]
        assert idx_rows == 6  # 回填补齐, 无重复 (重复会致 MATCH 计数膨胀)
