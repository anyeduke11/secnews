# PROGRESS.md — 执行进度台账（仅活跃段）

> **当前阶段 (2026-09-10)**: v0.8.5 已合入 main 打本地 tag；审查修复批 F1-F11 + 全仓整洁批（`fix/v085-review-p0`）、**信源节奏/存活修正批**与**代理内置批（DEV-0163/0164）**完成待评审合入（分支 `fix/source-cadence-health`）。生产后端已按新代码重启（30 分钟节奏 / 招标 6 小时 / 31 源退役 / 存活与有用分离 / 代理默认内置开启 + 失效自动切直连）。开放项: 15 个观察源 per-source 排查 / B1 信号观察窗调优 / 生产 warm 库 853 行迁移（待授权+备份前置）/ B0-B7 业务闭环整改。
> 接手顺序: 根 `AGENTS.md` → `PROJECT.md` → 本文件活跃段。历史完整段见 `docs/progress-archive/`，docs/ 全景见 `docs/README.md`。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [v0.5-baseline.md](docs/progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [v0.5-execution.md](docs/progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 |
| **v0.6 records** | 2026-08-24/26 | [v0.6-records.md](docs/progress-archive/v0.6-records.md) (856 行) | 里程碑验收 + Phase 7 数据迁移 + P0-P3 治理全记录 |
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [v0.7-records.md](docs/progress-archive/v0.7-records.md) | SettingsHub V2 + 观测批次 ①-⑨ + v0.6.3 性能/双根合并 |
| **v1.0 轨道** | 2026-09-03 ~ 09-08 | [v1.0-track-records.md](docs/progress-archive/v1.0-track-records.md) (1320 行) | T00-T19 / C01-C14 / v1.0.1 融合方案（路线已被 v0.8.5 反向收敛取代）+ REVIEW 20 项阻断 B0-B7 整改路径 |

> 原 v0.5 时代的「规格与文档 / 5 文件用法」小节随 v0.5 spec 一并归档（`docs/archived/2026-09-09-sweep/v0.5_refactor_plan/`），不再维护。

## 当前活跃段 (2026-09-03 起)

### 2026-10-03 v0.8.6 P1-1 切片3 审批收件箱前端 + Case 页 AI 起草接线（用例 A UI 闭环）— DEV-0265

- **范围**: 纯前端, 闭合切片2 遗留两条: ① `/action` 审批收件箱区块; ② Case 页"AI 起草研判"按钮接线。零后端变更、零新路由 (NAV4 硬规则: 新能力只能以四菜单区块进入)。
- **新建**: `frontend/src/api/proposals.ts`（Proposal/ProposalStatus 类型与 proposal_repo 行字典对齐; listProposals/draftJudgment/approveProposal/rejectProposal 四薄包装, 走 lib/api getJSON/postJSON）；`frontend/src/components/action/ApprovalInbox.tsx` + colocated 测试（`components/action/` 为新合法子目录, PascalCase 约定）。
- **ApprovalInbox**: 以页内 `<section style={PANEL_SHELL}>` 挂 `SentinelActionPage`（ExecOverviewPanel 之前, import+1 行渲染）; 并行拉 draft/failed 两队列, loading/unavailable/空态三态对齐 ExecOverviewPanel 不伪造数据。draft 卡 = 类型/发起方/证据数/case_id/prompt 版本/正文预览(claim 优先, 否则 JSON) + judgment_draft·knowledge_draft「写操作」橙标（title 明示批准会真实落盘）; 批准两步内联确认（防误触, 二次确认前不发 API）; 修订=受控 details 展开 JSON textarea（受控 open 不依赖 jsdom toggle 事件; 非法 JSON 客户端拦截, 合法对象才随批准提交, 不展开=原样批准）; 驳回原因必填+字数计数, >200 确认按钮禁用。failed 卡显示 error_msg, 「重试起草」=对原 case_id 重新调 draft-judgment（生成新提案, 成功进 draft/仍失败提示; 无 case 锚点按钮禁用）。批准/驳回/重试成功后重拉两队列; 单卡 busy/错误隔离。
- **CaseDetail.tsx**: 判断区按钮文案改「AI 起草研判」, handler 改调 draftJudgment (移除旧 generateJudgment import; 无证据前置警告保留; CVE 必填前置删除——后端只要求绑定证据); 返回 status=failed 走 error toast 并指引到 /action 收件箱, draft 成功 toast 指引收件箱。**Rule 7 裁决**: 旧 `POST /api/v1/judgments/generate`（dsh 直落 draft 绕过审批）前端按钮退役, api/v1.ts 包装与后端端点保留运行, 收编另开工单（Rule 3 不超范围）。
- **测试**: ApprovalInbox.test.tsx 6 用例（字段+橙标、批准二次确认且成功重拉、修订非法 JSON 拦截/合法带 payload、驳回必填≤200、failed 有/无 case 锚点重试、拉取失败 unavailable）; SentinelActionPage.test.tsx fetch mock 补 `/api/proposals` 空队列分支（新区块挂载导致 19 处渲染崩溃的修复; 本页测试不涉收件箱交互）。
- **验证**: `npx tsc --noEmit` 0 错; `npx vitest run` **663/663**（94 文件, 新增 6）; `npx vite build --logLevel error` 0 错。无需 generate_meta（纯前端无 service/router 增减, 数字仍 93/155）; 无需生产重启（后端零变更）。
- **遗留**: failed Run 重试端点（approved proposal + run failed 场景, 凭 run_id 定位）; 旧 /api/v1/judgments/generate 端点收编; 用例 A 验收③ v1_runs 月增 ≥10 待全链路运营观察; P1-1 三切片代码全部交付, 改动未 git commit。

### 2026-10-03 v0.8.6 P1-1 切片2 AI 起草研判接线 + 研判产物 sha256 登记（用例 A 后端闭环）— DEV-0264

- **范围**: 切片1 账本基座之上, 闭合用例 A 主流程 + 两条异常流的后端部分。**新建** `backend/services/judgment_drafter.py`（HEAVY 起草单一职责）；**修改** `run_ledger_service.py`（draft_judgment + 批准产物化）、`run_ledger_api.py`（POST /api/proposals/draft-judgment）；无新迁移、无新 router 文件（端点挂既有 CORE router）。
- **起草链路**: `draft_judgment(case_id, drafter=可注入)` → 取 `V1EvidenceRepository.case_evidence_materials`（空证据 400, 禁止无证据研判）→ `ai_draft_judgment` 经 `asyncio.run(ai_service.generate_text(task="report"))` 命中 HEAVY 档（model_router TASK_TIER_MAP: report→HEAVY→t3_summary=sensenova deepseek-v4-pro, 零 yaml 改动）→ JSON 容错解析（容忍 ```json fence/前后缀）+ claim 必填 + confidence 枚举 + unknowns 规整, 不合法即 JudgmentDraftError；成功落 draft proposal（evidence_ids=material id 列表 + prompt 版本 `judgment-draft@v1`）；超时/拒绝/空响应/不可解析落 **failed proposal**（payload 空, HTTP 200 + status=failed 供收件箱重试）。
- **批准产物化**: judgment_draft 批准不再即时 done — Run 先 `running/outcome=NULL`, md 渲染（研判正文 + 证据 Source url + sha256 短码 + proposal/prompt 溯源）落盘 `data/run_artifacts/<run_id>.md`, 经 ArtifactService.create（R08 读盘 sha256 比对）登记后 Run 置 `succeeded/done` 并回挂 artifact_ids；**落盘/哈希失败 → status=failed + outcome=failed + error/reason 留痕, 原异常上抛**, proposal 保持 approved（人的采纳成立, 失败的是执行）。人修订批准时产物即修订版（测试断言 AI 原稿不在盘）。其余 kind 保持切片1"采纳即 done"。
- **回溯链（验收①后端侧）**: artifact→v1_runs(run_id)→v1_proposals(case_id)→v1_case_materials→v1_materials.url, 且 md 正文内嵌该 url; 测试以一条 JOIN SQL + 落盘重算 sha256 机械化断言。UI 全链路回溯待切片3。
- **测试**: `test_run_ledger.py` §8 新增 8 用例（起草成功绑证据/prompt、drafter 异常→failed 无污染、无证据 400、批准产物+JOIN 回溯+sha256、人修订达产物、注入 ArtifactService 失败→Run failed 原异常上抛、HTTP 400、HTTP 端到端桩）；新建 `test_judgment_drafter.py` 8 用例（围栏 JSON/非对象/垃圾文本/缺 claim/confidence 非法/unknowns 规整/渲染含 url 与溯源）。切片1 两条 judgment_draft 审批测试改用 kind=report（意图=测账本 policy, 非产物化）。
- **验证**: 37/37 新集; 受影响面 **103 passed**（artifact/c05/c08/judgment api+service/ops_runs/ledger/drafter）；ruff 触碰 5 文件 0 错；`generate_meta --fix` 同步 **93 routers / 155 services**（judgment_drafter 新 service；router 数不变）。
- **裁决/边界（Rule 7/12）**: ① PRD 写"evidence_receipts 引用", 实现落为 case 绑定的 v1_materials id（receipt 表语义是提交流水, 非研判引用; material.url 才是 Source 原文回溯锚点）→ 已回写 PRD 用例 A 实现裁决；② "产物失败+告警事件"的 outbox 告警暂以 logger.error 承接, 显式事件留 G1 告警面板批次（未冒充完成）；③ failed Run 的重试端点未做（proposal approved + run failed 已可凭 run_id 定位, 重试动作待切片3 后单开）；④ 旧 `POST /api/v1/judgments/generate`（dsh 直落 draft, 绕过审批）未在本批收编, 保留运行, 收编另开工单（避免超范围）。
- **遗留**: 切片3 `frontend/src/components/action/ApprovalInbox.tsx` 挂 /action（待审/失败两态 + 修订 + 驳回≤200 + 重试）；Case 页"AI 起草研判"按钮接线 `/api/proposals/draft-judgment`；failed Run 重试端点；旧 judgment generate 收编。

### 2026-10-02 v0.8.6 P1-1 切片1 Run 账本后端基座（M1 提案审批循环）— DEV-0263

> **编号更正 (2026-10-02)**: P0-7~P0-12 初写时误标 DEV-0247~0252，与 DEV_LOG 既有条目撞号（0251=P0-1 / 0252=P0-2 等，权威最新号当时为 DEV-0256）。现按 DEV_LOG 顺序顺延：P0-7=**DEV-0257**、P0-8=**DEV-0258**、P0-9=**DEV-0259**、P0-10=**DEV-0260**、P0-11=**DEV-0261**、P0-12=**DEV-0262**、P1-1 切片1=**DEV-0263**、切片2=**DEV-0264**。下一个可用号 **DEV-0265**。

- **P0 收口说明**: PRD §10 P0 表只定义 P0-1~P0-12（标题"14 项"为计数笔误，draft3 修订注可证实际 12 行），**无 P0-13**。P0-1~P0-6 前序会话已完成（代码/生产实证：gateway E1 / warm 三索引 EXPLAIN SEARCH / mcp 鉴权 / 迁移幂等 / ops_runs+misfire / DEFAULT_SCORE 删除），P0-7~P0-12 = DEV-0257~0262（见上方编号更正）。本批转入 P1 第一项 P1-1（migration 131 + Run 账本服务 + 审批收件箱 M1），按规模切三刀：**切片1 后端账本基座（本批）** → 切片2 Case 页"AI 起草研判"接线 + evidence/prompt/artifact 哈希 → 切片3 `/action` 审批收件箱前端。用例 A 三验收：①Artifact→Source UI 回溯（切片2/3）②LLM 超时 proposal failed（本批后端可断言）③v1_runs 月增 ≥10（运营指标，全链路后观察）。
- **migration 131**（生产库副本预演 OK；v1_runs 生产现 0 行）：① v1_runs 扩 3 列 `plan_json`(NOT NULL DEFAULT '{}')/`policy_version`/`outcome`(可空，历史行不回填伪结论) + idx_outcome；② v1_proposals 新表（payload_json DDL CHECK ≤65536，沿用 101"枚举不上 CHECK 走 service"约定）；③ command_log 新表（P1-1 建表，P1-4 命令栏写入，本批无写者故不违反 R2 单写者门禁）。
- **代码**：`proposal_repo.py`（insert/get/list/update_decision）；`run_repo.py` 插入点加 plan/policy_version/outcome 可选列（既有 v1.0 调用方零改动）+ `update_outcome()`；`run_ledger_service.py`（create/list/get、record_failed_proposal、approve 双签 Run=done+冻结 APP_VERSION、reject reason 必填≤200、finish_run outcome 五态枚举）；`run_ledger_api.py`（POST /api/proposals、/failed、GET 列表/详情、approve/reject）；无条件 CORE 注册（_registry + core/routers 白名单）。
- **裁决记录（Rule 7）**：① PRD §8.1 status 四态（draft/approved/rejected/expired）漏列用例 A② 要求的 failed → 实现加 `failed`+`error_msg` 并**回写 PRD §8.1**（spec 漂移禁止纪律）；② PRD 表格写 outcome NOT NULL CHECK，但 131 是对存量 v1_runs ALTER ADD + 全库约定"枚举不上 CHECK"（101 注释明示）→ outcome 可空 + service 强制枚举，两冲突均取更晚/更贴近库约束的方案，在此留痕；③ ledger Run 的 action_id NOT NULL 无 v1_actions 归属 → 确定性锚点 `proposal:<id>`，幂等键同（一提案一 Run）。
- **测试** `test_run_ledger.py` **21 用例**：迁移 schema/历史行 null outcome/创建查询/枚举拒绝/service+DDL 64KB 双闸/审批 done Run+policy 冻结+双签/人修订覆盖原稿/二次审批冲突/reviewer 必填/驳回 reason 必填+200 上限/驳回不生 Run/failed 提案 payload 空无污染且可查/finish_run needs_human+枚举/HTTP 全链路 200/400/404。
- **验证**：21/21；受影响面回归 **736 passed**（run/artifact/proposal/registry/router/write_guard/migration/v1）；ruff 0；`generate_meta --fix` 已同步 **93 routers / 154 services**（ARCHITECTURE/AGENTS/CLAUDE 计数自动更新）。
- **遗留**：生产重启后 131 生效；切片2（AI 起草 + evidence_receipts + artifact sha256 登记与哈希失败 outcome=failed）、切片3（ApprovalInbox 前端）；pi 不可用→needs_human 的执行体接入在后续 action/command 通道，本批 finish_run 已备好终判入口。

### 2026-10-02 v0.8.6 P0-12 门禁错误策略统一 fail-closed（审计 E13）— DEV-0262

- **起因**: 审计 E13 — 同一个"门禁内部代码崩溃", 仅因异常捕获位置不同结论相反: gate.check() **上抛** → pipeline `_check_gate` 兜底 fail-closed (passed=False/`gate_crashed`/-15, P2-5 已修); gate.check() **内部 try/except 调 `_wrap_exception`** → 旧实现 passed=True/零扣分/无 flag = **免检放行 (fail-open)**。10 个 gate 用内部自捕模式 (schema/recency/content_quality/noise/ai_quality/category_match/title_summary/source_reputation/duplicate + 异步 url_content; author_verification/final_url 无 try 兜底, 异常直接上抛走 pipeline 路径), 即"任一自捕 gate 代码缺陷 → 该关静默全开"。PRD P0-12 验收 (R2): 构造 gate 异常用例, pipeline 与单 gate 断言结论一致 (均非 passed)。
- **修法 (单一真相源, 非两处对齐)**: ① `quality/base.py::_wrap_exception` 由 fail-open 改为与 pipeline 兜底**完全同形** (passed=False + `gate_crashed` + 扣 15 + reason `gate crashed: ...` + error_msg); ② `pipeline._check_gate` except 分支删除自建 GateResult, 改调 `gate._wrap_exception(item, e)` — 两条异常路径共用唯一构造点, 从结构上杜绝再次分叉 (日志 logger.error 保留在 pipeline 层); ③ 同步 base.py 模块约定与 `GateResult.error_msg` 字段文档 (旧文档写 "treated as skip", 已失效)。
- **边界**: `AIQualityGate._llm_detect` 的 LLM 超时由 `AIService.gate_detect` 在更下层吞成 None (service.py 既有 fail-open, 审计 G2 的 1,006 次/日静默项) — 不冒到 gate except, **本批不动** (属 AI 显式 outcome 域, P0-12 契约只锁门禁异常两条路径一致); 异步 `run_url_content_check` 消费方核查安全: gate_crashed 归类 `unreachable` + -15 + 写 log (旧行为内部解析崩溃反而记 verified 假通过, 新行为正确)。
- **测试**: 新建 `test_gate_error_policy.py` 5 用例 — ① RaisingGate(上抛)/SelfCatchingGate(自捕) 经 pipeline 兜底与单 gate 直调的 GateResult **字段级一致** (gate_name/passed/flags/deduction/reason/error_msg); ② PRD 验收直取: 两路径单 gate 结论均非 passed; ③ loose 聚合两崩溃 gate → 70 分 + gate_crashed 可见不抛; ④ strict 下 hard gate 崩溃两路径参数化均抛 QualityGateFailed 且 flags 含 gate_crashed。旧锁定 fail-open 的 2 测试改判 (test_quality_gates wrap_exception helper / test_recency_gate 异常用例)。
- **验证**: 新 5/5 过; 扩大回归 **951 passed / 1 skipped** (quality/gate/pipeline/collect/hook/dedup/dashboard/url_content); ruff 触碰 6 文件 0 错; `generate_meta --check` OK (58/14/92/153); 导入冒烟 + 单一构造点反射断言过。
- **爆炸半径实测**: 生产库 `quality_check_logs` 历史 error_msg 非空 **0 行**, 全天日志 `gate_crashed` **0 次** — 无现存 item 依赖免检路径, 语义翻转只影响"未来真发生 gate 缺陷时"的可见性。strict(生产 min_score=50) 下 hard gate 真崩溃将拒绝 (正确 fail-closed), soft 崩溃 -15 与其他扣分叠加才可能拒。
- **遗留**: 生产后端需重启生效; LLM 超时/拒绝的显式 outcome (G2 1,006 次/日静默, gate_detect 返回 None 路径) 不在本批, 待 AI outcome 相关任务。

### 2026-10-02 v0.8.6 P0-11 egress 凭据出站门禁全覆盖 + AST 防新增（审计 E2/F4-1）— DEV-0261

- **起因**: PRD §4.1 AI 层硬规则① "只有 gateway 能带凭据出站"; 审计 E2 — `check_credential_egress` (代码侧 LLM 主机白名单, base_url 可被同步包写入 llm.yaml, 不守卫则篡改 base_url 即可带走 Bearer key + 全部 prompt) 只在 gateway 2 处调用, "5 条带凭据路径中 3 条无门禁"; 验收 R2/R6 = **带凭据出站 5/5 过门禁 + 新增裸 httpx 带 key CI 红**。
- **取证全量枚举** (ai_hub 包 13 个 HTTP 出站点): 9 个携凭据 — 修前仅 3 守卫 (`gateway._call_provider_openai` chat 分支 / `gateway._call_openai` / `pool.probe_platform`), **6 个裸奔**: ① `image_service.generate` ② `image_service.understand` (Bearer 直拼, base_url 取 llm.yaml); ③ `service._call_sensenova_eval` ④ `service._call_sensenova_detect` (evaluate/gate_detect 每日数千次热路径, 同为配置驱动 base_url); ⑤ `gateway._call_provider_chat` anthropic 分支 ⑥ `gateway._call_anthropic` (x-api-key, URL 为代码常量 — 审计未点名, 但 G2 "100% 凭据出站" 要求且让 AST 门禁零豁免, 白名单本含 api.anthropic.com, 零行为变化)。ollama 4 站不附凭据天然豁免。域外凭据 (OAuth client_secret / GitHub PAT / secrets 页用户自输 base_url 连通性测试) 信任语义不同, 门禁作用域**刻意限定 ai_hub**。
- **修法 (外科式)**: 6 站点各在附凭据前插入 `check_credential_egress(base_url)` (配置驱动 URL 在拼 URL 前; 常量 URL 同样过)。审计处方的理想态是"删除 `_call_sensenova_*` 自建 httpx / image 改走 gateway"调用图收敛, 但验收契约是"过 check_credential_egress"且 pool 探测 (gateway 外携凭据点) 早有同款守卫先例 — 止血批不动 evaluate/gate_detect 热路径行为, 不做重写。
- **AST 门禁** `test_credential_egress_guard.py` 13 用例: ① 包级扫描 ai_hub 全部生产代码, **无豁免清单** — 按调用点是否真传凭据判定 (Authorization/x-api-key 头、Bearer 串、headers 凭据变量、api_key= kwarg), 守卫必须在**同语句块或外层块且行号在前**才算覆盖 (跨 if 分支/守卫后置均判违规); ② 防失明断言 8 个已知携凭据函数必须被扫到 (防"扫描器什么都看不见所以永远绿"); ③ 6 个扫描器元测试 (裸 Bearer/内联头/守卫正例/ollama 无凭据/守卫后置/异分支); ④ 运行时 5 个 — image generate+understand / sensenova eval+detect 篡改 base_url 到 evil.example.net 必须抛 `EgressNotAllowedError` 且 HTTP client 一个都不许构造, 另 1 个白名单正向锁定 (sensenova 请求照常携 Bearer 发出, 防误伤)。
- **验证**: 新 13/13 过; 关键字回归 363 passed (llm/ai_hub/image/gateway/sensenova/egress/semantic_filter/deep_read/provider_health/model_router) + 窄面 64 passed (egress/image/ai_quality_gate/failover/secrets); ruff 触碰 4 文件 0 错; `generate_meta --check` OK (58/14/92/153 无增删); 冒烟导入链 + 生产 llm.yaml 四携凭据主机 (sensenova/openai/qwen/anthropic) 均在白名单, **重启不断 AI 检测服**。
- **5/5 验收对照**: 审计快照 5 逻辑路径 (gateway openai-chat / gateway openai / image×2 / sensenova legacy) 现 100% 过门禁; 现态全量 9 站点亦 100% (含 pool 探测 + anthropic×2)。
- **遗留**: 生产后端需重启生效; `secrets_service.test_connection` (用户主动对自输 base_url 测连通, 自伤模型, 强套白名单会误伤自建端点) 与 OAuth/GitHub 出站是否另立域名白名单, 建议后续单独工单, 本批不扩张。

### 2026-10-02 v0.8.6 P0-10 日志降噪（例行成功→DEBUG）— DEV-0260

- **基线量化**: 完整一天日志 (app.2026-10-01, 61,107 行 / 52MB, loguru JSON 每行 ~850B) — INFO 53,610 行 (87.7%)。top 噪声: `auto_extract/alert_evaluator` 各 5,827 · kl_trigger_t1 空转 5,752 · `collect_start` 5,725 · api_request/response 1,991 · kl t2 空转 2,874 · scheduler tick 家族 (per-source running/done 变体) 数千。
- **机制**: `observability.log_event` 新增 `level` 参数 (默认 info, 白名单 debug/info/warning/error, 非法回落 info) — 事件式调用点无需换 API 即可降级。
- **27 处降级落地, 两类语义**: ① **无条件 DEBUG** (纯例行心跳/访问日志): collect_start/end, api_request/api_response (500 路径保持 info), cache_miss/invalidate, category_start/done, source_skipped, db connection opened, upsert_many ok, trend 三种, batch_score completed, collection started, planning actions generated, auto_extract/alert_evaluator (60s 例行), pick_score, url content check done, source coverage ok, scheduler tick running/done (done: failed 保持 info), scan/drift 例行零值; ② **空转条件化** (全零→DEBUG, 有产出/失败→INFO, 审计 R2 "失败不得静默"): kl_trigger t1-t4 (candidates/failed), source_scheduler_tick (failed), source_alerter (triggered), v1_signal_intake (materials/signals/denied), CVE sync 两处 (synced/updated/failed), concept_sync (synced/created), knowledge_classify (updated/errors), chunk_generation (created), security_enrichment (enriched), planning_check (total), cg scan/drift (created/matched)。**不动**: `no sources configured` / `ai gate-detect failed` / `all N sources failed` / `strict-mode reject` 等真实失败与配置信号 (P0-6 域)。
- **验证**: ① **基线重放** — 把新规则逐条应用到 10-01 全天日志: 49,703 行 INFO 将不落盘, **全日志行数降幅 81.3%** (61,107→~11,404), 叠加 P0-7 已消除的 fingerprint 513 行 WARNING = **82.1% ≥ 80% 验收**; ② 新增守卫: `test_log_noise_guard.py` 9 用例 (kl t1/t2/t3 × 空转→DEBUG/有候选→INFO/有失败→INFO 双向锁定, 防回潮也防矫枉) + `test_observability.py` 补 level 参数 2 用例; ③ 回归 185 passed (observability/catchup×2/cache/attention/hotspot_repo/api_observability/phase10_integration/kl_heartbeat/scheduler×3/source_scheduler_repo); ④ ruff 触碰 20 文件 0 错; generate_meta --check 过。
- **遗留**: 生产生效需重启后端; 24h 后按 PRD 口径复核日志实际增量 (预期 ~10MB/日 级)。`ai gate-detect failed` 1,219 次/日的治理属 P0-6/M2 (E13/超时策略), 不在降噪范围。

### 2026-10-02 v0.8.6 P0-9 正文抓取 SSRF 加固 + DB 路径/权限位修复（审计 F0-11/F0-12）— DEV-0259

- **F0-11 (R6, SSRF + TLS MITM)**: `quality/url_content_gate.py::_fetch_title` 此前裸 `session.get(url, ssl=False)` — item.url 是采集来的不可信输入, 可探内网读回响应, 且 TLS 校验被禁; 前置门 URLValidityGate 又已从管线移除, 正文抓取成为零校验出站路径。修复: 走全仓唯一出站校验源 `utils/url_safety` — ① `validate_url` 前置拒收 (loopback/私网/保留段/非 http(s), 字面 IP 路径**连接前**即拒, 不触网不依赖 DNS); ② `safe_aiohttp_connector` 锁解析 IP 防 DNS rebinding; ③ **移除 `ssl=False`** (connector ssl=True, 证书校验默认开启; session 构造失败早退路径 connector 兜底关闭)。`run_async` 把 SSRF 阻断映射为专属 `ssrf_blocked` flag (**quality_check_logs 里与普通 `url_unreachable` 可审计区分**, 不混入)。
- **F0-12a (R6, CWD 分裂)**: 生产 `.env` 实测 `HOTSPOT_DB_PATH=./backend/hotspot.db` 为相对路径 — 修复前换 CWD 启动解析到全新空库却 ATTACH 真实 warm 库 (main/warm 读写分裂, 磁盘 0 字节 `data/hotspot.db` 为证)。修复: `config/__init__.py` 新增 `_anchor_to_repo_root` field_validator, 7 个磁盘路径字段 (log/db/backup/data/warm/cold/llm_wiki_v2) 相对路径统一锚定仓库根 (.env 所在地, 语义自然); 绝对路径原样; **不做 resolve()** (符号链接解析 macOS `/var→/private/var` 会破坏 conftest T01 隔离守卫的字符串前缀断言)。真实配置冒烟: repo 根与 /tmp 两 CWD 启动均解析到同一 `/path/to/hotspot/backend/hotspot.db`。
- **F0-12b (R6, 权限位)**: 库文件与备份产物默认 0644 (含 llm_secrets 密文与全量 wiki 正文, 同机任意进程可读)。修复: ① `repository/db.py` 新增 `secure_db_file` (0600, 含 -wal/-shm 边车, best-effort), `get_connection` 每线程首连对 main/warm/cold 三库执行 (幂等, 存量 0644 自动收紧); ② `backup_service.py` 新增 `_secure_artifact`, 全部产物落盘即 0600 (全量/增量 .db 快照, .sha256 旁车, knowledge zip, manifest, 增量 .bin 链, 恢复目标)。
- **验证**: 新增 `test_url_content_gate.py` (7 用例: 127.0.0.1/192.168/localhost/file:// 连接前拒收 + ssrf_blocked flag + AST 契约任何调用 ssl 必须 True) + `test_db_hardening.py` (7 用例: 极端 CWD 锚定 / 双 CWD 同库 / 绝对路径原样 / warm-cold 同锚定 / 0644→0600 首连收紧 / -wal 边车 / 备份全产物 0600) 全过; 爆炸半径回归 102+24+51 passed (backup/url_safety/warm/isolation/config_hot_reload/quality 域); ruff 触碰文件 0 错; `generate_meta --check` 过。**Pre-existing 澄清**: `test_config.py::test_default_values` host 断言失败经 stash 复证为存量环境性问题 (本机 .env `HOTSPOT_HOST=0.0.0.0`, conftest 注释早已记录此坑), 非本批引入。

### 2026-10-02 v0.8.6 P0-8 E9/E10 修复 + E11 完整性断言 — DEV-0258

- **E9 (409 路径 NameError)**: `api/event_types_api.py` `_http_exc` 引用未导入的 `ConflictException` (ruff F821 唯一命中) — 冲突路径实际抛 NameError → 客户端 500。修复: import 补齐 (+顺手清触碰文件 pre-existing F401 `Query`)。新增 `test_event_types_api.py` 4 参数化用例锁 404/400/**409**/500 映射 (修复前 Conflict 分支必炸)。**验收 ruff F821 = 0 达成** (全后端 `--select F821` 0 命中)。
- **E10 (路由双声明 + 563 行不可达组件)**: `routes/index.tsx` 中 `/judge` 与 `/judge/graph` 各声明两次 (NAV4 扁平 redirect 在前胜出, SentinelLayout 组内页面路由永不可达), `/cases` 亦有同款重复。修复: 删 SentinelLayout 组内 `/judge` `/judge/graph` 声明 + v0.8.5 组重复 `/cases`; **`SentinelJudgePage.tsx` (563 行) + colocated test 物理删除** (零真实引用 — SentinelHomePage 并未 import, NAV4 记录的"嵌入"未发生, 判读能力实际由 `/` 质量区承接); `lazy-imports.ts` 导出删除; `scenario_deep_snapshot.test.ts` 移除对应用例; 4 处 `/judge` 残留链接改指 (SentinelGraphPage ×2 → `/`、CaseDetailPage onBack → `/action`、SentinelActionPage → `/`)。守卫测试 `nav4_shell.test.tsx` 新增 **"1 path 1 声明"全局唯一断言** (提取全部 `path="..."`, 重复即 CI 红 — 审计验收机械化)。ROUTE_REGISTRY.md 本就只记 redirect 口径, 无需改。
- **E11 (CORE_ROUTERS 完整性, 廉价修法)**: 白名单 45 项中 8 项实为 `config.feature_*` 条件注册 (谎报"永远注册"), 23 个无条件注册模块漏登记, 原断言只查重叠不查完整性。修复: ① `core/routers.py` 语义重组 — `CORE_ROUTERS` (60 项, = 无条件注册面) + 新增 `CONDITIONAL_ROUTERS` (9 项, feature flag 条件) + 防重叠断言扩为三向; ② 新增 `test_core_routers_completeness.py` AST 解析 `_registry.py` `register_all`, 三向**双向**核对 (顶层无条件 == CORE / feature 分支 == CONDITIONAL / extension 分支 == EXTENSION_ROUTERS) — 新增 router 漏登记即 CI 红, 白名单与注册面互为镜像; ③ 断言即抓即修 2 处 EXTENSION_ROUTERS 漏登记: `skill_registry` 键补 `skill_registry_v1_api`+`skill_registry_runs_api`, 新增 `trigger_gate` 键 (`trigger_webhook_api`, 此前 features 端点漏报)。
- **验证**: 后端 ruff 触碰文件 0 错 + F821 全仓归零 · `test_core_routers_completeness`+`test_feature_gates` 80 passed · `test_event_types_api` 4 passed · 启动冒烟 `register_routers` 91 routes + CORE=60/CONDITIONAL=9 · `generate_meta --check` 过 (无注册增删) · 前端 tsc 0 错 · vitest **657/657** (SentinelGraphPage 空态断言随文案同步更新) · vite build OK。

### 2026-10-02 v0.8.6 P0-7 warm 两处写库失败修复（审计 E15）— DEV-0257

- **起因**: v0.8.6 PRD P0-7 / 第一性审计 E15 — 生产日志两类写库失败: `_write_fingerprints failed: no such table: warm.hotspots` **439 次** (2026-10-02 当日日志仍在发生) + `write quality log failed: no such table: quality_check_logs` (warm 遗失窗口期)。即 2026-09-21 批挂起的 "`_write_fingerprints: no such table warm.hotspots` 单独工单"。
- **根因 (生产库副本实测定位)**: `scripts/migrate_temp_layers.py` 把 WARM 表 DDL **原样**拷入 warm.db, `content_fingerprints.hotspot_id REFERENCES hotspots(id) ON DELETE CASCADE` 随迁 — SQLite FK 只在子表所在 schema 内解析父表 (**跨库 FK 不支持**), 连接级 `foreign_keys=ON` 下 warm 侧 INSERT 全数失败 → 指纹补写断供、跨轮去重静默失效。该 FK 与其 CASCADE 在 warm 内永远不可能生效, 剥离无语义损失。`quality_check_logs` 无 FK、裸名当前可解析, 但属"环境探测"而非声明路由。
- **修复**: ① `repository/db.py` 新增 `_fix_warm_dangling_fks` init_db 自愈 (`PRAGMA foreign_key_list` 扫 warm 全表 → 悬空 FK 表以剥离 REFERENCES 的 DDL 重建, 行/显式 id/具名索引保全, `foreign_keys=OFF` 包裹, 幂等; best-effort 契约同 `_ensure_warm_*`) — 附带治好 `knowledge_skill_config→secrets` / `sync_history→sync_configs` 两张 0 行同病表; ② `db.py` 新增 `warm_table(name, conn)` accessor (main 优先, 镜像 SQLite 解析序, 对齐 `knowledge_items_table` 声明式路由哲学); ③ `quality_repo` 四处读写 + `collection_dedup` 判定/补写 + `collection_repo.insert_fingerprint` 全部走 accessor (每批解析一次, 查询数不随条目数增长)。
- **验证**: 新增 `test_warm_write_paths.py` 8 用例 (E15 错误复现 → 自愈 → 写入/去重恢复闭环 · 幂等 · warm 内合法 FK 不动 · accessor 三态 · 两写路径 warm 端到端); 定向回归 **76 passed** (fingerprint/quality_repo/collection_repo/t1_trigger/warm_indexes); 生产三库 /tmp 副本 `init_db` 端到端 12/12 断言全过 (FK 清零 · 33 行指纹保留 · 索引重建且 EXPLAIN SEARCH · `insert_fingerprint`/`write_log` 真实落 warm · 二次 init 幂等); ruff 触碰文件 0 错。
- **验收对照**: PRD "生产 24h 归零" — 代码路径已断根, 生产后端重启即触发 init_db 自愈, 待 24h 日志窗口复核归零。

### 2026-09-21 main 采集能力异常三层根因修复 — DEV-0226

- **现象**: 前端首页空态 "该范围暂无收录"。第一性逐环排查 (服务→数据→调度→采集→API→前端) 实锤三层独立根因叠加。
- **根因① 进程残留**: 服务带 `HOTSPOT_DISABLE_SCHEDULER=1` 启动, 57 jobs 全不点火 → `env -u` 干净重启。
- **根因② main 库 schema 漂移** (核心): 历史修复脚本 CREATE-only 幂等重放把 ~30 张 WARM 表误建到 main — 裸名 SQL 解析 temp→main→attached, main 同名表劫持本应写 warm 的全部读写; `collection_runs` 停在 001 老版 (status CHECK 缺 'running') = 采集写入链结构性断点。修复: 以 `scripts/retention.json` 为权威, 五相搬迁 (备份 175 表 → warm 79 对象就位含 041 最终版 → 3 张有数据表显式列名迁移 → main 45 对象 DROP + wal_checkpoint → 验证全绿), 备份留 `/tmp/hotspot_pre_warm_migrate_20260921.db`。
- **根因③ lifespan 阻塞** (新发现): `mitre_attack sync_to_db` 同步网络调用直接跑在 async lifespan, STIX 下载超时分钟级冻结 event loop → uvicorn 永不 bind 端口, 日志仍显示 startup_complete (强误导)。修复: `backend/main.py` 图点火 hook 改 `run_in_executor` 线程池后台化。**纪律确立: async lifespan 内禁止直接调用同步网络函数**。
- **验证**: `/api/health` status ok / 7d total=84 (空态消除) / catchup ingested=27 / warm 写入落点健康 (collection_runs 0→52) / 定向回归 40 passed; 服务干净环境运行 pid 6787。遵 owner 裁决未提交。

### 2026-09-21 服务启动修复 + 测试假设过期清零 — DEV-0225

- **服务异常修复**: migration 119 在生产 hot.db 崩溃 (knowledge_items 表缺失, warm.db 2026-09-18 遗失) → 前插 `CREATE TABLE IF NOT EXISTS` 幂等修复 (DEV-0182/112 先例), 服务恢复启动。
- **全量回归 6 failed 清零**: 均为 DEV-0196 (gate 开闸 + t1_score→pi) 后测试写死假设过期 — ai_classify/semantic_filter 两处 gate-off 改 env 覆盖; secrets 3 测钉 sensenova (pi 无 secrets 槽); model_router/scenario 两处期望动态对齐 router/llm.yaml 真源。两条修复模式已写入 DEV-0225 (复发时照抄)。
- **验证**: 全量 pytest **4666 passed / 9 skipped / 0 failed** (7m00s); 3 处残留 delenv 复核为"测 TOML 默认开"正确语义。
- **附带**: 全仓库接口梳理 (86 routers / 146 services / 57 jobs / 13 collectors, 与 ARCHITECTURE.md 数字一致, 无漂移)。

### 2026-09-13 七项决策落地: 收缩批全清 + CRM 删除 + 三份设计稿 — DEV-0204~0212

- **裁决** (owner, 7 项): ①P1-0 = dsh 设计边界控制 + pi 执行 (设计稿待复议) ②继续收缩解耦 ③前缀化走 accessor 模式 ④CodeGarden 转型安全实践域 (行动侧, 开源工具实践, 选题提取自资讯流) + **CRM 整体删除** ⑤prompts 命名不改 ⑥mitre 数据做知识梳理 (场景讨论稿) ⑦push 维持禁令 (已做本地 bundle)。
- **收缩批交付** (全部守卫验证): **R2** v1_admission 四表 + collection 四表补 repo (豁免 50→**42**); **R3** knowledge_api/case_api/sources/secrets 四大文件拆 ≤150 聚合层 (豁免 36→**32**, URL 等价性程序化证明 50 路由 AST 全等); **R4** skill_registry⇄skill_runner 环解开 (execute 改 runner 必填注入, 生产调用方实为 0), **环白名单归零** — 全 services import 图零环; **accessor** knowledge_items 裸读 43 处/21 文件→**0** (含 maintenance 参数化/wiki_stats 模块常量运行时化/t5 PRAGMA schema 化); **SSE** sentinel 4 页迁 realtime.ts (节流窗口逐字对照, DEV-0167 纪律 cadence 套件验证), useSSE 直调仅剩底座。
- **删除批**: CRM 全域 (后端 10 文件+前端 9 文件+gate+settings 入口+security-cockpit 设计稿 2497 行, -5040 行), 迁移 116 幂等 drop 三表; 实际构成以 grep 引用图谱为准 (crm 组件实为 7 文件)。
- **设计稿** (复议后状态):
  - `docs/DESIGN_P10_EXECUTOR_2026-09-13.md` → ✅ **已批准** (4 开放问题按推荐项: 逐 plan 审批 / 本机+降权 / 人工 plan 兜底 / 只读类 Action 试点); 待令开工 P1-0a 人工回执止血可先行
  - `docs/DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md` → ✅ **已批准 (含修订)** — 修订: **S1 信号提取对全部资讯识别** (不限域, 候选层再分类排序), phase2b 列删除候选
  - `docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md` → ✅ **v3 已批准 (4 开放问题全关)** — 词表 **11 类 (8 通用+3 金融特有: 反诈/数据泄露/监管通报)** / 数据来源 **LLM 抽取→owner 人审落库** (详见 §7 抽审规约: 候选池表/三态审核/追溯链/金融语料边界) / **L1 漏洞绑 CVE, NVD 为权威源** (与 P1-5 联动) / **技战法卡放知识层 (v1_knowledge), 判断层做调用** (详见 §8 双向关联: v1_judgments 扩 1 列 + knowledge_technique_ref 新表 + judgment 上下文装配 + 反向 SSE 通知不自动重生成); 分期 MP-1 图谱点火 1~2 天 (地基, 无依赖) / MP-2 L2 事件类型 3~4 天 / MP-3 L1 漏洞 2~3 天 (与 P1-5 联动) / MP-4 L3 响应+双向关联 2~3 天
  - `docs/PLAN_MP2_EVENT_TYPE_2026-09-13.md` → ✅ **方案立项** — **5 agent 并行覆盖 11 类** (agent-A 通用高优 5 类勒索/钓鱼/Web 入侵/供应链/云泄露 / agent-B 通用次优 3 类爆破/内部威胁/AI 模型投毒 / agent-C 反诈 / agent-D 数据泄露 / agent-E 监管通报; 5 个独立 worktree 互不阻塞); **金融三类按建议递进**: 监管通报 → 反诈 → 数据泄露 (第 3 批语料稀备降级); owner 人审是关键路径瓶颈 (~5.5h 分 2~3 天); 数据模型 5 表 (event_type 实体播种/event_technique_candidates/event_technique_map/incident_reports + 索引); 6 守卫测试; 验收门 11 类全覆盖每类 ≥3 条审定

### 2026-09-13 MITRE ATT&CK 知识图谱实例化: MP-1 图谱点火 + MP-2 事件类型 5-agent 并行 — DEV-0216~0219

- **MP-1 图谱点火** (commit `5060b24` on main): `load_attack_data()` + `MitreAttackClient.sync_to_db()` 接入启动流程, `attack_techniques` / `attack_cwe_map` / `security_edges` 表落数据; tactic=1 bug 修复为 14; 死视图 `view=attack` / `view=compliance` / `view=full` 复活; 5 守卫全绿 + pytest 5/5 通过。
- **MP-2 事件类型实例化** (3 commits on main): 
  - agent-A 共享基建 (commit `150efa2`): migration 117 (5 表: event_type 实体 + candidates + map + incident_reports + attack_techniques FK) + 4 service (IncidentReportService / EventTechniqueExtractService / EventTechniqueReviewService / AttackLabelService 多语义入口) + 4 repo + 6 API 端点 (candidates 2 + approve/reject/batch/event-types/techniques 4) + 5 守卫测试 + 25 语料。
  - B/C/D/E 语料合并 (commit `0ff0d13`): agent-B/C/D/E 语料 + 脚本合并到 main (agent-D 因含回归简化代码拒绝合并, 其语料已由其他 agent 覆盖); seed 文件安全落地 `dev_data/event_types_seed.json` (gitignore)。
  - API 拆分修复 (DEV-0219, commit `a2d4c68`): `event_technique_api.py` 200 行违反 ≤150 行守卫 → 拆分为 `event_technique_api.py` (107 行, candidates) + `event_types_api.py` (130 行, approve/reject/batch/event-types/techniques); URL 与 `_registry.py` 挂载点不变; 架构数字同步 83→85 routers / 141→145 services / migration 117。
- **验证**: 全量 pytest **4598 passed / 9 skipped / 0 failed** / vitest **496** / tsc 0 / build OK / `generate_meta.py --check` 全绿 ("OK: ARCHITECTURE.md matches code" + "OK: AGENTS.md 数字一致性校验通过 (4/4 文档)")。
- **当前状态**: MP-1/MP-2 基础设施已落地 main (4 commits: `5060b24` / `150efa2` / `0ff0d13` / `a2d4c68`); **11 类事件类型候选池待 owner 人审** (首批 3 类: 勒索/钓鱼/Web 入侵, ~5.5h 分 2~3 天); 金融三类递进 (监管通报 → 反诈 → 数据泄露); agent-D 语料质量不足 → **金融三类语料来源已按金融国际/国标/行业标准扩充** (`data/security/event_types_seed.json`, FATF/ISO/GB/JR/T/PCI DSS/NIST CSF/巴塞尔协议等); 待令开工 MP-3 (L1 漏洞绑 CVE, 与 P1-5 联动) / MP-4 (L3 响应 + 双向关联)。
- **风险**: owner 人审是关键路径瓶颈; agent-D 分支含回归代码拒绝合并 (event_technique_extract_service.py 218 行简化版, 移除 LLM 调用代码); 金融三类来源池已从原始监管通报/国际报告扩展为“国内监管 + 国际标准 + 行业标准”三层来源, 人审时可优先按国标/行业标准采标, 降低语料稀备降级概率。

- **验证** (实现与验证分离): 全量 pytest **4598/9sk/0** / vitest **496** / tsc 0 / build OK / meta --check 0 MISMATCH (**85 routers / 145 services / 117 migrations**) / 审计 **P0=0 P1=0** P2×6 记录性 (报告 .ua/tmp/shrink-batch-code-audit-report.md; R3 AST 全量 50 路由全等、R2 逐字比对、CRM 残留 grep 0 独立复核)。
- **遗留**: 设计稿三项待复议后实施 (P1-0a 止血可先行); R2 豁免 42 条剩余 (maintenance 动态 SQL/trigger_gate/skill_runner 等随触碰收缩); R3 豁免 32 随手收缩; scripts/db_diet.py 参数化 DELETE 在守卫外 (retention 台账路径); 文档历史 CRM/旧数字引用留 spec 修订批。
- **MITRE 实例化当前态** (DEV-0216~0219): MP-1 图谱点火已合入 (commit `5060b24`); MP-2 共享基建 + B/C/D/E 语料已合入 (commit `150efa2` + `0ff0d13`); API 层拆分修复已合入 (DEV-0219, commit `a2d4c68`); **11 类事件类型候选池已就绪, 待 owner 人审窗口开启** (首批 3 类高优: 勒索/钓鱼/Web 入侵; 金融三类递进: 监管通报→反诈→数据泄露)。

### 2026-09-13 解耦工程 P0-0 + 五批全落地: 止血/API 收口/repo 收敛/解环拆上帝服务/前端域客户端 — DEV-0191~0203

- **执行** (6 commits `a45e22c..184b592` on main, 未 push, 方案 `docs/FEATURE_DECOMPOSITION_2026-09-12.md` 最终版): **P0-0** (`60acba0`) 止血十项 — dsh 命令白名单三层 enforce + token 鉴权(默认关) + 回环 guard 共用 + vite host 127.0.0.1 + kl 路径穿越封堵 + **备份链根治** (WAL 帧累积 checksum/v2 格式/三库全量/原子恢复, 生产端到端 checker 27/27 integrity ok) + 证据收据三类 entity_type 白名单 (恒 pending→committed) + crypto 参数修正 + 明文 key 清扫(迁移 115) + 错误契约 8 码扁平 envelope (前端 10 组件同步)。**Batch 2** (`7a2b8fa`) api/knowledge.py 711→39 + api 层 52 处直连 SQL 清零 + R3 守卫。**Batch 3** (`756e569`) v1 五表补 repo + R2 守卫 (54 表豁免冻结增量) + knowledge_items_table() 单一真相源。**Batch 4** (`e257baa`) action⇄run 解环 (run_orchestrator) + R4 守卫 (Tarjan) + knowledge_service 974→150 / collection_service 1071→296 facade 拆分。**Batch 5** (`184b592`) 5 前端域客户端 + ~85 组件/hook 迁移 (**裸 fetch 280→11, 网络调用归零**) + SSE 失效统一 (realtime.ts, v1 迁移/sentinel 登记保留)。
- **守卫族** (4 个新机器断言, 规则机器化): R1 分层 (禁 services→api) / R3 api 零 SQL+行数豁免 36 / R2 写路径唯一 (表豁免 54 收缩制) / R4 零环 (白名单 1: skill_registry⇄skill_runner)。架构数字 85→86 routers / 127→141 services。
- **验证** (每批双独立 agent, 实现与验证分离): 全量 pytest **4600/9sk/0 失败** (基线 4466→+134 用例) / vitest **509** / tsc 0 / build OK / meta --check OK / 每批 code-reviewer 审计 **P0=0** (P1 累计 8 条全修: 备份 checksum 撕裂帧/恢复原子性/守卫绕过面×2/前端信封同步等); 报告 `.ua/tmp/{p0,batch2..5}-code-audit-report.md`。
- **遗留** (豁免收缩路线, 非阻断, 见方案 §4): R3 行数豁免 36 文件 (knowledge_api/case_api/sources/secrets 为目标) / R2 表豁免 54 条 (maintenance 动态 SQL 文件级/v1_admission 四表) / ai_hub write_back 外移待授权 / 裸读 knowledge_items ~20 文件 / sentinel SSE 5 处迁移 / P1-0 执行器 (产品决策待 owner)。

### 2026-09-12 解耦 Batch 1: SSE 事件总线下沉 + 分层守卫上线 — DEV-0191

- **背景**: owner 指令"熟悉仓库 + 功能拆解 + 关键功能独立 API + 解耦 (高内聚低耦合)"。盘点结论: 85 router 已按功能分文件 (`api/_registry.py`), "独立 API"骨架已在; 真正的债是四类耦合 — 反向依赖 8 处 / 层穿透 (api 直连 SQL 50 + services 绕 repo 239) / 上帝模块 (`api/knowledge.py` 711 行、`collection_service` 1071 行等) / `action↔run` 环。完整方案 = `docs/FEATURE_DECOMPOSITION_2026-09-12.md` (13 域拆解总表 + R1~R6 机械规则 + 五批路线图, Batch 2~5 待裁决)。
- **交付** (Batch 1, 零行为变更): 事件总线 `publish_event` 自 `api/events.py` 下沉 `backend/core/events.py`, **8 处 services/scheduler→api 反向依赖清零**; `api/events.py` 只留 SSE 端点 (C11 R18 outbox 重放不变); 新增 `backend/tests/test_layering_guard.py` AST 守卫 (services/scheduler/collectors/repository 四层禁 import backend.api — 分层规则首次机器化)。
- **验证**: 定向 51 passed; 全量 **4468/9sk/0 失败** (main 基线 4466 + 守卫 2; 与上条 4488 差 = fix/source-cadence-health 分支 +31 用例未合 main); meta --check OK (85/127/57/13 不变); ruff 触碰 11 文件 0; `import backend.main` 冒烟 OK。
- **遗留**: Batch 2 (api/knowledge.py 拆分 + api 直连 SQL 清零) ~ Batch 5 (前端域客户端收敛) 待 owner 排期; 与第一性原理 P0-0 止血批建议 P0-0 先行 (方案 §5); ai_hub write_back 外移属红线需显式授权。

### 2026-09-12 工作台聚焦 P0 交付: 标讯剔除 + 内容相关性门禁/实践域兴趣体系 — DEV-0174~0176f

- **裁决** (owner, 方案文档 `docs/WORKBENCH_FOCUS_PRD_v1.0.md` §0): ①否决「安全研究/标讯跟踪双视角切换」②**剔除工作台标讯功能** (取代初版 R2"维持现状": `/bid-alert` 路由+组件+壳菜单+Feed bid 档全删, 资讯流默认 `exclude_category=bid`; 后端 bid_alert API 与采集器暂保留, 停采待裁决) ③立项内容相关性门禁/实践域兴趣体系。**悬置裁决关闭**: v1.0 T00 "标注集 60-80" = 60 本地 admission (不入仓) + 20 入仓评测语料 (`backend/tests/fixtures/practice_domain_eval.json`)。
- **交付** (7+1 commits `1546dfe..a31d31d`+收尾): T0.0 标讯剔除 / T0.1 实践域词表 8 域 (`auto_classifier` 二级打标, 纯规则零 schema) / T0.2 评测语料 20 条+回归护栏脚本 / T0.3 `GET/PATCH /api/settings/interests` (kv+audit) + 设置页"我的方向"卡片 / T0.4 资讯流即时打标+兴趣域页内置顶 (降权不删, 游标时序保护) + 首页/FeedCard 命中徽标 / T0.5 SK-01 聚合分区 (后端; 前端渲染随 P1 动线, SK-01 无活消费面)。
- **验证** (实现与验证分离): 全量 pytest **4488/9skipped 0 失败** (+31 新用例) / vitest **495** / tsc 0 / build OK / meta --check OK / ruff 触碰文件 0。**独立双门**: 功能验收隔离库真实后端走查 **A1-A10 全 PASS** (真实三库 0 句柄零写入); code-reviewer 审计 **P0=0 / P1=4 已修** (画像读取防御 / 卡片 i18n / 两处 PRD 口径如实化待 owner 追认) / P2=11 已认领去向。报告: `.ua/tmp/p0-{acceptance,code-audit}-report.md`。
- **遗留**: ①`/api/secnews/feed` (报纸风页) 打标与 SK-01 前端摘要卡随 **P1 动线批** ②词表无偏人评属 **P1 运营机制** (同源护栏 100% ≠ 真实准确率) ③预存漂移 (非本批): SK-01 admission 查询列与 097 schema 不符静默降级、全仓 4 个预存 ruff error、bid 采集仍在跑 (停采待裁决)。

### 2026-09-10 首页刷新自激循环根治 (同分支, dev server HMR 已生效) — DEV-0167

- **起因**: owner 报首页刷新频率过高、多次页面刷新与抓取, 要求前后端节奏一致 (选 30 分钟就 30 分钟, 手动刷新除外)。生产日志实测: 页面未打开时调度器严格 30 分钟一轮; **首页打开的 44 分钟里采集启动 88 次、前端 `POST /api/refresh` 172 次** (峰值单分钟 9 轮)。DEV-0163 改对了后端节奏, 但前端 SSE 回调对**任意**事件都在 3s 后调 `refresh()` = `POST /api/refresh` (同步跑完整采集) → 一轮结束发 `job_done`+`collect_done` → 再 POST → 无限自激。
- **落地** (4 文件, 后端零改动, 不碰并行会话在改的 `SentinelShell.tsx`): ①`useSSE` 新增 `types` 过滤 (lastId 仍对全部事件推进) ②`useHotspotData` 分离只读 `refetch()` 与触发采集的 `refresh()` ③首页只订阅 `collect_done`, SSE 路径改只读重拉 + 右栏 10s 节流, 错误重试/URL 导入也改只读, 「立即采集」是唯一手动采集入口, 页脚/空态「每 5 分钟」改读 `GET /api/settings/refresh-interval` ④判断页同样过滤 + 30s 节流。
- **验证**: 新增 7 回归; 全量 vitest 487/487 (基线 480+7); tsc 本批 0 错; build 通过。**活体**: IAB 打开新代码首页挂 fetch 探针 → curl 手动采集 → `collect_done` 后页面只做 1 次 `GET /api/hotspots` + 右栏 1 次, **`POST /api/refresh` 0 次**, 后端无新增轮次; 页脚实测"每 30 分钟自动采集"。
- **遗留**: ①既有 bug — 首页/判断页 `usePipeReloadOnSse()` 在 Provider 外调用拿到空 reload, 心跳条采集后不刷新 (修法要动 SentinelShell, 待并行会话收口后做) ②手动 POST 走 `run_once()` 直调不发 `job_done` 不写 `job_runs`, 观测面板少算手动轮 ③owner 已打开的旧标签页需手动刷新一次脱离旧回调。

### 2026-09-10 国际/国内源归属 + 代理优先 + 死代码清理 (同分支, 已上线生产) — DEV-0165

- **归属落库**: migration 110 `crawler_sources.network_zone` (人工核定 6 国际主机: github.com / news.ycombinator.com / hnrss.org / thehackernews.com / hackread.com / schneier.com; 其余含 Cloudflare 托管的 4hou.com 均 domestic)。`prefer_proxy()` 以注册表为单一事实源 (enabled=1, DB 异常安全降级直连优先, 60s TTL)。
- **代理优先接线**: fetchers aiohttp 步 + github collector 第 1 步 — 国际源第一跳直接走 ProxySession (代理失败自动切直连), **实测耗时 GitHub Trending 34.9s→2.1s / TheHackerNews 30s 超时→2.1s (34 条) / Star History 31.8s→1.4s**; 国内源路径零变化。`/health/v2` 逐源暴露 `network_zone`; 新脚本 `scripts/audit_network_paths.py` 输出 全源×zone×renderer×cadence×路径 清单 (国际 4 / 国内 52) + 采集器级路径注记。prefer_proxy 归属缓存 TTL **5s** (原 60s 因 owner 反馈改 zone 延迟过长下调; 表仅 ~101 行单查微秒级; 需即时的写路径调 `invalidate_international_hosts()`)。
- **死代码清理**: 删 `services/proxy_pool.py` (零调用) 及 crawl4ai_parser 兼容钩子; `data_cleaning.validate_url` 死代理分支 (引用不存在的 config.proxy_mode) — **修正误判**: bookmark_sync 多行导入在用 (grep 漏检), 恢复为薄委托 proxy_probe.is_reachable_sync (代理感知+SSRF 门); 删 USER_GUIDE 幽灵 job `proxy-health-probe`; services 127→126 (ARCHITECTURE + 3 份 AGENTS, generate_meta 写模式不落盘需手改)。
- **验证**: 新增 9 后端测试; ruff/generate_meta 全绿; 待全量套件确认 (本条落笔时在跑)。

### 2026-09-10 网络代理内置批 (同分支 `fix/source-cadence-health`, 已上线生产) — DEV-0164

- **起因**: DEV-0163 观察组里 TheHackerNews / GitHub Trending / Star History 经 A/B 实测为纯网络问题 (直连 15s 黑洞, 7897 代理 200/秒回)。owner 裁决: 代理做成**内置可选项、默认开启、代理失效能切回原始直连**。探索发现代理子系统**三重死亡**: mode=off + `backend.proxy_session` 裸导入不可用 (`base.ProxySession` 永远 None, 兜底层不存在) + ProxySession 无失败处理; 另 3 个预存坏点 (`/api/proxy/test` 必 500、PUT 静默无效、前端设置页契约错位 UI 不可用)。
- **落地**: ①`proxy_config.py` 新增 `builtin` 默认模式 (127.0.0.1:7897 + 内置国内绕行清单 `*.cn`+25 主站), env `HOTSPOT_PROXY_*` 真正接线 (env > json > 默认), mtime 缓存 + 原子写, **进程级熔断器** (连败 3 次 → 300s 全直连 → 半开探测, `HOTSPOT_PROXY_FAIL_THRESHOLD/OPEN_SECONDS` 可调) ②`proxy_session.py` 修导入 + `_ProxyAwareRequest` 请求级回退 (代理链路失败立刻摘 proxy 直连重试 + 回写熔断) + SSRF 门 ③`BackendSession` 代理失败同轮直连重试 (不再同代理打死) ④RSS 接代理通道 (`_fetch_rss_bytes` 走 ProxySession, feedparser 只解析字节) ⑤GitHub Trending 新版 markup 解析修复 (repo 锚点不再在 h1/h2 内) ⑥`api/proxy.py` 重写 (修 /test 必 500、PUT 合并语义、直连 vs 代理逐站对照、熔断快照与重置; load/save 改模块属性调用 — 按值导入曾使 test_api 的文件保护失灵, 全量套件每跑一次把生产配置写回 off, 实测踩坑已修) ⑦前端设置页重写 (契约对齐 + 内置模式 + 熔断态 + 闭合按钮 + 直连/代理并列表)。
- **验证**: 新增 36 后端测试 + 4 前端测试; ruff/tsc/vitest 480/480/vite build/generate_meta 全绿; 生产实测: 死代理演练每轮秒切直连且第 3 败熔断、`/api/proxy/test` 经代理 5/5 vs 直连 3/5、**生产抓取链 GitHub Trending 13 条 / TheHackerNews 32 条 / Star History 1 条恢复** (国内千里马不受影响)。后端 pid 84021。
- **待办**: 被墙源仍先烧直连超时 (代理优先名单留作增强); crawl4ai/Playwright 不走代理; 误熔断半开自愈; `services/proxy_pool.py` 死代码 + migration 053 `proxy_health_log` 与 `data_cleaning.py:114` 硬编码清理工单。

### 2026-09-10 信源存活率 + 刷新节奏修正批 (分支 `fix/source-cadence-health` off `fix/v085-review-p0`, 已上线生产, 待评审合入) — DEV-0163

- **起因**: 心跳 "18 存活 / 69 离线" (实况 87 启用 = 14 active + 73 离线, 62 个为招标源); 5 分钟全量轮询 87 源 7 天 3 万 run 里 2 万 failed/partial; owner 裁决: 准确/稳定优先时效拉到 30 分钟, 先诊断抓不到的原因、能修则修、修不好激进退役, "不是能抓到多少而是多少有用"。
- **第一性根因 (实测, 按影响排序)**: ①存活与有用混成一个数字 — 健康机只看过滤后 `item_count`, 招标源首页 40 条锚点 / 0 条安全相关被判死 (含当时"存活"的采招网) ②`crawl4ai_parser` 把 markdown 当 HTML 交给锚点解析器 → bid 链 crawl4ai 一旦成功必然 0 条 (存量 bug) ③GB2312 声明 + GBK 扩展字让 `resp.text()` 抛异常被吞成 "all failed" (全仓 4 处) ④RSS feedparser 机器人 UA 被 Cloudflare 拦 + 无超时 ⑤`main.py` 硬编码 300 压过 env、`cadence_seconds`/`last_fetch_at` 死列、死源不退出轮转与每日复活形成抖动 ⑥failure_rate 口径错配永远 green / revival 与 probe 各自为政 / census 词汇漂移。**否定的假设**: SSRF 连接器 IPv6 乱序拖死直连 (aiohttp 3.14 happy-eyeballs, 未改 `url_safety`)。
- **落地**: T1 节奏 (config 1800 + 持久化 GET/POST + 启动回读; cadence 单一闸口 loader/`get_schedulable`; migration 109 全部 1800 / bid 21600; `url_full_check` 900) · T2 抓取链四修 + `SourceResult.raw_count` 存活/有用分离 (健康机/crawler_runs.fetched/source_stats.produced 走存活口径, accepted/total_items 走有用口径) · T2.3 退役 31 (备份 manifest `_drill/20260910_060238`, 改前状态 `reports/retired_sources_*.json` 可 `--revert`), enabled 87→56, 28 源经生产链实测已恢复 (电力招标网当场出 2 条安全招标), 15 源观察 · T3 failure_rate 双口径 + revival→Phase 3 grace 桥接 + `_check_url` 委托 prober SSRF 门 + census 词汇 · T4 `audit_source_value.py` 有用性排行 (133 源 / 18 有产出 / 37 低价值)。
- **新脚本**: `scripts/audit_dead_source_triage.py` (四层探测, 只读) / `scripts/check_source_fetch.py` (生产链实测, 只读) / `scripts/cleanup_retire_unfixable_sources.py` (dry-run 默认, 备份前置, 可 revert) / `scripts/audit_source_value.py`; 产物在 `reports/` (已 gitignore)。
- **验证**: pytest **4382 passed / 9 skipped / 0 failed** (+50 新测试 0 回归) · ruff 触碰文件 0 错 · generate_meta --check OK (58/14/85/127 不变) · 生产链复测 74 离线源 zero 67→46 / alive 6→27 · 后端重启 pid 59585 `/api/health collect_interval_seconds=1800`, 日志 `collect_all every 1800s`。
- **待办**: 15 观察源 per-source (SPA 薄页 / HackRead 换 feed / 安全内参改 RSS URL / TheHackerNews 慢 feed / 36氪 WAF / GitHub 抖动); Phase 3 仍 dead 的 5 个已恢复 bid 源走 03:30 probe 漏斗; 上游 crawl4ai `_crawl_web line 778` 重定向链 bug; 预存 `_write_fingerprints: no such table warm.hotspots` 单独工单; 前端设置页接 GET refresh-interval。**编号说明**: 下条 v0.8.5 记录引用的 `DEV-0162` 在 DEV_LOG 中不存在 (悬空), 本批按 max+1 使用 DEV-0163。

### 2026-09-09 审查修复批 F1-F11 + 全仓整洁批 (分支 `fix/v085-review-p0`, 待评审合入)

- **卡顿六因修复** (根因=采集管线稳态资源, 非 v0.8.5 前端): F4 门禁前 URL 预去重 (重复 item 不再每轮重付全量门禁) / F2 crawl4ai 连续超时指数退避 (300s×2^(n-1) 封顶 1800s) / F3 日志降噪 (实测 90s 窗口 2.2 万条) / F1 pipeline_stats 同步查询入 to_thread / F5 `HOTSPOT_DISABLE_SCHEDULER=1` dev 并行禁调度 / F6 compounding 30s TTL 缓存。
- **预存回归修复** (v1.0.1 融合带入, main 树复现): F11 unified_search 默认 sources 契约 + warm 限定名自适应 — **上条 D4 记录的 32 个 search/fts "pre-existing 基线" 已清零** (4285+32 → 4329 全绿) / F10 job 计数测试回写 55→58。
- **一致性漂移修正** (F7-F9): spec 路由算术双计 (85+11=96 → 85 总量含 v1 前缀 7 模块) + services 126→127 + ACCEPTANCE V1Prototype 措辞 + .gitignore runtime/upstreams 整目录。
- **整洁批**: docs 49 项归档 `archived/2026-09-09-sweep/` (git mv 全 100% rename) + 活跃指针修正 10 文件 + 新增 `docs/README.md` 导读; 磁盘垃圾 272MB (backend/logs / 杂散 DB / archify 截图); AGENTS.md 19.1→13.6KB; PROGRESS 本番规整 (v1.0 轨道 1315 行切出归档, 本条为新活跃头)。
- 验证: pytest 4329/0 · ruff 触碰文件 0 错 · generate_meta --check 过。
- **Mimosa 首次密封深扫贯通** (scan `scan-2026-09-09T14-26-59.592Z-434b9a445258`, seal sha256:3755…0e33, coverage=partial/inconclusive): 378 findings (HIGH 246 其中 250 条属 vendored dsh 上游)。生产路径响应批 `1797b47`+`a62acb5`+`63adec7`: ①真阳性 skill_runner wiki 写任意路径 → wiki root 包含性收口 ②假阳性源头措辞修正 (playbook ast 解释器自述/webdav 示例占位) ③dump_schema PRAGMA 拼接保持原状 (标识符来自自家 DB 自省; 两轮参数化重写被写入门误拦, 记人工验证接受风险) ④依赖通告 2 包命中但包名未随密封产物序列化, 待有 Semgrep 的复扫定位。

### 2026-09-08 v0.8.5 — 反向收敛: 三层 Sentinel 唯一壳 + v1.0 能力区块 (demo 评审通过, tag v0.8.5)

- [x] 用户裁决: v1.0.1 (C09-C13) 删三层路由换 v1 四入口的路线方向错误; **恢复 v0.8 Sentinel 为唯一壳**, v1.0 九对象/三类 receipt 降级为嵌入三层的能力区块。第一性依据: 复利的前提是日活, 日活的前提是顺手。上一条 v1.0.1 融合记录的方向正确、粒度不足, 其执行入口角色由 [v0.8.5 方案](docs/v0.8.5/V0.8.5_PLAN.md) 接续 (该文档已挂 superseded 横幅)。
- [x] 阶段一 spec: 路由表 §5 / 三层接口消费表 §6 / 实现验证分离 (五类独立 agent) / 方向固化机制 / 飞轮一等验收 (点火 D1 + 自动召回 D3)。
- [x] 阶段二 demo (分支 `feat/v0.8.5-demo` 10 commits, merge `a92effe`): 三层路由恢复 (SentinelLayout) + v1 四入口重定向透传 query + `/cases/:caseId` 深链 + `/knowledge/v1` + SignalPanel/CaseQueuePanel/ExecOverviewPanel 三区块 + CaseDetail 提取 + 守卫反转 `v085_route_shell.test.tsx` + 版本 0.8.5 + `V1SentinelShell` 物理删除。
- [x] 独立验证四门: FactCheck 9/9 · G1 codegen 0 drift · G2 端点 parity 74/74 · G3 黄金走查 13 PASS/1 DEGRADED/0 FAIL · code-review APPROVE · 视觉走查三层/深链/390 (judge 工具章程不含 web UI, 由主会话执行)。**独立验证战果: 抓到 `/api/skill-registry/v1` 被 legacy 参数路由运行时遮蔽 404 (openapi 静态门测不出, main 即坏), 已修。**
- [x] 收尾: tag `v0.8.5` (本地) + CHANGELOG 段 + 本条留痕。已知边界 (spec §9 明示 demo 不主张): 真实源信号供给 (B1) / dsh 真实出稿 (B2) — 分别是 D1/D2 的验收项; **B0-B7 前置阻断仍有效**, 排入 D1-D4 对应批次。
- [ ] **D1 (已开工, 开发项全部落地, 仅剩观察窗)**: **点火已贯通** — `v1_ingest_bridge.py` 编排 T06/T07/T05 (RSS→SourcePipeline→准入→v1_materials+v1_signals), job `v1_signal_intake_tick` 300s (默认 security:SecWiki), 实弹 10→10→0 失败 (`7c8f990`/`92042f4`)。**D1.2 立项携带证据**: migration 108 `v1_case_materials` + create_case 自动绑定 + aggregate `evidence_materials` + CaseDetail 证据区块 (`4217cd2`)。**D1.3 Subject 抽屉**: signals API +subject_id 过滤 + SignalPanel 抽屉下钻 (`4217cd2`)。仅剩: 准入规则观察窗 (job 自动积累 admission_log, 数日后调优, 无代码)。
- [ ] **D2 (已完成, `ee2228c`)**: 端口固定 (`npm run dev:demo`=8898→8000 固定对; 修 dev_environment.sh 代理 env 变量 bug); R09 artifact API 级 CAS (verify/accept/reject +expected_revision, 不符 409); CaseDetail 真实出稿按钮 (生成判断 SK-02 需证据+CVE 解析 / draft 发布 / 生成行动 SK-03 需 published 判断 §10.1, 失败如实报错); P2 修复 (aggregate 竞态守卫 + V1Prototype 死代码清理 698→330 行)。R05/R07 已在 C07 修好。
- [ ] **D3 (已完成, `d4664d9`)**: SK-05 自动召回 — `auto_recall_for_case` 已发布知识 × case 文本读时匹配 (CVE +5 / 关键词 +1 需 ≥2 分, 非 published 不参与, 候选带 reasons 诚实可解释); aggregate +recall_candidates; CaseDetail 召回区块 + 采用免手填 (case 页发起自动带 case_id)。**一等验收实弹**: 第二个同类 Case (无手动关联) 自动浮现 FastGate 处置手册, API 采用 → 回执 id=3 (total=3, adopted=3)。
- [ ] **D4 (已完成, `410c2e4`)**: 路由对账 (ROUTE_REGISTRY v0.8.5 重写); 复利卡诚实计数 (aggregate `reuse_summary`, adoption 真实回执, 不做无基线估算); **验收矩阵 `docs/v0.8.5/ACCEPTANCE.md`** (一致性门/§13/D1-D3 逐条对真实证据); legacy 对账 (dev mapping=0, 生产 853 行迁移需授权+备份前置)。后端全量回归 4285 passed (32 failed=pre-existing search/fts 基线)。
- **关联记录**: DEV-0162。方向固化: 改方向必须显式重写 `v085_route_shell.test.tsx` + 撤 spec 横幅, 不允许静默漂移。

### 2026-09-13 NAV4 四菜单壳重构 (本地待评审合入) — DEV-0174

- **起因**: Plan B demo「案头 The Desk」信息架构, owner 裁决按其 IA 重构 (资讯/知识/行动/设置 四菜单), 路径全复用既有路由、零新一级入口。核心判断: **「判断是动词不是房间」** — 判读台 (judge) 拆为质量区挂资讯 + CaseQueue 挂行动 + 图谱挂知识, `/judge`/`/cases`/`/judge/graph` 三层壳整体退役。
- **P0 (完成, 当日)**: SentinelShell 4-tab 化 (`LAYER_DEFS` 3→4, `SentinelLayer` 类型扩展, `layer` prop 改 menu key) + `menuOf(pathname)` 27 条路由自动归属 + 4 条 redirect (`/judge→/`, `/cases→/action`, `/judge/graph→/knowledge/graph`, `/secnews→/secnews/feed`) + i18n 4 键 (`nav.news/knowledge/action/settings`) + 窄屏适配 (640px 四菜单折叠) + `nav4_shell.test.tsx` 重写守卫 (v085_route_shell 删) + ROUTE_REGISTRY.md 第四次重写 + CaseDetailPage/SentinelGraphPage 壳高亮归位 (judge→action / judge→knowledge)。
- **P1 (完成, 当日)**:
  - 判读台主体拆入 `/` 质量区 (SentinelJudgePage 嵌入 SentinelHomePage) + CaseQueuePanel 拆入 `/action` (ExecOverviewPanel 旁)
  - SentinelGraphPage 壳改 `knowledge` + `/knowledge/graph` 路由验证
  - **SecNewsShell 拆挂**: 6 视图 (feed/pipeline/knowledge/analyze/analytics/observability) 从 SecNewsShell 子路由改为 PageLayout 直挂; /secnews index→feed redirect + image/settings→/settings redirect; `SecNewsShell` 组件退役过渡保留文件 (P2 物理删除) + StatusBar 由 SentinelShell 心跳条接管
  - 更多菜单 (UTILITY_GROUPS 17 项) 保留过渡, P2 评估物理删除
  - nav4_shell.test.tsx 加 10 条 SecNewsShell 拆挂断言 (6 直挂 + 2 redirect + 1 index redirect + 1 引用清零)
- **验证**: vitest **501/501 passed** (基线 491 + 新增 10) · tsc 0 错 · 7 路由 curl 走查 200 OK · dev server pid 健康。
- **未实现**: 死代码物理删除 (SecNewsShell.tsx 退役保留) + UTILITY_GROUPS 删除 + 纸面风 theme 入口接入 ThemeContext (P2 任务) + spec 修订 (V0.8.5_PLAN §5 修订注③、AGENTS.md ×2、PROJECT 改写)。
- **下号**: P2 清理批 + DEV-0175 立项 (待 owner 触发)。
