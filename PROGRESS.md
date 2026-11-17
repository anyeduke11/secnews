# PROGRESS.md — 执行进度台账（仅活跃段）

> **当前阶段 (2026-11-17)**: **v0.8.9 主干流量专项 P0~P6 已交付**（人工回执闭环 + 观测收口 + 边界协议 + pi 执行 + L3 加固 + Case 闭环/知识回流；演练①~⑥ 全 PASS，artifact_yield 活体 1.0），**P7 收口 C7-1 已交付**（版本 **0.8.9** 置位 + 全链版本对齐 + CHANGELOG + 权威 PRD 回写 G1~G5 分档）；**C7-2 `git tag v0.8.9` 待 owner**（前置：观测窗 2026-12-14 满窗判定 M-9/M-10 + G1 计数达标 + v0.8.8 两项遗留裁决，预审见 `docs/audit/V089_RELEASE_GATE_2026-11-17.md`）。**v0.8.8 全阶段已交付关闭**（P0~P5，约 31 commit，plan.9 终态对账完毕）——P3 零消费链路退役 + P2.5 数据热冷分层（主库 794→113MB）+ P4 七段埋点/幂等语义 + P4.5 四段指挥台与孤儿清理 + P5 版本收口 0.8.8。**当前版本**: v0.8.9（主干流量专项；PRD 见 `docs/v0.8.9/V0.8.9_PRD.md`）。
> 接手顺序: 根 `AGENTS.md` → `PROJECT.md` → 本文件活跃段。历史完整段见 `docs/progress-archive/`，docs/ 全景见 `docs/README.md`。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [v0.5-baseline.md](docs/progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [v0.5-execution.md](docs/progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 |
| **v0.6 records** | 2026-08-24/26 | [v0.6-records.md](docs/progress-archive/v0.6-records.md) (856 行) | 里程碑验收 + Phase 7 数据迁移 + P0-P3 治理全记录 |
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [v0.7-records.md](docs/progress-archive/v0.7-records.md) | SettingsHub V2 + 观测批次 ①-⑨ + v0.6.3 性能/双根合并 |
| **v1.0 轨道** | 2026-09-03 ~ 09-08 | [v1.0-track-records.md](docs/progress-archive/v1.0-track-records.md) (1320 行) | T00-T19 / C01-C14 / v1.0.1 融合方案（路线已被 v0.8.5 反向收敛取代）+ REVIEW 20 项阻断 B0-B7 整改路径 |
| **v0.8.6~v0.8.7 时代** | 2026-10-04 ~ 10-12 | [v0.8.6-v0.8.7-era.md](docs/progress-archive/v0.8.6-v0.8.7-era.md) | v0.8.6 P2/P3 收口 + v0.8.7 P3 五工单 + 停机链 R1-R17 + 资讯偏好/清理告警族（DEV-0277~0325） |

> 原 v0.5 时代的「规格与文档 / 5 文件用法」小节随 v0.5 spec 一并归档（`docs/archived/2026-09-09-sweep/v0.5_refactor_plan/`），不再维护。

## 当前活跃段 (2026-09-03 起)
## 当前活跃段 (v0.8.8 时代, 2026-11-10 起)

### 2026-11-14 v0.8.8 全阶段收口 + 计划 plan.9 终态对账 — DEV-0330~0365

- **阶段账**: P0 基线 ✅（四份盘点 520 端点）→ P1 裁决 18/18 ✅ → P2 消融 20 对象 ✅ → P3 移除 ✅（零消费 router 整链下线 + 待办域 410 垫片 + 泳道退役; routers 101→97）→ P2.5 数据热冷分层 ✅（备份链退役 449MB 回收 + 沉降管道生产实跑 37,255+37,317 行 + 重建容差 0 + 日志环截 −75% + 台账两层化 + C2.6 优化批; **主库 794→113MB, R-17-A2 ≤120MB 达标**）→ P4 强化 ✅（R-10 七段埋点 stage_span→audit_log + trace 端点; R-11 envelope error_code/retryable + Case client_request_id + Artifact 幂等去重）→ P4.5 ✅（R-15 四段指挥台 + R-16 孤儿清理 4 service/20 死导出/13 组件; services 161→153 + C5-6 知识→行动转Case 接线）→ P5 ✅（版本 0.8.8 全链对齐 + 发布门 10/13 勾）。
- **计划**: `docs/v0.8.8/V0.8.8_IMPLEMENTATION_PLAN.md` plan.9 = 终态对账（17 处一致性修正），与实况零漂移。
- **收尾动作**: PROGRESS 活跃段归档 v0.8.6~v0.8.7 时代（本文件重组）。
- **门禁终态**: pytest **5,374 passed / 0 failed** · tsc 0 · vitest 703 · build OK · meta/harness 双 check exit 0 · 回滚演练过（抽 C5-5③ revert→tsc→abort）。

### 2026-11-14 P2.5 尾巴 + P3 验收复核 — DEV-0363/0364

- P2.5 最后开口 p2.5.3④ 闭合: retention.json `$warm_boundary` WARM 层边界与保留策略声明（warm.db 36 表零 v1_* 命中; 陈旧副本经恢复+持续写入回归活跃, qcl MAX(checked_at)=当日）。
- P3 验收③首次复核: 两表停写超窗（最新行 11-04/11-08 早于生效日 11-11）+ 端点行为生产活体实测（410 契约体完整 / 404×3 / 回归路由活体 / health 200）。

### v0.8.8 留白清单（owner 侧, 实现侧不得代办）

| # | 项 | 材料 |
|---|---|---|
| 1 | T8 三主题人工走查（light/dark/paper × 四菜单） | `docs/audit/P45_ACCEPTANCE_TAIL_2026-11-14.md` §2 走查入口 |
| 2 | M-4 包体裁决（742,547 B, −1.8% 未达 −3%; 接受或改口径） | 同上 §1 |
| 3 | `v0.8.8` tag 打点授权（前置 = 1+2 闭合; M-9/M-10 观测窗可发布后继续） | `docs/audit/V088_RELEASE_GATE_2026-11-14.md` owner 清单 |

### 2026-11-16 v0.8.9 主干流量专项 — P0~P3 全交付（DEV-0368~0378）

- **阶段账**: P0 基线盘点 ✅（`docs/v0.8.9/EXECUTION_CHAIN_AUDIT_2026-11-14.md` 六断点 file:line + D1~D8 裁决 DEV-0368）→ P1 人工回执 ✅（`5aa219a` run claim/start/finish/cancel · `7ba0747` action finish 收口 · `d2d72a5` 四段指挥台接线；**演练① 达成首个 closed case**，v1_runs/v1_artifacts 0→1）→ P2 观测收口 ✅（`9b4aa97` artifact_yield 分母 `status='done'`→`outcome='done'`；活体 yield_ratio=**1.0**，此前恒 None；M-9/M-10 观测窗 **t0=2026-11-14**）→ **P3 边界协议 ✅**（`3e5cc14` migration 136 三列 + claim 落 executor · `22501a3` ExecutionPlan schema/service 状态机 + boundary_hash · `17eecb3` ai_hub 起草生成器（红线不动）+ 人工兜底 · C3-4 审批 API+UI `5ef86b5`）。
- **P3 不变式落地**: 默认拒绝（未 approved 不被执行体消费）· approve 即冻结（快照+boundary_hash+revision，改 plan = 新 attempt）· 仅 queued/claimed run 可做 plan 操作 · LLM 不可用 → 503 `fallback: manual_form`（不产半可信 plan）。
- **偏差留痕**: C3-4 落点由 `run_ledger_api.py` 改为新建 `run_plan_api.py`（142 行；原文件达体量上限 + `backend/api/AGENTS.md` ≤150 行硬约束；routers 98→99），实施计划 §4 已同步回写，无静默漂移。
- **门禁**: tsc 0 · vitest **713 passed**（98 文件）· pytest 全量 **5,388** / 相关域 130（test_execution_plan 22）· ruff clean · meta `--check` OK（56 jobs / 19 collectors / **99 routers** / 153 services / 66 core_routers）。
- **待办**: ① ~~C3-4 提交~~ ✅ `5ef86b5`；② `vite build` + `harness_analyze --check` 复跑 ✅；③ P4 pi 执行 ✅（见下段）→ P5 加固 → P6 Case 闭环/知识回流 → P7 收口 + 30 天观测窗。

### 2026-11-16 v0.8.9 P4 pi 执行 — 4 commit 全交付（DEV-0379~0382）

- **阶段账**: C4-1 enforce 编译器 ✅（`execution_plan/enforcer.py` 165 行：审批快照 → 进程约束；argv = 静态白名单 ∩ plan 子集；`boundary_hash` 不一致拒绝）→ C4-2 执行体 ✅（`execution_runner/` 267 行：逐条 subprocess 确定性 argv · `pi_executor_enabled` **默认关** · 每条落 `agent_runs`）→ C4-3 终态回写 ✅（`execute_and_settle` = 执行 + artifact 落盘登记（R08 hash 对账）+ `RunService.finish`；空 stdout → `E_ARTIFACT_EMPTY`；前端补 `v1_run` SSE 订阅 800 ms 节流重拉）→ C4-4 越界演练 ✅（`curl` → `E_ARGV_NOT_ALLOWED` **spawn 前**拦截，无 artifact、`agent_runs` 无 curl 行；熔断未触发）。
- **演练②③ 证据**（隔离 DB，`docs/audit/V089_PILOT_DRILL_2026-11-14.md`）: ② run succeeded/done + artifact report 63 B（落盘 sha256 == content_hash）+ `v1_run` outbox 3 条；③ run failed 带原因码，step1 已执行留 marker（合法步骤跑完、越界步骤未 spawn）。
- **偏差留痕**: 偏差注② —— 派发形态由 agent_bridge jsonl 改为**确定性 argv 执行**（owner 裁决；理由：plan 已冻结，LLM 转述命令 = 重新引入自由度），实施计划 §5 C4-2 已同 commit 回写。
- **如实披露**: L4 仅 500 字（全量 stdout 由 artifact `content_ref` 承接）· 路径约束是声明校验非沙箱（真隔离属 P5/L3）· `pi_executor_enabled` 生产仍默认关，开启须 owner 授权 · 首跑调试在 live DB 留 2 组演练②形态行（未删，不计观测窗）。
- **门禁**: pytest **全量 5,432 passed / 7 skipped / 0 failed**（11m18s，P4 提交后复跑）· 相关域 60 · tsc 0 · vitest **713 passed**（98 文件）· ruff clean · meta `--check` OK（core_routers **66→67**）。
- **顺手修复（DEV-0383，非 P4 新增）**: ① `action_api.py` 在 C1-2 拆分时误删 `_action_to_dict`/`_list_response` → `/api/v1/actions` 列表/详情/finish 运行时 NameError（已复原）；② `run_plan_api` 未登记 `CORE_ROUTERS` → `test_core_routers_completeness` 失败（已补登记）。

### 2026-11-16 P7 前置两笔债 —— 台账差集 + router 碎化体检（DEV-0384）

- **债一 `scripts/check_devlog_coverage.py`**（只读）: DEV_LOG ↔ git 三向差集（已对账 / 仅台账未提交 / **提交未落台账 = exit 1**）+ 重复编号检出。首跑: 248 条条目 / 1022 提交 → 已对账 171 · 仅台账 77 · **未落台账 13**（历史漂移，暴露不追溯） · 重复编号 19 组。
- **债二 `scripts/check_router_fragmentation.py`**（只读）: AST 端点密度体检。首跑: 136 模块 / 122 路由模块 / 521 端点 / 中位 112 行 → 超 150 行 **29**（存量 advisory）· 碎化候选 **6**（`kl_rollback_api` 等 1 端点 ≤40 行）· 同域前缀簇 **12**（`knowledge` 11 模块 / `v1` 8 / `secrets`·`source` 各 6 / `quality` 5 …）。
- **定位**: 均为 `check_*` 只读、恒不写代码；**未接 CI**（合并/拆分决策归 owner），避免与 ≤150 行硬约束冲突产「假门禁」。入口已登记 `scripts/AGENTS.md`。
- **提交切分**: P4 与两笔债共 4 commit —— ① `feat(exec)` C4-1~C4-3 ② `fix(api)` DEV-0383 ③ `docs(v0.8.9)` 演练留档 + 台账 ④ `chore(scripts)` 两笔债脚本（本段即台账落点）。

### 2026-11-16 v0.8.9 进展检查 + 4 处文档漂移清偿（DEV-0385）

- **检查结论**: P0~P4 全交付（17 commit），P5 加固 / P6 Case 闭环 + 知识回流 / P7 收口 **未启动**；活体 DB 实测 v1_runs 4（有效 1）/ v1_artifacts 3 / v1_cases 10（closed 1）/ agent_runs 3（`pi-executor`·argv）/ v1_knowledge 1。G2/G3 达成，G4 部分（拦截 ✅ 告警 ⬜），G1/G5 观测中（t0 = 2026-11-14 → 2026-12-14）。
- **漂移 1**: PRD §6 安全模型把 L3/L4 标「R-4 交付」而 P5 未启动（全仓无 ulimit/sandbox-exec/boundary_violation）→ 改为 ⬜ 未交付，L4 拆「逐命令审计 ✅ / 越界告警 ⬜」两行。
- **漂移 2**: PRD §4.3 + §9 D3 仍写「agent_bridge jsonl 派发」→ 回写为**确定性 argv 执行**（偏差注②），裁决理由栏保留原裁决 + 2026-11-16 改判理由。
- **漂移 3**: 权威 PRD `HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 滞后 → 原文改「原定 … 见 D3」+ 新增 2026-11-16 条目（P0~P4 阶段账 + 安全模型状态 + P5/P6/P7 待启动）。
- **漂移 4**: 实施计划 §4 C3-4「工作区已实现待提交」→ 已提交 `5ef86b5`；§11 步骤表 6 行加状态列（✅/🔶/⬜）。
- **同族顺带**: PRD 内 3 处「待裁决 D1/D2/D8」措辞与 §9 矛盾 → 改「✅ 已裁决」；PRD §8 发布计划加状态列 + commit 数订正；实施计划总 commit 数 **20→18**（与逐阶段合计不符）+ §6/§7 补未启动状态块与现状取证。
- **验证**: `generate_meta.py --check` 通过（56/19/99/153/67 零漂移）；纯文档改动，未触发 pytest/前端门。

### 2026-11-16 v0.8.9 P5 加固 — L3 系统层落地 + 红线演练④（DEV-0386）

- **交付**: C5-1 一 commit —— 新建 `execution_runner/sandbox.py`（per-plan Seatbelt profile + ulimit exec launcher）+ `observability_alert_service.py`（告警基建下沉，scheduler `_fire_alert` 改委托去重复实现）+ runner 接线（L3 约束 + `executor.boundary_violation` 告警 + CPU 信号宽限）+ 27 测试用例（21 新 + 6 改）+ 可复跑演练脚手架 `scripts/drill_v089_c5.py`。
- **红线演练④ 6 步全达成**（隔离 DB）：① 基线合法执行 ok（stdout=`source material`）② 写 workspace 外 → 内核 `PermissionError` + **文件未产生** ③ 读仓库 `.env` → 内核 `PermissionError` ④ 出网 → `NET-BLOCKED gaierror` ⑤a 死循环 → **内核 SIGXCPU（rc=-24）** ⑤b `sleep(30)` → `E_COMMAND_TIMEOUT`；告警落 **2 条** `executor.boundary_violation`。
- **演练暴露并修复 2 个真实缺陷**: ① 全局 cooldown 吞掉跨 run 越界（6 次越界只落 1 条告警，违反「失败必可见」）→ `fire_alert` 新增 `dedupe_key`，执行体传 `run_id`；② CPU 限额与 wall timeout 同值 → 内核限额永不触发 → wall timeout 加 2s 信号投递宽限。
- **Seatbelt 实测语义 5 条**（macOS 27.2，已写进模块 docstring）: last-match-wins · subpath 匹配 realpath · `deny default`+读白名单会让 CPython abort（改定向 deny 收窄）· host 级出网白名单不可表达 · 仓库内 venv 解释器需 subpath + literal 祖先目录双重放行。
- **已知边界（如实）**: 仅 macOS 生效（非 macOS 降级为仅 ulimit，audit_log 留痕 `sandbox=unavailable`）· `plan.network` 非空仍全禁（更严不放松）· `RLIMIT_AS` 内存上限 macOS 不可收紧（未实现）· 仓库外系统文件仍可读（边界目标是「计划外项目数据与凭据」）。
- **门禁**: pytest 全量 **5,461 passed / 7 skipped / 0 failed**（33m35s，较上轮 11m18s 慢 — 采样定位卡点在 SQLite prepare/parse 而非 sandbox 测试）· 相关域 75 · ruff clean（`backend/` + 演练脚本）· `generate_meta.py --check` OK（services **153→154**，新 service 已 `--fix` 同步 7 份文档）· 消融验证通过（关掉 sandbox → L3 测试确实失效）。
- **文档联动**: PRD §6 安全模型表（L3/L4 越界告警 → ✅）· PRD §8 发布计划 P5 行 · 实施计划 §0/§6/§11 · 权威 PRD 2026-11-16 条目 · 演练留档。

### 2026-11-16 v0.8.9 P6 C6-1 试点演练⑤ — 运营型 case 全链关闭（DEV-0387）

- **补齐 P5 尾巴**: `plan.network` 非空时 L3 仍恒 deny-all，但 `describe_limits` 只记声明值不记「声明被忽略」→ 增 `network_enforced="deny-all"` + `network_declared_ignored` 两字段 + runner warning + 断言（sandbox 测试 21→22），运维不再把「plan 声明了 net 却被拒」误诊为 bug。
- **演练⑤ PASS**: 运营型全链（case→judgment→published→action→run→artifact）经服务层合法通道关闭；`content_hash` 与落盘 sha256 一致（`8389dbca…beb9`）。
- **四守卫反向各自取证**（不是「结构性通过」）: (a) N1 action running 拦 · (b) N4 action cancelled × run queued 拦（`cancel` 不级联 run 是唯一可行组合）· (c) N2 artifact 仍 pending 拦 · (d) N3 无 judgment 的 case 拦。脚手架 `scripts/drill_v089_c6.py` 可复跑，留档 `docs/audit/V089_PILOT_DRILL_2026-11-14.md#演练⑤`。
- **C6-2 输入**: 演练实测 close **无 outbox 事件**（action/artifact/run 均有，case 无）→ `close_case` 需补 `v1_case_closed` 生产者，复盘提案才可能有触发源。

### 2026-11-17 v0.8.9 P6 C6-2 知识回流 glue — 事件直连全链 + 演练⑥（DEV-0388）

- **三处断点修复**: ① `CaseService.close_case` CAS 成功后 enqueue `v1_case_closed`（失败只 debug，不阻断关闭）② `OutboxDispatcher.add_handler` 新增订阅钩子（广播后 `asyncio.to_thread` fire-and-forget，`delivered_at`/SSE 语义不变）+ 新建 `retrospective_service`（订阅 → `copilot_draft("report")` **只起草**，`exists_for_case` 幂等）③ `_materialize_artifact` 尾部补 `_materialize_knowledge_draft`（report → `v1_knowledge` draft kind=playbook，evidence_refs 取 case 绑定材料，失败只 error 不改 Run 终判）。
- **演练⑥ PASS**（与演练⑤ 同一脚本、同一主链，隔离 DB + 临时 wiki）: 关闭后事件恰 1 条 → 提案 draft **0.015s** → 人批准 → 知识 draft(playbook) → publish → `auto_recall_for_case` 命中。人主律不破：起草、批准、发布三段各自独立。
- **首跑失败留痕（未伪造通过）**: 提案未产生 —— `copilot_draft` 契约要求 case 有绑定证据材料，演练⑤ 只把路径塞进 judgment 的自由字符串 `evidence_refs`。处置 = 主链补「7.5 绑定证据材料」（`insert_material` + `v1_case_materials`，hash 取真实文件 sha256），不放宽产品契约。
- **门禁**: ruff clean（7 文件）· `pytest -k "outbox or case_service or run_ledger or proposal or retrospective"` **78 passed** · `generate_meta.py --check` OK（services **155**）· 演练 `RESULT: PASS`。
- **文档联动**: 实施计划 §7 状态行 + C6-2 状态行 + §0 阶段表 + §11 · 演练留档（追加演练⑥）· DEV_LOG。
- **剩余**: P7 收口（version 0.8.9 + CHANGELOG + 权威 PRD 回写 + tag）须待观测窗 2026-12-14 满窗判定。

### 2026-11-17 v0.8.9 P7 C7-1 收口 — 版本 0.8.9 置位 + 全链对齐 + G1~G5 分档（DEV-0389）

- **C7-1 交付**: `backend/version.py::APP_VERSION` 0.8.8 → **0.8.9**（v0.8.9 段落说明）；全链对齐 = AGENTS.md 头部版本门 + CLAUDE.md + PROJECT.md + README.md 中英版本表/main 动态 + `frontend/package.json` + `assets/readme/{hero,roadmap,architecture}.svg` + `docs/CHANGELOG.md` v0.8.9 条目。`generate_meta.py --check` 版本一致性 7/7 通过（56 jobs / 19 collectors / 99 routers / **155 services** / 67 core_routers）。
- **G1~G5 分档（如实，不宣称未达项）**: G2 ✅ / G3 ✅ / G4 ✅ · **G1 ◐ 观测中**（活体 runs=4 / artifacts=3，目标 ≥10 / ≥5，窗口仅过 3 天）· **G5 ◐ 部分**（口径已修 yield=1.0 + `v1_run` 事件 12 条；M-9 七段 p95 / M-10 埋点开销需 2026-12-14 满窗）。
- **全量门禁抓出的真实回归（C6-2 遗留）**: `run_ledger_service` 引 `knowledge_service` facade + facade 反向引 `run_ledger_service` → **services 域依赖环**（`test_service_cycle_guard` 2 failed；定向测试未覆盖该守卫）。修复 = `_insert_draft` 落库逻辑提取为 `knowledge_evidence_bridge.insert_knowledge_draft()` module 级入口（mixin 方法改委托，公开 API 不变），`run_ledger_service` 改引 mixin 模块（计划 §C6-2 本就写明复用该 mixin）→ 单向无环；**新增哨兵** `test_run_ledger_does_not_import_knowledge_facade` 锁死（WHY: 误引 facade 即成环）。
- **演练⑥ 重跑 PASS**（解环后，全新隔离目录 `/tmp/v089_drill8*`）: 事件 1 条 → 提案 draft **0.008s** → 人批准 → 知识 draft(playbook) → publish → 同类召回命中；四守卫 N1~N4 全拦。
- **门禁全绿**: 全量 pytest **5,463 passed / 7 skipped / 0 failed** (1052.79s) · 前端 tsc 0 / vitest **713 passed** / build OK · ruff clean · `generate_meta.py --check` exit 0（版本门 7/7）· `harness_analyze.py --check` exit 0。
- **顺带纠偏**: README MCP 工具数 19 → **23**（16 读 + 7 写，与 PRD §6.1 权威口径一致；正文表格原为 v0.8.7 前旧账）；roadmap 脚注数字同步（99 routers / 155 services / 56 jobs / 133 migrations / 14 tags）。
- **发布门预审留档**: `docs/audit/V089_RELEASE_GATE_2026-11-17.md`（G1~G5 分档 + 10 项发布门 + owner 授权清单）。
- **剩余（C7-2，待 owner）**: `git tag v0.8.9` + 发布说明 —— 须待观测窗 2026-12-14 满窗判定 + G1 计数达标 + v0.8.8 两项遗留（M-4 包体 / T8 三主题走查）裁决。

### 下一版本指针

- **v0.8.9 立项（主干流量专项）**: PRD = `docs/v0.8.9/V0.8.9_PRD.md`，实施计划 = `docs/v0.8.9/V0.8.9_IMPLEMENTATION_PLAN.md`。依据: 生产实测 v1_runs=0 / v1_artifacts=0 / v1_cases=6 全 open——「资讯→知识」供给充沛（signals 7,666 / receipts 15,513）而「行动→产物→复利」零流量。
