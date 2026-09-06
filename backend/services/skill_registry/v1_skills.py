"""v1.0 T14 6 SK 受管能力包注册 (独立文件, 避免 builtin.py 853 行膨胀).

注册顺序: SK-01 daily-priority-intel / SK-02 cve-impact-brief / SK-03 inspection-materials /
SK-04 action-retrospective / SK-05 reuse-experience / SK-06 knowledge-review-due.
复用 T11/T12/T13 已落底层 prompt + service, 通过 _register_v1_skills() 统一注册.
"""
from __future__ import annotations

from backend.services.skill_registry.core import (
    ApiTarget,
    ServiceTarget,
    SkillDef,
    SkillRegistry,
)


def build_sk01_daily_priority_intel() -> SkillDef:
    """SK-01 daily-priority-intel — 今日 top N 重点情报 (PRD SK-01)."""
    return SkillDef(
        id="daily-priority-intel",
        name="今日漏洞情报聚合",
        desc="近 7 天 admission_log + 近 3 天 signals 聚合 → top N 重点 + 关注 subject 状态变化 + 下一步建议",
        category="operations",
        skill_type="A",  # 巡检类 — 走 service.compute 内部聚合 + dsh, builtin runner 单步 target
        target=ServiceTarget(module="backend.services.skill_registry.sk01_daily_priority", class_name="DailyPriorityIntelService", method="compute"),
        prompt_template=None,
        input_schema={"type": "object", "properties": {"subject_id": {"type": "string"}, "watchlist": {"type": "array", "items": {"type": "string"}}}, "required": []},
        output_schema={"type": "object", "properties": {"top_items": {"type": "array"}, "watchlist_changes": {"type": "array"}, "suggested_actions": {"type": "array"}}, "required": ["top_items"]},
        runner="builtin",
        timeout_seconds=120,
        feature_gate="skill.daily-priority-intel.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def build_sk02_cve_impact_brief() -> SkillDef:
    """SK-02 cve-impact-brief — 是否影响指定对象 (T11 已落)."""
    return SkillDef(
        id="cve-impact-brief",
        name="漏洞影响研判",
        desc="围绕 CVE + subject 输出有证据的 claim + conditions + unknowns (contracts §5.1 三重守卫)",
        category="analysis",
        skill_type="B",  # 查询类 (走 target 单步, 内部 service 调 dsh, 走 builtin runner)
        target=ServiceTarget(module="backend.services.judgment_service", class_name="JudgmentService", method="create_with_dsh"),
        prompt_template=None,
        input_schema={"type": "object", "properties": {"case_id": {"type": "string"}, "cve_id": {"type": "string"}, "subject_name": {"type": "string"}, "evidence_materials": {"type": "array"}}, "required": ["case_id", "cve_id", "subject_name"]},
        output_schema={"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}, "claim_type": {"type": "string"}}, "required": ["id"]},
        runner="builtin",
        timeout_seconds=300,
        feature_gate="skill.cve-impact-brief.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def build_sk03_inspection_materials() -> SkillDef:
    """SK-03 inspection-materials — 准备排查材料 (T12 已落)."""
    return SkillDef(
        id="inspection-materials",
        name="漏洞排查材料生成",
        desc="从 judgment 生成受控行动 plan (≤ 50KB Markdown) + 预期产物 + 验收准则 (T12 §6.2)",
        category="analysis",
        skill_type="B",  # 查询类
        target=ServiceTarget(module="backend.services.action_service", class_name="ActionService", method="create_with_dsh"),
        prompt_template=None,
        input_schema={"type": "object", "properties": {"case_id": {"type": "string"}, "judgment_id": {"type": "string"}, "title": {"type": "string"}, "subject_name": {"type": "string"}, "cve_id": {"type": "string"}, "scope": {"type": "string"}}, "required": ["case_id", "judgment_id", "title"]},
        output_schema={"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}}, "required": ["id"]},
        runner="builtin",
        timeout_seconds=300,
        feature_gate="skill.inspection-materials.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def build_sk04_action_retrospective() -> SkillDef:
    """SK-04 action-retrospective — 从结果提炼方法 (T13 已落 knowledge_prompt)."""
    return SkillDef(
        id="action-retrospective",
        name="行动后提炼经验",
        desc="从已完成 action + artifact 提炼 knowledge (prerequisites ≥ 1 + counter_examples + review_at 必填 SK-06 触发)",
        category="report",
        skill_type="B",  # 查询类 (走 target service 调 dsh, 走 builtin runner)
        target=ServiceTarget(module="backend.services.knowledge_service", class_name="KnowledgeService", method="create_with_dsh"),
        prompt_template=None,
        input_schema={"type": "object", "properties": {"case_id": {"type": "string"}, "judgment_id": {"type": "string"}, "action_id": {"type": "string"}, "kind": {"type": "string"}}, "required": ["case_id", "judgment_id", "action_id"]},
        output_schema={"type": "object", "properties": {"id": {"type": "string"}, "status": {"type": "string"}}, "required": ["id"]},
        runner="builtin",
        timeout_seconds=300,
        feature_gate="skill.action-retrospective.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def build_sk05_reuse_experience() -> SkillDef:
    """SK-05 reuse-experience — 减少重复研究 (T13 §9.4 派生)."""
    return SkillDef(
        id="reuse-experience",
        name="复用既有经验",
        desc="新 case 检索已有 knowledge (ReuseReceipt 派生 {total, by_judgment, by_action, recent_30d}) + 条件对比 + 采用回执",
        category="report",
        skill_type="B",  # 查询类
        target=ApiTarget(path="/api/v1/knowledge/{id}/reuse"),
        prompt_template=None,
        input_schema={"type": "object", "properties": {"knowledge_id": {"type": "string"}}, "required": ["knowledge_id"]},
        output_schema={"type": "object", "properties": {"receipt": {"type": "object", "properties": {"total": {"type": "integer"}, "by_judgment": {"type": "integer"}, "by_action": {"type": "integer"}, "recent_30d": {"type": "integer"}}, "required": ["total"]}}, "required": ["receipt"]},
        runner="builtin",
        timeout_seconds=60,
        feature_gate="skill.reuse-experience.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def build_sk06_knowledge_review_due() -> SkillDef:
    """SK-06 knowledge-review-due — 及时发现经验失效 (T13 已落 scheduler job 55)."""
    return SkillDef(
        id="knowledge-review-due",
        name="经验复查提醒",
        desc="扫描 review_at 到期 published knowledge, 挂 case blocker (v1_cases.tags_json 加 knowledge_review_due:{id}); 不改 status (§9.2 硬约束)",
        category="operations",
        skill_type="A",  # 巡检类
        target=ServiceTarget(module="backend.scheduler.jobs.knowledge_review", class_name="knowledge_review_due_job", method=None),
        prompt_template=None,
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema={"type": "object", "properties": {"scanned": {"type": "integer"}, "blocked_count": {"type": "integer"}, "errors": {"type": "array"}}, "required": ["scanned"]},
        runner="builtin",
        timeout_seconds=120,
        feature_gate="skill.knowledge-review-due.enabled",
        default_enabled=False,
        requires_gate_check=["skill_registry"],
        version="1.0.0",
        status="v1_active",
    )


def _register_v1_skills(registry: SkillRegistry) -> None:
    """T14: 6 v1 SK 全部注册到 SkillRegistry (v1_active)."""
    skills = [
        build_sk01_daily_priority_intel(),
        build_sk02_cve_impact_brief(),
        build_sk03_inspection_materials(),
        build_sk04_action_retrospective(),
        build_sk05_reuse_experience(),
        build_sk06_knowledge_review_due(),
    ]
    registry.register(skills)


__all__ = [
    "build_sk01_daily_priority_intel",
    "build_sk02_cve_impact_brief",
    "build_sk03_inspection_materials",
    "build_sk04_action_retrospective",
    "build_sk05_reuse_experience",
    "build_sk06_knowledge_review_due",
    "_register_v1_skills",
]
