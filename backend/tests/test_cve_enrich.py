"""CVE 空壳回源富化测试 (DEV-0300) — 检索/深读/CVE 模板三面契约。

第一性原理: CVE 条目 = 编号 (寻址) + 结构化事实 (内容); 只有编号的空壳
条目不该进检索面, 深读时必须回源 NVD 取事实, 回源失败诚实拒绝。
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.config import config
from backend.repository import db
from backend.services.cve_enrich_service import (
    compose_cve_brief,
    extract_cve_id,
    fetch_cve_facts,
    is_cve_shell,
)
from backend.services.search_service import unified_search


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_cve_enrich.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ── 空壳判定 ─────────────────────────────────────────────────


class TestCveShellDetection:
    def test_shell_pure_number(self):
        assert is_cve_shell("CVE-2026-21589")
        assert is_cve_shell("CVE-2026-21589 漏洞")

    def test_shell_none_or_no_cve(self):
        assert not is_cve_shell(None)
        assert not is_cve_shell("")
        assert not is_cve_shell("勒索软件攻击事件分析")  # 无 CVE 不算空壳

    def test_not_shell_with_substantive_content(self):
        assert not is_cve_shell(
            "CVE-2026-21589: Atlassian 双重 URL 解码缺陷导致任意文件读取,"
            "技术细节与 PoC 已公开, 影响多个 Data Center 产品"
        )

    def test_extract_cve_id(self):
        assert extract_cve_id("参考 cve-2026-1234 公告") == "CVE-2026-1234"
        assert extract_cve_id("无编号") is None


# ── NVD 回源 (mock 出站) ──────────────────────────────────────


def _nvd_payload() -> dict:
    return {
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-2026-21589",
                "published": "2026-10-05T22:16:58.423",
                "lastModified": "2026-10-07T13:17:22.273",
                "vulnStatus": "Awaiting Analysis",
                "descriptions": [
                    {"lang": "en", "value": "Arbitrary file read in Atlassian Data Center products."},
                ],
                "metrics": {
                    "cvssMetricV31": [{
                        "cvssData": {
                            "baseScore": 7.5,
                            "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N",
                            "baseSeverity": "HIGH",
                        },
                    }],
                },
                "configurations": [{
                    "nodes": [{"cpeMatch": [
                        {"criteria": "cpe:2.3:a:atlassian:bitbucket:9.4.25:*:*:*:*:*:*:*"},
                        {"criteria": "cpe:2.3:a:atlassian:confluence:9.2.25:*:*:*:*:*:*:*"},
                    ]}],
                }],
                "references": [{"url": "https://confluence.atlassian.com/security/x"}],
            },
        }],
    }


class TestFetchCveFacts:
    def test_fetch_parses_nvd_and_caches(self, temp_db):
        import urllib.request

        with patch.object(urllib.request, "urlopen") as mock_open:

            mock_open.return_value.__enter__.return_value.read = lambda: json.dumps(
                _nvd_payload()).encode()
            facts = fetch_cve_facts("CVE-2026-21589")

        assert facts is not None
        assert facts["cve_id"] == "CVE-2026-21589"
        assert facts["cvss_score"] == 7.5
        assert facts["severity"] == "HIGH"
        assert len(facts["affected_vendors"]) == 2
        assert "atlassian bitbucket" in facts["affected_vendors"][0]

        # 缓存命中: 二次调用不出站
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("must not fetch")):
            facts2 = fetch_cve_facts("CVE-2026-21589")
        assert facts2 == facts

    def test_fetch_none_when_nvd_empty(self, temp_db):
        import urllib.request

        with patch.object(urllib.request, "urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read = lambda: json.dumps(
                {"vulnerabilities": []}).encode()
            assert fetch_cve_facts("CVE-9999-99999") is None

    def test_fetch_none_on_network_error(self, temp_db):
        import urllib.request

        with patch.object(urllib.request, "urlopen", side_effect=OSError("net down")):
            assert fetch_cve_facts("CVE-2026-21589") is None


class TestComposeBrief:
    def test_brief_contains_structured_sections(self):
        """compose_cve_brief 纯函数单测 (不出站)。"""
        brief = compose_cve_brief({
            "cve_id": "CVE-2026-21589",
            "description_en": "Arbitrary file read in Atlassian products.",
            "cvss_score": 7.5, "cvss_vector": "CVSS:3.1/X", "severity": "HIGH",
            "published": "2026-10-05", "last_modified": "2026-10-07",
            "vuln_status": "Awaiting Analysis",
            "affected_vendors": ["atlassian bitbucket"],
            "references": ["https://r/1"], "nvd_url": "https://nvd/x",
            "fetched_at": "2026-10-08T00:00:00+00:00",
        })
        assert "漏洞情报简报 CVE-2026-21589" in brief
        assert "漏洞描述" in brief and "威胁评估" in brief
        assert "7.5" in brief and "atlassian bitbucket" in brief


# ── 深读分支 (空壳 → 回源 → cve profile) ─────────────────────


class TestDeepReadCveBranch:
    def _seed_shell(self, kid: str, topic: str) -> None:
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "INSERT OR REPLACE INTO knowledge_items (id, title, source, domain, "
            "topic, type, difficulty, tags, concepts, mastery, compiled, "
            "ingested_at, updated_at, source_url) "
            "VALUES (?, ?, 'test', 'security', ?, 'article', 'beginner', "
            "'[]', '[]', 0, 0, ?, ?, ?)",
            (kid, topic, topic, now, now, f"https://example.com/{kid}"),
        )

    def test_shell_routes_to_cve_profile_with_nvd_facts(self, temp_db, monkeypatch):
        """空壳条目深读 → NVD 事实简报 + category=cve (走漏洞通告 profile)。"""
        from backend.services.deep_read_service import _fetch_source

        self._seed_shell("ki-shell", "CVE-2026-21589")
        # 缓存预置 (不出站)
        db.get_connection().execute(
            "INSERT OR REPLACE INTO security_entities (id, entity_type, name, "
            "description, metadata, created_at, updated_at) "
            "VALUES ('cve:CVE-2026-21589', 'cve', 'CVE-2026-21589', 'x', ?, "
            "datetime('now'), datetime('now'))",
            (json.dumps({"facts": {
                "cve_id": "CVE-2026-21589",
                "description_en": "Arbitrary file read.",
                "cvss_score": 7.5, "cvss_vector": "CVSS:3.1/X", "severity": "HIGH",
                "published": "2026-10-05", "last_modified": "2026-10-07",
                "vuln_status": "Awaiting Analysis",
                "affected_vendors": ["atlassian bitbucket"],
                "references": ["https://r/1"], "nvd_url": "https://nvd/x",
                "fetched_at": "2026-10-08T00:00:00+00:00",
            }}, ensure_ascii=False),),
        )
        body, meta = _fetch_source("knowledge", "ki-shell")
        assert meta["category"] == "cve"
        assert "CVE-2026-21589" in meta["title"]
        assert "威胁评估" in body and "7.5" in body

    def test_shell_without_facts_raises(self, temp_db, monkeypatch):
        """空壳 + 无缓存 + NVD 不可达 → DeepReadError (诚实拒绝)。"""
        from backend.services.deep_read_service import DeepReadError, _fetch_source

        self._seed_shell("ki-shell2", "CVE-2026-99999")
        with patch(
            "backend.services.cve_enrich_service.fetch_cve_facts",
            return_value=None,
        ):
            with pytest.raises(DeepReadError, match="NVD 回源失败"):
                _fetch_source("knowledge", "ki-shell2")


# ── 检索面过滤 ────────────────────────────────────────────────


class TestSearchFiltersShell:
    def test_shell_rows_filtered_from_knowledge(self, temp_db):
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        for kid, title, topic in [
            ("k-shell", "CVE-2026-21589", "CVE-2026-21589"),
            ("k-rich", "Atlassian 任意文件读取分析",
             "CVE-2026-21589 双重 URL 解码致任意文件读取, PoC 已公开, 影响 Bitbucket/Confluence"),
        ]:
            conn.execute(
                "INSERT OR REPLACE INTO knowledge_items (id, title, source, domain, "
                "topic, type, difficulty, tags, concepts, mastery, compiled, "
                "ingested_at, updated_at, source_url) "
                "VALUES (?, ?, 'test', 'security', ?, 'article', 'beginner', "
                "'[]', '[]', 0, 0, ?, ?, ?)",
                (kid, title, topic, now, now, f"https://example.com/{kid}"),
            )
        result = unified_search("CVE-2026-21589", sources=["knowledge"])
        ids = [i["entity_id"] for i in result["items"]]
        assert "k-shell" not in ids   # 空壳被滤
        assert "k-rich" in ids        # 有实质内容的保留
