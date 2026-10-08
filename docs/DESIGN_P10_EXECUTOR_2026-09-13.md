# 已废止（superseded）

> **本文档已被取代**：权威产品文档 = [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](../HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md)；0.8.6 版本族详细文档 = [`docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`](../HOTSPOT_V0.8.6_AI_NATIVE_PRD.md)。本文仅作历史设计留痕，**不作为当前事实源**（取代依据见权威 PRD 头部「取代」名单 + `docs/audit/PRD_ALIGNMENT_AUDIT_2026-10-02.md`）。

---

# P1-0 执行器设计方案 — dsh 边界设计 + pi 执行

- 日期：2026-09-13
- 状态：**已批准（owner 2026-09-13 复议通过）** — 4 个开放问题按文中推荐项执行（①审批粒度=逐 plan 审批起步 ②执行环境=本机+降权 ③dsh 失败时允许人工手写 plan ④试点从只读类 Action 开始）。实施按分期推进，P1-0a（人工回执止血）可先行单独批
- 背景：`v1_runs` 永远 `queued`（无执行体），Case 数学上无法关闭（`case_service.close_case` 守卫互斥），Artifact 无法产出。第一性原理 §0.1 P0-D
- 前置依赖：无（run_orchestrator.py 已预留执行编排落点；approvable 审批语义已在 Action 契约中）

---

## 1. 角色分工（owner 裁决的架构含义）

| 角色 | 职责 | 形态 |
|---|---|---|
| **dsh** | **边界控制的设计者**：为每个 Action 生成"执行边界清单"（允许的命令、可写路径、网络目标、资源上限、禁区），供人审批 | 受管子进程（AI 架构 agent），已有 P0-A 命令白名单基础 |
| **pi** | **边界内的执行者**：按审批通过的边界清单执行，产出产物 | 受管子进程（AI 执行 agent），agent_bridge 协议已实测对齐 |
| **后端（代码）** | 边界的**执行者**而非设计者：边界清单被硬性 enforce（不信任任何 AI 输出），运行状态机、审批门、产物登记 | Python/FastAPI |

**关键设计原则：dsh 设计边界，代码 enforce 边界，pi 只能在边界内活动。** dsh 的边界产出本身也要过人审批——AI 不给自己的执行放行。

## 2. 执行链路（一条 Action 的生命周期）

```
Action(approved)
  → ① dsh 生成 ExecutionPlan（结构化 JSON）：
       commands[]      — 允许执行的命令（argv 级，逐条）
       writable_paths[]— 可写目录（相对 workspace 锁定根）
       readable_paths[]— 可读目录（默认 workspace + 材料引用）
       network[]       — 允许的出站目标（域名/IP，默认全禁）
       timeout_sec     — 单命令与总时长上限
       output_artifact — 预期产物声明（类型 + 验收要点）
  → ② 人审批 ExecutionPlan（UI 展示差异要点；默认全部拒绝）
  → ③ 后端 enforce：将边界编译为进程级约束
       （workspace 目录 + argv 白名单校验 + 网络 env 隔离 + timeout）
  → ④ pi 在约束内执行，事件流回传（复用 agent_bridge stream-json）
  → ⑤ 终态：completed/failed/timeout → Run 状态机
  → ⑥ Artifact 登记（body_hash + evidence 链）→ Case 可关闭
```

## 3. 安全模型（四层防线）

| 层 | 机制 | 状态 |
|---|---|---|
| L1 计划层 | dsh 生成的 plan 是**建议**，人未审批 = 不执行；默认全拒 | 待建（UI + API） |
| L2 进程层 | workspace 锁定根（agent_bridge 已有）+ argv 白名单（P0-A 已做，扩展为 per-plan 动态子集）+ `HOTSPOT_ALLOW_LAN` 反向逻辑（执行期强制禁外联，除非 plan 显式放行且人审批） | 部分已有 |
| L3 系统层 | 执行进程降权（非 owner uid 运行，如可行）；`ulimit` 资源上限；macOS sandbox-exec profile（-f 生成 per-plan profile） | 待调研（Phase 2） |
| L4 审计层 | 全量 stdin/stdout/exit code 落 agent_runs + evidence receipt；plan 与实际执行命令逐条比对，越界即 fail + 告警 | 复用观测栈 |

**明确不做**：shell=True、workspace 外写、交互式输入、凭据传递（执行环境不含 llm_secrets，pi 用自身已配凭据）。

## 4. 数据模型变更（最小集）

- `v1_runs`：加 `plan_json`（审批通过的边界快照）、`executor`（'pi'）、`boundary_hash`（plan 指纹，审计用）
- `v1_artifacts`：不变（RunService 产出路径已有）
- 新表暂不加——ExecutionPlan 存 run 行内，避免 schema 膨胀；若后续需要 plan 修订历史再拆表

## 5. 分期实施（每期独立可验收）

| 期 | 内容 | 验收 | 工作量 |
|---|---|---|---|
| **P1-0a 止血**：人工回执通道（决策 1 讨论中方案 C 的吸收） | Run 可被人登记终态 + Artifact 可人工上传登记；close_case 守卫改写为"有终态 run 或有 accepted artifact" | 一条 action 走到 completed、case 关闭 | 1~2 天 |
| **P1-0b 边界协议**：ExecutionPlan schema + dsh 生成 prompt + 审批 API/UI | dsh 能为样例 action 产出合法 plan；审批流跑通（默认拒绝） | 一个 dry-run plan 被生成并审批（不真执行） | 3~4 天 |
| **P1-0c pi 执行**：enforce 编译 + pi 派发 + 事件回传 + Artifact 自动登记 | 一条真实 action 在边界内执行并产出 artifact；越界命令被 L4 拦截 | case 全链关闭 + 越界演练 | 4~5 天 |
| **P1-0d 加固**：sandbox-exec 降权 + 资源上限 + 越界告警接入 alert | 越界执行在系统层被拦 | 红线演练通过 | 2~3 天 |

## 6. 需 owner 确认的开放问题

1. **审批粒度**：每个 plan 逐条审批（最严）vs 按域信任（如"纯读类 plan 免审批"）？推荐前者起步。
2. **执行环境**：pi 在本机跑（现状）还是先做 Docker 隔离？推荐本机 + P1-0d 降权起步，Docker 为后续增强。
3. **dsh 的 plan 生成失败兜底**：dsh 不可达时是否允许"人工手写 plan"通道？推荐允许（plan 本质是结构化表单）。
4. **第一批试点 Action 类型**：建议从"只读类"开始（如：让 pi 汇总某 CVE 的本地产物生成 brief 草稿）——零写入风险，全链演练。

## 7. 与既有决策的关系

- 不改 run_orchestrator 编排接口（P1-0c 在其下游接线）
- 不动 ai_hub 红线（pi 走 agent_bridge，不经 ai_hub）
- P0-A 命令白名单升级为"静态白名单 ∩ plan 动态子集"（更严，不放松）
- 决策 4 的 CodeGarden 安全实践域是执行体的**下游消费方**（实践任务也是一种 Action）
