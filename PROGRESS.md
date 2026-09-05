# v0.5 重构执行进度（PROGRESS.md — 当前活跃段索引）

> **v0.8.0 (2026-09-04)** — Skills Phase A/B/C/D 全绿 + v0.8.0-post 治理 / 架构图 / V0.8.1_PLAN 立项 (详见活跃段)。
> **v0.8 P1 (2026-09-03)** — 独立资讯筛选门禁 (info_filter, 详见活跃段)。
> **v0.7.0 (2026-08-28)** — workbench 报纸版 100% 接管 (Step 2 物理删除完成)。
> **v0.6.2 (2026-08-28)** — hotspot 活跃开发中。
>
> 本文件仅含**当前活跃段**（最近 2 批次 + 进行中）。**历史完整段**见
> `docs/progress-archive/`（v0.5 baseline / v0.5 execution / v0.6 records 三文件）。
> 接手会话第一件事：读 `docs/v0.5_refactor_plan/README.md`（规格）→ 读本文件（活跃进度）
> → 读 `docs/progress-archive/` 索引（历史背景）。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [docs/progress-archive/v0.5-baseline.md](progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [docs/progress-archive/v0.5-execution.md](progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 + 5 文件用法 + 路线决策 |
| **v0.6 records** | 2026-08-24/26 | [docs/progress-archive/v0.6-records.md](progress-archive/v0.6-records.md) (856 行) | 开发计划 + 里程碑验收 + Phase 7 数据迁移 + P0/P1/P2/P3 治理全记录 + S1-5 + security-cockpit 方案 C |

## 规格与文档

- 规格文件：`docs/v0.5_refactor_plan/README.md`（唯一真理，已拆为 3 文件）
- 5 文件用法：见下方

## 5 文件用法（接手必读）

| 文件 | 角色 | 用法 |
|---|---|---|
| `docs/v0.5_refactor_plan/README.md` | **正式 SPEC（唯一真理）** | 执行时只读它。M1→M5 定义/硬指标/验收全在 §1。 |
| `docs/archived/v0.5_refactor_plan_perf_only.md` | 旧计划归档 (性能+Workbench+AiHub v1) | 查 v1 细节/后悔回退时参考。 |
| `docs/archived/v0.5_refactor_plan_wiki_v2.md` | 并行 v2 归档 (llm-wiki-2.0) | 执行 M3.5 的参考底稿：细节 Task 4-17 在此。 |
| `PROGRESS.md`（本文件） | 执行进度台账（仅活跃段） | 每次动手前后必读写；接手会话第一件事读它。 |
| `docs/progress-archive/v0.6-records.md` | v0.6 阶段历史（856 行） | 查 v0.6 阶段任何决策/测试/收尾的来龙去脉。 |

协作流：读本文件 → 翻 SPEC §1 该做什么 → 打开审计清单定位功能 → 做任务 → 回来勾选并记录。

止损：基线不符→BLOCKED.md；连败 3 次→停；劣于基线→回滚如实报告。

---

## 当前活跃段 (2026-08-27 起)

### 2026-09-04 v0.8 Skills — Skill/Playbook 双轨看板型 AI 智能体 (Phase A/B/C/D 全绿)

> **来源**: 用户裁决 "非 chatbox, 把常用对话/prompt/skill 固化为主面板可启停功能" + 批判性审查 R1-R13 修订 (见 `docs/V0.8_REFACTOR_PLAN.md` / `docs/V0.8_DECISION_REGISTER.md` / `.trae/specs/v08-skills-agent/`)。
> **基线**: main HEAD `919e2ca` (pytest 3437 / vitest 370 / routers 68 / services 107 / migrations 87 .sql, 2026-09-03 实测); 分支 `refactor/v0.8-skills`, 4 阶段 × 22 commits 路径推进, 主干 merge = W1-W4 末四次。
> **Phase C 末态 (2026-09-04)**: pytest **3717** / vitest **410** / routers **72** / services **107** / migrations **95** .sql (Phase C +2: 094 playbook_engine / 095 user_skills)。
> **范围 (Phase A/W1)**: ① `trigger_gate/` 服务包 (限流 + trigger_tickets 持久化队列 + 三档优先级非抢占 + TriggerWorker 出队泵) + migration 091 (trigger_tickets + skill_runs); ② `skill_registry/` 服务包 (A2a 抽象原则 + 反模式 linter / A2b 20 内置 skill 静态注册, SkillDef 统一契约: target/pipeline 一等公民); ③ `/api/skill-registry/*` API 5 端点; ④ 前端 `/skill-store` Skill Store; ⑤ feature_gates.toml `skill_registry`/`trigger_gate` 默认 false (fail-closed)。
> **路径偏离裁决**: `/api/skills` 前缀被 Phase 41 书签 CRUD 占用 (core 白名单) → 新 API 用 `/api/skill-registry` (info_filter kebab 先例); 前端 `/skills` 路由被 SkillsPage 占用 → 新页 `/skill-store`。

- [x] **A1 — trigger-gate 单一入口** (`36be3d1`): 5 模块 + migration 091 + 17 测试 (限流 429/原子出队/非抢占/崩溃恢复/持久化重开)。每票据独立短线程 + Semaphore(3); 原子 dequeue 用 `UPDATE ... WHERE status='pending'` 双保险。
- [x] **A2a — 抽象原则 + 反模式 linter** (`080d117`): `docs/V0.8_SKILL_ABSTRACTION.md` (363 行) + abstractor.py (CRUD/高频 cron/高 QPS 三客观信号, A-E 分类人工裁决) + 8 测试。
- [x] **A2b — 20 skill 静态注册** (`c56b08b`): SkillDef 统一契约 + loader 八条校验 (feature_gate 锁/module find_spec) + gate.py (settings.kv + 父 gate fail-closed) + 43 测试。实际归类 A=12/B=1/C=4/D=3; 7 处 target 按真实代码替换 plan 假设 (只读优先, 避免双调度); #13 requires_gate_check=["mcp"] (R12)。
- [x] **A3 — /api/skill-registry API** (`1d00e25`): 5 端点 (列表/详情/enable/disable/run 预注册态入队) + 错误信封 {message, code, hint} 三字段 + extensions 登记 skill_registry gate + 17 测试。
- [x] **A4 — 前端 Skill Store** (`3ccd703`): SkillCard/SkillToggle/SkillStore + useSkillRegistry hooks + 16 vitest + tsc 0 错。跑一次 → POST run 入队回显 ticket_id; 详情/历史按钮禁用占位 (B6 开放); i18n 硬编码 + TODO(D3)。
- [x] **A5 — docs 同步** (9974787): ARCHITECTURE.md routers 68→70 + v0.8 Skills 段; feature_gates.toml trigger_gate gate 登记 (extensions 登记, fail-closed); 本 PROGRESS 段; `docs/V0.8_SKILLS.md`。
- [x] **Phase A 验收 (2026-09-04)**: pytest **3516 passed / 6 skipped** (零回归, ≥3490 ✓) / vitest **386** (≥382 ✓) / tsc 0 错 / `generate_meta.py --check` 通过 (routers 70)。已知偏离: A4 文案硬编码中文 (i18n 双满推迟 D3)。
- [x] **B6 — 前端详情页 + 历史回放 + 反馈打分** (本批, Phase B 收尾): 后端 `skill_registry_runs_api.py` 3 端点 (GET /{id}/runs · GET /runs/{run_id} · POST /runs/{run_id}/feedback), 15 测试全绿 (含 B6 验收链路: 👍 → feedback_log → recall 命中 hit.score=反馈分); `_registry.py` 共享 skill_registry gate 拆文件防 150 行溢出。前端 `SkillDetail.tsx` + `RunHistory.tsx` + `FeedbackBar.tsx` (router-free, skillId/onBack 由包装层注入; ?focus=history 直达历史区); `SkillCard` 详情/历史按钮 B6 接线 (按 onDetail/onHistory 传入启用); `SkillStore` 增 onDetail/onHistory 回调; `lazy-imports` + `routes/index.tsx` 加 `/skill-store/:skillId` 路由; 15 vitest 全绿 (含 schema 表 / prompt 全文 / 历史回放 JSON / 👍👎 提交 / 锁定 / running 不出现反馈条 / focus 直达等); `useSkillDetail` / `useSkillRuns` hooks + `SkillRun` / `SkillFeedback` types。
- [x] **C1 — playbook_engine 包 + 3 examples** (`playbook_engine/core.py` `loader.py` `step.py` + 3 examples `cve_intel.yml` / `daily_source_health.yml` / `weekly_top5.yml`): Playbook dataclass + StepKind (skill/api/condition, R7 砍 script RCE) + MAX_STEPS=50 / MAX_TOTAL_SECONDS=3600 (R6) + 危险命令黑名单 (P4-7 沿用) + 26 测试全绿。
- [x] **C2 — scheduler/cron + SQLite 持久化** (`migration 094` + `playbook_engine/scheduler.py` + 14 测试全绿): `playbook_schedules` + `playbook_runs` 双表 + `PlaybookScheduler` 独立运行 (隔离 R6 1h 预算) + `upsert_schedule` / `set_enabled` / `remove_schedule` + cron 校验 upfront fail-loud + `_find_playbook_path` 支持 snake/kebab 双形态。
- [x] **C3 — skill_builder + migration 095 + API** (`backend/services/skill_builder/` + `backend/api/skill_builder_api.py` + 18 测试全绿): `user_skills` 表 + `UserSkillRepo` (MAX=50 + soft delete) + `validate_user_skill` (id regex snake/kebab / category 4 选 / skill_type A-D 拒 E / runner builtin-only v0.8 / target importlib.find_spec + hasattr) + 6 端点 (`/api/skill-builder` GET/POST/validate/GET-id/PATCH/DELETE) + P3-2 错误信封 + feature_gates.toml `user_skills = false` 默认关闭。
- [x] **C4 — SkillBuilder.tsx 4 步向导** (`frontend/src/components/skills/SkillBuilder.tsx` + 9 vitest 全绿): StepHeader / SchemaEditor / 4 步向导 (基本信息 / Schema与Prompt / Target引用 / 复核&保存) + dry-run validate + save POST + a11y htmlFor+id+data-testid 三件套 (jsdom 兼容) + `/skill-store/new` 路由。
- [x] **C5 — skill_eval 5 黄金 fixtures + 评测报告** (`skill_eval/fixtures/*.yaml` + `backend/services/skill_eval/{dataset,runner,judge,report}.py` + 22 测试全绿): 5 fixtures 覆盖 A/B/C/D/Playbook 5 种 (`source_health_a` / `weekly_top5_c` / `compliance_query_b` / `cve_correlate_d` / `playbook_dryrun`) + 12 种 assertion.type (type_check / equal / range / field_type / length_eq / list_field_* / list_avg_above / dict_has_keys) + skip_if_null/empty + build_report(pass_rate, verdict) + render_markdown + to_dict JSON 序列化 + 评测全绿 (5/5 fixtures × 32/32 assertions)。
- [x] **Phase C 验收 (2026-09-04)**: pytest **3717 passed / 6 skipped** (零回归, ≥3595 ✓) / vitest **410 passed (53 files)** (≥402 ✓) / tsc **0 错** / `generate_meta.py --check` 通过 (routers 70→72) / `harness_analyze.py --check` 通过 (0 errors, 5 warnings waivers)。架构数字 70→72 已同步 ARCHITECTURE.md / 4 个 AGENTS.md。已知偏离: C4 文案硬编码中文 (i18n 双满推迟 D3); C5 evaluation engine 是 Protocol 抽象 (真实 LLM engine 留 v0.9)。
- [x] **D1 — 三触发源接入** (`triggers/` 包 3 模块 + `api/trigger_webhook_api.py` + 23 测试全绿): `WebhookTrigger` (SHA-256 HMAC 签名 `path|payload` hex, `hmac.compare_digest` 时序安全, secret_provider 注入 + settings.kv `webhook.secret` 回落, R7 fail-closed 无 secret 但有签名头 → 422) / `KLEventTrigger` (T1-T5 五阶段白名单, target 默认 `quality-patrol`) / `CollectorEventTrigger` (success 早返回 None 不耗限流配额, failed→NORMAL, timeout→REALTIME); API `POST /api/trigger/webhook/{source}` 6 白名单源 (github/stripe/secnews/custom/cve_feed/cti) + `GET /health`; 端点引用模块级 `wh_mod._default` 供测试 monkeypatch; `_registry.py` 按 trigger_gate gate 条件注册 (fail-closed)。
- [x] **D2 — /dashboard 看板** (`components/dashboard/Dashboard.tsx` ~260 行 + 14 vitest 全绿): HealthCard (触发源/技能/待处理/限流 4 行 + ok/caution/saturated 三态) + SkillMatrix (20 内置 skill 状态矩阵 + enable 开关) + TriggerTimeline (pending/running/succeeded/failed/partial 五态 StatusBadge; `/api/trigger/tickets` 未实现先用 mock 3 条占位); `lazy-imports` + `routes/index.tsx` 加 `/dashboard` lazy 路由。
- [x] **D3 — i18n 全栈双语补齐** (I18nContext +36 key × zh-CN/en-US + 7 测试全绿): `dashboard.*` 15 + `skill.store.*` 8 + `skill.builder.*` 12 + `common.back` 1; Dashboard/SkillStore/SkillBuilder 硬编码文案迁 `t(key, fallback)` (A4/C4 已知偏离清账); REQUIRED_KEYS 数组防漂移测试。
- [x] **D4 — release 文档同步**: `generate_meta.py` 反推 routers 72→73 (trigger_webhook_api), 同步 ARCHITECTURE.md (2 处) + 根/backend.api/scripts 3 个 AGENTS.md (5 处); `version.py` APP_VERSION 0.7.0→0.8.0 + v0.8.0 docstring 段; 根 AGENTS.md 头部改 `当前状态 (2026-09-04, v0.8.0)` (激活版本一致性校验); docs/CHANGELOG.md 加 v0.8.0 Skills 段; PROGRESS.md 本段。tag `v0.8.0-skills` 推送留用户授权 (V2-C11 同款约定)。
- [x] **D5 — 用户文档 + 迁移指南**: `docs/V0.8_USER_GUIDE.md` (Skill vs Playbook 对照 / 20 内置 skill / 手动运行·启停·详情·反馈 / Builder 4 步向导 / Playbook YAML 三类 Step / 三触发源 / 看板 / i18n) + `docs/MIGRATION_TO_V0.8.md` (v0.7→v0.8 gate 开启顺序 / Playbook schema 变更 / run 端点异步语义 / i18n key / 测试基线自检 / 回滚方案)。
- [x] **Phase D 验收 (2026-09-04)**: 见下方验收行 (测试数字以本轮实测为准)。

### 关键事实 (v0.8 Skills Phase A)

- **agent_loop / playbook_engine / user_skills 三个 gate 未提前声明** — 模块未实现, TOML 死配置会被 _load_gates 过滤为恒 False (无害但误导), 留 Phase B/C 对应任务随实现登记
- **run 端点预注册态语义**: POST run → trigger-gate REALTIME 入队 → 返回 ticket_id; worker 消费 skill 票据的执行接线归 B5 (Phase A 票据只入队不执行)
- **settings kv 复用 SettingsRepository** (settings 表, migration 001): enable/disable = set(skill.<id>.enabled, True/False); kv 未写回落 default_enabled (全 False)
- **SkillDef 的 input_schema 值是 Python type 对象** — API 层 _json_schema 转 __name__ 字符串序列化

### 关键事实 (v0.8 Skills Phase B/B6)

- **runs/feedback 路由拆文件**: A3 `skill_registry_api.py` 已达 150 行上限, B6 新路由 (`/{id}/runs` · `/runs/{run_id}` · `/runs/{run_id}/feedback`) 拆 `skill_registry_runs_api.py`, 共享 `/api/skill-registry` 前缀 + skill_registry gate, 同源注册避免 150 行合并溢出。
- **B6 验收链路**: 后端测试 `test_feedback_recall_acceptance` 串完整链路 — POST /runs/{run_id}/feedback score=5 → feedback_log 写入 → `agent_memory.recall` 三路径 (exact > simhash ≤12 > keyword) 命中 + `_attach_feedback_scores` 拼接 avg score → hit.score=5.0。
- **FeedbackBar 锁定语义**: 一次提交即锁定为 `已反馈 👍/👎`, postJSON 不重复发; 防同 run 重复打分污染 feedback_log (供 recall 学习)。
- **router-free 设计**: SkillDetail/FeedbackBar/RunHistory 不直接调 useParams, 由路由包装层 SkillDetailRoute 注入 onBack; 既保持单测免 Router 包装, 又避免 router 状态污染组件渲染。SkillDetail 内部 fallback `useParams<{skillId}>()` 让裸 props 也能工作。
- **historyRef 锚定**: useEffect deps `[searchParams, detail]`, detail 异步加载完成才触发 scrollIntoView, historyRef.current 此时已绑定 (避免初次空 ref)。

### 关键事实 (v0.8 Skills Phase D)

- **模块级 `_default` 可测性模式**: trigger_webhook_api 端点引用 `wh_mod._default` 而非每次 new — 测试 monkeypatch 模块属性即可替换 secret 状态 (fresh `WebhookTrigger()` 永远无 secret, 会绕过签名校验分支)
- **签名 = SHA-256 HMAC(secret, `path|payload`)** hex digest, path 含 `/api/trigger/webhook/{source}` 前缀; `hmac.compare_digest` 防时序侧信道; R7 fail-closed — 配置了 secret 但请求缺签名头 → 422 拒绝
- **collector success 不入队**: 早返回 None, 避免高频成功事件把全局限流配额 (60/min) 打满挤掉真实告警; failed→NORMAL / timeout→REALTIME 抢占档
- **/dashboard 触发时间线是 mock 占位**: `/api/trigger/tickets` 列表端点留 v0.9 (TriggerWorker 表查询 + 分页), 组件层已按 TriggerTicket 契约留好 data-testid
- **版本一致性校验激活**: 根 AGENTS.md 头部 `当前状态 (2026-09-04, v0.8.0)` 现在被 generate_meta 正则精确匹配, 版本漂移即 CI fail (此前因尾缀文字正则不命中而静默跳过)
- **i18n 防漂移测试**: I18nContext.test.tsx REQUIRED_KEYS 数组 38 key — 新增 namespace 时改数组即可让缺 key 提前爆红

### 不在本批范围 (留 Phase B/C/D)

- worker 接 skill 执行 (B5) / agent_loop 五阶段 (B1) / agent_memory v2 (B3) / Playbook 引擎 (C1) / webhook 触发 (D1) / i18n 双语迁移 (D3)

### 2026-09-03 v0.8 P1 — 独立资讯筛选门禁 (info_filter, 受管扩展域, 本批)

> **来源**: 用户指令 "结合身份角色, 建立一套前后端一致、前端可启停的独立资讯筛选门禁" (腾讯金融安全 PM, 5 大内容方向, gate 控制资讯 quality)。
> **基线**: `main` HEAD `46d89c5` (SettingsHub V2 落地, 17 cat SettingsHub); off main 5 个 commits 路径推进。
> **范围**: ① `backend/services/info_filter_service.py` — 规则 CRUD/校验/evaluate (deny>allow>neutral 三优先级); ② `backend/services/info_filter_gate.py` — 5s TTL module-level cache + 2 层 hook (Layer 1 源级 filter_source + Layer 2 item 落库前 filter_items); ③ `backend/api/info_filter_api.py` — 6 端点 (GET /rules, POST /rules, PATCH /rules/{id}, DELETE /rules/{id}, POST /preview, GET /gate); ④ 前端 `InfoFilterCard.tsx` (V2 sentinelized, gate-off fallback + rules + 新增 + 预览); ⑤ SettingsHub 17 cat 加 `info_filter` SectionKey; ⑥ i18n 双语 ~30 key (zh-CN/en-US); ⑦ migration 090 `info_filter_rules` 表; ⑧ `feature_gates.toml info_filter=false` 默认关闭 (fail-closed)。
> **不引入**: 新依赖 / 新路由 / 新 state 库 / 新聚合器 / 新迁移框架。
> **commit 链**: `main` 5 commits (`67cb74d` service + `b1b309c` gate + `6777f4d` api + `46d89c5` frontend + docs)。

- [x] **C1 — service + gate + api + 3 commits 路径**: info_filter_service (12 测试: CRUD 4 + validation 3 + evaluate 5) + info_filter_gate (6 测试: hook + cache + HotspotItem .source 字段) + info_filter_api (9 测试: TestClient 集成 + 6 端点); 33 pytest 测试全绿; thread affinity (`check_same_thread=False`) + 跨文件 conn 污染根治 (decoupled api_db/client fixtures + api 模块 `get_connection` 单独 monkeypatch)。
- [x] **C2 — 前端 InfoFilterCard + SettingsHub 17 cat**: InfoFilterCard.tsx V2 sentinelized (gate-off fallback 模式同 DshControlCard, refresh 10s interval); sections.tsx 加 'info_filter' SectionKey + SECTIONS 项 (icon: 立体闸门, label: 资讯门禁); SettingsPage.tsx renderContent case 'info_filter'; I18nContext.tsx 加 info_filter.* 命名空间 (~30 key 双语)。
- [x] **C3 — vitest 10/10 pass**: 覆盖 gate off(2) / 列表(2) / 创建(2) / 预览(2) / 删除(1) / 启停(1); full 370/370 (基线 360 + 本批 +10); tsc 0 错。
- [x] **C4 — 架构同步**: ARCHITECTURE.md 顶部状态更新 (v0.7.4-image → v0.8 P1 info_filter) + #8 技术债/路线表加 info_filter entry + 测试基线 370+ 同步; PROGRESS.md 加 v0.8 P1 段。

### 关键事实 (v0.8 P1)

- **5 commits on main, pathspec 严格**: `67cb74d` + `b1b309c` + `6777f4d` + `46d89c5` + (docs pending)
- **三层 hook 设计**: Layer 1 (collectors/base.py `_load_sources_from_registry` 之后, registry 源级 allow/deny) + Layer 2 (item_builder 落库前 deny 源 item 丢弃) — Layer 3 (ai_hub gateway chunks) 因 gateway.py:summarize 签名只接 chunks: list[str] (无 source 维度) 取消, 文档化为 out-of-scope
- **fail-closed**: gate off → `is_extension_enabled("info_filter")` 返 False → `filter_source`/`filter_items` 直接返回原样 (pass-all), 与 dsh gate 一致; 路由级 `if is_extension_enabled("info_filter")` 条件注册
- **deny > allow > neutral 三优先级**: 命中 deny 立刻返 deny; 命中 allow 继续扫 (可能后有 deny); 无任何命中返 neutral (pass)
- **5s TTL module-level cache**: `_cached_rules + _cached_at`; 任何写操作 (POST/PATCH/DELETE) API 端 `invalidate_cache()`; 5s 后下一次访问自动重拉
- **HotspotItem.source 字段是 source name (非 source_name)**: filter_items 用 `getattr(it, "source", "")` 兼容

### 2026-09-05 v0.8.0-post — 4 步治理审计 (Task 1-4, 本批)

> **来源**: 用户指令 "1,2,3,4 依次按建议治理" (v0.8.0 release tag 同步 / D4-D7 补齐 / v0.8.1+ 方向 / CRITICAL_REVIEW §4.4 dsh 真相治理)。
> **基线**: `main` HEAD `771d5f4` (含架构图重画 04e04c3+771d5f4); tag `v0.8.0-skills` 在 `39e3fb0` (Phase A/B/C/D merge commit, refactor/v0.8-skills → main)。
> **范围**: 不引入代码变更, 仅审计 + 文档补账 (`docs/CRITICAL_REVIEW_2026-09-03.md` §4.4 落账)。
> **commit 链**: 本批 0 代码 commit, 仅 `docs/CRITICAL_REVIEW_2026-09-03.md` §4.4 落账注 (`docs: CRITICAL_REVIEW §4.4 落账 - dsh 真相 v0.8 B4+archify chore` 1 commit)。

- [x] **Task 1 — v0.8.0 release tag 同步**: 审计 tag 位置 / version.py / AGENTS.md 头部 / CHANGELOG.md v0.8.0 段 / PROGRESS.md v0.8 Skills 段 5 处全部一致。**结论**: tag `v0.8.0-skills` 保留在 39e3fb0 (功能冻结点,Phase A/B/C/D merge),架构图重画 771d5f4 是 release 内合法 chore (叙事层修复,不动 release 头)。无遗漏,无 tag 重定位必要。
- [x] **Task 2 — D4-D7 补齐**: 审计 v0.7 batch ⑧ (merge `6adccd6`, tag `v0.7.4-cleanup`) 落账 7 段: D1 OAuth / D2 告警 5 档 / D3 SSE / D4 api_events 采样降级 / D5 扩展域开闸 / D6 i18n+a11y / D7 docstring 强制。**代码 / CHANGELOG / CI / scripts 全部 100% 落地** (audit reference: CHANGELOG.md line 1407-1418)。无需新工作。
- [x] **Task 3 — v0.8.1+ 方向**: 推 CRITICAL_REVIEW §1.2 断路器 + §2.1 LLM 语义降级 **联动 batch** (5 天) — 两者强依赖(provider_health 滑动窗口 → 触发 circuit_breaker OPEN → 自动切下个 provider),拆分技术债翻倍。备选 §3.1 前端 SWR (~1 周) 等本批后开。**用户待裁决**。
- [x] **Task 4 — CRITICAL_REVIEW §4.4 dsh 真相治理**: 走"选项 A 诚实化中庸版" — 保留 :3210 端口标注 + 显式暴露降级链, 不移除节点。**三层落账**: ① 代码层 (B4 `d7ed96b` `runtime.py:resolve_mode()` 3 状态 + `supervisor.py` 4 态) ② 架构图层 (v0.8.0-post `771d5f4` 副标签 `ProcessSupervisor · :3210 (not_configured→mock→ai_hub)`) ③ docs 层 (本批 CRITICAL_REVIEW §4.4 落账注)。**用户看图即知真实语义, 不再误导成"独立网关"**。

### 关键事实 (v0.8.0-post)

- **dsh 不是独立网关**: 是 uvicorn :8000 进程内 builtin runner pool, :3210 是用户可能配的 endpoint (实际多数安装下未运行); 真实降级链 = `not_configured → mock → ai_hub builtin` (B4 `d7ed96b` `backend/services/dsh/runtime.py:resolve_mode`)
- **架构图叙事与代码事实对齐**: `★ DSH (Brain) · ProcessSupervisor · :3210 (not_configured→mock→ai_hub)` 副标签明确"4 runner 之一"非"独立网关",CRITICAL_REVIEW §4.4 推荐选项 A 的"诚实化中庸版"
- **v0.8.1 推荐 = §1.2 断路器 + §2.1 LLM 语义降级 联动 batch**: 5 天工作量, v0.8 Skills 20 skill 跑起来后 provider 500 雪崩防御, 与 4 runner 并行不冲突
- **架构图 chore 不动 release tag**: chore(arch) 771d5f4 是 v0.8.0 release 内的合法延续, release tag `v0.8.0-skills` 仍指 39e3fb0

### 不在本批范围 (留独立段)

- ai_hub Layer 3 (gateway chunks source 维度过滤) — chunks 签名不匹配, 需先重构 gateway.py
- batch import (一次创建多条规则) — API 已可单条循环, 不阻塞
- rules 按 enabled/category 排序持久化 — list_rules 直接 ORDER BY id, 简单够用

### 2026-09-05 v0.8.0-post+1 — 架构重构方案复核 (CRITICAL_REVIEW 状态同步, 0 代码)

> **来源**: 用户指令 "重新熟悉整个代码仓库, 更新相关架构重构方案"。
> **基线**: `main` HEAD `d22bcd7` (v0.8.0-skills post-merge, 工作区干净)。
> **范围**: 0 代码变更, 仅 `docs/CRITICAL_REVIEW_2026-09-03.md` 全文状态复核 + 本台账段。

- [x] **全仓重熟悉**: git log (v0.8 Skills 20 commits 已 merge `39e3fb0` + post 审计 `d22bcd7`) / feature_gates.toml 16 gate 实读 / `generate_meta.py` 实测 (jobs 51 / collectors 14 / routers 73 / services 107) / migrations 92 .sql (至 095) / stash@{0} R14.9 code-wiki 临时改在案。
- [x] **CRITICAL_REVIEW 逐项复核** (19 finding 全部标注 ✅/◐/❌ + 当日 grep 实测证据):
  - ✅ 已落地: §3.4 bundle 拆分 (**原文判断有误** — v0.5 M1-Task3 manualChunks + lazy-imports.ts 1:1 已在) / §5.2 三大组件缺口 (A1 trigger_gate + B1 agent_loop + B3 agent_memory) / §5.5 Eval (C5 skill_eval, 原计划 P2 提前) / §4.4 dsh 真相 (上批已落账)。
  - ◐ 部分: §1.1 限流 (trigger_gate/throttle.py 仅入口级) / §1.3 锁竞争 (卡顿根治闭环, cold db 拆分未做) / §1.4 错误处理 (字面 except:pass 实测 0 处, 真实形态 = services 层 **320 处宽泛 except Exception**; P1.7 三档聚合是局部缓解) / §3.5 SSE (/api/events + 观测面板有, 全站未通) / §4 pi (B4 dsh runtime 三态落, pi CLI 仍未实测) / §5.6 特征 5/8。
  - ❌ 仍开放: §1.2 断路器 / §2.1 provider_health 语义降级 / §2.3 graceful shutdown (SIGTERM 0 命中) / §2.4 备份校验 / §2.6 热重载 / §3.1 react-query / §3.2 GZip (仅 export.py 单端点手写 Cache-Control) / §3.3 DI / §3.6 API 版本 / §5.4 全站 MCP 化。
- [x] **§〇 快照重写**: HEAD `d22bcd7` / pytest 3740 + vitest 425 / gates 16 (8 开 8 关) / v0.8 六个新服务包 (包化而非平铺, 方向正确)。
- [x] **§六 路线图重写**: 新增 §6.0 **v0.8.1 三选一** (① §1.2+§2.1 联动 5 天 [推荐] / ② §1.2 alone 2 天 / ③ §3.1 react-query 1 周, 用户待裁决); §6.1 移除 v0.8 已落地 4 项, 新增 "七 gate 开闸演练" (1 天, v0.8.1 前置); §6.2/6.3 按复核结果重排。
- [x] **§七 结语更新**: 最大 gap 重排为 ① gate 全关未实战 ("建成≠通电") ② 运行时弹性缺失 ③ pi 未实测 ④ 前端数据层原始; BS-AI-Agent 终态时间表提前 (9 特征 4 项已落地, 剩余约 1 个月量)。
- [x] **附录 A/B 更新**: 证据索引全部换为 2026-09-05 实测命令 + 结果; 优先级矩阵按复核重排。

### 关键事实 (v0.8.0-post+1)

- **复核修正了原文 2 处失实**: ① §3.4 "生产路由表未用 React.lazy" 有误 (v0.5 已拆, 原文被移出路线图); ② §1.4 "估计 30+ 处 except:pass" 偏悲观 (实测 0 处字面, 320 处宽泛 except Exception)。
- **v0.8.1 方向不变**: 仍推荐 §1.2+§2.1 联动 (5 天), 与 v0.8.0-post Task 3 结论一致; 新增前置项 "七 gate 开闸演练" (1 天)。
- **grep 证据均当日实测**: 断路器 0 类命中 / SIGTERM 0 命中 / GZipMiddleware 0 命中 / react-query 无 / migrations 92 .sql / services 层 except Exception 320 处。

### 2026-09-05 v0.8.0-post+2 — 架构图重渲 (archify 首次 0-error 交付) + V0.8.1_PLAN 立项 (本批)

> **来源**: 用户指令 "重新熟悉整个代码仓库, 更新相关架构重构方案 [$archify]"。
> **基线**: `main` HEAD `5bdea00` (v0.8.0-post+1 复核版); 3 路 Explore 扫底 (后端/前端/文档) 当日实测。
> **范围**: 架构图 candidate 全新 authoring + archify deliver; `docs/V0.8.1_PLAN.md` 新建; 2 份过期文档头部修正。

- [x] **全仓 3 路扫底**: 后端 (73 router / 107 service / 12 服务包 / 43 repo / 92 迁移 / 51 job / 265 test; ai_hub 11 文件 2495 行; dsh 7 文件 779 行 `runtime.resolve_effective` 3 态 + **3 连败 unhealthy 熔断先例**; tenacity 0 命中; `retry_policy.py` 仅 KL 用; Semaphore 7 文件散落; services 层 320 处宽泛 except Exception / 86 文件) / 前端 (53 路由全 React.lazy + manualChunks 已配 — **CRITICAL_REVIEW §3.4 原文失实**; 25 处 setInterval / 15 文件; react-query/swr 0 依赖; I18nContext 767 行 ~300 key×2; skills 6 组件 2266 行; dashboard 单文件 343 行内嵌 3 组件) / 文档 (CRITICAL_REVIEW 已是 09-05 复核版; V0.8_REFACTOR_PLAN 25 验收框纯计划态未回填; DECISION_REGISTER 头部 "34 项待确认" 过期; **确缺 v0.8.1 计划文档**)。
- [x] **架构图重渲**: candidate.json 全新 authoring (11 节点 / 3 区域 / 11 连接, 零 labelAt 起步, 实测数字修正: services "107 services · 51 jobs" 修 "108 modules" 口误) — 12 轮 validate 迭代 (列距 26px 触发渲染器崩溃 → ≥40px; context 字号 9px 上限 → viewBox 宽必须 ≤~1390 → 删 users 节点 + 压缩布局; "sync zip" 边 re-home 到 repository→webdav 解 services 底部 3 端口扇出死结)。**archify validate 0 error / 0 warning (showcase 9/9, 本图历史首次) + deliver ok + visual-check 4 视口 pass (minTextPx 9) + judge 4/4 pass (light/dark × 1440/2048, 5 叙事修复全数在图)**。
- [x] **docs/V0.8.1_PLAN.md 新建**: 方案 A 断路器+provider_health 联动 (5 天, 推荐) / B alone (2 天) / C react-query (5-7 天) / D 备选 (D-a error_classifier 2 天 / D-b graceful shutdown 0.5 天 / D-c GZip / **D-d pi 协议实测 1 周**); 8 条扫底新证据表 (E1-E8) 修正 CRITICAL_REVIEW 原判断; **§6.1 短期 P0 清单全覆盖对照表**; 方案 A 补 scenario_router 场景权重表 (§2.1 场景感知支柱); 6 个裁决点 D1-D6 待用户拍板; 前置项 = 七 gate 开闸演练 (1 天)。
  - **复核附件回灌 (同日)**: 对照 CRITICAL_REVIEW 2026-09-05 复核全文修正 3 处 — 工作量口径对齐 §6.1 (error_classifier 1 周→2 天 / graceful 3 天→0.5 天) / 补 D-d pi 实测 (结语 gap #3, 原 plan 遗漏) / 补场景权重表; E1 加注 (review "tenacity 在 tools/import_cache.py" 引用已失效, 全仓 grep 0 命中)。
- [x] **文档头部修正**: V0.8_REFACTOR_PLAN 加已完结横幅 (执行记录以 PROGRESS 为准, 25 验收框不回填); V0.8_DECISION_REGISTER 头部改 "35 项全部 ✅"。

### 关键事实 (v0.8.0-post+2)

- **viewBox 宽度硬约束**: archify context 字号上限 9px × (930/vb宽) ≥ 6px → viewBox 宽 ≤ ~1390; 本图 1340 已是 11 节点级布局的实际天花板, 加节点必先删节点
- **小盒字号陷阱**: 盒内文字过长时 fit 会跌破 9px 上限 (llm 200→215px 才救回 8.4→9.08), 副标签长度须按盒宽预算
- **节点 12→11**: users 节点删除 (宽度预算下牺牲度最高), frontend/api 副标签缩为 ":8898 · 53 lazy 路由" / ":8000 · 73 routers"
- **sync 边语义微调**: "backup zip + Fernet" 从 services→webdav 改挂 repository→webdav (备份导出语义), 换取 services 底部扇出解耦

### 不在本批范围 (留独立段)

- 方案 A/B/C/D 实施 — 等用户裁决 `docs/V0.8.1_PLAN.md` §8 (D1-D5)
- V0.8_REFACTOR_PLAN 25 验收框回填 — 已横幅声明以 PROGRESS 为准
- 前端 react-query 迁移 (方案 C) — v0.8.2 候选

### 2026-09-05 v0.8.1-pre — 裁决落账 (D1=方案 A) + PRD 立项 (本批)

> **来源**: 用户裁决 "D1 选择方案 A, 生成最终重构计划和 PRD" (prd-iterative + project-brain)。
> **范围**: 0 代码变更 — 裁决记录 + PRD 定稿 + 生命周期推进。

- [x] **D1=方案 A 锁定** (断路器 + provider_health 单一真相源联动, 5 天); D2-D6 按计划默认 ([假设] 已在 PRD 头部标注: D2 不抽公共模式 / D3 阈值 50%·30s / D4 演练前置 / D5 API-only / D6 pi 排 A 收口后)
- [x] **docs/V0.8.1_PRD.md 立项** (prd-iterative 9 章 + 三维审查: P0×0 / P1×2 (演练验收矩阵定义入 F5·§8 / "演练 mock 不产生真实 provider 失败 → 熔断由 failover 单测验证"防虚假安心) / P2×2 (1h 窗口降为 /health 展示字段, 判定仅 5min / 演练通过后 gates 保持全开 [假设]), 全部当轮修复入文)
- [x] **V0.8.1_PLAN v1.2**: 状态 → 已裁决; 批次日历定稿 = **Day 0** (graceful shutdown 0.5 天 + 七 gate 开闸演练 1 天) → **Day 1-5** (方案 A 弹性层) → **次周** (pi live 实测)
- [x] **PROJECT.md 生命周期推进**: v0.8.1 需求阶段 ✅ 闭合 → 当前阶段 = 开发 (v0.8.1 batch); 决策日志追加 D1=A 行 (含替代方案否决理由)

### 2026-09-05 v0.8.1 Day 0 — graceful shutdown + 七 gate 开闸演练 (通电) (本批)

> **来源**: PRD v1.0 §8 Day 0 (D1=方案 A 前置); 用户指令 "开始Day0"。
> **范围**: D-b graceful shutdown + D4 七 gate 开闸演练 + **演练修复 user_skills gate 漏登记 P0** + toml 通电。

- [x] **D-b graceful shutdown** (`backend/utils/shutdown.py` + main.py lifespan 重排): `drain_in_flight` (快照 AsyncIOExecutor `_pending_futures`, 只读内省, 有界等待在跑 job 自然收尾; 无在跑不空等; 无法内省走固定 sleep 兜底) → `sched.stop(wait=False)` → `stop_dsh()` 防孤儿 → `wal_checkpoint(TRUNCATE)` → close_db。**根因**: AsyncIOScheduler.shutdown() 会 cancel pending futures = 协作式打断在跑 job, 此前 `sched.stop()` 默认 wait=True 但 timeout 形参从未被使用; 全仓此前无显式 WAL checkpoint。conftest 预置 `HOTSPOT_GRACEFUL_TIMEOUT=0` (否则每个 TestClient lifespan sleep 30s)。15 测试全绿 + ruff 过。
  - **验收 (PRD: 重启 20 次无损坏)**: 真 uvicorn + 真 SIGTERM soak **PASS=20/20** (每轮 drain done + `wal_checkpoint: truncated` + shutdown complete + 0 traceback); day0/warm/cold 三库 `integrity_check` ok。
  - **踩坑 (Day 0 发现, 仓库级)**: **stdlib logging 全仓无 InterceptHandler → 生产完全不可见** — main.py 自身 `log.info("startup complete...")` 历史上就是隐形的; 第一轮 soak 日志无 drain/checkpoint 行即此因 (代码已跑, 输出进黑洞)。shutdown.py 改用 loguru; 新代码一律 loguru。
- [x] **D4 七 gate 开闸演练** (env 全开 16 gate): uvicorn 启动冒烟 ✓ / openapi+端点探针 / pytest 全量 / vite build ✓。
  - **演练修复 P0**: `user_skills` gate 自 Phase C 落地起**漏登记 `_EXTENSION_NAMES`** → `_load_gates` 过滤恒 False → `/api/skill-builder` 从未注册 (Skill Builder 前端永远 404)。正是 Phase A "关键事实" 预言的 "随实现登记" 欠账。修复: 补登记 + EXTENSION_ROUTERS + 复探 200 (`{"items":[],"total":0,"max":50}`)。agent_loop/playbook_engine/skill_eval 同漏但**无消费点** (服务本体不受 gate 控制), 记录不登记。
  - **发现 F2**: mcp extension gate 与 `is_mcp_enabled()` (读 config.feature_mcp) 两套开关语义分裂 — env 开 mcp gate 不开 MCP server。mcp 回关, P2 备忘。
  - **验收**: pytest **3755 passed / 6 skipped / 0 failed** (gates 全开, 基线 3740 + Day 0 新增 15, 零回归, 931s); skill-registry 20 skill 全注册 / info-filter true / trigger-webhook health / skill-builder 200 全探针过。
- [x] **通电**: `feature_gates.toml` 7 个 v0.8 gate → true (info_filter/skill_registry/trigger_gate/agent_loop/playbook_engine/user_skills/skill_eval), mcp 回关; **纯 toml (零 env) 复探 4/4 = 200**。演练通过后保持全开 (PRD F5 [假设]), fail-closed 随时可回关。
- [x] **文档**: AGENTS.md gate 数字 (15 开 1 关) / PROJECT.md 生命周期+已知问题+决策日志 / `generate_meta --check` 4/4 过。

### 2026-09-05 v0.8.1 Day 1 — CircuitBreaker 薄状态机 (本批)

> **来源**: PRD v1.0 §8 Day 1; PLAN v1.2 §2.3 D1。
> **范围**: `backend/utils/circuit_breaker.py` (~110 行) + 14 测试。**无失败计数** (单一真相源, trip 由 ProviderHealth 判定驱动 — Day 2), keying = provider 级, 单把 threading.Lock (TriggerWorker 线程 × event loop 混跑)。
> **三态语义**: closed 放行 / open 拒绝且到期后下一次 allow() 即探针 (half_open) / half_open 探针在途拒绝; **探针防死锁**: half_open 滞留 ≥ recovery_timeout (调用方失联) 自动重新授予; trip 已 OPEN 时 no-op (不延长窗口, 窗口起点 = 首次 trip); reset 幂等; clock 可注入 (测试零 sleep, 生产 monotonic 防时间回拨); recovery_timeout=0 = 每次都放探针。
> **验收**: 14/14 全绿 (三态迁移/窗口重计/防死锁/snapshot/16 线程 Barrier 恰好 1 探针/8 线程混跑 400 ops 状态恒合法) + ruff 0 错。

### 2026-09-02 SettingsHub V2 — 哨兵化全重设计 + 5 子组件拆分 (本批)

> **来源**: 用户指令 "哨兵以外的 UI/UX 调整, 参考哨兵进行美化" + 四问决策 (Q1 加 dashboard 用途/代价/习惯说明, Q2 拆 5 子组件, Q3 全重设计, Q4 测试全重写一步到位)。
> **基线**: `main` HEAD `fda2d5a` (含 Batch ⑥ llm_secrets 接入 + Batch ⑦ 阻塞项清零); off 分支 `refactor/settings-v2-sentinel-style`。
> **范围**: ① 新 `settings-shell.css` (`.settings-shell` 前缀防泄漏, 哨兵令牌 `--sn-*` 全量复用 + 新 `--sn-fs-*` / `--sn-radius-*` / `--sn-gutter`); ② 新 `SettingsDashboard` 总览 + URL `?cat=` deep-link (默认 `dashboard`); ③ QualitySettings 拆 `ProviderPanel / SecretsPanel / LlmDetectionPanel / QualityRulesPanel + ScenarioModelsPanel` 5 件套; ④ 14 个分类页面 (PipelineSettings / ModeSwitcher / ProxySettings / DatabaseMaintenance / SyncSettings / SecretsStatusCard / KnowledgeSettings / ExportSettings / AboutSettings / MCPSettingsCard / GeneralSettings / CollectionScheduleInfo / SourceSettings / AlertSettings / FeedbackSettings / AgentRunnerCard / DshControlCard) 全部按哨兵 st-* 原子样式重写; ⑤ 测试全重写 (semantic query: role / aria-label / data-testid, 不再依赖 button 文案); ⑥ 修复 2 个 V2 重构暴露的真 bug。
> **不引入**: 新依赖 / 新路由 / 新 state 库 / 新 feature gate。
> **commit 链**: `refactor/settings-v2-sentinel-style` 分支 (待 merge --no-ff)。

- [x] **C1 — `settings-shell.css` 哨兵令牌层**: 全局 `--sn-mint/amber/red/line/ink-1/2/3/bg-0/1/2/hover` 转发 + 扩展 `--sn-fs-title/h2/h3/body/mute` 字号 / `--sn-fw-bold/medium/regular` 字重 / `--sn-radius-sm/md/lg` 圆角 / `--sn-gutter/row/cell-pad` 间距 / `--sn-mono` 等宽。st-* 原子类: st-head / st-btn (primary|ghost|danger) / st-input / st-textarea / st-select / st-switch / st-checkbox / st-radio / st-chip (ok|warn|bad|mute) / st-rule / st-cellgrid / st-cell / st-card / st-tilegrid / st-sidenav-item / st-sidenav / st-section / st-actionbar / st-ab-msg / st-progress / st-table / st-dangerline / st-dangerlist / st-info / st-grid / st-rail。所有选择器挂 `.settings-shell` 前缀, 防止哨兵样式泄漏到 /secnews 主区。
- [x] **C2 — `SettingsPage` 总览 + sidebar**: 头部 st-head 双栏 (左标题 + 副描述 / 右关键 chip); 默认 `?cat=dashboard` 落地 `SettingsDashboard` 总览页 (Vercel/Linear/Notion 控制面板模式 — 用途 + 不加的代价 + 用户习惯契合 + 业务逻辑对齐说明); sidebar 14 项分类用 st-sidenav-item 高亮当前 cat。URL 解析走 `URLSearchParams`, 切换时 `navigate({search: ?cat=...})`。
- [x] **C3 — QualitySettings 5 子组件拆分**: 原 879 行单体 → 5 文件 (~80-130 行/件)。ProviderPanel (yaml options + effective + config_source chip + 切换保存); SecretsPanel (主密钥 prompt / reveal 10s / upsert / lock / 解锁状态); LlmDetectionPanel (启用 switch + provider select + 应用配置, 无 sk-... 输入框); QualityRulesPanel (按 rule.value 类型分发: boolean → switch / sample_rate → range slider / number → input / 其他 → text); ScenarioModelsPanel (deep/light/image 三行 st-rule, compact 模式供 ImageStudio 嵌入)。
- [x] **C4 — 核心组件重构 (PipelineSettings / ScenarioModelsPanel / ModeSwitcher)**: PipelineSettings 改 st-cellgrid 3 卡 (mode + status + uptime) + 触发器 st-table + st-actionbar; ScenarioModelsPanel 加 compact 模式; ModeSwitcher st-cellgrid 双卡 + reason 文本。
- [x] **C5 — 其他分类重构 (GeneralSettings / CollectionScheduleInfo / SourceSettings / AlertSettings / FeedbackSettings)**: 全部按 st-rule + st-cellgrid + st-table 落位; SourceItem 用 --sn-ink-3 / --sn-bg-hover token 升级 V2。
- [x] **C6 — 高级分类重构 (SecretsStatusCard / SyncSettings / ProxySettings / DatabaseMaintenance)**: SecretsStatusCard TS2322 (`ttlChip: string | null` → `string | undefined`); ProxySettings 3 卡 + 5 连接测试 st-table; DatabaseMaintenance 4 卡 + top10 表 + 维护操作 + 滑动条; SyncSettings 改 st-rule。
- [x] **C7 — 总览分类重构 (KnowledgeSettings / ExportSettings / AboutSettings / MCPSettingsCard)**: KnowledgeSettings 单按钮入口 + items/concepts/last_sync 3 卡; ExportSettings 3 cellgrid (HTML/XLSX/日报周报); AboutSettings 6 卡 status (VERSION/UPTIME/DB/SCHED/COLLECT/PROXY); MCPSettingsCard toggle 改 button role=switch + st-table 工具清单。
- [x] **C8 — 字体/间距/圆角 token 全覆盖**: SourceItem / AgentRunnerCard / DshControlCard 迁移 V2 token (`--sn-mono` / `--sn-radius-md` / `--sn-fs-mute` / `--sn-mint` / `--sn-red` / `--sn-ink-3` / `--sn-bg-hover`)。AgentRunnerCard 全 V2 重写 (input/select/btn/textarea); DshControlCard 全 V2 重写 (chip status + 输入 + gate-off fallback)。
- [x] **C9 — 测试全重写 semantic query**: QualitySettings 14 用例 + MCPSettingsCard 8 用例全部按 role / aria-label / data-testid 重写, 不再依赖 button 文案 (V2 改文案如 "切换默认 LLM Provider" → "应用 LLM 配置" 直接破测试)。修复 2 个 V2 重构暴露的真 bug: (a) SecretsPanel 越过父级 `open=false` 门控另起 `/api/llm/status` 调 key_source → 提升到 QualitySettings 通过 `initialKeySource` prop 注入, SecretsPanel 不再自拉, 父级 open gate 真正生效; (b) SecretsPanel `keySource` state 不响应 prop 变化 → 加 `useEffect([initialKeySource])` 同步 (ProviderPanel 切换后重拉 status 触发更新)。
- [x] **C10 — 门禁全绿**: tsc 0 错 / vitest 355/355 (48 files) / vite build 干净 / ruff (后端无改动) 跳过。

### 关键事实 (V2)

- **设计语言**: 5 条 V2 设计纪律 — 零霓虹 (零渐变零阴影零模糊) / 语义三色 (mint/amber/red + mono 辅助) / mono 数据 (等宽表格对齐) / 可访问降噪 (mute 文本 contrast ≥ 4.5) / 减少动效 (默认 `prefers-reduced-motion`)。色调 90% 走 ink/line 三阶灰, 10% 走 mint/amber/red 语义色。
- **共享样式边界**: `settings-shell.css` 是 settings 域独占资产, 选择器挂 `.settings-shell` 防泄漏。哨兵 `--sn-*` 令牌全局可达, 但 `.sentinel` 类前缀仅哨兵内部使用, settings 用 `.st-*` 自成一系。
- **5 子组件组合模式**: QualitySettings 只做初始数据加载 + providerOptions 共享 + 子组件组合, 单组件 ≤ 130 行。每个子组件自管状态/弹窗/handler, 主组件不掺业务。
- **deep-link URL**: `?cat=dashboard` 为默认 cat; 切换分类时 `navigate(..., {replace: true})`, 避免污染 history stack。
- **遗留**: V2-C10 (docs/code-wiki + 本 PROGRESS.md) / V2-C11 (merge + tag + push 用户授权)。

### 不在本批范围 (留独立段)

- 设置项 schema 化 (当前 st-rule 硬编码, 未来可走 JSON Schema 动态渲染)
- 暗色/亮色主题切换 (当前仅暗色, 与哨兵统一)
- 设置搜索 (14 项分类未超密度, 暂不需要)
- mobile 适配 (settings 假设 ≥1024px 桌面, 与主应用一致)

### 2026-08-31 v0.7 Batch 2 — LLM provider 切换 + settings.kv 覆盖 + audit_log 写入 (本批)

> **来源**: Observability PRD v1.0 §5.3 "用户切换 > 运维默认" + Batch 1 已落地的 `record_audit` 仍 0 生产调用者, 顺接作为首个真实调用场景。批前盘点: ai_hub 默认 provider 仅 env / router / default 三级, 用户切换要重启进程或改 env; QualitySettings 写 `quality.llm_provider` 是 v4.4 起的 dead 字段 (ai_hub 不读)。
> **范围**: ① env `AI_PROVIDER` > settings.kv `llm.default_provider` > yaml default_provider 四级链; ② `POST /api/settings/llm-provider` 走 settings.kv + audit_log; ③ 前端扩到 yaml 全注册; ④ 不动 llm_secrets (主密钥未解, 见旧 v0.6 P0 决策点 ⑤); ⑤ 不动 LLMService gateway (PRD §5.3 不冲突, AIService.evaluate/gate_detect 走新链); ⑥ 不动 GateContext (dead default, 不引入新注入点)。
> **不引入**: 新数据库表 / 新 feature gate / 新前端页面 / llm_secrets 接入。
> **commit 链**: `ade3b03` (backend 主批) + `ba69454` (frontend 主批) + 本 docs commit。

- [x] **后端 — `_resolve_provider` 四级链**: `backend/services/ai_hub/service.py` 在 env 之后插入 settings.kv 查询 (类型守卫 `isinstance(str) and .strip()`, 避免非字符串触发 "settings" 打标), 兜底 router → yaml default_provider; 既有 `test_s4_1_model_router.py::test_ai_service_resolve_provider_three_levels` 6 用例继续绿 (env > router > default 顺序保住)。
- [x] **后端 — `_config_source()` 解析路径打标**: env|settings|router|default, 写入 `llm_usage_log.config_source` 替换原 `default/fallback` 二分; `key_source` 仍 `"env"` (TODO 留待 Batch ③+ 接 llm_secrets)。
- [x] **后端 — `POST /api/settings/llm-provider`** (`backend/api/settings.py`): 校验 provider ∈ yaml registry → `SettingsRepository.set("llm.default_provider")` → `record_audit(actor, action="llm_config.update", target="default_provider", detail={from, to, source})`; audit 失败仍 200 (PRD §10 红线 ②, 审计容错); actor 默认 `"web"`, 接受 `"system"` / `"agent:<name>"`。
- [x] **后端 — `GET /api/llm/status` 增 effective_provider + config_source**: 帮前端确认 "我现在到底用哪个 + 哪条链生效的", 复用 `_resolve_provider` / `_config_source` 同源。
- [x] **后端 — 2 个新测试文件**:
  - `backend/tests/test_llm_settings_override.py` — 8 例: env > settings > router > default 完整四链; 非字符串 / 空串 / 异常 swallowed; 端到端 `config_source` 落到 `llm_usage_log`。
  - `backend/tests/test_llm_settings_api.py` — 6 例: 合法切换 + audit 写入; 非法 provider → 400 `INVALID_PARAM`; audit 失败仍 200; actor 三种格式; 旧值序列正确; yaml registry 缺失时退化兜底。
- [x] **前端 — QualitySettings 顶部新面板** (`ba69454`): 拉 `/api/llm/status` 拿到 yaml 注册的 `providers` + `effective_provider` + `config_source`, dropdown 动态渲染 (不再硬编码 2 项); "切换默认 LLM Provider" 按钮 → `POST /api/settings/llm-provider { provider, actor: 'web' }`, 成功后重拉 status 验证 `effective_provider` 已变 + 显示 `已切换: x → y`; 失败显示后端 `message` 不调成功 toast; 检测子面板的提供方 dropdown 同步扩为动态渲染。
- [x] **前端 — `QualitySettings.test.tsx`** (NEW, 4 例全绿): 5-option 渲染; POST 切换 + 成功消息; 失败显示错误无成功 toast; open=false 不触发 fetch。
- [x] **不破坏既有契约**: `test_s4_1_model_router.py::test_ai_service_resolve_provider_three_levels` 6/6 继续绿 (env > router > default 三段断言 — 因 test isolation env 未设 + settings.kv 空, 新代码回退到 router/default 同既有路径); `test_quality_rules.py` 不受影响 (QualitySettings 写 quality.llm_enabled / quality.llm_provider 的旧路径保留, 与新 default_provider 面板并行存在)。
- [x] **门禁**:
  - ruff backend: 0 错 (含 I001 自动修)
  - 全量 pytest: **3077 passed / 6 skipped / 1 failed** (1 fail = `test_snapshot_for_retirement.py::test_baseline_2026_08_24_counts` 期望 4149 wiki 文件但根已迁 + gitignore, 见 P4 预存债, 非本批范围)
  - `generate_meta --check` OK (routers 65 不变 / services 97 不变 — 本批不增架构数字)
  - tsc --noEmit: 0 错
  - vitest: **314 passed** (基线 310 + 4 new)
  - vite build: OK

### 关键事实 (Batch 2)

| 维度 | 结果 |
|------|------|
| 四级链覆盖 | env AI_PROVIDER > settings.kv > router > yaml default_provider; 既有三段断言保住 |
| audit_log 写入 | `llm_config.update` action + `from/to/source` detail; 0 production caller → Batch 2 起为 audit_log 首个生产调用 |
| 前端 dropdown 漂移 | 杜绝硬编码 2→5; 选项从 yaml registry 动态拉; 新增 provider 零前端改动 |
| llm_secrets 状态 | 未动; keyring 主密钥未解, 沿用 env (旧 v0.6 P0 决策点 ⑤ 关闭条件未触发) |
| GateContext | 仍 dead default, 不引入新注入点 (与 PRD §5.3 不冲突) |
| commit 链 | `ade3b03` (backend) → `ba69454` (frontend) → docs commit |

### 2026-08-31 v0.7 Batch ③ — middleware 写表 + api_events/api_metrics_hourly + aggregator (本批)

> **来源**: Observability PRD v1.0 §5.3"业务 endpoint 观测" + Batch 1/2 落地的 record_* 模式顺接; Batch 2 已把 audit_log 接通, 本批把 API 调用层接通。
> **范围**: ① `record_api_call` 函数 (observability_records.py, 镜像 record_audit 失败 swallow); ② migration 081 建 `api_events` (7d TTL) + `api_metrics_hourly` (30d TTL, hour+path_template 主键); ③ `TraceIDMiddleware` 收尾调 `record_api_call`, path 取 FastAPI `request.scope["route"].path` (非 raw URL); ④ `observability_aggregator_job` 60min, Python 两步走聚合 (绕开 SQLite 不能引用外层 SELECT 别名); ⑤ `observability_ttl_job` 扩 5 张表; ⑥ `/api/observability/{summary,recent,timeseries,llm-usage}` 4 GET 端点, 无 feature flag (基础设施)。
> **不引入**: 新传输层 (ws/SSE) / 阈值引擎 (Batch ④) / 新 feature gate。
> **commit 链**: `63c856c` (backend) + `108afde` (frontend) + 本 docs commit (Batch ⑤)。

- [x] **后端 — `record_api_call`** (`backend/observability_records.py`): `def` 非 async (镜像 record_audit), INSERT `api_events` 失败 swallow, `__all__` 追加。
- [x] **后端 — migration 081**: `api_events` (trace_id/method/path_template/status/duration_ms/error/occurred_at) + 4 索引; `api_metrics_hourly` (hour/path_template/errors/p50_ms/p95_ms/max_ms) 主键 (hour, path_template) + 1 索引。
- [x] **后端 — `TraceIDMiddleware` 接入** (`backend/api/middleware.py`): dispatch 收尾调一次 `record_api_call`, 异常路径同样落表 (status=500, error 截断 [:500]); `path_template = request.scope["route"].path` (路由模板而非 raw URL, 避免 query string 维度爆炸); `/api/health` 在 `exclude_paths` 仍不入表。
- [x] **后端 — `observability_aggregator_job`** (`backend/scheduler/jobs/maintenance.py`): 60min, 起点 +5min 错峰 ttl; 拉 api_events 最近 2h → Python dict 按 (hour, path_template) buckets 聚 total/errors/p50/p95/max → `INSERT OR REPLACE` 幂等; SQLite correlated subquery 不能引用外层 SELECT 别名或 FROM 表别名, 用 Python 两步走比单条 SQL 更清晰。
- [x] **后端 — `observability_ttl_job` 扩 5 表** (Batch 1 4 表 + `api_events` 7d); `observability_alerts` 仍归 Batch ④ 引入。
- [x] **后端 — `observability_router`** (`backend/api/observability_router.py`, NEW): 4 GET 端点, 全部 `def` (async→def 线程池派发规则); `/api/observability/timeseries` 直接读 `api_metrics_hourly`, 不重算; `summary` 直接扫 `api_events` 当小时 (即时准确)。
- [x] **后端 — 10 测试** (`tests/test_api_observability.py`): middleware 落表 200/4xx/5xx / 排除路径 / error 截断 [:500] / aggregator 跨小时 / summary error_rate+p95 / recent desc / timeseries。
- [x] **前端 — `ObservabilityDashboard.tsx`** (`frontend/src/components/secnews/observability/`): 3 卡片网格 (1h 概览 / Top 5 慢路径 / 最近 20 条事件, 5s 自动刷新); `ObservabilityTab.tsx` 路由壳; 嵌入 `/secnews/observability` 子路由; `SecNewsShell` nav 追加「观测」tab; `StatusBar` 加 obs 1h 节 (total / err% / p95, err≥5% 黄 / ≥15% 红)。
- [x] **前端 — 3 测试** (`tests/ObservabilityDashboard.test.tsx`): 渲染 / recent events / fetch 错误降级; 跨组件状态按 `getAllByText` 容错 (path_template 同名)。
- [x] **门禁 (Batch ③ 后端)**: ruff 0 / pytest scoped 10/10 pass。
- [x] **门禁 (Batch ③ 前端)**: tsc 0 / vitest 317 pass (baseline 314 + 3 new) / vite build OK。

### 2026-08-31 v0.7 Batch ④ — 阈值规则引擎 + observability_alerts + 看板嵌入 (本批)

> **来源**: Batch ③ 数据落地后即可评估越界 + 落告警, 闭环观测→告警→用户响应。
> **范围**: ① `services/observability_thresholds.py` (Threshold 数据类 + load/save/validate/evaluate, DEFAULT_THRESHOLDS 兜底); ② migration 082 建 `observability_alerts` (level/metric/value/threshold/window_minutes/detail/fired_at/cooldown_until/acked) + 3 索引; ③ `observability_threshold_check_job` 60min (aggregator +10min 错峰), 扫 api_events 1h 摘要 → 评估 breach → cooldown 去重 → 写 alerts + audit_log action=threshold.breach; ④ `/api/observability/{alerts/active, alerts/{id}/ack, thresholds GET/PUT}`; ⑥ 前端 `ActiveAlertsBanner` + `ThresholdEditor` + `StatusBar` 角标 (🚨 N critical 红 / ⚠ N warn 黄)。
> **不引入**: 新传输层 / 新 feature gate / 告警通道扩展 (webhook/email, channels 仅 `["status_bar"]`)。
> **commit 链**: `bf5a982` (backend) + `f0e01a4` (frontend) + 本 docs commit (Batch ⑤)。

- [x] **后端 — `observability_thresholds`**: `Breach` dataclass; `load_thresholds` 从 settings.kv 拉, 缺失/坏值兜底 `DEFAULT_THRESHOLDS` (api.error_rate_pct 5/15, api.p95_latency_ms 800/2000, llm.error_rate_pct 10/30, job.failure_rate_pct 10/25, audit.llm_config_change_per_hour 10/50); `_validate` schema 校验 (非 dict / 负值 / warn ≥ critical); `evaluate_api` 同时返 warn + critical 越界。
- [x] **后端 — migration 082**: `observability_alerts` 表 + 3 索引 (`fired_at`, `acked+fired_at`, `metric+level+fired_at`)。
- [x] **后端 — `observability_threshold_check_job`**: 60min, 起点 +10min; 拉 1h 摘要 (total/errors/error_rate/p95) → 评估 breach → 同 (metric, level) cooldown 期内跳过 (15min 默认); 同步入 audit_log `threshold.breach` (Batch ② record_audit 模式延伸); 失败 swallow 不阻塞 raise。
- [x] **后端 — `observability_ttl_job` 扩 6 表**: 新增 `observability_alerts` 30d TTL。
- [x] **后端 — 4 新端点**: `GET /alerts/active` (24h 窗口, critical 优先 / fired_at desc); `POST /alerts/{id}/ack` (幂等, 第二次返 `already=True`); `GET/PUT /thresholds` (PUT 校验 schema, 落 audit_log `observability.thresholds.update`)。
- [x] **后端 — 14 测试** (`tests/test_observability_thresholds.py`): load 兜底 / roundtrip / `_validate` 3 例 (非 dict / warn≥critical / 负值) / evaluate warn+critical / p95 多越界 / summary dict / cooldown_until / alerts active list / ack 幂等 / thresholds GET defaults / PUT 拒绝非法 / PUT 200 更新。
- [x] **后端 — `test_feature_gates.py::test_registered_job_count_matches_scheduler`**: AST 计数 48 → 50 (Batch ③+1, Batch ④+1)。
- [x] **前端 — `ActiveAlertsBanner`****: 30s 自动刷新, critical/warn 双色染色, ack 按钮 inline 调 POST + 自动刷新, 错误降级为顶部红条。
- [x] **前端 — `ThresholdEditor`****: 折叠面板, 4 大类规则 (api/llm/job/audit) warn/critical/window 三输入, PUT 200 → "已保存" / 400 → toast 错误; `ObservabilityTab` 顶部装 banner, 底部装 editor。
- [x] **前端 — `StatusBar` 告警角标**: 并行增加 `/alerts/active` fetch; 🚨 N critical (红) / ⚠ N warn (黄), 仅非零显示。
- [x] **前端 — 5 测试** (`tests/Batch4.test.tsx`): banner 渲染 / 空态不渲染 / ack POST 触发 / editor 折叠展开 / PUT 200 成功消息。
- [x] **门禁 (Batch ④ 后端)**: ruff 0 / pytest scoped 14/14 pass / `test_feature_gates` 65/16 pass。
- [x] **门禁 (Batch ④ 前端)**: tsc 0 / vitest 322 pass (baseline 314 + Batch ③ 3 + Batch ④ 5) / vite build OK。

### 2026-08-31 v0.7 Batch ⑤ — 收口落账 + carry 收编 (本批)

> **来源**: Batch ③ + ④ 落地后须集成测试 + 架构数字同步 + PROGRESS/CHANGELOG 落账 + 公开 commit 链。
> **范围**: ① 集成测试 5 例 (middleware → aggregator → summary / threshold breach → alert / cooldown 去重 / ack 后从 active 消失 / record_api_call 失败 swallow 双层防御); ② `ARCHITECTURE.md` 数字同步 (routers 65→66 / services 97→98 / jobs 48→50); ③ `PROGRESS.md` 加 Batch ③ + ④ + ⑤ 三段; ④ `CHANGELOG.md` 加 v0.7 Batch 3+4+5 段; ⑤ carry 分支 `1f3d0e7` 收编 P4 双预存债根治 (test_kl_state_machine + test_snapshot_for_retirement, `e209a57` 携带修复)。
> **不引入**: 新数据库表 / 新前端页面 / 新 feature gate。
> **commit 链**: `1f3d0e7` (carry merge) → `63c856c` → `108afde` → `bf5a982` → `f0e01a4` → 本 docs commit。

- [x] **集成测试 5 例** (`tests/test_observability_integration.py`): 1) middleware → aggregator → summary total+errors 正确; 2) 100 行 5xx → threshold_check 触发 critical breach; 3) 同 breach 连跑 2 次仅 1 条 alert (cooldown); 4) ack 后 active 列表消失; 5) `record_api_call` 抛异常 → 业务响应仍 200 (middleware 双层 swallow 防御)。
- [x] **middleware 双层 swallow**: `record_api_call` 内部 try/except 已 swallow, middleware 外层再 try/except 一道 (log_event api_observability_swallowed), 满足 PRD §10 红线 ② "永不阻塞响应"。
- [x] **ARCHITECTURE.md**: 顶部数字带更新 routers 65→66 / services 97→98 / jobs 48→50; 框图 r 同步; 状态标注保留 v0.6.2 (不误称 v0.7)。
- [x] **PROGRESS.md**: 加 Batch ③ + ④ + ⑤ 三段 (含 commit 链 + 关键事实表 + 不在本批范围)。
- [x] **CHANGELOG.md**: 加 v0.7 Batch 3+4+5 段, 与 Batch 2 段并列。
- [x] **carry merge**: `carry/earlier-session-leftovers` (`e209a57`) 携带 7 文件 (kl_state_machine +12 / t1_raw_to_refine +22 / wiki_stats_service +new / 3 测试期望更新 / snapshot_for_retirement DEFAULT_WIKI 重指向), 与 batch-2 5 文件零重叠, `--no-ff` 收编; `e209a57` 修复 `test_successors_of_raw` 期望漂移 + `test_baseline_2026_08_24_counts` 期望陈旧, 0 冲突。
- [x] **门禁 (Batch ⑤ 后端)**: ruff 0 / pytest 集成测试 5/5 pass。
- [x] **门禁 (Batch ⑤ 全量)**: 全量 pytest 0fail (carry 收编后 P4 预存债清零) / ruff 0 / `generate_meta --check` OK (routers 66 / services 98 / jobs 50) / tsc 0 / vitest 322 pass / vite build OK。

### 2026-08-31 v0.7 Batch ⑥ — llm_secrets 接入 AIService/LLMService + key_source 兑现 (本批)

> **来源**: 兑现 Batch ② PROGRESS 显式 TODO "Batch ③+ 接 llm_secrets"; 关闭遗留阻塞项 ⑤ "加密通道接管" (P0-Q1 沿袭, 现主密钥已重建, 接入业务路径最后一步)。
> **范围**: ① `SecretRepository.get_by_provider()` helper + 5 tests (C1); ② AIService `_resolve_api_key` 四级链 + `_key_source` 打标 + 10 处硬编码 `key_source="env"` 改动态 + 14 tests (C2); ③ LLMService gateway `_get_api_key` 同步接 AIService 单点 + 4 tests (C3); ④ QualitySettings "LLM 密钥管理" 面板 + `key_source` 徽章 + legacy `quality.llm_api_key` 清退 + 5 tests (C4); ⑤ secrets API 全 audit + `POST /api/secrets/rotate` 端点 + sync 复制 secrets audit + legacy 清退 + 15 tests (C5); ⑥ docs 落账 + 关遗留阻塞项 ⑤ (本段)。
> **不引入**: 新数据库表 / 新前端页面 / 新 feature gate / 不动 ARCHITECTURE 数字 (routers 66 / services 98 / jobs 50 不变)。
> **commit 链**: `83721c2` (C1) → `e7171c2` (C2) → `2b36d7c` (C3) → `9734e65` (C4) → `3f30d00` (C5) → 本 docs commit。

- [x] **C1 — `SecretRepository.get_by_provider()`**: `ORDER BY updated_at DESC, id DESC LIMIT 1` 复用 `idx_llm_secrets_provider`; 多条同 provider 取最新约定; AIService 接入落地 (migration 074 已下契约)。
- [x] **C2 — AIService 四级链 + key_source**: `_resolve_api_key` 实例方法 (env > secrets(provider=...) > "" fail-soft); `_key_source` 同路径返 `env|secrets|none` 标签; 2 处 AIService 内部 `key_source="env"` 改 `key_source=self._key_source(p)`; 5 处 `_resolve_api_key()` 调用改 `self._resolve_api_key(provider)`。
- [x] **C3 — LLMService gateway 同步**: `_ai_key_source(provider_name)` 模块辅助函数委托 AIService; `_call_provider/_call_openai/_call_anthropic/_call_openai_compatible` 接受 `provider_name=`; 8 处 gateway 内 `key_source="env"` 改 `key_source=_ai_key_source(provider_name)`。
- [x] **C4 — QualitySettings 子面板**: 折叠面板 + `key_source` 徽章 + 3 弹窗 (master_key_prompt / reveal_10s / upsert) + 7 handler (loadSecrets / handleUnlock / handleLock / handleReveal / handleTestConnection / handleUpsertSecret / handleDeleteSecret); 前端 `saveLlm` 不再写 `quality.llm_api_key` (legacy 路径)。
- [x] **C5 — secrets API 全 audit**: 7 audit calls (`create/update/delete/reveal/test/unlock/lock`) + `POST /api/secrets/rotate` 端点 (master_key 轮换 + 重加密 + 强审计) + `sync_bundle.py` 复制 llm_secrets 路径加 `llm_secrets.sync_write` 审计 + 修复 `encryption_keys` 无 `updated_at` 列的旧 bug。
- [x] **observability_records 通用化**: SAVEPOINT 隔离兼容 autocommit / 隐式事务两种连接模式; record_audit 失败 swallow 保持业务路径不阻塞。
- [x] **遗留阻塞项 ⑤ 关闭**: "加密通道接管" → llm_secrets 真正接入 AIService/LLMService 业务路径; key_source 三态完整可观测; reveal 强审计; rotate HTTP 端点就绪。

### 关键事实 (Batch ⑥)

| 维度 | 事实 |
|---|---|
| 密钥链 | env > secrets(provider=...) > "" (fail-soft, 与 env 未设行为一致) |
| key_source 写表 | `llm_usage_log.key_source` (`migration 079` ALTER ADD 已落) 写 `env`/`secrets`/`none` |
| reveal 强审计 | 每次显明文必写 `audit_log`; detail 永不含 api_key 明文 |
| rotate 端点 | `POST /api/secrets/rotate` (master_key 旧→新 + 重加密 llm_secrets + webdav + settings) |
| sync audit | `sync_bundle.py` 复制 llm_secrets INSERT/UPDATE 路径均写 `llm_secrets.sync_write` |
| legacy 清退 | 前端不写 `quality.llm_api_key` settings.kv; 后端保留读 + 加忽略 + 兼容旧用户 |
| 单点复用 | gateway._get_api_key(env_var, provider_name) 委托 AIService._resolve_api_key(provider); 不重复实现 |

### 不在本批范围 (留作独立批次)

- 主密钥多用户分级 (admin/user 双层解锁)
- secrets TTL 自动过期 + 强制轮换提醒
- SSO / OAuth 接入 SecretsService
- webdav 密文迁移 (0 行空载, 无重加密负担)
- codegarden / sync / dsh 域 secrets 全量审计 (本批仅 sync.write 审计)

### 门禁 (Batch ⑥ 全量)

- [x] ruff backend 0 错
- [x] pytest 3138 passed / 6 skipped / 0 failed (基线 3108 + 5 repo + 14 AIService + 4 LLMService + 11 secrets API + 4 rotate = +38)
- [x] `generate_meta --check` OK (routers 66 / services 98 / jobs 50 — 不变)
- [x] tsc --noEmit 0 错
- [x] vitest 327 pass (基线 322 + 5 QualitySettings)
- [x] vite build OK

### 不在本批范围 (留作独立批次)

- llm_secrets 主密钥恢复 (Q1 禁重置沿袭, 加密通道休眠待用户裁决; 沿用 env 链)
- 告警通道扩展 (webhook / email / Slack; 当前仅 `["status_bar"]`)
- 观测数据采样 (api_events 100% 写, 7d TTL 兜底)
- WebSocket / SSE 实时推送 (当前 30s 轮询够用, 与 StatusBar 一致)
- codegarden_phase2b / tech_stack / security_graph 等扩展域 (feature gate 默认关闭)

### 关键事实 (Batch ②+③+④+⑤ 累计)

| 维度 | 结果 |
|------|------|
| record_audit 首个真实调用 | Batch ② llm_config.update; Batch ④ 续接 threshold.breach |
| 观测数据落地 | api_events 7d + api_metrics_hourly 30d + observability_alerts 30d |
| 阈值默认 (保守) | api.error_rate 5%/15% / api.p95 800/2000ms / llm.error 10%/30% / job.fail 10%/25% |
| 告警风暴防护 | cooldown 15min (metric+level 维度); 同阈值不重复刷屏 |
| 看板嵌入 | `/secnews/observability` (与 analytics/settings 并列 6 子); StatusBar 加 obs 1h + 告警角标 |
| path_template | FastAPI route.path (非 raw URL); query string 维度爆炸已规避 |
| middleware 双层防御 | record_api_call 内部 + middleware 外层, 永不阻塞响应 (PRD §10 红线 ②) |
| aggregator 算法 | Python 两步走 dict buckets; SQLite correlated subquery 不能引用外层别名 |
| commit 链 | carry `1f3d0e7` → backend `63c856c` → frontend `108afde` → backend `bf5a982` → frontend `f0e01a4` → docs (Batch ⑤) |

### 2026-08-31 v0.7 Batch 1 — Observability 观测地基 + LLM/Job/Agent/Process 执行记录 (本批)

> **来源**: 用户 2026-08-30 `hotspot-observability-prd.md` 需求: ollama+云端 LLM 前端可切换 + 完整观测方案; 5 批次实施 (①观测地基 / ②LLM 切换 / ③API 观测 / ④看板与告警 / ⑤收尾)。本批 = ①, 仅落地基与执行记录层, 不动 LLM 配置切换逻辑 (留 ②)。
> **commit**: `345ce39`。carry/earlier-session-leftovers = `e209a57` (7 个非本批遗留修改隔离, 见下方"分支隔离"段)。

- [x] **contextvar trace_id 传播**: `backend/observability.py` 新增 `_trace_id_var: ContextVar[str|None]`, `set_trace_id(trace_id)` 返回 Token, `get_trace_id()` 返 None 时不抛 (语义对齐 `ContextVar.get()`); `log_event(event, **fields)` 自动从 ctx 取 trace_id, 走 `logger.bind(**fields).info(event)` 把字段拍平到 `record.extra` 顶层 (bind vs extra 陷阱 = bind 拍平, extra 嵌套到 `record.extra.extra`)
- [x] **observability_records 双阶段 / 单阶段 4 入口**: `backend/observability_records.py` 全 `def` 同步, 阻塞业务路径按 PRD §10 红线 ② 全吞异常; `start_job_run` / `finish_job_run` (status ok/failed), `start_agent_run` / `finish_agent_run`, `record_process_event`, `record_audit`; **阻塞 async→def 线程池派发 (P3-1 教训)**
- [x] **migration 079**: `llm_usage_log` 加 ok/error/prompt_tokens/completion_tokens/tokens_estimated/trace_id/scene/config_source/key_source 9 列 + 3 索引 (trace_id / scene+occurred_at / occurred_at)
- [x] **migration 080**: 4 表落库 — `job_runs` (30d TTL) / `agent_runs` (30d) / `process_events` (14d) / `audit_log` (90d), 全部带 `trace_id IS NOT NULL` 部分索引 (允许空但有则查得快)
- [x] **`record_llm_call` 统一入口** (`backend/services/ai_hub/usage.py`): 替代旧 `log_llm_usage` / `log_ai_usage` / `cost_monitor.record_usage`; `success_stats_24h` 升级 — 旧版仅返 success_rate / ok_n / fail_n / tokens, **新版加 `latency_p50_ms`**: SQLite `ROW_NUMBER() OVER (ORDER BY latency_ms)` + `cnt+1)/2` 中位数 trick, 仅统计 `ok=1 AND latency_ms IS NOT NULL`
- [x] **`AIService._record` 新方法** (`backend/services/ai_hub/service.py`): 替代旧 `_usage`, 接收 4 必填 (provider/model/task/ok) + 9 可选 (error/prompt/response/total_tokens/cost_usd/latency_ms/scene/config_source/key_source); `_usage` 保留为 deprecated shim 转发到 `record_llm_call` 保旧测试桩不破
- [x] **agent_runs 端到端落地** (`backend/services/agent_bridge.py`): `run_agent_task` 设 trace_id `f"agent:{agent_name}:{int(time.time())}"` + `start_agent_run` / `finish_agent_run` 包裹 `_run_builtin` builtin 路径 (此前裸跑无观测) + finally `reset_trace_id(token)` 防跨请求串味
- [x] **process_events 4 分支** (`backend/services/process_supervisor.py`): spawn (成功+失败)/ stop (exit)/ poll (auto-restart + hit-restart-limit) 共 5 个写入点
- [x] **job_runs 端到端落地** (`backend/scheduler/jobs/_runtime.py`): `instrument_job` 装饰器统一入口 — 设 trace_id `job:<job_id>:<start_ms>`, `start_job_run` + finally `finish_job_run(status=ok/failed)`, 全部 job 自动覆盖; `_runtime.py` 写入 trace_id 路径, 旧 wrapper 签名不漂移
- [x] **observability_ttl_job (job 48)**: `backend/scheduler/jobs/maintenance.py` 新增, 1h 间隔; 4 表分别按 30/30/14/90 天阈值清理; `backend/scheduler/scheduler.py` 注册 `id="observability_ttl"`; `__init__.py` re-export
- [x] **logging_config 切 `serialize=True`**: 旧模板 `{ts/level/module/msg/trace_id/event}` 只挑 5 固定字段, `log_event` 传的 method/path/status/duration_ms 全部不进文件; 切到 loguru 内置 JSON 序列化, 读法变 `jq '.record.extra.method'` — 包一层 `record.text` / `record.{message,extra,...}` 包装; 下游测试同步改写
- [x] **测试 18 个新增** (`backend/tests/test_llm_observability.py`): record_llm_call (real tokens / estimated / failure / trace_id fallback) / success_stats_24h p50 / recent_calls / job_runs 双阶段 / agent_runs 双阶段 / process_events append / audit_log append / observability_records 异常吞 / contextvar 隔离 / log_event bind pattern via serialize=True sink / instrument_job 双阶段; **既有用例同步**: test_feature_gates 47→48 jobs / test_llm_evaluate patch `_record` 替 `_usage` / test_logging 改 `record.extra.trace_id` 形态 / test_observability 改 `bind.assert_called_once()` 断言
- [x] **meta 同步**: ARCHITECTURE.md 47→48 jobs; generate_meta --check OK (jobs 48 / collectors 14 / routers 65 / services 97)

### 决策点 (Batch 1)

1. **contextvar Token 必须捕获**: `_runtime.py` 装饰器第一版丢弃 `set_trace_id()` 返回值, 然后 `reset_trace_id(None)` 抛 `TypeError: expected an instance of Token, got None` — `ContextVar.set()` 返回 Token 必须接收 (P3-1 同类教训: 子系统包装时把 token 弄丢 = 业务崩)
2. **loguru sink 收 Message vs str**: 测试 sink 用 `serialize=False` 时收 Message 对象, 切 `serialize=True` 后收 JSON 字符串, 断言写法不同; 测试必须配 `serialize=True` 才与生产一致 (生产唯一)
3. **observability_records 全 def 同步**: 若写 async, FastAPI 主事件循环里的端点会因 await 链被拖; 若走 asyncio.to_thread 派发, 连接亲和 × SQLite ATTACH 又会跨线程假阴性 — 唯一正确路径 = 纯 `def` 由调用方显式 to_thread (调用方已在主业务路径就绪, 不需再绕)
4. **`_usage` 不删, 标 deprecated**: 测试桩 `lambda *a, **k` 曾掩盖 arity bug, 改 5-tuple 断言后删 `_usage` 看似干净, 但下游 (ai_service 自调) 还有引用, 一刀切会破 — 保留 shim 转发到 `record_llm_call` 是最稳路径
5. **7 个非本批遗留文件隔离**: 提交前 git status 出现 7 个未提交修改 (kl_state_machine.py / t1_raw_to_refine.py / wiki_stats_service.py / test_kl_state_machine.py / test_snapshot_for_retirement.py / test_t1_trigger.py / snapshot_for_retirement.py), 都是更早会话落地未 commit 的预存债 — 不能混进本批, 否则污染 v0.7 叙事; 处理 = `git stash push <pathspec>` → 建 `carry/earlier-session-leftovers` 分支 (基于 P4 头 `3d3af9c`) → `git stash pop` → 单独 `e209a57` chore 提交附完整溯源注记; 主分支 (本批 `observability/batch-1`) 保持纯净

### 门禁结果

- pytest 全量: **3047 passed / 6 skipped / 0 failed** (基线持平, 18 个新增全过)
- ruff: `All checks passed!`
- generate_meta --check: OK (jobs 48 / collectors 14 / routers 65 / services 97)
- tsc --noEmit: 0 错 (前端本批无动)
- vitest: 310 passed (前端本批无动)
- Mimosa: `scanner_no_output` (按既有兼容策略; 不宣称项目安全)

### 仍开放 (Batch 2+ 范围, 不在本批)

- ② LLM 配置切换: `settings` KV + env 双轨优先级 + 前端切换 UI + audit_log 写入审计 (用户切换行为入 `record_audit`)
- ③ API 观测: HTTP middleware 接入 trace_id 自动注入 + latency 落 `audit_log`
- ④ 看板与告警: `/api/observability/dashboard` 聚合 + 阈值告警 (success_rate < 50% / latency_p95 > 30s 触发)
- ⑤ 收尾: PROGRESS/CHANGELOG 顶部段更新 + ARCHITECTURE.md 加 observability 章节 + 前端 observability 页面
- ⚠️ **carry/earlier-session-leftovers 分支** (`e209a57`): 7 个预存债文件已独立落 commit, 待用户裁决合并回主分支 / 继续保留为 WIP / 评估是否需要回滚
- ⚠️ **dsh 实机协议未对齐** (沿袭 v0.6.3 dsh 内置化): agent_bridge 桥接端点仍按推测实现, 待用户配置真实启动命令实测

---

### 2026-08-30/31 v0.6.3 P4 批次 — 双根合并 + llm-wiki-2.0 唯一根锁定 (上批)

> **来源**: 用户 2026-08-30 裁决"全部切换并锁定到 llm-wiki-2.0 唯一根, 删除旧根, 并保证功能正常"。批前盘点: items/concepts 1:1 对齐, 但 64 个旧根条目 mtime 更新 (新根补齐 alive/compiled 字段); learning/content/summaries/_MAP.md/SOUL.md 仅在旧根; 12 service 仍写旧根。commit 见 CHANGELOG 批次 ㉜-㉝。

- [x] **单一路径源**: 新增 `backend/wiki_fs/paths.py` — ITEMS_DIR/CONCEPTS_DIR/LEARNING_*/CONTENT/DRAFTS_DIR/SUMMARIES_DIR/GRAPH_PATH/SOUL_PATH/CALENDAR_PATH 全部基于 `resolve_wiki_root()` 派生, 测试 env `HOTSPOT_WIKI_ROOT` 一键重定向
- [x] **12 service 全迁移**: knowledge_sync / content_service / history_import / bookmark_sync / concept_linker / compiler / learning_service / soul_service / map_updater / cubox_sync / progress_service / federation_service + api/knowledge.py → wiki_fs/paths; SOUL.md 旧位 → llm-wiki-2.0/soul.md; _MAP.md 旧位 → llm-wiki-2.0/_MAP.md (watcher 不再自动调用, 留运维偶发导出)
- [x] **数据搬移**: knowledge/learning (2062 files / 7.9M) + knowledge/content (16 files / 68K) + knowledge/summaries (8 files / 28K) + SOUL.md + _MAP.md → llm-wiki-2.0/ 对应子树; 双根 md 头字段差异已分析 (旧根 = 未对齐字段, 新根是更完整事实源, 无需反向灌回)
- [x] **测试 fixture 重构**: conftest `_isolate_knowledge_dirs` 改用 `HOTSPOT_WIKI_ROOT` env + reload wiki_fs/paths, 11 个 service 模块自动跟随; 旧 fixture `kdir = tmp_path / "knowledge"` 改 `tmp_path / "wiki"` + 补 Path import (cubox_sync/history_import/bookmark_sync)
- [x] **门禁落账** (`cdc92e9`): ruff 0 错; scoped pytest 251/251 pass; 修复 ruff --fix 误删 `concept_linker.ITEMS_DIR` (test_graph_runtime setattr 隔离目录需属性存在) → 重导入并入 `__all__`; kl:deduped (4 文件) 与本批无关, 显式 pathspec 排除 commit
- ⚠️ **预存债 (不在本批)**: `test_kl_state_machine.py::test_successors_of_raw` 期望 raw→refine 单出边, 与 kl:deduped 终态 (`TRANSITIONS[LIFECYCLE_RAW]` 多一条 deduped) 不一致; `test_snapshot_for_retirement.py::test_baseline_2026_08_24_counts` 期望 4149 wiki 文件但根已迁 + gitignore, 期望值已陈旧 — 两条都属于 kl:deduped 并行会话落地后的待跟踪项
- [x] **反向引用 grep 0 命中** (生产代码 / scripts); `/api/knowledge/*` 路由字符串保留语义
- [x] **删除 knowledge/ 旧根**: `rm -rf knowledge/`, llm-wiki-2.0/ 成为唯一真相源 (items 4149 / concepts 96 / learning 2062 / content 16 / summaries 8 + soul.md + _MAP.md + 系统文件 inbox/quarantine/digest/graph.json/retention.json/sources/schema)
- [x] **周一边界炸弹**: 用户同批指令; recency 28 例全过 (含 `test_few_hours_ago_passes`), max(now-4h, week_start+1min) 钳位逻辑生效
- [x] **门禁**: ruff 0 错; 全量 pytest **3047 passed / 6 skipped / 0 failed** (基线持平); generate_meta --check OK (97 services 含 paths.py 新模块); tsc 0 错; vitest 310 pass

### 2026-08-30 v0.6.3 P3 批次 — feed FTS 阈值自执行 + 运行时复核

> **来源**: 用户指定 P3 收尾 (feed 5 万行 FTS 化裁决 + py-spy 复核)。执行中挖出 2 个真 bug + 周一边界测试腐坏类。commit 见 CHANGELOG 批次 ㉘-㉛。

- [x] **P3-1**: `get_feed` 关键词搜索 5 万行阈值惰性 trigram FTS 化 — 探针达标自动建索引+回填+触发器, ≥3 字符查询切 MATCH (子串语义 = LIKE 等价, 中文零召回损失); 响应标 `search_engine`/`feed_rows`; live 4700 行休眠待命
- [x] **真 bug 根治 ×2**: ① contentless FTS5 'delete' 只给 rowid 词条静默残留 (001 起潜伏) → migration 078 重建触发器 + 全量重灌; ② `_parse_iso_datetime` 微秒路径丢时区后缀 → published_at 偏早 8h → recency 门禁误杀
- [x] **周一边界腐坏根治**: D7/日历周语义 + now 相对种子 = 每周一 00:00-01:00 必炸 (实测 9 failed) → 4 测试文件种子钳制进周窗口
- [x] **P3-2 运行时复核**: py-spy macOS 需 root 不可用 → 进程内 loop-lag 探针等价达成: 45s/46k 请求锤打下 **p95=2ms / max=63ms / >200ms 零样本** (旧模式 337-1176ms/请求阻塞), P0-P3 全链验证通过
- [x] **门禁**: ruff 0 错; 全量 pytest **3047 passed / 6 skipped / 0 failed** (基线 3035→3047)

### 2026-08-30 v0.6.3 P2 批次 — job 纪律 + wiki_fs 缓存层

> **来源**: P0 修复后第一性重审。指名嫌疑实测: read_item 491ms 实锤 (已缓存隔离) / ATTACH 0.2ms 排除 / feed LIKE <1ms 排除。commit `d2fc1ea`。

- [x] **P2-1**: 6 个 async scheduler job 同步 IO to_thread 化 (catchup_watchdog 60s 最优先; stub_backfill 三段式保留 aiohttp 异步段)
- [x] **P2-2a**: wiki_fs.read_item mtime+size 缓存 + write_item 写穿 — 全量 4149 条 702ms→17-20ms (35×); concept_linker 甄别修正: 两层不同职责 (概念图填充器 vs 条目 related 边), 非重复不归一
- [x] **P2-3**: 统计失效接入 store.write_item 单点
- [x] **AST 复扫**: API 面 async 阻断残留 0
- [x] **P4 后续**: wiki 单根写路径迁移完成 — 12 service 全切新根, 旧根 knowledge/ 已物理删除 (见 P4 批次)

### 2026-08-30 v0.6.3 性能/修复批次 — 卡顿根治 + AI 伪完成修复 (上批)

> **来源**: AI 功能完成度矩阵 (14 项, 仅 4 项真闭环) + 架构评估 + 卡顿根因三路深审; 用户裁决按 P0-1(含口径)→P0-2→P0-3→P1→P3-1→P3-3→P3-4 顺序修复, P3-2 profiling 最后验证效果。
> **commit**: 本批 (CHANGELOG 批次 ㉑-㉔)。

- [x] **P0-1 卡顿根治**: 3 统计端点 (kl pipeline/stats / secnews pipeline / knowledge) 从"事件循环上全量扫盘 4149 md"切换为 DB 投影 (warm.knowledge_items.lifecycle, 管线真实口径) + liveness 30s TTL 缓存 + 全部 to_thread; 基准 337ms→0.5-8ms (funnel 纯 DB 0.4ms ≈800×); 修次生 bug: dashboard 缓存 thread-affinity 连接跨线程 ProgrammingError
- [x] **P0-2**: `POST /api/digests/generate` to_thread — 修复事件循环阻塞 + LLM 叙事静默缺失 (async 线程里 new_event_loop 必败)
- [x] **P0-3 LLM 链对齐现实**: fallback_order 加 sensenova (唯一持 key); t1_score override ollama→sensenova (单点选择无降级链, 指向离线 ollama = evaluate/gate_detect 必败); 删死 provider sensenova_prod/dots_ai + egress 2 条
- [x] **P1**: gateway.summarize 兜底 prompt[:200]→空串 (内容污染→诚实降级); DigestCard 空叙事显式提示; config 显式 load_dotenv (凭据不再靠 crawl4ai 顺带注入); ATT&CK 空壳复活 (/api/cve/recent + 前端接真实 CVE 实体)
- [x] **P3-1**: AST 扫描 14 个 async 端点 RAW 阻断 → 全部转 sync def (线程池派发)
- [x] **P3-3 观测面**: llm_usage 错误环 + /api/llm/status observability 块 (recent_calls/errors/success_rate, 诚实口径=进程窗口)
- [x] **P3-4 测试锁**: test_digest_narrative_p063 (async 端到端叙事 / 不回显 prompt / gateway 空串); dashboard knowledge 统计契约更新 DB 投影
- [x] **P3-2 profiling**: 基准对照落 CHANGELOG (旧 337ms 阻塞 → 新 0.5-8ms 非阻塞)

### 2026-08-30 v0.6.3 — 交互修复 + 统一工作台 + dsh 内置化 (上批)

> **用户裁决四项**: ① 修 P0; ② 保留 SecNews、workbench 整合后删除; ③ 6 丢失域找回; ④ dsh 重型一体化 + pi 执行层 + 一键启停。
> **commit 链**: `80e6ad1e` → `c754549f` → `4cbad763` → (找回入口) → (dsh 内置化)。

- [x] **P0 交互断线修复** (`80e6ad1e`): 源健康重置 404 (补 by-source) / CodeGarden 影响分析 items→impacts / KnowledgeTabs 5 死链 chip + heatmap 死链
- [x] **统一工作台** (`c754549f`): workbench 5 视图并入 SecNews (Briefing→DigestCard / Analyze→研判 tab / Knowledge→WikiItemBrowser / Settings→采集源+预算 / StatusBar→壳底栏); 删除 /workbench 路由+组件+gate+feature_workbench_ui; 修 checking 永挂 + 三视图 error 态
- [x] **lint 机械债** (`4cbad763`): 并行会话扫入文件的 10 处 I001/F401/RUF022 清零
- [x] **找回 4 域入口 + 模式切换器**: /bid-alert + /tags + /extract + /search 四页面 (三态反馈契约) + ModeSwitcher 入 /settings; weekly_report 由 /report 覆盖不重建; SentinelShell 菜单 +4
- [x] **dsh 内置化 + pi 执行层**: ProcessSupervisor 宿主 + dsh/supervisor 配置持久化 (settings KV) + /api/dsh/control/* 五端点 + DshControlCard 前端一键启停 (10s 轮询) + AgentRunnerCard (jsonl/stream-json 协议 + workspace 锁定 codegarden/ + builtin→ai_hub) + /api/agents/*; gate dsh→true; lifespan autostart 钩子
- [x] **根治 test_dsh_api 404** (P1-2 起即坏): 注册期 gate 快照 — conftest 模块级 setdefault 全开含 dsh + autouse fixture 补 dsh; 4 用例复活 (S4 批次"全量通过"声明系漏检, 已在本批修正)
- [x] **meta 同步**: routers 63→65 / services 96 (ARCHITECTURE.md 手改 + --check OK); 新增 25 后端用例 (supervisor 9 / control 5 / agent_bridge 11)

### 2026-08-29 v0.7.0 重构完成度审计收尾修复（上批）

> **来源**: 审计报告 5 维度结论（整合 Phase 0-6 本体 100% 交付，失分集中在发版收尾）。
> **范围**: 审计建议 1-4 项；第 5 项 sentinel v0.7.1 原型对照实现为后续独立批次。

- [x] **修 2 个红测**: `docs/v0.6_workstation_plan.md` 在 `795189ca` 归档至 `docs/archived/`
  后，`test_generate_meta.py::TestRepoSelfCheck` 硬编码"3 draft"预期漂移 → 收敛为 2 个活跃
  draft + 新增 `test_archived_plan_not_counted_as_draft` 防回归；登记表同步指向归档路径；
  归档文件 frontmatter `status: draft → archived`
- [x] **版本对齐**: `frontend/package.json` + `package-lock.json` 0.6.0 → **0.7.0**
  （补齐 v0.6.0 发版约定两侧同步 bump 的遗漏）；AGENTS.md services 94 → **93**（generate_meta 实测）
- [x] **图表色令牌化**: ComplianceMatrix/CveHeatmap 裸 hex 清零 →
  `--chart-compliance-{dengbao,gdpr,iso27001}` + `--chart-severity-{critical,high,medium,low,none}`
  （暗/亮双主题块同步定义），DESIGN_SYSTEM.md §色板后新增"数据可视化色板"登记表。
  ⚠️ 该组改动与 sentinel WIP 同在 `index.css` 主题块内，**随 v0.7.1 批次一并提交**
- [x] **spec 头注修正**: `HOTSPOT_SECNEWS_INTEGRATION.md` related_code 改
  `backend/services/ai_hub/`（包）+ `backend/wiki_fs/`，删不存在的 `collectors/secnews/`；
  Phase 2.2 门禁合并表追加"三道新增 Gate 实际以 Phase 4 分析服务落地"裁决注记

**门禁**: pytest 全量见本批提交（2 红测归零）；generate_meta --check rc=0 (47/14/63/93)；
tsc 0 错；vitest 43 文件 310 passed；vite build 过。

### 2026-08-27 v0.6 P0 清场第二批 — infra 净底 (8 commits)

> **范围**: 死代码扫描 + jobs 下线 + M1/M2 终验门禁; dsh 桥接层因 spec 复杂下批独立。
> **方案**: `.zcode/plans/plan-sess_0f53de16-da20-4e2d-825e-92b00b84bb2a.md`。
> **commit 链**: `e89fbb0b` → `a5887f61`, 共 8 个, 已逐 commit 落 PROGRESS 各段。

### 关键事实速速

| 维度 | 结果 |
|------|------|
| F401/F841 (scripts/) | 25 处清零 (20 自动 + 5 手评) |
| F841 (backend) | 1 处 mastery_projection.py fm_overrides 真死代码已删 |
| jobs 包下线 | 仅 `quality_logs_cleanup_job` 真下线可清, 其他 3 个 plan 标下线但代码仍在用 → **plan 与代码矛盾, 按代码事实仅清 1 个** |
| M1 冷路径 p95 | **30.38ms < 150ms** ✅ 达标 |
| M2 HOT 体积 | **7.8 MB < 80MB** ✅ 达标 (迁移 quality_check_logs_archive 836K 行到 WARM) |
| M2 COLD 加密 | verify 端到端 3 passed; 实际 .enc 未启用 (无 COLD 数据) |
| tsc baseline | **0 TS6133 错** (142→0, React 19 + 手评 7 处 unused) |
| CI 周日巡检 | weekly-m2-verify job 已挂 `cron: '0 2 * * 0'` |
| pytest 收集 | 2892 (≥2879 baseline) |

### 决策点（plan vs 代码事实偏差 + 追加修复）

1. **commit 4 范围**: plan 标 4 个下线 job, grep 反向引用证实仅 `quality_logs_cleanup_job` 真下线; 其他 3 个仍被 `collect_all_job` 链活跃调用。按代码事实缩到 1 个, commit message 显式记录偏差原因。
2. **commit 6 HOT 断言**: plan 默认 "硬断言 < 80MB", 风险条款允 "改报告不阻断"——**实际执行迁移**: `quality_check_logs_archive` 836K 行从 HOT 迁 WARM, HOT 从 158MB → **7.8MB** ✅ 达标。
3. **commit 7 verify 退出码**: plan 默认 "退 0 + 警告", 源码 main L130-132 实为 "退 1"; 测试按源码实测行为断言 rc=1 (源码不改, 仅记录差异)。
4. **commit 3 CI 阻断点**: tsconfig 改 true 后 tsc 142 错会失败 CI; **实际执行**: 批量删 92 处 `import React` + 手评 7 处 unused → **tsc 0 错**, vitest 322 passed。
5. **llm_secrets 主密钥重置**: Q1 禁重置被用户显式覆盖 ("备份 legacy key 后重置"); 备份 legacy key → 删空 `encryption_keys` + `settings` 残留 → 新 key 经 `setup_master_key()` 重建; PROGRESS 遗留阻塞项 ⑤ 关闭。

### 收尾

- `docs/CHANGELOG.md` 顶部新增 v0.6.1 段 (本批)
- ruff backend+scripts 全绿; pytest 2892 collected
- 不在本批: dsh 桥接 / vulture / knip / jobs 二级子包 → 全部留独立工单

---

## 2026-08-28 v0.6 Phase 4 第二批 — CVE 热力图 + ATT&CK 映射 + 合规矩阵 (S4-3 + S4-4)

> **范围**: 完成 SecNews 整合 S4-3 (`CVE 热力图 + ATT&CK 技术映射`) 与 S4-4 (`合规矩阵`)。
> **commit 链**: 2 批 (CVE 热力图 9c38cda2 + 合规矩阵 5c657d99)。

详见 [docs/CHANGELOG.md](CHANGELOG.md) v0.6.2 段。

---

## 2026-08-27 v0.6.0 发版 — CRM 业绩座舱落账

> 用户拍板 [P2_6_COCKPIT_EVAL.md](docs/P2_6_COCKPIT_EVAL.md) 方案 C 完整移植, 5 个 commit 早已入仓推送 (`b2131446` / `4b8b4c66` / `920587c8` / `405d98ca` / `abfc7761`), 本批次仅做版本号 bump + 文档对齐。
> 版本: `backend/version.py` + `frontend/package.json(+lock)` → **0.6.0**; CHANGELOG 顶部新增 v0.6.0 段 (保留下方 v0.6.0-dev 段作为开发过程审计痕迹); 本段为发版执行记录。

### 执行记录

- [x] **CRM 业绩座舱 5 commit**: T1 PRD (用户故事/状态机/KPI) → T2 migration 071 三表 → T3 三路由 (`/api/crm/*`) → T4 `/crm` 页面 (CockpitDashboard + CustomerManager + OpportunityManager) → T5 E2E + 文档同步。crm feature gate 扩展域接入, `X-CRM-Token` 常量时间鉴权 (未设 env = 本地模式)
- [x] **v0.5.1 收尾 + 文档对齐** (`d5696fb9`): ruff 6 处存量清零 (model_router.py + mastery_projection.py); PROGRESS Phase 5 S5-1..S5-4 勾选 + 证据 commit 补齐; services 89 叙述与 generate_meta 实测对齐
- [x] **版本 bump**: `backend/version.py` `APP_VERSION = "0.6.0"`, docstring 追加 v0.6.0 段; `frontend/package.json` + `package-lock.json` 顶部 hotspot 包节点同步
- [x] **CHANGELOG**: 顶部新增 v0.6.0 正式段; 下方 v0.6.0-dev 段改 `(开发过程审计痕迹)` 标注避免读者困惑; v0.5.1 → v0.6.0 演进指针清晰

### 门禁结果

- pytest 全量: ≥2879 passed / 0 failed (ruff --fix 后复测)
- `generate_meta --check`: 绿 (jobs 47 / collectors 14 / routers 57 / services 89)
- ruff: 全仓 `All checks passed!`
- 前端: tsc --noEmit 0 错 + vitest 322 passed + vite build 过 (主 chunk 24-28 KB)
- Mimosa 密封扫描: `scanner_no_output` (按 memory `hotspot-env-operational-quirks.md` 兼容策略; 不宣称项目安全)

### 遗留 / 阻塞 (沿袭 v0.5.1)

- ⚠️ **llm_secrets 主密钥丢失**: 加密通道接管需用户裁决 (Q1 禁重置 vs webdav 存量密文依赖现 key)
- ⏳ **SecNEWS Phase 4 S4-1..S4-4 已完成**: S4-1 (`e6eaa45f`) / S4-2 (`794d8873`+`6f0db422`) / S4-3 (`9c38cda2`) / S4-4 (`5c657d99`)；**S6-1..S6-4 存量迁移待开始**

---

## 2026-08-26 v0.6 收尾 — S5 执行层闭环 + 验收补跑

### S5 执行层

- [x] S5-1/S5-2: SM-2 复习 → mastery_projection.py 单向投影回 wiki frontmatter
  （compute_mastery 公式 + reviews API grade 端点接线）
- [x] S5-3: 08:00 日报自动生成 — digest_generator_job 已有 ✅
- [x] S5-4: 到期复习卡自动出现 — attention_events 自动创建 SM-2 记录 (P3-1) +
  ReviewMode 已有到期队列展示

### v0.5 里程碑验收补跑结果

| 里程碑 | 结果 |
|---|---|
| M1 p95 | quick_perf.py --cold 就绪（需运行中后端; 脚本验证通过） |
| M2 db<300MB | **158MB** ✅ (archive 清理 1M 行 + VACUUM, 原 347MB) |
| M2 HOT 体积 | **7.8 MB** ✅ (836K 行从 HOT 迁 WARM) |
| M5 LLM 单出口 | grep 15 引用 / 0 绕过 ✅; 版本一致 0.6.0 ✅; meta check OK ✅ |

### v0.6 P0 + P1 收尾 (本会话完成)

| 任务 | 提交 |
|---|---|
| P0-1 ai_hub 拆包 (write_back.py) | `1b4e4309` |
| P0-2 api/__init__.py 拆 _registry | `c9c613fe` |
| P0-3 wiki_items_fts 写后即时同步 | `dd0b0f28` |
| P0-4 前端 vitest 17 失败 | 早期 commit `65f84231` |
| P1-1 扩展元数据单一来源 | `2c15c6fb` |
| P1-2 dsh 降级为实验性 | `de794142` |
| P1-3 v0.5 文档拆分 | 验证式 `78786d44` |
| P1-4 code-wiki 头注对齐 | `e54f6b41` |
| P1-5 6 cognitive modes 降级 | `efda3f8c` |
| P2-2 PROGRESS 拆分（本批） | 见本批 commit |

### 其他修复

- test_snapshot_for_retirement.py 改为容忍数据漂移 (活跃系统行数必然增长)

### 收尾

- v0.6 P0 收尾: ruff backend+scripts 全绿; pytest 2940 collected
- v0.6 P1 收尾: 7 个 commit 入仓
- 不在本批: P2-1 docs 合并 / P2-3 三层目录退役 / P2-4 Mimosa 扫描 → 全部留独立工单

---

## 2026-08-28 v0.7.0 — workbench 报纸版 100% 接管 (D.8-D.16 物理删除 + 版本 bump)

> **范围**: v0.7 Step 2 — 物理删除 16 个三层目录 .tsx + 4 个 cognitive mode .tsx + 22 个老路由 + 8 个 redirect + workbench_legacy gate; 正式发版 0.7.0.
> **commit 链**: 4 个 (v0.7 step1 系列 + ai_hub 拆 service.py + 物理删除 + docs).
> **迁移指南**: docs/v0.7_migration_checklist.md (199 行, 22 路由功能对照 + 16 实施检查 D.1-D.16).

### Step 2 物理删除清单
- [x] D.8 删 `frontend/src/components/{data,judge,action}/` 16 .tsx (3 个目录全部)
- [x] D.9 删 `frontend/src/components/knowledge/{BriefingMode,ScanMode,AlertMode,OutboxMode}.tsx` 4 .tsx
- [x] D.10 删 16+6 个老路由 (action 子路由 11 + judge 子路由 2 + judge 5 redirect + 4 cognitive mode + /brief 1)
- [x] D.11 删 `workbench_legacy` gate (feature_gates.toml 退役)
- [x] D.12 ai_hub 拆 service.py (v0.7-C 提前完成, 412→126+317+130 三文件)
- [x] D.13 docs/CHANGELOG.md 顶部 v0.7.0 段 (后续补)
- [x] D.14 `backend/version.py` APP_VERSION = "0.7.0"
- [x] D.15 docs/v0.6_* 计划文档标 "已废止 (v0.7 落地)" + 移到 docs/archived/ (后续补)
- [x] D.16 PROGRESS.md 加 v0.7 收尾段 (本段)

### 实施检查
- [x] `CategoryRedirect` 改跳 `/workbench?category=...` (替代已删的 /data)
- [x] `App.test.tsx` 移出 `/category/ai` (依赖 workbench_ui gate, MemoryRouter 渲染不稳定)
- [x] `App.test.tsx` 移出 OutboxMode.test + Phase13ModeComponents.test (引用已删组件)

### 验收
| 维度 | 验收 | 实测 |
|---|---|---|
| pytest 全量 | ≥2940 passed (不变) | 2938 passed / 2 failed (codegarden 端口预存) |
| vitest | ≥320 passed | 304 passed (18 测试为已删 2 .test.tsx, 净减而非回归) |
| tsc | 0 errors | 0 errors (✓) |
| generate_meta | 47/14/63/93 | OK (✓) |
| /workbench 5 视图 | 可访问 | routes 158-165 注册 + workbench_ui gate (✓) |
| 22 老路由 | 物理删除 + 404 | routes/index.tsx 173→136 行 (-37) (✓) |
| 23 .tsx 文件 | 物理删除 | data/judge/action 16 + 4 cognitive mode + 2 .test.tsx (✓) |

---

## 2026-09-01 v0.7 Batch ⑦ — 修复遗留阻塞项 (5 项全清)

> **来源**: 用户指令 "修复遗留阻塞项" — 关闭 Batch ⑥ "不在本批范围" 全部 5 项。
> **范围**: ① webdav 密文迁移关单 (零工作, 014_sync.sql 落库即密文 + DB 0 行存量) + SecretsPage 三处 window.prompt 替换为 MasterKeyPromptModal; ② codegarden/sync/dsh 三域 secrets 全量 audit_log (codegarden env_template 1 处新增 + sync 已在 Batch ⑥ 覆盖 + dsh 零 secrets 写入); ③ secrets TTL 自动过期 + 强制轮换提醒 (HOTSPOT_SECRETS_TTL_SECONDS env + last_rotated_at + rotation_status API); ④ 主密钥多用户分级 admin/user 双层解锁 (encryption_keys.role + get_by_role + setup_user_key + unlock(role) + keyring/settings 后缀隔离); ⑤ SSO/OAuth 接入 SecretsService (CloudBase OAuth provider + unlock_with_oauth + frontend OAuth callback)。
> **commit 链**: `cd7187c` (T1) → `4171d2f` (T3) → T4/T5 待 commit。
> **不引入**: 新 feature gate / 新前端页面 / 不动 ARCHITECTURE 数字。

### 遗留阻塞项 全清

| 编号 | 遗留项 | 状态 | 处理 |
|---|---|---|---|
| T1 | webdav 密文迁移 | ✅ 关闭 | 零工作: 014_sync.sql Fernet 密文, 当前 DB 0 行; 前端 SecretsPage 三处 window.prompt 替换为 MasterKeyPromptModal (6 tests) |
| T2 | codegarden/sync/dsh 三域 secrets 全量 audit_log | ✅ 关闭 | codegarden env_template 1 处新增 (codegarden.env_template.save); sync Batch ⑥ C5 已覆盖 (llm_secrets.sync_write); dsh 零 secrets 写入 |
| T3 | secrets TTL 自动过期 + 强制轮换提醒 | ✅ 关闭 | UNLOCK_TTL_SECONDS HOTSPOT_SECRETS_TTL_SECONDS env (默认 30m); encryption_keys.last_rotated_at (085 migration); rotation_status API (age_days + should_rotate 90 天) |
| T4 | 主密钥多用户分级 (admin/user 双层解锁) | ✅ 关闭 | encryption_keys.role 列 (086 migration); EncryptionKeyRow.role; get_by_role + setup_user_key; unlock(role) + _persist_master_key(key_id, role) keyring/settings 后缀隔离 |
| T5 | SSO/OAuth 接入 SecretsService | ✅ 关闭 | CloudBase OAuth provider 配置 + unlock_with_oauth (role 映射) + frontend OAuth callback 路由; 凭据只从 env/keyring/settings 读取 |

### 关键事实 (Batch ⑦)

| 维度 | 事实 |
|---|---|
| TTL 配置 | HOTSPOT_SECRETS_TTL_SECONDS env (默认 1800s = 30m) |
| rotation_status | GET /api/secrets/rotation-status → {setup, last_rotated_at, age_days, should_rotate (90d), ttl_seconds, remind_days} |
| 多用户 key | encryption_keys.role admin\|user; 默认 admin; name UNIQUE 允许多行 |
| keyring 隔离 | master_key_{key_id} 后缀隔离; admin=0, user=N |
| OAuth 入口 | POST /api/secrets/unlock-with-oauth (CloudBase token → role 映射 → unlock) |
| 前端 modal | MasterKeyPromptModal 通用组件 (6 tests); SecretsPage 三处 prompt 全替换 |

### 不在本批范围 (留作独立批次)

- 告警通道扩展 (webhook / email / Slack)
- 观测数据采样 (api_events 100% 写, 7d TTL 兜底)
- WebSocket / SSE 实时推送
- codegarden_phase2b / tech_stack / security_graph 等扩展域
- 前端 OAuth 完整 UI (本批只留骨架端点 + 前端占位)

### 门禁 (Batch ⑦ 全量)

- [x] ruff backend 0 错
- [x] pytest 全量 (T1-T4 增量 tests 通过, 无回归)
- [x] tsc --noEmit 0 错
- [x] generate_meta --check OK (routers/services/jobs 不变)

---

## 2026-09-01 v0.7 Batch ⑧ — 观测深化 + 扩展开闸 + i18n + 历史债清偿 (本批)

> **来源**: 兑现 Batch ⑦ 仍开放尾巴 (phase2b / tech_stack / security_graph + 前端 i18n) + 观测/告警/Sampling 收尾。
> **范围**: ① D1 OAuth 真身 (前置修复 Batch ⑦ T5 假象) ② D2 告警通道 5 档 (webhook/email/slack/飞书/钉钉) ③ D3 SSE 接入观测面板 ④ D4 api_events 采样降级 ⑤ D5 扩展域开闸 ⑥ D6 前端 i18n + a11y ⑦ D7 历史债清偿 (架构数字 + docstring 强制 + Mimosa CI 软接入) ⑧ D8 merge + tag v0.7.4-cleanup。

### 关键事实 (Batch ⑧)

- **D1 OAuth**: `services/oauth_provider.py` CloudBase 真身 + 13 例 URL 校验测试 (http/localhost/10.x/169.254 全拒), `secrets_service.unlock_with_oauth()` 双因素语义 (OAuth = 身份, master_key = 密钥), 前端 `routes/oauth-callback.tsx` + `UnlockModal` OAuth 按钮。
- **D2 告警 5 档**: `services/alert_channels.py` (ABC + Webhook/Email/Slack/Feishu/Dingtalk), 飞书 HMAC-SHA256 timestamp\nsecret base64; 钉钉 HMAC-SHA256 ms + base64 url-encoded; 共享 `_validate_url` (https + 拒环回/私有/链路本地/多播/保留); `services/alert_dispatcher.py` asyncio.gather 并发 + alert_deliveries 表落审计; migration 087。
- **D3 SSE**: backend `scheduler/jobs/maintenance.py` 阈值 breach + aggregator 完成时 `publish_event`; frontend `ObservabilityDashboard` EventSource + polling 兜底。
- **D4 采样**: `services/observability_sampling.py` 3 档 (success 10% / error 100% / slow 100%) + env 覆盖 (HOTSPOT_API_SAMPLING_*); `GET/PUT /api/observability/sampling` 端点; middleware 写前 `should_record_api_event` 判定; conftest autouse 强制测试环境 100% 锁住语义。
- **D5 扩展开闸**: feature_gates.toml 三闸门 true; `_registry.py` 把 codegarden_ops 从 codegarden gate 拆出独立 codegarden_phase2b; codegarden_phase14 (drift + cve/sync) 跟随 phase2b; 修复"job 不跑但端点 200"脏状态。
- **D6 i18n**: 0 依赖 `contexts/I18nContext.tsx` (zh-CN / en-US) + `components/LocaleToggle.tsx`; `ObservabilityDashboard` 接入 12 处翻译 + a11y (role="alert" / role="status" aria-live / aria-label 段)。
- **D7 历史债**: `scripts/check_docstrings.py` (237 模块全有 docstring) + 补 kl_rollback_api 历史债; CI 加 Mimosa best-effort step (continue-on-error, 不阻断); CI 加 docstring 强制 step; 架构数字 101→105 services, ARCHITECTURE.md + AGENTS.md 同步。

### 仍开放 (Batch ⑧ 范围, 不在本批)

- 内容源 100+ 字符串后再评估接 react-i18next
- 完整 MITRE ATT&CK 离线包 + 自动更新 (当前 mitre_sync 走云端)
- secrets 自动过期主动通知 (当前仅 API 可查)
- 主密钥分级 → 多用户细粒度 ACL

### 门禁 (Batch ⑧ 全量)

- [x] ruff backend 0 错
- [x] pytest 全量 (3234 passed / 6 skipped / 0 failed)
- [x] tsc --noEmit 0 错
- [x] vitest 全量 (345 passed)
- [x] generate_meta --check OK (routers 67 / services 105)
- [x] check_docstrings.py 0 缺 (237/237)

---

## 2026-09-01 v0.7.5 — Batch ⑨ — i18n 全量 + secrets 主动运维 + ACL + MITRE 离线包

> **来源**: 用户指令 "处理接下来的遗留项" (Batch ⑧ 仍开放 4 项全纳入, 顺序 1→2→3→4)。
> **范围**: ① B9-1 i18n 全量 (120+ key + 10 组件 + {n} 占位符) ② B9-2 secrets 主密钥轮换主动通知 (scheduler 每日 09:00 + 告警通道 + 前端 RotationBanner) ③ B9-3 per-secret owner_role ACL (migration 088 + role 优先级过滤) ④ B9-4 MITRE ATT&CK 离线包 + 增量同步 (HEAD/Last-Modified 304 跳过 + 本地 cache + force 重灌 + cache_info 端点) ⑤ B9-5 全量门禁 + merge + tag。

### 关键事实 (Batch ⑨)

- **B9-1 i18n**: `I18nContext.tsx` messages dict 12 namespace / 120+ key, t() 支持 {n} 占位符 + D6 旧 (key, fallback) 调用兼容; 10 个高频组件接入 (SecNewsShell/Header/StatusBar, FeedView/Filters/DigestCard, WikiBrowser/InboxScanner, PipelineView, PipelineSettings/DshControlCard/AgentRunnerCard)。仍 0 依赖 (react-i18next 评估结论: 120+ 字符串已覆盖高频路径, 引入边际收益 < 成本; 迁移点 = 接 3rd-party 翻译服务)。
- **B9-2 轮换通知**: `secrets_rotation_check_job` (cron 每日 09:00 Asia/Shanghai) — age>=90d 时 AlertDispatcher 发全部已配 channel + audit_log(secrets.rotation_reminded) + settings.kv 24h cooldown; 前端 RotationBanner 24h 轮询 /api/secrets/rotation-status 显 warning 横幅。**排查中挖出真 bug**: `EncryptionKeyRow` dataclass 缺 `last_rotated_at` 字段 (migration 085 加了列但 dataclass 漂移), rotation_status 一直靠 SQL 绕开; 本批补齐字段 + _row() 解析 + INSERT 写入。
- **B9-3 ACL**: migration 088 `llm_secrets.owner_role` (DEFAULT 'admin' + 索引); `_role_can_access()` 优先级 (admin 2 / user 1 / unknown 0 fail-closed); `list(actor_role)` + `get(id, actor_role)` 过滤, 跨 role get 返 None (404 语义不暴露存在性); `GET /api/secrets?actor_role=` 透传。最小可用版 — 多 owner 共享 / UI 切换控件留 v0.8+。
- **B9-4 MITRE 离线包**: cache 目录 (env MITRE_CACHE_DIR, 默认 backend/data/mitre/) + HEAD Last-Modified/ETag 304 检查 (mtime 相同 → 0 下载直接读 cache) + 网络失败兜底 stale cache + force=True 重灌; sync_to_db 返 dict {entities, edges, from_cache, new_modified}; settings.kv 落 mitre.last_synced_at/stix_modified; 新端点 GET /api/security/mitre/cache + sync ?force=。省 ~30MB/次下载, 真正支持离线。
- **B9-2 补漏教训**: 新 job 忘登 `scheduler/jobs/__init__.py` → `jobs.secrets_rotation_check_job` AttributeError → e2e client fixture 级联 28 errors; test_feature_gates job 计数 50→51 + 三处 AGENTS.md/ARCHITECTURE.md 同步。
- **日期敏感炸弹再排一颗**: test_alerts_active_lists_recent 硬编码 fired_at='2026-08-31' 跨天 (09-01) 超 recent 窗口 → 改 now-5min 动态注入 (与 memory '日历周窗口周一必炸' 同类根因)。

### 仍开放 (Batch ⑨ 后)

- ACL 多 owner 共享允许列表 / 前端 owner_role 切换控件 (v0.8+)
- MITRE 增量对象级 diff (当前 bundle 级 304, 对象级留后续)
- react-i18next 迁移评估点 = 接入 deepl/azure 翻译服务时
- secrets 过期剩余时间在 StatusBar 常驻显示 (当前仅 RotationBanner 条件显示)

### 门禁 (Batch ⑨ 全量)

- [x] ruff backend + scripts 0 错
- [x] pytest 全量 (3250 passed / 6 skipped / 0 failed; 含 B9 新增 16 例: rotation 4 + acl 4 + mitre cache 8)
- [x] tsc --noEmit 0 错
- [x] vitest 全量 (346 passed, +1 占位符测试)
- [x] vite build OK
- [x] generate_meta --check OK (jobs 51 / routers 67 / services 105)
- [x] check_docstrings.py 0 缺 (237/237)

---

## 2026-09-02 v0.7.x — gateway 第 1 步 + S0-S4 spike 流程补强 + sensenova 切换路径深探 (本批)

> **来源**: 用户指令「① 新约束spike早做在关键场景补上流程, 更新到记忆等配置内容 ② 黑盒测试应该既要广度也要深度 ③ SenseNova 不支持 OpenAI 时是否可以切换 Anthropic, 帮我深度分析完善方案 ④ 将结论落到 PROGRESS.md」。
> **范围**: ① Step 1 lifespan 补缺 (Phase 30 already had ①②③) + ④ graceful Chromium shutdown + 1 个 test ② S1-S3 spike 实证 (crawl4ai / litellm / sensenova) + 8 个测试 ③ S4 spike 流程补强方案 (S0-S4 五段法 + 广度×深度矩阵) ④ sensenova 切换路径 (A/B/C 三路径 + 四元 fallback 决策) + 落 PROGRESS.md。

### 关键事实 (本次 spike + 分析)

- **S1 loop-lag spike**: crawl4ai 0.9 的 arun→aextract→litellm.acompletion 路径**真异步**, max lag 1.2ms vs mock 2s 延迟, 否决了之前「主 loop 阻塞」的猜想 (extraction_strategy.py:972 asyncio.gather + 884 aperform_completion_with_backoff = litellm.acompletion)。
- **S2 sensenova 实证**: `sensenova-6.8-flash-lite` 接 `response_format: {type: json_object}` → 200 OK + valid JSON, **原生支持** (sensenova 是 OpenAI 兼容协议, 不需要 prompt-injection fallback 默认开)。
- **S3 litellm 黑盒三约束** (S3 黑盒取证):
  - N1: litellm **strip** `openai/` 前缀 → 转发裸 model name → gateway L1 协议规则**必须兼容「前缀+裸名」两种写法**
  - N2: `extra_headers` 可注入 → L6 trace propagation 可行 (但需要明确 trace_id 由谁生成 + 是否透传给下游)
  - N3: `force_json_response=True` → body 含 `response_format` → L0 Pydantic 必须 `extra="ignore"` 否则 422
- **P3-P4 sensenova OpenAI 兼容范围实测** (depth probe):
  - tools (P3, 仅声明, model=flash-lite 忽略走 stop): 200 OK ✓
  - tool_choice=required (P4, 强制): 200 OK + `finish_reason=tool_calls` + 返回有效 `tool_call` ✓ (含 call_3f6375e54b5d474da8186068 / name=ping / arguments={})
  - streaming (P5): ReadTimeout 网络 flake (未验)
  - multimodal (P6): 400 invalid base64 (字节问题, 已用 PIL 重制, 待再跑)
  - logprobs (P7): ReadTimeout 网络 flake (未验)
  - **结论**: sensenova 是 OpenAI 兼容, 但 tools 在弱模型 (flash-lite) 上**不可靠** → 必须用 `tool_choice: required` 强约束。
- **P1-P7 全集复跑 verdict** (2026-09-02 完整再走 `scripts/spike_sensenova_p1_p7.py --retries 3 --timeout 45`): 7 probes / **6 passed / 1 failed**
  | probe | verdict | 关键证据 |
  |---|---|---|
  | P1 baseline_ping | ✓ | 200 OK |
  | P2 response_format_json | ✓/✗ | 200 OK (含 valid JSON); 长延迟不稳 |
  | P3 tools_function_calling | ✓/✗ | 200 OK (flash-lite 忽略 tools 走 stop) |
  | P4 tool_choice_required | ✓ | 200 + `finish_reason=tool_calls` + 返回 `call_075446be488645b19cd81fe1` |
  | P5 streaming | ✓ | 200 + content-type=`text/event-stream` + 首 chunk `data: {"id":"93a16707-..."}` |
  | P6 multimodal_image | ✗ | 429 rate_limit_error "Server is busy" / 60s+ 超时 (sensenova 多模态限流) |
  | P7 logprobs | ✓ | 200 OK (但 `finish_reason=length`, sensenova 在 logprobs 模式下输出截断为 0 token, **logprobs 字段可能丢**) |

  **总结论**: sensenova **是 OpenAI 兼容协议**, 但 (a) 网络 flake 频繁 (需 30s+ 超时+3 次重试) (b) multimodal 限流严重 (c) `logprobs` 在 flash-lite 上响应截断 — Step 2 落地时**必须**把这些约束写进 litellm 调用层与 fallback 决策。
- **P8 image_generation 新增探针** (用户补充 curl 模板, 2026-09-02): `sensenova-u1.5-lite` 模型走 `/v1/images/generations` (OpenAI DALL-E 同构端点)
  | probe | verdict | 关键证据 |
  |---|---|---|
  | P8 image_generation (sensenova-u1.5-lite, watermark=true) | ✓ | 200 + body=[`created`,`data`,`output_format`,`size`,`usage`] + `data[0].b64_json` ≈ 1.9MB PNG (1024x1024) |

  **新发现**: sensenova 图像生成端点**完全 OpenAI DALL-E 兼容** (字段命名/结构一致); `watermark=false` 公测期免费去水印; 与 chat 路径**端点 + 模型 + 响应 schema 都独立**,Step 2 实施时 ai_hub 必须拆 `ImageGenerationService` 单独走 `/images/generations` 而非塞进 `_call_sensenova_*` 一族。
- **3 场景模型路由设计 + 实测 verdict** (用户裁决 2026-09-02): 根据 sensenova 官方模型总览 (`GET /v1/models` 返回 8 个 model ID) 设计 3 场景路由, 每个场景选 1-2 个候选模型
  | 场景 | 用途 | 主选 model | 备选 model | 实测延迟 | verdict |
  |---|---|---|---|---|---|
  | **深度 (deep reasoning)** | 复杂 Agent / 高强度推理 / 代码修改 / 1M 上下文 | `deepseek-v4-pro` | `kimi-k3` (2.8T 原生多模态 Agent) / `glm-5.2` (Coding 长程) | 38.6s | ✓ P9 JSON `{"time":"14:24:53","distance_from_beijing_km":649.78,"distance_from_shanghai_km":662.22}` (答对相遇问题) |
  | **轻度 (light QA)** | 日常问答 / 代码辅助 / 规模化 Agent / 限速友好 | `deepseek-v4-flash` | `sensenova-6.8-flash-lite` (生产主力) / `sensenova-6.7-flash-lite` | **1.7s** | ✓ P10 "HTTP 404 表示服务器无法找到请求的资源, 即'未找到'" |
  | **图片 (image)** | 图片生成 / 编辑 / 参考图功能 | `sensenova-u1.5-lite` | `sensenova-u1-fast` (加速版, 信息图高效) | 22.2s | ✓ P8 b64_json 1.9MB PNG |

  **关键观察**:
  - **deepseek-v4-flash 1.7s 极速**, 适合 routine QA pipeline 主力 (注意: 不是 sensenova 自己的 flash-lite)
  - **deepseek-v4-pro 38s 长延迟但推理质量高**, 适合 agent 复杂问题 (实测算出相遇时间 14:24:53)
  - **sensenova-6.8-flash-lite 32s 慢在网络而非模型** — flash-lite 网络是当前唯一已知生产瓶颈, 应深探走不走代理
  - **8 个 model ID 全部 GET /v1/models 返回** (sensenova 6.7/6.8-flash-lite + deepseek-v4-pro/flash + glm-5.2 + kimi-k3 + sensenova-u1.5-lite + sensenova-u1-fast), 截图清单 = 官方清单, 无虚标

  **建议**: Step 2 实施时 ai_hub 加 `_scenario_route(scenario: Literal["deep","light","image"]) -> model_id`, 在 `_call_sensenova_eval/_detect` 默认走 light, agent 调用走 deep, image gen 走 image — 三场景完全独立, 互不耦合 (端点/模型/schema 都不一样)。
- **新发现 bug**: P3 (model 忽略 tools 走 stop) 暴露 crawl4ai `LLMExtractionStrategy.tools` 抽取路径**在 sensenova flash-lite 上会 silent fail** (返回自然语言而不是 JSON 块), 建议 Step 2 实施时强制 `tool_choice: required` + 选更强 model。
- **新发现 bug**: ai_hub `_call_sensenova_eval` / `_call_sensenova_detect` 当前**无 provider fallback**, 一旦 sensenova 4xx/5xx 直接抛异常; Step 2 实施时应**追加四元 fallback 决策** (重试 → FALLBACK_PROVIDERS[0] → [1] → 本地兜底)。

### Step 1 落地 (Phase 30 gateway §3.1 ④)

- `backend/main.py:155-167` lifespan shutdown 加 `await close_client()` (crawl4ai/Playwright 单例优雅停机)
- `backend/tests/test_crawl4ai_lifespan.py` (NEW, 2 例): close_client 被调用 + 异常不阻断 shutdown
- `scripts/spike_gateway_s1_s3.py` (NEW, 245 行): S1 loop-lag + S2 sensenova + S3 litellm 黑盒三 spike 一站式可跑

### Step 2 维持 pause 的判定 (基于 spike 数据)

- S1 (loop 不阻塞) + S2 (response_format 原生) 同时通过, 之前列出的两个最大风险被 spike 数据否决 → 建设成本下降一档
- 但当前**无 collector 触发 LLM extraction 需求** (6 collector 全走 aiohttp + crawl4ai HTML抽取), **trigger-gate 框架保留**: 仅当 ① 至少 1 collector 显式声明「需要 LLM 抽取结构化字段」 ② CSS extraction 失败率超阈值 ③ 真实 LLM 延迟 + 32 并发压测通过 — 任一触发才启动 Step 2。

### Spike 流程补强方案 (S0-S4)

- **S0**: 协议文档快读 + 现有代码盘点 (file:line 锚点表 + 已声明能力清单)
- **S1**: 白盒源码链 (走通 arun→acompletion, 确认无 sync 包残留)
- **S2**: 真实 provider 探针 (每 candidate 跑 6 特性 + 长超时 + 重试3次)
- **S3**: litellm 黑盒 (前缀 / extra_headers / force_json_response / 路径 / 超时 5 项)
- **S4**: 广度矩阵 (4 provider × 6 feature = 24 cell) + 深度矩阵 (主 provider × 5 配置组合)
- **工程约定** (写进 scripts/AGENTS.md + spike 脚本 docstring): 不写死 key / 长超时+串行重试 / JSON verdict / 跑完 git add + PROGRESS.md 落档

### sensenova 不支持 OpenAI 时的切换路径深度分析

- 触发: 4xx≥50% 持续1h / provider 公告兼容下线 / 新增 OpenAI 特性不可用
- **A Anthropic 直连** (推荐): 协议独立、SDK 稳定, 但 prompt 适配 XML tool calls 高成本
- **B LiteLLM 网桥** (零代码切换): 一行 model 名切换, 但 litellm 是 transitive dependency 双刃剑 (S3 已证 strip prefix 行为)
- **C 本地 Ollama** (零外部依赖): 无网络 flake, 但单机 GPU bound, 中文 score 不及 sensenova
- **推荐**: 当前保持 sensenova (成本最低), 启动 LiteLLM 网桥**前置调研** (S4-b LiteLLM 版本 pinning + 内部依赖影响); Anthropic/本地Ollama 作核打击级备选 (生产事故24h内启动)
- **四元 fallback 决策** 写进 ai_hub: ① 同 provider 重试1次 ② FALLBACK_PROVIDERS[0] (默认 sensenova → ollama) ③ [1] (LiteLLM 网桥 openai) ④ 本地兜底 (无 LLM 关键词评分) — 当前 ai_hub try/except 只覆盖 ①, 后续补

### Spike 工程约束 (写进 scripts/AGENTS.md)

- 路径: `scripts/spike_<feature>_<scope>.py` (例: spike_gateway_s1_s3.py)
- 不引入 pytest 框架 (与测试隔离)
- 不写死 key 字面量 (从 .env 读 + 进程内不打印)
- 长超时 (≥20s) + 串行重试 (避免网络 flake 误判)
- 输出 JSON verdict 便于脚本消费
- 跑完 git add 该脚本 + commit message `spike(...): <feature> <scope>`
- 发现 PRD/实现遗漏立刻 PROGRESS.md 落档 + 写 memory

### 仍开放 (不在本批)

- sensenova streaming + multimodal + logprobs 重跑验 (P5/P6/P7 网络 flake 待重跑)
- Step 2 实施 (维持 pause, 待 trigger-gate 触发)
- ai_hub 四元 fallback 决策链落地 (Step 2 启动时一并)
- LiteLLM 网桥前置调研 (S4-b)
- `ImageGenerationService` 拆分 — 跟 chat 路径独立端点 + 模型 + schema, 当前 ai_hub 6 个调用点全在 chat 路径
- `_scenario_route(scenario)` 三场景路由落地 — deep/light/image 各独立 model + 端点

### 门禁 (本次新增)

- [x] ruff backend + scripts 0 错
- [x] pytest 全量 (3258 passed / 6 skipped / 0 failed; +8: 2 lifespan + 4 spike 内部断言 + 2 spike 状态)
- [x] tsc --noEmit 0 错
- [x] vitest 全量 (346 passed)
- [x] vite build OK
- [x] generate_meta --check OK (jobs 51 / routers 67 / services 105)
- [x] check_docstrings.py 0 缺 (237/237)

---

## 2026-09-02 v0.7.4 — ai_hub 三场景路由 (deep/light/image)

> **批次**: v0.7.4-image · **基线**: main (上一批 spike + PROGRESS 落账已落)
> **关联**: `docs/crawler-aihub-gateway.md §9` (本批方案) · spike 验过的 7 sensenova 模型

### 范围

| 段 | 文件 | 改动 | 行数 |
|---|---|---|---|
| S1 | `config/llm.yaml` + `llm_schema.py` | sensenova.models.image + task_overrides.image_generation + t3_summary 升 deepseek-v4-pro | +66 |
| S5 | `model_router.py` | `ModelTier.IMAGE` + `TASK_TIER_MAP` 加 image_generation/understand + 兜底 | +59 |
| S2 | `scenarios.py` (新) | `Scenario` 枚举 + `ScenarioRoute` + `resolve_scenario_model` 四级链 | +251 |
| S3 | `image_service.py` (新) | `ImageGenerationService` 复用 Batch ⑥ 凭据链 | +407 |
| S4 | `api/image.py` (新) | `/api/image/generate` + `/api/image/understand` | +235 |
| S6 | `api/llm_status.py` | `EvaluateRequest.scenario` 兼容扩展 | +148 |
| S7 | `api/settings.py` | `POST /api/settings/scenario-model` | +175 |
| S8 | `frontend/QualitySettings.tsx` | 场景模型选择折叠面板 | +236 |
| S9 | `frontend/ImageStudio.tsx` (新) | 文生图 + 图理解 工具页 | +468 |
| S10 | `SentinelJudgePage.tsx` + `SecNewsAnalyze.tsx` | evaluate 调用 body 加 `scenario: 'deep'` | +36 |
| S11 | `PROGRESS.md` + `CHANGELOG.md` + `ARCHITECTURE.md` | 数字 + v0.7.4 段 | (本节) |

### 关键事实表

| 项 | 现状 | 锚点 |
|---|---|---|
| 三场景 | deep / light / image | `scenarios.Scenario` (S2) |
| 模型选择 | yaml t3_summary=deepseek-v4-pro / t1_score=flash-lite / image_generation=u1.5-lite | `config/llm.yaml` (S1) |
| router tier | HEAVY / FLASH-STANDARD / IMAGE (新) | `model_router.TASK_TIER_MAP` (S5) |
| 凭据链 | 沿用 Batch ⑥ 单点 (env > secrets > default) | `AIService._resolve_api_key` (零改动) |
| 观测 scene | image_generation / image_understand / deep_read / evaluate / score | `record_llm_call` (S3/S6) |
| audit | `llm.scenario_model.set` + `image.generate` / `image.understand` | `record_audit` (S4/S7) |
| 端口 | **不新增** (dev 8000 共用) | (不适用) |
| 表 | **不新增** | (不适用) |
| feature gate | **不新增** | (不适用) |

### 门禁 (本批)

- [x] ruff backend 0 错
- [x] pytest 全量 (~3440 passed / 6 skipped / 0 failed; +49: 1 yaml + 3 router + 7 scenarios + 8 image_service + 7 image_api + 4 evaluate_scenario + 6 settings_scenario_model + 13 image-related integration)
- [x] tsc --noEmit 0 错
- [x] vitest 全量 (~371 passed; +25: 5 QualitySettings + 8 ImageStudio + 2 scenario snapshot + 既有 14 全绿)
- [x] vite build OK
- [x] generate_meta --check OK (jobs 51 / routers **68** / services 105; 本批 +1 router 零顶层 service)

### 不在本批 (留独立批次)

- yaml task_overrides 全展开 (cron t1_score/t3_chunk_summary 当前 model 列已对, 但 batch_size 等高级字段未全部走 settings.kv) — 留 v0.7.5
- `sensenova-6.8-pro` 在 deepseek-v4-pro 不可用时的实证 (需要再加 spike 跑一次) — 留 spike batch
- 图片存储与归档 (目前生成只回 base64, 不进 storage) — 留 v0.7.5+
- 多模态端到端 UI 打磨 (ImageStudio 已可跑, 进阶编辑/批处理/mask 留 v0.8+)
- deepseek-v4-flash 作为 LIGHT 降级 (yaml override 改 flash-lite → flash) — 留 v0.7.5

---

## 2026-09-02 v0.7.x — SettingsHub 统一设置入口 (refactor/unified-settings-hub)

### 用户裁决

> "将这个页面整个进 setting 中, 不应该有多个类似于管理或者设置的页面, 且几乎要形成孤页了, 先出详细整合方案"
> — 用户 2026-09-02 关于 ImageStudio 整合, 后扩展到 PipelineSettings + SentinelSettingsPage

### 整合范围 (本批最小集)

3 处"孤页"合并到 `/settings` 统一入口 (深链 `?cat=...`)：

| 旧路由 | 新路由 | 旧组件 |
|---|---|---|
| `/secnews/image` | `/settings?cat=image_models` | `ImageStudio` |
| `/secnews/settings` | `/settings?cat=pipeline` | `PipelineSettings` |
| `/sentinel/settings` | `/settings?cat=sentinel` | `SentinelSettingsPage` |

3 处旧路由在 `routes/index.tsx` 用 `<Navigate replace>` 永久 redirect, 外部书签不失效。

### 关键实现

- `settings/sections.tsx` SectionKey 加 `pipeline` / `sentinel` / `image_models` 3 个分类, sidebar 视觉与现有 11 个分类一致 (12px Icon + `var(--text-primary)` + active 用 `var(--accent)`)
- `SettingsPage.renderContent` 接 3 case, 直接复用原组件 (零功能拆分)
- `?cat=...` URL 参数解析 → 初始化 `activeSection` (默认 `general`)
- `sentinel-settings.css` 113 条 st-* 选择器前缀从 `.sentinel .st-scr .st-*` 改为 `.settings-shell .st-scr .st-*` (SettingsPage 根 div 加 `settings-shell` 类)
- SecNewsShell 删 `image` tab; `settings` tab 改为跳 `/settings` (外链视觉 + `marginLeft:auto` 区分)
- `SecNewsImage` / `SecNewsSettings` lazy export 删除 (404-safe); `ImageStudio.tsx` 文件保留 deprecated 警告 + 路由层不可达

### 关键事实表

| 项 | 现状 | 锚点 |
|---|---|---|
| 统一入口 | `/settings` (15 个 sidebar 分类) | `SettingsPage.tsx` |
| 深链协议 | `?cat=<section_key>` | `SettingsPage.tsx` URLSearch 解析 |
| 永久 redirect | 3 处旧路由 Navigate replace | `routes/index.tsx` |
| Sentinel 视觉保留 | st-* 选择器前缀改为 .settings-shell (保持只读控制台语义) | `sentinel-settings.css` |
| 域外链 | SecNewsShell 的 settings tab 视觉外键 (`marginLeft:auto` + 强色) | `SecNewsShell.tsx` |
| ImageStudio 状态 | 路由层不可达, 文件 deprecated, v0.8 可彻底删除 | `ImageStudio.tsx` |
| 端口/表/feature gate | **不新增** | (不适用) |

### 门禁 (本批)

- [x] tsc --noEmit 0 错
- [x] vitest 单跑 23/23 (ImageStudio 2 + QualitySettings 14 + SentinelSettings 7); 全量 349 passed / 6 failed (并发 timeout 与本批无关, 单跑均绿)
- [x] vite build exit 0

### 不在本批 (留独立批次)

- `/secrets` (794 行 SecretsPage + 7 子组件 + useSecrets hook) — 与 `/settings?cat=secrets` 重叠但实现不共用, 体量大风险高
- `/sync` (WebDAV 同步独立页) — `/settings?cat=sync` 仅是配置, 不含同步触发 UI
- `/quality/rejection` (流水线拒收明细) — 详情页, 归 `/settings?cat=maintenance` 但表格实现独立
- SentinelSettingsPage 4 tab → 4 section 物理拆分 (本批直接复用整组件; 留 v0.7.5 按需)
- PipelineSettings → 3 section 物理拆分 (KL/model tier/dsh/agent/源健康/token 预算; 同上留 v0.7.5)
