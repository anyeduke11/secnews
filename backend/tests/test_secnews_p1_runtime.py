"""SECNEWS Phase 1 运行时测试 (2026-08-24)。

覆盖两块新增装配:
- AIHubLLMClient 同步桥接 (无循环 / 循环内 / ai_hub 单例惰性解析)
- refine 阶段 LLM 路径 (S1-6): JSON 结构化字段 + 无 LLM 降级摘要

(心跳 job 测试见 test_kl_heartbeat_job.py)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from backend.kl_pipeline import KLPipeline
from backend.kl_pipeline.llm_adapter import AIHubLLMClient


# ---------------------------------------------------------------------------
# Fixtures (与 test_kl_pipeline.py 同款最小 schema)
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kl_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 5,
            next_run_at TEXT,
            last_error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, stage)
        );
        CREATE TABLE IF NOT EXISTS token_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER, item_id TEXT, model TEXT, provider TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    yield conn
    conn.close()


@pytest.fixture
def tmp_wiki(tmp_path):
    root = str(tmp_path / "wiki")
    os.makedirs(root, exist_ok=True)
    from backend.wiki_fs import WikiFs
    return WikiFs(root)


def _enqueue_due(tmp_db, item_id: str, stage: str) -> None:
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    tmp_db.execute(
        "INSERT INTO kl_queue (item_id, stage, next_run_at) VALUES (?, ?, ?)",
        (item_id, stage, past.isoformat()),
    )


# ---------------------------------------------------------------------------
# AIHubLLMClient — async generate → sync chat 桥接
# ---------------------------------------------------------------------------
class FakeAsyncService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"ok:{prompt}"


class TestAIHubLLMClient:
    def test_chat_outside_event_loop(self):
        """工作线程 (scheduler asyncio.to_thread) 无循环 → asyncio.run 直跑。"""
        svc = FakeAsyncService()
        client = AIHubLLMClient(service=svc)
        assert client.chat("p1") == "ok:p1"
        assert svc.prompts == ["p1"]

    def test_chat_inside_event_loop(self):
        """API 事件循环线程内调用 → 独立单线程池跑新循环, 不嵌套。"""

        async def main() -> str:
            return AIHubLLMClient(service=FakeAsyncService()).chat("p2")

        assert asyncio.run(main()) == "ok:p2"

    def test_lazy_singleton_resolves_ai_hub_service(self, monkeypatch):
        """未注入时惰性复用 ai_hub.llm_service 模块级单例。"""
        fake = FakeAsyncService()
        monkeypatch.setitem(
            sys.modules,
            "backend.services.ai_hub",
            types.SimpleNamespace(llm_service=fake),
        )
        client = AIHubLLMClient()
        assert client.chat("p3") == "ok:p3"
        assert client._service is fake


# ---------------------------------------------------------------------------
# refine LLM 路径 (S1-6)
# ---------------------------------------------------------------------------
class _FakeChat:
    """refine 期望的同步 chat() 客户端替身。"""

    def __init__(self, payload: str | Exception) -> None:
        self._payload = payload
        self.calls = 0

    def chat(self, prompt: str, response_format: str | None = None) -> str:
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


_REFINE_JSON = (
    '{"summary": "云上凭据泄露事件摘要", '
    '"tags": ["cloud", "credentials", "CVE-2026-0001"], '
    '"severity": "high", "topic": "云安全", "type": "incident"}'
)


class TestRefineLLMPath:
    def test_llm_json_populates_structured_fields(self, tmp_db, tmp_wiki):
        """chat() 返回合法 JSON → summary/tags/severity/topic/type 全部落 fm。"""
        result = tmp_wiki.ingest_url(
            "https://llm.example/json", title="J",
            text="long enough body for the llm path",
        )
        item_id = result["id"]
        _enqueue_due(tmp_db, item_id, "kl:refine")

        fake = _FakeChat(_REFINE_JSON)
        pipeline = KLPipeline(
            wiki_fs=tmp_wiki, db_session=tmp_db, llm_client=fake)
        res = pipeline.drain_due()
        assert res == {"done": 1, "failed": 0}
        assert fake.calls == 1

        fm = tmp_wiki.read_item(item_id)["fm"]
        assert fm["lifecycle"] == "kl:refine"
        assert fm["summary"] == "云上凭据泄露事件摘要"
        assert "CVE-2026-0001" in fm["tags"]
        assert fm["severity"] == "high"
        assert fm["topic"] == "云安全"
        assert fm["type"] == "incident"

    def test_llm_exception_falls_back_to_truncation(self, tmp_db, tmp_wiki):
        """chat() 抛异常 → 降级为正文截断摘要, 不失败不入死信。"""
        body = "raw incident text"
        result = tmp_wiki.ingest_url(
            "https://llm.example/boom", title="B", text=body)
        item_id = result["id"]
        _enqueue_due(tmp_db, item_id, "kl:refine")

        fake = _FakeChat(RuntimeError("provider down"))
        pipeline = KLPipeline(
            wiki_fs=tmp_wiki, db_session=tmp_db, llm_client=fake)
        res = pipeline.drain_due()
        assert res == {"done": 1, "failed": 0}

        fm = tmp_wiki.read_item(item_id)["fm"]
        assert fm["lifecycle"] == "kl:refine"
        assert fm["summary"] == body

    def test_llm_empty_response_degrades(self, tmp_db, tmp_wiki):
        """ai_hub 未配置 provider 时 generate 返回 '' — JSON 解析失败走降级摘要。"""
        body = "no llm configured today"
        result = tmp_wiki.ingest_url(
            "https://llm.example/empty", title="E", text=body)
        item_id = result["id"]
        _enqueue_due(tmp_db, item_id, "kl:refine")

        fake = _FakeChat("")
        pipeline = KLPipeline(
            wiki_fs=tmp_wiki, db_session=tmp_db, llm_client=fake)
        res = pipeline.drain_due()
        assert res == {"done": 1, "failed": 0}

        fm = tmp_wiki.read_item(item_id)["fm"]
        assert fm["lifecycle"] == "kl:refine"
        assert fm["summary"] == body
        assert "severity" not in fm or fm.get("severity") != "high"
