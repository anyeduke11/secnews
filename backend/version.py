"""应用版本号单一来源 (Single Source of Truth)。

所有需要展示应用版本的地方 (main.py FastAPI(version=...)、
exceptions.py 错误响应体、/api/health 等) 一律从这里 import,
禁止在别处再硬编码应用版本号。

注意: API 响应体内的 ``version`` 字段若表示 *数据格式/协议版本*
(如 export envelope、sync bundle), 与应用版本无关, 不受此约束。

v0.4.3 (2026-08-16): 结构收敛 + 复利引擎落地 — 软分层 Core/Extension 架构,
见 docs/v0.4.3_prd.md。

v0.5.0 (2026-08-23): llm-wiki-2.0 数据底座 + ai_hub 单出口 — M3.5 Task13/14
graph.json 6 边运行时填入 + 一次性迁移 4149 items / 96 concepts; M5 Task19
合并 llm_service+ai_service 为 ai_hub 单出口 (ai_scores 写路径唯一);
见 docs/v0.5_refactor_plan/README.md。

v0.5.1 (2026-08-25): v0.6 P0 清场第一批 — ⑥ ai_hub 双引擎收敛
(AIService sensenova 硬编码并入 llm.yaml 单一来源) + ③ scheduler/jobs.py
按域拆分为 jobs/ 包 (空壳门面) + ⑤ 凭据单一来源 (settings 明文收敛);
见 docs/v0.6_ai_workstation_plan.md §P0。

v0.6.0 (2026-08-27): CRM 业绩座舱正式发版 — security-cockpit 方案 C 完整移植。
T1 PRD (用户故事/状态机/KPI) + T2 migration 071 三表 + T3 三路由 + T4 /crm 页面
+ T5 全栈 E2E 闭环; crm feature gate 扩展域接入; 见 docs/COCKPIT_PRD.md。

v0.7.0 (2026-08-28): workbench 报纸版 100% 接管 (Step 2 物理删除)
Step 1 (D.1-D.7) 灰度通过后, 物理删除 19+4 个 .tsx (3 三层目录 + 4 cognitive mode) + 10+6 路由;
workbench_legacy gate 退役; 根路径 / 与 404 fallback 跳 /workbench;
ReviewMode + DeepReadMode 保留为主路径, 8 个 knowledge 域组件 (KnowledgeImport/Process/Compile/Compound/FavoritesView/AttentionHeatmap) 不变;
迁移 checklist docs/v0.7_migration_checklist.md (199 行) 全 ✅.

v0.8.0 (2026-09-04): v0.8 Skills — Skill/Playbook 双轨看板型 AI 智能体 (Phase A/B/C/D 全绿)
Phase A: trigger_gate 包 (限流 + trigger_tickets 持久化队列 + 三档优先级) + skill_registry 包
(20 内置 skill 静态注册 + 反模式 linter) + /api/skill-registry API + /skill-store 前端;
Phase B: agent_loop 五阶段 + agent_memory v2 + worker 执行接线 + B6 详情页/历史回放/反馈打分;
Phase C: playbook_engine (skill/api/condition 三类 Step) + cron 调度持久化 + skill_builder
(user_skills 表 + 4 步向导) + skill_eval 5 黄金 fixtures 评测框架;
Phase D: webhook/KL 事件/collector failure 三触发源 + /dashboard 看板 + i18n 双语补齐;
见 docs/V0.8_REFACTOR_PLAN.md / docs/V0.8_USER_GUIDE.md。

v0.8.1 (2026-09-05): 运行时弹性层 + Skills 通电 — Day 0 graceful shutdown
(utils/shutdown.py: drain_in_flight 有界等在跑 job + wal_checkpoint) + 七 gate
开闸演练 (修复 user_skills gate 漏登记 P0, /api/skill-builder 首次可达) + 7 gate
通电 (mcp 回关); Day 1 CircuitBreaker 薄状态机 (utils/circuit_breaker.py, 无失败
计数单一真相源); Day 2 ProviderHealth (ai_hub/provider_health.py, 5min 滑窗判定
+ min_samples 防单发误熔断); Day 3 gateway/_call_provider 集中记账 + 4 循环
breaker skip + image 双直连点接入; Day 4 /api/observability/llm/health + reset
端点 + breaker 迁移 audit_log + quality/scenario_router.py deep 场景权重重排;
见 docs/V0.8.1_PRD.md / docs/V0.8.1_PLAN.md。
"""

APP_VERSION = "0.8.1"
