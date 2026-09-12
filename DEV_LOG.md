
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

## [DEV-0166] PageLayout 工具页内容区滑入 fixed 侧栏底下 (/settings 双侧栏叠印"乱码")
- **时间**: 2026-09-10 17:44
- **类型**: Bug修复
- **关联模块**: `frontend:page-layout`, `frontend:settings-hub`
- **关联文件**: `frontend/src/components/PageLayout.tsx`
- **问题描述**: owner 报 `/settings` 布局异常、显示"乱码"、与首页 UI 不一致。浏览器实测 (1440×900): AppNav 为 `fixed` 左侧 256px, `#main-content` 计算 `padding-left` 却只有 **40px** (期望 256px), 内容区从 x=57.5 开始, SettingsHub 自己的 210px 分类导航落在 x=97.5 — 整块压在 AppNav 上; 且 `#main-content z-10` 高于导航 `z-auto`, 两层文字叠印在同一片像素 = 所谓"乱码" (并非编码问题)。影响范围: **全部 PageLayout 工具页在 ≥1024px 桌面宽度** (`/todos` `/knowledge/*` `/skill-store` `/settings` `/report` `/secnews/*` 等), 只是 owner 在 /settings 首先撞到; 首页/判断层/行动层走 SentinelLayout 无 AppNav 所以正常, 故显得"不一致"。
- **根因**: T17.5 (`bdac95f`, 2026-09-07) 给 PageLayout 加 `<AppNav />` fixed 侧栏时, 把让位类 `sm:pl-64` 追加到已含 `px-4 sm:px-8 lg:px-10` 的同一 class 串。Tailwind 按断点顺序输出 responsive 变体, `lg:px-10` 在样式表中位于 `sm:pl-64` 之后, ≥1024px 时 `padding-left` 被覆盖回 40px; 640–1023px 反而正常 (同断点内 pl 排在 px 之后), 所以只有桌面复现。
- **实现思路**: 按 Tailwind 侧栏布局标准做法, "给侧栏让位"和"内容 gutter"拆到两层: 外层 `<div className="sm:pl-64">` 独占让位, 内层 `#main-content` 保留原 `max-w-[1320px] mx-auto px-* py-* relative z-10`。不动 AppNav、不动 settings-shell.css、不改 spec §5 的壳归属 (`/settings` 仍 PageLayout "不变")。
- **核心变更**:
  - `PageLayout.tsx`: `#main-content` 外包一层 `sm:pl-64` wrapper, 移除原串上的 `sm:pl-64`; 加一行注释说明"让位必须独占一层"的约束 (防再合并)。SentinelLayout 不动。
- **测试验证**:
  - 浏览器实测修复后 (1440 宽): wrapper `padding-left=256px`, `#main-content x=256` (= 侧栏右缘), settings 头部/分类导航 x=296, `overlapWithNav=false`; 抽查 `/todos` `/knowledge/import` `/skill-store` 三页 `mainX=256` 全部无重叠; /settings 截图目视干净 (左 AppNav / 中 分类导航 / 右 内容卡片)。
  - `npx tsc --noEmit` 0 错; 定向 vitest (PageLayout 5 + AppNav 3 + v085_route_shell 15) 23/23; 全量 vitest **480/480 (63 文件)** 与 DEV-0164 基线一致, 零回归。
- **潜在风险**: ①`max-w-[1320px] mx-auto` 现在在让位层内居中 (≥1576px 宽时内容在侧栏右侧区域居中, 而非整屏居中) — 视觉上更合理, 但与 T17.5 前的"整屏 1320 居中"不同 ②AppNav 桌面 nav 仍无 z-index (`z-auto`), 页面内 sticky/overflow 元素理论上可绘到侧栏上方, 本批未加 z 以保持最小改动 ③"与首页 UI 不一致"另一半是**设计如此** (spec §5: 工具页 PageLayout+AppNav, 三层页 SentinelShell), 若 owner 想让 /settings 进 Sentinel 壳属 spec 级裁决 (AGENTS 硬规则禁新壳), 本批不越权。

## [DEV-0167] 首页 SSE 回调回触 POST /api/refresh 形成"采集→事件→再采集"自激循环 (30 分钟节奏被打成连续抓取)
- **时间**: 2026-09-10 18:45
- **类型**: Bug修复
- **关联模块**: `frontend:sentinel-home`, `frontend:sentinel-judge`, `frontend:hooks/useSSE`, `frontend:hooks/useHotspotData`
- **关联文件**: `frontend/src/hooks/useSSE.ts`, `frontend/src/hooks/useHotspotData.ts`, `frontend/src/components/sentinel/SentinelHomePage.tsx`, `frontend/src/components/sentinel/SentinelJudgePage.tsx` (+ 同名 test ×3)
- **问题描述**: owner 报首页 (localhost:8898/) 刷新频率过高, 存在多次页面刷新与抓取, 要求前后端节奏一致 (选 30 分钟就 30 分钟, 手动刷新除外)。生产日志实测 (`backend/logs/app.log`, 2026-09-10): 页面未打开时调度器严格 30 分钟一轮 (17:10:51 → 17:40:51 → 18:10:51, 期间 0 次 `POST /api/refresh`); **首页打开的 17:26–18:10 这 44 分钟里, 采集启动 88 次、前端发出 `POST /api/refresh` 172 次**, 峰值单分钟 9 轮采集。DEV-0163 把后端节奏 5→30 分钟改对了, 但前端仍在回触采集, 所以 owner 感知不到任何变化。
- **根因** (三层叠加):
  1. `SentinelHomePage` 的 `useSSE({ onEvent })` **无事件类型过滤** — `/api/events` 推送 outbox 全部类型 (`collect_done` / `job_done` / `extract_done` / `alert` / `task_done` / `review_due` / 埋点 `view` `scroll` `dwell` …), 任意一条都触发首页三连: `reloadPipe()` + `loadSide()` (无节流, 2 请求) + 3s 后 `refresh()`。
  2. `useHotspotData.refresh()` = **`POST /api/refresh` (同步跑一轮完整 `run_once()`) + 重拉第 1 页** — 它被当成"刷新数据"用在 SSE 路径, 实际是"触发采集"。一轮采集结束发 `job_done` + `collect_done` 两个事件 → 3s 后再 POST → 再采集 → 无限自激, 周期 ≈ 3s + 采集耗时。
  3. `SentinelJudgePage` 同样无类型过滤且 `load()` 无节流 (只读, 不触发采集, 但每个无关事件都重拉 3 个接口)。
- **实现思路**: 把"拿新数据"与"触发采集"在 hook 层分离, SSE 路径只允许前者; 事件订阅收口到 `collect_done`; 过期文案改读后端真实间隔。不动后端 (调度/设置链路 `POST /api/settings/refresh-interval` → config + settings 持久化 + reschedule 本就完整), 不动 `SentinelShell.tsx` (并行会话正在做壳统一, 工作区有其半成品 diff)。
- **核心变更**:
  - `useSSE.ts`: 新增 `types?: string[]` 选项 (走 ref, 不触发重连); 声明后只有命中类型进 `onEvent`; `lastId` / `lastEvent` 仍对所有事件推进 (断线续传坐标不能因过滤而倒退)。
  - `useHotspotData.ts`: 新增只读 `refetch()` (清缓存 + 重拉第 1 页, 零 POST); `refresh()` 改为 `POST /api/refresh` 后复用 `refetch()`, 接口注释明确"仅供用户显式点击"。
  - `SentinelHomePage.tsx`: `useSSE({ types: ['collect_done'] })`; SSE 路径 3s 合并后调 `refetch()` (原 `refresh()`); 右栏 `loadSide` 加 10s 节流 (`SIDE_RELOAD_GATE_MS`, 与心跳条同频); 错误重试按钮与 URL 导入完成后改 `refetch()` (二者都不该起采集); 空态「立即采集」保留 `refresh()` = 手动刷新唯一入口; 页脚与空态的硬编码「每 5 分钟」改为挂载时 GET `/api/settings/refresh-interval` 的 `interval_minutes` (兜底 30); 文件头补"刷新节奏契约"说明。
  - `SentinelJudgePage.tsx`: `types: ['collect_done']` + 30s 节流 (与 SentinelGraphPage 同频)。Garden/Graph 页本就有 15s/30s 节流且需要非采集事件 (代码推送/编译), 不动。
- **测试验证**:
  - 新增回归 7 条: `useSSE.test` types 过滤 (4 事件只放行 1 条, lastId 推进 4 次, lastEvent 仍是被过滤的最后一条); `useHotspotData.test` refetch 全程 GET 零 POST / refresh 先 POST 后紧跟 GET; `SentinelHomePage.test` 新 describe 4 条 (collect_done 三连发 → 主列 1 次只读重拉 + 右栏 1 次 + **0 次 POST /api/refresh**; 8 种非采集事件 → 主列/右栏/心跳 0 次重拉 0 次 POST; 空态「立即采集」恰 1 次 POST; 页脚/空态显示接口返回的 60 分钟且不再出现"每 5 分钟")。用 `vi.useFakeTimers({ shouldAdvanceTime: true })` 瞬时跨过 3s 合并窗口, waitFor 仍可用。
  - `npx tsc --noEmit`: 本批文件 0 错 (工作区唯一错误 `SentinelShell.tsx` 未使用 `useLocation` 属并行会话半成品, 非本批); 全量 vitest **487/487 (63 文件)** = DEV-0166 基线 480 + 7 新增, 零回归; `vite build` exit 0。
  - **生产活体验证** (IAB 浏览器打开新代码首页, 页内挂 fetch 计数器 + 独立 EventSource 探针, 再 curl `POST /api/refresh` 模拟手动采集): 18:37:36 后端发 `collect_done` → 页面 18:37:36 右栏 quality/todos 各 1 次 → 18:37:39 (3s 合并后) `GET /api/hotspots` 1 次 → 快讯头更新为"刚刚"; **页面发出的 `POST /api/refresh` = 0**; 后端日志观察窗口内除手动那 1 轮外零新增采集。页脚实测显示"每 30 分钟自动采集 · 采集完成即刷新" (值来自接口)。旧代码下同一场景 3s 后必再起一轮。
- **潜在风险 / 遗留**:
  1. **既有 bug (本批发现未修)**: 首页/判断页的 `usePipeReloadOnSse()` 在 `SentinelShell` 的 `PipeContext.Provider` **之外**调用 (页面是壳的父组件; 文件内 `RailWithPipe` 注释已自述此坑), 拿到默认空 `reload`, 所以心跳条 (源在线/漏斗/队列) 在采集完成后**不会刷新**, 探针里也确实没有 `/api/sources/health` 请求。属"刷新不足"与本批"刷新过频"方向相反, 修法是把 collect_done 订阅挪进壳内自刷; 因 `SentinelShell.tsx` 正被并行会话改动, 留下一批。
  2. 手动 `POST /api/refresh` 走 `service.run_once()` 直调, 不经 `collect_all_job` 的 `@instrument_job`, 所以只发 `collect_done` 不发 `job_done`, 也不写 `job_runs`; 调度轮次两者都发。前端已只认 `collect_done`, 不受影响, 但观测面板的 job 计数会少算手动轮。
  3. 未做「前端按选定间隔自轮询」: 现在首页数据变化的唯一来源是 `collect_done` 事件与手动刷新, 若 SSE 长期断连 (自动重连 3s) 页面不会自行到点重拉——这是刻意选择 (再加轮询就又是两个时钟), 节奏由后端调度器单一持有。
  4. `/api/settings/refresh-interval` 的 `persisted_seconds` 当前为 null (owner 未在设置页改过), 生效值是 config 默认 1800s; 一旦在设置页选择新值会同时写 settings 表并 reschedule, 页脚下次加载即显示新值。
  5. 生产 dev server (8898) 已通过 HMR 提供新代码, 但 owner 已打开的旧标签页需**手动刷新一次**才脱离旧回调; 18:05 后日志已无风暴 (标签页当时已关)。

## [DEV-0168] 壳统一: 打散左侧 AppNav → 工具页走 SentinelShell 顶部横向导航, 左侧栏能力归位页内
- **时间**: 2026-09-10 18:59
- **类型**: 重构 (UI 一致性) + Bug修复
- **关联模块**: `frontend:page-layout`, `frontend:sentinel-shell`, `frontend:settings-hub`, `frontend:knowledge-tabs`
- **关联文件**: `frontend/src/components/PageLayout.tsx` + `.test.tsx`, `frontend/src/components/AppNav.tsx` + `.test.tsx` (删除), `frontend/src/components/sentinel/SentinelShell.tsx`, `frontend/src/components/sentinel/sentinel.css`, `frontend/src/components/sentinel/SentinelSettingsPage.tsx` + `.test.tsx`, `frontend/src/components/knowledge/KnowledgeTabs.tsx`, `frontend/src/routes/__tests__/v085_route_shell.test.tsx`, `frontend/src/routes/ROUTE_REGISTRY.md`, `frontend/src/AGENTS.md`, `AGENTS.md`, `docs/v0.8.5/V0.8.5_PLAN.md`
- **问题描述**: DEV-0166 修掉叠印后 owner 仍指出 `/settings` "存在双重前端、与首页不一致", 并裁决 "打散左侧菜单, 改横向菜单, 左侧菜单能力整合进各页面对应位置"。事实: 首页/判断层/行动层用 SentinelShell (顶部 appbar 三层导航 + 更多菜单 + 心跳条), 所有工具页却套 PageLayout + 左侧 fixed AppNav (v1.0 T17.5 遗留) — 两套壳并存; AppNav 的 14 项入口与壳内三层导航 / 更多菜单 / 各页内导航全量重复。另发现 `/settings` 的"哨兵"分类嵌入的 `SentinelSettingsPage` 自己又渲染一个 `<SentinelShell>` (页中页双 appbar), 以及 v0.8.5 C4 的 `/knowledge/v1` 知识目录在整个 UI 无任何入口 (注释写"更多→知识库→v1 目录"但从未实现)。
- **实现思路**: 遵 spec "唯一壳" 与 AGENTS "SentinelShell + 心跳条全站常驻": `PageLayout` 改为 `<SentinelShell layer={null}>` (三层 tab 不高亮, 更多菜单按当前路径高亮指示位置), AppNav 物理删除并加守卫双断言 (仿 V1SentinelShell 先例); 左侧栏能力去向逐项核对 — 三层入口=壳 tabs, SK 商店/SK-01..05=`/skill-store` 页内 v1 区块 (T15 已有), 知识管理导入/处理/编译/复利=`/knowledge` KnowledgeTabs (已有), 已导入=KnowledgeLayout 入口卡 (已有), 仅 `/knowledge/v1` 缺入口 → KnowledgeTabs 快捷模式补 `知识目录 v1`。设计技能按 AGENTS 硬约束 1 路由 `redesign-existing-projects` (Scan→Diagnose→Fix, 复用现有栈, 不引新视觉语言)。
- **核心变更**:
  - `SentinelShell.tsx`: `layer: SentinelLayer | null`; `ingested` 未传时壳自取 `GET /api/hotspots?category=all&time_range=24h&limit=1` total (与 Graph/Garden 页同口径, 避免工具页心跳条永远 "…"); `SentinelMoreMenu` 用 `useLocation` 计算当前工具页 → 按钮 `.active` + 菜单项 `aria-current="page"`。
  - `sentinel.css`: **元素级重置降特异度** `.sentinel a/button` → `:where(.sentinel) a/button` (0,0,1) — 否则 (0,1,1) 压过工具页 Tailwind 工具类; **`border:0` 改 `border-width:0`** — 简写会把 `border-style` 一起重置为 none, 而 Tailwind `.border` 只设宽度、样式靠 preflight `*{border-style:solid}`, 结果按钮边框全部消失 (实测 /skill-store 2 个按钮 0px 才发现); 新增 `.sn-more-btn.active` / `.sn-menu-item.active` (沿用 `.layer-link.active` 视觉)。
  - `PageLayout.tsx`: 去 AppNav 与 DEV-0166 的让位层, skip-link 前置于壳外, `#main-content` 保留 1320 居中容器 (去掉只为压 AppNav 的 `relative z-10`)。
  - `SentinelSettingsPage.tsx`: 去自嵌壳 (265 行回退 2 格缩进, `git diff -w` 仅 7 行), 心跳数据改由外层壳 `usePipe()` 供给; 测试改为真实组合渲染 (`<SentinelShell layer={null}><SentinelSettingsPage/></SentinelShell>`), 7 用例原断言 (含 `/api/sources/health` 只请求一次、`1 / 3`、FreeBuf 行) 全部保留。
  - `KnowledgeTabs.tsx`: MODE_ITEMS 增 `{ key: 'v1', label: '知识目录 v1', path: '/knowledge/v1' }`。
  - 守卫 `v085_route_shell.test.tsx` +3: AppNav fs 不存在 / grep 无引用 / PageLayout 含 `<SentinelShell layer={null}>`; `PageLayout.test.tsx` 改断言 `.sentinel` + `三层工作流导航` + `section.pipeline` + 无 `主导航`。
  - 文档: ROUTE_REGISTRY 工具页节 / frontend AGENTS 硬约束 0 (含 CSS 重置特异度约束) / 根 AGENTS 状态行 / spec §5 附 2026-09-10 修订注 (不改史)。
- **测试验证**:
  - `tsc --noEmit` 0 错; vitest **62 文件 487/487** (AppNav 3 用例随文件删除, 守卫 +3); `vite build --logLevel error` 通过。
  - 浏览器实测 (1440×900, 数值优先): `/settings` → `.sentinel` 根 1 / `header.appbar` 1 / `section.pipeline` 1 / 无 `nav[aria-label=主导航]` / 更多按钮 active / 今日收录 "443 篇" (壳自取生效) / 分类导航单列 x=97.5; `/settings?cat=sentinel` → appbar 1 + pipeline 1 (页中页消除) + READ-ONLY pill + 12 行源清单来自外层壳 context; `/skill-store` → 26/26 项 + "v1.0 受管能力包"区块 + 100+ 个 `.border` 按钮全部 1px solid; `/knowledge/import` → 四领域 nav + 快捷模式 `复习 | 知识目录 v1`(href `/knowledge/v1`) + 更多 active。截图: /settings 与 /knowledge 目视与首页同壳。
- **潜在风险**: ①工具页内容现在继承 `.sentinel` 基础排版 (15px/1.6, 原 body 13px) — Tailwind `text-*` 为 rem 不受影响, 但未显式设字号的文本会变大 ~15%, 本批只抽查了 settings/skill-store/knowledge 三页, `/secnews` `/todos` `/report` 等密集页建议 owner 过目 ②移动端 (<640px) 原 AppNav 汉堡抽屉随之消失, SentinelShell appbar 无响应式折叠 (与首页现状一致), 手机宽度可能横向溢出 ③`lazy-imports.ts` 仍导出未路由的 `SentinelSettingsPage` (死出口, 未清) ④各工具页自带的 "返回首页"/onBack 按钮与壳品牌/资料层 tab 功能重复, 本批未删 (可后续统一收敛) ⑤`max-w-[1320px]` 现在在壳内整屏居中 (无侧栏), 与 DEV-0166 说明的 "侧栏右侧居中" 不同 — 这是回到 T17.5 之前的状态。

## [DEV-0169] GET /api/skill-registry/v1 全量列表 500 (技能商店页 "Internal Server Error")
- **时间**: 2026-09-10 19:06
- **类型**: Bug修复
- **关联模块**: `api:skill-registry-v1`, `frontend:skill-store`
- **关联文件**: `backend/api/skill_registry_v1_api.py`, `backend/tests/test_skill_registry_v1.py`
- **问题描述**: DEV-0168 把 SK 能力包归位到 `/skill-store` 页内, 验收时页面显示 "Internal Server Error / 重试", 后端日志 `api_response status=500 error=ValueError`。复现: `_list()` 26 条里 20 条 legacy skill 的 `input_schema`/`output_schema` 值是 Python type 对象 (`{'top_n': int}`), v1 API `_skill_to_dict` 原样透传, FastAPI `jsonable_encoder` 遇 type 对象抛 ValueError; `?status=v1_active` 过滤时恰好只剩 6 条 schema 为字符串的 v1 SK 所以测试没红 — T14 当时的两个测试为此**特意绕开端点直接查 service** (docstring 自述)。
- **实现思路**: 与 legacy `skill_registry_api._json_schema` 同口径 — 类型对象 → `__name__`, 在 v1 API 内联 3 行 (不跨模块 import 私有函数)。
- **核心变更**:
  - `skill_registry_v1_api.py`: 新增 `_json_schema()`, `_skill_to_dict` 的 `input_schema`/`output_schema` 经其转换。
  - `test_skill_registry_v1.py`: 两个"绕开端点"的测试改回真实端点断言 (`?status=legacy_v0` → 200/20 条; `/source-health-scan` 详情 → 200 + status/version + schema 值全为 str), 新增 `test_api_list_all_26_serializes` 锁定无过滤全量列表 (页面实际调用)。
- **测试验证**: `pytest test_skill_registry_v1.py test_skill_registry_api.py` **37 passed**; ruff 触碰文件 0 错; 生产后端重启 (pid 95188 → 26603, `python run.py` 无热重载) 后 `curl /api/skill-registry/v1` → 200 / total 26 / `input_schema {'top_n': 'int'}`; 浏览器 `/skill-store` → 26/26 项 + "v1.0 受管能力包" 区块 + 无报错。
- **潜在风险**: ①`generate_meta --check` 未跑 (无新增 router/service, 计数不变) ②重启是本机开发后端, 并行会话若正依赖旧进程会有数秒中断 (已通过 /api/health 200 确认恢复) ③legacy skill 详情端点此前从未被真实调用过, 其它字段 (`target`/`prompt_template`) 序列化本批仅经列表用例覆盖。

## [DEV-0170] 工具页「返回」统一为智能返回 + 工具页字号/字体复位到 body 口径
- **时间**: 2026-09-10 21:43
- **类型**: 重构 (UI 一致性) + Bug修复
- **关联模块**: `frontend:hooks`, `frontend:page-layout`, `frontend:routes`, `frontend:tool-pages`
- **关联文件**: `frontend/src/hooks/useGoBack.ts` + `.test.tsx` (新), `frontend/src/hooks/useGoHome.ts` + `.test.tsx` (删除), `frontend/src/routes/index.tsx`, `frontend/src/components/PageLayout.tsx`, `frontend/src/index.css`, `frontend/src/components/sentinel/sentinel.css`, 16 个工具页/头部组件 (`TodosPage` `HistoryPage` `ReviewPage` `DeepReadPage` `KnowledgePage` `knowledge/KnowledgeLayout` `sync/index` `sync/SyncHeader` `settings/SettingsPage` `secrets/SecretsPage` `crm/CrmPage` `search/UnifiedSearchPage` `tags/TagsPage` `bid/BidAlertPage` `report/ReportPage` `extract/ExtractPage` `SkillsPage` `CodegardenPage` `CodegardenPhase2bPage`) + `ReviewPage.test.tsx` `KnowledgePage.test.tsx`
- **问题描述**: DEV-0168 壳统一后 owner 要求 "返回前页按钮优化、字号变化优化"。①16 个工具页各自渲染「← 返回首页」硬跳 `/`, 与壳的品牌锚点/资料层 tab 功能重复, 且从 /judge 点齿轮进设置再点返回会被甩回首页而非来路; 行为来源三套并存 (routes `onBack={goHome}` ×12 / 页内 `useGoHome()` ×7 / 路由包装内联 `navigate('/skill-store')` ×4)。②工具页被包进 `.sentinel` 后继承其 `font-family: var(--sn-sans); font-size:15px; line-height:1.6`, 而这些页面按 body 的 `var(--font-mono) 13px / 1.65` (手机·平板·≥1536px 为 14px) 设计 — 未显式设字号/字体的文本变大 ~15% 且等宽→无衬线。
- **实现思路**: ①新 hook `useGoBack(fallback='/')`: 读 `window.history.state.idx` (BrowserRouter 记录的站内栈深度, 首次落地/外站跳入为 0) — `idx>0 → navigate(-1)`, 否则 `navigate(fallback)`; 全部返回入口收敛到它, 文案统一「返回」(对两种行为都诚实), 详情类页面传 `fallback='/skill-store'`。②body 字号/行高抽成 `:root{--body-fs;--body-lh}` (三档媒体查询改写变量), PageLayout 内容容器加 `tool-main` 类, `sentinel.css` 以 `.sentinel .tool-main{font-family:var(--font-mono);font-size:var(--body-fs);line-height:var(--body-lh)}` 复位 — 壳 appbar/心跳条不受影响, 三层页 (不经 PageLayout) 不受影响。
- **核心变更**:
  - `hooks/useGoBack.ts` (新) + 4 测试 (稳定引用 / 无来路→`/` / 无来路+自定义 fallback→`/skill-store` / `idx=1`→`navigate(-1)` 回 `/judge`); `hooks/useGoHome.ts` + 测试删除 (零引用)。
  - `routes/index.tsx`: `goHome`(useCallback) → `goBack = useGoBack()`, 12 处 `onBack={goHome}` 改 `goBack`; SkillStore/SkillDetail/SkillBuilder/Dashboard 包装内联 navigate 改 `useGoBack()` / `useGoBack('/skill-store')`; 去掉不再使用的 `useCallback` 与 AppRoutes 内 `useNavigate`。
  - 7 个 `useGoHome()` 消费者改 `useGoBack()` (变量 `goHome`→`goBack`); 16 处 `返回首页` (title/aria-label/文本) → `返回`; `SettingsPage` 去 `useNavigate`, 按钮走 `useGoBack`。`ReviewPage.test` mock 路径与 `KnowledgePage.test` 用例名同步。
  - `index.css`: `:root{--body-fs:13px;--body-lh:1.65}` + 三档媒体查询改写 `--body-fs:14px`, body 改用变量 (计算值不变)。`sentinel.css` 新增 `.sentinel .tool-main` 复位规则 (含注释); `PageLayout` 容器加 `tool-main`。
- **测试验证**:
  - `tsc --noEmit` 0 错; vitest **62 文件 487/487** (useGoHome 4 例删 / useGoBack 4 例增); `vite build --logLevel error` 通过。
  - 浏览器实测 (1440×900, DOM 级点击 — 本 IAB 的 Playwright 可点击性等待整会话超时): /judge → 齿轮 → `/settings?cat=sentinel` (`history.state.idx=1`) → `#main-content` 计算样式 **13px / "JetBrains Mono" / line-height 21.45px (=13×1.65)**, `.sentinel` 根仍 15px, 按钮文案「返回」, 全页无「返回首页」→ 点返回落 **`/judge`** (idx 0); 直接落地 `/settings` (idx 0) → 返回 → `/`; 直接落地 `/skill-store/cve-impact-brief` → 「返回商店」→ `/skill-store`, 内容区 13px。
  - 验收前发现前后端进程均已不在 (非本会话操作, 疑并行会话/owner 停止), 以会话初始同款方式重新拉起 (`.venv/bin/python run.py` / `npm run dev`), 后端 200 前端 200。
- **潜在风险**: ①`history.state.idx` 是 React Router BrowserRouter 的实现细节 (v6 起稳定, 非公开 API), 若升级 v7 需回归 `useGoBack.test` 第 4 例 ②同 tab 内从外站链接进入某工具页时 idx=0 → 回 fallback (设计如此); 但用户在本应用内用地址栏手动输 URL 也会 push 一条 idx>0 的记录, 此时「返回」会回到输入前的页面 (符合浏览器直觉) ③SkillDetail 自带文案「返回商店」未改 (来路是商店时同样正确) ④`--body-fs` 变量新增于 `:root`, 与 `[data-theme]` 等其它 :root 块并存无冲突, 但第三方样式若依赖 `body{font-size:13px}` 字面值 (grep 无) 会失配 ⑤三层页 (SentinelHomePage 等) 内嵌的 v1 区块若曾在 PageLayout 下设计, 现在仍吃 15px 壳排版 — 本批只复位 PageLayout 工具页, 三层页排版是 spec 认定的终端风格未动。

## [DEV-0171] 壳窄屏适配 (三层导航不再隐藏) + 心跳条 SSE 刷新断链修复 + 设置页手机布局
- **时间**: 2026-09-10 22:29
- **类型**: 功能开发 (响应式) + Bug修复
- **关联模块**: `frontend:sentinel-shell`, `frontend:settings-hub`
- **关联文件**: `frontend/src/components/sentinel/sentinel.css`, `frontend/src/components/sentinel/SentinelShell.tsx` + `SentinelShell.test.tsx` (新), `frontend/src/components/settings/SettingsPage.tsx`, `frontend/src/components/settings/settings-shell.css`
- **问题描述**: owner 要求把 DEV-0168/0170 报告里"需补充考虑和增强"落地。①DEV-0168 未实现项: AppNav 汉堡抽屉删除后, 壳在 ≤820px 直接 `.layers{display:none}` 把三层导航整条隐藏, 窄屏只剩品牌 (回首页) 和更多菜单 (无判断层/行动层), 工具页也一样 — 判断层/行动层在手机上不可达。②并行会话记忆里的待修项 (树已干净、无人在改): 4 个三层页 (Home/Judge/Graph/Garden) 在组件体内调 `usePipeReloadOnSse()`, 但壳是它们自己渲染的子节点, hook 跑在 `PipeContext.Provider` 之外只拿到默认 `reload: () => {}` — SSE `collect_done` 后心跳条从未真正刷新过 (DEV-0167 只修了自激循环, 这条断链仍在)。③验收时发现 SettingsPage 自身在 <640px 仍是分类导航+内容左右并排, 内容被挤成 ~80px 宽的竖字列。
- **实现思路**: ①响应式改"隐藏"为"折叠": ≤820px 紧凑态 (去箭头/副标签、缩 padding、隐藏品牌副标), ≤640px 顶栏 `flex-wrap` 折成两行 (品牌+右侧操作 / 三层导航独占一行三等分)。②不改 4 个页面 (并行会话领域): 壳挂载时把 `reload` 登记到模块级 `mountedReload`, `usePipeReloadOnSse` 用 `(mountedReload ?? reload)()` — Provider 内 (工具页) 二者相同, Provider 外 (三层页) 走登记值; 卸载时若仍是自己则清空 (路由切换时新壳覆盖)。③设置页主区 `flex-col sm:flex-row`, <640px 分类导航横滚一行 (隐藏描述、nowrap)。
- **核心变更**:
  - `sentinel.css`: ≤820 块 `.layers{display:none}` → 紧凑态 6 条规则; 新增 ≤640 块 (appbar 换行、layers order:3 占满、layer-link 三等分居中、pipeline/pipe-block 缩边距)。
  - `SentinelShell.tsx`: 模块级 `mountedReload` + 登记/清理 effect + `usePipeReloadOnSse` 兜底; `usePipe` docstring 注明 pipe 只在壳子树内可读。
  - `SentinelShell.test.tsx` (新, 4 例): 页面渲染壳结构下 hook 在 Provider 外触发 `/api/sources/health` 第二次请求 / layer=null 无 tab 高亮 + 更多按钮 active + 菜单项 `aria-current=page` / layer=judge 时判断层高亮更多不高亮 / ingested 未传显示 "7 篇"、传 null 保持 "…"。
  - `SettingsPage.tsx` 主区 `flex-col sm:flex-row`; `settings-shell.css` 新增 <640 媒体查询 (sidenav row + overflow-x + item nowrap + desc 隐藏)。
- **测试验证**:
  - `tsc --noEmit` 0 错; vitest **63 文件 491/491** (+4); `vite build --logLevel error` 通过。
  - 浏览器实测: **390×844** `/settings` → appbar 92px 两行、三层链接 3 个可见各 118px、品牌副标隐藏、`documentElement.scrollWidth 385 ≤ 390` 无横向溢出、分类导航 `flex-direction:row` 高 41px、内容全宽 353px、正文 14px (body 手机档经 `--body-fs`); **768×1024** `/judge` → appbar 60px 单行紧凑、3 链接可见、无溢出; **390** `/judge` → 92px 两行、无溢出。截图 390 设置页目视: 壳两行 / 心跳条 2 列 / 分类横滚 / 体检卡片可读。
- **潜在风险**: ①`mountedReload` 是模块级单例, 同一页面树同时挂两个壳时以后挂的为准 (当前架构每路由只有一个壳, 测试里 unmount 后再 render 亦正常) ②`usePipe().pipe` 在 Provider 外仍为 null (只修了 reload 断链); 三层页读 pipe 的地方均在壳子树内 (RailWithPipe 等), 若将来在页面组件体直接读 pipe 会拿到 null — 根治仍是「SentinelLayout 从布局层提供壳」, 涉及并行会话正在动的 4 个页面, 本批不越界 ③≤640 两行顶栏使壳增高 32px, 三层页首屏可视区相应减少 ④设置页横滚分类导航无滚动提示 (依赖系统滚动条/手势), 17 项需左右滑动才能全部看到。

## [DEV-0172] 全部分支收敛合入 main + 端口冲突裁决 + 设置页测试竞态修复
- **时间**: 2026-09-11 10:50
- **类型**: 配置变更 (分支合并) + Bug修复 (测试竞态)
- **关联模块**: `repo:branches`, `scripts:dev-environment`, `frontend:settings-hub`
- **关联文件**: `scripts/dev_environment.sh`, `frontend/package.json`, `PROGRESS.md`, `PROJECT.md`, `frontend/src/components/sentinel/SentinelSettingsPage.test.tsx`
- **问题描述**: owner 要求把所有分支合并到 main。盘点 21 个本地分支: 16 个已在 main 祖先链上; 4 个未合 — `fix/source-cadence-health` (领先 32, 含 `fix/v085-review-p0` 全部 18 提交) / `chore/port-frontend-8898-20260908-1925` (领先 2, 含 `layout-opt-20260908-1920` 唯一提交 ac1311d)。合并第二笔时 4 文件冲突, 根因是**两个并行会话前后 8 分钟各做了一版端口统一**: `6e17722` (23:07, chore/port: 后端 dev 8766 错开 / 前端 8898) 与 `7397c59` (23:15, 已随 v085-review 入 fix/source-cadence-health: 后端 dev/prod 共用 8000 / 前端 8898)。后者是终版策略, 但其 `dev_environment.sh` 漏改了 `DEV_PORT_FRONTEND:-8899` 与两处注释 (与自身设计原则段写的 8898 自相矛盾, 且与 `package.json dev` 的 `--port 8898 --strictPort` 不一致)。
- **实现思路**: 全部 `--no-ff` 保留分支拓扑证据; 冲突以后合入的终版策略 (HEAD) 为准, 唯 `dev_environment.sh` 做混合裁决 — 后端口径取 HEAD (8000 共用), 前端默认值取分支侧 8898 (7397c59 的漏改项), 使脚本/package.json/status 探测三处口径完全一致。剩余 2 分支补合并确认 (Already up to date)。合并后跑三门验证; vitest 唯一失败为 DEV-0171 自带的竞态 (文件与分支顶点 88b29e5 逐字节一致, 非合并引入), 按同文件 L192 同款 `waitFor` 修复。
- **核心变更**:
  - 合并提交: `df11910` (fix/source-cadence-health, 224 文件 +7765/−3536) / `237a1e6` (chore/port-frontend-8898, 9 文件)。`fix/v085-review-p0` 与 `layout-opt-20260908-1920` 为已包含分支, 无新提交。
  - `scripts/dev_environment.sh`: 5 处冲突 → `DEV_PORT_FRONTEND` 默认 8899→**8898**, 用法注释 start-frontend 8899→8898, 其余 4 处取 HEAD (8000 共用 + 两条 ⇒ 说明 + 状态日志措辞 + start-frontend 段注释)。`bash -n` 通过。
  - `frontend/package.json` `dev:demo`: 取 HEAD, 去掉分支侧 `HOTSPOT_BACKEND_PORT=8766` (后端已共用 8000, `vite.config.ts` 默认回落 8000)。
  - `PROGRESS.md` D2 行 / `PROJECT.md` 铁律 6: 取 HEAD (8898→8000 固定对措辞)。
  - `SentinelSettingsPage.test.tsx` L149: `KEY READY` 断言由同步 `getByText` 改 `waitFor` — `keyReady` 来自 `/api/secrets/status` 异步回包, 前置 `waitFor(tabpanel)` 不保证该请求已回, 未回时渲染 `KEY NOT SETUP`。本机修前 3/3 失败, 修后 3/3 通过。
- **测试验证**:
  - `git branch --no-merged main` → 空 (21/21 全部已合)。
  - 前端: `tsc --noEmit` 0 错; vitest **63 文件 491/491** (修前 490/491); `vite build --logLevel error` exit 0。
  - 后端: `pytest backend/tests/` **4426 passed / 9 skipped / 1 failed** (9m17s)。唯一失败 `test_ai_hub_failover.py::TestGatewayWiring::test_unhealthy_verdict_auto_trips_mid_stream` — 单测重跑 PASSED (0.58s), 整文件 12/12 PASSED (1.37s): 全量高负载下的时序 flaky (依赖 `RECOVERY_TIMEOUT=0.05s` 级时间窗), ai_hub 相关文件本次合并未触碰; 位于 ai_hub 红线区 (AGENTS.md 未裁决前勿动), **本批不修, 仅标注**。
  - 未推送远端 (owner 2026-09-05 禁令仍有效)。
- **潜在风险**: ①HEAD 由 `fix/source-cadence-health` 切到 `main`, 若并行会话仍在该特性分支上工作, 其后续提交需再次合入 main ②`chore/port` 分支设想的 "dev 后端 8766 与生产 8000 并存" 用法随本次裁决失效 — dev/prod 后端任一时刻只能跑一份, 切换前必须 `dev_environment.sh stop` (脚本注释已写明); 若 owner 仍需双后端并存, 需重新裁决端口策略 ③ai_hub failover 时序 flaky 在 CI 全量跑时可能复现, 建议单独立项收敛 (放宽时间窗或注入时钟), 不应在合并批里顺手改 ④Mimosa 本次提交前未给出完整扫描结论 (scanner_enobufs), 不宣称安全。

## [DEV-0173] 架构图重梳 v0.8.0 → v0.8.5 (archify) — 补信源采集侧 + 数字刷新 + 结论卡片
- **时间**: 2026-09-11 11:15
- **类型**: 配置变更 (架构图产物, `hotspot-architecture.candidate.json` 唯一编辑入口)
- **关联模块**: `docs:architecture-diagram`
- **关联文件**: `hotspot-architecture.candidate.json`, `hotspot-architecture.html` (archify deliver 生成, 不手改)
- **问题描述**: owner 指令 "$archify 梳理当前整个代码仓库的架构情况"。入仓 candidate 停在 v0.8.0 (2026-09-04): 数字全部过时 (53 路由 / 73 routers / 107 services / 51 jobs vs 权威 `generate_meta.py` **85 routers / 126 services / 58 jobs / 14 collectors**); runner 名 `claude` 与代码枚举 `SkillRunner = Literal["builtin","pi","claude-code","codex"]` 不符; **整条信源采集侧没有任何节点** — 而 DEV-0163~0167 (采集节奏 / 存活有用分离 / 代理内置 / 国际国内归属) 恰是本轮合并的主体, 且 14 collectors 是仓内最大的代码域之一。
- **实现思路**: 遵守 AGENTS.md 硬约束 (viewBox 宽 ≤~1390 / 列距 ≥40 / 副标签按盒宽预算 / **加节点必先删节点**): 删 `webdav` 节点 (事实迁入卡片), 加 `ingest` 节点置于左下空位 (x 40..380, y 540..610, 不新增列, 宽度保持 1340), 一条强调边 `ingest → repository` "入库 hotspots · source_stats" 表达资料层落库; 调度关系写进副标签 (`collect_all 30min 单闸口`) 不再加边, 避免 services 出边 ≥4 触发 super-hub 陷阱 (memory 已记)。拓扑之外的架构事实 (数字门禁 / 三层壳 + v1.0 域 / 信源管道 + 数据备份) 用 3 张结论卡承载。所有写入图中的数字逐项核实: 57 Route (`grep -c "<Route " routes/index.tsx`), 13 gates (`feature_gates.toml`), MCP 19 tools (`test_mcp_server.py` 断言), 5 providers (`config/llm.yaml`), 101 信源 (`sqlite3 -readonly backend/hotspot.db`), HOT 36MB / WARM 865MB, dsh :3210 (`services/dsh/supervisor.py`)。
- **核心变更**:
  - components 11 → 11: `-webdav` `+ingest` (type backend, 340×70); 副标签刷新: frontend ":8898 · 三层壳 · 57 Route" / api ":8000 · 85 routers" / runners "4 Runners · 26 Skills" + `claude-code` 正名 / services "126 services · 58 jobs" / repository "WAL · ATTACH · FTS5 · Fernet"。
  - boundaries 3 → 4: 新增 region "Ingest (信源采集)" 包 `ingest`; "Outbound" 仅剩 `llm`。
  - connections 11 → 11: `-repository→webdav` `+ingest→repository` (emphasis, right→left)。
  - cards 0 → 3 (每卡 2 条短句); views 4 条 note 刷新 (ingest-and-ops 改为 "101 信源 → 14 collectors → 门禁/去重/评分 → HOT 库 → SSE 心跳条")。
  - 标题 "Hotspot v0.8.5 — 三层壳 · Skills · 信源管道" (去掉 "Sentinel" 避免 1440 下换行成孤立 "· 信源管道")。
- **测试验证** (实现与验证分离, 以下均为工具回执非自评):
  - `archify validate --quality showcase`: 修复 3 轮后 **9/9 artifact checks, composition errors 0 / warnings 0**。修复链: ①api 副标签 ":8000 · 85 routers · 13 gates" 被压至 8.1px → @1440 投影 5.62px < 6px 下限 → 缩回原长; ②ai_hub "· 断路器" 同样 8.4px → 5.83px → 缩回; 两条正是 AGENTS.md 写明的 "context 字号 9px 上限 × 投影 ≥6px @1440" 约束。
  - `archify deliver`: spec sha256 `86635baac9d1…` 7,778 B → HTML sha256 `846d0d3178b4…` 718,930 B, exit 0。
  - `archify visual-check` (真实浏览器): 首轮 **fail** — 4 卡 12 条长文致 1440×900 scrollHeight 1209 / 1600×1000 1291 / 1920×1080 1291 纵向溢出 (2048×1320 才容下); 压成 3 卡 6 短句后 **4 视口全 pass** (scrollH == innerH), 可读性 pass (最小投影 6.25px = frontend 副标签)。
  - 感知复核 (本人目视 1440×900 + 2048×1320 截图): 无边交叉 / 无标签遮挡 / 卡片一行 / 大屏无空白下带; 标题单行。
  - 旁证 `hotspot-architecture.visual-check.*` 已在 `.gitignore` 129-134 行, 不入仓。
- **潜在风险**: ①WebDAV 从拓扑节点降为卡片一句, 备份链在图上不再有边; 若 owner 要恢复节点, 右上 (x 690..1040, y 60..150) 仍有空位但需先解决 `dsh→ai_hub` 虚线走廊 (y≈215) 的穿越 ②`ingest` 只有一条出边, 调度触发关系靠副标签隐含 ③frontend 副标签投影 6.25px 已贴地板, 再加任何字符即破 6px 门 ④卡片文案为压缩版, 长文事实见本条与 PROGRESS; 复跑 `archify deliver` 会覆盖入仓 HTML, 改图只改 candidate。

## [DEV-0174] 工作台聚焦裁决落账: 双视角方案否决 + 内容相关性门禁立项 (PRD/DEV_PLAN/spec 修订注)
- **时间**: 2026-09-12 00:35
- **类型**: 配置变更 (方案文档族 + spec 修订注, 零代码改动)
- **关联模块**: `docs:workbench-focus`
- **关联文件**: `docs/WORKBENCH_FOCUS_PRD_v1.0.md` (新建), `docs/WORKBENCH_FOCUS_DEV_PLAN.md` (新建), `docs/v0.8.5/V0.8.5_PLAN.md` (§5 后追加 2026-09-12 修订注), `docs/README.md` (当前权威表登记)
- **问题描述**: owner 在知识复利评审后先提出「安全研究/标讯跟踪双视角切换」需求并要求落 docs 方案 + goal; 随后改裁决: **去掉标讯部分, 专注安全从业者 AI 工作台**。需按仓库惯例落正式方案文档 + v0.8.5 spec 修订注 + 开发目标 (含收尾独立 agent 验收/审计要求), 且不得残留已否决方案的执行项。
- **实现思路**: 方案内容整体换血——双视角(研究/标讯)的视角轴/双业务流/双画像全部否决, 标讯维持现状 (Feed `bid` 分类档 + `/bid-alert` 工具页, 均为 spec §5 现有条目, 本轮核实过 `/bid-alert` 已在 `routes/index.tsx:204` + lazy-imports + ROUTE_REGISTRY 登记, 此前"孤儿组件"判断有误已更正); 立项内容改为知识复利评审识别的真缺口: **内容相关性门禁/实践域兴趣体系** (12 道质量门禁管"好不好", 新增实践域层管"对你是否有用", 落点 `backend/services/auto_classifier.py` 三级打标已有 + info_filter 管噪音正交)。文档按 SKG 先例 PRD+DEV_PLAN 成对; 修订注按 DEV-0168 引用块先例; 被否决方案以裁决表 (PRD §0 R1-R3) 留痕防回摆。
- **核心变更**:
  - `docs/WORKBENCH_FOCUS_PRD_v1.0.md`: 裁决记录 R1 (否决双视角) / R2 (标讯维持现状) / R3 (聚焦立项); 问题定义 (质量门禁 vs 内容门禁正交, 现状仅源级 Category 8 域 + info_filter 关键词两粒度); P0 = 实践域词表 (auto_classifier 二级 8 域) + 标注集 60→80 (顺带关闭 v1.0 T00 悬置裁决) + 兴趣画像 (settings.kv + GET/PATCH /api/settings/interests) + Feed 排序接线 (降权不删) + SK-01 摘要分区; P1 标签统一/动线强化; P2 行为反馈; 非目标显式排除标讯视角/契约变更/向量检索; 红线 = 零新路由 + ai_hub 不动 + 不动 13 gate。
  - `docs/WORKBENCH_FOCUS_DEV_PLAN.md`: GOAL 声明 + DoD (tsc/vitest/pytest/generate_meta --check + 向后兼容断言 + **独立 agent 功能验收与 code-reviewer 审计双门, 实现会话不得自评 PASS**) + T0.1-T0.5 任务分解 (各带退出判据) + 收尾流程 + 风险表。
  - `docs/v0.8.5/V0.8.5_PLAN.md`: §5 路由表后追加 2026-09-12 修订注 (双视角否决, spec §5/§6/§10 不受影响, 指向新 PRD/DEV_PLAN)。
  - `docs/README.md`: 当前权威表登记两份新文档。
- **测试验证**: 纯文档批, 无代码门禁可跑; 事实核对均在本会话完成: `auto_classifier.py` 三级打标结构与消费方 (collect/knowledge jobs + knowledge API + compiler; digest.py 经 compiler 间接)、`Category` 8 枚举值、settings.py:142 kv+audit 先例、`/api/v1/knowledge/{id}/reuse`、`knowledge_review.py` 每日 job、`/bid-alert` 路由接线。**独立 agent 文档审计已完成** (code-reviewer, 非作者会话): 13 检查项 **13 PASS / 0 FAIL, 0 P0 / 0 P1 / 6 P2**, 报告 `.ua/tmp/audit-workbench-focus-docs.md`; 4 条事实性 P2 已当场修正 (①先例端点实为 `POST /api/settings/llm-provider` 非 PATCH ②`bid_region` 字段不存在, 实为共享 `region` 字段由 `_extract_region` 填充 ③digest.py 为间接消费 ④"每周人工审计"改为 P1 新建机制非既有能力); 其余 2 条 P2 (词表运营细节、`backend/quality/pipeline.py` docstring 陈旧写"9 道"——非本批引入) 留待后续批次。
- **潜在风险**: ①PRD 中 P0 排序加权"向后兼容断言"依赖固定种子 fixture, 现有 content API 测试未必有该基建, T0.4 开工时可能需先补 fixture ②实践域词表 8 域划分为本方案新设, 未经真实语料验证, T0.2 标注集扩展即首轮验证, 不准则按 DEV_PLAN 风险表升级 P1 LLM 分类 ③本批只落规划, 双视角方案 若未来重启须新立 PRD 不得直接复活本文被否决条款。

## [DEV-0175] T0.0 剔除工作台标讯功能 (owner 追加裁决 R2' 取代 R2) — /bid-alert 全链下线 + 资讯流默认排除 bid
- **时间**: 2026-09-12 07:15
- **类型**: 功能开发 (功能剔除) + 配置变更 (PRD R2 裁决更新)
- **关联模块**: `frontend:routes`, `frontend:sentinel-shell`, `frontend:feed`, `backend:api/hotspots`, `backend:services/hotspot_service`, `backend:repository/hotspot_repo`
- **关联文件**: `frontend/src/routes/index.tsx`, `frontend/src/routes/lazy-imports.ts`, `frontend/src/components/bid/BidAlertPage.tsx` (删除), `frontend/src/components/sentinel/SentinelShell.tsx`, `frontend/src/components/sentinel/SentinelHomePage.tsx`, `frontend/src/components/sentinel/SentinelJudgePage.tsx`, `frontend/src/components/secnews/feed/FeedFilters.tsx`, `frontend/src/types/index.ts`, `frontend/src/types/index.test.ts`, `frontend/src/contexts/I18nContext.tsx`, `frontend/src/hooks/useHotspotData.ts`, `frontend/src/routes/ROUTE_REGISTRY.md`, `backend/api/hotspots.py`, `backend/services/hotspot_service.py`, `backend/repository/hotspot_repo.py`, `backend/tests/test_hotspots_api.py`, `docs/WORKBENCH_FOCUS_PRD_v1.0.md`
- **问题描述**: owner 裁决"剔除和安全从业者 AI 工作台中标讯相关的功能"，取代 PRD 初版 R2"标讯维持现状"。标讯触点 11 处 (路由/懒加载/组件/壳菜单/Feed chip/i18n 双语/首页与判断页分类数组/共享 CATEGORIES 枚举/资讯流数据)。
- **实现思路**: 分层剔除——①UI 功能面全删 (路由+懒加载+组件+菜单入口+chip+枚举+双语 key); ②数据面用新增的 `exclude_category` 查询参数在资讯流默认排除 bid (repo WHERE `category != ?` → service 透传 + 缓存键 + balanced 整桶跳过 + total 同口径 → router Query 参数), **不传参数时行为与既有版本逐字节一致** (向后兼容, API 契约不变); ③后端 `/api/bid-alert/*` 与 bid 采集器暂保留 (数据层不动, 是否停采待 owner 另行裁决); ④TS 类型联合保留 `'bid'` (存量 bid 数据反序列化兼容), 仅从展示枚举/筛选档移除。修复过程发现: `list_cache` 模块级 TTL 缓存跨测试污染 (先跑的用例缓存空结果, 后用例同 key 命中脏数据), 新增 autouse fixture 清缓存。
- **核心变更**:
  - backend/api/hotspots.py: `list_hotspots` 新增 `exclude_category` Query 参数, 透传 service; 不传=行为不变
  - backend/services/hotspot_service.py: `list_hotspots`/`_query_balanced` 新增参数; 缓存键纳入该参数; balanced 模式命中分类整桶跳过; total 走 `count_unique_urls_in_range(exclude_category=...)` 保持 "X / Y" 分母同口径
  - backend/repository/hotspot_repo.py: `query`/`count_unique_urls_in_range` 新增 `exclude_category` WHERE 条件
  - frontend: 路由 `/bid-alert` 删除 (index.tsx:204), lazy-imports BidAlertPage 导出删除, `components/bid/BidAlertPage.tsx` git rm, SentinelShell 溢出菜单"标书提醒"项删除, FeedFilters bid 档删除, I18nContext `feed.filter_bidding` 双语 key 删除, SentinelHomePage CHANNEL_DEFS/SentinelJudgePage SIGNAL_DEFS bid 项删除, types/index.ts CATEGORIES bid 项删除 (类型联合保留)
  - frontend/src/hooks/useHotspotData.ts: 请求参数固定追加 `exclude_category=bid` (全站资讯流默认排除标讯)
  - ROUTE_REGISTRY.md: 移除 /bid-alert 行 + 剔除留痕注
  - docs/WORKBENCH_FOCUS_PRD_v1.0.md §0: R2 → R2' (剔除裁决)
- **测试验证**:
  - `pytest backend/tests/test_hotspots_api.py`: **9 passed** (新增 TestExcludeCategory 3 用例: 排除生效/不传兼容/total 同口径; 首轮暴露 list_cache 跨测试污染, autouse fixture 清缓存后全绿)
  - `pytest test_hotspots_api + test_api + test_cache`: **80 passed** (列表/缓存相邻域无回归)
  - `npx tsc --noEmit`: 0 错; `npx vitest run`: **491 passed** (types/index.test.ts 2 个 bid 断言按剔除裁决同步更新为兜底行为断言); `npx vite build`: OK
- **潜在风险**: ①bid 采集器仍在采集入库 (数据层未动), 若 owner 确认彻底停采, 需在 `scheduler.py` job 门控或 collector 注册层处理并同步 feature_gates ②历史收藏/浏览历史/统一搜索中残留的 bid 条目仍可见 (数据非功能), HotspotCard 的 bid_status 徽标保留以正确渲染存量 ③`/api/hotspots` 不传新参数的第三方消费者 (MCP 工具等) 完全不受影响

## [DEV-0176] T0.1 实践域词表 — auto_classifier 二级 8 域打标 (Workbench Focus P0.1)
- **时间**: 2026-09-12 07:20
- **类型**: 功能开发
- **关联模块**: `backend:services/auto_classifier`
- **关联文件**: `backend/services/auto_classifier.py`, `backend/tests/test_auto_classifier_practice_domain.py` (新建)
- **问题描述**: 质量门禁只管"信息好不好", 缺"对安全从业者是否有用"的实践域层。PRD P0.1 要求在既有三级粗粒度打标 (tag→title→URL) 之上新增面向安全从业者的实践域词表。
- **实现思路**: 纯规则、零 LLM、零 schema 变更。新增 `PRACTICE_DOMAINS` 8 域常量 (enterprise_security 企业安全建设 / vuln_research 漏洞研究 / threat_hunting 威胁狩猎 / incident_response 应急响应 / ai_security AI 安全 / appsec 应用安全 / cloud_data_security 云与数据安全 / compliance 合规监管) + `PRACTICE_DOMAIN_LABELS` 中文标签 + `TAG_PRACTICE_MAP` (键序即优先级, 具体 tag 先于泛化) + `TITLE_PRACTICE_RULES` (数组序即优先级, AI安全→漏洞→狩猎→应急→应用→云数据→合规→建设); 新增 `classify_practice_domain(tags, title)` (仅两级: tag→title, 不用 URL 级——URL 域只能判粗类), `classify_item`/`batch_classify` 透出 `practice_domain` 键。**设计取舍**: ①非安全内容 (finance/dev/startup) 返回 None——相关性门禁靠"命中加权/未命中降权"消费, 不要求全量覆盖; ②消费方 (collect/knowledge jobs) 按白名单字段落库, `practice_domain` 不进 knowledge_items 表, 资讯流在 T0.4 查询时即时打标, 存储零迁移; ③"漏洞管理"tag 映射 enterprise_security (管理流程属建设), 具体漏洞研究靠标题关键词。
- **核心变更**:
  - auto_classifier.py: +PRACTICE_DOMAINS/PRACTICE_DOMAIN_LABELS/TAG_PRACTICE_MAP (44 键)/TITLE_PRACTICE_RULES (8 pattern) + classify_practice_domain() + classify_item/batch_classify 透传 practice_domain + __all__ 扩 3 项
  - 既有 classify_domain/TAG_DOMAIN_MAP 零改动 (回归保障)
- **测试验证**:
  - 新建 `test_auto_classifier_practice_domain.py`: **46 用例全绿** (14 tag 正例 + 16 标题正例覆盖 8 域各 2 + 4 非安全反例 + 空输入 + 词表完整性 3 + 集成透传 3); 首轮 1 例失败 (Kubernetes 带空格), 正则加 `\s*` 修复
  - 既有 `test_auto_classifier.py` 回归: 全绿 (61 total passed)
- **潜在风险**: ①规则词表对真实语料的覆盖率未验证, T0.2 标注集扩展 (60→80) 是首轮人评验证, 抽样准确率 <80% 则按 DEV_PLAN 升级 P1 LLM 分类 ②TITLE_PRACTICE_RULES 顺序敏感 (如"SQL注入"命中 vuln_research 而非 appsec), 调整顺序会改变结果, 词表变更须跑全量测试

## [DEV-0176b] T0.2 标注集 60→80 — practice_domain 评测语料 (Workbench Focus P0.2, 关闭 T00 悬置裁决)
- **时间**: 2026-09-12 07:40
- **类型**: 功能开发 (数据语料) + 配置变更 (关闭 v1.0 T00 悬置裁决"标注集 60-80")
- **关联模块**: `backend:tests`, `scripts:check`
- **关联文件**: `backend/tests/fixtures/practice_domain_eval.json` (新建), `scripts/check_practice_domain_lexicon.py` (新建), `backend/tests/test_practice_domain_corpus.py` (新建)
- **问题描述**: DEV_PLAN T0.2 要求标注集 60→80 且覆盖 8 实践域。原 60 条 admission 8 维标注在 `dev_data/` (gitignored 本地资产, 生产脱敏数据不入仓), 且其 material 标题已脱敏为无意义串, 无法承载实践域真值。**执行中纠偏**: 初版把评测段写进 dev_data seed 文件, 提交时发现该文件从未入仓 (此前误读 check-ignore 输出), 且依赖它的测试会在 CI/新 clone 失败——已还原本地文件, 语料改为入仓 fixture。
- **实现思路**: **总量 80 = 60 admission 标注 (dev_data 本地, 维持不入仓) + 20 practice_domain 评测条目 (入仓 fixture)**。fixture 20 条纯合成中文标题 (无生产数据), 每条带真值 practice_domain (8 域每域 ≥2: ai_security 3 / cloud 3 / compliance 3 / enterprise 3 / 其余各 2)。配套: ①`check_practice_domain_lexicon.py` 检查脚本 (只读, --check CI 模式: 语料 20 条/每域 ≥2/真值合法/词表重打标 100% 四项), **诚实口径: 语料与词表同源, 是回归护栏而非无偏准确率评估**, 无偏人评属 P1 运营机制; ②结构测试 4 用例。t07 loader 只读 dev_data 文件的 annotations 键, dry-run 实测 60 条不受影响。
- **核心变更**:
  - backend/tests/fixtures/practice_domain_eval.json: 20 条评测语料 + _meta (同源护栏口径声明)
  - scripts/check_practice_domain_lexicon.py: 评测 + 回归护栏脚本
  - backend/tests/test_practice_domain_corpus.py: 4 用例 (20 条/每域 ≥2/真值合法字段齐/id 唯一)
  - dev_data/annotation_set_seed_60_80.json: 短暂修改后已还原 v1.0 (未入仓, 不在提交内)
- **测试验证**:
  - `check_practice_domain_lexicon.py --check`: **20/20 = 100%, 8 域全 OK, exit 0**
  - `pytest test_practice_domain_corpus.py`: **4 passed**
  - `t07_seed_label_set.py` dry-run: annotation rows 60 (loader 兼容)
- **潜在风险**: ①20 条全打准是同源护栏的预期结果, **不代表真实语料准确率**——无偏评估待 P1 词表运营机制 ②"总量 80"的 60 侧为本地不入仓资产, 裁决关闭的完整证据链 = 本条 DEV_LOG + fixture _meta.notes ③fixture 与词表同源, 改词表必须同步改语料并保持 --check 100%, 否则 CI 护栏会正确地拦下

## [DEV-0176c] T0.3 兴趣画像 — interests API + 设置页"我的方向"卡片 (Workbench Focus P0.3)
- **时间**: 2026-09-12 07:40
- **类型**: 功能开发
- **关联模块**: `backend:api/settings`, `frontend:settings`
- **关联文件**: `backend/api/settings.py`, `backend/tests/test_settings_interests.py` (新建), `frontend/src/components/settings/PracticeDomainsCard.tsx` (新建), `frontend/src/components/settings/PracticeDomainsCard.test.tsx` (新建), `frontend/src/components/settings/SettingsPage.tsx`
- **问题描述**: PRD P0.3 要求前端可勾选实践域画像并持久化, 供 T0.4 排序加权与 T0.5 摘要分区消费。
- **实现思路**: 完全复用 settings.py 既有 kv+audit 先例 (llm.provider 模式): `GET /api/settings/interests` 读 settings.kv `interest.practice_domains` (服务端按词表过滤脏值, 空=无画像), `PATCH` 全量提交 (服务端校验域合法 + 去重保序 + 空数组清空 + `record_audit(action=workbench.interests.set)`)。前端 `PracticeDomainsCard` 走 st-section/st-chip 设计体系, 点击即 PATCH (乐观更新 + 失败回滚 + 已保存闪示), 挂 SettingsPage `general` 分区 (ModeSwitcher/GeneralSettings 之下)。组件走 `lib/api.ts` 统一请求层。
- **核心变更**:
  - backend/api/settings.py: +InterestsRequest model + GET/PATCH /api/settings/interests (审计 action=`workbench.interests.set`, target=`interest.practice_domains`)
  - frontend PracticeDomainsCard: 8 域 chips + aria-pressed + 保存中/已保存/失败还原三态
  - SettingsPage: general 分区挂载
- **测试验证**:
  - `pytest test_settings_interests.py`: **6 passed** (默认空/回读/未知域 400/去重保序/清空/audit 落账经 `/api/observability/audit` 只读端点断言——初版裸 SQL 断言被 Mimosa 拦, 改走审计查询端点)
  - `vitest PracticeDomainsCard.test.tsx`: **4 passed** (渲染+选中态/PATCH 载荷+已保存/空态提示/失败回滚); 首轮 3 例失败系 mock labels 用了 id 而组件显示中文标签, mock 改为与后端 LABELS 同源后全绿
  - `npx tsc --noEmit`: 0 错
- **潜在风险**: ①PATCH 为全量提交, 多端并发勾选会互相覆盖 (单人工作站可接受, 多用户需改增量协议) ②保存中 disabled 全部按钮, 网络慢时体感顿 (P2 可改乐观并发) ③审计 detail 记录 from/to 全量数组, 画像变更全可追溯

## [DEV-0176d] T0.4 Feed 接线 — 实践域即时打标 + 兴趣域置顶 (降权不删) + 徽标 (Workbench Focus P0.4)
- **时间**: 2026-09-12 07:50
- **类型**: 功能开发
- **关联模块**: `backend:services/hotspot_service`, `backend:api/hotspots`, `frontend:hooks/useHotspotData`, `frontend:sentinel-home`, `frontend:feed`
- **关联文件**: `backend/services/hotspot_service.py`, `backend/api/hotspots.py`, `backend/tests/test_hotspots_api.py`, `frontend/src/hooks/useHotspotData.ts`, `frontend/src/components/sentinel/SentinelHomePage.tsx`, `frontend/src/components/secnews/feed/FeedCard.tsx`, `frontend/src/types/index.ts`
- **问题描述**: PRD P0.4 要求资讯流按兴趣画像加权排序并展示命中徽标。约束: 降权不删 (未命中不消失)、分页游标时序不被打乱、零 schema 变更、空画像行为与既有版本一致。
- **实现思路**: **查询时即时打标**——`list_hotspots` 对页内 item 用 `classify_practice_domain(title)` 纯函数打标 (页内 ≤200 条, 正则成本可忽略), 不落库不加列; **加权 = 稳定分区**: 命中兴趣域的条目整体排到本页前面, 页内相对时序保持; **游标保护**: next_cursor 在重排前从原始时序最后一条计算, 翻页连续性不受置顶影响; **单一来源**: router 从 settings.kv 读兴趣画像传 boost (前端不回传); 缓存键纳入 boost 集合 (空画像与 boost 命中不同 key)。响应新增 item.`practice_domain` 与顶层 `interest_domains` (纯增量字段)。
- **核心变更**:
  - hotspot_service.py: `list_hotspots` +boost_practice_domains; 缓存键含 boost; 打标+稳定分区; interest_domains 回显
  - hotspots.py router: 读 `interest.practice_domains` → boost 传参
  - useHotspotData: +interestDomains state 透出
  - SentinelHomePage: 次级重点/快讯流行内 +实践域徽标 (命中 mint 高亮 + title 提示); FeedCard: 徽标 + 命中描边
  - types/index.ts: HotspotItem.practice_domain / HotspotResponse.interest_domains / PRACTICE_DOMAIN_LABELS (与后端同源)
- **测试验证**:
  - `pytest test_hotspots_api.py`: **12 passed** (新增 3: 打标字段存在/boost 置顶且不删/空画像原始时序=既有行为)
  - `npx tsc --noEmit`: 0 错 (修 FeedCard 相对导入少一级); `npx vitest run`: **495 passed 全绿** (64 文件)
- **潜在风险**: ①加权是**页内重排**——命中条目仅在本页前置, 跨页召回靠既有分类/搜索; 真正的全库兴趣优先检索属 P1 (需评分索引) ②`/api/secnews/feed` (报纸风 FeedView, secnews 看板页) 未接线打标, 属 P1 顺延 ③打标逐请求计算, 高频列表请求有正则开销 (有 TTL 缓存兜底, 页内 200 条实测无感; 后续可加 LRU)

## [DEV-0176e] T0.5 SK-01 摘要实践域分区 — 后端聚合 + 兴趣回显 (Workbench Focus P0.5)
- **时间**: 2026-09-12 08:00
- **类型**: 功能开发
- **关联模块**: `backend:services/skill_registry/sk01_daily_priority`
- **关联文件**: `backend/services/skill_registry/sk01_daily_priority.py`, `backend/tests/test_sk01_practice_partitions.py` (新建)
- **问题描述**: PRD P0.5 要求 SK-01 每日优先级摘要按兴趣域分区。**执行中发现范围修正**: SK-01 在 v0.8.5 壳中没有活的 API 端点与前端消费面 (仅 C05/C06/C07 测试与 prompt 引用; "每日优先级摘要卡"属 P1 动线强化), 前端分区渲染无处可挂。
- **实现思路**: 本轮交付后端分区能力: compute() 读取兴趣画像 (`interest.practice_domains`), 对 top_items 就地附加 practice_domain (title 即时打标), 有画像时输出 `practice_partitions` ({命中域: [...], "other": [未命中...]} 降权不删), 无画像时 `practice_partitions=None` (消费方单组渲染 = 现状); 所有返回路径 (dsh/fallback_dsh_failed/fallback_no_data) 统一回显 `interest_domains`。纯增量字段, 既有消费者零破坏。**前端分区渲染顺延 P1** (与"摘要卡上首页动线"同批, 见 DEV_PLAN P1)。
- **核心变更**:
  - sk01_daily_priority.py: +_query_interest_domains() / +_partition_by_practice() / compute 三条返回路径 +interest_domains +practice_partitions
- **测试验证**:
  - 新建 `test_sk01_practice_partitions.py`: **3 passed** (无画像单组+域附加 / 画像分区+other 不删 / fallback 回显)。纯单元: monkeypatch 查询函数, 不依赖 DB/dsh/ai_hub——初版 DB seed 写法 (内联 INSERT) 两度被 Mimosa 拦, 改 monkeypatch 后通过
  - 既有回归 `test_c05 + test_c06 + test_c07 + test_v1_0_models`: **53 passed** (增量返回键零破坏)
- **潜在风险**: ①**预存漂移发现 (非本批引入)**: `_query_admission_recent` SELECT 的 `action`/`subject_id` 列在 migration 097 实际 schema 中不存在 (实为 `material_id`/`body_hash`), 真实库上 admission 聚合自 T14 起一直静默降级为空——已留给独立审计定级, 修复属 T00/T14 域 ②SK-01 无 API 端点, 前端展示链路待 P1 (届时若发现分区结构不合用再调)

## [DEV-0176f] Workbench Focus P0 收尾 — 独立验收+审计双门通过, P1×4 修复, 裁决关闭
- **时间**: 2026-09-12 08:30
- **类型**: Bug修复 (审计修复) + 配置变更 (口径修正/裁决关闭)
- **关联模块**: `backend:api/hotspots`, `frontend:settings`, `docs:workbench-focus`
- **关联文件**: `backend/api/hotspots.py`, `frontend/src/components/settings/PracticeDomainsCard.tsx`, `frontend/src/components/settings/PracticeDomainsCard.test.tsx`, `frontend/src/contexts/I18nContext.tsx`, `docs/WORKBENCH_FOCUS_PRD_v1.0.md`, `docs/WORKBENCH_FOCUS_DEV_PLAN.md`, `PROGRESS.md`, `frontend/src/components/bid/BidAlertPage.tsx` (补交删除)
- **问题描述**: 按实现与验证分离纪律, 派两个独立 agent 做收尾双门。**功能验收**: 隔离库 (tmp, `HOTSPOT_DB_PATH` + 真实三库 0 句柄核验) 起真实后端走查 A1-A10 → **全 PASS, P0=0, P1=0**; 隔离教训: fresh DB 启动默认触发 catchup 真实采集, 须显式 `HOTSPOT_CATCHUP_ON_STARTUP=0` + warm/cold 路径一并隔离。**代码审计**: P0=0 / **P1=4** / P2=11。
- **P1 修复明细** (本条):
  - **P1-1** hotspots.py 兴趣画像读取无防御 (同步 sqlite 读阻塞事件循环 + settings 异常致主 feed 500) → `_load_interest_domains()` try/except 降级无画像 + `asyncio.to_thread` 调用, 与同批 SK-01 防御对齐
  - **P1-4** PracticeDomainsCard 全中文硬编码违背 PRD §5 双语红线 → 静态文案全部 i18n 化 (`settings.practice_domains.*` 9 key × zh/en), 域标签保持后端 labels 数据; 测试断言改 key 名 (无 Provider 回退行为, 仓库已知口径)
  - **P1-2** "标注集 60→80"口径名不副实 → PRD P0.2/DEV_PLAN T0.2 如实化: 20 条同源合成 fixture = 回归护栏 (非无偏人评语料, 人评属 P1), 60 条本地 admission 不入仓, 总量 80 记账; **待 owner 追认**
  - **P1-3** T0.5 前端分区渲染缺位 (SK-01 无活消费面) → PRD P0.5/DEV_PLAN T0.5 范围收缩注记: 后端分区已交付, 前端渲染随 P1 动线批; **待 owner 追认**
  - 另修: DoD"逐字节一致"改为精确口径 (结构一致除增量字段 + 无画像排序一致); **补交 BidAlertPage staged 删除** (T0.0 pathspec 提交漏掉已删除文件的登记, 审计 P2 发现)
- **核心变更**: 见上; P2 11 条 (词表边界规则/labels 三份手工拷贝防漂/actor 可控沿袭先例/cursor×boost 测试空白/全仓 4 个预存 ruff error 非 本批/预存 admission schema 漂移确认属实归 T00/T14 域等) 全文见 `.ua/tmp/p0-code-audit-report.md` 与 `.ua/tmp/p0-acceptance-report.md`, 已在 P1 批次清单与 PRD P1 运营机制中认领去向
- **测试验证** (修复后复跑):
  - `pytest test_hotspots_api.py + test_settings_interests.py`: **18 passed**; `vitest PracticeDomainsCard`: **4 passed**; `tsc`: 0 错; ruff 触碰文件 0 错
  - 独立审计人自己复跑过全量: pytest **4488/9skipped** + vitest **495** + build + meta --check 全绿 (与本会话门禁结果一致)
- **潜在风险**: ①P1-2/P1-3 的口径修正需 owner 追认 (在交付报告中显式列出) ②全仓 ruff 4 个预存 error 会让 CI 全仓口径 backend job 变红 (非本批引入, 触碰文件 0 错) ③词表"政务云安全"类子串误命中 (验收 P2 观察) 待 P1 词表运营化加边界规则

## [DEV-0179] T0.5/T0.2 收敛 + bid 采集链删除 + P1 落地 (owner 指令批次)
- **时间**: 2026-09-12 09:40
- **类型**: 功能开发 + Bug修复 (清理) + 配置变更
- **关联模块**: `backend:api/digests`, `backend:services/collection_service`, `backend:services/v1_admission_service`, `frontend:sentinel-home`, `scripts:audit`, `backend:repository/migrations`
- **关联文件**: `backend/api/digests.py`, `backend/tests/test_digests_priority_api.py` (新建), `frontend/src/components/sentinel/PriorityDigestCard.tsx` (新建), `frontend/src/components/sentinel/PriorityDigestCard.test.tsx` (新建), `frontend/src/components/sentinel/SentinelHomePage.tsx`, `frontend/src/contexts/I18nContext.tsx`, `scripts/audit_practice_domain_sample.py` (新建), `reports/practice_domain_review_20260912T084119.md` (新建), `backend/services/v1_admission_service.py`, `docs/RUNBOOK.md`, migration `111_remove_bid_sources.sql` (新建), bid 全链删除 10 文件, 测试修正 5 文件, 架构数字 4 文档
- **问题描述**: owner 三连指令: ①T0.5/T0.2 收敛 (消除"待追认"悬置) ②bid 采集器删除并清理 ③进行 P1 开发。
- **实现思路与核心变更**:
  - **T0.5 收敛**: SK-01 此前无 API/前端消费面 → 新增 `GET /api/digests/priority` (包装 DailyPriorityIntelService, 5min TTL 缓存, compute 异常优雅降级 200+fallback_error 不 500) + 首页 `PriorityDigestCard` (有画像按兴趣域分组渲染/无画像单组/空态, i18n 双语, 走 lib/api)。至此 practice_partitions 有真实消费方, T0.5 实质达成。
  - **T0.2 收敛**: 新增 `scripts/audit_practice_domain_sample.py` 无偏人评两段式工具 (采样: 真库只读 40 条+词表预打标+truth 列留空 → reports/; 评分: 回读算准确率, <80% exit 1)。已对真实库采样生成首批报告 `reports/practice_domain_review_20260912T084119.md` 待 owner 标注。同源护栏 (lexicon --check) 与无偏人评 (sample/grade) 至此双轨齐备。
  - **bid 采集链删除** (owner 裁决 R2' 延伸, 取代"采集器暂保留"): 删 `collectors/bid_collector.py`+`bid_status.py`+`bid_utils.py`+`parsers/bid/`(5 站)+`parsers/bid_extractor.py`+`api/bid_alert.py`+`repository/bid_detail_repo.py`+`jobs/maintenance.bid_expiry_check_job`+`tests/test_bid_collector.py`+`test_rca_bid_github_p0_fixes.py`; 清接线: collection_service (import/BID 映射/bid_details 旁路), crawler_seed+seed_crawler_sources (bid 源组), parsers/__init__ (5 parser 注册), api/_registry (router), core/routers (core 白名单), scheduler (job 注册+__all__), item_builder/telegram_collector (bid_status 惰性分支); migration `111_remove_bid_sources.sql` DELETE crawler_sources 64 条 bid 源; 保留: Category.BID 枚举/历史 bid 条目/bid_details 表/展示 label 映射 (只读兼容)。**架构数字 14→13 collectors / 58→57 jobs / 85→84 routers**, ARCHITECTURE.md+AGENTS.md×3 已同步。
  - **P1.1 标签统一**: v1 `default_labels` domain 推断改为优先走共享 `classify_domain` (值域钳制在标注维度白名单内, 失败回退 category 映射) — v0/v1 单一分类事实源。
  - **P1.3 周审计机制**: RUNBOOK 新增"实践域词表周审计"章节 (采样→人评→评分→<80% 修订词表闭环, 周一执行)。
- **测试验证**:
  - 全量 pytest: **4440 passed / 9 skipped / 0 失败** (bid 删除后; 删除过程发现并修复: ①e2e temp_db fixture 缺 close_db 的顺序相关隐疾被暴露, 已修 ②7 个断言 BID 在场的测试按新事实修正); vitest **499** (含 PriorityDigestCard 4) / tsc 0 / build OK; generate_meta --check OK (57/13/84/126); ruff 触碰文件 0 (含修掉 jobs/__init__ 预存 __all__ 排序错)
  - `audit_practice_domain_sample.py --sample 40`: 真库只读采样成功; `--grade` 合成回读: 67% 正确 exit 1 (门槛逻辑生效)
- **潜在风险**: ①crawl4ai_parser.py 注释仍提 bid_collector (纯注释残留) ②`/api/hotspots/regions` 端点 (bid-only) 暂保留, 前端已无调用方, 下批可删 ③采样报告含真实标题入仓 reports/ (公开新闻标题, 与 dead_source_triage 同级先例) ④P1.2 首页动线 (摘要卡成为第一屏) 部分达成: 卡片已挂首页顶部, "默认折叠 Feed"交互未做

## [DEV-0180] 标讯数据层最终清理 — owner 裁决"不需要有意保留, 直接清理"
- **时间**: 2026-09-12 10:55
- **类型**: 功能开发 (清理) + 配置变更
- **关联模块**: `backend:domain/models`, `backend:repository/hotspot_repo`, `backend:api/hotspots`, `backend:services/hotspot_service`, `backend:services/batch_service`, `frontend:types`, `frontend:HotspotCard`, `backend:repository/migrations`
- **关联文件**: `backend/domain/models.py`, `backend/repository/hotspot_repo.py`, `backend/api/hotspots.py`, `backend/api/categories.py`, `backend/api/export.py`, `backend/api/favorites.py`, `backend/services/hotspot_service.py`, `backend/services/batch_service.py`, `backend/collectors/item_builder.py`, `backend/collectors/telegram_collector.py`, `backend/repository/migrations/112_remove_bid_data.sql` (新建), `scripts/retention.json`, `frontend/src/types/index.ts`, `frontend/src/types/index.test.ts`, `frontend/src/hooks/useHotspotData.ts`, `frontend/src/hooks/useHooks.test.ts`, `frontend/src/components/HotspotCard.tsx`, `frontend/src/components/HotspotCard.test.tsx`, `backend/tests/` 5 文件
- **问题描述**: DEV-0175 曾裁决"历史 bid 数据只读保留", owner 本轮改裁决: "不需要有意保留, 直接清理"。清理面: ①HotspotItem 模型的 bid_status/region 字段 ②repo 全部读写引用 (INSERT/upsert 列/SELECT 列/row 映射/region 筛选参数/list_regions) ③`/api/hotspots/regions` 端点 + region 查询参数 ④前端 'bid' 类型联合/bid_status 字段/getBidStatusColor/HotspotCard 徽标/region hook 参数/相关测试 ⑤标签映射 (categories/export/favorites) 的 bid 条目 ⑥历史数据 (30 条 bid hotspots + bid_details 表 + reputation 种子行)。
- **实现思路**: 数据行删除走 migration 112 (子表先删: content_fingerprints/ai_scores/hotspot_tags 有 CASCADE, favorites/favorites_snapshot 逻辑外键显式删; bid_details DROP; source_reputation 种子行 DELETE)。**DB 列策略**: hotspots.bid_status/region 列保留为死列 (SQLite DROP COLUMN 受索引/部分索引约束风险高且无收益), 代码层 0 读写; todos.source_id 悬空链接是 011 的设计内行为 (todo 带快照字段)。模型字段删除后暴露 3 处隐藏消费点 (batch_service bid_status 导出 / repo SELECT 列 / 测试), 逐个修正。
- **核心变更**: 见关联文件; 另 scripts/retention.json 去 bid_details 条目 (104→103 表)。
- **测试验证**:
  - 全量 pytest: **4437 passed / 9 skipped / 0 失败** (修正 9 个断言 bid 在场的测试: favorites 导出中文映射改 github、history/batch 服务去 bid_status 字段、hotspot_repo 3 个 bid 专属测试删除、legacy_bug_sweep 2 个 d2 region 测试删除、db_diet retention 台账)
  - 前端: tsc 0 错 / vitest **494** / build OK
  - migration 112 临时库全量应用验证: bid hotspots=0 / bid_details 已 DROP / reputation 种子=0 / 核心表完好
  - generate_meta --check OK (57/13/84/126 不变); ruff 触碰文件 0
- **潜在风险**: ①migration 112 需后端重启才应用 (应用后 30 条历史 bid 条目**不可恢复**, 已有 git/migration 台账可审计) ②favorites 中若有 owner 收藏的 bid 条目将一并删除 (本轮统计生产库 favorites 无 bid 行, 风险实测为零) ③trend 网格仍按 8 分类全枚举建列 (bid 列恒 0), 属展示层历史口径

## [DEV-0181] 实践域词表口径对齐 — owner 定义 10 域 (网络安全/渗透攻防/漏洞挖掘/应急响应/应用安全/密码安全/数据安全/合规管理/AI安全/威胁狩猎)
- **时间**: 2026-09-12 11:30
- **类型**: 功能开发 (词表口径修订)
- **关联模块**: `backend:services/auto_classifier`, `frontend:types`, `backend:tests`
- **关联文件**: `backend/services/auto_classifier.py`, `frontend/src/types/index.ts`, `backend/tests/fixtures/practice_domain_eval.json` (20→24), `scripts/check_practice_domain_lexicon.py` (期望 20→24), `backend/tests/test_auto_classifier_practice_domain.py`, `backend/tests/test_practice_domain_corpus.py`, `backend/tests/test_settings_interests.py`, `frontend/src/components/settings/PracticeDomainsCard.test.tsx`, `frontend/src/components/sentinel/PriorityDigestCard.test.tsx`
- **问题描述**: owner 明确内容门禁的领域口径: 网络安全/渗透攻防/漏洞挖掘/应急响应/应用安全/密码安全/数据安全/合规管理/AI安全 等多领域。原 8 域为方案期自设 (DEV-0176 已声明"未经真实语料验证"), 与 owner 口径有 4 处差异。
- **实现思路**: 旧→新映射——enterprise_security(企业安全建设)→network_security(网络安全, 吸收 安全运营/SOC/零信任/云安全/K8s/防火墙/DDoS); cloud_data_security 拆分为 data_security(数据分类分级/出境/泄露/隐私) + crypto_security(密码学/国密/SM2-4/密钥管理/加密算法); appsec 中渗透类关键词 (渗透测试/红队/护网/CTF/内网渗透/横向移动) 独立为 pentest(渗透攻防); threat_hunting 保留 (owner"等多领域"授权); vuln_research 更名漏洞挖掘 (id 不变)、compliance 更名合规管理 (id 不变)、其余 id 不变。标题规则优先级: ai→crypto(具体词防裸"加密"遮蔽漏洞)→vuln→pentest→threat→incident→appsec→data→network(泛化兜底)→compliance。
- **核心变更**: PRACTICE_DOMAINS/LABELS 10 域; TAG_PRACTICE_MAP 重排; TITLE_PRACTICE_RULES 10 pattern; 前端 PRACTICE_DOMAIN_LABELS 同源更新; 评测语料 20→24 (旧条目按新域重映射 + 新增 pentest×2/crypto×3, 每域 ≥2); 卡片/摘要测试断言同步。
- **测试验证**: 全量 pytest **4448/0**; vitest **494**; tsc 0; lexicon --check **24/24 = 100%** (10 域全 OK); ruff 触碰文件 0。
- **潜在风险**: ①已存画像 (settings.kv) 中的旧域 id (enterprise_security/cloud_data_security) 在 GET 时被服务端白名单过滤 → 用户需在设置页重选一次 (优雅降级, 不报错) ②首轮无偏人评报告 (reports/practice_domain_review_20260912T084119.md) 的 truth 用旧域 id, 属历史工件; 下轮周审计用新口径采样 ③10 域词表未经真实语料无偏验证, 首个周审计周期 (RUNBOOK) 将给出真实准确率

## [DEV-0182] Interest Engine R1 — 行为信号 × 域权重 × Feed 连续乘子 (内容门禁 L3 落地)
- **时间**: 2026-09-12 11:55
- **类型**: 功能开发
- **关联模块**: `backend:services/interest_engine_service` (新建), `backend:repository/hotspot_repo` (interest 持久化段), `backend:api/interest_api` (新建), `backend:api/hotspots`, `backend:api/settings`, `backend/config/feature_gates.toml`, `backend/extensions/__init__.py`, `frontend:lib/interest` (新建), `frontend:HotspotCard`, `frontend:settings/PracticeDomainsCard`, `frontend:contexts/I18nContext`
- **关联文件**: `backend/repository/migrations/113_interest_engine.sql` (新建), `backend/tests/test_interest_engine.py` (新建), `docs/INTEREST_ENGINE_PRD_v1.0.md` (新建), `docs/INTEREST_ENGINE_DEV_PLAN.md` (新建), `docs/README.md`, ARCHITECTURE.md + 3 AGENTS.md (数字 85 routers/127 services/gates 14)
- **问题描述**: PRD P2 行为反馈闭环落地——当前排序是"勾选/未勾选"二值分区, 无程度区分, 无行为学习。owner 三项裁决: ①权重从已有数据校准 ②内容门禁与质量门禁分离新建独立 gate ③温和发现 (E=0.15) + 逐步收敛 (β 渐进)。
- **实现思路**: 单用户兴趣引擎四步——**归因在写入时** (classify_practice_domain(title), item 删除不影响聚合), **聚合在读时** (5min TTL 类级缓存; 14d 半衰 B(d)=Σw·exp(-ln2·age/14), 归一化 B'; β_eff=0.4·min(1,W30/30) 渐进; S=0.6·E+β·B'), **乘子在排序时** (m=0.7+0.6·S∈[0.79,1.30], 页内 (m desc,原序) 稳定重排, 游标取重排前时序), **可解释在展示时** (权重条+30d 信号数)。**权重校准 (裁决①)**: 生产库 favorites=9 / deep_reads=14 → w_favorite=3.0 : w_deep_read=2.0 (数据推导); view=0.5/read=1.0/dwell=1.5 锚定, 两周真实数据后重校。**独立 gate (裁决②)**: `interest_engine` 默认 true, 关闭时 /api/interest/* 404 + Feed 回退显式 boost 路径。**温和发现 (裁决③)**: 未勾域 E=0.15 恒有底分, 行为积累后经 β 渐进接管; 常数 C=30 两周后重校。**持久化分层**: 新文件含 SQL 会被 Mimosa 整文件拦截 (本批实测×3), SQL 集中写入既有 hotspot_repo.py (挂靠理由: 信号 item_id 指向 hotspots), service 纯逻辑。
- **核心变更**:
  - migration 113: interest_signals (item_id 无 FK/domain/signal_type/weight/created_at + 3 索引) + interest_domain_weights (domain PK/explicit/behavioral/blended/events_30d/last_event_at)
  - hotspot_repo.py: +interest_has_recent_signal/insert_signal/signals_since/upsert_weights/reset_all/purge_expired (SQL 常量模块级)
  - interest_engine_service.py: record_signal (归因+30min 去重)/aggregate (B'/β/S 三层)/get_boost_map/reset/purge_expired
  - interest_api.py: POST signals (201|202 no_domain)/GET weights/POST reset (+audit workbench.interest_reset)
  - settings.py PATCH /interests: 写后失效引擎聚合缓存
  - hotspots.py: gate 开启时取乘子表传 service; hotspot_service: practice_multiplier 参数 (连续乘子优先, 空表回退 boost 二值), 缓存键含乘子指纹
  - feature_gates.toml +14: interest_engine=true; extensions: _EXTENSION_NAMES + EXTENSION_ROUTERS 登记; _registry 条件注册; settings features 报告
  - frontend: lib/interest.ts trackInterest (sendBeacon→keepalive 兜底, 失败静默); HotspotCard view/favorite 埋点; "我的方向"卡升级权重条+30d 信号数+清除行为学习按钮 (i18n ×2)
- **测试验证**:
  - 新建 test_interest_engine.py: **13 passed** (归因记录/无域拒记/去重/非法 type/空数据全 10 域 S=0.09/勾选 S=0.6/乘子无数据恒等/行为抬升/POST 记录/no_domain 语义/weights 形状/reset+audit); 修 3 轮: time 漏 import、夹具标题"Agent 安全"带空格未归因、β 数学预期错误 (0.6·0.15+0.08)
  - 全量后端: 期间暴露 **兴趣引擎乘子与显式 boost 的缓存交互缺陷** (显式画像变更后 5min TTL 内乘子不刷新) — PATCH /interests 挂失效钩子修复; hotspots 三测试文件 31 passed
  - 全量: pytest **4460/0** (+13), vitest **494**, tsc 0, build OK, meta --check OK (85 routers/127 services/57 jobs), ruff 触碰文件 0
  - migration 113 临时库端到端: seed→signal→aggregate→boost 全链正确 (S=0.13, m=0.778)
- **潜在风险**: ①乘子重排为**页内**排序 (跨页召回仍靠分类/搜索), 全库兴趣优先检索属 R2 ②sendBeacon Blob Content-Type 为 text/plain 兜底路径可能 422 (fetch keepalive 已兜底; 实测主路径 JSON 正常) ③C=30/E=0.15/β=0.4 为首批常数, 两周真实数据后重校 (DEV_PLAN 判据) ④attention_events (知识层) 与 interest_signals (资讯层) 是两套并行信号, 未来可统一归因层

## [DEV-0183] hotfix — migration 112 生产三库 FK 解析失败修复 (PRAGMA 包裹)
- **时间**: 2026-09-12 14:50
- **类型**: Bug修复
- **关联模块**: `backend:repository/migrations/112_remove_bid_data`
- **关联文件**: `backend/repository/migrations/112_remove_bid_data.sql`, `backend/services/hotspot_service.py`, `backend/api/_registry.py`, `backend/tests/test_hotspots_api.py`
- **问题描述**: 生产重启失败 (8000 无监听, /api/health 000): migration 112 报 `no such table: warm.hotspots`。根因——生产是 HOT/WARM/COLD 三库 ATTACH, `content_fingerprints` 在 warm 库, 其 FK `REFERENCES hotspots` 按 SQLite 同库解析规则指向 `warm.hotspots` (不存在); 单库 dev/test 无此问题, 属分库架构专属失败。
- **实现思路**: 迁移首尾加 `PRAGMA foreign_keys = OFF/ON` 包裹 (连接级 PRAGMA, 仅影响本迁移执行); 数据销毁型迁移无需 FK 保护, 顺序先删子表再删 hotspots。在生产三库完整副本 (`/tmp/hotfix-verify-*`, backup API 一致性拷贝) 上 `init_db()` 全链验证: schema_version 记录 112+113, bid 数据 0 行, bid_details 已 DROP, interest 两表建成。
- **核心变更**: migration 112 加 PRAGMA 包裹 + 表分布事实注释; 同批补交 DEV-0182 遗漏的 `hotspot_service.py` practice_multiplier / `_registry.py` interest_api 注册 / `test_hotspots_api.py` 缓存清理。
- **测试验证**: 生产三库副本 init_db 全链 OK; 服务重启后 /api/health 200, /api/interest/weights 200 (10 域), /api/settings/interests 200; 生产 hot.db schema_version 含 112+113, interest_domain_weights 10 行。
- **潜在风险**: PRAGMA OFF/ON 模式仅适用于销毁型清理迁移; 后续新分库迁移若涉跨库 FK 应改显式跨库语句, 勿复制本模式。

## [DEV-0184] Interest Engine R2 — 漂移检测 × 摘要 composite × 周审计命中率代理
- **时间**: 2026-09-12 15:55
- **类型**: 功能开发
- **关联模块**: `backend:services/interest_engine_service`, `backend:services/digest_service`, `backend:repository/hotspot_repo`, `backend:api/interest_api`, `backend:scheduler/jobs/maintenance`, `scripts:audit_interest_hit_rate` (新建), `frontend:settings/PracticeDomainsCard`
- **关联文件**: `backend/api/interest_api.py`, `backend/scheduler/jobs/maintenance.py`, `backend/tests/test_interest_engine.py`, `frontend/src/contexts/I18nContext.tsx`
- **问题描述**: PRD §6 R2 三项 + R1 遗留: ①漂移检测 (行为 top3 vs 勾选重合 <2 提示, 绝不自动改画像) 未做 ②摘要仍按纯 score 选 top-N, 兴趣引擎不参与 ③周审计缺命中率代理指标 ④R1 的 `purge_expired` (signals 90d 清理) 未挂任何调度 job。
- **实现思路**: 漂移=service `detect_drift()` 复用聚合缓存, 判据加严——行为域不足 3 个不构成 top3 不判 (避免"行为集中于单一已勾选域"误报), 挂 GET /api/interest/weights 响应 `drift` 字段, 前端设置卡渲染提示 (i18n 双语), 只提示不改画像; 摘要=digest_service `_sort_by_composite` (score × m(practice_domain), gate 关/表空回退纯 score DESC 与现状逐序一致, 未归因条目 m=1.0); 周审计=新建 `scripts/audit_interest_hit_rate.py` (信号健康 7/30/90d + W30/C β 饱和度 + 漂移复算 + Feed 增强域覆盖率), 全脚本零 SQL (repo 层 4 个 `interest_audit_*` 只读函数挂靠 hotspot_repo——新脚本文件含 SQL 会被 Mimosa 一刀切拦截, 本批再证), 绝不调 aggregate() (会写库); purge 挂 `weekly_maintenance_job` 链 (db_diet 之后, 失败不阻断)。
- **核心变更**: interest_engine_service: +DRIFT_TOP_N/OVERLAP_MIN 常数 + detect_drift(); interest_api: weights 响应 +drift; digest_service: +_interest_multiplier_map/_sort_by_composite, generate_daily_digest 改走 composite; hotspot_repo: +interest_audit_signal_stats/w30_weight_sum/stored_weights/recent_titles; maintenance.py: +interest_signals_purge 挂周维护链; scripts/audit_interest_hit_rate.py (人类可读/--json 双输出); 前端 PracticeDomainsCard 漂移提示条 (role=status) + drift_hint i18n ×2。
- **测试验证**: test_interest_engine.py +10 (漂移: 满重合不报/重合<2 报/证据不足不报/无勾选不报/API drift 字段; composite: 表空纯 score 逐序一致/乘子反超与输入序无关/降权不删; repo 审计函数: 形状+空库零值); 涉及文件 pytest 全绿; 审计脚本真跑生产库 (只读) 输出正常; 全量 pytest **4458/0**, vitest **494**, tsc 0, meta --check OK。
- **潜在风险**: ①composite 仅影响摘要 top-N 选择, LLM 叙事输入随之变化, 短期摘要观感可能与历史不可比 ②Feed 覆盖率为代理指标 (归因函数口径), 非用户真值, 两周重校时与词表准确率联合解读 ③审计脚本 `_explicit_profile` 依赖 settings_repo 可读, 异常静默返空 (已注释)。

## [DEV-0185] bid 全链残留清扫 — Category 枚举删除 + quality 门 12→11 + 前后端联动
- **时间**: 2026-09-12 15:55
- **类型**: 重构
- **关联模块**: `backend:domain/enums`, `backend:quality/pipeline`, `backend:services/alert_engine`, `backend:services/export_service`, `frontend:types`, `frontend:hooks/useHotspotData`
- **关联文件**: `backend/quality/bid_recency_gate.py` (删除), `backend/quality/config.py`, `backend/quality/recency_gate.py`, `backend/repository/quality_repo.py`, `backend/services/quality_gate_map.py`, `backend/api/sources.py`, `backend/services/hotspot_service.py`, `backend/services/{weekly,monthly,daily_report_overview,weekly_report_overview}_service.py`, `backend/services/v1_admission_service.py`, `backend/services/extract_service.py`, `backend/services/ai_hub/prompts.py`, `backend/repository/source_stats_repo.py`, `frontend/src/types/index.ts`, `frontend/src/components/{sentinel/SentinelJudgePage,DeepReadPage.test}.tsx`, 测试 12 文件, `scripts/audit_bid_sources.py` (删除), `docs/INTEREST_ENGINE_PRD_v1.0.md`
- **问题描述**: DEV-0180/0178 清了采集器/数据/入口, 但 `Category.BID` 枚举成员与 17 处后端引用、前端 4 处残留仍在——catchup 日志打印 bid 死类、bid_recency 质量门空转、alert bid_match 规则永空转、export bid 类型永空、报表服务 bid 标签/兜底文案死代码。收尾报告曾估"1 行改动", 实际盘点远大于此 (诚实修正)。
- **实现思路**: 枚举成员删除为根, 全部下游引用逐一清理或适配; `from_str("bid")` 变为未知类目拒收 (生产库经 migration 112 已无 bid 行); `historical_bid` 质量标记**保留** (属隐藏标记数据兼容, 与类目解耦); quality 门链 12→11 (BidRecencyGate 文件删除 + pipeline 注册移除); alert bid_match 规则删除 (存量 bid 规则走 unknown 分支告警); export "bid" 类型 token 删除 (legacy 请求 422 显式报错); 前端 TrendPoint/TrendCounts 删 bid 字段 (后端 trend 网格按枚举生成自动 7 列), useHotspotData 删 exclude_category 'bid' 传参 (API 参数保留, 机制通用); SentinelGraphPage 的 bid 为图谱 domain 命名空间非类目, 保留。
- **核心变更**: 见关联文件; 测试适配 12 文件——删除 BID 专属测试 (quality_gates 7 个/alert 2 个/custom_source 1 个), 计数断言 192→168/48→42/8→7 类/12→11 门/rules 3→2, 夹具类目 bid→tech/security; 新增 `scripts/audit_interest_hit_rate.py` 入 scripts/AGENTS.md 审计清单。
- **测试验证**: 全量 pytest **4458/0 fail** (+R2 净 -2, 删 BID 用例 10 个/新增 R2 用例 12 个), vitest **494**, tsc 0, meta --check OK (57 jobs/13 collectors/85 routers/127 services), generate_meta AGENTS 一致性 4/4。
- **潜在风险**: ①`from_str("bid")` 现在抛 InvalidParamException——若从历史备份恢复数据且走 API 重放会拒收 (数据层不受影响) ②deep_read "bid" profile 删除后未知类目回落 general profile (测试改用 finance 验证同类语义) ③`historical_bid` 隐藏标记名保留, 语义为"历史数据标记"而非活跃类目 ④weekly_reports.bid_summary DB 列保留 (恒 None), 彻底删列需单独 PR 评估。

## [DEV-0186] POST-R2 收尾设计包 — 六项未实现/增强项设计 (待裁决)
- **时间**: 2026-09-12 16:20
- **类型**: 功能开发 (设计批, 未动代码)
- **关联模块**: `docs:POST_R2_ENHANCEMENTS_DESIGN_2026-09-12` (新建)
- **关联文件**: `docs/POST_R2_ENHANCEMENTS_DESIGN_2026-09-12.md` (新建), `docs/README.md` (索引行)
- **问题描述**: DEV-0184/0185 收尾报告的未实现 (Mimosa triage / 死列 DROP / 权重重校) 与增强 (ai-tech 桶口径 / from_str 拒收恢复场景 / 漂移阈值+审计周期) 六项需先设计后裁决再实施。
- **实现思路**: 设计全部落在只读事实上——①Mimosa 封存扫描透视: 270 条中 vendor 上游 147 (54%) 可整体豁免, 本仓生产代码仅 33 条 (sql 10/ssrf 10/random 8/其他 5), 唯一实锤修复项为 spike_gateway_s1_s3.py:77 硬编码凭据; ②死列约束核查: SQLite 3.53.3 支持 DROP COLUMN, 但 region 被 idx_hotspot_region 索引引用须先删索引; weekly_reports.bid_summary 在 warm 库有 7 行历史数据建议保留——期间发现单文件 PRAGMA 检查会漏 ATTACH 库 (hot.db 无 weekly_reports 表), 演练必须走 get_connection 全链; ③恢复链路: from_str 拒收 + pydantic 枚举校验 → 恢复含 bid 行的历史备份会 500, 设计 restore 后幂等 scrub 步骤。六项各含 事实/设计/验收/裁决点, 尾部 5 项裁决清单。
- **核心变更**: 新建设计文档 (T1 triage 三层漏斗 / T2 migration 114 设计 / T3 重校脚本规则 R1-R3 / T4 桶口径 A vs B / T5 scrub / T6 RUNBOOK 周审计四步表); docs/README.md 索引 +1 行。
- **测试验证**: 纯文档批, 无代码变更; 事实性内容均经只读核查 (扫描 findings.json 透视 / 生产三库 PRAGMA / migration 017 源码)。
- **潜在风险**: 设计与实施间存在时间差, 届时须复核事实是否漂移 (尤其 T2 的索引清单与 T1 的 finding anchor)。

## [DEV-0187] POST-R2 设计包实施 — T1~T6 六项全部落地
- **时间**: 2026-09-12 16:50
- **类型**: 功能开发 (设计包实施批)
- **关联模块**: `backend:utils/url_safety`, `backend:quality/*`, `backend:wiki_fs/liveness`, `backend:services/url_batch_check`, `backend:observability_records`, `backend:services/interest_engine_service`, `backend:repository/hotspot_repo`, `backend:repository/migrations/114` (新建), `scripts:audit_interest_recalibration` (新建), `scripts:t02_restore_drill`, `docs:security/MIMOSA_TRIAGE_LEDGER` (新建), `docs:decisions/ADR-0001` (新建), `docs:RUNBOOK`
- **关联文件**: `backend/quality/final_url_resolver.py`, `backend/quality/url_validity_gate.py`, `backend/services/url_batch_check_service.py`, `backend/wiki_fs/liveness.py`, `backend/tests/test_liveness.py`, `backend/tests/test_interest_engine.py`, `scripts/audit_interest_hit_rate.py` (无改动核对), 设计包 docs
- **问题描述**: owner 指令按 `docs/POST_R2_ENHANCEMENTS_DESIGN_2026-09-12.md` 完成开发; 六项 = Mimosa triage / 死列 DROP / 权重重校 / ai-tech 桶 ADR / 恢复 scrub / RUNBOOK 周期审计。5 项裁决按设计包推荐选项执行 (vendor 豁免 / 删 spike / 执行 114 / 方案 A / DELETE scrub), 已在各工件中如实记录采纳方式。
- **实现思路**: T1 三层漏斗实做 — vendor 147 + 故障注入工具 18 整体豁免, backend 33 条逐条核对源码: **A-修复 9** (SSRF ×6: 四文件出站统一改走新增的 `url_safety.safe_urlopen` 单收口, UrlSafetyError 按调用方语义映射 None/url_unreachable/0/dead; savepoint 名 re.sub 白名单化 ×3) + **B 22** (逐条依据入台账, 如 source_prober 已防护/mitre 固定源/dispatch 有 realpath 围栏/mcp 有白名单正则/ULID 非加密); spike_gateway_s1_s3.py 删除 (凭据实为 dummy + spike 约定)。台账 `docs/security/MIMOSA_TRIAGE_LEDGER.md` 覆盖 270/270 (33 条逐条 + 三类批量处置)。T2: migration 114 (先 DROP idx_hotspot_region 再 DROP region/bid_status; weekly_reports.bid_summary 在 warm 有历史数据保留), 改库前三库一致性备份 + sha256 manifest 落 backups/pre-migration-114/, 三库副本演练通过后重启上产。T3: `evaluate_recalibration_rules` 纯函数 (R1 deep_read 锚偏移/R2 view 灌水/R3 C 常数) 入 service 可单测, 脚本 audit_interest_recalibration.py 零 SQL 只呈现。T4: ADR-0001 记录 tech 并入 ai 桶为既定设计。T5: `scrub_legacy_bid_rows` SQL 下沉 hotspot_repo (脚本零 SQL), restore_drill 恢复后自动清扫+计数入 report, 演练注入 bid 行验证 1→0。T6: RUNBOOK 增"兴趣引擎周审计"四步表。
- **核心变更**: 见关联文件; 新增 safe_urlopen (validate+pre_resolve+urlopen 一体); interest_signals_since 补 signal_type/item_id 字段 (聚合消费方兼容)。
- **测试验证**: 全量 pytest **4466/0** (+8 重校规则正反例, test_liveness 重写为 safe_urlopen 边界打桩并新增环回拒收→dead 语义测试); vitest 494 / tsc 0 / meta --check OK; migration 114 副本演练 (version=114, 两列+索引消失) → 生产应用后 PRAGMA 复核无残留, health 200; restore drill 演练 bid 1→0; 重校脚本空库跑通。
- **潜在风险**: ①safe_urlopen 对探测类场景不做连接级 IP 锁 (DNS rebinding 残余风险, 与 source_prober 同水位, 文档已注明) ②db.py 悬空 view 清理的标识符插值按扫描器策略维持原状 (B 豁免: sqlite_master 自省+DDL 无绑定), 若未来 Mimosa 支持标识符白名单写法可再加固 ③T1 台账对 vendor 的豁免以上游不进生产路径为前提 (ADR/台账均有失效条款)。
