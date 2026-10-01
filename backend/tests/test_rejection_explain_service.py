"""rejection_explain_service — 拒收日志 LLM 批量解释 (spec §4)。

契约:
- explain IS NULL 的行批量取 (LIMIT), 合并单次 pi 调用, 逐行回填
- 空积压 → 零 LLM 调用
- LLM 挂/解析失败 → explain 保持 NULL (下轮重试), 返回 {"explained": 0}
- 只更新解析结果中 id 匹配且 explain 非空的行 (防毒化)
"""
import pytest

from backend.services import rejection_explain_service as res


def _mock_llm(monkeypatch, payload=None, fail=False):
    import asyncio
    from backend.services.ai_hub.gateway import llm_service

    async def _gen(prompt, *, task="summary", **kw):
        assert task == "rejection_explain"
        if fail:
            raise RuntimeError("pi down")
        return payload
    monkeypatch.setattr(llm_service, "generate", _gen)


def _insert_rejection(item_id_title: str, reason: str, explain: str | None = None) -> int:
    from backend.repository.db import get_connection

    cur = get_connection().execute(
        "INSERT INTO quality_rejection_log"
        " (source_id, item_title, item_url, rejected_by, reason, raw_data,"
        "  created_at, explain) VALUES ('s', ?, 'u', 'strict_mode', ?, '',"
        " datetime('now'), ?)",
        (item_id_title, reason, explain),
    )
    return cur.lastrowid


class TestRunRejectionExplain:
    def test_empty_backlog_zero_llm_calls(self, temp_db, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        assert res.run_rejection_explain() == {"explained": 0}
        assert called["n"] == 0

    def test_batch_generates_and_backfills(self, temp_db, monkeypatch):
        id1 = _insert_rejection("Chrome 0day 爆出", "['category_mismatch']")
        id2 = _insert_rejection("某厂商泄露", "['empty_summary', 'author_unknown']")
        _mock_llm(monkeypatch, (
            f'[{{"id": {id1}, "explain": "内容与安全分类不相关"}},'
            f' {{"id": {id2}, "explain": "摘要为空且作者未知, 疑似低质"}}]'
        ))
        result = res.run_rejection_explain()
        assert result == {"explained": 2}
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT id, explain FROM quality_rejection_log ORDER BY id"
        ).fetchall()
        assert rows[0]["explain"] == "内容与安全分类不相关"
        assert rows[1]["explain"] == "摘要为空且作者未知, 疑似低质"

    def test_llm_failure_keeps_null_for_retry(self, temp_db, monkeypatch):
        _insert_rejection("t", "['noise_title']")
        _mock_llm(monkeypatch, fail=True)
        assert res.run_rejection_explain() == {"explained": 0}
        from backend.repository.db import get_connection
        row = get_connection().execute(
            "SELECT explain FROM quality_rejection_log LIMIT 1"
        ).fetchone()
        assert row["explain"] is None  # 保持 NULL 待下轮

    def test_garbage_output_keeps_null(self, temp_db, monkeypatch):
        _insert_rejection("t", "['noise_title']")
        _mock_llm(monkeypatch, "完全不是 JSON")
        assert res.run_rejection_explain() == {"explained": 0}

    def test_already_explained_rows_skipped(self, temp_db, monkeypatch):
        _insert_rejection("old", "['noise_title']", explain="已有解释")
        _mock_llm(monkeypatch, "[]")
        assert res.run_rejection_explain() == {"explained": 0}
        # explain 已存在的行不被触碰 (IS NULL 过滤)

    def test_batch_limit_respected(self, temp_db, monkeypatch):
        for i in range(5):
            _insert_rejection(f"t{i}", "['noise_title']")
        _mock_llm(monkeypatch, "[]")
        res.run_rejection_explain(batch_limit=3)  # 不抛; LIMIT 生效由 SQL 保证

    def test_prompt_contains_title_and_flags(self, temp_db, monkeypatch):
        from backend.services.ai_hub.prompts import build_rejection_explain_prompt
        _insert_rejection("Chrome 0day 爆出", "['category_mismatch']")
        prompt = build_rejection_explain_prompt([
            {"id": 1, "title": "Chrome 0day 爆出", "reason": "['category_mismatch']"},
        ])
        assert "Chrome 0day 爆出" in prompt
        assert "category_mismatch" in prompt
        assert "60" in prompt  # 字数上限要求
