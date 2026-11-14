# v0.8.9 P0 基线盘点 — 执行链全链勘察审计

> **日期**: 2026-11-14
> **性质**: 只读勘察（sqlite mode=ro + file:line grep + 全链代码走读），零改动
> **方法**: 全链代码走读（run_service / run_repo / worker_pump / skill_runner / agent_loop / run_ledger_service / action_service / case_service / knowledge_service / knowledge_ai / run_ledger_api / kpi_service / pi_transport / agent_bridge / dsh runtime+adapter / outbox / events）+ 生产库三库只读实测 + P1-0 设计文档（DESIGN_P10_EXECUTOR_2026-09-13）逐节对照
> **用途**: v0.8.9 实施计划 P1~P6 的核准清单事实基线；PRD §1.1 六断点的完整证据版
> **裁决状态**: D1~D8 已裁决（2026-11-14，按推荐项定稿，见 `V0.8.9_PRD.md` §9 与 DEV-0368）

---

## 1. 六断点总表（结论）

| # | 断点 | 定性 | 详见 |
|---|---|---|---|
| ① | run 创建即孤儿——7 态机无任何推进器 | 结构性 | §2 |
| ② | Action.start 单程票——action 永远 running | 结构性 | §3 |
| ③ | 三协议执行体全悬空——pi 仅单轮文本补全 / dsh vendor 死路 / direct 仅标记 | 结构性 | §4 |
| ④ | Case 运营型被守卫 (c) 死锁 | 结构性 | §6 |
| ⑤ | 知识回流断头——proposal 批准 ≠ Knowledge 写入 | 结构性 | §6 |
| ⑥ | 观测上行失明——artifact_yield 口径 bug + run 域零事件 | bug + 结构性 | §9 |

---

## 2. Run 推进链现状（断点①）

- 7 态机定义：`backend/services/run_service.py:8-12`（queued→claimed→running→succeeded/failed/cancelled/timed_out）；allowed_actions 映射 `:45-53`（claim/start/finish 仅为元数据）；协议白名单 `{dsh, pi, direct}` `:57`（mock 已移除）；`create_or_replay` 永远落 queued `:150`。
- RunService 本体**只有 create/list/get**（`:96-200`），无 claim/start/finish 方法；RunRepository 无 claim（run_repo.py 全文仅 insert/get/find/update_status/update_outcome/reset_for_retry）。
- `run_service.py:143` 注释宣称"真实派发由 worker_pump._c07_r04_skill_dispatcher 走 SkillRunner.run"——**与事实不符**：worker_pump（`backend/scheduler/jobs/worker_pump.py:44-45`）自述"不写 v1_runs，只跑 SkillDef"，消费 trigger_gate 票据写 skill_runs 表。
- worker_pump job 53 每 60s tick（`scheduler.py:626-631`）；dispatch 触发 = TriggerQueue.dequeue 票据带 payload.skill_id（worker_pump.py:56-67）→ SkillRunner.run（`backend/services/skill_runner/core.py:60-157`，写 skill_runs：A/B fast-path resolve→execute→commit `:162-206`；C/D 走 agent_loop 五阶段 INTENT/PLAN/EXECUTE/REFLECT/COMMIT，`agent_loop/state.py:28-32`）。
- **TriggerGate 无任何生产者**：全仓 enqueue 调用仅 `trigger_gate/core.py:117` 内部与测试；trigger_tickets 实测 **53 条全遗物**（27 done / 26 running，main 库）。
- SkillRunner 生产调用方仅 worker_pump.py:68、`skill_registry_api.py:123`、`playbook_engine/step.py:209`——与 v1_runs 零关联。
- 协议执行体：dsh/pi/direct 对 v1_runs **均无 protocol→executor 映射**；direct 仅作账本 run 标记（run_ledger_service.py:300），其"执行体"是内联 `_materialize_artifact`。

**定性**：run 创建即孤儿——状态机的允许动作只是 JSON 元数据，无任何代码路径能把 queued 推进到 running/done（除账本直插 running 的旁路）。

## 3. Action.start 后续链路现状（断点②）

- `action_service.py:287-323`：start 做 CAS planned→running（`:306-311`）→ `run_orchestrator.create_run_for_action_start`（run_orchestrator.py:37-67，attempt=1、inputs={action_id, plan_hash}）→ 发 v1_outbox 事件（action_service.py:325-341）。**之后无任何推进**。
- `run_orchestrator.py:24-26` 自述："P1-0 真实执行体 (run 派发/claim/finish 编排) 产品决策未做，本模块暂只承载启动桥接"。
- `RunLedgerService.finish_run`（run_ledger_service.py:348-361）**无生产调用方**；`run_ledger_api.py:12` 注明"Run 终判 (finish_run) 暂不开放 HTTP — 由后续 pi 执行体/artifact 校验内部调用"，唯调用点在测试（test_run_ledger.py:202）。
- `retry_run`（`:363-393`）唯一有 HTTP 出口——POST /api/proposals/runs/{run_id}/retry（run_ledger_api.py:139-147）；`_materialize_artifact`（`:402-460`）纯内部，仅被 approve_proposal（`:319`）与 retry_run（`:388`）调用。
- `ActionService.finish`（action_service.py:361-377）docstring 称"Run 完成后被 RunService 调"，但 RunService 已不依赖 action_service（run_service.py:87-91 死代码移除注）；action_api 仅 approve/start/cancel 三个 POST（action_api.py:196-231）——**running 的 action 无收口端点**。

**定性**：start→run 是单程票；且 `finish_run`/`retry_run`/`_materialize_artifact` 只服务账本 proposal Run（action_id=proposal:*），与 action.start 产出的 run 是**两套互不相通的世界**。

## 4. pi / dsh 执行能力现状（断点③）

- **pi = 单轮文本补全**：`ai_hub/pi_transport.py` run_pi_print（`:54-76`）spawn `pi -p --mode json` 单发子进程，stdin 进 NDJSON 出取 message_end 文本（`:19-51`）；serialize_messages_to_prompt（`:79-95`）平铺单 prompt（"pi -p 为单发子进程，无多轮会话语语义"）。无工具调用、无任务循环、无会话。
- **agent_bridge**（agent_bridge.py:119-238）：按 config/agents.yaml 路由 task_type → 外部 CLI 子进程（jsonl = pi --mode json / stream-json = claude）或 builtin→ai_hub generate（`:241-266`）；输出统一信封 {ok, agent, protocol, result, error, duration_ms}；trace 落 agent_runs（`:153-158`）。唯一生产调用方 `agents_api.py:39`，与 v1_runs/proposals 零关联。
- **dsh 全链降级**：runtime.resolve_effective 三态 mock/subprocess/not_configured（dsh/runtime.py:133-152）；execute_with_fallback 失败→mock 兜底 + 审计 dsh.runtime_fallback（`:236-256`），连续 3 次熔断（`:52`）。但 subprocess 路径死路——`dsh_adapter.py:12-34` D3 节点裁决：deepseek-harness runtime 二进制不在 git 树内，probe_dsh_vendor（`:116-177`）显式抛 DSHVendorUnavailableError，调用方统一降 ai_hub（如 knowledge_ai.py:115-120）；live_bridge 默认命令 `python -m deepseek_harness`（live_bridge.py:56）同样不可启动。
- pi 同构：`pi_adapter.py:20-31` D3 实测 pi coding-agent vendor TS 编译失败 → PIVendorUnavailableError → ai_hub；`pi/live_session.py` 为 T10 mock 骨架。**真正活着的只有 ai_hub gateway type=="pi" 的 `pi -p` 补全通道**。

**定性**："pi 执行"目前 = pi 命令行当 LLM 用（文本生成），不是能在边界内执行任务/工具的执行体；dsh 执行体只有 mock/降级链；三协议全部悬空。→ D3 裁决：执行体走 agent_bridge jsonl（协议实测对齐）。

## 5. P1-0 设计（P10）代码对应物核查（D1 依据）

设计决策（已裁决 D1 继承）：dsh 设计边界 / 代码 enforce / pi 边界内活动；ExecutionPlan JSON（commands[]/writable_paths[]/readable_paths[]/network[]/timeout_sec/output_artifact）；四层防线；明确不做 shell=True / workspace 外写 / 交互式输入 / 凭据传递。

| 设计项 | 代码对应物 | 状态 |
|---|---|---|
| workspace 锁定根 | agent_bridge.py:41-42、68-77（codegarden/<project>/） | ✅ 已有，可复用 |
| 静态 argv 白名单 | dsh/supervisor.py:39-93（dsh 启动命令） | ◐ 需升级为「静态 ∩ plan 动态子集」 |
| agent_bridge jsonl 协议 | agent_bridge.py:83-113 | ✅ 已实测对齐 |
| ExecutionPlan schema | 全仓 grep 零命中 | ❌ 待建（R-2） |
| per-plan enforce / sandbox-exec | 零命中 | ❌ 待建（R-3/R-4） |
| boundary_hash / executor 列 | 全 135 migration 零命中 | ❌ 待加（migration 136） |
| plan_json 列 | migration 131:11 已有 | ◐ **语义不同**——装账本审批快照 {proposal_id, kind, dual_sign}（run_ledger_service.py:305-306），非边界计划 → D2 裁决另加列 |
| close_case 守卫改写 | 未做（见 §6） | ◐ R-1 供弹药不改语义 |

## 6. Case 关闭闭环现状（断点④⑤）

**close_case 四守卫**（case_service.py:463-576，C08 R17）：
- (a) 所有 v1_actions 终态（`:490-502`）；(b) 无 active v1_runs（`:504-518`，经 v1_actions join）；(c) ≥1 verified/accepted v1_artifacts（`:520-547`，经 run join）；(d) ≥1 published v1_judgments（`:549-560`，无条件）。
- **研究型旁路**：无任何 v1_actions 行（`:522-525`）或全部 action cancelled/rejected（`:526-531`，视为研究型跳过 (c)），+ revision CAS（`:478-483`）+ published judgment。生产 6 case 全 open、1 judgment published——**研究型数学上可关，运营型不可**。

**SK-04→Knowledge 链路断点**（三处）：
1. skill `action-retrospective`（skill_registry/v1_skills.py:83-107，default_enabled=False + gate + requires_gate_check）→ `KnowledgeService.create_with_dsh`（knowledge_service.py:81-136）→ `_call_dsh`（knowledge_ai.py:102-120：vendor 不可用→ai_hub 降级）→ `RunLedgerService.copilot_draft('report')` 落 proposal（knowledge_service.py:133-135）；
2. **提案批准无 knowledge 写入**：approve 路径只做 md 落盘 + ArtifactService.create（run_ledger_service.py:442-446，无 knowledge repo 引用），artifact status 停在 pending（需人工 artifact_api.py:123/135 verify/accept）；
3. artifact/knowledge 提案 → v1_knowledge 发布 → close 守卫 (c) **无任何 glue**。

**定性**：复盘经验→Knowledge 发布是断头路；且 SK-04 触发依赖的 TriggerGate 票据无生产者（§2）→ skill 路径实际不可达。→ D8 裁决：case closed 事件直连起草，TriggerGate 不复活。

## 7. 提案通道流量现状

- `v1_proposals` 在 migration 131_run_ledger.sql:17-37（五态 + failed；payload_json 64KB CHECK）。
- 实测 **2 行**：status = draft 1 / rejected 1；kind = case_suggestion 1 / judgment_draft 1。
- 创建入口：draft_judgment（run_ledger_service.py:143-182 ← POST /api/proposals/draft-judgment）；copilot_draft（`:184-247` ← POST /api/proposals/copilot-draft + SK-04）；create_proposal（`:107-121` ← POST /api/proposals + 命令栏 create_case/report 意图（command_bar_service.py:229-250，纯静态文案无 LLM））；record_failed_proposal（`:123-141`）。
- approve/reject ← run_ledger_api.py:122-133（人工）；MCP 仅只读 list_proposals（mcp_operations.py:40），**无 MCP 写通道**。

**定性**：纯"人工点单 + 命令栏占位"——距"主干流量"差两个数量级。

## 8. v1_runs schema 现状（D2 依据）

- migration 101_v10_actions_runs_artifacts.sql:43-67：id / action_id / attempt / skill_id / protocol / trigger_source / idempotency_key / status（default queued）/ inputs_json / steps_json / budget_tokens / budget_seconds / started_at / finished_at / duration_ms / result_excerpt / error / artifact_ids_json / revision / created_at / updated_at / allowed_actions_json / reason；索引含 uniq(action_id, attempt)（`:69-73`）。
- migration 131_run_ledger.sql:11-14 后补 **plan_json / policy_version / outcome**（+ outcome 索引）；RunRepository.insert 写三列（run_repo.py:28,44-45）。
- **boundary_hash / executor：零命中**（135 migration 全查）→ migration 136 待加（D2：另加三列中的两个 + execution_plan_json）。

## 9. 观测面现状（断点⑥）

- `GET /api/ops/kpi`（kpi_api.py:19-36）→ KpiService：
  - triage_latency（kpi_service.py:41-90）：v1_cases.created_at − related_signal_ids_json 首信号 v1_signals.created_at，P50/P90/min/max，无关联信号 case 诚实缺省；容忍双时间戳格式（`:22-35`）。
  - **artifact_yield 口径 bug**（`:92-111`）：分母写 `status='done'`——现行 7 态终态是 `status='succeeded' + outcome='done'`（run_ledger_service.py:455-460），**全仓无任何代码写 status='done'** → 分母恒 0，yield 恒 None。→ D7 裁决修复。
  - signals_ratio 已降级参考值（`:113-127`）。
- **v1_outbox**（migration 104）：写入方 signal_service.py:61 / judgment_service.py:446 / artifact_service.py:250 / action_service.py:330 / knowledge_evidence_bridge.py:67。实测 **355 行、0 未投递**；分布 = v1_signal 350 / v1_knowledge 2 / v1_live_dispatch 1 / v1_judgment_published 1 / v1_action_started 1（后三种为旧命名遗留行）。**run 域零事件写入方**——run 生命周期对观测面不可见。
- SSE：GET /api/events（events.py:31）双源（进程内 subscribe + last_id 重放 outbox `:44-66`）；OutboxDispatcher 每 1s 批量 50 + mark_delivered（outbox_dispatcher.py:51-75）。

**定性**：下行管道健康（0 积压），上行 artifact_yield 口径 bug + run 事件缺失 → D7/D8 与 R-6。

---

## 10. 基线快照（2026-11-14 冻结）

| 表 | 值 |
|---|---|
| v1_runs | **0** |
| v1_artifacts | **0** |
| v1_proposals | 2（draft 1 / rejected 1） |
| v1_actions | planned 1 |
| v1_judgments | published 1 |
| v1_cases | open 6（**closed 0**） |
| v1_signals | 7,684（持续采集增长中） |
| v1_evidence_receipts | 15,549 |
| v1_outbox | 355 行 / 0 未投递 |
| trigger_tickets | 53（done 27 / running 26——全遗物，无生产者） |
| 架构数字 | 56 jobs / 19 collectors / 97 routers / 153 services / 65 core_routers |
| 版本 | 0.8.8（`168eb13` 基线 + 裁决批 `d32f4fd`） |

> 注：signals/receipts 为持续采集表，数字随时间增长属正常；主干实体（runs/artifacts/proposals/cases）在 P1 交付前应保持冻结值，P1 后按 30 天观测窗判定 G1。

## 11. D1~D8 裁决 ↔ 证据映射

| 裁决 | 依据证据 |
|---|---|
| D1 P10 继承 | §5 对照表：四层防线架构同构、可复用面（workspace/白名单/jsonl）明确 |
| D2 另加三列 | §8：plan_json 语义冲突实证 |
| D3 agent_bridge jsonl | §4：vendor 死路 + jsonl 实测对齐 |
| D4 direct 人担保 | §2：无执行体现实 + audit_log 通道既有 |
| D5 只读类试点 | §6/§7：最小风险路径验证全链 |
| D6 守卫 (d) 保留 | §6：研究型已有旁路，不放松 |
| D7 口径修复 | §9：status='done' 恒空实证 |
| D8 事件直连 | §2/§9：TriggerGate 遗物 + outbox 管道健康 |
