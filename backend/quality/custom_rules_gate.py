"""自定义质量规则门禁三件套 (v0.8.6 P2, owner 裁决 2026-10-04)。

两层质量规则的 pipeline 执行面 (与 11 个内置 gate 同管道、同留痕、
同 P1-5 拒收回放覆盖):

- :class:`ExpertRejectGate` (hard) — action='reject' 的专家规则, strict
  模式命中即拒 (P2-5 语义); loose 打 flag 扣分。
- :class:`ExpertFlagGate` (soft)  — action='flag' 的专家规则, 命中扣分。
- :class:`SemanticRulesGate` (soft) — NL 语义规则**聚合单次 LLM 判别**
  (task="semantic_filter" STANDARD 档); fail-open 可见: LLM 失败 →
  flag ``semantic_rules_unavailable`` 零扣分 (与 P2-1 outcome 语义对齐);
  预算: ``quality.semantic_rules.max_per_batch`` (GateContext 计数,
  超限 flag ``semantic_rules_budget_exhausted`` 零扣分)。

全局开关: ``quality.semantic_rules.enabled`` (默认开; 无规则 = 零 LLM);
每 gate 开关: ``quality.gate.<name>.enabled`` (默认 True, 5s TTL 缓存,
pipeline.run_all 入口过滤)。

留痕: 命中写 quality_check_logs (gate_name=expert_reject/expert_flag/
semantic_rules) → P1-5 拒收回放自动覆盖。
"""
from __future__ import annotations

import re
import time
from typing import Any

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.repository.quality_custom_rules_repo import QualityCustomRulesRepository

# gate 开关 5s TTL 缓存 (settings 读)
_toggle_cache: dict[str, tuple[float, bool]] = {}
_TOGGLE_TTL_S = 5.0


def gate_enabled(name: str) -> bool:
    """读 ``quality.gate.<name>.enabled`` (默认 True), 5s TTL 缓存。"""
    now = time.monotonic()
    hit = _toggle_cache.get(name)
    if hit and (now - hit[0]) < _TOGGLE_TTL_S:
        return hit[1]
    try:
        from backend.repository.settings_repo import SettingsRepository

        raw = SettingsRepository().get(f"quality.gate.{name}.enabled", True)
        enabled = bool(raw) if isinstance(raw, bool) else str(raw).lower() != "false"
    except Exception:
        enabled = True
    _toggle_cache[name] = (now, enabled)
    return enabled


def clear_toggle_cache() -> None:
    """测试/改开关后立即失效缓存。"""
    _toggle_cache.clear()


def _scope_ok(rule: dict[str, Any], item: HotspotItem) -> bool:
    scope = str(rule.get("scope_category") or "").strip()
    return not scope or scope == str(getattr(item, "category", "") or "")


def _match_expert(rule: dict[str, Any], item: HotspotItem) -> bool:
    kind = rule["match_kind"]
    value = str(rule.get("match_value") or "")
    if kind == "title_contains":
        return value.lower() in (item.title or "").lower()
    if kind == "source_in":
        sources = {s.strip().lower() for s in value.split(",") if s.strip()}
        return (item.source or "").lower() in sources
    if kind == "category_equals":
        return (item.category or "") == value
    if kind == "url_matches":
        try:
            return bool(re.search(value, str(item.url or "")))
        except re.error:
            return False
    if kind == "summary_len_lt":
        try:
            return len(item.summary or "") < int(value)
        except (TypeError, ValueError):
            return False
    return False


def _hit_result(
    rule: dict[str, Any], item: HotspotItem, gate_name: str,
) -> GateResult:
    return GateResult(
        gate_name=gate_name,
        passed=False,
        score_deduction=int(rule.get("deduction", 10)),
        flags=[f"custom_rule_{rule['id']}"],
        reason=f"自定义规则「{rule.get('name')}」命中 ({rule['match_kind']})",
    )


class ExpertRejectGate(BaseGate):
    """hard — action='reject' 的专家规则 (strict 命中即拒, loose 打 flag)。"""

    gate_type = "hard"
    name = "expert_reject"

    def check(self, item: HotspotItem, context: GateContext) -> GateResult:
        rules = [
            r for r in QualityCustomRulesRepository().list_rules(
                kind="expert", enabled_only=True,
            )
            if r.get("action") == "reject" and _scope_ok(r, item)
        ]
        for rule in rules:
            if _match_expert(rule, item):
                return _hit_result(rule, item, self.name)
        return GateResult(gate_name=self.name, passed=True)


class ExpertFlagGate(BaseGate):
    """soft — action='flag' 的专家规则 (命中扣分, 仍入库)。"""

    gate_type = "soft"
    name = "expert_flag"

    def check(self, item: HotspotItem, context: GateContext) -> GateResult:
        rules = [
            r for r in QualityCustomRulesRepository().list_rules(
                kind="expert", enabled_only=True,
            )
            if r.get("action") == "flag" and _scope_ok(r, item)
        ]
        hits = [r for r in rules if _match_expert(r, item)]
        if not hits:
            return GateResult(gate_name=self.name, passed=True)
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=sum(int(r.get("deduction", 10)) for r in hits),
            flags=[f"custom_rule_{r['id']}" for r in hits],
            reason="自定义规则命中: " + "; ".join(
                f"「{r.get('name')}」(-{r.get('deduction', 10)})" for r in hits
            ),
        )


class SemanticRulesGate(BaseGate):
    """soft — NL 语义规则聚合单次 LLM 判别; fail-open 可见 + 预算封顶。"""

    gate_type = "soft"
    name = "semantic_rules"
    MAX_CONTENT_CHARS = 2000

    _SYSTEM_PROMPT = (
        "你是资讯质量规则判定器。根据用户给出的编号规则逐条判定资讯内容, "
        "只输出 JSON: {\"violated\": [违反的规则编号数组]}。"
        "无法判定某条规则时不要把它放进 violated。不要输出 JSON 以外文字。"
    )

    def check(self, item: HotspotItem, context: GateContext) -> GateResult:
        from backend.repository.settings_repo import SettingsRepository

        enabled = SettingsRepository().get(
            "quality.semantic_rules.enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() != "false"
        if not enabled:
            return GateResult(gate_name=self.name, passed=True)

        rules = [
            r for r in QualityCustomRulesRepository().list_rules(
                kind="semantic", enabled_only=True,
            )
            if _scope_ok(r, item)
        ]
        if not rules:
            return GateResult(gate_name=self.name, passed=True)

        cap = SettingsRepository().get("quality.semantic_rules.max_per_batch", 10)
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            cap = 10
        used = int(getattr(context, "semantic_llm_calls", 0))
        if used >= cap:
            return GateResult(
                gate_name=self.name, passed=True, score_deduction=0,
                flags=["semantic_rules_budget_exhausted"],
                reason=f"语义规则预算已用尽 ({used}/{cap}), 本条未判别 (可见不扣分)",
            )

        violated, error = self._evaluate_llm(rules, item)
        # pydantic 严格模式拒 setattr → 走 __dict__ 注入 (url_title_pairs 先例)
        context.__dict__["semantic_llm_calls"] = used + 1
        if error is not None:
            return GateResult(
                gate_name=self.name, passed=True, score_deduction=0,
                flags=["semantic_rules_unavailable"],
                reason=f"语义规则 LLM 判别失败 (fail-open 可见): {error}",
            )
        if not violated:
            return GateResult(gate_name=self.name, passed=True)
        hit_rules = [r for r in rules if rules.index(r) + 1 in violated]
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=sum(int(r.get("deduction", 10)) for r in hit_rules),
            flags=[f"semantic_rule_{r['id']}" for r in hit_rules],
            reason="语义规则违反: " + "; ".join(
                f"「{r.get('name')}」(-{r.get('deduction', 10)})" for r in hit_rules
            ),
        )

    # ── LLM 判别 (dry-run 复用) ──────────────────────────────────

    @classmethod
    def _evaluate_llm(
        cls, rules: list[dict[str, Any]], item: HotspotItem,
    ) -> tuple[list[int], str | None]:
        """返回 (violated 规则在列表中的序号 1-based, error)。"""
        import asyncio

        from backend.services.ai_hub import ai_service

        numbered = "\n".join(
            f"{i}. {r.get('match_value')}" for i, r in enumerate(rules, 1)
        )
        content = f"{item.title or ''}\n{item.summary or ''}"[:cls.MAX_CONTENT_CHARS]
        messages = [
            {"role": "system", "content": cls._SYSTEM_PROMPT},
            {"role": "user", "content": f"规则:\n{numbered}\n\n资讯内容:\n{content}"},
        ]
        try:
            raw = asyncio.run(ai_service.generate_text(
                messages, task="semantic_filter",
                max_tokens=300, temperature=0.0,
            ))
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
        if not raw or not raw.strip():
            return [], "empty response (model refused/unavailable)"
        try:
            import json as _json
            import re as _re

            m = _re.search(r"\{.*\}", raw, _re.DOTALL)
            if not m:
                return [], "response is not valid JSON"
            data = _json.loads(m.group(0))
            ids = data.get("violated", [])
            if not isinstance(ids, list):
                return [], "violated is not an array"
            return [int(x) for x in ids if str(x).strip().isdigit()], None
        except Exception as e:
            return [], f"parse failed: {e}"


__all__ = [
    "ExpertFlagGate",
    "ExpertRejectGate",
    "SemanticRulesGate",
    "clear_toggle_cache",
    "gate_enabled",
]
