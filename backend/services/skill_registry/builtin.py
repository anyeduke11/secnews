"""skill_registry.builtin — 20 个内置 skill 静态注册 (v0.8 Phase A · A2b).

清单出处: docs/V0.8_REFACTOR_PLAN.md §4 (四个分组共 20 个);
每个 skill 注册前已按 docs/V0.8_SKILL_ABSTRACTION.md §6.2 五步流程执行:
过 abstractor 反模式门 → 人工 A-E 分类 → 按契约写 SkillDef。

target 真实性纪律 (契约规则 2 "只存引用"):
- ServiceTarget.module 全部经 importlib.find_spec 实地核验存在
- ApiTarget.path 全部为仓库中真实注册的 GET 路由 (不 import backend.api,
  只存路径字符串); 与 plan 假设不符处均已按代码为准替换, 明细见各条注释

分类对账 (§6.3 验收): A=12 / B=1 / C=4 / D=3 / E=0, 总数 20;
operations=8 / compliance=6 / analysis=4 / report=2。
"""
from __future__ import annotations

from backend.services.skill_registry.core import (
    ApiTarget,
    ServiceTarget,
    SkillDef,
    SkillRegistry,
    Step,
)

__all__ = ["BUILTIN", "BUILTIN_SKILLS"]

# ---------------------------------------------------------------------------
# 安全运营类 (operations, plan §4.1 — 8 个)
# 类型分布: A 巡检 ×5 (#1/4/5/6/8 直调 service/api 只读面) +
#           B 查询 ×1 (#7 ApiTarget 单 GET) + C 报告 ×2 (#2/3 LLM 摘要归档)
# ---------------------------------------------------------------------------
_OPERATIONS: list[SkillDef] = [
    SkillDef(
        id="source-health-scan",
        name="信源质量巡检",
        desc="扫最近 24h 死源/失败率, 输出 top 10 问题源 (A 类巡检, 零 LLM)。",
        category="operations",
        skill_type="A",
        # plan §4.1 假设 run_check(); 代码实况: SourceSchedulerService 只有
        # tick() (触发采集, 与 60s cron 冲突) 与 get_status() (读调度器状态
        # + 源健康统计) — 巡检语义取只读的 get_status, 不触发执行 (R2 精神)
        target=ServiceTarget(
            module="backend.services.source_scheduler_service",
            class_name="SourceSchedulerService",
            method="get_status",
        ),
        input_schema={"top_n": int},
        output_schema={
            "running_count": int,
            "stats": dict,  # total/active/grace/stale/dead/active_rate
        },
        feature_gate="skill.source-health-scan.enabled",
    ),
    SkillDef(
        id="weekly-top-events",
        name="本周 top 5 安全事件",
        desc="拉近 7 天安全分类热点, LLM 挑选 top 5 按重要性排序, 落 wiki 归档。",
        category="operations",
        skill_type="C",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.hotspot_service",
                    class_name="HotspotService",
                    method="list_hotspots",
                ),
                args={"category": "security", "time_range": "7d", "limit": 50},
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="ops/{{ run.date }}-top5.md",
                content="{{ steps.1.output }}",
            ),
        ],
        prompt_template=(
            "从以下近 7 天安全热点中挑出 top 5 事件并按重要性排序, "
            "每条给出标题、来源与一句重要性理由:\n{{ steps.0.output }}"
        ),
        input_schema={"top_n": int},
        output_schema={"top_events": list, "report_md": str},
        feature_gate="skill.weekly-top-events.enabled",
    ),
    SkillDef(
        id="daily-vuln-intel",
        name="今日漏洞情报聚合",
        desc="聚合本周 CVE 热力数据, LLM 去重并按严重度输出今日漏洞情报摘要。",
        category="operations",
        skill_type="C",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.cve_heatmap_service",
                    method="weekly_heatmap",
                ),
                args={"weeks": 1},
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="digest/{{ run.date }}-vuln-intel.md",
                content="{{ steps.1.output }}",
            ),
        ],
        prompt_template=(
            "从以下 CVE 数据聚合今日漏洞情报: 去重、按严重度分组、"
            "标注 CVSS ≥ 8.0 的高危项:\n{{ steps.0.output }}"
        ),
        input_schema={"weeks": int},
        output_schema={"high_risk": list, "summary_md": str},
        feature_gate="skill.daily-vuln-intel.enabled",
    ),
    SkillDef(
        id="monthly-source-failure-trend",
        name="本月信源失败率趋势",
        desc="拉单源近 30 天 crawler_runs 统计, 输出失败率/拒绝率趋势数据。",
        category="operations",
        skill_type="A",
        # 真实数据面: SourceSchedulerRepository.get_run_stats (crawler_runs
        # 按源聚合, since_hours=720 即月窗) — §1.2 判据 1 允许直调 repository
        target=ServiceTarget(
            module="backend.repository.source_scheduler_repo",
            class_name="SourceSchedulerRepository",
            method="get_run_stats",
        ),
        input_schema={"source_id": str, "since_hours": int},
        output_schema={
            "total_runs": int,
            "failed_runs": int,
            "rejection_rate": float,
        },
        feature_gate="skill.monthly-source-failure-trend.enabled",
    ),
    SkillDef(
        id="collector-health-check",
        name="采集器健康自检",
        desc="读 source_stats 历史累计快照, 输出各采集器 liveness 状态表。",
        category="operations",
        skill_type="A",
        # plan 假设 "5 min 干跑 collector" — 干跑会与 60s cron 竞态 (R2);
        # 按代码实况替换为 source_census_service.stats_snapshot (只读统计)
        target=ServiceTarget(
            module="backend.services.source_census_service",
            method="stats_snapshot",
        ),
        input_schema={},
        output_schema={"collectors": list},
        feature_gate="skill.collector-health-check.enabled",
    ),
    SkillDef(
        id="gateway-error-dist",
        name="gateway 错误码分布",
        desc="拉 api_metrics_hourly 时序聚合, 输出各路径错误数/时延分布。",
        category="operations",
        skill_type="A",
        # plan 假设 "api_events 按 status_code 聚合 top 20" — 无该现成端点;
        # 最近似真实路由: GET /api/observability/timeseries (按小时/路径的
        # total+errors+p95 聚合, 观测面 §v0.7 Batch ③)
        target=ApiTarget(path="/api/observability/timeseries"),
        input_schema={"hours": int, "path_template": str},
        output_schema={"points": list},
        feature_gate="skill.gateway-error-dist.enabled",
    ),
    SkillDef(
        id="agent-task-audit",
        name="dsh/pi 任务审计摘要",
        desc="拉 agent runner 可用性面板, 输出各 runner 协议/任务类型/可用状态。",
        category="operations",
        skill_type="B",
        # plan 假设 "agent_run_records 按 runner/status 聚合" — agent_runs 表
        # 尚无读取端点 (只有 middleware 写入); /api/agents 仅 2 路由,
        # 取只读的 GET /api/agents/available
        target=ApiTarget(path="/api/agents/available"),
        input_schema={},
        output_schema={"agents": list},
        feature_gate="skill.agent-task-audit.enabled",
    ),
    SkillDef(
        id="todo-cross-period",
        name="TODO 跨期跟踪",
        desc="拉 todos 表未完成项 (带 deadline), 输出超期/临期清单。",
        category="operations",
        skill_type="A",
        # plan 假设 "扫 wiki <TODO> 标签" — 真实机制是 todos 表
        # (TodoRepository.list 带 deadline 跨期字段), 按代码实况替换
        target=ServiceTarget(
            module="backend.repository.todo_repo",
            class_name="TodoRepository",
            method="list",
        ),
        input_schema={"status": str, "limit": int},
        output_schema={"items": list, "total": int},
        feature_gate="skill.todo-cross-period.enabled",
    ),
]

# ---------------------------------------------------------------------------
# 合规/审计类 (compliance, plan §4.2 — 6 个)
# 类型分布: 全部 A 巡检 ×6 — 合规检查天然只读, 零 LLM (设计纪律 2);
# #13 是 R12 前置 gate 检查的唯一使用者 (mcp 关 → 输出 "gate off" 跳过探测)
# ---------------------------------------------------------------------------
_COMPLIANCE: list[SkillDef] = [
    SkillDef(
        id="secrets-rotation-status",
        name="Secrets 轮换状态巡检",
        desc="拉 encryption_keys 轮换状态, 输出待轮换清单 (A 类只读巡检)。",
        category="compliance",
        skill_type="A",
        target=ApiTarget(path="/api/secrets/rotation-status"),  # secrets.py:348 实测存在
        input_schema={"role": str},
        output_schema={"rotation_status": dict},
        feature_gate="skill.secrets-rotation-status.enabled",
    ),
    SkillDef(
        id="feature-gate-matrix",
        name="Feature Gate 启用矩阵",
        desc="拉当前扩展 gate 启用清单, 与 settings kv 对账输出矩阵。",
        category="compliance",
        skill_type="A",
        target=ServiceTarget(
            module="backend.extensions",
            method="get_enabled_extensions",
        ),
        input_schema={},
        output_schema={"enabled": list},
        feature_gate="skill.feature-gate-matrix.enabled",
    ),
    SkillDef(
        id="api-route-health",
        name="API 路由健康清单",
        desc="拉观测面 summary (错误率/p95/最慢路径 top 5), 输出路由健康清单。",
        category="compliance",
        skill_type="A",
        # plan 假设 "扫 app.routes 找 501 stub" — 仓库无 501 stub 机制,
        # 且 service 层禁 import backend.api; 最近似真实路由为观测 summary
        target=ApiTarget(path="/api/observability/summary"),
        input_schema={},
        output_schema={"error_rate_pct": float, "top_slow_paths": list},
        feature_gate="skill.api-route-health.enabled",
    ),
    SkillDef(
        id="migration-consistency",
        name="数据迁移一致性校验",
        desc="跑幂等迁移器 apply_migrations, 校验 schema_version 一致性。",
        category="compliance",
        skill_type="A",
        # apply_migrations(conn) 为迁移一致性权威机制 (schema_version 记账 +
        # 幂等重放); conn 由 runner 的 RunContext 注入, 不进 input_schema
        target=ServiceTarget(
            module="backend.repository.db",
            method="apply_migrations",
        ),
        input_schema={},
        output_schema={"applied": int},
        feature_gate="skill.migration-consistency.enabled",
    ),
    SkillDef(
        id="mcp-tools-availability",
        name="MCP 19 tools 可用性",
        desc="前置检查 mcp 父 gate; 开启时拉 19 个 MCP tool 清单输出可用性。",
        category="compliance",
        skill_type="A",
        # R12: gate 关闭时直接输出 "gate off" 报告, 不探测 (避免恒报全不可用)
        requires_gate_check=["mcp"],
        target=ApiTarget(path="/api/mcp/tools"),  # mcp.py:66, 恰为 19 tools
        input_schema={},
        output_schema={"count": int, "tools": list},
        feature_gate="skill.mcp-tools-availability.enabled",
    ),
    SkillDef(
        id="wiki-root-compliance",
        name="Wiki 单根合规检查",
        desc="解析 wiki 唯一根 (resolve_wiki_root), 校验单根合规配置。",
        category="compliance",
        skill_type="A",
        # plan 假设 "扫 knowledge/ vs 白名单输出越界文件" — 无该现成函数;
        # 单根合规的权威入口是 wiki_fs.root.resolve_wiki_root (env 覆盖 >
        # llm-wiki-2.0, 2026-08-24 裁决的实现体)
        target=ServiceTarget(
            module="backend.wiki_fs.root",
            method="resolve_wiki_root",
        ),
        input_schema={},
        output_schema={"wiki_root": str},
        feature_gate="skill.wiki-root-compliance.enabled",
    ),
]

# ---------------------------------------------------------------------------
# 事件分析类 (analysis, plan §4.3 — 4 个)
# 类型分布: A ×1 (#17 FTS5 直查) + D 分析 ×3 (#15/16/18 多 service 聚合
# + LLM 推演 + wiki 落盘, 粒度锁定单源/单 CVE — §2.5 防"全量分析"陷阱)
# ---------------------------------------------------------------------------
_ANALYSIS: list[SkillDef] = [
    SkillDef(
        id="collector-failure-analysis",
        name="collector 失败事件深度分析",
        desc="单源失败统计 + 全源健康快照 → LLM 推演失败根因, 落 wiki。",
        category="analysis",
        skill_type="D",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.repository.source_scheduler_repo",
                    class_name="SourceSchedulerRepository",
                    method="get_run_stats",
                ),
                args={"source_id": "{{ input.source_id }}", "since_hours": 72},
            ),
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.source_census_service",
                    method="stats_snapshot",
                ),
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="analysis/{{ run.date }}-{{ input.source_id }}-failure.md",
                content="{{ steps.2.output }}",
            ),
        ],
        prompt_template=(
            "结合单源近 72h 失败统计 (steps.0.output) 与全源健康快照 "
            "(steps.1.output), 推演该源采集失败的根因并给出修复建议:\n"
            "单源统计: {{ steps.0.output }}\n全源快照: {{ steps.1.output }}"
        ),
        input_schema={"source_id": str},
        output_schema={"root_cause": str, "analysis_md": str},
        feature_gate="skill.collector-failure-analysis.enabled",
    ),
    SkillDef(
        id="source-lifecycle-trend",
        name="某信源首次出现到稳定趋势",
        desc="单源 30 天运行统计 + 全源健康判定 → LLM 输出健康度变化曲线解读。",
        category="analysis",
        skill_type="D",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.repository.source_scheduler_repo",
                    class_name="SourceSchedulerRepository",
                    method="get_run_stats",
                ),
                args={"source_id": "{{ input.source_id }}", "since_hours": 720},
            ),
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.source_health_service",
                    method="check_all_health",
                ),
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="analysis/{{ run.date }}-{{ input.source_id }}-lifecycle.md",
                content="{{ steps.2.output }}",
            ),
        ],
        prompt_template=(
            "基于单源 30 天运行统计 (steps.0.output) 与全源健康判定 "
            "(steps.1.output), 刻画该源从首次出现到当前的健康度变化趋势:\n"
            "单源统计: {{ steps.0.output }}\n健康判定: {{ steps.1.output }}"
        ),
        input_schema={"source_id": str},
        output_schema={"trend_md": str},
        feature_gate="skill.source-lifecycle-trend.enabled",
    ),
    SkillDef(
        id="keyword-30d-trend",
        name="某关键词 30 天热点追踪",
        desc="FTS5 全文检索 wiki 中该关键词的提及, 按日聚合输出热点追踪。",
        category="analysis",
        skill_type="A",
        target=ServiceTarget(
            module="backend.services.search_service",
            method="search_wiki_only",
        ),
        input_schema={"keyword": str, "limit": int},
        output_schema={"results": list},
        feature_gate="skill.keyword-30d-trend.enabled",
    ),
    SkillDef(
        id="cve-mention-network",
        name="某 CVE 在 wiki 的提及网络",
        desc="FTS5 检索 wiki 提及 + 安全实体图检索 → LLM 构建提及网络, 落 wiki。",
        category="analysis",
        skill_type="D",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.search_service",
                    method="search_wiki_only",
                ),
                args={"q": "{{ input.cve_id }}", "limit": 50},
            ),
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.security_graph_service",
                    class_name="SecurityGraphService",
                    method="list_entities",
                ),
                args={"q": "{{ input.cve_id }}", "limit": 50},
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="analysis/{{ run.date }}-{{ input.cve_id }}-mentions.md",
                content="{{ steps.2.output }}",
            ),
        ],
        prompt_template=(
            "基于 wiki 全文提及 (steps.0.output) 与安全实体图 (steps.1.output), "
            "构建该 CVE 的提及网络: 列出提及条目、关联实体与知识链接:\n"
            "wiki 提及: {{ steps.0.output }}\n实体图: {{ steps.1.output }}"
        ),
        input_schema={"cve_id": str},
        output_schema={"mentions": list, "network_md": str},
        feature_gate="skill.cve-mention-network.enabled",
    ),
]

# ---------------------------------------------------------------------------
# 报告生成类 (report, plan §4.4 — 2 个)
# 类型分布: 全部 C 报告 ×2 — service 拉总览数据 → LLM 自然语言化 →
# wiki digest 归档 (§2.4: "结构化 → 自然语言" 三步 pipeline 标准形态)
# ---------------------------------------------------------------------------
_REPORT: list[SkillDef] = [
    SkillDef(
        id="daily-briefing",
        name="每日安全简报生成",
        desc="跑日报总览数据 → LLM 生成每日安全简报 → 落 wiki digest 归档。",
        category="report",
        skill_type="C",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.daily_report_overview_service",
                    method="generate_daily_overview",
                ),
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="digest/{{ run.date }}-daily-briefing.md",
                content="{{ steps.1.output }}",
            ),
        ],
        prompt_template=(
            "基于今日总览数据 (主题/分类摘要/亮点) 生成一份每日安全简报, "
            "面向安全从业者, 控制在 500 字内:\n{{ steps.0.output }}"
        ),
        input_schema={},
        output_schema={"briefing_md": str},
        feature_gate="skill.daily-briefing.enabled",
    ),
    SkillDef(
        id="weekly-briefing",
        name="每周安全周报生成",
        desc="跑周报总览数据 → LLM 生成每周安全周报 → 落 wiki digest 归档。",
        category="report",
        skill_type="C",
        pipeline=[
            Step(
                kind="service",
                target=ServiceTarget(
                    module="backend.services.weekly_report_overview_service",
                    method="generate_weekly_overview",
                ),
                args={"week_start": "{{ input.week_start }}"},
            ),
            Step(kind="llm"),
            Step(
                kind="wiki",
                path="digest/{{ run.date }}-weekly-briefing.md",
                content="{{ steps.1.output }}",
            ),
        ],
        prompt_template=(
            "基于本周总览数据生成每周安全周报: 本周主线、重点事件复盘、"
            "下周关注建议:\n{{ steps.0.output }}"
        ),
        input_schema={"week_start": str},
        output_schema={"briefing_md": str},
        feature_gate="skill.weekly-briefing.enabled",
    ),
]

#: 20 个内置 skill (plan §4 官方清单; 顺序 = plan 编号顺序)
BUILTIN_SKILLS: list[SkillDef] = _OPERATIONS + _COMPLIANCE + _ANALYSIS + _REPORT

#: 模块级单例 — 沿用仓库惯例 (trigger_gate.trigger_gate / ai_hub 同款);
#: register() 内部过 loader 六条规则, 违规定义在 import 期即爆炸 (fail loud)
BUILTIN = SkillRegistry()
BUILTIN.register(BUILTIN_SKILLS)
