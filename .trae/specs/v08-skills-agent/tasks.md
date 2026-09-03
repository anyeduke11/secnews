# Tasks — v0.8 Skills Agent (4 阶段 × 22 commits, ~5.2 周)

> 分支: `refactor/v0.8-skills` (从 main, 基线 git `e066951`) · 每 commit 显式 pathspec, ≤800 行 · 主干 merge = W1-W4 末四次
> 验收公式 (R5): 阶段目标 = 基线 (pytest 3437 / vitest 370) + 累计新增用例 + **零回归** (任何回归 = 硬失败, 修复优先)

## Phase A — Skill 商店骨架 (W1, 6 commits)

- [x] Task A1: trigger-gate 单一入口 — 限流 + 排队 + 三档优先级 + worker 出队泵 (commit 36be3d1, 17 test 全绿)
  - [x] A1.1: 新建 `backend/services/trigger_gate/{core,queue,priority,throttle,worker}.py` (~650 行) — submit() 入口 / Priority 三档 (出队优先, 非抢占 R6) / token-bucket (per-user 60/min + global 600/min → 429) / TriggerWorker 1s 优先级轮询 → 派发 runner_pool + 崩溃恢复扫描
  - [x] A1.2: migration 091 — trigger_tickets + skill_runs 两表 (R3, skill_runs 为 RunHistory/Dashboard/反馈统一数据源)
  - [x] A1.3: `backend/tests/test_trigger_gate.py` ≥15 case (限流 429 / 优先级出队顺序 / kill 后 pending 重消费 / REALTIME 不抢占运行中)
- [x] Task A2a: 抽象原则落地 — 原则文档 + 反模式 linter (commit 080d117, 8 test 全绿)
  - [x] A2a.1: `docs/V0.8_SKILL_ABSTRACTION.md` (~400 行) — 三判据 (感知/触发/LLM 包装) + 5 类分类法 + 7 反模式 + 5 正反例
  - [x] A2a.2: `backend/services/skill_registry/abstractor.py` (~150 行) — 反模式 linter (客观信号: CRUD / 已有 cron / 高 QPS; A-E 分类人工裁决)
- [x] Task A2b: 20 skill 静态注册 (严格走 A2a 原则) (commit c56b08b, 43 test 全绿)
  - [x] A2b.1: `skill_registry/{core,builtin,loader,gate}.py` — SkillDef 统一契约 (R1: target/pipeline 一等公民, prompt_template 仅 C/D 类必填); 每 skill 独立 gate `skill.<id>.enabled` (settings.kv + 父 gate)
  - [x] A2b.2: 20 skill 定义 (实际归类 A=12 / B=1 / C=4 / D=3, E=0; ServiceTarget 14 module 实地核验 + ApiTarget 6 真实路由, 7 处按真实代码替换 plan 假设; #13 MCP 巡检 requires_gate_check R12); `test_skill_registry.py` 43 case
- [x] Task A3: `backend/api/skill_registry_api.py` (~150 行) — **前缀 /api/skill-registry** (既有 /api/skills 被 Phase 41 书签 CRUD 占用, 按 info_filter 先例裁决偏离, A4/A5 同步此路径) (commit 1d00e25, 17 test 全绿)
- [x] Task A4: 前端 Skill Store — `components/skills/{SkillStore,SkillCard,SkillToggle}.tsx` + V2 sentinel tokens + `SkillStore.test.tsx` 16 case (卡片为预注册态, "跑一次" B5 才生效; **路由 /skill-store** — 既有 /skills 被 Phase 41 SkillsPage 占用) (commit 3ccd703; i18n 硬编码 + TODO(D3))
- [x] Task A5: docs 同步 — `docs/V0.8_SKILLS.md` + ARCHITECTURE.md + feature_gates.toml 加 gate 默认 false + `generate_meta.py --check` 通过 (commit 9974787; trigger_gate gate 已登记, agent_loop/playbook_engine/user_skills 留 B/C 随实现登记; /api/skill-registry + /skill-store 路径偏离已记录)

## Phase B — Skill Runtime + agent_loop (W2, 6 commits)

- [ ] Task B1: agent_loop 五阶段状态机 — Intent→Plan→Execute→Reflect→Commit
  - [ ] B1.1: `backend/services/agent_loop/{core,state,checkpoint}.py` (~500 行) — 无状态函数式, REFLECT retry 1 → partial=True
  - [ ] B1.2: migration 092 — loop_checkpoints (每阶段写, 崩溃可续跑)
  - [ ] B1.3: `test_agent_loop.py` ≥15 case (含崩溃恢复续跑)
- [ ] Task B2: skill_runner — 按 skill_type 分流派单 (R2)
  - [ ] B2.1: `skill_runner/{core,dispatch,result}.py` (~400 行) — A/B 走 fast-path (resolve→execute→commit 直调 target, 不调 LLM); C/D 完整五阶段; SkillRunResult 含 run_id (skill_runs 主键)
  - [ ] B2.2: `test_skill_runner.py` ≥12 case (A 类零 LLM token / C 类产物落 wiki)
- [ ] Task B3: agent_memory v2 — `agent_memory/{memory,recall,miner}.py` (~500 行) + migration 093 (feedback_log) + recall 三路 (trigram/simhash/tag) + 偏好挖掘规则 + `test_agent_memory.py` ≥12 case (user_memory v1 接口保留)
- [ ] Task B4: dsh mock + 真子进程切换 — 改 `dsh/{bridge,supervisor,runtime}.py` (~300 行), settings.kv 持久化, 失败回退 mock + `test_dsh_runtime.py` ≥10 case
- [ ] Task B5: skill_registry 接入 skill_runner — run_skill(skill_id, params) 端到端 + `test_skill_run_e2e.py` ≥8 case (点 "信源质量巡检" → 跑完 → 产物落 wiki → 历史可查)
- [ ] Task B6: 前端 Skill 详情页 — `{SkillDetail,RunHistory,FeedbackBar}.tsx` (~400 行) + SSE 阶段进度 (A/B 类 2 阶段, C/D 类 5 阶段) + 反馈打分写 agent_memory + `SkillDetail.test.tsx` ≥12 case

## Phase C — Playbook YAML + 用户自建 Skill (W3, 5 commits)

- [ ] Task C1: playbook_engine — YAML 加载/校验/执行 (升级 codegarden_orchestration, 旧路由保留)
  - [ ] C1.1: `playbook_engine/{core,loader,executor,step}.py` (~700 行) — step 仅 skill / api (本机白名单) / condition (R7 砍 script); 50 step + 1h 上限; SkillDef 引用校验 (R8 悬空引用 → 校验失败)
  - [ ] C1.2: 3 个 examples yaml (daily-source-health 等 — 全部引用已注册 skill)
  - [ ] C1.3: `test_playbook_engine.py` ≥15 case
- [ ] Task C2: cron 触发器 — `playbook_engine/triggers/cron.py` (~300 行) APScheduler + SQLite 持久化 schedule + `test_playbook_cron.py` ≥10 case
- [ ] Task C3: user_skills + Skill Builder API — `skill_builder/{core,schema,validate}.py` (~400 行) + migration 094 + 上限 50 + 软删 + dry-run + `test_skill_builder.py` ≥12 case
- [ ] Task C4: 前端 Skill Builder UI — `SkillBuilder.tsx` (~350 行) 4 步向导 + YAML 预览 + dry-run + `SkillBuilder.test.tsx` ≥8 case
- [ ] Task C5: Eval v1 — `skill_eval/{dataset,judge,runner,report}.py` (~400 行) + 5 黄金 fixture + 报告落 SQLite + `test_skill_eval.py` ≥8 case

## Phase D — 看板收尾 + 触发器 (W4, 5 commits)

- [ ] Task D1: trigger-gate 接入 webhook + KL 事件 + collector failure
  - [ ] D1.1: `trigger_gate/triggers/{webhook,kl_event,collector_event}.py` (~300 行) — webhook: HMAC + 时间戳 ±5min + nonce (R7) + IP 白名单; KL T4 完成触发 "质量巡检" (P2-10)
  - [ ] D1.2: `test_trigger_sources.py` ≥15 case (含重放拦截 / 401 路径)
- [ ] Task D2: 前端 Dashboard — `components/dashboard/{Dashboard,SkillMatrix,TriggerTimeline,HealthCard}.tsx` (~450 行) + `Dashboard.test.tsx` ≥12 case
- [ ] Task D3: i18n 全栈双语 + a11y — I18nContext 加 skill./playbook./dashboard./trigger. 4 namespace (~80 key), **每 commit 双满** (R11) + `test_i18n_skill.ts` ≥6 case
- [ ] Task D4: tag `v0.8.0-skills` + ARCHITECTURE/PROGRESS/CHANGELOG 同步 + `generate_meta.py --check`
- [ ] Task D5: `docs/V0.8_USER_GUIDE.md` + `docs/MIGRATION_TO_V0.8.md`

# Task Dependencies

> **Phase A 验收 (2026-09-04)**: pytest **3516 passed / 6 skipped** (基线 3437 → 零回归, ≥3490 ✓) · vitest **386** (≥382 ✓) · tsc 0 错 ✓ · `generate_meta.py --check` 通过 (routers 70) · 已知偏离: A4 文案硬编码中文 + TODO(D3) (R11 每 commit 双满推迟至 D3 统一迁移, 记录于 checklist)

```
A1 (gate+migration 091) ─→ B1 (loop) ─→ B2 (runner) ─→ B5 (e2e) ─→ C1 (playbook) ─→ D1 (触发器)
A2a (原则) ─→ A2b (注册) ─→ A3 (API) ─→ A4 (前端)          B3 (memory 093) ─→ B6 (反馈 UI) ─→ D2 (Dashboard)
                                          └─→ C3 (builder 094) ─→ C4 (Builder UI)
                                              C2 (cron) ─→ D1
A5 ─→ (generate_meta 基线校验, 各 phase 末复跑)
```

- Phase 间强依赖: A → B → C → D (主干 merge 四次, 每 phase 末)
- Phase 内可并行: A2a 与 A1 无依赖可并行; B3 与 B1/B2 可并行; C2 与 C3 可并行
- 每 phase 末全量验证: pytest + vitest + tsc + `generate_meta.py --check`, 对比基线**零回归**
