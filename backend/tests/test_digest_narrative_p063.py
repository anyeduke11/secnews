"""Digest LLM 叙事回归测试 (v0.6.3 P3-4, 对应审计"伪完成 Top #1")。

三个历史断链点, 各对应一条锁死回归的用例:
1. ``POST /api/digests/generate`` 是 async def — 旧实现在事件循环线程上
   ``new_event_loop().run_until_complete()`` 必然 RuntimeError → 裸 except
   吞掉 → summary_md 恒空 (P0-2 to_thread 修复)。
2. ollama 离线时 gateway.summarize 兜底返回 prompt 前 200 字 → 被当叙事
   写库 (P1-1 改为返回空串)。
3. 真实失败路径端到端不回显 prompt 指令头。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

PROMPT_ECHO_MARK = "以下是 Top"  # prompt 指令头片段, 旧兜底会把它写进 summary_md


def _insert_hotspot(item_id: str, title: str, score: float, ingested_at: str):
    """与 test_digest_service 相同的种子方式: 直插 hotspots 昨日窗口。"""
    from backend.repository.db import get_connection

    get_connection().execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id, title, "", "test-src", f"https://example.com/{item_id}", "ai",
            ingested_at, score, ingested_at, 0,
            100, "[]", ingested_at,
        ),
    )


def _yesterday_shanghai_hours_ago(hours: int) -> str:
    """昨日窗口内的稳定种子: 昨日 12:00 Shanghai - hours (任意运行时刻都落在昨日窗口)。

    v0.6.3 修正: 原 `now - 1d - hours` 在本地 00:00-01:00 之间运行会落进
    前天 (周一零晨周界炸弹同款), 改为按"昨日日历日"锚定。
    """
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=8))  # Asia/Shanghai
    now_sh = datetime.now(tz)
    yesterday_noon = (now_sh - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    dt = yesterday_noon - timedelta(hours=hours)
    return dt.astimezone(timezone.utc).isoformat()


@pytest.fixture()
def client(temp_db):
    with TestClient(app) as c:
        yield c


def test_endpoint_async_context_writes_llm_narrative(client: TestClient, temp_db, monkeypatch):
    """P0-2 回归锁: 经 async 端点生成 (to_thread 路径), summary_md 承载叙事。

    旧代码在 async 端点上 new_event_loop 必败 → summary_md 恒空; 本用例在
    TestClient (事件循环) 内打端点, 桥必须仍然工作。
    """
    _insert_hotspot("h1", "AI 突破", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))

    from backend.services.ai_hub import llm_service

    async def _fake_summarize(chunks):
        return "端到端叙事: AI 主线领涨。"

    monkeypatch.setattr(llm_service, "summarize", _fake_summarize)

    r = client.post("/api/digests/generate?top_n=3")
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["summary_md"] == "端到端叙事: AI 主线领涨。"


def test_all_providers_fail_returns_empty_not_prompt_echo(client: TestClient, temp_db, monkeypatch):
    """P1-1 回归锁: 全 provider 失败 → summary_md 为空, 绝不回显 prompt 指令头。

    旧 gateway 兜底 text[:200] 会把 "昨日共 N 篇文章。以下是 Top..." 写进
    summary_md, 前端优先渲染 → 用户看到指令回显 (内容污染)。
    """
    _insert_hotspot("h1", "安全通告", score=90, ingested_at=_yesterday_shanghai_hours_ago(1))

    # 不 mock summarize 本身 — 打穿真实链: 每个 provider 的 _call_provider 都失败
    from backend.services.ai_hub import llm_service

    async def _always_fail(cfg, model, prompt, **kwargs):
        raise ConnectionError("provider down (test)")

    monkeypatch.setattr(llm_service, "_call_provider", _always_fail)

    r = client.post("/api/digests/generate?top_n=3")
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["summary_md"] == "" or item["summary_md"] is None
    assert PROMPT_ECHO_MARK not in (item["summary_md"] or "")


def test_gateway_summarize_all_fail_returns_empty_string(temp_db, monkeypatch):
    """P1-1 单元锁: LLMService.summarize 全链失败 → "" (非 text[:200])。"""
    _insert_hotspot("h1", "x", score=1, ingested_at=_yesterday_shanghai_hours_ago(1))

    import asyncio

    from backend.services.ai_hub import llm_service

    async def _always_fail(cfg, model, prompt, **kwargs):
        raise ConnectionError("provider down (test)")

    monkeypatch.setattr(llm_service, "_call_provider", _always_fail)

    result = asyncio.run(llm_service.summarize(["一段需要被摘要的正文"]))
    assert result == ""
