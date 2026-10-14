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

v0.8.2 (2026-09-05): 治理合批 — 子批 1 快赢包 X (B1 llm.yaml per-provider 断路器
阈值 + B2 全仓 ruff 167→0 + B3 死 gate 键治理/mcp 双开关契约化 16→13 gate +
B4 PROGRESS 归档/CHANGELOG 时序 + C2 GZipMiddleware/字典端点 Cache-Control);
子批 2 通电治理 Y (A1 utils/concurrency.py 全局并发单一真相源 — LLM 出站首次
强制执行 max_concurrent + 8 接入点; A2 feature_gates/llm.yaml/provider 阈值
5s TTL 热重载免重启; A4 backup_verify 备份完整性校验周一 job + 按需端点,
jobs 51→52 / services 107→108)。

v0.8.5 (2026-09-08): 反向收敛 demo — v0.8 Sentinel 三层恢复为唯一壳 (资料层 /
→ 判断层 /judge → 行动层 /action, SentinelLayout 全屏组 + 页内 SentinelShell
心跳条常驻), v1.0 九对象/三类 receipt 降级为三层能力区块 (SignalPanel /
CaseQueuePanel / ExecOverviewPanel); v1 四入口 /workbench /intel /cases 重定向
(透传 query), V1SentinelShell 物理删除; 守卫 v085_route_shell.test.tsx 反转;
spec = docs/v0.8.5/V0.8.5_PLAN.md。后端业务零改动 (仅版本号)。

v0.8.6 (2026-10-14): AI Native 证据工作台 — 换主干 (P0-P3 全绿, DEV-0269~0328)。
换的是主干而非加能力: 让已有能力围绕"可验证的安全判断"重新产生流量。四轴 AI Native
(①Agent 优先工作循环 ②模型驱动管线 ③全界面 AI 副驾 ④对话式驱动) 均入主轴; 主干 =
资讯→Signal→Case→Claim→Run→Artifact→Knowledge 全链 run record, 禁止"成功但无产物";
提案 (proposal) 未审批不得成事实 (人主律); 证据回执 (evidence receipt) 为一等公民。
- 主干流量: Run 账本 + 提案通道 + v1_evidence_receipts + /api/ops/runs|kpi 观测面;
  对话式命令栏 (轴④) 四类固定意图全命令 run record; 副驾四卡走提案通道 (轴③);
  ai_classify 零消费点收编 + 批级预算防失控 (轴②); 档位路由 task_overrides 三档锚点。
- 失败可见性: 静默失败三形态收口 (gate fail-open / 写库失败 / job misfire) 全部落显式
  outcome; 停机链 R1-R17 (SIGTERM 有界化 + 孤儿收割 + 重放线程化) + run.py 单实例守卫
  (pgid 锁 + 端口探活双检) + 清理类 job 告警全覆盖 + 备份卡滚动保留 (1 full + 3 增量
  roll-forward 合成) + 清理卡三档滚动模型 (retention.json qcl 7→21 三方同源)。
- 质量与归因: 质量规则两层模型 (专家规则 + AI 语义规则, DEV-0280); 内容偏好 AI 自动化
  (类目/来源第二轴 + 自动学习 + 建议采纳); 资讯赞/踩 reaction 状态型信号 → 推荐优化 v1。
- 数据与契约: 同步 SQL 离开 event loop + apply_bundle 事务化 (注入失败 base 不推进);
  deep-read wiki 分支原文真源切 llm-wiki-2.0 md; MP-2 事件类型实例化链路接通 (采集→
  ai_hub 抽取→候选池→人工审定, migration 135 补种 B/C/D/E 6 类) + 8 用例契约测试;
  统一检索 P4 (FTS5 主引擎 + CommandBar 收敛); paper sources 采集 + Cubox 本地化 .md
  导入增强 (NOT NULL 约束崩溃修复)。
详见 docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md (版本族详细文档); 权威 PRD =
docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md。

v0.8.7 (2026-10-14): 公开仓库交付收口 — 非功能补丁 (v0.8.6 主干零改动)。
PII 卫生清理: 机器本机绝对路径 → __file__ 派生 / 通用占位, 个人标识中性化,
force-add 产物 frontend/test-results/.last-run.json 移除 + .gitignore knowledge/ 规则
收紧为根锚定; 版本/文档/资产全链对齐 (version.py 单一真源 + AGENTS/CLAUDE/PROJECT/
README + CHANGELOG + assets/readme/*.svg); 承接文档中已标注 v0.8.7 的 P2/P3 收口工作
(随 v0.8.6 主干一并交付)。
"""

APP_VERSION = "0.8.7"

