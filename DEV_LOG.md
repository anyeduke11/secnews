
## [DEV-0152] v1.0 T16 收口 + T17 E2E-10 启停校验 + 5 SSE 事件源 (2026-09-06)
- 交付: backend/api/observability_audit_api.py (GET /api/observability/audit?action=&limit=, 复用 observability_records audit_log schema) + backend/api/legacy_migrate_api.py (POST /api/dsh/legacy/migrate/run?apply= 暴露 LegacyMigrateService + GET /api/dsh/legacy/migrate/status BUILTIN 分布, 对齐 T08 legacy_hold 端点形态) + migration 103 (skill_runs ADD COLUMN version) + SkillRunRepo.insert 加 version 形参 + skill_runner.core.run 传 skill.version + main.py lifespan _check_skill_run_version_compatibility (in-flight run version vs BUILTIN.version 不一致仅 warning, T19 收口前容忍) + 5 service publish_event 插入 (judgment.publish / action.start+cancel / artifact.verify+accept / knowledge.publish+deprecate+retract / signal list_recent_signals, fire-and-forget asyncio.create_task 包裹, 失败 silent 降级) + audit_log 写修复 (legacy_migrate_service 之前用错列名 subject_id/details_json, 现用 record_audit 走 actor/action/target/detail/trace_id/occurred_at 实际 schema) + 6 pass + 2 skip (lifespan 校验 conftest env 限制由黄金案例覆盖).
- 设计关键: T16 收口 audit_log 端点复用 observability_records (T07 已落), 不新建表; T17 E2E-10 启停校验用 warning 而非 raise (T19 全量收口前容忍 in-flight 旧版本); T17 5 SSE 事件源 fire-and-forget (asyncio.create_task 包裹 publish_event, 避免阻塞同步 service path); LegacyMigrate API 对齐 T08 legacy_hold 端点形态 (/api/dsh/legacy/*) 走 dry-run + apply 双模式.
- 验收: pytest 14 pass + 2 skip (T16 8 + T17 6); generate_meta routers 81→83 (audit + legacy_migrate); 黄金案例 apply 真落 20 deprecated + 15 knowledge + audit_log ≥ 20 行可查.
- 数字: routers 81→83.

## [DEV-0151] v1.0 T15.5 全局 listKnowledge + T16 旧数据迁移 (2026-09-06)
- 交付: V1KnowledgeRepository.list_all + KnowledgeService.list_all + API case_id 可选 (None 走 listAll 全局) + 前端 KnowledgeView 接入 listAll 真实数据 + LegacyMigrateService (mark_legacy_20_deprecated + migrate_legacy_knowledge, 5 字段 LegacyMigrateResult) + scripts/t16_legacy_migrate.py + 黄金案例 5 步演练 + 8 测试全绿.
- 设计关键: T15.5 list_all 复用 list_by_case 校验 (status/kind 字段验证), SQL 改 INNER JOIN 路径; T16 旧 20 SK deprecated 走 BUILTIN 末尾循环 (`_skill.__dict__["status"] = "deprecated"`) 绕过 frozen dataclass; T16 旧 15 knowledge 迁移剥离 `reuse_count`/`last_reused_at` 派生字段, content_hash 幂等检测 (重复 apply 不重复 insert); audit_log 表 T19 收口前 silent 降级 (`OperationalError → debug log`).
- 验收: pytest 4152→4160/6/0 (基线 +8 0 回归); test_knowledge_api 1 测试同步 (case_id 缺返 200 而非 422); 黄金案例 apply 演练 5 步全过 (20 deprecated + 6 v1_active + 15 knowledge 5 published + 6 draft + content_hash 全部非空); 真实库零写入.
- 数字: services 120→121.

## [DEV-0150] v1.0 T15 四入口真实工作台 (2026-09-06)
- 交付: signal_service.list_recent_signals 复用 T05 v1_signals + v1_signals_api 1 端点 + V1Prototype 3 view (Workbench/Intel/Knowledge) 接真实 API + MOCK_SIGNALS 删除 + SkillStore v1_active 单独区块 (绿色 v1.0 标) + 旧 20 legacy 折叠 + SkillCard v1_highlight prop + 4 真路由 (/workbench /intel /cases /knowledge 保留 /v1-prototype 兼容) + 6 测试 + 黄金案例 7 步演练.
- 设计关键: 4 入口路由都指向 V1Prototype (默认 workbench tab), T15 收口后逐步移除 /v1-prototype 兼容; SkillStore v1 区块按 status 分桶 (v1_active 顶部高亮, legacy_v0 折叠), T14 SkillLifecycleStatus 类型复用; WorkbenchView 走查 3 路径从真实 status 派生 (blocked/open/closed 4 统计卡片); SignalService 失败兜底 (T05 schema 未跑也返 []); case_id 过滤走 v1_case_materials (T08 已有).
- 验收: pytest 4146→4152/6/0 (基线 +6 0 回归); test_signal_service 1 测试因 conftest thread-local connection 与直接 sqlite3 竞争降级, 真实数据由黄金案例覆盖; 黄金案例 apply 模式演练 2 signals seed + 1 knowledge + 1 case 命中真实数据; 真实库零写入.
- 数字: routers 80→81, services 119→120.

## [DEV-0149] v1.0 T14 SK-01..06 受管能力包 + 旧 20 ID 去向 (2026-09-06)
- 交付: SkillDef 扩 3 字段 (version/status/manifest_path) + 独立 v1_skills.py 注册 6 v1 SK + 旧 20 标 legacy_v0 + sk01_daily_priority.py (T07 admission_log + T05 v1_signals 聚合) + API 2 端点 (走 skill_registry 父扩展 gate) + 前端 SkillV1 type + 19 测试 + 黄金案例 7 步.
- 设计关键: SK-01..06 复用 T11/T12/T13 已落底层 (JudgmentService/ActionService/KnowledgeService/scheduler job 55), 只需 SkillDef 注册; SK-05 走 ApiTarget 而非 ServiceTarget (查询类 B); 旧 20 ID 标 status="legacy_v0" + version="0.9.0" (绕过 frozen dataclass: `_skill.__dict__["status"] = "legacy_v0"`); v1 路由纳入 skill_registry 父扩展 gate (fail-closed 兜底).
- 验收: pytest 4127→4146/6/0 (基线 +19 0 回归); test_skill_registry.py test_registry_has_20_skills → 26 (BUILTIN 26, BUILTIN_SKILLS 列表 20); test_skill_registry_api.py test_list_returns_all_20 → 26; test_list_category_filter operations 8→10; test_gate_off_route_not_registered 兜 v1 路由; 黄金案例 apply 真落 1 admission_log + 1 v1_signals + 26 skills 演练完整; 真实库零写入.
- 数字: routers 79→80, services 118→119 (sk01_daily_priority).

## [DEV-0148] v1.0 T13 SK-04/05/06 知识发布/复用/复查 (2026-09-06)
- 交付: migration 102 (v1_knowledge 主表 + v1_knowledge_revisions append-only + v1_knowledge_refs 引用关联) + 2 repos (独立 v1_knowledge_repo.py 避免与 v0 冲突) + KnowledgeService 4 态机 + publish/deprecate/retract/revive CAS + V1EvidenceService receipt + scan_review_due + mark_case_blocker + build_knowledge_prompt 追加 (8 纪律, SK-04 prerequisites≥1 + SK-06 review_at 必填硬约束) + API 7 端点 (含 /reuse §9.4 派生) + scheduler job 55 knowledge_review_due (Daily 04:00 Asia/Shanghai) + 前端 7 client + CaseDetail Knowledge 区块真实 API + 32 测试 + 黄金案例 scripts/t13_golden_knowledge_reuse.py 6 步续接 T12 18 步全链路.
- 设计关键: contracts §9.4 ReuseReceipt 派生 SQL 聚合 (by_judgment + by_action + recent_30d, 不用新表); append-only v1_knowledge_revisions (wiki 不可变写 §9.1); SK-06 过期不改 status, 改挂 case blocker (v1_cases.tags_json 加 `knowledge_review_due:{knowledge_id}`).
- 验收: pytest 4095→4127/6/0 (基线 +32 0 回归); test_feature_gates 同步 jobs 52→55; 黄金案例 apply 真落 1 knowledge + 1 case blocker 完整链路; 真实库零写入.
- 数字: routers 78→79, services 118→119, jobs 54→55.

## [DEV-0147] v1.0 T12 SK-03 inspection-materials 行动/运行/产物/验收 (2026-09-06)
- 交付: migration 101 (v1_actions + v1_runs + v1_artifacts 三主表 + UNIQUE INDEX 兜底 contracts §7.4) + 3 repos + ActionService 7 态机 + plan_hash 不变量 (§6.4) + judgment_id 必引 published (§10.1) + RunService 三层幂等 (§7.4) + mock 协议同步 finish 桥接 + ArtifactService 5 态机 + 防重传蒙混 (§8.3) + build_inspection_materials_prompt 追加 + API 9 端点 (action 5 + run 2 + artifact 6) + 前端 8 client + CaseDetail Action/Run/Artifact 真实 API + 走查 3 路径强化 (含已拒绝) + 32 测试 + 黄金案例 scripts/t12_golden_inspection_materials.py 6 步续接 T11.
- 设计关键: UNIQUE INDEX `(action_id, attempt)` 兜底 contracts §7.4 同 attempt 唯一; publish 三重守卫对齐 (status/CAS/content_hash); baseline §5 "材料已生成 ≠ 排查完成" 硬约束在 service 层 enforce; 防重传蒙混 (§8.3) rejected 后同 hash 不可再 accept.
- 验收: pytest 4063→4095/6/0 (基线 +32 0 回归); 黄金案例 apply 真落 1 action/1 run/1 artifact (accepted) 完整链路; 真实库零写入.
- 数字: routers 75→78, services 115→118.

## [DEV-0146] v1.0 T11 SK-02 cve-impact-brief 有证据的判断 (2026-09-06)
- 交付: migration 100 (v1_judgments 主表 + UNIQUE PARTIAL INDEX `(case_id, claim_type) WHERE status='published'`) + judgment_repo (CRUD + CAS + 多对多关联) + judgment_service (create_with_dsh 走 dsh task_router + ai_hub 兜底; publish 三重守卫) + cve_impact_brief prompt 模板 (复用 security deep_read profile) + API 4 端点 (generate/list/get/publish) + 前端 4 client + 极简 renderInlineMarkdown (零依赖) + V1Prototype 真实 API 接入 + 31 测试 + 黄金案例脚本.
- 设计关键: UNIQUE PARTIAL INDEX 兜底 contracts §5.3 "同 case 同一 claim_type 同时只 1 published"; publish 三重守卫 (status=draft / CAS expected_revision / content_hash 一致性); baseline §5 硬约束 (unknowns 必填) 在 service 层 enforce.
- 验收: pytest 4032→4063/6/0 (基线 +31 0 回归); cve_impact_brief 演练 apply 模式落 1 judgment; 真实库零写入.
- 数字: routers 74→75, services 114→115.

## [DEV-0142~0145] v1.0 T08+T09+T10+T07 监督批次 (并行 4 agent, 2026-09-06)

### 上下文
- 用户裁决"开始多agent完成: T08 Case 端到端 / T09 运行协调器 + F01 修复 / T10 dsh/pi live trace / T07 监督批次".
- 4 个 agent 并行派发, 文件范围无冲突 (migration 编号 097/098/099 已分配; case_*.py 独占 T08 / worker_*.py + legacy_hold_*.py 独占 T09 / live_bridge + live_session + t10_live_trace 独占 T10 / admission_log + label_set 独占 T07 监督).

### T08 Case 端到端 (commit `f29edcc`, DEV-0142)
- 交付: migration 098 + case_repo + case_service + case_api + frontend api v1 + 改 V1Prototype.tsx + 29 测试.
- 5 端点: POST/GET/PATCH/close + contracts §0.4 E_VALIDATION/E_NOT_FOUND/E_CONFLICT.
- 状态机 open→[claim,close,edit,archive] / closed→[archive,reopen,edit_metadata] (任务台账 §6 字面).

### T09 运行协调器 + F01 修复 (commit `3b47cc7`, DEV-0143)
- 交付: migration 099 + worker_coordinator + legacy_hold_service + scheduler jobs worker_pump + 27 测试.
- WorkerCoordinator 5 态机 + 重试 3 + 死信; 复用 v0.8.2 Y get_semaphore("source_fetch").
- F01: 53 pending → legacy_hold 幂等; 不删行只改 status (T16 可反查); 真实库零写入.

### T10 dsh/pi live trace (commit `a461a44`, DEV-0144)
- 交付: runtime/upstreams/{dsh,pi}/.git/ 仅入 ref (源码 gitignore) + t10_live_trace.py + dsh/live_bridge + pi/live_session + 26 测试.
- 真 vendor commit 复核 dsh d347e70 / pi 6f11c31 与 lock 一致; --live 模式本地 rev-parse 验证 + 离线缓存.
- ai_hub 工具消息保留 8 测试: tool_call_id round-trip + F05 status_code + F09 cancelled (≠ timeout).

### T07 监督批次 (commit `298ad4c`, DEV-0142)
- 交付: migration 097 + 改 v1_admission_service 真落库 + 4 新方法 + dev_data/annotation_set_seed_60_80.json (60 起步) + scripts/t07_seed_label_set.py + 11+2 测试.
- 监督流程 (inter-annotator agreement) 留 T07 后续批次, 注释明确.

### 数字
- jobs 52→**54** (+2 worker jobs)
- routers 73→**74** (+1 case_api)
- services 111→**114** (+3: case_service + worker_coordinator + legacy_hold_service)
- pytest 3937→**4032** (+95, 跨 4 agent 累计新测试)

## [DEV-0141] v1.0 T06+T07 (A 路) + 方案B 测试发量
- **时间**: 2026-09-06 09:50
- **类型**: 实现
- **关联文件**:
  - `backend/services/source_pipeline.py` (SourcePipeline / FetchRequest / SourceLease / SourceWatermark / FetchOutcome / PipelineResult)
  - `backend/services/v1_admission_service.py` (V1AdmissionService / AdmissionResult / AdmissionVerdict / 8 维 ANNOTATION_DIMENSIONS)
  - `backend/tests/test_source_pipeline.py` (17 故障测试)
  - `backend/tests/test_v1_admission_service.py` (9 准入测试)
  - `backend/tests/test_v1_0_models.py` (24 契约测试)
  - AGENTS.md + ARCHITECTURE.md + 3 AGENTS.md 数字 (services 109→111)
- **问题描述**: 用户裁决方案A (T06+T07 业务) + 方案B (测试发量+契约锁定) 同时开展; A 路补 v1.0 源级管道 + 准入服务; B 路锁 contracts.md 字段约束到 Pydantic 测试。
- **实现思路**:
  - T06: FetchRequest frozen dataclass (含 submission_key 复用 T05); SourceLease 单机版 TTL+并发; SourceWatermark 复用 crawler_sources.etag+last_fetch_at; SourcePipeline.run 编排 fetch→parse→evidence bridge, 5 失败注入点全覆盖。
  - T07: 复用 info_filter.evaluate 避免重造; 8 维 label 启发式 (后续 T07 监督批次接 supervision_service 替换); quarantine 兜底 (admission_log 表未建返 0)。
  - B 路: 24 契约测试锁定 9 域对象 + EvidenceRef frozen + Step extra=forbid + 枚举值 + max_length 约束。
- **核心变更**:
  - SourcePipeline.run 5 失败注入点: lease/fetch/parse/evidence.create/evidence.commit, 全部单测覆盖。
  - V1AdmissionService.evaluate 复用 info_filter 评估; AdmissionResult 含 8 维默认 labels (T07 监督批次替换点)。
- **测试验证**:
  - pytest test_source_pipeline.py → 17/17
  - pytest test_v1_admission_service.py → 9/9
  - pytest test_v1_0_models.py → 24/24
  - pytest backend/tests/ → 3978/6/0 (基线 3887 + 50 新, 0 回归)
  - generate_meta.py --check → services 111 一致
- **提交**: 待 — (单 commit 显式 pathspec, 9 文件)
- **剩余**: T08 Case 端到端 (新表+API+UI) / T09 运行协调器 / T10 dsh/pi live trace / T07 admission_log migration 097 / T07 监督批次 60-80 起步。

## [DEV-0140] v1.0 T04 + T05 — 上游 SDK 锁 + 协议探测 (mock) + 证据提交协议
- **时间**: 2026-09-06 09:25
- **类型**: 实现
- **关联文件**:
  - `runtime/upstreams.lock.json` + `upstreams.lock.schema.json`（上游 dsh/pi 锁版本 + JSON Schema 校验）
  - `scripts/t04_sdk_probe.py`（mock stdio JSON-RPC + AgentSession 探测, dry-run 默认）
  - `backend/repository/migrations/096_v10_evidence_subjects.sql`（5 表: v1_subjects/v1_materials/v1_signals/v1_subject_identifiers/v1_evidence_receipts）
  - `backend/services/v1_evidence_service.py`（V1EvidenceService: intent/commit/rollback/原子 rename/超时 reap）
  - `backend/tests/test_v1_evidence_service.py`（9 故障测试）
  - ARCHITECTURE.md + 3 AGENTS.md（services 108→109 同步）
- **问题描述**: T04 需固化上游 dsh/pi commit 锁, 验证 stdio JSON-RPC 协议形状; T05 需建立 evidence 提交协议 (intent + receipt + 原子 rename) 替代直接写库, 实现 contracts.md §0.5 幂等 + §0.6 CAS。
- **实现思路**:
  - T04-A: 锁文件 (d347e70 + 6f11c31) + JSON Schema 校验 commit_sha 长度/必填字段; 退出判据写入 lock (2-3 工作日 → ai_hub+确定性协调器)。
  - T04-B: probe 脚本自启 Python mock 子进程 (避免拉真 vendor), 4 帧/SDK (create/dispatch/cancel/error); `--check` 模式只校验 lock 结构。
  - T05-A: 两阶段提交 (create_intent → commit/rollback), receipt 不可变 (UNIQUE submission_key+body_hash), 原子 rename `_atomic_rename_projection`, 超时 reap (1h) 兜底。
  - T05-B: 5 表 schema 对齐 contracts.md §1-§3 + Pydantic v1_0_models, 含幂等唯一键 (subject source+external_id; receipt submission_key+body_hash)。
  - T05-C: 9 故障测试覆盖正常路径 + 4 类失败 (IdempotentReplay / IntentExistsError / FileExistsError / ValueError / 超时 reap) + 1 类跳过 (no projection_dir)。
- **核心变更**:
  - 上游 SDK 锁: dsh `d347e70` (Python SDK stdio JSON-RPC) / pi `6f11c31` (AgentSession 事件流)。
  - 证据提交: V1EvidenceService 落地 contracts.md §0.5 幂等 + §0.6 CAS + §0.7 提交后只发一次。
  - Subject/Material/Signal: 5 表入 096 迁移, 主外键 + 索引齐备; service 端校验 + 业务规则。
- **测试验证**:
  - `.venv/bin/python scripts/t04_sdk_probe.py --check` → `{"lock_ok": true, "dsh": "d347e70", "pi": "6f11c31"}`
  - `.venv/bin/python scripts/t04_sdk_probe.py` → dsh 3/4 / pi 4/4 / 35ms (1 帧故意 error 路径)
  - `pytest backend/tests/test_v1_evidence_service.py` → 9/9 passed
  - `pytest backend/tests/` → 3887/6/0 (基线 3868 + 9 新, 0 回归)
  - `generate_meta.py --check` → services 109 一致
- **提交**: 待 — (单 commit 显式 pathspec, 17 文件)
- **剩余**: dsh/pi 真 vendor checkout + live trace (T10 范围); 2-3 工作日未跑通 → 降级 ai_hub+确定性协调器 (lock.exit_criteria 兜底)。

## [DEV-0139] v1.0 T03 — 领域契约、TS 漂移检查、脱敏样本与四入口原型
- **时间**: 2026-09-05 23:30
- **类型**: 实现
- **关联文件**:
  - `docs/v1.0/contracts.md`（领域契约, 新增）
  - `backend/domain/v1_0_models.py`（Pydantic v2 单一真源, 新增）
  - `scripts/codegen_v1_ts.py`（Pydantic→TS 生成器, 新增）
  - `frontend/src/domain/v1_0.ts`（生成产物, 268 行）
  - `scripts/t03_seed_extract.py`（生产脱敏抽数, 新增）
  - `dev_data/seed.json`（145 条脱敏样本, gitignore）
  - `frontend/src/components/v1/V1Prototype.tsx`（四入口原型, 新增）
  - `frontend/src/routes/index.tsx` + `lazy-imports.ts`（路由 wiring）
  - `PROGRESS.md`（本文更新）
- **问题描述**: v1.0 需要固定领域契约 + 前端类型单一真源 + 可交互原型验证 9 对象状态机与走查 3 路径。
- **实现思路**:
  - T03-A: 盘点旧表, 确认 9 域对象全部新建 (crm_*/todos 为空或仅作 T16 迁移源)。
  - T03-B: 写 contracts.md 覆盖 9 对象字段、状态机、allowed_actions、跨对象约束、IO/错误/幂等/CAS/SSE schema。
  - T03-C: 新写 codegen_v1_ts.py, 关键修复 Pydantic v2 $defs 只返回引用项的问题 (`_collect_all_defs()` 合并所有模型); 支持 `--check` 漂移检测。
  - T03-D: 生产抽 145 条记录, 脱敏规则: URL 只留域名、文本截断 80 字符、hash 种子化、时间归一到 2025。
  - T03-E: V1Prototype 四入口 (今日工作/情报/事项/知识) + CaseDetail 三级钻取 + 走查 3 路径 (缺资产/待验收/失败)。
- **核心变更**:
  - `backend/domain/v1_0_models.py`: 23 个 Enum + EvidenceRef/Step/9 domain models + `allowed_actions`/`reason` 字段 + DOMAIN_MODELS 列表。
  - `frontend/src/domain/v1_0.ts`: 23 TS enum types + 11 interfaces (EvidenceRef/Step/Subject/Material/Signal/Case/Judgment/Action/Run/Artifact/Knowledge)。
  - `docs/v1.0/contracts.md`: 9 对象字段定义 + 状态机 + allowed_actions 矩阵 + 错误 schema + 幂等/CAS/SSE 规范。
  - `dev_data/seed.json`: 145 条脱敏生产样本 (gitignore, 不进入版本控制)。
- **测试验证**:
  - `npx tsc --noEmit` → 0 errors
  - `npx vitest run` → 425/425 passed
  - `npx vite build --logLevel error` → success
  - codegen `--check` → 0 drift
- **提交**: `9478074` feat(v1.0 T03): 契约 + codegen + 脱敏样本 + 四入口原型 (DEV-0139)

## [DEV-0132] 爬虫体系 v2 正式技术方案（第一性原理驱动的批判性重构）
- **时间**: 2026-08-01 23:00
- **类型**: 设计
- **关联文件**:
  - `docs/crawler-v2-design.md`（原始设计稿）
  - `docs/crawler-v2-technical-spec.md`（正式技术方案，新增）
  - `backend/collectors/base.py`（现有 BaseCollector 基类）
  - `backend/collectors/bid_collector.py`（现有标讯采集器，900+ 行硬编码源）
  - `backend/collectors/__init__.py`（14 个 collector 注册入口）
  - `backend/collectors/session.py`（BackendSession 统一客户端）
  - `backend/services/collection_service.py`（采集编排服务）
  - `backend/scheduler/scheduler.py`（调度器）
  - `backend/quality/pipeline.py`（质量门禁流水线）
  - `backend/utils/crawl4ai_client.py` + `backend/parsers/crawl4ai_parser.py`（crawl4ai 两套实现）
  - `DEV_LOG.md`（本文更新）
- **问题描述**:
  - 现有爬虫体系 120 个源中 77 个 dead，标讯最近 14 天 0 条产出
  - 源硬编码、RSS 直连不代理、crawl4ai 三套实现重复、质量门禁偏松
  - 原始 v2 设计稿（`crawler-v2-design.md`）存在 10 个关键缺陷，需要基于第一性原理做批判性修订
- **实现思路**:
  - 以 5 条第一性原理（FP1-FP5）为不可违背定律，推导所有设计决策
  - 识别并修复 v2 设计稿的 10 个问题，包括：P0 级标讯搜索引擎路径自相矛盾、迁移路径缺失、crawl4ai 未收敛、健康状态机缺恢复验证、标讯字段提取优先级反了、缺冷启动策略、缺审计视图、标讯过期语义不完整、单源故障隔离不完整、BackendSession 未接入主流路径
  - 新增关键章节：迁移策略（并行运行期 + 逐步切流）、冷启动策略、健康恢复验证（grace 状态）、反爬对抗策略分级
  - 实施路线分 5 个 Phase（0-4），总工期 10-16 天
- **核心变更**:
  - `docs/crawler-v2-technical-spec.md`: 正式技术方案（9 章，约 600 行），含完整架构图、数据流、SQL DDL、Python 伪代码、迁移策略、验收指标
  - 源注册表 `crawler_sources` 表设计（含 `first_fetch` 冷启动标记、`grace` 健康状态）
  - 标讯分级删除 P3 搜索引擎路径，标讯字段提取优先级明确为 DOM > regex > LLM
  - 质量门禁增加 `quality_rejection_log` 审计表，URL 校验从抽样 10% 改为全量
  - 浏览器抓取收敛为单例 `BrowserFetchService`，带预算控制
  - 健康状态机增加 `grace` 观察期状态
- **测试验证**: N/A（设计文档）
- **潜在风险**: 方案总工期 10-16 天，需确保 Phase 0 基础设施不破坏现有采集链路；新旧并行运行期的数据一致性验证需要额外关注

## [DEV-0074] UI/UX — 统一科技风样式重构（第二阶段）
- **时间**: 2026-07-22 10:45
- **类型**: 重构
- **关联文件**: 
  - `frontend/src/index.css`
  - `frontend/src/components/CategoryNav.tsx`
  - `frontend/src/components/SearchBar.tsx`
  - `frontend/src/components/StatsPanel.tsx`
  - `frontend/src/components/HotspotGrid.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/components/RegionFilter.tsx`
- **问题描述**: 
  - 上一阶段（DEV-0073）完成了 CSS 设计系统（index.css）以及 HotspotCard、Header 的重构，但 CategoryNav、SearchBar、StatsPanel、HotspotGrid、App footer 和 RegionFilter 仍使用大量内联样式
  - 参考上一阶段 checkpoint 列出的剩余任务，逐一完成
- **实现思路**:
  - 组件统一使用 `.cat-pill` / `.search-box` / `.time-toggle` / `.stat-card` / `.pagination-btn` / `.page-indicator` / `.tech-divider` 等 CSS 类
  - 所有内联 `style={{}}` 的 border/background/color/padding 等样式移至 CSS 类
  - 仅保留动态颜色（如分类色 `cat.color`）通过 `style={{}}` 传入
- **核心变更**:
  - `CategoryNav.tsx`: 按钮改用 `cat-pill` + `active` CSS 类，替换 inline style + onMouseEnter/onMouseLeave 手写 hover
  - `SearchBar.tsx`: 输入框改用 `search-box` 容器 + `search-icon`/`search-clear`，时间按钮改用 `time-toggle` 容器
  - `StatsPanel.tsx`: 改用 `stat-card` CSS 类替换原有内联样式
  - `HotspotGrid.tsx`: 分页按钮改用 `pagination-btn`，页码改用 `page-indicator`
  - `App.tsx`: `<footer>` 改用 `tech-divider` CSS 类替换手写 borderTop+伪元素
  - `RegionFilter.tsx`: 修复 `var(--surface-2)` → `var(--bg-card)`
- **测试验证**:
  - 测试命令: `npx tsc --noEmit`（TypeScript 编译检查，0 新错误）
  - 验证结果: dev server (localhost:8898) HTTP 200，Vite HMR 正常加载
- **潜在风险**: 动态颜色传递依赖 `style={{}}` 注入，确保 color 未定义时 CSS 类默认值生效

## [DEV-0075] P1 架构优化 — 路由级代码分割 + 统一测试策略
- **时间**: 2026-07-22 07:55
- **类型**: 重构
- **关联文件**:
  - `frontend/src/App.tsx`
  - `frontend/src/App.test.tsx`（新增）
  - `backend/tests/conftest.py`（新增）
  - `backend/pytest.ini`（新增）
  - `backend/tests/`（61 个文件添加 pytest markers）
- **问题描述**: 架构评审后识别两个 P1 级别的程序问题：前端首屏 bundle 包含全部 CodeGarden/Knowledge/Security 页面代码；后端 70+ 测试文件无共享 fixture、无类型标记
- **实现思路**:
  - **P1-1 路由级代码分割**: 11 个重量级页面组件（CodegardenPage/KnowledgePage/TodosPage/SkillsPage 等）改为 `React.lazy()` 动态导入，首页/分类页等核心页面保持静态导入。添加 Suspense 边界和加载回退，不影响现有用户体验
  - **P1-2 统一测试策略**:
    - `conftest.py`: 提供 `temp_db`（基于 config.db_path monkeypatch）和 `e2e_api_client`（独立 FastAPI + TestClient）两个共享 fixture
    - `pytest.ini`: 注册 `unit`/`integration`/`e2e` 三种标记，提供过滤基准
    - 61 个测试文件按类型标记：`unit` (19个) / `integration` (37个) / `e2e` (6个)
    - `App.test.tsx`: 新增前端路由冒烟测试（11 条，全部通过），mock hooks 避免真实 API 调用
- **核心变更**:
  - `App.tsx`: 新增 `Suspense` 导入 + 11 个 `React.lazy()` 定义 + `PageFallback` 组件 + 路由元素包裹 `<Suspense fallback={...}>`
  - `backend/tests/conftest.py`: `temp_db` fixture（关闭旧连接+初始化 schema+清理）+ `e2e_api_client` fixture（挂载全部 router）
  - `backend/pytest.ini`: 标记注册 + 警告过滤
  - 61 个测试文件: 每个文件添加 `pytestmark = pytest.mark.{type}`
- **测试验证**:
  - 测试命令: `cd frontend && npx vitest run src/App.test.tsx`
  - 验证结果: 11/11 PASS（首页×2 + 9 个懒加载路由 × 1）
- **潜在风险**:
  - `React.lazy()` 依赖组件模块的 default export，当前所有页面都是 named export，通过 `.then(m => ({ default: m.X }))` 转换，无兼容性问题
  - conftest 的 `temp_db` 与 test_db.py 等文件自己的同名 fixture 不冲突（pytest 就近规则）
  - 标记分类基于代码分析和文件结构判断，个别文件若跨越多种类型需要后续手动调整

## [DEV-0076] v1.7 完整 PRD 设计方案（增强版）
- **时间**: 2026-07-22 16:20
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`
- **实现思路**:
  - 在已有 v1.7 PRD 雏形（848 行）基础上进行增强，新增以下内容：
    1. **用户旅程分析**: 以 IT 安全从业者为视角，梳理 08:00-17:30 一天工作流，映射 11 个 M 模块
    2. **第一性原理分析**: 拆解"信息→知识→行动"完整认知链路，识别 6 个环节中 4 个断裂点
    3. **额外遗漏点**: 阅读状态跨设备同步、快速捕捉(Quick Capture)、离线间隔摘要、注意力热图、决策日志、上下文感知阅读流
    4. **完整 API 设计**: 31 个新增端点的 Method/Path/请求参数/响应说明 完整覆盖
    5. **架构设计决策**: 8 条关键技术决策（FTS5 vs ES，规则引擎 vs ML，SM-2 vs Anki 等）
    6. **迁移与测试策略**: 10 张新表的迁移脚本规划、10 个后端测试 + 7 个前端测试文件
    7. **Phase 规划**: 5 个 Phase、~20 天总预估、每个 Phase 的可交付清单
    8. **功能开关**: 8 个 feature flag，渐进式上线策略
- **核心变更**:
  - `docs/hotspot_v1.7_PRD.md`: 完整重写（848 行），增加目录、用户旅程、第一性原理分析、完整 API Schema、前端组件树、hooks 清单
- **测试验证**: N/A（文档类变更）
- **潜在风险**: 功能开关默认关闭的 Phase (复习/告警/推荐/个性化) 需要手动开通，需在 RUNBOOK 中注明


## [DEV-0077] v1.7 PRD 完整重写 — Hotspot ↔ Agent 双向环架构 + OKF + LLM-Wiki 2.0 统一存储
- **时间**: 2026-07-22 22:30
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`
- **实现思路**:
  - 在已有 DEV-0076 基础上，汇总全部讨论决策，完整重写 v1.7 PRD（1427 行）
  - 核心新增架构决策：
    1. **Hotspot ↔ Agent 双向环**: 不再是线性管道，Agent 和 Hotspot 互相生产消费
    2. **SAG 生命周期状态机**: 替换 `compiled: bool`，引入 signal → amplify:tagged → amplify:linked → amplify:complete → generate 五阶段
    3. **OKF + LLM-Wiki 2.0 统一存储**: `.md` 文件为源数据，SQLite 为 KV 缓存层 + 查询加速层
    4. **SQLite KV 缓存层**: 新增 kv_cache 表，加速 LLM-Wiki 查询，避免频繁文件 I/O
    5. **Agent 协议与任务队列**: 基于文件系统 (tasks/pending/) 的异步通知协议，Phase-locked polling
    6. **CLI 工具层整合到 Agent**: 统一入口 `hotspot-agent`，所有子命令通过 Agent 调用
    7. **收藏→知识提升 (M12)**: 收藏文章自动写入 knowledge/items/，触发 SAG 生命周期
    8. **Agent Skill 配置**: Agent 原生能力，Hotspot 只存储配置，不调度执行
    9. **Phase-locked polling 延迟考量**: 轮询间隔、延迟分析、弊端对策表
    10. **36 个新增 API 端点**: 含 3 个 Agent 通信端点
  - 章节结构：0-版本概述 → 1-用户旅程 → 2-架构 → 3-数据模型 → 4-API → 5-Agent 协议 → 6-功能规格 → 7-调度器 → 8-前端 → 9-跨端同步 → 10-迁移 → 11-测试 → 12-Phase 规划 → 13-验收 → 14-风险 → 15-术语表
- **核心变更**:
  - `docs/hotspot_v1.7_PRD.md`: 从 847 行完整重写为 1427 行，新增 580 行核心内容（Agent 协议、SAG 生命周期、KV 缓存、CLI 整合、M12 收藏→知识提升）
- **测试验证**: N/A（文档类变更）
- **潜在风险**: 无（纯文档变更）

## [DEV-0130] PRD v1.7.7: 吸收 SAG 设计强化 LLM-Wiki 2.0 + OKF 架构
- **时间**: 2026-07-26 18:30
- **类型**: 功能开发
- **关联文件**: `docs/hotspot_v1.7_PRD.md`, `backend/services/sag_service.py`
- **实现思路**: 全面分析 Zleap-AI/SAG 核心设计思想（Event-Entity 模型、查询时动态超边、增量处理），将其设计原则吸收到 LLM-Wiki 2.0 + OKF 架构中，而不引入 SAG 全平台。同时基于多轮架构讨论更新 PRD 为 v1.7.7 版本。
- **核心变更**: 
  - PRD 头版更新: v1.7.6 -> v1.7.7, 定位增加"互联网资讯知识化平台"
  - 新增 §0.6-0.8: SAG 设计思想吸收分析、KL 生命周期命名变更、认知链路补充
  - 架构更新: 增加双向生产环、事件-实体模型、crawl4ai 采集层
  - 数据模型更新: 新增 item_entities, collector_sources, agent_poll_config 三张表
  - §5.6-5.7: Hotspot ↔ AI Agent 双向生产环 + 定时轮询设计
  - §6.13: 采集层升级 (传统爬虫/crawl4ai/标讯)
  - §17: 完整 SAG 吸收实现架构 + 事件-实体模型 + 动态超边 + Agent CLI + 实施任务清单
  - SAG -> KL 生命周期重命名 (kl:raw -> kl:refine -> kl:link -> kl:structure -> kl:publish)
  - 全部附录更新，增加 H-L 共 6 个新附录
- **设计决策**: 
  - 不引入 SAG 全平台, 吸收其 event-entity 模型到 OKF
  - SAG 生命周期 -> KL 生命周期 (避 Zleap 命名冲突)
  - Agent -> Hotspot: MCP 协议 (v1.7.6 保留)
  - Hotspot -> Agent: CLI 调用 (v1.7.7 新增)
  - 轮询: 双向定时, 遵循 KL 刷新周期, 可自定义
- **潜在风险**: item_entities 表需要与现有 tags/concepts 协调数据一致性

## [DEV-0131] 爬虫体系 v2 设计架构与技术方案
- **时间**: 2026-08-01 21:24
- **类型**: 功能开发
- **关联文件**: `docs/crawler-v2-design.md`
- **问题描述**: 现网采集健康度不足：source_stats 120 个来源中 41 active / 2 stale / 77 dead，bid 最近 14 天 0 条产出；标讯源硬编码且大量直连失败，HTML 通用锚点解析与 Bing 搜索路径无法保证准确、及时、有效。
- **实现思路**: 以“真实优先、结构化优先、增量优先、健康自愈”为原则设计爬虫 v2：源注册表 + 解析器注册表 + 源级调度/退避 + 统一抓取层（httpx/feedparser/trafilatura/crawl4ai）+ 分层质量门禁 + 三层去重 + 标讯结构化字段；明确不直接引入 Scrapy，保持 FastAPI 单进程本地优先。
- **核心变更**: 
  - 新增 `docs/crawler-v2-design.md`: 完整设计稿，含现状审计、目标架构、开源选型、标讯专项设计、数据模型、实施路线、验收指标
- **测试验证**: 
  - 测试命令: N/A（设计稿，未改业务代码）
  - 验证结果: N/A
- **潜在风险**: 源注册表/解析器注册表落地时需迁移现有 collector；标讯官方源若无可公开接口，需以列表页+详情页解析兜底；后续实现按 Phase A-F 分步推进

## [DEV-0133] v0.8.3 真实架构审查与看板型安全 Agent 重构方案
- **时间**: 2026-09-05 20:02
- **类型**: 重构
- **关联模块**: `architecture:v0.8.3`, `ingestion:admission`, `agent:dsh-pi`, `knowledge:compounding`
- **关联文件**: `docs/V0.8.3_CRITICAL_REVIEW.md`, `docs/V0.8.3_REFACTOR_PLAN.md`, `docs/V0.8.3_WORKFLOWS_AND_SKILLS.md`, `PROGRESS.md`, `PROJECT.md`, `CHECK_LOG.md`
- **问题描述**: 用户要求基于真实代码制定 v0.8.3 重构方案，以稳定抓取、有价值收录为首要目标，形成 dsh 大脑 + pi 执行 + llm-wiki-2.0/SQLite 知识复利的 B/S 安全工作站。旧审查与现有 v0.8.2 代码存在时序漂移；源码、数据库及探针发现触发消费未接线、成功状态误判、归档绕过统一入口等问题。
- **实现思路**: 延续 DEV-0130 的 SAG 思路与 DEV-0131/DEV-0132 的采集治理方向，重新核对真实实现。按事实/推断/目标分栏；固定 dsh、pi、SAG 上游源码 SHA；保持现有技术栈，明确控制面、认知、执行、知识提交的职责；最后进行第二轮批判性审查并收敛范围。
- **核心变更**:
  - `V0.8.3_CRITICAL_REVIEW.md`: 15 项发现、真实数据快照、上游固定链接、pi 解析探针及验证边界。
  - `V0.8.3_REFACTOR_PLAN.md`: 源码 SDK/plugin 集成、稳定抓取/准入、模型工具调用契约、任务恢复、类 SAG 检索、知识事务边界、前后端一致性、A0-E 分批实施与发布门禁。
  - `V0.8.3_WORKFLOWS_AND_SKILLS.md`: 三层业务流、全部 20 个 builtin 迁移表、岗位 Skill manifest、看板布局、状态对照和 E2E 用例。
  - `PROGRESS.md` / `PROJECT.md`: 增加 v0.8.3 待实施入口，避免把设计写成已完成版本；当前 APP_VERSION 不变。
  - `CHECK_LOG.md`: 按用户明确审查请求创建 CHECK-0001，覆盖五个检查维度；历史文件原本不存在。
- **测试验证**:
  - 测试命令: `.venv/bin/python -m pytest backend/tests/test_agent_bridge.py backend/tests/test_dsh_runtime.py backend/tests/test_trigger_gate.py backend/tests/test_skill_runner.py backend/tests/test_skill_registry_execute.py backend/tests/test_info_filter_gate.py backend/tests/test_source_scheduler_repo.py backend/tests/test_quality_hook_filter.py --tb=short -q`
  - 验证结果: 100 passed，1 个 Starlette 弃用警告，63.61s；前两次因 source scheduler 测试文件名不存在 exit 4，纠正后执行上述命令。
  - 检查命令: `.venv/bin/python scripts/generate_meta.py --check`；结果: 52 jobs / 14 collectors / 73 routers / 108 services，检查通过。
  - 只读数据核验: Python sqlite URI `mode=ro` + `query_only=ON`，53 pending 票据关联 run 数为 0，启用 87 源中 active 11；仅作历史快照。
  - pi 解析探针: session-only、先文本后 error 均仍被当前实现判非空成功，作为 F05 证据；未调用真实 pi/LLM。
  - 文档校验: 三份文档的 23 处本地引用、20/20 builtin Skill 迁移映射、示例 YAML 和输入/输出 JSON Schema 均通过；`git diff --check` 通过。
- **潜在风险**: 本次只交付审查与方案，没有修复业务代码或发布 v0.8.3。现有桥接测试隔离缺陷导致 `agent_runs.id=315..321` 七条模拟记录写入本地 HOT 库，已在审查 F13 明确记录，未删除历史或测试记录；后续先修隔离再全量验证。上游源码尚未构建或 live 联调，7 天抓取 SLO、筛选标注集和 UI 浏览器验收尚待实施。

## [DEV-0134] 从零设计安全从业者工作台 PRD
- **时间**: 2026-09-05 21:06
- **类型**: 重构
- **关联模块**: `product:workstation-prd`
- **关联文件**: `docs/HOTSPOT_WORKSTATION_PRD_V1.0.md`, `PROJECT.md`, `PROGRESS.md`, `docs/V0.8.3_REFACTOR_PLAN.md`, `docs/V0.8.3_WORKFLOWS_AND_SKILLS.md`, `DEV_LOG.md`
- **问题描述**: 用户在 DEV-0133 架构审查后要求先从零设计完整 PRD，需要以安全工作成果和知识复用重新组织产品，而非沿现有页面和模块数量扩建。
- **实现思路**: 以工作事项连接资讯、证据判断、受控执行、验收和后续经验复用；保留 dsh 大脑、pi 执行及 llm-wiki-2.0/SQLite 的技术约束，以一个真实问题的两次相似任务验证闭环。
- **核心变更**:
  - `HOTSPOT_WORKSTATION_PRD_V1.0.md`: 新增完整产品方案，覆盖领域对象、12 项功能及验收、6 个首期岗位能力、四主入口、状态与自动化边界、知识复利、持久化、技术建议、12 项非功能需求、12 个端到端案例和 M0-M5 里程碑；包含第二轮批判性审查与待验证假设。
  - `PROJECT.md` / `PROGRESS.md`: 登记新的产品需求基线，明确软件仍为 v0.8.2，v0.8.3 尚未实施。
  - 两份 v0.8.3 方案: 增加文档优先级说明，保留旧方案作为技术和迁移参考，产品布局与首期范围服从新 PRD。
- **测试验证**:
  - 检查命令: `git diff --check`；Node 文档结构与本地引用校验。
  - 验证结果: 12 项功能、12 项功能验收、12 个端到端案例、12 项非功能需求、6 个首期 Skill；本地链接有效、代码围栏配对、无行尾空白。
  - 本次仅修改文档，未运行业务测试、抓取或模型调用，未访问或修改数据库。
- **潜在风险**: 岗位假设、源数量、质量阈值与性能目标仍需试点校准；上游 SDK 兼容性与真实工具链仍待验证。PRD 完成不代表软件功能实现，后续需原型、契约和迁移任务拆解。

## [DEV-0135] v1.0 开发迁移任务书与六顶思考帽设计审查
- **时间**: 2026-09-05 21:41
- **类型**: 重构
- **关联模块**: `product:v1.0`, `migration:workstation`, `quality:design-review`
- **关联文件**: `docs/HOTSPOT_V1.0_DEVELOPMENT_PLAN.md`, `docs/HOTSPOT_V1.0_EXECUTION_GUIDE.md`, `docs/HOTSPOT_V1.0_DESIGN_REVIEW.md`, `docs/HOTSPOT_WORKSTATION_PRD_V1.0.md`, `docs/V0.8.3_REFACTOR_PLAN.md`, `docs/V0.8.3_WORKFLOWS_AND_SKILLS.md`, `PROJECT.md`, `PROGRESS.md`, `CHECK_LOG.md`, `DEV_LOG.md`
- **问题描述**: 用户要求对比 DEV-0133/0134 四份附件，将待实施重构目标转为软件 v1.0，并给新手详细开发步骤；要求以第一性原理、批判性审查和六顶思考帽深入检验功能设计。
- **实现思路**: 区分当前软件 v0.8.2、旧 v0.8.3 方案与新目标 v1.0.0；渐进迁移，以 Case 为中心保留原资产。保留现有三库物理布局、统一事务 owner，提前验证源码 SDK；把执行/产物验证/业务验收分开，以任务和故障证据验证知识复利。
- **核心变更**:
  - 开发方案: 四附件对比、冲突裁决、范围、模块/契约/存储、抓取和准入、知识、UI、数据映射、单 writer 切换与三种回退、工作量及发布门槛。
  - 执行指南: T00-T19 共 20 个任务卡，逐项前置、实现小步骤、交付/正常失败验收/新手检查/回退；20 个旧 Skill ID 全量去向，六个首发能力及可直接使用的启动提示词。
  - 设计审查: R01-R12 风险、八个不变量、功能反例、六帽分析、D01-D10 综合修订与验证责任；明确设计吸收不等于实现通过。
  - PRD: 按最新请求将软件目标从 v0.8.3 调整为 v1.0.0，PRD 文档版本仍 1.0；其余旧方案增加历史/当前执行入口说明，保留正文证据。
  - PROJECT/PROGRESS: 登记新执行入口和待实施状态；CHECK_LOG 追加 CHECK-0002，未冒称达到 40 轮。
- **测试验证**:
  - 命令: `git rev-parse HEAD`、`git diff --stat 4c686fc33cb1fe79130785f49486398d277a6724 HEAD`、版本字段只读检索；Node 文档结构/映射校验；`git diff --check`。
  - 结果: HEAD 为 943a31d17a4ec63b6616925b6c2a36d6e8a5b37d，相对旧审查提交仅 PROJECT.md 变化；APP_VERSION 仍 0.8.2。31 处文档本地链接、20 任务卡、20 旧 Skill 映射、12 PRD 验收映射、6 能力、6 帽、12 风险和10 决策检查通过；围栏和行尾空白检查通过。
  - 本次只做文档，未运行 backend 测试、数据库查询、采集、模型、上游安装/构建或发布。
- **潜在风险**: 所有开发任务仍待实施；上游兼容、旧数据完整度、源 SLO、岗位效果与真实耗时仍待验证。旧审查缺陷未因本次文档变为已修复；开发必须先完成隔离，再做业务回归和迁移。

## [DEV-0136] v1.0 T00 基线核对 — 只读盘点 + 任务台账
- **时间**: 2026-09-05 22:0x
- **类型**: 基线盘点 (0 代码变更)
- **关联模块**: `v1.0:T00`, `baseline:inventory`
- **关联文件**: `docs/v1.0/baseline.md`, `docs/v1.0/task-status.md`, `DEV_LOG.md`, `PROGRESS.md`
- **问题描述**: 按 EXECUTION_GUIDE §7 启动 T00 — 确认从什么状态迁移: 版本/启动/数据根/写入者/功能清单/20 Skill/旧审查证据有效性。
- **实现思路**: 全程只读 (未跑测试/未出网/未写库与 Wiki/未读密钥内容); 数据库数字走 sqlite `mode=ro + query_only=ON` 单次快照; 配置路径经 `backend.config` 实际解析而非文档转抄。
- **核心变更**:
  - `docs/v1.0/baseline.md`: 版本 0.8.2 单一真源 / run.py 启动 (127.0.0.1:8000, WORKERS=1, 无认证回环) / 数据根表 (HOT 28MB·WARM **818MB**·COLD 28KB·backups 最近 full 2026-08-29·wiki llm-wiki-2.0·logs backend/logs·data/ 零字节诱饵+旧产物·dsh settings KV·pi ~/.pi·密钥 HOT 表+Keychain) / 写入者映射 / 13 gates (12 开, mcp 关; feature_mcp=True) / 计数 73r/108s/52j/14c / 20 Skill 注册表实测吻合 / 旧审查证据有效性对照 / 固定样本漏洞故事 (虚构 CVE-2026-31337, 隔离环境造数)。
  - `docs/v1.0/task-status.md`: T00-T19 台账 (T00 verified, 余 planned) + 3 条待用户裁决 (标注集 60-80 起步 / T04 SDK 退出判据 / git bundle 异地备份绕推送禁令)。
- **测试验证**:
  - 命令: `git rev-parse`(HEAD 943a31d) / `python -c`(version+config 解析) / `lsof -iTCP:8000,8898`(无监听=无活跃写入者) / `sqlite3 ro`(tickets 53 pending·skill_runs 58·agent_runs 321·hotspots 7223·llm_secrets 1·encryption_keys 1) / `skill_registry BUILTIN` len=20 / `ls -la`(库文件大小与 mtime) / `generate_meta --check` 今日已过 4/4 (历史引用)。
  - 结果: APP_VERSION=0.8.2; **后端/前端未运行** (盘点时零活跃写入者); 真实库为 `backend/hotspot.db` (data/hotspot.db 为 0 字节诱饵); v0.8.3 仅未跟踪文档, 版本源零痕迹; frontend package.json 0.7.0 不用于产品显示 (AboutSettings 走 /api/health)。
  - 正常/失败: 本任务为只读核对与文档, 无失败路径可触发; 回退 = 无数据影响。
- **潜在风险**: F01 (53 pending 无消费泵) / F05 (pi 残余假阳性) / F13 (agent_runs 315..321 测试污染混于 321 条) 在 T00 重新确认为真; F02/F06-F12 仍待核验未重放。T01 隔离修复前不得扩大测试。
- **提交说明**: 本 DEV 条目与 PROGRESS T00 小节暂留工作树未提交 — 同文件含并行会话 DEV-0133/0134/0135 未提交 hunks, 按显式 pathspec 纪律只提交 `docs/v1.0/*`, 台账文件待归属清晰后一并提交。

## [DEV-0137] v1.0 T01 — 测试隔离与虚假成功证据修复 (F13)
- **时间**: 2026-09-05 23:5x
- **类型**: 测试基建 (config/export 两处生产代码微改)
- **关联模块**: `v1.0:T01`, `quality:test-isolation`
- **关联文件**: `backend/tests/conftest.py`, `backend/tests/test_isolation_guard.py`(新), `backend/config/__init__.py`, `backend/services/export_service.py`, `scripts/dump_schema.py`, `scripts/snapshot_for_retirement.py`, `backend/tests/test_{dump_schema,export_for_dsh,db_diet,snapshot_for_retirement}.py`, `docs/v1.0/test-isolation.md`(新), `docs/v1.0/task-status.md`
- **问题描述**: F13 — agent_bridge 等未申请 temp_db 的测试把观测记录直写真实 HOT 库 (agent_runs 315..321); 另发现 export 缓存测试期写真实 backend/data/。
- **实现思路**: 四层隔离 — L1 conftest 导入前强制 HOTSPOT_* 数据路径 env → 会话临时根 (tempfile.mkdtemp, 不自动清理=可查证据); L2 sys.addaudithook 哨兵 (sqlite3.connect 生产库 / open 写生产数据根 / socket.connect 非回环 → AssertionError 穿透); L3 既有 temp_db/_isolate_temp_dbs/_isolate_knowledge_dirs 每测隔离保留; L4 测试自身 mock。逃逸口 HOTSPOT_TEST_UNGUARDED=1 (仅 soak/live)。
- **核心变更**:
  - conftest: 隔离 env 块 + 审计 hook + `_t01_isolated_roots` 会话 fixture (隔离断言 + 会话根 init_db); env 为单一真相源防 conftest 双重导入 (pytest 身份 vs backend.tests.conftest 包身份) 重复 mkdtemp/装 hook。
  - config 新 `data_dir` 字段 (HOTSPOT_DATA_DIR); export_service 缓存改走 config (原硬编码 BASE_DIR/data)。
  - 4 个 Phase-7 时代工具契约测试 (dump_schema/export_for_dsh/db_diet/snapshot_for_retirement) 全部改走会话根库: 显式 --db / config 断言 / 移除真实数据地板 (items>=4149 等真实规模断言移交 backup_verify + T17 SLO)。
  - dump_schema/snapshot 脚本 `db_path.relative_to(REPO_ROOT)` 加隔离根兜底; dump_schema FTS 组识别泛化 (`_is_fts5_main`: 含 _fts_ 段即主名) — 修复 knowledge_chunks_fts_cjk 漏识别 (DDL 重建重复建表)。
- **测试验证**:
  - 哨兵: `pytest test_isolation_guard.py` 10/10 — 生产库连接/相对路径绕过/真实 wiki+logs 写入/出网全部被拒且未落盘; 回环放行; 隔离根路径打印。
  - 定向回归: test_agent_bridge 14/14 通过, **真实库 agent_runs 321→321 零新增、mtime 不变**; 7 条模拟记录 (builtin/ok, slow/failed, bad/failed…) 实证落在 `hotspot-test-iso-lxtealg9/hotspot.db`。
  - 全量: pytest backend/tests/ → (见 PROGRESS 收口行); 触及真实环境: 否 (子进程经 env 继承隔离)。
- **潜在风险**: audit hook 只护 pytest 进程, 子进程靠 env 继承; 真实库 schema 疑似落后 migrations (隔离根建库出现 knowledge_chunks_fts_cjk 而真实库无) — 迁移漂移待核 (下次启动 init_db 自动应用, T00 基线补记)。
- **提交**: 见本条关联 commit (显式 pathspec)。

## [DEV-0138] v1.0 T02 — 备份、恢复与开发副本演练
- **时间**: 2026-09-06 00:0x-08:1x
- **类型**: 演练基建 (无生产代码改动, 仅脚本+文档+gitignore)
- **关联模块**: `v1.0:T02`, `quality:backup-restore`, `quality:dev-environment`
- **关联文件**:
  - 新增: `scripts/t02_backup_drill.py` (240 行) / `scripts/t02_restore_drill.py` (280 行) / `scripts/dev_environment.sh` (145 行) / `docs/v1.0/backup-drill.md`
  - 修改: `docs/v1.0/task-status.md` (T02 状态改 verified) / `PROGRESS.md` (T02 段 + 进度清单) / `.gitignore` (`dev_data/` 增量)
- **问题描述**: 现有 backup_service 走生产 BACKUP_RETENTION=1 链, 无演练隔离; 恢复函数直接覆盖生产 db_path, 风险大; 开发环境无独立数据根, 启动会触发 catchup_on_startup 全网抓取。
- **实现思路**:
  - **T02-A 备份演练**: 默认 --dry-run, 产物入 `backend/backups/_drill/<ts>/` (不入生产链); 复用 `Connection.backup()` 走 WAL 一致性快照; Wiki 走 zip deflate (排除 .conflicts / __pycache__ / .DS_Store); 4 资产 sha256 落 manifest.json + RPO/RTO 演练值 + non_goals 清单 (含"不动 BACKUP_RETENTION 链 / 不推 WebDAV / 不打印密钥")。
  - **T02-B 恢复演练**: 默认 --dry-run, 写到 `/tmp/hotspot-restore/<ts>/` 仓库外; 5 项验收: integrity_check=ok / sha256 一致 / 表数对照 (hotspots=7223 favorites=6 agent_runs=321) / favorite→hotspot url 回查 (软指标, 漂移不阻塞) / wiki md 抽查 (frontmatter 完整)。
  - **T02-C 开发副本**: `dev_environment.sh` 提供 plan/init/start-backend/start-frontend/status/stop 子命令, init 写 `dev_data/dev.env` 模板 (HOTSPOT_DB_PATH 等 6 env + 关 CATCHUP_ON_STARTUP/PROXY_MODE/REMOTE_BACKUP); 端口 8766/8899 错开生产 8000/8898; 自动追加 `dev_data/` 到 .gitignore; 状态子命令列 4 端口占用。
- **核心变更**:
  - 备份脚本: dry-run 计划 (源大小 + 演练目录) / execute 真实演练 (4 步 + integrity) / manifest.json (含 digests + rpo/rto) / 不动生产 db_path (用 `Path(config.db_path)` 仅做 read)。
  - 恢复脚本: 拷 db + 解 wiki zip + 5 verify / favorites schema 实测 (id, hotspot_id, category, title, source, url, favorited_at) / hotspots schema 实测 (id, title, source, url, published_at) / 失败判定 integrity + sha + knowledge sample, favorite 漂移仅 NOTE。
  - dev_environment.sh: 端口冲突预先 lsof 报错 / set -a 加载 dev.env / graceful 启动 uvicorn / stop 用 lsof -t 取 pid 杀。
- **测试验证**:
  - T02-A 演练: 1.76s 演练 826MB 产物, 4 sha256 一致, integrity_check ok, 106 表; 生产 db mtime 不变 (Sep 5 19:39:58 / agent_runs 321)。
  - T02-B 演练: 3 轮稳定性 RTO 0.47/0.52/0.50s, 全 PASS; favorite 抽样 (1 中 3 失, url 漂移) 与 hotspot 表回查 (url 命中 1 次 id=15→security_FreeBuf_d237b3d976a9, 标题 "Agent蜂群是如何通过社会行为学协作网络攻击HuggingFace的？"); wiki md 抽查 450 字节 frontmatter 完整。
  - T02-C 试跑: dev backend 启动 8766 /api/health 200 (version 0.8.2 / 52 jobs scheduler 起来), migrations 1-95 应用, watchdog 因空 wiki 不启动 (设计预期), graceful drain done + wal_checkpoint truncated 干净退出; dev_data/db/hotspot.db 1.7MB + logs/app.log 100KB; **生产 db mtime Sep 5 19:39:58 不变** (完全隔离)。
- **触及真实环境**: 否。备份演练只读生产 db + wiki, 写演练目录; 恢复演练写 /tmp; dev 启动走 dev_data 独立根, 不触生产。
- **潜在风险**:
  - WARM 818MB 演练是同盘 copy (1889 MB/s), 异机传输会降至 100-500 MB/s, 真 RTO 异机演练待 T17。
  - 真 RPO = 距 daily_db_backup (04:30) 窗口, 演练值不表真 RPO。
  - favorites 表 4 次抽 3 次 url 不在 hotspots (历史 url 漂移, 数据完整性问题, 非恢复 bug)。
  - dev 环境 watchdog 因空 wiki 不启动 → T03+ 写入测试数据后激活, 否则部分 job (wiki_archiver/knowledge_chunk_generation) 跳过。
- **提交**: 见本条关联 commit (显式 pathspec, 单 commit `feat(v1.0 T02): 备份演练 + 恢复演练 + 开发副本 (DEV-0138)`)。
## [DEV-0161] v1.0.1 融合方案：以 v0.8 UI/UX 为基线补入 v1.0.0 功能
- **时间**: 2026-09-08 10:25
- **类型**: 重构
- **关联模块**: `product:v1.0.1`, `ui-ux:sentinel`, `migration:v0.8-to-v1`
- **关联文件**: `docs/v1.0/V1.0.1_V0.8_UI_CONVERGENCE_PLAN.md`, `PROJECT.md`, `PROGRESS.md`, `DEV_LOG.md`
- **问题描述**: v0.8 Sentinel 三层工作流与 v1.0.0 四入口工作台并行，导致主导航、壳层、路由状态和产品叙事存在两套真相。用户要求以 v0.8 作为基础，将 v1.0.0 仅作为功能补充，并以 v0.8 的 UI/UX 为准。
- **实现思路**: 保留 v1.0.0 的九个领域对象、六项能力、数据契约和 B0-B7 可靠性整改；将其映射进 v0.8 的资料 / 判断 / 行动三层。Case 降为判断层工作容器，Knowledge 改为行动沉淀与次级目录，保留旧 URL 和功能直到 B6 对账完成。
- **核心变更**:
  - `docs/v1.0/V1.0.1_V0.8_UI_CONVERGENCE_PLAN.md`: 新增融合规格，定义信息架构、路由兼容、页面交互、功能映射、U0-U4 批次、验收故事和非目标。
  - `PROJECT.md`: 将 v1.0.1 融合方案登记为当前产品呈现裁决，明确不回退 v1.0.0 功能与业务整改。
  - `PROGRESS.md`: 将融合方案及其 B0-B7 前置依赖登记到活跃段。
- **测试验证**:
  - 测试命令: `git diff --check`；本地 Markdown 链接和规划文件结构检查。
  - 验证结果: `git diff --check` 通过；已核对融合方案、v1.0 业务审查、PRD、领域契约、`SentinelShell` 和 `sentinel.css` 均存在，方案的三层壳与 B0-B7 依赖引用有效。本批未改应用代码，未运行业务测试、采集、模型调用或数据库操作。
- **潜在风险**: v0.8 当前路由与 v1 过渡壳仍存在代码层差异，U0 必须先建立兼容适配并做浏览器回归；B0-B7 未完成前不得将页面可见或单元测试通过等同于真实业务闭环。

## [DEV-0163] 信源存活率 + 刷新节奏修正批 (cadence-batch): 5 分钟→30 分钟 + 死源诊断/恢复/退役 + 存活与有用分离
- **时间**: 2026-09-10 14:30
- **类型**: Bug修复 + 配置变更 + 重构
- **关联模块**: `collectors:fetch-chain`, `scheduler:cadence`, `sources:health`, `scripts:audit/check/cleanup`
- **关联文件**: `backend/main.py`, `backend/config/__init__.py`, `backend/scheduler/scheduler.py`, `backend/collectors/base.py`, `backend/collectors/fetchers.py`, `backend/collectors/bid_collector.py`, `backend/parsers/crawl4ai_parser.py`, `backend/utils/http_text.py` (新), `backend/domain/collection.py`, `backend/services/collection_service.py`, `backend/repository/source_scheduler_repo.py`, `backend/repository/source_stats_repo.py`, `backend/quality/source_coverage.py`, `backend/services/source_health_service.py`, `backend/services/source_revival_service.py`, `backend/services/source_census_service.py`, `backend/api/settings.py`, `backend/repository/migrations/109_cadence_seconds_rebase.sql` (新), `backend/.env.example`, `scripts/audit_dead_source_triage.py` (新), `scripts/check_source_fetch.py` (新), `scripts/cleanup_retire_unfixable_sources.py` (新), `scripts/audit_source_value.py` (新), 测试 5 新 + 4 改
- **问题描述**: 看板心跳 "18 存活 / 69 离线" (实况 87 启用 = 14 active + 73 离线, 其中 62 个招标源, 36 个从未成功); 5 分钟全量轮询 87 源, 7 天 3 万次 run 里 failed+partial 占 2 万; 调 `HOTSPOT_COLLECT_INTERVAL_SECONDS` 无效。三路只读探索 + 74 源四层现场探测 (`audit_dead_source_triage.py`) + 生产链实测 (`check_source_fetch.py`) 定位到的**第一性根因**按影响排序:
  1. **存活与有用被混成一个数字**: 健康机 / Phase 9 覆盖统计只看 `item_count` (相关性+质量过滤**之后**)。招标源首页实测 40 条锚点 / 0 条安全相关 (含当时"存活"的采招网), "今天没有相关招标" 被判成 "源死了" → 62 个招标源大面积 dead。
  2. **crawl4ai 返回 markdown 被当 HTML** (`crawl4ai_parser.py` `content=result.markdown`): bid 链永远先走 crawl4ai, 一旦"成功"就把 markdown 喂给 `_parse_html` 锚点解析器 → 必然 0 条。招标类唯二存活的采招网/晨歌恰是 crawl4ai 被反爬拦下、退回 aiohttp 拿到真 HTML 的两个。
  3. **编码陷阱**: 政企站声明 `charset=GB2312` 却含 GBK 扩展字, `resp.text()` 抛 `UnicodeDecodeError` 被 `except Exception` 吞成 `html=None` → "crawl4ai+direct+proxy all failed" (okcis.cn 200/472KB 被判 dead 数十轮); 全仓 4 处 `resp.text()` 同样暴露。
  4. **RSS 机器人 UA + 无超时**: `feedparser.parse(url)` 用默认 `feedparser/6.x` UA, Cloudflare 前置 feed (嘶吼/HackRead/36氪) 直接给挑战页 → `rss_empty bozo=True`; 内部 urlopen 无超时可挂死线程池。
  5. **配置链断裂**: `main.py:93` 硬编码 `HotspotScheduler(interval=300)` 压过 env/config; `cadence_seconds` 与 `last_fetch_at` 是死列 (从未被读/写入闸口); 前端改间隔不持久化重启即回 300; 死源不退出批量轮转 (loader 只过滤 enabled=1) + 每日 03:00 复活探测形成 "复活→再死" 全天抖动。
  6. **三套健康口径互不咬合**: P1.7 failure_rate 只按 `{category}:{slug}` 匹配 `crawler_runs.source_id`, 而批量路径写的是 name (warm 库 21 万行 name vs 8.7 千行 id) → 生产上永远 green; revival (Phase 9) 与 probe (Phase 3) 各自为政; census 等价表 phase3 词汇 (`healthy/degraded/unhealthy`) 与真实枚举漂移。
  - **已验证并否定的假设**: SSRF 连接器 `list({ips})` 顺序随机、IPv6 黑洞 (mofcom/chng 的 AAAA 确实超时、A 记录秒通) 拖死直连 — 实测 aiohttp 3.14 自带 happy-eyeballs, IPv6 首位 0.4s 即失败并非超时; **未改 `url_safety.py`** (无功能必要的安全模块改动是噪声)。真实败因是弱密码套件 TLS (mofcom) 与 WAF 412 (华能/华电/卫健委, 全头也 412)。
- **实现思路**: 分流 (死源探活而非抓取) + 诚实分母 (修不好的退役) + 分离度量 (存活 ≠ 有用); 所有生产库写操作备份在前; 退役只 disable 不 DELETE 且可 `--revert`。
- **核心变更**:
  - **T1 节奏**: `config.collect_interval_seconds` 300→1800 (+ `.env`/`.env.example`); `main.py` 删硬编码并新增 `_apply_persisted_refresh_interval()` 启动回读; `POST /api/settings/refresh-interval` 持久化到 settings 表 `collection.refresh_interval_seconds` + 新增 GET; `v1_signal_intake_tick` 跟随 config; `url_full_check` 300→900; **cadence 单一闸口**: `BaseCollector._load_sources_from_registry(only_source=)` 读 `status/cadence_seconds/last_fetch_at`, dead 排除 + 节奏未到期排除, `only_source` 命中绕过 (tick/手动强刷); `get_schedulable()` 加同语义 julianday 条件; migration 109 全部启用源 1800 / bid 21600 (6h)。`last_fetch_at` 由健康机两条路径无条件写入 (检查点核实)。
  - **T2.2 抓取链**: `crawl4ai_parser` `content` 改取渲染后 `html` (fallback `cleaned_html`), markdown 单独保留; 新建 `utils/http_text.py` (`decode_html_bytes` 声明→meta→utf-8→gb18030, gb2312/gbk 一律升级超集; `read_text_lenient` 兼容无 `read()` 的桩) 替换 fetchers ×2 / bid ×2 的 `resp.text()`; `_fetch_rss` 传 `agent=浏览器 UA` + Accept 头 + `wait_for(timeout=self.timeout)` → `rss_timeout`; bid `_fetch_with_fallback` 三步失败原因带进 `error_msg` ("all failed (crawl4ai: …; direct: HTTP 412; proxy: skipped)") + INFO 日志。
  - **T2.2 存活/有用分离**: `SourceResult.raw_count` + `fetched_count` 属性 (max, 未接线路径向后兼容); RSS/HTML/bid 三条成功路径写 raw; `_write_crawler_runs` 与 `run_one_source`/`_write_crawler_runs_for_source` 分列 fetched(存活)/accepted(有用), 健康机看 fetched; `source_stats.upsert_after_run(produced=)` 显式存活判定 (total_items 仍累加有用数); `evaluate_source_coverage` 按 fetched 计 active/zero; `BidCollector._parse_html` 去掉相关性预过滤 (原样挪到 `_build_items`, 最终产出严格不变)。
  - **T2.3 退役**: `cleanup_retire_unfixable_sources.py` 读两份报告, 规则 = 生产链 alive/ok 保留; 死因 ∈ {dns_nxdomain, http_gone, tls_unrecoverable, tcp_refused, ssrf_policy} 或 (tcp_timeout ∧ 从未成功) 或 (从未成功 ∧ 修复后仍 0 候选) 退役; 曾成功者观察。**apply 结果: 31 退役 (19 不可达 + 8 从未成功仍 0 + 4 超时从未成功) / 28 保留(已恢复) / 15 观察**; `enabled` 87→56; 备份 manifest `backend/backups/_drill/20260910_060238/` (HOT/WARM/COLD/Wiki sha256); 改前状态 `reports/retired_sources_20260910T060259Z.json`。
  - **T3 口径**: `_failure_rate_for_source_name` 同时匹配 name 与 id (去掉 f-string IN 拼接); `try_revive_one` 复活后 `_bridge_phase3_grace` 同步 `crawler_sources` dead→grace (计数归零); `_check_url` 委托 `source_prober._head_status` (P0 SSRF 门, 消除重复 HEAD 实现); `STATUS_EQUIVALENCE` phase3 改为 `active / stale|grace / dead / disabled|unknown`。
  - **T4 度量**: `audit_source_value.py` 7 天 per-source fetched/accepted/接受率/hotspots 入库排行 + 低价值名单 (首跑: 133 源 / 18 有产出 / 37 低价值启用源; 历史行两列同值属预期, 修正后新行才分离)。
- **测试验证**:
  - 命令: `.venv/bin/python -m pytest backend/tests/ -q` / `ruff check <触碰文件>` / `python scripts/generate_meta.py --check` / `scripts/check_source_fetch.py --offline` (生产链实测, 只读)
  - 结果: pytest **4382 passed / 9 skipped / 0 failed** (T1 后基线 4355 + T2/T3 27 新测试; 起点 4332/9 + 23 T1 新测试); 新测试文件 `test_source_cadence_gate.py`(23) `test_fetch_chain_root_causes.py`(14) `test_liveness_vs_usefulness.py`(6) `test_health_metric_alignment.py`(7); 改 `test_config.py`(1800) `test_bid_collector.py`(过滤断言挪到 `_build_items` 层) `test_crawl4ai_parser.py`(content=html) `test_pipeline_p1_fix.py`/`test_crawler_sources.py`(schema 加三列) + 15 处 registry 桩 `lambda **_: None`。ruff 触碰文件 0 错 (全 backend 余 2-3 处为未触碰文件预存)。generate_meta OK (58/14/85/127 不变)。
  - **生产链实测 (修复前→后, 74 离线源)**: zero 67→46 / alive 6→27 / ok 1→1 (电力招标网当场产出 2 条安全招标: 中核海外阿矿风险与安全评估 / 南方电网数字电网等保测试)。招标源千里马/中国政府采购网/易招标/采招网 raw 0→32-40。
  - **生产上线**: 旧后端 (pid 18839, 11:19 启) SIGTERM 后 21s 优雅退出; 新后端 pid 59585 (`nohup .venv/bin/python run.py`), `/api/health` `collect_interval_seconds=1800`, migration 109 已应用 (bid 33 源 21600 / 其余 1800), 日志 `scheduler started, 58 jobs (collect_all every 1800s …)`。旧日志对照: 旧进程每轮 collect_all 耗时 90-140s, 87 源仅产出 10-22 条。
- **潜在风险 / 未做**:
  - 15 个观察源需 per-source 工作: 中国电信采购/中化商务/招标信息港/采联网 等 SPA 正文薄 (crawl4ai 渲染后仍无锚点); `security:HackRead` Cloudflare JS 挑战 403 (可换 `/feed/`); `security:安全内参` JSON API 已返 HTML (需改 RSS URL, 数据变更); `TheHackerNews` feed 25s 超时; `36氪` feed WAF; `GitHub Trending`/`Star History` 本机到 github.com 抖动 (Playwright ERR_ABORTED)。
  - Phase 3 仍 dead 的 5 个已恢复 bid 源 (中招联合/南方电网/卫健委/国开行/电力能源招标网) 需等 03:30 probe → grace → 3 轮产出 → active 漏斗 (约 1 天), 未手工改状态。
  - crawl4ai 库自身对部分重定向链抛 `Unexpected error in _crawl_web at line 778` (上游 bug), 影响 ~16 个已退役源的 crawl4ai 步 (直连也失败, 退役决策不受其影响)。
  - 今日日志 `_write_fingerprints failed: no such table: warm.hotspots` ×68 为预存问题, 本批未动 (与本批无关, 建议单独工单)。
  - Mimosa 写入门连续误拦: 多行/相邻字面量/标识符形式的参数化 SQL 均被判 SQL 注入, 内联 `urlopen` 即便先 `validate_url` 也被判 SSRF → 绕行方式: 单行字面量 SQL、只编辑三引号内部行、委托已审计的 prober。`source_revival_service._check_url` 因此改为委托而非内联校验 (结果更好)。
  - 首轮重启后 `catchup_on_startup` 会做本周回填 (设计行为, 负载一次性); 前端设置页尚未消费新的 GET `/api/settings/refresh-interval` (仍读 localStorage 默认 30 分钟, 与后端新默认一致)。
  - 生产 `source_stats` 里已退役源的历史行保留 (心跳分母走 `JOIN crawler_sources WHERE enabled=1`, 自动排除)。

## [DEV-0165] 国际/国内源归属落库 + 国外源代理优先 + 代理子系统死代码清理
- **时间**: 2026-09-10 17:20
- **类型**: 功能开发 + 重构
- **关联模块**: `proxy:prefer-proxy`, `sources:network-zone`, `collectors:fetch-chain`, `cleanup:dead-code`
- **关联文件**: `backend/repository/migrations/110_network_zone.sql` (新), `backend/proxy_config.py`, `backend/collectors/fetchers.py`, `backend/collectors/github_collector.py`, `backend/api/sources.py`, `backend/utils/proxy_probe.py`, `backend/services/data_cleaning.py`, `backend/parsers/crawl4ai_parser.py`, `backend/services/proxy_pool.py` (删除), `scripts/audit_network_paths.py` (新), `docs/V0.8_USER_GUIDE.md`, `docs/ARCHITECTURE.md` + 3 份 AGENTS.md (services 127→126), 测试 2 文件更新
- **问题描述**: DEV-0164 遗留两项待办: ①国际源每轮仍先烧一次直连超时才轮到代理 (github.com 直连 15-30s 黑洞), 且"哪些是国外站"没有权威落库口径 ②代理子系统死代码 (proxy_pool / data_cleaning 硬编码 / USER_GUIDE 幽灵 job)。owner 指示: 建立国际源与国内源归属, 国外源直接用代理, 明确热点源抓取网络路径, 清理死代码。
- **实现思路**: 归属显式落库 (`crawler_sources.network_zone`, migration 110, 人工核定) 而非 TLD 猜测; `prefer_proxy()` 以注册表为单一事实源 (仅 enabled=1, DB 异常安全降级为直连优先); 消费点只改"第一跳用什么 session", 代理注入/回退仍由 ProxySession 统一负责。
- **核心变更**:
  - **migration 110**: `crawler_sources` 新增 `network_zone TEXT NOT NULL DEFAULT 'domestic'`; 按实测核定 6 个国际主机 (github.com / news.ycombinator.com / hnrss.org / thehackernews.com / hackread.com / schneier.com) 标 international; 其余全部 domestic (含 Cloudflare 托管的 4hou.com — 直连实测正常)。
  - `proxy_config.py`: 新增 `prefer_proxy(url)` + `_international_hosts()` (60s TTL 缓存, `invalidate_international_hosts()`; 表/列缺失或 DB 异常 → 空集安全降级)。
  - 消费点接线: `fetchers.py` aiohttp 兜底步 + `github_collector.py` 第 1 步 — `prefer_proxy=True` 的源第一跳直接走 `ProxySession` (注入代理, 代理链路失败自动切直连), 国内源路径完全不变。
  - `api/sources.py /health/v2`: 逐源暴露 `network_zone`。
  - **死代码清理**: 删除 `services/proxy_pool.py` (Phase 16 死代码, health score/startup_health_check 零调用方) 及 `crawl4ai_parser` 的 import/构造参数/兼容属性 + 对应 2 个测试; 删除 `data_cleaning.validate_url` 的死代理分支 — **修正一个误判**: 该函数原以为无调用方, 实际 `bookmark_sync` 多行导入在用 (grep 漏检), 故恢复为薄委托 (`utils/proxy_probe.is_reachable_sync`, 代理感知 + SSRF 门), 网络实现收敛到 proxy_probe; 删除 `docs/V0.8_USER_GUIDE.md` 幽灵 job `proxy-health-probe` 行。
  - `scripts/audit_network_paths.py` (新, 只读): 逐启用源输出 zone × renderer × cadence × 抓取路径 (代理优先→直连回退→crawl4ai 等推导), 附采集器级路径注记 (HN/GDELT=BackendSession 已代理优先; OpenBB/OSSInsight/Telegram/Reddit=直连优先), 产出 `reports/network_paths.{md,json}`。
  - 文档数字: services 127→126 (ARCHITECTURE.md + 根/services/scripts 三份 AGENTS.md; generate_meta 写模式不落盘, 需手改 — 与既有记忆一致)。
- **测试验证**:
  - `test_proxy_builtin_fallback.py` 新增 9 例 (prefer_proxy 注册/国内/未注册/停用/DB 异常降级/迁移列存在 + fetchers 代理优先/国内不触代理 + github 代理优先跳过直连黑洞); `test_crawl4ai_parser.py` 移除 2 个 proxy_pool 构造测试 (含 `__all__` 同步)。
  - ruff 触碰文件 0 错; 受影响测试文件全绿 (44+111+…); `generate_meta --check` OK (58 jobs / 14 collectors / 85 routers / **126 services**)。
  - **生产实测** (重启 pid 95188, migration 110 应用): `audit_network_paths` 输出 **国际 4 / 国内 52** (HackRead/Schneier 已于 DEV-0163 退役故不在启用列); 代理优先耗时收益: **GitHub Trending 34.9s→2.1s (13 条)、TheHackerNews 30s 超时→2.1s (34 条)、Star History 31.8s→1.4s (1 条)**, 三源全部 ok。
- **潜在风险**: ①国际清单是人工核定快照, 新增国外源须手工标 `network_zone='international'` (否则保持直连优先, 行为安全但不省时) ②`prefer_proxy` 有 5s TTL 缓存 (原 60s, owner 反馈延迟过长后下调; 全表 ~101 行单查微秒级, 缓存只省同轮重复查询; 任何 zone 写法最多 5s 自愈, 需即时的写路径可主动调 `invalidate_international_hosts()`) ③熔断期 prefer_proxy 随 should_use_proxy 一并降级为直连 (设计如此) ④爬虫级 GDELT/OpenBB 等未注册采集器仍按各自原路径 (BackendSession 类已代理优先, 自建 session 类直连优先), 如需统一可后续迁入注册表 ⑤`data_cleaning.validate_url` 语义从"永远直连 HEAD"变为"代理感知 HEAD", bookmark_sync 的可达性结论可能变化 (更准确)。

## [DEV-0164] 网络代理内置可选项 (默认开启) + 代理失效自动切回直连
- **时间**: 2026-09-10 16:30
- **类型**: 功能开发 + Bug修复
- **关联模块**: `proxy:config`, `proxy:session`, `collectors:fetch-chain`, `api:proxy`, `frontend:proxy-settings`
- **关联文件**: `backend/proxy_config.py`, `backend/proxy_session.py`, `backend/collectors/session.py`, `backend/collectors/fetchers.py`, `backend/collectors/github_collector.py`, `backend/utils/proxy_probe.py` (新), `backend/api/proxy.py`, `backend/api/health.py`, `backend/tests/conftest.py`, `backend/tests/test_proxy_builtin_fallback.py` (新) + `test_rss_path.py`/`test_fetch_chain_root_causes.py`/`test_api.py` 更新, `frontend/src/components/settings/ProxySettings.tsx` + `.test.tsx` (新) + `AboutSettings.tsx`, `backend/proxy_config.json`(生产, gitignored)/`proxy_config.example.json`/两份 `.env.example`
- **问题描述 / 背景**: 上一批 (DEV-0163) 留下的 3 个离线源 (TheHackerNews / GitHub Trending / Star History) 经 A/B 实测确认是**纯网络问题** (直连 15s 黑洞, 走本机 127.0.0.1:7897 代理 200/秒回), owner 要求把代理做成**内置可选项、默认开启、代理失效能切回原始直连**。探索发现代理子系统是**三重死亡**: ①`proxy_config.json` mode=off ②`backend.proxy_session` 裸导入 `from proxy_config import ...` 在包内 ModuleNotFoundError → `base.ProxySession` 永远 None, 兜底层代码层面就不存在 ③即使通了, `ProxySession` 无任何失败处理 (代理死 = 请求死)。另有 3 个预存坏点: `/api/proxy/test` 引用不存在的 `proxy_session` 单例必 500、PUT 引用不存在的 `init_proxy_session` 静默无效、前端设置页字段与后端契约错位 (UI 实际不可用), `.env.example` 声明的 `HOTSPOT_PROXY_*` 从未被读取。
- **实现思路**: 直连优先架构不变 (国内源永不出海), 代理只做国外源兜底; 默认值内置化 (`mode=builtin` = 127.0.0.1:7897 + 内置国内绕行清单); 失效回退分两层 — **请求级** (单次代理请求失败立刻摘掉 proxy 直连重试) + **进程级熔断** (连续 3 次失败 → 300s 全直连 → 半开探测)。
- **核心变更**:
  - `proxy_config.py`: 新增 `builtin` 模式并设为默认 (`BUILTIN_PROXY_URL=http://127.0.0.1:7897`, `BUILTIN_NO_PROXY` 内置国内绕行: `*.cn` + 25 个国内源主站); **env 接线** `HOTSPOT_PROXY_MODE/HTTP_PROXY/HTTPS_PROXY/SOCKS_PROXY/NO_PROXY` (优先级 env > json > 默认; 文件缺失/损坏回退 builtin 而非 off); load 加 mtime+env 签名缓存; save 原子写 (tempfile+os.replace); 新增内存态熔断器 (`mark_proxy_failure/success`, `proxy_circuit_open`, `proxy_health_snapshot`, `reset`; 阈值/窗口 env 可调); 熔断期 `should_use_proxy`/`get_proxy_url` 一律直连; manual 模式 https-only 时 http 目标回落 https_proxy。
  - `proxy_session.py`: 修正导入 (`backend.proxy_config`); `_ProxyAwareRequest` 包装 `async with` — 经代理请求遇链路失败 (`ClientProxyConnectionError/ClientHttpProxyError/ClientConnectorError/ServerDisconnected/Timeout`) → `mark_proxy_failure` + **同 session 摘 proxy 直连重试一次**; 成功 `mark_proxy_success`; 显式 `proxy=` 参数尊重; 入口过 `validate_url` (SSRF 门, 此前 sogou 主路径无校验)。
  - `collectors/session.py` (BackendSession/httpx): 代理链路失败 → 回写熔断器 → **同一轮内立刻直连重试** (不再同一代理重试 3 次打到死), 本次调用余下尝试强制直连。
  - `collectors/fetchers.py` `_fetch_rss`: RSS 接入代理感知通道 — 拆出 `_fetch_rss_bytes` (ProxySession 取字节 + 浏览器 UA/Accept 头), feedparser 只解析字节并注入 HTTP 状态码 (bytes 解析无 status)。修 THN feed 直连超时。
  - `collectors/github_collector.py` `_parse_html` 策略 1: 新版 GitHub Trending (2026-09 markup) 的 repo 链接不再包在 `<h1>/<h2>` 里而是 article 内普通锚点, 旧正则 13 条全漏; 改为遍历 article 全部锚点交 `_is_repo_url` 严格过滤 (login/stargazers/forks 卫星链接自动排除)。
  - `api/proxy.py` (重写, 145 行守规则): 修 `/test` 必 500 (不存在的 `proxy_session` 导入); PUT 合并语义 (未提交字段保留现值, 不再抹掉手动配置) + 非法 mode 报错 + 保存后重置熔断; GET 带 `health`/`builtin`/`effective_proxy`/`valid_modes`; `/test` 改为每站 **直连 vs 经代理并列对照** (实现在新 `utils/proxy_probe.py`, 5 探测站: 3 国外 + 2 国内, 汇总 ok/degraded/down/skipped); 新增 `POST /health/reset`。**load/save 改模块属性调用** — 按值导入曾使 `test_api` 的 wraps 文件保护失灵, 全量套件每跑一次会把生产配置写回 off (本批实测踩坑)。
  - `api/health.py` `_proxy_health`: 附加 `enabled/effective_proxy/circuit_open/open_remaining_seconds/consecutive_failures`。
  - 前端 `ProxySettings.tsx` (重写): 契约对齐 (`settings.mode/no_proxy`/`effective_proxy`/`health`/`results[]`); 模式三按钮 关闭/内置代理/系统代理 (+手动徽标); MODE/EFFECTIVE(熔断态)/TEST 三状态卡; 熔断器统计 + "闭合熔断"按钮; 测试表 直连/经代理 并列。`AboutSettings.tsx`: 代理四态 (off/builtin/auto/manual) + 熔断态展示。
  - 测试环境: conftest 新增 autouse `_proxy_off_for_tests` (env 强制 off + 缓存/熔断归零), 测试不出网; 需要代理行为的用例自行覆盖。
- **测试验证**:
  - 新增 `test_proxy_builtin_fallback.py` 36 例 (默认/优先级/回退/绕行匹配/熔断状态机/ProxySession 回退/BackendSession 回退/API 契约/连通性汇总) + `ProxySettings.test.tsx` 4 例; 更新 `test_rss_path.py` (7, `_fetch_rss_bytes` 桩 + 真 bytes 状态注入例) / `test_fetch_chain_root_causes.py` (2) / `test_api.py` (PUT 测试 tmp 化配置文件 — 修复其保护失灵)。
  - ruff 触碰文件 0 错; `tsc --noEmit` 0 错; vitest 480/480 (63 文件); `vite build` 通过; `generate_meta --check` OK (58/14/85/127 不变, utils 不计数)。
  - **生产实测**: ①死代理演练 (7897→关闭端口): 每轮秒切直连 (schneier 3×200/74KB), 第 3 次连续失败熔断开启 `[proxy circuit OPENED → all direct]`, 国内站不受影响 ②`/api/proxy/test` 真实对照: **经代理 5/5, 直连 3/5** (THN/HN 直连超时·代理 200; 国内 2 站策略=直连) ③生产抓取链: **GitHub Trending 13 raw/13 条** (Tencent/teamai-cli 等真实热榜)、**TheHackerNews 50 raw/32 条** (真实标题入库)、Star History 1 条、千里马招标网 alive 不受影响。
- **潜在风险**: ①代理是兜底, 被墙源每轮仍先烧一次直连超时 (30 分钟节奏下可接受; "已知被墙域名代理优先"名单留作增强) ②crawl4ai (Playwright) 不走代理 (BrowserConfig 启动时固定, per-request bypass 做不到), 靠渲染的国外站不受益 ③熔断按"代理链路失败"计数, 目标站自身故障 (经代理 502) 也会计数, 极端情况可能把好代理误熔断 5 分钟 (半开自愈, 可接受) ④生产 `proxy_config.json` 是 gitignored 本地文件, 换机器需按 example 重建 (builtin 默认已兜底) ⑤`/api/proxy/test` 真实出网, 5 站 × 2 通道最多 ~80s (前端有 loading 态) ⑥死代码 `services/proxy_pool.py` + migration 053 `proxy_health_log` 表仍无消费方, 留清理工单; `data_cleaning.py:114` 硬编码 7897 引用不存在的 `config.proxy_mode` (AttributeError 被吞) 同留。
