"""v0.5 §18 wiki 工具族测试 — wiki_events repo + /api/wiki/* 端点。

验证意图: llm-wiki-2.0 与 SQLite 运营层之间的事件桥接可用,
agent 能通过 MCP 工具族 搜索/读取/图导航/反查来源。
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# WikiEventRepo (纯 DB, 用 conftest 隔离的临时库)
# ===========================================================================
class TestWikiEventRepo:
    def test_log_and_trace_by_wiki_path(self, temp_db):
        """事件写入后能按知识路径完整反查 — db_trace 的核心契约。"""
        from backend.repository.wiki_event_repo import wiki_event_repo

        eid = wiki_event_repo.log(
            kind="sync_item",
            wiki_path="items/test-a.md",
            db_table="hotspots",
            db_row_id="hs-001",
            agent="collector:bid",
            payload={"url": "https://example.com"},
        )
        assert eid > 0

        events = wiki_event_repo.trace_by_wiki_path("items/test-a.md")
        assert len(events) == 1
        ev = events[0]
        # 反查必须还原「谁在什么时候因为什么产生了这条知识」
        assert ev["kind"] == "sync_item"
        assert ev["db_table"] == "hotspots"
        assert ev["db_row_id"] == "hs-001"
        assert json.loads(ev["payload"])["url"] == "https://example.com"

    def test_trace_by_db_ref_forward(self, temp_db):
        """正向追踪: 从运营层行找到衍生知识 — 与反查互为逆操作。"""
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind="agent_write",
            wiki_path="items/derived.md",
            db_table="hotspots",
            db_row_id="hs-002",
        )
        events = wiki_event_repo.trace_by_db_ref("hotspots", "hs-002")
        assert len(events) == 1
        assert events[0]["wiki_path"] == "items/derived.md"

    def test_stats_groups_by_kind(self, temp_db):
        """按 kind 统计 — 运维面板判断写入分布。"""
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(kind="sync_item")
        wiki_event_repo.log(kind="sync_item")
        wiki_event_repo.log(kind="sync_concept")
        stats = wiki_event_repo.stats()
        assert stats.get("sync_item") == 2
        assert stats.get("sync_concept") == 1


# ===========================================================================
# /api/wiki/* 端点 (e2e_api_client: 隔离 DB + 全路由, 不起 lifespan)
# ===========================================================================


class TestWikiRead:
    def test_read_existing_item(self, e2e_api_client: TestClient, tmp_path, monkeypatch):
        """读存在的 .md 返回全文 — agent wiki_read 的主路径。"""
        items_dir = tmp_path / "knowledge" / "items"
        items_dir.mkdir(parents=True)
        (items_dir / "demo-item.md").write_text(
            "---\ntitle: demo\n---\n\n正文内容", encoding="utf-8"
        )
        import backend.api.wiki_tools as wt
        monkeypatch.setattr(wt, "KNOWLEDGE_DIR", str(tmp_path / "knowledge"))

        resp = e2e_api_client.get("/api/wiki/read", params={"path": "items/demo-item.md"})
        assert resp.status_code == 200
        body = resp.json()
        assert "title: demo" in body["content"]
        assert body["path"] == "items/demo-item.md"

    def test_read_rejects_path_traversal(self, e2e_api_client: TestClient):
        """/../ 穿越和绝对路径必须被拒 — 安全红线 (P4-9 同款)。"""
        for evil in ("../../etc/passwd.md", "/absolute/path.md", "..\\x.md"):
            resp = e2e_api_client.get("/api/wiki/read", params={"path": evil})
            assert resp.status_code == 400, f"{evil} should be rejected"

    def test_read_missing_file_404(self, e2e_api_client: TestClient):
        resp = e2e_api_client.get("/api/wiki/read", params={"path": "items/no-such-file.md"})
        assert resp.status_code == 404


class TestWikiGraph:
    def test_graph_adjacency_form(self, e2e_api_client: TestClient, tmp_path, monkeypatch):
        """邻接表形态的 graph.json 能正确返回 k=1 邻居。"""
        concepts_dir = tmp_path / "knowledge" / "concepts"
        concepts_dir.mkdir(parents=True)
        (concepts_dir / "graph.json").write_text(
            json.dumps({"zero-trust": ["mfa"], "mfa": []}), encoding="utf-8"
        )
        import backend.api.wiki_tools as wt
        monkeypatch.setattr(wt, "KNOWLEDGE_DIR", str(tmp_path / "knowledge"))

        resp = e2e_api_client.get(
            "/api/wiki/graph", params={"concept": "zero-trust", "depth": 1}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["graph"]["zero-trust"] == ["mfa"]

    def test_graph_missing_concept_graceful(self, e2e_api_client: TestClient, tmp_path, monkeypatch):
        """概念不存在时返回 found=False 而非报错 — 方便 agent 探索。"""
        import backend.api.wiki_tools as wt
        monkeypatch.setattr(wt, "KNOWLEDGE_DIR", str(tmp_path))  # 无 graph.json

        resp = e2e_api_client.get("/api/wiki/graph", params={"concept": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["found"] is False


class TestDbTraceEndpoint:
    def test_trace_via_api_roundtrip(self, e2e_api_client: TestClient):
        """API 层往返: log → POST /api/wiki/trace 反查 — MCP db_trace 全链路。"""
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind="cli_agent_run",
            wiki_path="items/api-roundtrip.md",
            db_table="hotspots",
            db_row_id="hs-rt",
            agent="agent:dsh/claude-code",
        )
        resp = e2e_api_client.post(
            "/api/wiki/trace",
            json={"wiki_path": "items/api-roundtrip.md"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) >= 1
        assert any(e["kind"] == "cli_agent_run" for e in events)

    def test_trace_requires_query_key(self, e2e_api_client: TestClient):
        """空查询参数必须 400 — 防全表扫描误用。"""
        resp = e2e_api_client.post("/api/wiki/trace", json={})
        assert resp.status_code == 400


class TestWikiSearch:
    def test_search_like_fallback(self, e2e_api_client: TestClient):
        """无 FTS 数据时 LIKE 回退仍返回结果 — 空库/短查询不空手而归。"""
        # conftest 已把 DB 重定向到 tmp_path; knowledge_chunks 表存在但为空
        resp = e2e_api_client.post("/api/wiki/search", json={"q": "zzz-no-match-词"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["results"] == []


class TestWikiWrite:
    @pytest.fixture
    def wiki_env(self, e2e_api_client: TestClient, tmp_path, monkeypatch):
        """重定向 knowledge_sync 目录到 tmp_path (ai_hub 写路径的真实落点)。"""
        items_dir = tmp_path / "items"
        items_dir.mkdir(parents=True)
        from backend.services import knowledge_sync

        monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", items_dir)
        return {"items": items_dir}

    def test_write_creates_md_and_logs_event(
        self, e2e_api_client: TestClient, wiki_env
    ):
        """wiki_write 落盘 .md + SQLite 同步 + wiki_events 留 mcp:wiki_write 痕。"""
        from backend.repository.db import get_connection

        resp = e2e_api_client.post("/api/wiki/write", json={
            "item_id": "agent-note-1",
            "title": "Agent 笔记",
            "content": "# 正文\n\nagent 产出的持久知识",
            "source": "claude-code",
            "source_url": "https://example.com/src",
            "tags": ["mcp", "test"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"wiki_path": "items/agent-note-1.md",
                        "item_id": "agent-note-1", "synced": True}

        # 真相源: md 已落盘且含正文 + frontmatter 元数据
        md_text = (wiki_env["items"] / "agent-note-1.md").read_text(encoding="utf-8")
        assert "agent 产出的持久知识" in md_text
        assert 'id: "agent-note-1"' in md_text

        # 遥测: wiki_events 留 agent_write + sync_item 两痕 (写回 + 索引同步各一)
        rows = [dict(r) for r in get_connection().execute(
            "SELECT kind, agent FROM wiki_events "
            "WHERE wiki_path = 'items/agent-note-1.md' ORDER BY id")]
        assert [(r["kind"], r["agent"]) for r in rows] == [
            ("agent_write", "mcp:wiki_write"),
            ("sync_item", "watcher"),
        ]

    def test_write_rejects_invalid_item_id(self, e2e_api_client: TestClient):
        """item_id 白名单外 (大写/空格/穿越) 必须 400 — 不产生任何文件副作用。"""
        for evil in ("Bad-ID", "has space", "../evil"):
            resp = e2e_api_client.post("/api/wiki/write", json={
                "item_id": evil, "title": "t"})
            assert resp.status_code == 400, f"{evil!r} should be rejected"

    def test_write_existing_preserves_ingested_at(
        self, e2e_api_client: TestClient, wiki_env
    ):
        """更新已有条目保留原 ingested_at、刷新 title — 幂等更新语义。

        frontmatter 契约无 updated_at 字段 (仅 DB 索引承载), 故以 title 变化
        验证覆盖写生效, 以 ingested_at 不变验证「新建时间戳保留」。
        """
        def _fm_field(text: str, key: str) -> str:
            for line in text.splitlines():
                if line.startswith(f"{key}:"):
                    return line.split(":", 1)[1].strip().strip('"')
            return ""

        e2e_api_client.post("/api/wiki/write", json={
            "item_id": "dup-item", "title": "v1", "content": "one"})
        first = (wiki_env["items"] / "dup-item.md").read_text(encoding="utf-8")

        e2e_api_client.post("/api/wiki/write", json={
            "item_id": "dup-item", "title": "v2", "content": "two"})
        second = (wiki_env["items"] / "dup-item.md").read_text(encoding="utf-8")

        assert _fm_field(first, "ingested_at") != ""
        assert (_fm_field(first, "ingested_at")
                == _fm_field(second, "ingested_at"))
        assert _fm_field(second, "title") == "v2"

    def test_write_md_failure_returns_500(
        self, e2e_api_client: TestClient, wiki_env, monkeypatch
    ):
        """md 真源写失败必须 500 向上抛 — 静默成功会让 agent 误以为已持久化。"""
        from backend.services import knowledge_sync

        def _boom(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(knowledge_sync, "write_item_to_md", _boom)
        resp = e2e_api_client.post("/api/wiki/write", json={
            "item_id": "fail-case", "title": "t"})
        assert resp.status_code == 500
        assert "disk full" in resp.json()["detail"]
        assert not (wiki_env["items"] / "fail-case.md").exists()
