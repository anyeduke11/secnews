"""P4 统一检索重构验收测试 (DEV-0296) — 四项结构性修复的契约锁定。

对应批判性审查四项:
- P4-1 结果可点: hotspot 命中必须带原文 url
- P4-2 查询预处理: 多词 AND 命中 / CVE 编号不被 NOT 解析 / FTS 特殊串不炸
- P4-3 FTS5 主引擎: rank 相关度排序面生效, LIKE 退兜底 (零命中自愈)
- P4-4 CommandBar 查询收敛: 信号面 + 统一面 merge 去重
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services.command_bar_service import CommandBarService
from backend.services.search_service import build_fts_query, unified_search


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_search_p4.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_hotspot(hid: str, title: str, summary: str = "",
                    ingested_at: str | None = None) -> None:
    now = ingested_at or datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        "INSERT OR REPLACE INTO hotspots (id, title, summary, source, url, "
        "category, published_at, score, fetched_at, is_fallback, quality_score, "
        "quality_flags, url_check_status, ingested_at) "
        "VALUES (?, ?, ?, 'test', ?, 'security', ?, 50.0, ?, 0, 80, '[]', 'pending', ?)",
        (hid, title, summary, f"https://example.com/{hid}", now, now, now),
    )


class TestP41ResultsClickable:
    def test_hotspot_hit_carries_source_url(self, temp_db):
        _insert_hotspot("h1", "FastAPI RCE 漏洞", "未授权访问")
        result = unified_search("FastAPI")
        hit = result["items"][0]
        assert hit["entity_type"] == "hotspot"
        assert hit["url"] == "https://example.com/h1"  # 检索闭环锚点


class TestP42QueryPreprocess:
    def test_build_fts_multi_word_and(self):
        assert build_fts_query("勒索软件 金融机构") == '"勒索软件" "金融机构"'

    def test_build_fts_cve_not_parsed_as_not(self):
        assert build_fts_query("CVE-2026-1234") == '"CVE-2026-1234"'

    def test_build_fts_quotes_doubled(self):
        assert build_fts_query('say "hi"') == '"say" """hi"""'

    def test_multi_word_matches_rows_with_both_terms(self, temp_db):
        """旧 LIKE 整串匹配必 0 命中的场景 — 分词 AND 后命中。"""
        _insert_hotspot("h1", "勒索软件攻击金融机构", "Ransomware")
        result = unified_search("勒索软件 金融机构")
        assert [i["entity_id"] for i in result["items"]] == ["h1"]

    def test_multi_word_and_excludes_partial(self, temp_db):
        """AND 语义: 只含一词的不命中。"""
        _insert_hotspot("h1", "勒索软件攻击金融机构", "")
        _insert_hotspot("h2", "勒索软件横行", "")
        result = unified_search("勒索软件 金融机构")
        assert [i["entity_id"] for i in result["items"]] == ["h1"]

    def test_cve_number_finds_row(self, temp_db):
        """"CVE-2026-1234" 短语查询必须命中 (旧版 - 解析为 NOT → 假阴性)。"""
        _insert_hotspot("h1", "CVE-2026-1234 越界写入漏洞", "")
        result = unified_search("CVE-2026-1234")
        assert [i["entity_id"] for i in result["items"]] == ["h1"]

    def test_fts_syntax_noise_no_500(self, temp_db):
        """FTS 特殊语法串 (旧版直接喂 MATCH 会炸/空) → 落兜底仍可查。"""
        _insert_hotspot("h1", "NOT 操作符测试", "")
        result = unified_search('"unbalanced NEAR( ')  # 语法噪声
        assert result["items"] == []  # 不抛 5xx 即可

    def test_like_wildcard_literal_preserved(self, temp_db):
        _insert_hotspot("h1", "100% 完成", "")
        _insert_hotspot("h2", "100X 完成", "")
        ids = [i["entity_id"] for i in unified_search("100%")["items"]]
        assert "h1" in ids and "h2" not in ids  # % 字面语义 (FTS 零命中 → LIKE 兜底转义)


class TestP43FtsPrimaryEngine:
    def test_rank_order_relevant_first(self, temp_db):
        """相关度排序面: 标题双词命中 rank 优于摘要单词 (FTS rank 主导)。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_hotspot("h_weak", "FastAPI 速览", "其他内容", ingested_at=now)
        _insert_hotspot("h_strong", "FastAPI 安全加固指南", "FastAPI 最佳实践",
                        ingested_at=now)
        items = unified_search("FastAPI 安全")["items"]
        assert items[0]["entity_id"] == "h_strong"  # rank 相关度优先于时间

    def test_url_in_fts_results(self, temp_db):
        _insert_hotspot("h1", "FTS 路径也带 url", "")
        hit = unified_search("FTS 路径")["items"][0]
        assert hit["url"].startswith("https://")


class TestP44CommandQueryConvergence:
    def test_command_query_merges_unified_results(self, temp_db):
        """CommandBar 查询: 信号面 + hotspots/knowledge 统一面 merge;
        同 title (同一证据两态) 去重不重复展示。"""
        from datetime import datetime as dt
        from datetime import timedelta as td

        _insert_hotspot("h_u", "统一面独有整合关键词热点", "")
        _insert_hotspot("h_dup", "同名去重关键词条目", "")  # 与信号同 url 域不同 title
        conn = db.get_connection()
        occ = (dt.now(timezone.utc) - td(hours=1)).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO v1_subjects (id, entity_type, canonical_name, "
            "first_seen_at, last_seen_at) VALUES ('subj-1', 'other', 'x', ?, ?)",
            (occ, occ),
        )
        # 信号 material 的 url 指向 h_dup 原文 (同一证据) → 应被去重
        conn.execute(
            "INSERT OR REPLACE INTO v1_materials (id, source_kind, url, title, "
            "content_hash, content_length, published_at, fetched_by, fetched_at) "
            "VALUES ('mat-1', 'url', 'https://example.com/h_dup', '同名去重关键词条目', 'h', 10, ?, 't', ?)",
            (occ, occ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO v1_signals (id, subject_id, material_id, summary, "
            "occurred_at, admission_rule_version, admission_reason, confidence, status) "
            "VALUES ('sig-1', 'subj-1', 'mat-1', '同名去重关键词条目', ?, 'v', 'r', 'unverified', 'unverified')",
            (occ,),
        )
        result = CommandBarService().run_command("查 同名去重 信号")
        ids = [i["signal_id"] for i in result["results"]]
        assert "sig-1" in ids                                   # 信号面
        # 同证据 (信号 url 与 hotspot 原文相同) → 统一面去重不重复展示
        assert "unified:hotspot:h_dup" not in ids
        assert result["outcome"] == "done"

        # 统一面独有条目: 换词查
        result2 = CommandBarService().run_command("查 整合关键词 信号")
        ids2 = [i["signal_id"] for i in result2["results"]]
        assert "unified:hotspot:h_u" in ids2                    # 统一面 merge (P4-4)
        assert result2["outcome"] == "done"
