# v0.8 Skill/Playbook 双轨看板型 AI 智能体 Spec

> 来源: `docs/V0.8_REFACTOR_PLAN.md` (2026-09-04 已应用批判性审查 R1-R13 修订) + `docs/V0.8_DECISION_REGISTER.md` (34 项裁决按推荐默认 P0-P3 全 A 推进)
> 基线: **pytest 3437 / vitest 370 / routers 68 / services 107 / migrations 87 .sql @ git `e066951`** (2026-09-03 实测)

## Why

hotspot 已沉淀 51 jobs / 404 endpoints / 107 services 的"能力暗物质"，但用户感知层只暴露一小部分；对话式 chatbox 路径已被用户裁决否决。需要把已有能力固化为**可启停的 Skill 卡片 + Playbook YAML 编排**，使 hotspot 从"数据 + 工具集合体"升级为安全从业者看板型 AI 智能体，实现资料(P)→判断(J)→行动(A) 的知识复利闭环。

## What Changes

- **新增 trigger_gate** (单一触发入口): 限流 + SQLite 持久化排队 + 三档优先级 + **TriggerWorker 出队泵** (R4 — 进程内守护线程, 1s 优先级轮询 → 派发 runner_pool 3 并发)
- **新增 skill_registry**: 20 个内置 skill 静态注册 (A2a 抽象原则 + A2b 实现), SkillDef 统一为 target/pipeline 契约 (R1), 每 skill 独立 feature gate
- **新增 agent_loop**: 五阶段状态机 (Intent→Plan→Execute→Reflect→Commit) + checkpoint 崩溃恢复; **A/B 类走 fast-path 2 阶段** (R2 — resolve→execute→commit, 不调 LLM)
- **新增 skill_runner**: 按 skill_type 分流派单 (R2) — A/B 直调 ServiceTarget/ApiTarget, C/D 走完整五阶段 + ai_hub/runner_pool
- **新增 agent_memory v2**: 升级 user_memory (v1 接口保留) — feedback_log + recall + 偏好挖掘
- **新增 playbook_engine**: 升级 codegarden_orchestration_service (旧路由保留) — YAML 加载/校验/执行 + cron 触发; **不引入 script step** (R7 — RCE 边界)
- **新增 skill_builder + user_skills 表**: 用户可视化创建 skill (上限 50)
- **新增 skill_eval**: 5 黄金 fixture + 评分 + 报告
- **新增前端三路由**: `/skills` (Skill Store) / `/playbooks` (YAML 编辑器) / `/dashboard` (状态矩阵 + 触发器时间线), Sentinel Terminal 顶部 tab
- **新增 migrations 091-094** (R3): 091 trigger_tickets + skill_runs / 092 loop_checkpoints / 093 feedback_log / 094 user_skills
- **新增 5 个 feature gate** (默认 false, fail-closed): skill_registry / trigger_gate / agent_loop / playbook_engine / user_skills
- **新增 webhook 触发**: HMAC + 时间戳 ±5min 防重放 (R7) + IP 白名单 + nonce
- **传输定稿 REST + SSE** (R6 — 不引入 WebSocket); i18n **每 commit zh-CN + en-US 双满** (R11)

## Impact

- Affected specs: 无 (全部为新增能力; codegarden_orchestration 与 user_memory 为升级保留旧接口, 不破坏既有行为)
- Affected code:
  - 新增 backend 包: `services/trigger_gate/` `services/skill_registry/` `services/skill_runner/` `services/agent_loop/` `services/agent_memory/` `services/playbook_engine/` `services/skill_builder/` `services/skill_eval/`
  - 新增 API: `api/skills.py` `api/playbooks.py` `api/dashboard.py` `api/trigger_webhook.py` (routers 68→76)
  - 修改: `backend/config/feature_gates.toml` (+5 gate) · `backend/services/dsh/` (mock/真子进程切换) · `backend/scheduler/scheduler.py` (playbook cron 接入) · `frontend/src/App.tsx` (三路由) · `frontend/src/contexts/I18nContext.tsx` (+~80 key)
  - 新增前端: `components/skills/*` (7 组件) + `components/dashboard/*` (4 组件) + `hooks/useSkillRegistry.ts` 等 3 hook + `types/skill.ts`
  - 新增 migrations: 091-094 (编号紧接现有 090)
  - 复用不动: ai_hub (3492 行) / agents.yaml 4 runner / ProcessSupervisor / alert_engine / wiki-first / MCP 19 tools (不包装为 skill, P1-7)

## ADDED Requirements

### Requirement: 触发单一入口 (trigger-gate)
系统 SHALL 使全部 skill/playbook 触发 (手动按钮 / cron / webhook / KL T1-T5 事件 / collector failure) 经 trigger-gate 排队后执行, 不存在绕过入口的直接调用路径。

#### Scenario: 手动触发经队列
- **WHEN** 用户点 Skill 卡片 [跑一次] 按钮 (POST /api/skills/{id}/run)
- **THEN** 返回 ticket_id, REALTIME 优先级入 trigger_tickets 表, 由 TriggerWorker 出队派发, SSE 推送阶段进度

#### Scenario: 限流
- **WHEN** 单用户 1 分钟内提交第 61 次
- **THEN** 返回 429, 不入队

#### Scenario: 崩溃不丢
- **WHEN** 进程在 ticket pending 期间被 kill
- **THEN** 重启后 TriggerWorker 扫描超时 pending ticket 重新入队消费

### Requirement: 优先级调度 (非抢占)
优先级仅在出队时排序 (REALTIME→NORMAL→BATCH), SHALL NOT 抢占已运行任务 (R6)。

#### Scenario: 出队顺序
- **WHEN** 队列同时存在 BATCH 与 REALTIME ticket 且 runner_pool 有空位
- **THEN** REALTIME 先出队; 运行中任务不被中断

### Requirement: Skill 注册与启停 (skill_registry)
系统 SHALL 提供 20 个内置 skill (A 巡检 8 / B·A 合规审计 6 / D 事件分析 4 / C 报告 2), 每个含 skill_type (A-E) + target/pipeline + input/output schema + 独立 feature gate (`skill.<id>.enabled` settings.kv + 父 gate)。

#### Scenario: 一键启停
- **WHEN** 用户 toggle 卡片启停
- **THEN** 写 settings.kv + audit_log, SSE 推 skill_state_changed, 卡片徽章实时更新

#### Scenario: 反模式拦截 (A2a)
- **WHEN** abstractor (反模式 linter) 检测到 CRUD 内部端点 / 已有 cron 高频 job / 高 QPS 路径
- **THEN** 输出反模式警告, 不生成 skill 草稿 (A-E 分类由人工裁决, 机器只拦客观反模式)

### Requirement: 执行分流 (skill_runner, R2)
- A/B 类 SHALL 走 fast-path (resolve→execute→commit, 直调 service/API target, 不调 LLM)
- C/D 类 SHALL 走完整五阶段 (含 LLM 调用与 reflect retry 1)
- 全部产物 SHALL 写 skill_runs 表 (RunHistory/Dashboard/反馈的统一数据源, R3)

#### Scenario: A 类快速返回
- **WHEN** 用户触发 "信源质量巡检" (A 类)
- **THEN** 直调 SourceSchedulerService.run_check(), 耗时接近直调 service, 不产生 LLM token 消耗

#### Scenario: C 类完整链路
- **WHEN** 用户触发 "每周安全周报生成" (C 类)
- **THEN** 五阶段执行, 产物落 llm-wiki-2.0, 历史可在 RunHistory 查询

### Requirement: 状态机与崩溃恢复 (agent_loop)
agent_loop SHALL 在每阶段结束写 loop_checkpoints (migration 092), REFLECT 失败自动 retry 1 次, 仍失败 commit partial=True。

#### Scenario: 崩溃续跑
- **WHEN** EXECUTE 阶段后进程崩溃
- **THEN** 重启后从 checkpoint 恢复, 不重跑已完成阶段

### Requirement: 记忆闭环 (agent_memory v2)
系统 SHALL 记录用户反馈 (feedback_log), 提供 intent 召回 (trigram+simhash+tag 三路), 偏好挖掘 (avoid_skill / prefer_runner / prefer_style)。

#### Scenario: 反馈可召回
- **WHEN** 用户对某次 skill 跑 👍 并评论, 之后触发相似 intent skill
- **THEN** recall API 命中 ≥1 条该历史

### Requirement: Playbook YAML 编排 (playbook_engine)
系统 SHALL 加载/校验/执行 Playbook YAML (JSON Schema 校验 + Jinja 表达式), step 类型仅限 skill / api (本机 /api/* 白名单) / condition; step 上限 50 + 总时长 1h; **script step 不实现** (R7)。

#### Scenario: cron 自动触发
- **WHEN** daily-source-health playbook 已启用, 到达 08:00 (Asia/Shanghai)
- **THEN** cron 触发经 trigger-gate (BATCH), 步骤依 if 条件执行, 异常自动建 ticket, 产物落 wiki

#### Scenario: 防死循环
- **WHEN** playbook 执行超 50 step 或 1h
- **THEN** 强制停止 + 写 audit

### Requirement: 用户自建 Skill (skill_builder)
用户 SHALL 可通过 Skill Builder API/UI 创建 skill (存 user_skills 表, migration 094), 支持软删与 dry-run; 总量上限 50; 示例 YAML 引用的 skill 必须已注册 (R8 — 不允许悬空引用)。

#### Scenario: 自建跑通
- **WHEN** 用户创建 "我的日报" skill 并启用
- **THEN** 出现在 Skill Store 末尾, 跑通后历史可查

### Requirement: Webhook 外部触发 (D1)
webhook 端点 `/api/trigger/webhook/{source}` SHALL 校验 HMAC 签名 + 时间戳 ±5min + nonce (防重放, R7) + IP 白名单, 通过后以 REALTIME 入队。

#### Scenario: 重放拦截
- **WHEN** 同一有效签名的请求在 10 分钟后重发
- **THEN** 时间戳超窗, 返回 401, 不入队

### Requirement: 前端三页面看板
- `/skills`: 20 卡片网格 + cat/runner/状态筛选 + 启停 + 跑一次 + 历史; Phase A 末为**预注册态** (跑一次按钮 B5 才生效, 验收明示)
- `/playbooks`: monaco YAML 编辑器 + 实时校验 + dry-run
- `/dashboard`: skill 状态矩阵 + 触发器时间线 + 健康卡片 (echarts) + 反馈统计
- 全部走 `apiFetch` + 错误信封 `{detail: {message, code, hint}}` 三字段必填 + snake_case 类型契约

### Requirement: 一致性保障 5 锁
字段命名锁 (snake_case) / 错误信封锁 / 类型同步锁 (`scripts/gen_ts_types.py` Pydantic→TS, CI drift 校验) / i18n key 锁 (每 commit 双满) / feature_gate 锁 (注册必声明 gate)。

### Requirement: BS-Agent 9 特性可测验收 (R9)
9 特性 = 单一触发入口 / 优先级调度 / 持久化队列 / 执行状态机 / 多 runner 派发 / 记忆闭环 / 产物沉淀 / 多步编排 / 事件推送 (SSE)。现状 3/9 (#5/#7/#9), 期末 SHALL 9/9 且每项挂可测验收 (见 plan §19.7.1)。

## MODIFIED Requirements

### Requirement: feature_gates.toml 扩展
[extensions] 新增 skill_registry / trigger_gate / agent_loop / playbook_engine / user_skills 五项, 默认 false (fail-closed — 路由不注册 + job 不调度 + 前端 tab 隐藏, 沿用 v0.4.3 机制)。

### Requirement: dsh 运行时切换
dsh SHALL 支持 mock/真子进程切换 (settings.kv 持久化); 真子进程失败自动回退 mock, supervisor max_restarts=3。v0.8 大脑 = ai_hub + agent_loop, dsh 真二进制留 v0.9+ (P2-1)。

## REMOVED Requirements

（无 — v0.8 全部为新增/升级, 旧接口 user_memory v1 / codegarden_orchestration 路由保留兼容）

**明确不引入**: Playbook script step (RCE 边界, R7) · WebSocket (R6) · E 类操作型 skill (P1-6 留 v0.9) · MCP 19 tools 包装为 skill (P1-7) · Skill Marketplace / 跨用户分享 (v1.0) · HITL 主动打断 (v0.9)。
