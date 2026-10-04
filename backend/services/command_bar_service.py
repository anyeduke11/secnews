"""CommandBarService — M4 对话式命令栏 (v0.8.6 P1-4, 轴④)。

PRD 用例 B 契约 (§4):
- **意图集固定四类模板 (查询/建案/出报告/执行), 本地规则优先匹配;
  不做通用 NLU、不做自由对话** — 识别不中显式列出可选动作, 不猜
  (防命令栏演化为第二个 Skill* 平台, R5 教训)。
- 查询类直接 SQL (v1_signals JOIN v1_materials, 结果带 Source url);
  行动类生成 proposal 进审批流 (source=command, 人审后生效)。
- 每条命令写 command_log 行 = 命令的 run record (原始输入/意图判定/
  action_ref/outcome); 行动类经人批准后产生 v1_runs (proposal.run_id)。

执行类说明: 四类模板中的"执行"的执行体是 pi (M1 遗留, 后续批次接入)。
本批识别到执行类意图时**诚实返回暂未开放**, 不伪装成 proposal
(P0-6 "系统不宣称成功" 纪律), command_log 落 outcome=unsupported。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.logging_config import logger
from backend.repository.command_repo import command_repo
from backend.services.run_ledger_service import RunLedgerService

COMMAND_INTENTS = ("query", "create_case", "report", "execute", "unknown")
DEFAULT_QUERY_WINDOW_DAYS = 14
MAX_QUERY_RESULTS = 20
COMMAND_OUTCOMES = {"done", "unsupported", "unrecognized", "error"}

# 本地意图规则 (顺序即优先级; 全部确定性 regex, 无 LLM)
_RE_CREATE_CASE = re.compile(r"(?:为|给|把)?(?P<topic>.+?)(?:建案|立项)[。!.?]?$")
_RE_REPORT = re.compile(
    r"^(?:出|生成|写)(?:一份|个)?(?P<topic>.+?)(?:报告|简报)[。!.?]?$"
)
_RE_QUERY = re.compile(r"^(?:查|搜索|找)(?:一下)?(?P<body>.+?)信号[。!.?]?$")
_RE_WINDOW = re.compile(r"过去(?P<days>\d+)\s*天|近(?P<days2>\d+)\s*天")
_RE_EXECUTE = re.compile(r"^(?:执行|跑|重启|运行)\b|^(?:执行|跑)(?P<what>.+)")


@dataclass
class ParsedIntent:
    """parse_intent 的纯数据结果 (无副作用, 便于测试矩阵)。"""

    intent: str
    keyword: str = ""
    window_days: int = DEFAULT_QUERY_WINDOW_DAYS
    matched: bool = False
    options: list[str] = field(default_factory=list)


def parse_intent(text: str) -> ParsedIntent:
    """本地规则意图路由 — 四类固定模板, 不猜 (PRD 用例 B 范围约束)。"""
    t = (text or "").strip()
    if not t:
        return ParsedIntent(intent="unknown")

    # 1. 建案 (含"建案/立项"即命中, 主题 = 前置文本)
    m = _RE_CREATE_CASE.search(t)
    if m:
        topic = m.group("topic").strip().removeprefix("为").removeprefix("给").strip()
        if topic:
            return ParsedIntent(intent="create_case", keyword=topic, matched=True)

    # 2. 出报告
    m = _RE_REPORT.match(t)
    if m and m.group("topic").strip():
        return ParsedIntent(intent="report", keyword=m.group("topic").strip(),
                            matched=True)

    # 3. 查询 (时间窗 + 关键词; 无窗默认 14 天)
    if _RE_QUERY.match(t) or (t.startswith(("查", "搜索", "找")) and "信号" in t):
        body = t
        window = DEFAULT_QUERY_WINDOW_DAYS
        wm = _RE_WINDOW.search(t)
        if wm:
            window = int(wm.group("days") or wm.group("days2"))
            body = t[:wm.start()] + t[wm.end():]
        body = body.strip()
        # 去掉引导动词与尾部"信号"
        body = re.sub(r"^(?:查|搜索|找)(?:一下)?", "", body).strip()
        body = re.sub(r"的高?置信?信号$", "", body).strip()
        body = re.sub(r"信号$", "", body).strip()
        body = body.removeprefix("的").strip()
        return ParsedIntent(intent="query", keyword=body,
                            window_days=window, matched=True)

    # 4. 执行类 (识别到但执行体未接入 — 诚实 unsupported, 不伪装)
    if _RE_EXECUTE.match(t):
        return ParsedIntent(intent="execute", matched=True)

    return ParsedIntent(
        intent="unknown",
        options=[
            "查 <关键词> 过去N天的信号 — 检索信号池 (带原文链接)",
            "为 <主题> 建案 — 生成建案提案进审批收件箱",
            "出 <主题> 报告 — 生成报告提案进审批收件箱",
        ],
    )


def _cutoff_iso(window_days: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()


def _query_signals(
    keyword: str, window_days: int, limit: int = MAX_QUERY_RESULTS,
) -> list[dict[str, Any]]:
    """v1_signals 关键词检索 (LIKE, 单机规模够用) + Source url 回溯列。

    PRD 验收①: "查过去两周 X 的高置信信号"返回结果带来源链接 —
    JOIN v1_materials 拿 url 即回溯锚点。
    """
    from backend.repository.db import get_connection

    like = f"%{keyword}%"
    rows = get_connection().execute(
        "SELECT s.id, s.summary, s.occurred_at, s.confidence, m.url, m.title "
        "FROM v1_signals s JOIN v1_materials m ON m.id = s.material_id "
        "WHERE s.occurred_at >= ? AND (s.summary LIKE ? OR m.title LIKE ?) "
        "ORDER BY s.occurred_at DESC LIMIT ?",
        (_cutoff_iso(window_days), like, like, limit),
    ).fetchall()
    return [
        {"signal_id": r["id"], "summary": r["summary"], "url": r["url"],
         "title": r["title"], "occurred_at": r["occurred_at"],
         "confidence": r["confidence"]}
        for r in rows
    ]


class CommandBarService:
    """命令栏入口: parse_intent (纯规则) → 路由执行 → command_log 落账。"""

    def __init__(self, ledger: RunLedgerService | None = None) -> None:
        self.ledger = ledger or RunLedgerService()

    def run_command(self, text: str) -> dict[str, Any]:
        """执行一条命令。恒不抛 (命令栏故障不反噬 Shell): 异常落
        command_log outcome=error 并显式返回错误消息 (fail loud)。"""
        text = (text or "").strip()
        parsed = parse_intent(text)
        cmd_id = _ulid26("cmd_")
        action_ref: str | None = None
        outcome = "done"
        result: dict[str, Any] = {"command_id": cmd_id, "intent": parsed.intent}
        try:
            if parsed.intent == "unknown":
                outcome = "unrecognized"
                result["message"] = "未理解，可选动作："
                result["options"] = parsed.options
            elif parsed.intent == "execute":
                outcome = "unsupported"
                result["message"] = (
                    "执行类命令暂未开放（pi 执行体后续批次接入）；"
                    "当前可用：查信号 / 为主题建案 / 出报告"
                )
                result["options"] = parse_intent("").options
            elif parsed.intent == "query":
                items = _query_signals(parsed.keyword, parsed.window_days)
                result["results"] = items
                result["result_count"] = len(items)
                result["window_days"] = parsed.window_days
                result["message"] = (
                    f"近 {parsed.window_days} 天「{parsed.keyword}」命中 "
                    f"{len(items)} 条信号"
                )
            elif parsed.intent == "create_case":
                p = self.ledger.create_proposal(
                    source="command", kind="case_suggestion",
                    payload={
                        "title": f"建案建议：{parsed.keyword}",
                        "rationale": f"命令栏建案请求「{text}」（人审后生效）",
                    },
                )
                action_ref = p["id"]
                result["proposal_id"] = p["id"]
                result["message"] = "已生成建案提案，进审批收件箱（人审后生效）"
            elif parsed.intent == "report":
                p = self.ledger.create_proposal(
                    source="command", kind="report",
                    payload={
                        "title": f"报告草案：{parsed.keyword}",
                        "summary": f"命令栏出报告请求「{text}」（人审后生效）",
                    },
                )
                action_ref = p["id"]
                result["proposal_id"] = p["id"]
                result["message"] = "已生成报告提案，进审批收件箱（人审后生效）"
        except Exception as e:  # fail loud 不静默: 落 error 行 + 显式返回
            outcome = "error"
            logger.error(f"command {cmd_id} failed: {type(e).__name__}: {e}")
            result["message"] = f"命令执行失败: {type(e).__name__}: {e}"

        command_repo.insert(
            cmd_id=cmd_id, input_text=text, intent=parsed.intent,
            action_ref=action_ref, outcome=outcome,
        )
        result["outcome"] = outcome
        return result

    def list_commands(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        items, total = command_repo.list_commands(limit=limit, offset=offset)
        return {"items": items, "total": total}


_ULID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _ulid26(prefix: str) -> str:
    import random

    return prefix + "".join(random.choice(_ULID_ALPHABET) for _ in range(26))


__all__ = [
    "COMMAND_INTENTS",
    "CommandBarService",
    "ParsedIntent",
    "parse_intent",
]
