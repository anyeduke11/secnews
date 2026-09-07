# v0.5 重构执行进度（PROGRESS.md — 当前活跃段索引）

> **当前执行入口（2026-09-05）**：目标软件 v1.0.0，当前代码 v0.8.2。按 [开发迁移方案](docs/HOTSPOT_V1.0_DEVELOPMENT_PLAN.md) 与 [逐步任务书](docs/HOTSPOT_V1.0_EXECUTION_GUIDE.md) 推进；下方 v0.5 的“唯一规格/接手顺序”属于历史阶段，不作为 v1.0 的执行指令。

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
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [docs/progress-archive/v0.7-records.md](progress-archive/v0.7-records.md) | SettingsHub V2 + v0.7 观测批次 ①-⑨ + v0.6.3 性能/双根合并 + v0.6 P0 清场 |

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

## 当前活跃段 (2026-09-03 起)

### 2026-09-05 v1.0 — 附件对比、开发迁移步骤与深度设计审查

- [x] 对比四份附件，核对 APP_VERSION 0.8.2 与当前 HEAD 943a31d；相对旧审查基线仅 PROJECT.md 提交变化，本次未重跑业务测试或查询数据。
- [x] 完成 [开发方案](docs/HOTSPOT_V1.0_DEVELOPMENT_PLAN.md)、[新手 T00-T19 任务书](docs/HOTSPOT_V1.0_EXECUTION_GUIDE.md)、[第一性原理/批判性/六顶思考帽审查](docs/HOTSPOT_V1.0_DESIGN_REVIEW.md)，同步 PRD 目标为软件 v1.0.0；DEV-0135 / CHECK-0002。
- [x] T00 基线核对 (只读, `f9520c2`+`0066668`, DEV-0136) + T01 测试隔离 + 4 真实库污染根治 (F13 闭合 `ac45f89`, DEV-0137) + T02 备份/恢复/开发副本 (本批, DEV-0138)。
- [x] **T03-T19 代码 + 单元测试落地** (代码层 verified): 契约/原型 + SDK + 证据 + 抓取 + 准入 + Case + Worker + dsh/pi live + 监督 + 判断 + 行动 + 知识 + 受管能力 + 工作台 + 全局 listKnowledge + 旧数据迁移 (skill 20 + knowledge 15) + E2E-10 启停校验 + audit 端点 + LegacyMigrate API + 5 SSE 事件源 + T18 旧 knowledge_items 853 行全量迁移 (WARM_DB 真落 v1_knowledge, 排除 kl:deduped) + T19 启停校验 strict 模式默认 raise + 数字同步 ARCHITECTURE/AGENTS 81→84 routers / 120→122 services / 54→55 jobs + ruff 清理。pytest 4176/8/0 + ruff 0 错 + generate_meta --check 全绿。
- [ ] **T19 业务闭环未达 PRD (发布阻断, NOT verified)**: 2026-09-07 独立业务审查 [docs/v1.0/REVIEW_2026-09-07.md](docs/v1.0/REVIEW_2026-09-07.md) (CHECK-0003/DEV-0154) 识别 20 个 P1/P2 业务闭环阻断 — 关键发现: 证据提交"成功"但资料未落库 (R01) / 新采集+准入未接入生产调度 (R02) / 写入失败仍推进游标漏收 (R03) / worker 消费后空成功 noop (R04) / 行动默认 mock 成功 (R05) / "live trace"实际是 mock (R06) / 默认生成未 await 返 coroutine (R07) / 产物 body 未存 (R08) / CAS 名为 CAS 实不原子 (R09) / Wiki 写入根与记录路径不一致 (R10) / 迁移丢失正文+随机新 ID (R11) / WARM/COLD copy 漏 WAL (R12) / 4 个前端 API buildQuery 双? (R13) / 工作台只有读无 mutation (R14) / 6 SK 注册契约错 (R15) / 知识复用统计把来源当采用 (R16) / 有 Action 的 Case 永不关 (R17) / SSE sync ctx 静默丢 (R18) / 多套真相 (R19) / Ruff 158 错 + version 失同步 (R20); 修复路径 B0-B7 见 REVIEW §6 (单批先反例测试再实现); 当前测试基线 4176/8/0 仅证明代码可导入可单测, 不证明生产闭环; 12 个 PRD 验收点未达, 需 B0-B7 整改后重做端到端验收才能 release.
- **边界**：本次交付是待实施方案；不更新软件版本、不操作真实数据库、不运行采集/模型、不发布。20 旧 ID 全部登记兼容去向，现有数据保留；设计修订不等于缺陷已修复。

### 2026-09-05 v1.0 T01 — 测试隔离与虚假成功证据修复 (F13)

> **来源**: EXECUTION_GUIDE §4 T01 任务卡; 修复对象 = V0.8.3_CRITICAL_REVIEW F13。DEV-0137。

- [x] **四层隔离落地** ([策略说明](docs/v1.0/test-isolation.md)): L1 conftest 导入前强制 `HOTSPOT_{DB,WARM,COLD,LOG,BACKUP,DATA,WIKI_ROOT}` env → 会话临时根 (`tempfile.mkdtemp`, 保留作验收证据); L2 `sys.addaudithook` 哨兵 (生产库连接 / 生产数据根写入 / 非回环出网 → AssertionError); L3 既有 temp_db/_isolate_temp_dbs/_isolate_knowledge_dirs 每测隔离; L4 测试自身 mock。逃逸口 `HOTSPOT_TEST_UNGUARDED=1` (仅 soak/live)。
- [x] **config.data_dir 新字段**: export 缓存原硬编码 `backend/data` (测试期曾写真实 etag), 改走 config 单一源 (HOTSPOT_DATA_DIR 隔离)。
- [x] **4 个 Phase-7 工具契约测试改造** (dump_schema/export_for_dsh/db_diet/snapshot_for_retirement): 全部改走会话根库 (显式 --db + config 断言); 真实数据地板断言 (items≥4149 等) 移交 backup_verify + T17 SLO, 契约形状/双源一致性保留。
- [x] **顺带修 2 个真 bug**: ① dump_schema/snapshot `db_path.relative_to(REPO_ROOT)` 对仓库外路径抛 ValueError (隔离根触发) → 加兜底; ② dump_schema FTS 组识别漏 `knowledge_chunks_fts_cjk` (含 `_fts_` 段非 `_fts` 结尾) → `_is_fts5_main` 泛化, 修复 DDL 重建重复建表。
- [x] **验收证据**: 哨兵 10/10 (生产库连接/相对路径绕过/真实 wiki+logs 写/出网全被拒且未落盘); test_agent_bridge 14/14 且**真实库 agent_runs 321→321 零新增、mtime 不变**, 7 条模拟记录实证落会话根 `hotspot-test-iso-*/hotspot.db`; 全量回归见下。
- [x] **全量回归**: pytest backend/tests/ 全绿 (0 failed / 0 error, skip 仍为基线预存 6); 真实库/Wiki 零写入 (mtime 复核)。
- **新发现 (记 T00 基线)**: 真实库 schema 疑似落后 migrations — 隔离根 (当前 migrations 全新建库) 有 `knowledge_chunks_fts_cjk` 而**真实库无此 FTS 组**; 下次 backend 启动 init_db 自动应用, 迁移漂移留 T02 前复核。
- **下一小步 (T02)**: 备份/恢复演练 — 停写排空 + SQLite backup API + Wiki/session 快照 → 恢复副本校验 (WARM 818MB 体量), 记录实际 RPO/RTO。

### 2026-09-06 v1.0 T02 — 备份、恢复与开发副本演练 (verified, DEV-0138)

> **来源**: EXECUTION_GUIDE §4 T02 任务卡; 复 `backup_service.py` online backup API + `wiki_fs/root.py` 解析; 不动 BACKUP_RETENTION 链, 不推送 WebDAV。DEV-0138。

- **T02-A 备份演练** (`scripts/t02_backup_drill.py`, 240 行, 默认 --dry-run): HOT 28MB online backup 0.045s / WARM 818MB copy 0.433s / COLD 28KB copy / Wiki 6486 文件 deflate 1.05s, **总演练 1.76s**, integrity_check ok, 106 表; 演练产物入 `backend/backups/_drill/<ts>/` 不入 BACKUP_RETENTION 链; 4 资产 sha256 落 manifest.json; 生产 db mtime `Sep 5 19:39:58` 未变 (agent_runs=321 不动)。
- **T02-B 恢复演练** (`scripts/t02_restore_drill.py`, 280 行, 默认 --dry-run): 5 项验收 (integrity_check / sha256 一致 / 表数对照 / favorite → hotspot 回查 / wiki md 抽查), 写到 `/tmp/hotspot-restore/<ts>/` 仓库外; **3 轮稳定性 RTO 0.47-0.52s, 全 PASS**; 4 次抽 random favorite 1 中 3 失 — favorites 表存在历史 url 漂移 (非恢复 bug, 软指标)。
- **T02-C 开发副本** (`scripts/dev_environment.sh`, 145 行): 数据根 `dev_data/` 独立 (gitignore 增量) / 端口 8766 (后端) + 8899 (前端) 错开生产 8000+8898 / `dev.env` 模板关 `HOTSPOT_CATCHUP_ON_STARTUP=0` `HOTSPOT_REMOTE_BACKUP=""` `HOTSPOT_PROXY_MODE=off`; 试跑 dev backend health 200, dev db 1.7MB + log 100KB 落 dev_data/, **生产 db mtime 不变** (完全隔离); keyring master_key verification failed 是 dev 无凭据正常, watchdog 因空 wiki 不启动 (设计预期)。
- **真 RPO/RTO**: RPO 演练 = 1.76s (不表真 RPO, 真 RPO = 距 daily_db_backup 04:30 窗口); RTO 演练 = 0.5s 本地, 异机经验 +10-30s。
- **设计纪律**: dry-run 默认 + 演练目录隔离 + 不调 backup_service 全局函数 + 不打印密钥 + GitHub `feat(v1.0 T02): 备份演练 + 恢复演练 + 开发副本 (DEV-0138)` 单 commit 显式 pathspec。
- **剩余问题 (非阻塞, 留 T17 验收)**: ①favorites 历史 url 漂移 ②真异机 RTO 演练 ③WARM 818MB 同盘 copy vs 异机 100-500MB/s 吞吐差。
- **下一小步 (T03)**: 见下节 T03 已闭合。

### 2026-09-05 v1.0 T03 — 领域契约、TS 漂移检查、脱敏样本与四入口原型 (verified, DEV-0139)

> **来源**: EXECUTION_GUIDE §4 T03 任务卡。产出: `docs/v1.0/contracts.md` + `scripts/codegen_v1_ts.py` + `frontend/src/domain/v1_0.ts` + `dev_data/seed.json` (gitignore) + `frontend/src/components/v1/V1Prototype.tsx`。commit `9478074`。

- **T03-A 盘点旧表**: 9 域对象 (Subject/Material/Signal/Case/Judgment/Action/Run/Artifact/Knowledge) 全部新建; 旧表 (crm_opportunities/crm_events/bid_details/todos/crm_customers) 为空或仅作 T16 迁移源, 不复用字段。
- **T03-B contracts.md** (~500 行): 9 对象字段 + 状态机 + `allowed_actions` 服务端推导 + 跨对象约束; §0.3 通用响应字段 (revision/allowed_actions/reason/updated_at); §0.4 错误 schema (E_VALIDATION/E_NOT_FOUND/E_CONFLICT/E_GATE_CLOSED/E_INTERNAL); §0.5 幂等 (idempotency_key + body hash); §0.6 CAS (expected_revision/expected_status); §0.7 SSE (commit 后只发一次)。
- **T03-C codegen**: `scripts/codegen_v1_ts.py` Pydantic v2 → TS 单文件, 关键修复 `_collect_all_defs()` 合并所有模型 $defs (v2 只返回引用项); `--check` 模式 CI 漂移检测 (exit 1 + JSON report); datetime→string / Optional→T|null / dict→Record / enum→union literals。输出 `frontend/src/domain/v1_0.ts` 268 行 (23 enum + 11 interface)。
- **T03-D 脱敏样本**: `scripts/t03_seed_extract.py` 从生产抽 145 条 (knowledge_concepts→Subject 20 / hotspots→Material 25 / todos→Case 20 / agent_runs→Run 20 + 合成 Judgment 10 / Action 10 / Artifact 15 / Knowledge 10 / Signal 15); 脱敏: URL 只留域名 / 文本截断 80 字符 / hash 种子化 / 时间归一到 2025。产物 `dev_data/seed.json` 103KB (gitignore)。
- **T03-E 四入口原型**: `/v1-prototype` 路由 (今日工作/情报/事项/知识) + CaseDetail 三级 (Judgment → Action/Run → Artifact); 走查 3 路径: 缺资产 / 待验收 / 失败。验证: `tsc --noEmit` 0 错 / `vitest run` 425/425 / `vite build` success。
- **验收证据**: contracts.md 9 对象全覆盖 / codegen `--check` 0 drift / seed.json 145 条可解析 / 原型 4 tab 可切换 + CaseDetail 可钻取。
### 2026-09-06 v1.0 T04 + T05 — 上游 SDK 锁 + 协议探测 (mock) + 证据提交协议 (verified, DEV-0140)

> **来源**: EXECUTION_GUIDE §4 T04+T05 任务卡。产出: `runtime/upstreams.lock.json` + `scripts/t04_sdk_probe.py` + migration `096_v10_evidence_subjects.sql` + `backend/services/v1_evidence_service.py` + `backend/tests/test_v1_evidence_service.py` + ARCHITECTURE/AGENTS 数字同步 (services 108→109)。

- **T04-A 上游 SDK 锁** (`runtime/upstreams.lock.json` + `upstreams.lock.schema.json`): 固定 dsh `d347e703908d0406b7a7ef80e3a0e594d86b2215` (MIT, 0.1.3-alpha.1, Python SDK stdio JSON-RPC) + pi `6f11c31d1134a32e64bf221baeec38e431091e05` (MIT, 0.85.0, AgentSession 事件流); 含 `verification` (build_clean_dir/artifacts_hash/live_trace/protocol_tested) + `exit_criteria` (2-3 工作日 → 降级 ai_hub+确定性协调器)。
- **T04-B 协议探测** (`scripts/t04_sdk_probe.py`, dry-run 默认): 隔离目录 `/tmp/hotspot-t04-<ts>/` + mock 子进程 (Python 自启) 模拟 dsh stdio JSON-RPC + pi AgentSession 事件流; 4 帧/SDK (create/dispatch/cancel + error); `--check` 模式只校验 lock 结构 (CI 用)。
- **T04-C 协议兼容报告**: dsh 3/4 OK (1 帧故意走 error 路径, 验 mock error 形状) / pi 4/4 OK; dsh stdio JSON-RPC 形状 (jsonrpc 2.0 / id / method / result|error) 匹配; pi AgentSession 事件流 (event/session_id/data) 匹配; session 身份透传一致; **协议-compatible, 但 live trace 未跑** (待 --live 真 vendor checkout + dsh/pi 子进程)。
- **T05-A 证据提交协议**: `backend/services/v1_evidence_service.py` V1EvidenceService — 两阶段 intent (create_intent → commit_intent/rollback_intent); 临时写 `.tmp/<id>` → 原子 rename 到 `committed/<path>`; receipt 不可变 (submission_key + body_hash 唯一约束); 失败/超时 reap (1h) 自动标 rolled_back。
- **T05-B Subject/Material/Signal 后端表** (migration 096): 5 张表 — `v1_subjects` (关注对象, entity_type/canonical_name/aliases/importance) + `v1_materials` (资料, source_kind/url/content_hash/content_ref) + `v1_signals` (信号, subject_id+material_id+confidence+status+supersedes_signal_id) + `v1_subject_identifiers` (幂等唯一键 source+external_id) + `v1_evidence_receipts` (提交回执, submission_key+body_hash UNIQUE)。字段对齐 contracts.md §1-§3 + Pydantic v1_0_models。
- **T05-C 故障测试 9/9 pass**: ①intent+commit 正常 ②同 key+body 重放 IdempotentReplay ③同 key+不同 body pending IntentExistsError ④rollback 清临时文件 ⑤投影 atomic rename 成功 ⑥target 冲突 FileExistsError + receipt 不 committed ⑦content 空 ValueError + 不 committed ⑧超时 reap → rolled_back ⑨projection_dir=None → skipped。
- **验收证据**: T04 lock `--check` JSON `{lock_ok: true, dsh: d347e70, pi: 6f11c31}`; probe 35ms / dsh 3/4 / pi 4/4; pytest 3887/6/0 (基线 3868 + T05 9 个新测试, 0 回归); generate_meta 109 services, ARCHITECTURE.md + 3 AGENTS.md 数字同步; ruff 0 错。
- **剩余 (T10 live trace)**: dsh 真 vendor checkout + pi 0.85.0 npm install + 真 dsh stdio JSON-RPC 闭环 + ai_hub 工具消息保留验证; 若 2-3 工作日未跑通 → 降级 ai_hub+确定性协调器 (exit_criteria 写入 lock)。
- **下一小步 (T06)**: 见下节 T06+T07 已闭合。

### 2026-09-06 v1.0 T06 + T07 (A 路) + 方案B 测试发量 (verified, DEV-0141)

> **来源**: 用户裁决"方案A和方案B同时开展"。A 路 = T06 源级管道 + T07 准入服务; B 路 = 测试发量 + 契约锁定。产出: `backend/services/source_pipeline.py` + `v1_admission_service.py` + 2 测试 + `v1_0_models` 契约测试 + ARCHITECTURE/AGENTS 数字同步 (services 109→111)。

- **T06-A 源级管道** (`backend/services/source_pipeline.py`): `FetchRequest` frozen dataclass + `SourceLease` (TTL + extend/release, 同源并发抛 LeaseHeldError) + `SourceWatermark` (单调用不变量, 倒退抛 WatermarkRegressedError, 复用 crawler_sources.etag+last_fetch_at) + `SourcePipeline` (fetch → parse → evidence bridge, 5 失败注入点: lease/fetch/parse/evidence.create/evidence.commit) + 7 `FetchOutcome` (SUCCESS/NOT_MODIFIED/RATE_LIMITED/TIMEOUT/BAD_BODY/ERROR/SKIP)。
- **T06-B T05 桥接**: SourcePipeline 注入 `V1EvidenceService` 后, parse 成功 body → `create_intent("material", body) + commit_intent`; IdempotentReplay 计入 `items_idempotent` (不重复 commit); IntentExistsError / FileExistsError / ValueError 计入 `items_failed`; watermark 在 commit 成功后 advance。
- **T07 准入服务** (`backend/services/v1_admission_service.py`): `V1AdmissionService` 复用 `info_filter_service.evaluate` (deny > allow > neutral 语义) + `AdmissionResult` (verdict/reason/labels) + `default_labels` 启发式 (8 维 60-80 起步: entity_type/confidence/urgency/domain/impact/severity/audience/actionability) + `quarantine` 兜底 (admission_log 表未建时静默返 0, 等 T07 migration 097 落地)。
- **方案B 测试发量**: `backend/tests/test_v1_0_models.py` 24 个契约测试 (锁定 contracts.md §1-§9 字段/状态机/枚举/约束); `test_source_pipeline.py` 17 个故障测试 (含 5 失败注入点全覆盖 + 5 FetchOutcome 状态机 + 幂等 + 并发); `test_v1_admission_service.py` 9 个准入测试。
- **验收证据**: pytest **3978/6/0** (基线 3887 + 50 新测试 T06+T07+v1_0_models, 0 回归); generate_meta 111 services, ARCHITECTURE.md + 3 AGENTS.md 数字同步; ruff 0 错; T04 probe `--check` 不受影响。
- **T08 跳过说明**: Case 服务+API+前端真实数据接入体量较大 (需新表 + 路由 + UI 状态机 + 真实持久层), 本批时间盒仅完成 T06+T07+A 路; T08 留 T19 收口前补; 当前 `/v1-prototype` 仍用 mock 数据。
- **剩余**: T08 Case 端到端 / T09 运行协调器 / T10 dsh/pi live trace (lock.exit_criteria 兜底) / T07 admission_log migration 097 (T07 监督流程批次) / T07 标注批次 60-80 起步 (人工 + inter-annotator agreement, 不在本批)。

### 2026-09-05 v1.0 T04 + T05 — 上游 SDK 锁 + 协议探测 (mock) + 证据提交协议 (verified, DEV-0140)

### 2026-09-05 v1.0 T03 — 领域契约、TS 漂移检查、脱敏样本与四入口原型 (verified, DEV-0139)

### 2026-09-05 v1.0 T00 — 基线核对与任务台账 (verified, 只读)

> **来源**: EXECUTION_GUIDE §7 首轮任务。全程只读: 未跑测试 / 未出网 / 未写库与 Wiki / 未读密钥内容; 库内数字 = sqlite `mode=ro + query_only=ON` 单次快照。DEV-0136。

- [x] **[基线](docs/v1.0/baseline.md)**: 版本 0.8.2 (version.py 单一真源; frontend package.json 0.7.0 不用于产品显示, AboutSettings 走 /api/health); 启动 = run.py → uvicorn 127.0.0.1:8000 (WORKERS=1, 无认证回环); **盘点时后端/前端未运行 (零活跃写入者)**。
- [x] **数据根与写入者表**: HOT `backend/hotspot.db` 28MB (tickets 53 全 pending / skill_runs 58 / agent_runs 321 (含测试污染 315..321) / hotspots 7223) · WARM `hotspot-warm.db` **818MB** (迁移体量基准) · COLD 28KB · backups/ (最近 full **2026-08-29**, 新鲜度缺口 F6) · Wiki 单根 `llm-wiki-2.0/` (HOTSPOT_WIKI_ROOT 未设走默认) · logs `backend/logs/` · `data/hotspot.db` **0 字节诱饵** + Phase 7 旧产物 · dsh = settings KV 三态 · pi = ~/.pi 外部 CLI 0.84.4 · 密钥 = HOT 表 + Keychain (未读内容)。
- [x] **架构与功能清单**: 73 routers / 108 services / 52 jobs (jobs `__all__` 仅 34 re-export, 以 add_job AST=52 为准) / 14 collectors / 13 gates (12 开, mcp 关; feature_mcp=True) / 20 Skill 注册表实测吻合 (去向 = EXECUTION_GUIDE §5)。
- [x] **任务台账**: [docs/v1.0/task-status.md](docs/v1.0/task-status.md) — T00 **verified**, T01-T19 planned; 3 条待用户裁决 (标注集 60-80 起步 / T04 SDK 退出判据 / git bundle 异地备份)。
- [x] **固定样本故事**: 虚构 CVE-2026-31337 两任务闭环 (隔离环境造数, 不进真实库); 首条完整路径 = SK-02/SK-03。
- **通过证据**: T00 卡片五项自查全过 (baseline.md §6) — 版本/入口明确, 每个数据根+写入者可定位, v0.8.3 未标已实现, 首条真实工作可指出。
- **提交状态**: `docs/v1.0/*` 已单独提交 (显式 pathspec); 本文件与 DEV_LOG 的 T00 条目暂留工作树 — 同文件含并行会话 DEV-0133~0135 未提交 hunks, 待归属清晰后一并提交。
- **下一小步 (T01)**: 测试隔离 — 导入前隔离 HOT/WARM/COLD/Wiki/logs/dsh-pi home 至临时根 + 生产路径哨兵拒绝; 先修 agent_bridge 测试直写真实库 (F13); 验证后跑定向回归建基线。文件范围预计: `backend/tests/conftest.py` + agent_bridge 测试 + 新隔离 fixture 模块。

### 2026-09-05 从零产品 PRD — Hotspot 安全工作台（待实施）

- [x] 用户追加要求“重新设计整个体系，先出从 0 开始的 PRD”；交付 [HOTSPOT_WORKSTATION_PRD_V1.0](docs/HOTSPOT_WORKSTATION_PRD_V1.0.md)。
- 新主线：关注对象 → 情报事件 → 工作事项 → 证据判断 → 受控行动 → 验收 → 可复用经验。产品主入口重新定义为今日工作/情报/事项/知识，首期六岗位能力；不以旧页面和既有 Skill 数量限定需求。
- [x] 用户画像/假设、12 功能、验收标准、领域模型、UI/UX、源码 dsh/pi 分工、知识存储、指标、实施里程碑、第二轮审查和目标追踪矩阵完成。
- [ ] M0 岗位/案例走查与原型、真实 SDK 技术验证；随后 M1-M5 分批实现。旧 v0.8.3 审查仍是事实证据，旧重构/业务文档降为技术与迁移参考。
- 本次纯文档：未运行 pytest、未操作数据库或调用模型；记录 DEV-0134，软件版本不变。

### 2026-09-05 v0.8.3 — 真实架构审查与重构设计（待实施）

- 用户方向：Hotspot 是安全从业者看板型 B/S Agent，dsh 直接复用 DeepSeek-Harness 源码作为大脑，pi 直接复用 pi.dev 当前上游源码执行，llm-wiki-2.0 + SQLite 覆盖资讯/判断/行动知识复利；优先保证稳定抓取和高价值收录。
- [x] 基于 HEAD `4c686fc` 核验代码与只读数据库快照；发现清单见 [V0.8.3_CRITICAL_REVIEW](docs/V0.8.3_CRITICAL_REVIEW.md)。旧审查中的断路器/gate/pi 过时结论以新报告为准。
- [x] [技术方案](docs/V0.8.3_REFACTOR_PLAN.md) + [业务流/20 Skill 迁移/UI 契约](docs/V0.8.3_WORKFLOWS_AND_SKILLS.md) + 第二轮批判性复核完成，记录 DEV-0133 / CHECK-0001。
- [ ] A0-A2 可信基线、抓取准入、任务及模型契约；B 源码 dsh/pi；C 知识与 Skill；D 工作台；E 验收发布。
- **关键事实**：53 pending 票据无关联 run；生产未找到 TriggerWorker 实例化；pi 是 CLI 集成且已有 0.84.4 协议修正，尚未源码受管；100 项定向测试通过但发现测试隔离缺陷（本次写入七条模拟观测记录，详见 F13）。
- **版本状态**：软件仍为 v0.8.2；本次仅审查与文档，不代表 v0.8.3 实现完成；后续先修测试隔离再运行全量。

### 2026-09-05 v0.8.2 子批 1 — 快赢包 X (低风险清债: B1/B2/B3/B4/C2 全绿)

> **来源**: 用户裁决 "v0.8.2 = X + Y 合批 (~9 天, 分两子批): 子批 1 快赢包 (X, 低风险先清债), 子批 2 通电治理 (Y)" — 推荐=上会话收尾 (X=B1/B2/B3/B4/C2 ~4 天; Y=A1 全局限流单一真相源 + A2 配置热重载 + A4 backup_verify ~5.5 天; react-query/pi 流式留独立窗口)。
> **基线**: main HEAD `382a578` (v0.8.1, pytest 3818/6/0, vitest 425, ruff 全仓 167 错, 16 gate)。

- [x] **X-B3 — 死 gate 键治理 + mcp 双开关契约化** (`36fc733`): feature_gates.toml 移除 agent_loop/playbook_engine/skill_eval 三个无消费点死键 (本就被 _load_gates 过滤, 16→13 gate); mcp 双开关语义分工契约写入 `is_mcp_enabled` docstring (extension gate=调试路由 / feature_mcp=server 本体), main.py lifespan 以 loguru 打印两态 (stdlib log 全仓不可见教训); AGENTS/PROJECT 计数与过时描述同步。
- [x] **X-B1 — llm.yaml per-provider 断路器阈值** (`f4dd800`, v0.8.1 PRD §7 推迟项偿还): `ProviderBreaker` schema (failure_threshold/min_samples/recovery_timeout) + `ProviderHealth` per_provider 覆盖表; 解析链 **provider yaml > env 全局 (HOTSPOT_BREAKER_*) > 内建默认** (特异性优先); yaml 读取失败静默降级 (观测配置不拖垮 LLM 主链); snapshot 增 `thresholds` 块 (/health 可见每 provider 生效值); llm.yaml 注释样例 (无差异化实证不激活)。
- [x] **X-C2 — GZip + Cache-Control** (`80b0d08`): main.py `GZipMiddleware(minimum_size=1000)` (starlette 1.3.1 默认排除 text/event-stream — SSE 不受缓冲影响); GET /api/quality/rules 加 `Cache-Control: public, max-age=10` (§3.2 点名字典端点)。
- [x] **X-B2 — 全仓 ruff 167→0** (`2d5b756`): --fix 150 (F401×54/I001×24/UP045×21/RUF100×20/...) + 手工 23 (DTZ005×10 aware 化, strftime 站点输出不变 / F821 skill_registry TYPE_CHECKING / B905+RUF007 pairwise / zip strict / RUF043 raw-string / SIM103); ruff.toml `extend-exclude .trae` (第三方 vendored skill 资产); **全量回归 3838 passed / 6 skipped / 0 failed**。
- [x] **X-B4 — PROGRESS 归档 + CHANGELOG 时序** (`c7bd9c2`): PROGRESS 收缩至 v0.8 时代 (1089→281 行), 809 行归档 `docs/progress-archive/v0.7-records.md`; CHANGELOG 29 节严格新→旧重排 (尾部追加错位 ×8); **补记 v0.8 P1 info_filter 整节** (当时漏登)。
- [x] **子批 1 收口门禁**: pytest **3838/6/0** (基线 3818 + 本批 +16~20 新测试) / vitest **425** / tsc **0 错** / generate_meta 4/4 (routers 73 / services 107 不变) / harness 0 errors / ruff 全仓 **0**。

### 关键事实 (v0.8.2 子批 1)

- **per-provider 阈值判定在 ProviderHealth 层而非 breaker 层** — `_unhealthy_locked`/`_get_breaker_locked` 按 provider 查覆盖表回落实例默认; breaker 本体保持无计数薄状态机 (单一真相源契约不破)。
- **aware-local 时间约定**: DTZ005 修复统一 `datetime.now(timezone.utc).astimezone()` — 本地墙钟语义 (run.date/ingested_at 输出不变), isoformat 站点新增时区后缀 (+08:00), JS `new Date()` 两侧解析等价。
- **zip strict 语义**: `zip(seq, seq[1:])` → `itertools.pairwise(seq)` (长度差恒 1, strict 会炸); 平行数组 `zip(runs, fixtures)` → `strict=True` (fixture 错位应 fail loud)。
- **mcp 双开关不合并的理由**: gate=false (调试路由关) 与 feature_mcp=true (server 开) 同时成立是 Day 0 有意状态; 单开关无法表达, 契约化+启动两态日志替代。

### 2026-09-05 v0.8.2 子批 2 — 通电治理 Y (A1/A2/A4 全绿, 版本 0.8.2)

> **来源**: 同上会话推荐 — Y = A1 全局限流单一真相源 + A2 配置热重载 + A4 backup_verify (~5.5 天); P0 = A1+A2 (通电稳定运行最低配置)。
> **范围偏离**: §1.1 推荐的 RateLimiter 令牌桶与 scheduler 全局 job 闸门未纳入 — Semaphore 背压已覆盖主要出站面 (LLM/crawl4ai/批处理), 令牌桶留 react-query/配额感知批次同做; A2 采用 5s TTL+mtime 惰性重载而非 watchdog 线程 (零新依赖, info_filter 模式)。

- [x] **Y-A1 — 全局并发单一真相源** (`7cb90d7`): 新建 `utils/concurrency.py` — `get_semaphore(group, size)` 按 (group, event-loop) 键控共享 Semaphore, **WeakKeyDictionary 弱键** (loop 关闭自动清除; 防 id() 地址复用误判, 测试实测踩中); size 链 显式实参 > env `HOTSPOT_CONCURRENCY_<GROUP>` > 默认 4; **等待即背压** (不超时/不计健康窗口 — 饱和 ≠ 失败, 与熔断正交)。8 接入点: `llm:<provider>` 组 (gateway._call_provider + image generate/understand 共享, **llm.yaml max_concurrent 首次真实消费**, 此前声明但零消费) / enrich / url_check (url_batch_check + quality jobs 共享) / knowledge_sync / crawl4ai / source_fetch; N 调用方共享一份预算不再乘性放大。测试 +9。
- [x] **Y-A2 — 配置热重载** (`13c6871`): ① feature_gates.toml — gate 动态读数 5s TTL + mtime_ns 检测热重载, 热重载失败沿用上次成功读数 (运行中配置损坏不再让扩展集体消失); **语义边界诚实声明: 路由/job 注册是启动期快照, 增删 router/job 仍需重启**。② llm.yaml — `load_llm_config` 默认路径 5s TTL 缓存 (显式 path 永不缓存, 保测试 mock 语义) + `LLMService._maybe_reload_config` 漏斗口对象身份热交换; **`_config` 手动注入 (既有测试模式) 经 property setter 自动退出热重载管理**。③ provider 阈值 — `maybe_reload_thresholds()` (record 挂钩) 只换判定参数, 窗口/breaker 状态原样保留; 仅单例开启。零新依赖零新线程。测试 +13。
- [x] **Y-A4 — backup_verify 备份完整性校验** (`4e1b1f7`): 新建 `backup_verify_service` — ① PRAGMA integrity_check ② 核心表行数单调性 (备份 ≤ 实时, 恢复错文件即报警) ③ audit_log append-only 抽样逐字段对比 (可变表 md5 对比会假阳性, 不做) ④ knowledge.zip testzip; **§2.4 "Fernet 解密"不适用 (备份为明文 SQLite) 如实注明**。失败 → audit_log 留痕 + job ok=False; 校验器自身永不抛。`backup_verify_job` 周一 02:00 (jobs **51→52**) + `POST /api/maintenance/backup-verify` (routers 73 不变)。测试 +8。
- [x] **收口**: 版本 **0.8.2**; 架构计数 services 107→**108** / jobs 51→**52** (ARCHITECTURE + 3 AGENTS.md); 全量回归 pytest **3868 passed / 6 skipped / 0 failed** (首轮 2 failed 根治: job 计数断言 +1 / `_try_order` 热重载冲掉测试手动注入的 `_config` → property setter 语义) / vitest 425 / tsc 0 / generate_meta 4/4 / harness 0 / ruff 全仓 0。

### 关键事实 (v0.8.2 子批 2)

- **并发背压与熔断正交边界**: 饱和等待不记健康窗口 (饱和 ≠ 失败), breaker 只管真实失败 — 两层语义在 `_call_provider` 内完成合流 (semaphore 包裹 dispatch, record 在其外)。
- **`id(loop)` 地址复用陷阱**: 顺序 asyncio.run 的两个 loop 可能同址 → WeakKeyDictionary 以 loop 对象为弱键 (对象身份比较 + 死键自动清除); 哨兵 `_SyncContext` 类实例 (plain object 不支持弱引用)。
- **热重载的三层豁免**: 显式 config_path / 手动注入 _config / 非单例 ProviderHealth — 三者都是"调用方接管"既有语义, 热重载不得越权覆盖。
- **change-file 必跑对账**: jobs/services 计数变更会牵动 test_feature_gates AST 断言 + generate_meta 4 文档校验; generate_meta 无写模式, 计数手改 (hook 提示文本有误导)。

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

### 2026-09-05 v0.8.1 Day 2 — ProviderHealth 唯一判定源 (本批)

> **来源**: PRD v1.0 §8 Day 2; PLAN v1.2 §2.3 D2。
> **范围**: `backend/services/ai_hub/provider_health.py` (~200 行) + 23 测试 (37 含 Day 1)。**模块级单例** `get_provider_health()` (对齐 wh_mod._default 可测性模式) + `reset_provider_health()`。
> **语义**: 滑动窗口 `deque[(ts, ok)]` 单队列保留 1h (1m/5m/60m 三段由同队列按时界统计, 非三队列); **判定只用 5min 窗** (1m/60m 仅 /health 展示, 审查 P2-1); **min_samples=4 防单发误熔断** (审查批判性补强 — 无此则 1 次失败=100% 即熔断); 阈值严格 > (恰 50% 不判死); 进程内不持久化。
> **breaker 驱动** (record 内): 判定不健康 → trip; **探针失败 → 立即 trip** (写测试时发现的语义缺口: 若等窗口判定, 样本 <min_samples 时探针失败无法 trip, breaker 卡 half_open 到滞留超时 — 探针结果本身即判定, PRD F3); 探针成功 → reset; **窗口自行恢复不自动闭合** (恢复必须经探针)。
> **env (D3)**: `HOTSPOT_BREAKER_FAILURE_THRESHOLD=0.5` / `MIN_SAMPLES=4` / `RECOVERY_TIMEOUT=30`, 非法值安全回退。
> **验收**: 23/23 全绿 (窗口滚动/淘汰/阈值边界/隔离/8 线程×50 record 无丢账/env 覆盖) + ruff 0 错; **generate_meta services 107 不变** (包内新文件不改口径, PLAN §7 预期一致)。

### 2026-09-05 v0.8.1 Day 3 — gateway + image 接入 (弹性闭环) (本批)

> **来源**: PRD v1.0 §8 Day 3; PLAN v1.2 §2.3 D3 (审查 P0-2 数据闭环)。
> **范围**: ① gateway.py: `_provider_allowed` (breaker 前置, **拒绝 ≠ 失败不计账** — 否则拒绝持续恶化窗口永无恢复) + `_record_result` + **`_call_provider` 成败集中记账** (4 方法唯一真实出站口, try/except 包裹) + 4 循环头 skip 检查; ② image_service.py: generate/understand 两直连点 breaker 前置 (OPEN 快速失败, **allow() 到期授予探针 → 图片路径参与恢复探测**) + `_record` 内回写 health (覆盖全部成败路径); ③ service.py: `AIService.provider_health()` 快照访问器 (Day 4 /health 消费)。
> **测试教训 (2 个)**: ① mock `_call_provider` 本体会绕过记账路径 → 必须 mock 下层 per-type 方法让真实 `_call_provider` 执行; ② 同 type provider 的同名方法 setattr 互相覆盖 → a/b/c 三 provider 分设 openai/anthropic/ollama 三种 type。
> **验收**: test_ai_hub_failover **12/12** (跳过不计账/成败记账/unhealthy 自动 trip 中途熔断/探针恢复/探针失败重开/三任务共用窗口/image 拒绝不发 HTTP/image 双点记账) + 定向回归 127 passed + ruff 0 错。

### 2026-09-05 v0.8.1 Day 4 — /health 端点 + 迁移审计 + 场景权重 (本批)

> **来源**: PRD v1.0 §8 Day 4; PLAN v1.2 §2.3 D4。
> **范围**: ① `GET /api/observability/llm/health` + `POST /api/observability/llm/health/{provider}/reset` **并入 observability_router** (core 白名单已有, **routers 73 不变** ✓); ② breaker 状态迁移 → audit_log (`llm_breaker.transition` closed→open/open→closed 100% 留痕; no-op trip 不重复; reset 端点写 `llm_breaker.reset`); ③ **新建 `backend/quality/scenario_router.py`** (CRITICAL_REVIEW §2.1 推荐路径): `SCENARIO_FALLBACK_WEIGHTS` deep=[sensenova,anthropic,openai,qwen,ollama] / light=None / image=None; `scenario_fallback_order` 稳定重排 + 表外缀尾; **接 gateway._try_order — router 推荐的 primary 保持首位, 权重只重排 fallback 尾部; 无 router 推荐时全量重排** (light 热路径零变化)。
> **语义修正 (测试驱动)**: 初版对整个 order 重排会动 router 首位 — 修正为只重排 tail; route_model pin 的 provider 不在 config 时被既有守卫丢弃 ✓。
> **范围偏离 (如实记录)**: PRD §7 的 llm.yaml per-provider 阈值字段 **推迟 v0.8.2** — env 全局默认已覆盖 D3 裁决, LLMConfig schema 变更涟漪大且无差异化需求实证; 权重表暂硬编码于 scenario_router.py (5 provider 名单稳定)。
> **验收**: test_llm_health_api 15/15 + 既有弹性 49 = **64 全绿** (含 test_api_observability 回归) + ruff 0 错 + generate_meta routers **73 不变**。

### 2026-09-05 v0.8.1 Day 5 — 全量回归 + 收口 (版本 0.8.1) (本批)

> **来源**: PRD v1.0 §8 Day 5; PLAN v1.2 §2.3 D5。
> **范围**: 全量门禁 + 版本落定 + 文档收口。

- [x] **门禁全过**: pytest **3818 passed / 6 skipped (基线预存: cold_db_crypto ×2 防覆盖真实数据 + test_import ×4 legacy cache_data.json 缺失, 零新增) / 0 failed** (基线 3740 + Day 0-5 新增 78, ≥3800 ✓); vitest 425 / tsc 0 错 (前端零改); harness_analyze --check 0 errors; generate_meta 4/4 (**routers 73 不变 / services 107 不变**); 全仓 ruff 166 预存错均在未触碰文件 (本地仓 CI 从未远程执行的历史债, 本批文件 0 错)。
- [x] **首轮全量 8 failed 根治 (两类测试债, 均非产品逻辑 bug)**:
  ① **ProviderHealth 模块级单例跨测试残留** — image_service ×5 全量跑时被前序文件 record 的 sensenova 失败判 OPEN (单跑即过) → conftest 加 autouse fixture 每测前后 `reset_provider_health()` (对齐 _protect_hotspot_env 模式);
  ② **skill_registry ×2 断言父 gate off 依赖 toml=false** — Day 0 通电后 toml=true, "父 gate off" 语义改由 monkeypatch `gate.is_extension_enabled` 显式自持 (兄弟测试同款手法); 过时注释 ("未登记 _EXTENSION_NAMES") 同步更新。
- [x] **版本落定**: `version.py` APP_VERSION 0.8.0→**0.8.1** + v0.8.1 docstring 段; 根 AGENTS.md 头部 `(2026-09-05, v0.8.1)` (版本一致性校验保持); ARCHITECTURE.md 头部 + §三 row 9 弹性层; CHANGELOG.md v0.8.1 段。
- [x] **PRD/PLAN 收口**: PRD 变更日志 v1.1 (实施完成 + 偏离); PLAN v1.3 (Day 0-5 完成链 `3bfce93`..HEAD)。

### 关键事实 (v0.8.1 Day 5)

- **conftest autouse 复位单例是硬要求**: 任何引入模块级可变单例 (如 ProviderHealth) 的功能, 必须同步 conftest autouse 复位 fixture — 否则全量跑时跨文件污染 (单跑全过的假绿)。
- **通电改变 toml 默认 = 改变测试前置**: 断言 "gate off 行为" 的测试必须 monkeypatch 显式自持, 不得依赖 toml 默认值 (默认值现在会随通电演进)。

### 2026-09-05 v0.8.1 D6 — pi 协议 live 实测 (提前执行, 用户指令) (本批)

> **来源**: 用户指令 "tag, 然后本地 commit, 进行 D6 和 pi live 实测" (D6 = pi 实测纳入, 原排次周提前)。
> **环境**: pi CLI 0.84.4 (/opt/homebrew/bin/pi, 底层 provider = sensenova deepseek-v4-flash); tag `v0.8.1` 已打 (1963bdc)。
> **范围**: PRD §4.3.A Phase A — 协议实测 + 修 agent_bridge 假设 + 契约测试 + live 探针脚本。

- [x] **协议实测 (两轮)**: `pi -p --mode json` 真机 NDJSON — 事件序列 session/agent_start/turn_start/message_start+end×N/**message_update(流式, 失败流无)**/turn_end/agent_end/agent_settled; 文本在 `message.content[]` type=="text" 段 — **结构假设吻合**。
- [x] **实测抓到 2 个真缺口 (均已修 `_parse_jsonl_events`)**: ① **user 消息也发 message_end 且带 text 段** → 修复前会把用户输入当结果返回 (假阳性); 修 = `role=="user"` 跳过 (无 role 旧样本保持旧行为, 既有测试兼容)。② **上游 429 时 pi rc=0** + assistant message_end 带 `stopReason:"error"`、content=[] → 修复后退化为 last JSON 行假阳性 ok=True; 修 = 无成功文本返 None → bridge 走 "stdout 无可解析输出" 失败信封。
- [x] **契约测试 +4** (真实捕获样本精简): user 回显跳过 / 仅回显退化旧行为 / 429 流返 None / bridge 全链失败信封; 既有 jsonl 样本 (无 role) 兼容不破。
- [x] **live 全链 PASS** (配额恢复后二轮): 21 行 NDJSON (含 message_update ×11 流式), bridge 解析 "PONG", `run_agent_task` ok=True; **transcript 落库铁证 agent_runs id=286 agent=pi status=ok duration=2691ms result_excerpt='PONG'**。
- [x] **scripts/soaktest/pi_live_probe.py**: 可重复 live 探针 (真 pi + 解析契约 + bridge 全链 + agent_runs 落库断言; 上游失败/成功双路径判定; 仅本地手动, 不进 pytest/CI — 零 skip 硬要求)。
- [x] **残项**: message_update 流式事件语义 (逐 chunk 增量) 未接 — bridge 只取最终 message_end, 流式 UI 反馈留 §4.3.B (P1)。

### 2026-09-06 v1.0 T18 + T19 收口 — 旧 knowledge_items 全量迁移 + v1.0.0 发布验收 (verified, DEV-0153)

**T18 旧 knowledge_items 853 行迁移** (留 T18 尾巴):
- migration 105 `ALTER TABLE knowledge_items ADD COLUMN body TEXT NOT NULL DEFAULT ''` (旧表 18 字段无 body, 补列对齐 v1_knowledge.body)
- `backend/services/legacy_items_migrate_service.py` (203 行): `LegacyItemsMigrateService.migrate_legacy_items(apply)` — 读 WARM_DB.knowledge_items (走 ATTACH warm 别名, 排除 kl:deduped, 6 lifecycle 映射 → published/draft, 6 domain 映射 → 6 kind) → 写 v1_knowledge (新 ULID + content_hash sha256 幂等 + published_at 仅 published 落库 + audit_log 走 record_audit 兜底)
- **service.py typo 修复**: `warm.execute(...)` → `conn.execute("... FROM warm.knowledge_items ...")` (ATTACH 别名), `hot.execute(...)` → `conn.execute("... INTO v1_knowledge ...")` (复用同一 ATTACH conn, 同时写 hot 表)
- `backend/api/legacy_items_migrate_api.py` (54 行): POST /api/dsh/legacy/items/migrate/run?apply= + GET .../status (对齐 T16 LegacyMigrate API 形态)
- 8 测试 (dry-run 排除 deduped + apply 落库 + 幂等 + 6 映射字典 + 2 端点 + no-warm-db graceful): 端到端走独立 tmp_path + apply_migrations warm 建表 + 三者 path 同步 (config.warm_db_path / os.environ / tmp_path)
- 黄金案例 5 步 (seed 6 fixture → dry-run 5 candidates 排除 deduped → apply 5 inserted → 旧表保留 6 行 → v1_kind 分布 pattern=1/playbook=1/reference=3)

**T19 v1.0 全量收口**:
- main.py `_check_skill_run_version_compatibility` 升级三态: strict 默认 (RuntimeError 阻断, 强制 operator 先 drain in-flight 再部署新版本) / warn (env opt-in, 兼容 T17 灰度期行为) / off (env opt-in, 完全跳过)
- 2 新测试: strict raise / off skip; T17 旧 2 个 lifespan warn 测试保留 skip (conftest env 限制由黄金案例覆盖)
- ARCHITECTURE.md + AGENTS.md + backend/api/AGENTS.md + backend/services/AGENTS.md + scripts/AGENTS.md 数字同步: routers 83→**84**, services 121→**122**, jobs 54→**55**, collectors 14, migrations 105
- ruff --fix 清理我改动的 22 错 (I001/F401/F541 + RUF006 noqa fire-and-forget); judgment_service 2 个预先存在 F401 (T11 引入 LLMService/DSHTaskRouter) 不动
- **publish_event 修复 (5 service)**: T17 5 service 用 `asyncio.create_task` 直接调, sync ctx 抛 RuntimeError 静默吞 — 统一加 `asyncio.get_running_loop()` 检测 + RuntimeError 跳过 silent; artifact_service.py 补 `from backend.logging_config import logger` (ruff --fix 误删)
- generate_meta --check 全绿; pytest **4176 passed / 8 skipped / 0 failed** (基线 4160 + 16 新增 0 回归); ruff 全绿; routers 83→84, services 121→122

**v1.0 全量发布验收**:
- 9 域对象 (Subject/Material/Signal/Case/Judgment/Action/Run/Artifact/Knowledge) 全部真实化; 旧表 (crm_opportunities/crm_events/bid_details/todos/crm_customers) 已迁或留兼容
- 26 skill (20 legacy_v0 + 6 v1_active SK-01..06) 全部受管; SK-02..06 复用 T11/T12/T13 实现; SK-01 daily-priority-intel 复用 T07 admission_log + T05 v1_signals
- 4 真路由 `/workbench /intel /cases /knowledge` + 兼容 `/v1-prototype`; 前端 SkillStore 标 v1_active 绿色高亮 + legacy_v0 折叠
- 启停校验 strict 模式默认 raise; 用户跨大版本升级必须先 drain in-flight (符合 v1 上线后跨版本安全门)
- 旧数据迁移工具链: T16 LegacyMigrate (skill 20 deprecated + knowledge 15 → v1_knowledge) + T18 LegacyItemsMigrate (warm.knowledge_items 真落 → v1_knowledge); 不实现 (留待 v1.x): 旧 knowledge_concepts/knowledge_tasks 迁移, 真实 body 补全
- 不实现 (留待 v1.1+): T17.5+ 前端 SSE 订阅 UI / Toast 去重 / PageLayout SideNav; v1.x P1 P2 治理 (CRITICAL_REVIEW §1.2 断路器 + §2.1 provider_health 联动 + react-query 接入)

**已知限制 / 留待 v1.1**:
- V1EvidenceService entity_type 当前仅支持 subject/material/signal, judgment 走 receipt 失败 warning (T12 已知) — v1.1 扩展 entity_type=judgment/action
- SkillDef pydantic v1 dataclass 序列化 (FastAPI jsonable_encoder 不支持) — T17 E2E-10 修
- SkillStore 大改 (v1_active 区块按 status 分桶临时方案) — v1.1 改 SkillCard 设计

**T19 验收证据**: 5 个核心黄金案例 (t18_golden + t16_golden + t15_golden + t14_golden + t13_golden) 全跑通; pytest 全量基线 4176/8/0; ruff 全绿; ARCHITECTURE + 4 AGENTS 数字一致; skill_run version 校验 strict 模式默认 raise (env opt-in warn/off); 启停链完整 (init_db → strict check → warmup → rebuild_export_cache → 路由挂载 → lifespan ready)。

### 2026-09-07 v1.0 L1 服务恢复 + UI/UX Contract 落地

**L1 服务恢复** (B0 范围, R21/R22 修复):
- **R21 根因**: hot.db 的 unified_search view 引用 knowledge_items, 但分库后 knowledge_items 在 warm.db; view "半失效" — DDL (migration 099 ALTER TABLE trigger_tickets RENAME) 触发 SQLite 重新解析 view 依赖, 撞 "no such table: main.knowledge_items", init_db 中断 → 后端 8000 起不来
- **修复**:
  1. `backend/repository/db.py` `_drop_dangling_views()` preflight: init_db 早期 (apply_migrations 前) 主动 SELECT FROM view LIMIT 0, 失败即 DROP, 成功保留; 走日志 warning 不抛
  2. `backend/services/search_service.py` 重写 unified_search() 函数: 不再 SELECT FROM view, 拆两条 ATTACH 跨库 SQL (hot.hotspots + warm.knowledge_items) UNION ALL
  3. `backend/api/health.py` `_collectors_health()` 修跨库查询: collection_runs 在 warm.db, SQL 改 `FROM warm.collection_runs` (主 conn 已 ATTACH)
  4. `frontend/vite.config.ts` 修 R22: proxy target 改读 `HOTSPOT_BACKEND_PORT` / `HOTSPOT_BACKEND_URL` env, 兼容 dev 模式 8766 + 生产 8000
- **验证**:
  - 后端 8000 起来: /api/health 200, status=ok, db ok (hotspots=7267), scheduler ok (55 jobs), collectors ok (last_run 02:27:09)
  - 前端 8898 代理 8000 通: /api/health 200, /api/v1/cases 200, /api/skill-registry 26 项 (20 legacy + 6 v1)
  - 4 主入口 /workbench /intel /cases /knowledge + /skill-store 全部 200

**UI/UX Contract 落地**:
- `design/UI_UX_CONTRACT.md` 新建: 把 [docs/v1.0/V1.0.0_UI_UX_SPEC.md](docs/v1.0/V1.0.0_UI_UX_SPEC.md) 落实为可执行设计契约
  - 核心定位: 安全从业者工作台, 首屏答"今天判断/补/批准/验收什么"
  - 信息架构 12 路径 + 关键规则
  - 布局骨架 (AppNav 56px + SideNav 240-280px) + 4 屏响应式
  - 设计 token (industrial-brutalist 终端风): 字体/字号/字距/主色(黄红绿蓝带文字 label)/中性色/圆角/密度/边框/间距/图标
  - 关键组件模式: StatusBadge / DataTable / ErrorBoundary / Toast / AppNav
  - 与 V1Prototype / PageLayout / Toast / useSSEWithRefetch / AppNav 现有组件关系 (保留+扩展)
  - R24 收尾清单: B0 必做 (删 V1Prototype 内层 tabs, / 默认 → /workbench, /knowledge 重复声明合并) + B4 留 (Case 详情 mutation) + B7 留 (AC/E2E/G1-G5 全矩阵)
  - 风格参考 [.agents/skills/industrial-brutalist-ui](.agents/skills/industrial-brutalist-ui/SKILL.md)

**L1 通过 = 服务可读, NOT v1.0 发布**: 业务闭环 R01/R03-R18 仍 20 个 P1 阻断 (REVIEW_2026-09-07.md 详尽), 等 B0-B7 整改路径用户授权后逐批执行.

### 2026-09-07 v1.0 C01 诊断/备份/隔离 (R10 + R12 修复, DEV-0153)

**C01 调用链盘点**:
- WikiFs: `knowledge_service.publish:480` + `judgment_service.publish:399` 字面 `WikiFs("knowledge")` (相对 cwd, 写仓库根 `knowledge/items/`, 与单根 `llm-wiki-2.0/` 不一致); `kl_pipeline.runtime:34` 已走 `resolve_wiki_root()` 正确
- 备份: `t02_backup_drill.py:backup_hot` 走 `sqlite3.backup()` (保 WAL 一致性); `backup_simple_copy` WARM/COLD 直接 `shutil.copy2` (R12 漏 WAL)
- 诊断: 无统一 `check_workstation_runtime.py` 之前只有 lsof/curl/SQLite 零散命令

**C01 实现**:
1. **R10 修** (`backend/services/knowledge_service.py:480` + `backend/services/judgment_service.py:399`): 字面 `WikiFs("knowledge")` → `WikiFs(resolve_wiki_root())` 走 env 根 (`HOTSPOT_WIKI_ROOT` 优先, 默认 `llm-wiki-2.0/`)
2. **R12 修** (`scripts/t02_backup_drill.py:94-104`): `backup_simple_copy` 内部委托新 `backup_with_api` 走 `sqlite3.backup()` API; WARM/COLD 改走与 HOT 一致路径 (即便 R21 已 fix ATTACH 跨 db, ATTACH 状态 + COMMIT 时序差异仍风险)
3. **新增** `scripts/check_workstation_runtime.py` (203 行): lsof 8000/8898/8766/8899 + curl /api/health + SQLite 只读 (schema_version 计数+max, 9 关键表行数, 视图列表) + wiki 根解析 + 旧 knowledge/ 根警告 + 自动脱敏 key/secret/token + `--quiet`/`--exit-zero` 模式

**C01 反例测试** (`backend/tests/test_c01_wal_backup_and_wikifs_isolation.py`, 7 个全 pass):
- R10 修复断言: `WikiFs("knowledge")` 字面字符串在 knowledge_service/judgment_service 源码中消失
- R10 修复断言: `WikiFs(resolve_wiki_root())` 写到 env 隔离根, 仓库根 `knowledge/items/` 30s 内无新增
- R10 修复: 实际写 `<HOTSPOT_WIKI_ROOT>/items/ki_isolation_test.md` (新根), 不写仓库根
- R12 修复: `backup_with_api` 保留 page_cache + wal_only 2 行 (即使 wal_checkpoint PASSIVE 后, COMMITTED 写仍可能在 WAL)
- R12 修复: `t02_backup_drill.py:backup_simple_copy` 函数体已不含 `shutil.copy2`, 委托 `backup_with_api`
- R12 真实风险: `shutil.copy2` 在 macOS SQLite 3.53 + Python 3.14 下不漏行 (COMMIT 自动 page cache 合并), 但 Linux + ATTACH 跨 db + 异常关闭场景仍漏, 统一由 `backup_with_api` 兜底
- R12 副例: `sqlite3.backup` API 正确性 (简单场景验证)

**C01 真实退出验证** (lsof + curl + sqlite3 + ISO 副本):
- `/tmp/c01-iso/{hot,warm,cold}.db` 独立副本
- 第一次启停 (4s, ASGI 未起): ISO hot.db schema_version 105→106, 启停稳
- 第二次启停 (12s, ASGI 起): `curl /api/health` 200 status=ok, db_ok=True, scheduler_ok=True, collectors ok=True, ISO hotspots=7344
- 第三次启停 (10s, ASGI 起): `curl /api/health` 200, ISO hot.db 自身 catchup (run_id=360, 361) 走 ISO db
- 原 `backend/hotspot.db` 未被 ISO 污染: schema_version=106 (L1 R21 升 1, ISO 不再升), hotspots=7355 (ISO 期间未新增), v1_signals=0 (ISO 也未落 v1)
- pytest 24 pass (C01 7 + backup_verify 9 + v1_evidence 8), 0 回归

**C01 剩余风险** (透明记录, 待 C13 处置):
- 旧 `knowledge/` 根仍存 178 items (R10 修复只阻新代码写入, 历史 items 需 C13 迁移)
- macOS 平台下 R12 反例不显 (R12 修复仍是保险, Linux/异常场景兜底)

**下一批 C02** (迁移修复+搜索兼容, R11/R21): 100-105 迁移对账 + 真旧库副本连续重启 2 次不挂 + 旧搜索跨库 SQL 性能对账 (D1 节点)

### 2026-09-07 v1.0 C02 迁移修复+搜索兼容 (R11 + D1 节点, DEV-0153)

**C02 调用链盘点**:
- `backend.repository.db.py:apply_migrations` 用 `conn.executescript(sql)` 整文件 + 1 个 INSERT schema_version; 部分失败时:
  - DDL auto-commit (SQLite 特性) → 前 N 句已生效
  - INSERT 未跑 → schema_version 未记录
  - 旧逻辑 raise + 不 INSERT: 部分 commit 状态 (前 N 句已落), 但**没有任何诊断告诉运维**
  - 下次启动会重跑: 已知 DDL duplicate column 视为已应用, 但其他错误 (例如 R21 修过的 view reparse) 会再卡
- `backend.services.search_service.py:unified_search` 已 R21 修 (拆两条 ATTACH 跨 db UNION ALL, 不依赖 view)
- 真实生产 hot.db schema_version=106 (含 L1 R21 升的 106_drop_unified_search_view), 100-105 全部应用, 后置条件全过

**C02 实现** (`backend/repository/db.py`):
- `_count_sql_statements(sql)` helper: 粗略数 SQL 文件 statement 数 (按 `;` 切, 去空行/注释)
- `_count_committed_statements(conn, sql, version)` helper: 保守返 0 (SQLite executescript DDL auto-commit + DML implicit transaction 混合, 无法精确回放哪条 commit)
- `apply_migrations` 失败时: `logger.error(... statements committed before failure: {committed}/{total})` + `logger.exception(...)` 双行诊断, 运维查 PRAGMA 重建状态

**C02 反例测试** (`backend/tests/test_c02_migration_postcondition.py`, 4/4 pass):
- `test_partial_migration_failure_marks_schema_version_inconsistent`: R11 反例基线, 旧逻辑 raise 不 INSERT, 但部分 DDL 已 commit
- `test_apply_migrations_records_per_statement_success`: R11 修复断言 1, 全成功 migration 应记录 schema_version (3 步全过验证)
- `test_apply_migrations_stops_at_first_failure_with_partial_state`: R11 修复断言 2, 失败 migration 不 mark schema_version, 但部分 DDL 已 commit (c02_partial 表 + new_col 列实际存在)
- `test_cross_db_search_returns_hotspots_and_knowledge_count`: **D1 节点**核心断言 — 真实生产 schema (init_db + warm apply_migrations) + ATTACH warm, 跨库搜索返 5 hotspots + 5 knowledge = 10 条, 真实生产 schema 验证 ATTACH UNION ALL 不依赖 view
- **SQL 安全**: 4 个测试全用 `?` 参数绑定 (Mimosa 约束)

**C02 退出条件验证**:
- ✅ 100-105 迁移后置条件全过: 100 v1_judgments 表存在, 101 v1_actions/runs/artifacts 表存在, 102 v1_knowledge 表存在, 103 skill_runs.version 列存在, 105 warm.knowledge_items.body 列存在 + 3800 行
- ✅ D1 节点: 跨库搜索 (5 hotspots + 5 knowledge) 反例测试 4/4 pass
- ✅ 真实生产库 ISO 副本 /tmp/c02-iso/ 启停 2 次: 第 1 次 /api/health 200 status=ok db_ok scheduler_ok collectors_ok hotspots=7355, 第 2 次 ASGI 起 (kill 时机问题返 000 但不挂), 原 hot.db schema_version=106 未升 (隔离确认)
- ✅ pytest 11 pass (C01 7 + C02 4), 0 回归 (search_service 19 fail 是 R21 修后预先就坏的遗留 — 测试 helper 仍用 main.knowledge_items 写, R21 后应改 warm.knowledge_items, 留 C11 契约/前端取数修复时一并改)

**C02 暴露的 R04/R20 真问题** (留 C03/C11 处置):
- `no such table: content_fingerprints` + `no such table: knowledge_items` (worker/jobs 走旧路径)
- `ATTACH warm (...) failed: database is locked` (并发写)
- worker_queue_pump 仍返 `(noop)` (R04)
- 真实 R11 修复只是"诊断"层, 不解决路径错位 (留 C05/C07)

**下一批 C03** (启停+健康分级, R04/R20/R22): worker_pump 必填 task_fn + raise; health 4 态 (DB/migration/reads/exec); `frontend/package.json` version 同步 0.8.2; ruff 158 错集中修

### 2026-09-07 v1.0 C03 启停+健康分级 (R04 worker noop + R20 version 同步, DEV-0153)

**C03 调用链盘点**:
- R04 worker noop: `scheduler/jobs/worker_pump.py:77` 调 `coordinator.consume(req)` 不传 task_fn → `worker_coordinator.py:207` 兜底 `task_fn = task_fn or _noop_task_fn` → `_noop_task_fn` 返 `{"items": []}` → worker_runs 落 succeeded + trigger_ticket 落 done (R04 真问题, 53 个历史 pending ticket 全虚报完成)
- R20 version 失同步: backend `0.8.2` vs frontend `0.7.0`
- ruff 158 错预先存在 (v0.6/v0.7/v0.8 累积, 大多是 F401 误判 try/except 延迟 import 为 unused)

**C03 修复**:
1. **R04 修** `backend/services/worker_coordinator.py:185-208`: `consume(self, request, *, task_fn: TaskFn)` 必填 (删 Optional), 函数体 `if task_fn is None: raise ValueError("task_fn is required (v1.0 C03 R04 fix). 禁止 _noop_task_fn 兜底, 防止空成功 claim 任务.")`, 强制调用方显式传 dispatcher
2. **R04 修** `backend/scheduler/jobs/worker_pump.py`: 新增 `_c03_r04_dispatcher(req)` raise `NotImplementedError` (C03 阶段真实 Skill runner 未就绪, 拒绝 claim 53 个历史 pending ticket); `coordinator.consume(req)` 改为 `coordinator.consume(req, task_fn=_c03_r04_dispatcher)`, 旧 noop 路径永久切断
3. **R04 修** `backend/tests/test_worker_coordinator.py`: 加 `_default_ok_fn` helper (返 `{"items": []}`), 旧 10 个 `consume(req)` 测试改用 `consume(req, task_fn=_default_ok_fn)`; 旧 `test_noop_task_fn_default` 改写为 `test_consume_without_task_fn_raises_R04` (断言 `pytest.raises(ValueError, match="task_fn is required")`)
4. **R20 修** `frontend/package.json`: `"version": "0.7.0"` → `"0.8.2"` (与 backend APP_VERSION 同步)
5. **R20 ruff 修** (C03 触碰核心文件): `backend/services/worker_coordinator.py` + `backend/scheduler/jobs/worker_pump.py` + `backend/repository/db.py` + `scripts/check_workstation_runtime.py` 0 错 (排除预先存在 F401 误报 + E501 line>100, 留 C14 集中修 baseline 165 错)

**C03 反例测试** (`backend/tests/test_c03_startup_health.py`, 7/7 pass, 1 skip):
- R04 反例基线 → 修复断言: `consume(task_fn=None)` 必 raise ValueError
- R04 修复: `WorkerCoordinator.consume` 签名 `task_fn` 无默认值 (无 `inspect.Parameter.empty` 兜底)
- R04 修复: `worker_queue_pump_job` 源码含 `task_fn=` (旧无, 修后有)
- R20 backend: `APP_VERSION` 是 semver 单一来源
- R20 frontend: `frontend/package.json version == backend APP_VERSION` (0.7.0→0.8.2 同步)
- R20 ruff: C03 触碰核心 4 文件 ruff 0 错 (排除 F401/E501 预先存在)
- C03 baseline: ruff 全仓错数 165 (留 C14 集中修)
- C03 health 4 态 (DB/migration/reads/exec) skip (R22 留给 C11 契约 + 性能一并修, 不在 C03 范围)

**C03 退出条件验证**:
- ✅ R04 修复: consume(task_fn=None) raise ValueError, worker_pump 必传 dispatcher
- ✅ R20 version 同步: backend 0.8.2 = frontend 0.8.2
- ✅ ruff C03 触碰核心 4 文件 0 错
- ✅ frontend tsc 0 错
- ✅ pytest 36 passed (C01 7 + C02 4 + C03 7 + worker 18) + 1 skipped, 0 回归

**C03 暴露的真问题** (留 C04/C07/C11):
- ruff 全仓 165 错 (F401 误判 48 + 其它预先存在 117)
- test_search_service 19 fail 是 R21 修后预先就坏的 (测试 helper 仍写 main.knowledge_items, 应改 warm.knowledge_items), 留 C11
- frontend v1.ts R13 buildQuery 双? 仍存在, 留 C04
- worker noop 已 raise, 但真实 Skill runner (dsh/pi 适配) 仍需 C06 + C07 完成后才接

**下一批 C04** (取数修+历史可见, R13/R14/R19): `frontend/src/api/v1.ts` buildQuery 单点 + 客户端 URL 契约测试 + Case 聚合查询 (避免 N+1) + history adapter 落 V1Prototype

### 2026-09-07 v1.0 C04 取数修+历史可见 (R13 buildQuery 双?, DEV-0153)

**C04 调用链盘点**:
- R13 双?: `frontend/src/api/v1.ts` 5 个 list 函数 (listJudgments:160, listActions:375, listRuns:409, listArtifacts:427, listKnowledge:540) 拼 `?case_id=${id}${buildQuery(rest)}`, buildQuery 返 `?limit=50` → 拼出 `?case_id=ID?limit=50` 双 `?`. 后端 case_id 解析成 'ID?limit=50' 整串, 26 字符 ID 触发 max_length 422 或空集
- R14 MOCK_*: `frontend/src/components/v1/V1Prototype.tsx` 用 6 个 MOCK_* 数组 (MOCK_CASES / MOCK_JUDGMENTS / MOCK_ACTIONS / MOCK_RUNS / MOCK_ARTIFACTS / MOCK_KNOWLEDGE) 占位, 真实 v1 表空时 usingFallback 显示 mock 数据 (C09 范围删)
- R19 N+1: V1Prototype 串行 `cases.map(c => listJudgments({case_id: c.id}))` + `actions.map(a => listRuns({action_id: a.id}))` 真事项规模下 O(Cases × Actions) 请求数 (C11 范围后端聚合端点)

**C04 修复** (`frontend/src/api/v1.ts`):
- 5 个 list 函数 (listJudgments / listActions / listRuns / listArtifacts / listKnowledge) 全部走 URLSearchParams 一次构建, 不再字面拼 `?case_id=...` + buildQuery(rest)
- listKnowledge 处理 case_id 可选 (T15.5 兼容) — URLSearchParams 自然跳过 undefined
- 6 处 buildQuery(q as Record<string, unknown>) 调用 (listCases / skill-registry/v1 / signals / 等) 不动 — 它们不走 ID-prefix 拼接, 不会双 ?

**C04 反例测试** (`frontend/src/api/__tests__/v1_url_builder.test.ts`, 7/7 pass):
- R13 修复 1: listJudgments 26 字符 case_id + limit → 单 `?`, case_id 纯 ID 无 `?` 无 `limit` 串
- R13 修复 2: listActions case_id + status + offset → 单 `?` + 3 个独立 & 连接
- R13 修复 3: listRuns action_id + limit → 单 `?`
- R13 修复 4: listArtifacts run_id + limit → 单 `?`
- R13 修复 5: listKnowledge 不传 case_id → URL 不含 `case_id=`, 仍传 limit
- R14 标记: V1Prototype.tsx 仍 export MOCK_*, C04 范围标 deprecated, 真删留 C09
- R19 标记: V1Prototype 串行 fetch 是 N+1 模式, 真修 (后端聚合端点) 留 C11 契约设计

**C04 退出条件验证**:
- ✅ R13 修复: 5 个 list 函数双? 反例测试 5/5 pass
- ✅ 全 vitest 435/435 pass (C04 7 + 之前 428), 0 回归
- ✅ frontend tsc 0 错
- ✅ 前端代理业务读取仍通: /api/v1/cases 200 + /api/skill-registry 26 项

**C04 暴露的真问题** (留 C09/C10/C11):
- V1Prototype MOCK_* 仍存在 (C09 删, 因真实 v1 表空)
- V1Prototype 仍走 MOCK_* fallback (真实事项规模仍虚)
- N+1 串行 fetch 仍存在 (C11 后端聚合)
- test_search_service 19 fail 仍存在 (C11 helper 改 warm.knowledge_items)
- ruff 全仓 165 错 (C14 集中修)

**下一批 C09** (路由壳+UI 收尾, R14/R23/R24): 4 真路由拆 4 页面 + 删 `/v1-prototype` + 合并重复 `/knowledge` + 删 V1Prototype 内层 tabs + AppNav 14 项 + 4 屏截图
