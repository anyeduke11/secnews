"""P1-4/M4 命令栏测试 (PRD 用例 B)。

验收三条映射:
- ① 查询 "查过去两周 X 的信号" → 结果带来源链接 (v1_signals JOIN materials);
- ② "为 X 建案" → 生成 proposal 而非直接建案 (source=command, 人审后生效);
- ③ 每条命令可查 → GET /api/commands (command_log run record; PRD 原文写
  /api/ops/runs 为 job_runs 专用口, 查询口回写见 DEV-0272 落账)。

契约 (Rule 9 WHY): 本地规则路由不猜 (unknown 必须给可选动作清单)、
执行类诚实 unsupported 不伪装 proposal、command_log 行 = 命令 run record。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.repository.db import get_connection
from backend.services.command_bar_service import (
    CommandBarService,
    parse_intent,
)


@pytest.fixture
def svc(temp_db) -> CommandBarService:
    return CommandBarService()


def _seed_signal(signal_id: str, material_id: str, summary: str,
                 days_ago: float, url: str, title: str = "t") -> None:
    """最小信号桩: v1_subjects + v1_materials + v1_signals (全部真表)。"""
    conn = get_connection()
    occurred = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    now = occurred
    conn.execute(
        "INSERT OR IGNORE INTO v1_subjects "
        "(id, entity_type, canonical_name, aliases_json, importance, tags_json, "
        " related_subject_ids_json, first_seen_at, last_seen_at) "
        "VALUES (?, 'other', 'subj', '[]', 0.5, '[]', '[]', ?, ?)",
        (f"subj_{material_id}", now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials "
        "(id, source_kind, url, title, content_hash, content_length, "
        " fetched_at, fetched_by) "
        "VALUES (?, 'url', ?, ?, ?, 0, ?, 'test')",
        (material_id, url, title, "0" * 64, now),
    )
    conn.execute(
        "INSERT INTO v1_signals (id, subject_id, material_id, summary, "
        "occurred_at, admission_rule_version, confidence, status) "
        "VALUES (?, ?, ?, ?, ?, 'test@v1', 'unverified', 'unverified')",
        (signal_id, f"subj_{material_id}", material_id, summary, occurred),
    )
    conn.commit()


# ── 意图路由纯函数矩阵 (本地规则, 不猜) ─────────────────────────────

class TestParseIntent:
    def test_query_with_window_and_keyword(self):
        p = parse_intent("查过去14天勒索软件信号")
        assert p.intent == "query"
        assert p.window_days == 14
        assert "勒索软件" in p.keyword

    def test_query_default_window_14d(self):
        """无显式时间窗 → 默认 14 天 (与 PRD 验收① '过去两周' 口径一致)。"""
        p = parse_intent("查供应链攻击信号")
        assert p.intent == "query"
        assert p.window_days == 14
        assert "供应链攻击" in p.keyword

    def test_create_case_wei(self):
        p = parse_intent("为勒索软件态势建案")
        assert p.intent == "create_case"
        assert p.keyword == "勒索软件态势"

    def test_create_case_lixiang(self):
        p = parse_intent("AI 供应链风险立项")
        assert p.intent == "create_case"
        assert "AI 供应链风险" in p.keyword

    def test_report(self):
        p = parse_intent("出勒索软件周报告")
        assert p.intent == "report"
        assert p.keyword == "勒索软件周"

    def test_execute_recognized(self):
        assert parse_intent("执行全量采集").intent == "execute"

    def test_unknown_lists_options_not_guess(self):
        p = parse_intent("今天天气怎么样")
        assert p.intent == "unknown"
        assert len(p.options) >= 3, "识别不中必须给可选动作清单 (PRD: 不猜)"

    def test_empty_is_unknown(self):
        assert parse_intent("  ").intent == "unknown"


# ── run_command: 验收三条 ───────────────────────────────────────────

class TestRunCommand:
    def test_query_returns_results_with_source_url(self, svc):
        """验收①: 查询结果必须带来源链接 (material.url); 窗口外信号不计入。"""
        _seed_signal("sig_in", "mat_in", "勒索软件家族新增变种", days_ago=3,
                     url="https://src.example.com/ransom-1", title="勒索软件周报")
        _seed_signal("sig_old", "mat_old", "勒索软件旧闻", days_ago=60,
                     url="https://src.example.com/old")
        r = svc.run_command("查勒索软件信号")
        assert r["intent"] == "query"
        assert r["outcome"] == "done"
        assert r["result_count"] == 1  # 60 天前那条在 14 天窗之外
        assert r["results"][0]["url"] == "https://src.example.com/ransom-1"
        assert "勒索软件" in r["results"][0]["summary"]

    def test_create_case_generates_proposal_not_case(self, svc):
        """验收②: 建案命令生成 proposal, 不直接建案 (人主律)。"""
        r = svc.run_command("为勒索软件态势建案")
        assert r["intent"] == "create_case"
        assert r["outcome"] == "done"
        pid = r["proposal_id"]
        assert pid and pid.startswith("prop_")
        p = svc.ledger.get_proposal(pid)
        assert p["source"] == "command"           # 命令栏通道
        assert p["kind"] == "case_suggestion"
        assert p["status"] == "draft"             # 待人审, 未成事实
        assert "勒索软件态势" in p["payload"]["title"]

    def test_report_generates_proposal(self, svc):
        r = svc.run_command("出勒索软件报告")
        assert r["intent"] == "report"
        p = svc.ledger.get_proposal(r["proposal_id"])
        assert p["source"] == "command"
        assert p["kind"] == "report"
        assert p["status"] == "draft"

    def test_execute_honest_unsupported(self, svc):
        """执行类: 识别到但执行体未接入 → unsupported, 不伪装 proposal。"""
        r = svc.run_command("执行全量采集")
        assert r["intent"] == "execute"
        assert r["outcome"] == "unsupported"
        assert "proposal_id" not in r
        assert "暂未开放" in r["message"]

    def test_unknown_explicit_options(self, svc):
        r = svc.run_command("今天天气怎么样")
        assert r["intent"] == "unknown"
        assert r["outcome"] == "unrecognized"
        assert "未理解" in r["message"]
        assert len(r["options"]) >= 3

    def test_every_command_logged_as_run_record(self, svc):
        """验收③: 每条命令落 command_log (run record: input/intent/action/outcome)。"""
        _seed_signal("sig_q2", "mat_q2", "x", days_ago=1, url="https://x/2")
        svc.run_command("查勒索软件信号")
        svc.run_command("为测试主题建案")
        svc.run_command("胡言乱语")
        out = svc.list_commands()
        items, total = out["items"], out["total"]
        assert total == 3
        by_intent = {i["intent"]: i for i in items}
        assert by_intent["query"]["outcome"] == "done"
        assert by_intent["create_case"]["action_ref"].startswith("prop_")
        assert by_intent["unknown"]["outcome"] == "unrecognized"
        # 原始输入全量留痕
        assert {i["input_text"] for i in items} == {
            "查勒索软件信号", "为测试主题建案", "胡言乱语",
        }

    def test_command_error_is_loud_not_silent(self, svc, monkeypatch):
        """执行异常 → outcome=error + 显式错误消息 (fail loud, 不静默)。"""
        def boom(**kw):
            raise RuntimeError("ledger down")

        monkeypatch.setattr(svc.ledger, "create_proposal", boom)
        r = svc.run_command("为X建案")
        assert r["outcome"] == "error"
        assert "ledger down" in r["message"]
        items = svc.list_commands()["items"]
        assert items[0]["outcome"] == "error"


# ── HTTP 契约 ───────────────────────────────────────────────────────

def test_api_run_command_and_list(e2e_api_client):
    client = e2e_api_client
    r = client.post("/api/commands", json={"text": "为API主题建案"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "create_case"
    assert body["proposal_id"].startswith("prop_")

    r = client.get("/api/commands")
    assert r.status_code == 200
    listing = r.json()
    assert listing["total"] == 1
    assert listing["items"][0]["intent"] == "create_case"

    r = client.post("/api/commands", json={"text": ""})
    assert r.status_code == 422  # Pydantic min_length
