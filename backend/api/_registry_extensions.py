"""_registry_extensions.py — 路由注册表 extension/v1 半区 (DEV-0287 D5 拆分)。

R3 行数守卫: _registry.py 291>271, 按域分组拆两半 — 本文件承载 SecNews /
DSH / info_filter / skill_registry / v1 端到端 (case/judgment/action/run/
artifact/run-ledger/command-bar/quality/knowledge/legacy/signals/events);
core + feature-flag 区见 ``_registry_core.py``。调用顺序 = 原文件顺序。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_extensions(app: FastAPI) -> None:
    """extension + v1 端到端区 (原 _registry.py L197-L289 逐字搬移)。"""
    from backend.extensions import is_extension_enabled

    # SecNews 整合 Phase 0: KL 管线 + 安全看板 (按 feature_gates 注册)
    if is_extension_enabled("secnews"):
        from backend.api import feedback_api, kl_pipeline_api, secnews_dashboard_api
        app.include_router(feedback_api.router, tags=["feedback"])
        app.include_router(kl_pipeline_api.router, tags=["kl-pipeline"])
        app.include_router(secnews_dashboard_api.router, tags=["secnews"])
    # v0.6 P0: DSH 桥接层 (按 feature_gates 注册)
    # v0.6.3: 内置化 — dsh 升级为受管子进程 (control 面启停), pi 执行 agent 同 gate
    if is_extension_enabled("dsh"):
        from backend.api import dsh_api
        app.include_router(dsh_api.router, tags=["dsh"])
        from backend.api import dsh_control_api
        app.include_router(dsh_control_api.router, tags=["dsh-control"])
        from backend.api import agents_api
        app.include_router(agents_api.router, tags=["agents"])
    # v0.8 P1 info_filter: 独立资讯筛选门禁
    if is_extension_enabled("info_filter"):
        from backend.api import info_filter_api
        app.include_router(info_filter_api.router, tags=["info-filter"])
    # v0.8 Phase A A3: skill_registry Skill 商店 (默认 false, 开闸归 A5)
    if is_extension_enabled("skill_registry"):
        # v0.8.5 修复 (流程验证 G3 发现): v1 路由必须先于 legacy /{skill_id} 参数路由注册,
        # 否则 GET /api/skill-registry/v1 被吞成 skill_id='v1' → 404 SKILL_NOT_FOUND
        # (useSkillRegistry / SkillStore v1_active 分桶自 v1.0.2 F4a 起走 v1 路径)。
        from backend.api import skill_registry_v1_api
        app.include_router(skill_registry_v1_api.router, tags=["v1-skill-registry"])
        from backend.api import skill_registry_api
        app.include_router(skill_registry_api.router, tags=["skill-registry"])
        # v0.8 Phase B B6: 运行历史 + 反馈打分 (与 A3 同 gate, 拆文件避 150 行上限)
        from backend.api import skill_registry_runs_api
        app.include_router(skill_registry_runs_api.router, tags=["skill-registry"])
    # v0.8 Phase C C3: Skill Builder (用户自建 skill)
    if is_extension_enabled("user_skills"):
        from backend.api import skill_builder_api
        app.include_router(skill_builder_api.router, tags=["skill-builder"])
    # DEV-0182 Workbench Focus: 兴趣引擎 (行为信号 + 域权重 + reset)
    if is_extension_enabled("interest_engine"):
        from backend.api import interest_api
        app.include_router(interest_api.router, tags=["interest"])
    # v0.8 Phase D D1: webhook + KL + collector 触发源适配 (webhook 端点需暴露, 沿用 trigger_gate gate)
    if is_extension_enabled("trigger_gate"):
        from backend.api import trigger_webhook_api
        app.include_router(trigger_webhook_api.router, tags=["trigger-webhook"])

    # v1.0 T08: Case 端到端 (服务+API+UI) — 无 gate 限制, 与 codegarden 等核心域同源
    from backend.api import case_api
    app.include_router(case_api.router, tags=["v1-cases"])
    # v1.0 T11: Judgment 端到端 (SK-02 cve-impact-brief) — 4 端点 (generate/list/get/publish)
    from backend.api import judgment_api
    app.include_router(judgment_api.router, tags=["v1-judgments"])
    # v1.0 T12: Action / Run / Artifact 端到端 (SK-03 inspection-materials + 验收)
    from backend.api import action_api
    app.include_router(action_api.router, tags=["v1-actions"])
    from backend.api import artifact_api, run_api
    app.include_router(run_api.router, tags=["v1-runs"])
    app.include_router(artifact_api.router, tags=["v1-artifacts"])
    # v0.8.6 P1-1 / M1: 提案审批循环 + Run 账本 (无条件 core)
    from backend.api import run_ledger_api
    app.include_router(run_ledger_api.router, tags=["run-ledger"])
    # v0.8.6 P1-4 / M4: 对话式命令栏 (无条件 core)
    from backend.api import command_bar_api
    app.include_router(command_bar_api.router, tags=["command-bar"])
    # v0.8.6 P1-5: 质量门禁拒收回放 (无条件 core)
    from backend.api import quality_api
    app.include_router(quality_api.router, tags=["quality"])
    # v0.8.6 P2: 两层质量规则管理面 (无条件 core)
    from backend.api import quality_rules_api
    app.include_router(quality_rules_api.router, tags=["quality"])
    # v1.0 T13: Knowledge 端到端 (SK-04/05/06 知识发布/复用/复查)
    from backend.api import knowledge_api
    app.include_router(knowledge_api.router, tags=["v1-knowledge"])
    # v1.0 T16 收口: audit_log 查询 + LegacyMigrate API 暴露
    from backend.api import legacy_migrate_api, observability_audit_api
    app.include_router(observability_audit_api.router, tags=["observability-audit"])
    app.include_router(legacy_migrate_api.router, tags=["legacy-migrate"])
    # v1.0 T18 旧 knowledge_items 数据迁移 API
    from backend.api import legacy_items_migrate_api
    app.include_router(legacy_items_migrate_api.router, tags=["legacy-items-migrate"])
    # v1.0 C13: LegacyMigrateServiceV1 API (3 源独立 + mapping 表 + promote)
    from backend.api import legacy_migrate_v1_api
    app.include_router(legacy_migrate_v1_api.router, tags=["legacy-migrate-v1"])
    # v1.0 T15: Signal API (Intel 入口真实化, 复用 T05 v1_signals)
    from backend.api import v1_signals_api
    app.include_router(v1_signals_api.router, tags=["v1-signals"])
    # MP-2 (DEV-0218): 事件类型实例化 — 候选 2 文件拆分 (≤150 行守卫)
    from backend.api import event_technique_api, event_types_api
    app.include_router(event_technique_api.router, tags=["event-technique"])
    app.include_router(event_types_api.router, tags=["event-technique"])
    from backend.api import cubox_import_api  # UI 收尾批 C2 (DEV-0195): cubox 导入兜底
    app.include_router(cubox_import_api.router, tags=["knowledge"])
    from backend.api import auto_intake_api  # 2026-09-26: 自动入管配置 (settings 子路径)
    app.include_router(auto_intake_api.router, tags=["settings"])


__all__ = ["register_extensions"]
