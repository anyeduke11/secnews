"""MP-2 EventTechniqueExtractService — LLM 抽取 + 程序化校验 + 落候选池.

职责
----
- ``extract_for_report(report_id, event_type_id, llm_model, ...)``: 读一份 incident_report,
  调 LLM 抽 technique 候选, 程序化校验 (FK / evidence_quote substring / confidence),
  落 ``event_technique_candidates`` (owner_status='pending')
- ``bulk_extract(event_type_id, dir_path, ...)``: 批量对一个 event_type 的所有报告抽取

LLM 调用约束 (引自 DISCUSSION §7.2)
------------------------------------
1) technique_id 必须是 enterprise-attack 中存在的 T-id (FK 校验 — attack_techniques 表)
2) stage 必须在 event_type.kill_chain_stages 列表内 (MP-2: 我们放宽为自由短串, 但写入时记录)
3) evidence_quote 必须是 source_report.report_md 子串 (normalized form C)
4) confidence ∈ [0.0, 1.0], <0.4 不入候选池 (强约束 — 落 auto_reject_reason)

LLM 调用
--------
- 走 ai_hub.llm_service.generate() (异步), 不动 _try_order / _resolve_provider
- 失败时降级到 mock-extract-v1 (基于 typical_signals + kill_chain_stages 的启发式),
  保证演示数据可落库
"""
from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import InternalException, NotFoundException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.event_technique_repo import (
    EventTechniqueCandidateRepo,
    EventTypeRepo,
    IncidentReportRepo,
)
from backend.repository.event_technique_repo import (
    new_ulid as _new_ulid,
)

# confidence 阈值 (<此值不入候选池)
CONFIDENCE_THRESHOLD = 0.4

# evidence_quote 最大长度
EVIDENCE_QUOTE_MAX_LEN = 120

# 默认 mock model 标识 (LLM 不可用时降级用)
MOCK_LLM_MODEL = "mock-extract-v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_text(s: str) -> str:
    """Unicode NFKC + 去多余空白 — evidence_quote substring 校验 (normalized form C)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())
    return s


def _load_attack_techniques_set() -> set[str]:
    """从 attack_techniques 表读 technique_id 集合 (FK 校验目标)."""
    conn = get_connection()
    rows = conn.execute("SELECT id FROM attack_techniques").fetchall()
    return {str(r["id"]) for r in rows}


def _extract_quote_from_report(report_md: str, technique_signal_keywords: list[str]) -> str | None:
    """从报告原文切 ≤120 字片段作为 evidence_quote (启发式: 找包含关键词的句子).

    Returns:
        找到则返回 ≤120 字片段; 找不到返回 None.
    """
    if not report_md:
        return None

    # 按句号/换行切句
    sentences = re.split(r"[。.!?！？\n]+", report_md)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 10]

    # 找含关键词的第一句
    for sent in sentences:
        norm_sent = _normalize_text(sent)
        for kw in technique_signal_keywords:
            if _normalize_text(kw).lower() in norm_sent.lower():
                # 截断到 120 字 (按 NFKC 长度)
                return norm_sent[:EVIDENCE_QUOTE_MAX_LEN]
    # 兜底: 报告正文的前 120 字
    normalized = _normalize_text(report_md)
    return normalized[:EVIDENCE_QUOTE_MAX_LEN] if normalized else None


# ---------------------------------------------------------------------------
# LLM call (ai_hub) — 异步 + mock 降级
# ---------------------------------------------------------------------------
async def _call_llm_extract(
    prompt: str,
    llm_model: str,
) -> str:
    """调 ai_hub LLM 生成 (返回 JSON 字符串). 失败/降级返回 ''."""
    try:
        from backend.services.ai_hub.gateway import llm_service
    except Exception:
        return ""
    try:
        # llm_service.generate() 是 async, 接收 prompt + task; 不动 _try_order / _resolve_provider
        result = await llm_service.generate(prompt, task="summary", max_tokens=1024)
        return result or ""
    except Exception as e:
        logger.warning("llm extract call failed: %s", e)
        return ""


def _mock_extract(
    event_type_id: str,
    report_md: str,
    event_type_meta: dict,
    valid_techniques: list[str],
) -> list[dict[str, Any]]:
    """Mock extraction — 基于 typical_signals + 文本匹配, 不依赖外部 LLM.

    启发式:
      1) 取 event_type.typical_signals + report_md 中明显提到的 ATT&CK technique 名
      2) 用 kill_chain_stages 顺序分配 stage
      3) confidence 视命中关键词次数而定 (0.5 ~ 0.9)
    """
    if not valid_techniques:
        return []

    # 简化 technique 字典 (snippet — 实际项目用 attack_techniques 全集)
    technique_signals = {
        "T1566": "phishing|spear|email|钓鱼|邮件诱导",
        "T1078": "valid account|凭据|账号|legitimate credentials",
        "T1190": "exploit public-facing|web|sql injection|exposed|面向公众",
        "T1204": "user execution|用户执行|attachment|malicious attachment",
        "T1059": "command and scripting|powershell|cmd|脚本|命令执行",
        "T1068": "privilege escalation|提权|exploit for privilege",
        "T1486": "data encrypted|encryption|encrypt|数据加密|勒索",
        "T1490": "inhibit system recovery|shadow copy|vss|删除备份|删除卷影",
        "T1027": "obfuscated|encoded|payload|混淆|编码",
        "T1110": "brute force|credential stuffing|password spray|爆破|撞库",
        "T1110.001": "password guessing|字典",
        "T1110.003": "password spraying|口令喷洒",
        "T1110.004": "credential stuffing|撞库",
        "T1071": "application layer protocol|c2|command and control|c2 通道",
        "T1041": "exfiltration over c2|c2 通道外传",
        "T1567": "exfiltration to web service|外传到云",
        "T1133": "external remote services|vpn|rdp|远程服务",
        "T1195": "supply chain|dependency|第三方组件|供应链",
        "T1195.002": "compromise software supply chain|软件供应链",
        "T1199": "trusted relationship|third party|第三方信任",
        "T1505": "server software component|web shell|后门",
        "T1505.003": "web shell|webshell|web 后门",
        "T1053": "scheduled task|cron|计划任务",
        "T1543": "create or modify system process|service|服务",
        "T1574": "hijack execution flow|dll|dll 劫持",
        "T1552": "credentials in files|凭据文件|配置文件",
        "T1003": "credential dumping|mimikatz|lsass|凭据提取",
        "T1083": "file and directory discovery|目录扫描|文件发现",
        "T1057": "process discovery|进程发现",
        "T1018": "remote system discovery|扫描|remote discovery",
        "T1021": "remote services|lateral|smb|rdp|横向",
        "T1021.001": "remote desktop protocol|rdp",
        "T1021.002": "smb|admin shares",
        "T1530": "data from cloud storage|云存储",
        "T1538": "cloud service dashboard|云控制台",
        "T1078.004": "cloud accounts|云账号",
        "T1654": "log enumeration|日志枚举",
    }

    text_norm = _normalize_text(report_md).lower()
    found: list[tuple[str, float, str]] = []  # (technique_id, confidence, matched_signal)

    for tid, signal in technique_signals.items():
        if tid not in valid_techniques:
            continue
        keywords = signal.split("|")
        hits = sum(1 for kw in keywords if _normalize_text(kw).lower() in text_norm)
        if hits > 0:
            # confidence 视命中数: 1 keyword=0.55, 2=0.7, 3+=0.85
            conf = min(0.55 + 0.15 * (hits - 1), 0.92)
            matched = next((kw for kw in keywords if _normalize_text(kw).lower() in text_norm), keywords[0])
            found.append((tid, conf, matched))

    # 按 confidence 降序, 至少取前 5 个
    found.sort(key=lambda x: -x[1])
    found = found[:8]

    # 给每个 candidate 配 stage + evidence_quote
    kill_chain_stages = event_type_meta.get("kill_chain_stages", [])
    typical_signals = event_type_meta.get("typical_signals", [])

    candidates = []
    for tid, conf, matched in found:
        # 简单按 (stage 顺序) round-robin
        stage = kill_chain_stages[len(candidates) % len(kill_chain_stages)] if kill_chain_stages else "execution"
        # 取 evidence_quote (≤120字)
        quote = _extract_quote_from_report(report_md, [matched] + typical_signals[:3])
        if not quote:
            continue
        candidates.append({
            "technique_id": tid,
            "stage": stage,
            "confidence": round(conf, 2),
            "evidence_quote": quote,
            "rationale": f"文本命中关键词 '{matched}' (mock-extract-v1)",
        })

    return candidates


# ---------------------------------------------------------------------------
# EventTechniqueExtractService
# ---------------------------------------------------------------------------
class EventTechniqueExtractService:
    """LLM 抽取 + 程序化校验 + 落候选池."""

    def __init__(self) -> None:
        self.candidate_repo = EventTechniqueCandidateRepo()
        self.report_repo = IncidentReportRepo()
        self.event_type_repo = EventTypeRepo()
        # 缓存 FK 集合 (避免每条 candidate 都查 attack_techniques)
        self._technique_set_cache: set[str] | None = None

    # ------------------------------------------------------------------
    # FK 缓存
    # ------------------------------------------------------------------
    def _valid_techniques(self) -> set[str]:
        if self._technique_set_cache is None:
            self._technique_set_cache = _load_attack_techniques_set()
        return self._technique_set_cache

    def _valid_techniques_list(self) -> list[str]:
        return sorted(self._valid_techniques())

    # ------------------------------------------------------------------
    # 程序化校验
    # ------------------------------------------------------------------
    def _validate_candidate(
        self,
        candidate: dict,
        source_report_md: str,
        kill_chain_stages: list[str],
    ) -> tuple[bool, str]:
        """校验单条 candidate. 返回 (pass, reason).

        reason: 'pass' / 'technique_not_in_attack_db' / 'quote_not_found' /
                'confidence_below_threshold' / 'stage_invalid' / 'missing_field'
        """
        tid = candidate.get("technique_id", "").strip()
        if not tid:
            return False, "missing_field:technique_id"
        stage = candidate.get("stage", "").strip()
        if not stage:
            return False, "missing_field:stage"
        quote = candidate.get("evidence_quote", "").strip()
        if not quote:
            return False, "missing_field:evidence_quote"
        conf = candidate.get("confidence")
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            return False, "missing_field:confidence"

        if tid not in self._valid_techniques():
            return False, f"technique_not_in_attack_db:{tid}"
        if conf < CONFIDENCE_THRESHOLD:
            return False, f"confidence_below_threshold:{conf}"
        # evidence_quote 必须在 source_report_md 中 substring 命中 (normalized form C)
        norm_md = _normalize_text(source_report_md)
        norm_quote = _normalize_text(quote)
        if norm_quote not in norm_md:
            return False, "quote_not_found"
        # stage 校验 (MP-2 期放宽 — 自由短串, 不强制 enum)
        # 但若 kill_chain_stages 非空且 stage 不在其中, 记 reason 但不强制 reject (留 owner 决策)
        if kill_chain_stages and stage not in kill_chain_stages:
            # stage 在候选里, 但不在 event_type 的 kill_chain_stages 内 — 标 soft warning
            # 不作为 auto_reject; 让 owner 决定
            pass

        return True, "pass"

    # ------------------------------------------------------------------
    # 抽取入口 (单条)
    # ------------------------------------------------------------------
    async def extract_for_report(
        self,
        report_id: str,
        event_type_id: str,
        llm_model: str = MOCK_LLM_MODEL,
        agent_owner: str = "A",
    ) -> dict:
        """对单份报告做 LLM 抽取 + 程序化校验 + 落候选池.

        Returns:
            {
              "report_id": ...,
              "event_type_id": ...,
              "llm_model": ...,
              "candidates_extracted": int,
              "candidates_inserted": int,
              "candidates_rejected": [{"reason": ..., "candidate": ...}, ...],
              "duration_ms": int,
            }
        """
        t0 = datetime.now(timezone.utc)

        report = self.report_repo.get(report_id)
        if not report:
            raise NotFoundException(f"report {report_id} not found")
        event_type = self.event_type_repo.get(event_type_id)
        if not event_type:
            raise NotFoundException(f"event_type {event_type_id} not found")

        report_md = report["report_md"]
        kill_chain_stages = event_type.get("kill_chain_stages", [])
        typical_signals = event_type.get("typical_signals", [])

        # 1. LLM 抽取 (或 mock 降级)
        prompt = _build_llm_prompt(report, event_type, self._valid_techniques_list())
        if llm_model == MOCK_LLM_MODEL:
            raw = ""  # 直接走 mock
        else:
            raw = await _call_llm_extract(prompt, llm_model)

        if raw:
            # 尝试解析 LLM 输出 JSON
            try:
                parsed = json.loads(raw)
                extracted = parsed.get("techniques", []) if isinstance(parsed, dict) else []
            except json.JSONDecodeError:
                logger.warning("LLM returned non-JSON, fallback to mock")
                extracted = _mock_extract(event_type_id, report_md, event_type, self._valid_techniques_list())
        else:
            # mock 降级
            extracted = _mock_extract(event_type_id, report_md, event_type, self._valid_techniques_list())

        # 2. 程序化校验 + 落库
        inserted = 0
        rejected: list[dict] = []
        for cand in extracted:
            ok, reason = self._validate_candidate(cand, report_md, kill_chain_stages)
            if not ok:
                rejected.append({"reason": reason, "candidate": cand})
                continue

            cid = _new_ulid("etc")
            try:
                self.candidate_repo.insert(
                    candidate_id=cid,
                    event_type_id=event_type_id,
                    technique_id=cand["technique_id"],
                    stage=cand["stage"],
                    confidence=cand["confidence"],
                    evidence_quote=cand["evidence_quote"],
                    rationale=cand.get("rationale", ""),
                    source_report_id=report_id,
                    llm_model=llm_model,
                    llm_run_at=t0.isoformat(),
                    agent_owner=agent_owner,
                )
                inserted += 1
            except Exception as e:
                # UNIQUE conflict (event_type_id, technique_id, source_report_id) — 视为重复
                if "UNIQUE" in str(e).upper() or "duplicate" in str(e).lower():
                    rejected.append({"reason": "duplicate_candidate", "candidate": cand})
                else:
                    logger.error("candidate insert failed: %s", e)
                    raise InternalException(f"candidate insert failed: {e}") from e

        duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        logger.info(
            "extract_for_report done",
            extra={
                "trace_id": "",
                "report_id": report_id,
                "event_type_id": event_type_id,
                "extracted": len(extracted),
                "inserted": inserted,
                "rejected": len(rejected),
            },
        )
        return {
            "report_id": report_id,
            "event_type_id": event_type_id,
            "llm_model": llm_model,
            "candidates_extracted": len(extracted),
            "candidates_inserted": inserted,
            "candidates_rejected": rejected,
            "duration_ms": duration_ms,
        }

    def bulk_extract(
        self,
        event_type_id: str,
        report_ids: list[str] | None = None,
        llm_model: str = MOCK_LLM_MODEL,
        agent_owner: str = "A",
    ) -> dict:
        """对 event_type 下的所有报告 (或给定 report_ids) 同步跑抽取.

        (为了避免脚本端复杂度, 用 asyncio.run 包装 async extract_for_report)
        """
        async def _runner() -> list[dict]:
            results = []
            for rid in report_ids or []:
                r = await self.extract_for_report(rid, event_type_id, llm_model, agent_owner)
                results.append(r)
            return results

        results = asyncio.run(_runner())
        return {
            "event_type_id": event_type_id,
            "llm_model": llm_model,
            "report_count": len(results),
            "total_extracted": sum(r["candidates_extracted"] for r in results),
            "total_inserted": sum(r["candidates_inserted"] for r in results),
            "total_rejected": sum(len(r["candidates_rejected"]) for r in results),
            "details": results,
        }


# ---------------------------------------------------------------------------
# LLM Prompt builder (私有)
# ---------------------------------------------------------------------------
def _build_llm_prompt(
    report: dict,
    event_type: dict,
    valid_techniques: list[str],
) -> str:
    """构造 LLM prompt — 严格按 DISCUSSION §7.2 规约.

    强约束:
      1) technique.id 必须在 [valid_techniques] 列表内
      2) stage 必须在 [kill_chain_stages] 列表内
      3) evidence_quote 必须是 report_md 子串
      4) confidence < 0.4 不入候选
    """
    kill_chain = ", ".join(event_type.get("kill_chain_stages", []))
    signals = ", ".join(event_type.get("typical_signals", [])[:10])
    tech_sample = ", ".join(valid_techniques[:60])  # 截断到 60 个避免 prompt 过长

    return f"""你是 ATT&CK 实例化助手. 给定一份公开安全事件报告, 抽取该事件涉及的 MITRE ATT&CK technique 候选.

事件类型: {event_type['name_zh']} ({event_type['name_en']})
定义: {event_type.get('description', '')}
典型信号: {signals}
推荐 kill chain 阶段: {kill_chain}

报告标题: {report.get('title', '')}
报告 URL: {report.get('source_url', '')}
报告正文:
\"\"\"
{report.get('report_md', '')[:2000]}
\"\"\"

可用 ATT&CK technique 列表 (你只能从中选):
{tech_sample}
... 共 {len(valid_techniques)} 项可用

输出 JSON (严格按此 schema, 不要其他说明):
{{
  "event_type_id": "{event_type['id']}",
  "techniques": [
    {{
      "id": "T1486",
      "stage": "impact",
      "confidence": 0.85,
      "evidence_quote": "≤120 字原文片段, 必须能在上面 report_md 中找到",
      "rationale": "≤80 字理由"
    }}
  ]
}}

约束 (违反任意一条, 该 technique 不应输出):
1. id 必须在上方可用列表中存在 (不要输出 T9999 等假 ID)
2. stage 必须在上方 kill chain 阶段列表内 (initial_access / execution / ...)
3. evidence_quote 必须是上面 report_md 中**逐字能找到**的片段 (≤120 字)
4. confidence ≥ 0.4, 不确定宁可不出
"""


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "EVIDENCE_QUOTE_MAX_LEN",
    "MOCK_LLM_MODEL",
    "EventTechniqueExtractService",
    "_new_ulid",
    "_normalize_text",
]
