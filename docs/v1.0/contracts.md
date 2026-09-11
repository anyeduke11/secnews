# v1.0 领域契约 (contracts)

> 单一事实源: 本文件定义 9 域对象 + 状态机 + IO/错误/幂等/CAS/SSE 规范。
> 下游: `backend/domain/v1_0_models.py` (Pydantic) + `scripts/codegen_v1_ts.py` (TS) + 前端 `frontend/src/domain/v1_0.ts`。
> 受 DEVELOPMENT_PLAN §5.1/5.2/5.4 与 PRD §4 约束; 不重复全文, 只在 v1.0 强约束的点上落契约。
>
> 状态: **T03-B 起草, T03-C 写完 codegen 后即受脚本漂移检查保护**。
> 约定: 字段名/枚举值/状态字符串一旦发布 = 外部接口, 改字必须迁移。

---

## 0. 通用约定 (适用于全部 9 域对象)

### 0.1 标识与稳定键

- **id**: 客户端可见的稳定 ID。
  - Subject/Case/Judgment/Action/Artifact/Knowledge: `id` = ULID 26 字符字符串 (大写 Crockford Base32) — 人类可读, 时间序, 不带隐私。
  - Material: `id` = sha256(source + url + first_seen_at)[:26] — 同一来源同一 URL 永不重复, **不**是 sequence。
  - Signal: `id` = ULID, 与 SourceEvent 1:N (一事件可能含多条 Signal, 由 admission 决定是否合并)。
  - Run: `id` = `run_<ulid>` 前缀, 便于人眼辨识。
- **revision** (适用 Subject/Material/Judgment/Action/Knowledge/Case):
  - 整数, 单调递增, 同实体下唯一; 从 1 开始。
  - 仅在**内容**变更时自增; 单纯状态变更 (case close、action approve) **不**自增 revision — 走事件流 + 状态机。
  - 服务端强制 (HTTP 409 on conflict), 前端 UI 用 `expected_revision` 防覆盖。

### 0.2 时间戳

- **created_at / updated_at**: ISO 8601 UTC, 微秒精度, 带 `+00:00` 后缀; 服务端写, 客户端不传。
- **业务时间** (subject.imported_at / material.fetched_at / signal.occurred_at / case.due_at):
  显式命名, 不复用 created_at; 文档化"录入时间 vs 业务发生时间"。
- 所有时间字段都是字符串 (DTO 层); Pydantic 在 ingress 时校验, 服务端不假设前端传值类型。

### 0.3 通用响应字段 (5.4 §4)

任何 GET 单个 / 列表项必须包含 (在 dto 字段层, 非 envelope):

```yaml
revision: int                # Subject/Case/Judgment/Action/Knowledge/Material
allowed_actions: list[str]   # 状态机推导, 见 §1-§9
reason: str | null           # 当前阻塞原因 (blocker), null = 可继续
updated_at: str              # ISO 8601 UTC
```

能力/开关对象再带 `requested / effective / pending_restart` (DEVELOPMENT_PLAN §5.4 §4)。

### 0.4 错误 schema (5.4 §6)

所有 4xx/5xx 响应统一:

```json
{
  "detail": "Human-readable sentence",
  "message": "Same or technical detail",
  "code": "E_CASE_CONFLICT",
  "trace_id": "01J8H7B4M5F2ZK9N0WX3RYC8PA"
}
```

| code | HTTP | 触发 |
|---|---|---|
| `E_VALIDATION` | 400 | 字段校验失败, `detail` 列出字段 |
| `E_AUTH` | 401 | token 失效 |
| `E_FORBIDDEN` | 403 | 能力未开 / 角色不够 |
| `E_NOT_FOUND` | 404 | id 不存在 |
| `E_CONFLICT` | 409 | revision 不匹配 / 幂等键冲突 |
| `E_RATE_LIMIT` | 429 | 限流 |
| `E_GATE_CLOSED` | 409 | 能力/feature gate 未开 |
| `E_INTERNAL` | 500 | 兜底; `trace_id` 必填 |

### 0.5 幂等键 (5.4 §2)

POST 创建 Run 类资源 (Action.run / Skill.invoke) 必须:

- 请求体含 `idempotency_key: str` (客户端生成 ULID)。
- 相同 key + 相同 body → 返回**同一个** run_id (HTTP 200, 重复幂等)。
- 相同 key + 不同 body → 409 `E_CONFLICT` (key 复用但意图改变)。
- 不传 key → 422 `E_VALIDATION` (不允许隐式分配)。

### 0.6 CAS (Compare-And-Swap) 写入 (5.4 §3)

任何 PATCH / PUT 必须带 `expected_revision: int` (适用对象) 或 `expected_status: str` (状态机):

- 匹配 → 写入并自增 revision, 返回新 revision。
- 不匹配 → 409 `E_CONFLICT`, body 附 `current_revision / current_status` 供前端 diff。

### 0.7 SSE 推送 (5.4 §5)

- 端点: `GET /api/events?object=case&since=<ulid>&cursor=<rev>` (具体协议 T15 定型)。
- 推送: **仅事务 commit 后**才发持久事件; 失败事务不发。
- 重连: `Last-Event-ID` 重放; 服务端检测游标过期 → 推送 `resync_required` 事件后, 客户端走 snapshot 端点拉全量。
- 接收顺序: 服务端按 `updated_at` + revision 排序; 较晚到达的旧 HTTP 响应不能覆盖新状态 (前端 query key 含 revision, 旧响应被 SWR 丢弃)。

### 0.8 写入者权威 (5.1)

| 对象 | 权威载体 | 写入服务 |
|---|---|---|
| Material (原文快照) | Wiki 单根不可变 evidence | `evidence_service.write` (T05) |
| Judgment / Knowledge (正文) | 不可变 Markdown revision | `judgment_service.publish` / `knowledge_service.publish` (T11/T13) |
| Case / Action / Run / Signal | HOT 事务 | `case_service` / `action_service` / `run_coordinator` / `signal_service` |
| chunks / FTS / 概念投影 | 派生 | listener, 失败不阻塞主流程, 不允许把未完成提交暴露为已发布 |

---

## 1. Subject (关注对象)

### 1.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| entity_type | enum[product, vendor, cve, technique, regulation, person, org, custom] | ✓ | |
| name | str | ✓ | 主显示名 |
| aliases | list[str] | | 别名, 用于 fuzzy 匹配 |
| importance | enum[critical, high, normal, low, watchlist] | ✓ | 默认 normal |
| revision | int | ✓ | ≥1 |
| context_revision | int | | 关联 context (岗位/项目) 的版本; null = 跨 context 通用 |
| tags | list[str] | | |
| notes | str | | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 1.2 状态

Subject 无工作流状态 (它是被关注的对象, 不是任务)。`reason` 字段用于:
- 别名冲突提示。
- 被下游引用计数 (不能删, 只能 archive)。

### 1.3 allowed_actions (服务端按引用情况派生)

| 条件 | actions |
|---|---|
| 无 case/judgment 引用 | `["edit", "archive", "delete"]` |
| 有引用 | `["edit", "archive"]` (delete 禁用, reason="referenced_by_n") |
| 已 archive | `["unarchive", "edit_metadata"]` |

### 1.4 唯一性

- (entity_type, name, context_revision) 唯一 (context_revision=null 时跨 context 唯一)。

---

## 2. Material (原始资料)

### 2.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (sha256(source+url+first_seen_at)[:26]) | ✓ | 稳定键 |
| source | str | ✓ | 来源名 (与 collector 注册一致) |
| url | str | ✓ | 抓取入口 |
| title | str | | |
| author | str | | |
| published_at | str (ISO) | | **业务**发布时间; null 时按 `first_seen_at` |
| first_seen_at | str (ISO) | ✓ | 抓取到的时间 |
| hash | str (sha256) | ✓ | 抓取内容 sha256 |
| parser_version | str | ✓ | parser 版本 (废弃旧值用) |
| snapshot_path | str | | wiki 内 evidence 路径 (T05 后写) |
| revision | int | ✓ | 内容变更时 +1 (parser 升级或重新抓取到不同内容) |
| extra | dict | | 抓取器/parser 自由扩展, schema 校验按 source 走 |
| quality_flags | list[str] | | 由 quality_service 打 (T05 之前为空) |
| is_fallback | bool | | fallback 抓取 (代理/缓存) 显式标, 不冒充正本 |

### 2.2 状态

- 无显式状态; 派生: `has_snapshot` (snapshot_path != null) / `quality_ok` (flags 不含 `low_quality` / `parser_error`)。
- `reason` = quality_flags 解释或 `legacy_missing` (原文丢失但记录在)。

### 2.3 不可变性

- **不删不修**; 修正内容走新 revision, 旧 revision 保留可访问 (wiki 不可变 evidence)。
- `first_seen_at` 永远不变; `published_at` 修正走新 revision。

---

## 3. Signal (情报事件)

### 3.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| subject_id | str (Subject.id) | | 关联关注对象 |
| material_id | str (Material.id) | ✓ | 必有至少一份证据 |
| summary | str | ✓ | 事件一句话 |
| occurred_at | str (ISO) | ✓ | 事件发生时间 (≠ created_at) |
| admission_rule_version | str | ✓ | 准入规则版本号 (回放可重现) |
| admission_reason | str | | 为什么被收录 (规则命中) |
| supersedes_signal_id | str | | 取代的旧 signal (同主题更新) |
| confidence | enum[verified, likely, unverified, retracted] | ✓ | 默认 unverified |
| revision | int | ✓ | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 3.2 状态机

```
unverified → likely → verified
    ↑          ↓
retracted ←── superseded
```

- 状态变更通过 `PATCH /api/signals/{id}/status`, 必须带 `expected_revision`。
- `retracted` 不可逆, `reason` 必填, 写 wiki_event。

### 3.3 allowed_actions

| 状态 | actions |
|---|---|
| unverified | `["promote_likely", "retract", "edit_summary"]` |
| likely | `["promote_verified", "demote_unverified", "retract"]` |
| verified | `["retract"]` (理由必填) |
| retracted | `[]` (终态) |
| superseded | `[]` (终态) |

---

## 4. Case (工作事项) — **首切对象**

### 4.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| title | str | ✓ | ≤120 字符 |
| question | str | ✓ | 要回答的问题 (事项主线) |
| goal | str | | 完成条件 (可衡量) |
| scope | str | | 范围 (in/out) |
| priority | enum[p0, p1, p2, p3] | ✓ | 默认 p2 |
| status | enum[open, in_progress, blocked, closed, archived] | ✓ | 默认 open |
| due_at | str (ISO) | | 截止 |
| subject_id | str (Subject.id) | | 主要关注对象 |
| related_subject_ids | list[str] | | 其它关注对象 |
| related_signal_ids | list[str] | | 关联 Signal |
| related_case_ids | list[str] | | 关联 Case (父子/并行) |
| tags | list[str] | | |
| owner_role | enum[user, system, shared] | ✓ | 谁负责 (system = 自动; shared = 多人) |
| revision | int | ✓ | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |
| closed_at | str (ISO) | | 关闭时写 |

### 4.2 状态机

```
   open ──claim──> in_progress ──finish──> closed
    │                  │  ↑↓                 ↑
    │                  │ block               │
    ▼                  ▼                     │
  archived ←─unarchive (closed) ──reopen────┘
                  blocked ──unblock──> in_progress
```

转换规则 (HTTP PATCH 必带 expected_status):

| from | to | 触发 |
|---|---|---|
| open | in_progress | 有人 claim, 必填 `owner_user_id` |
| open | closed | 立即关闭 (无动作) |
| open | archived | 归档 |
| in_progress | blocked | 提供 blocker reason |
| in_progress | closed | 提供完成结论 (至少 1 个 judgment 或显式 goal=null 的说明) |
| in_progress | archived | 仅 owner_role=system 允许 |
| blocked | in_progress | blocker 解决 |
| closed | in_progress | reopen (会创建新 judgment 记录"复审") |
| closed | archived | 归档 |
| archived | open | unarchive |

### 4.3 allowed_actions (服务端派生)

| status | blocker 存在 | actions |
|---|---|---|
| open | - | `["claim", "close", "archive", "edit"]` |
| in_progress | - | `["block", "close", "edit", "add_judgment"]` |
| blocked | yes | `["unblock", "edit", "add_judgment"]` (close 禁用) |
| blocked | no | 服务端矛盾, 500 (程序员错) |
| closed | - | `["reopen", "archive", "edit_metadata"]` |
| archived | - | `["unarchive"]` |

### 4.4 业务约束

- claim 必须指定 `owner_user_id` (本期 v1.0 单用户, owner_user_id 默认当前用户)。
- close 必须至少满足一条: 存在 judgment 引用 OR goal=null 且 `close_reason` 标 "research_only"。
- reopen 关闭的 case 自动创建 1 条 `reopened_at` 事件, 触发关联 judgment 复审提醒。
- 不可在 blocked 状态 close (服务端 409)。

### 4.5 列表端点契约

`GET /api/cases?status=open&priority=p0,p1&subject_id=<>&q=<>&limit=50&cursor=<>`:

- 响应: `{ items: [Case...], next_cursor: str|null, total: int }`
- 排序: priority asc → due_at asc → updated_at desc
- 筛选 query key (前端 SWR): `['cases', 'list', filters]`

---

## 5. Judgment (判断)

### 5.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| case_id | str (Case.id) | ✓ | 必有归属事项 |
| subject_id | str (Subject.id) | | 关联对象 |
| claim_type | enum[finding, assessment, recommendation, warning, hypothesis] | ✓ | |
| claim | str | ✓ | 核心断言 (Markdown, ≤ 10KB) |
| conditions | str | | 适用条件 (Markdown) |
| confidence | enum[low, medium, high, proved] | ✓ | 默认 medium |
| evidence_refs | list[EvidenceRef] | ✓ | ≥1 |
| counter_evidence_refs | list[EvidenceRef] | | |
| unknowns | list[str] | | 未知项 |
| status | enum[draft, published, superseded, retracted] | ✓ | 默认 draft |
| revision | int | ✓ | |
| wiki_path | str | | 不可变 Markdown revision path (T11 后) |
| content_hash | str (sha256) | | claim 文本 hash, 校验完整性 |
| published_at | str (ISO) | | 状态=published 时填 |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 5.2 EvidenceRef 内嵌结构

```yaml
EvidenceRef:
  material_id: str            # Material.id
  signal_id: str | null       # 可选 Signal 锚点
  chunk_id: str | null        # chunk 投影 ID
  offset: [int, int] | null   # [start, end] 字符偏移
  hash: str                   # sha256, 与 material.hash 一致才生效
  quote: str | null           # ≤ 500 字符引用
```

服务端校验: evidence_refs 至少 1 个; 每条 material_id 必须存在; hash 必须与 material.hash 匹配 (否则 422)。

### 5.3 状态机

```
draft ──publish──> published ──supersede──> superseded (新 judgment 取代)
                     │  ↑↓
                     │  retract
                     ▼
                  retracted
```

- publish 必须: evidence_refs 非空 + 至少 1 个 wiki_path 写过 (T11 后) + content_hash 与 claim 一致。
- supersede: 新 judgment 提供 `supersedes_judgment_id`; 旧 judgment 状态自动转 superseded, 写 wiki_event 链。
- retract: 必填 reason, 写 wiki_event; **不删**, 留审计。

### 5.4 allowed_actions

| status | actions |
|---|---|
| draft | `["edit", "publish", "discard"]` |
| published | `["create_supersede", "retract", "add_counter_evidence"]` |
| superseded | `["view_only"]` |
| retracted | `["view_only"]` |

### 5.5 关键不变量

- 同一 case 下, 同一 claim_type 的 published 判断**默认同时只允许 1 个**; 新 publish 必须 supersede 旧。
  (业务规则, 跨 case 不限; 用户可在 PR §6 之后裁决要不要放宽到 N 个并列)
- published 不可改 claim 文本; 改文本 = 创建新 revision = create_supersede。
- evidence_refs 永远不可改 (指向 Material 不可变快照)。

---

## 6. Action (行动)

### 6.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| case_id | str (Case.id) | ✓ | |
| judgment_id | str (Judgment.id) | ✓ | 行动基于哪个判断 (锁版本) |
| title | str | ✓ | |
| scope | str | | in/out |
| plan | str (Markdown) | ✓ | 计划内容 |
| plan_hash | str (sha256) | ✓ | plan 文本 hash |
| tool_versions | dict[str, str] | | 工具版本固定 (skill/dsh/pi) |
| expected_artifacts | list[str] | | 预期产物类型 |
| success_criteria | str | | 验收标准 |
| expires_at | str (ISO) | | 计划有效期; 过期触发复审 |
| status | enum[planned, approved, running, succeeded, failed, cancelled, rejected] | ✓ | 默认 planned |
| approved_by | str | | approved 状态时填 |
| approved_at | str (ISO) | | |
| revision | int | ✓ | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 6.2 状态机

```
planned ──approve──> approved ──start──> running ──finish──> succeeded
   │                     │                  │  ↑                ▲
   │                     │                  │ fail              │
   │                     ▼                  ▼                    │
   │                  rejected         failed ──retry──> approved
   │                     │                  │                    │
   │                     ▼                  └───cancel──> cancelled
   ▼                  cancelled
cancel ───────────────────────────────> cancelled
edit (任何非终态)
```

- start: 创建 Run (POST /api/runs with idempotency_key + action_id); Run 启动后 action.status 自动 running。
- fail → retry: 只能由 plan_hash 相同的 plan 重启; plan 改了 = 走 reject + 新 action。
- cancel: 任何非终态可取消; running 状态取消 = 给 Run 发 cancel 信号, action 等 Run 终止 (graceful) 后再转 cancelled。

### 6.3 allowed_actions

| status | actions |
|---|---|
| planned | `["approve", "reject", "edit", "cancel"]` |
| approved | `["start", "edit", "cancel", "revise_to_planned"]` (revise 仅 plan 微调) |
| running | `["cancel"]` (不能 edit) |
| succeeded | `["view_only", "create_followup"]` |
| failed | `["retry", "revise", "cancel"]` (revise = 改 plan) |
| cancelled | `["view_only", "create_followup"]` |
| rejected | `["view_only"]` |

### 6.4 关键不变量

- plan_hash 改了 → 必走 revise → reject → 重建 action; 不允许原地改 plan。
- 终态 (succeeded / cancelled / rejected) 不可改任何字段。
- expires_at 过期: 系统自动在 case 上加 blocker ("action 过期需复审")。

---

## 7. Run (执行运行)

### 7.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (`run_<ulid>`) | ✓ | |
| action_id | str (Action.id) | ✓ | |
| attempt | int | ✓ | 1, 2, 3... (失败重试计数) |
| skill_id | str | | 调用的 skill |
| protocol | enum[dsh, pi, direct, mock] | ✓ | 实际走的协议 |
| trigger_source | enum[user, agent, system, scheduled, webhook] | ✓ | |
| idempotency_key | str | ✓ | 客户端给的 |
| status | enum[queued, claimed, running, succeeded, failed, cancelled, timed_out] | ✓ | 默认 queued |
| inputs | dict | | 入参 (脱敏) |
| steps | list[Step] | | 执行步骤 (按序) |
| budget_tokens | int | | 预算 |
| budget_seconds | int | | 预算 |
| started_at | str (ISO) | | claimed 时填 |
| finished_at | str (ISO) | | 终态时填 |
| duration_ms | int | | 终态时填 |
| result_excerpt | str | | 前 4KB 结果 |
| error | str | | 失败时填 |
| artifact_ids | list[str] | | 产出的 Artifact |
| revision | int | ✓ | |
| created_at | str (ISO) | ✓ | |

### 7.2 Step 内嵌

```yaml
Step:
  seq: int
  tool: str                  # 工具名
  started_at: str (ISO)
  finished_at: str (ISO) | null
  input_hash: str
  output_hash: str | null
  status: enum[ok, error, skipped]
  error: str | null
  duration_ms: int
```

### 7.3 状态机

```
queued ──claim──> claimed ──step start──> running ──step end──> succeeded
   │                │                          │  ↑                ▲
   │                │                          │ fail              │
   │                ▼                          ▼                    │
   │             (lease 过期回收)            failed ──(人工或自动 retry)──> (新 Run, attempt+1)
   │                                            │
   └──cancel──> cancelled (终态)                └──cancel──> cancelled
                                                  └──timeout──> timed_out
```

- claim: worker 抢租, `lease_until` 字段 (数据库列, 不在 DTO); lease 过期未续约 → 服务端回收 → 重新可 claim。
- timeout: 超过 budget_seconds, graceful shutdown 后转 timed_out。

### 7.4 幂等

- 重复 `(idempotency_key, action_id)`:
  - body 完全相同 → 200 + 原 run_id + `replayed: true`。
  - body 不同 → 409 `E_CONFLICT`。
- 重复 `(action_id, attempt=N)` 同 attempt: 服务端 422 (每个 attempt 只能 1 个 Run)。

### 7.5 SSE 推送

- Run 状态变更全部进 SSE 流 (`/api/events?object=run`)。
- 客户端通过 Last-Event-ID 重放; 错过终态 → 服务端推 `resync_required`。

---

## 8. Artifact (产物)

### 8.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| run_id | str (Run.id) | ✓ | 产出本次运行的 Run |
| kind | enum[report, file, data, chart, code_patch, message, ...] | ✓ | 类型 |
| title | str | ✓ | |
| content_ref | str | | wiki 不可变 evidence path |
| content_hash | str (sha256) | ✓ | 内容 hash |
| format | enum[md, json, csv, png, ...] | ✓ | |
| size_bytes | int | ✓ | |
| verified_by | str | | 自动验证者 (CI 任务/工具) |
| verified_at | str (ISO) | | |
| verified_result | enum[pass, fail, warn] | | |
| accepted_by | str | | 业务验收人 |
| accepted_at | str (ISO) | | |
| accepted_note | str | | |
| status | enum[pending, verified, accepted, rejected, superseded] | ✓ | 默认 pending |
| revision | int | ✓ | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 8.2 状态机

```
pending ──verify──> verified ──accept──> accepted
   │                   │  ↑                ▲
   │                   │ verify_fail       │
   ▼                   ▼                    │
rejected ←────── (verified)                  │
                  ──supersede──> superseded │
                                    │       │
                                    ▼       │
                              (新 Artifact 接受 = 旧 superseded)
```

- reject 后再 verify: 不允许 (必须新 run → 新 artifact); 旧 artifact 保留作审计。
- supersede: 同 action 下的 artifact 被新版本取代; 旧 status 转 superseded。

### 8.3 关键不变量

- 拒绝 (rejected) 后, 不能用同 content_hash 重新接受 (防"重传蒙混"); 必走新 Run。
- `accepted` 是终态; 撤销接受走 supersede + wiki_event, 不删记录。

---

## 9. Knowledge (经验)

### 9.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | str (ULID) | ✓ | |
| kind | enum[principle, pattern, anti_pattern, reference, playbook, checklist] | ✓ | |
| title | str | ✓ | |
| body | str (Markdown) | ✓ | 经验正文 |
| prerequisites | list[str] | | 前提条件 |
| counter_examples | list[str] | | 反例 |
| evidence_refs | list[EvidenceRef] | | (同 §5.2) |
| expiry_at | str (ISO) | | 经验有效期; null = 长期 |
| review_at | str (ISO) | | 下次复查时间 |
| reuse_count | int | | 累计复用次数 (派生, 不存) |
| last_reused_at | str (ISO) | | (派生) |
| status | enum[draft, published, deprecated, retracted] | ✓ | 默认 draft |
| revision | int | ✓ | |
| wiki_path | str | | 不可变 Markdown revision path |
| content_hash | str (sha256) | | |
| published_at | str (ISO) | | |
| created_at | str (ISO) | ✓ | |
| updated_at | str (ISO) | ✓ | |

### 9.2 状态机

```
draft ──publish──> published ──deprecate──> deprecated
                     │  ↑↓                     │
                     │  retract                ▼
                     ▼                    (review_at 触发复审)
                  retracted
```

- deprecate: 必填 reason + 建议替代 knowledge_id (可空)。
- 过期 (review_at 到期): 自动在 related case 上挂 blocker ("knowledge 复查"), 不改 status。
- retract: 同 Judgment.retract 语义, 必填 reason。

### 9.3 allowed_actions

| status | actions |
|---|---|
| draft | `["edit", "publish", "discard"]` |
| published | `["create_revision", "deprecate", "retract"]` |
| deprecated | `["revive"]` (转回 published, revision+1) |
| retracted | `[]` (终态) |

### 9.4 复用记录 (ReuseReceipt)

- 不在 knowledge 主表; 派生自"被 judgment 引用次数" + "被 action 引用次数"。
- `GET /api/knowledge/{id}/reuse` 返回 `{total, by_judgment, by_action, recent_30d}` 聚合, 服务端派生。

---

## 10. 跨对象约束

### 10.1 ID 引用

- 所有 ID 引用服务端校验存在; 不存在 → 422 `E_VALIDATION` (引用未发表), 404 (引用已删)。
- 引用修订: 引 judgment/action 写 `judgment_id` 时记录当时 `judgment_revision` (脱敏字段 `_linked_revision`); 不匹配 → 409 `E_CONFLICT` "judgment 已升级, 请重新发布行动"。

### 10.2 时间一致性

- 任何 created_at 早于 2020-01-01 或晚于 now+1h → 服务端 422 (防日期乱填)。
- updated_at ≥ created_at (DB 层 CHECK 约束)。

### 10.3 删除语义

- 任何已引用对象 (subject / material / judgment / knowledge) **不删**, 只能 archive/retract/supersede。
- 未引用对象 (零 case 引用) 可 hard delete (admin only, 写 audit log)。

### 10.4 字段 schema 漂移

- codegen 脚本 (T03-C) 同时生成 `backend/domain/v1_0_models.py` + `frontend/src/domain/v1_0.ts`, CI 比较 schema hash。
- 任何字段/枚举/状态字符串改动必须同时改: Pydantic + codegen + CI 漂移检查基线。
- 改字 (rename) = breaking change, 必须发 v1.0.x 重大版本, 在 CHANGELOG 标 BREAKING。

---

## 11. 待 T03-C 落地

1. 把 §1-§9 全部枚举提取为 Python `Enum` 集合, 生成单文件 `backend/domain/v1_0_models.py`。
2. codegen 脚本读 Pydantic → 写 TS; TS 文件 `frontend/src/domain/v1_0.ts` 单文件单类型导出。
3. CI 加 `python scripts/codegen_v1_ts.py --check` 步骤, drift → exit 1。
4. `frontend/src/domain/v1_0.ts` 是前端**唯一**导入域类型来源; lint 禁止从 Pydantic 镜像路径 (老 schema) 导入。

---

## 12. 引用

- [HOTSPOT_WORKSTATION_PRD_V1.0.md §4](../archived/2026-09-09-sweep/HOTSPOT_WORKSTATION_PRD_V1.0.md) — 9 域对象
- [HOTSPOT_V1.0_DEVELOPMENT_PLAN.md §5](../archived/2026-09-09-sweep/HOTSPOT_V1.0_DEVELOPMENT_PLAN.md) — 5.1/5.2/5.4 约束
- [task-status.md](task-status.md) — T03 任务台账
- [backup-drill.md](backup-drill.md) — T02 备份/恢复/开发副本
