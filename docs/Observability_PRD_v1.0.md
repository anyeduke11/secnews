# Observability PRD v1.0 — 系统可观测性完整方案

> **状态**: design (待评审 → 分批实施)
> **日期**: 2026-08-30
> **范围**: LLM 配置前端切换 (ollama + 云端) / 大模型接口观测 / 功能服务接口观测 / 执行记录 / 告警与看板
> **前置阅读**: 根 `AGENTS.md` (Feature Gates / core 边界)、`PROGRESS.md` (v0.6.3 卡顿教训)、`backend/services/AGENTS.md` (ai_hub 唯一性)

---

## 0. 一句话目标

把"AI 是否真在工作、系统是否真健康、谁在什么时候做了什么"从**进程内存口**升级为**持久化、可追溯、前端可见**的三位一体观测面，并在此之前补齐 LLM 配置的前端切换能力（ollama 与云端并存）。

---

## 1. 现状审计（摸底结论，含证据）

### 1.1 LLM 层

| 事实 | 证据 |
|---|---|
| ai_hub 是唯一 LLM 出口，四类 provider 调用全走 httpx 直连 | `backend/services/ai_hub/gateway.py:254-291` (`_call_provider` 四支)、`service.py:226-279` |
| 双引擎: `LLMService`（生成类，走 fallback 链）+ `AIService`（evaluate/gate_detect，单点选择） | `gateway.py:41`、`service.py` |
| 配置唯一事实源 = 仓库根 `config/llm.yaml`（providers/fallback_order/task_overrides），**不进 DB，无写端点** | `backend/config/llm_schema.py:84-103`、`config/llm.yaml` |
| **llm.yaml 在进程启动时一次性加载**（模块级单例），改配置必须重启 | `gateway.py:52-64` |
| provider 解析链: `AI_PROVIDER` env > model_router(task_overrides) > default_provider | `service.py:90-109`、`services/llm/model_router.py:106-128` |
| ollama 已真实支持（/api/generate、/api/chat），健康检查仅探活 `/api/tags` **不解析模型列表**，模型名写死 yaml | `gateway.py:293-320`、`service.py:122-138` |
| 前端无全局 provider 切换 UI；唯一的 provider 下拉只影响质量门禁 settings | `frontend/src/components/settings/QualitySettings.tsx:216-241` |
| 密钥双轨互不联通: 运行时走 `.env`→env 变量（`api_key_env`），`llm_secrets` 表是独立前端密钥库，**ai_hub 运行时不读它** | `gateway.py:423-432`、`secrets_service.py:528`（`decrypt_for_internal_use` 唯一消费者是 codegarden_github） |
| egress 凭据外发白名单是硬闸门，新增云端 provider 必须同步改代码 | `ai_hub/egress.py:23-28` |

### 1.2 可观测性现状（v0.6.3 P3-3 之后）

| 已有 | 证据 |
|---|---|
| loguru JSON 日志 + `X-Trace-Id` 中间件（api_request/api_response 事件） | `logging_config.py:38-99`、`api/middleware.py:27-81` |
| `/api/llm/status` observability 块（recent_calls/recent_errors/success_stats） | `api/llm_status.py:17-56` |
| llm_usage_log 表（仅成功调用） | `migrations/052_v1.7_llm_cache.sql:20-33` |
| /api/health（db/scheduler/cache/collectors/proxy 五组件）+ /api/stats | `api/health.py:223-352` |
| SSE `/api/events`（job_done/collect_done/task_done/extract_done/alert/review_due） | `api/events.py` |
| KL 管线观测: funnel/token_ledger/kl_dead_letters/kl_metrics（进程内） | `api/kl_pipeline_api.py:117-153`、`backend/metrics/kl_metrics.py` |
| CodeGarden 服务拓扑/日志/指标/重启（docker 实时探测，无历史采样） | `services/codegarden_service_service.py:530-628` |

### 1.3 七大缺口（本方案逐一对付）

1. **LLM 失败不落库** — 只进进程内 `deque(50)` 错误环，重启清零；成功率口径="本进程窗口"（`ai_hub/usage.py:22-24,69-77`）
2. **latency_ms 恒 0、tokens 为 len//4 估算** — 无法回答"LLM 慢不慢/贵不贵"（`usage.py:91-93,101,124`）
3. **全链路无 task_id/trace_id 贯穿** — llm_usage_log 无关联键，一次 digest 生成串不起 job→LLM 调用
4. **无通用 job 执行历史** — 仅 collection_runs/catchup_runs/crawler_runs 三类专用表，其余 ~40 job 失败只 log.error（`jobs/_runtime.py:55-87`）
5. **agent/pi/dsh 执行零记录** — `/api/agents/run` 只回一次性信封不落库；ProcessSupervisor 纯内存重启即丢（`agent_bridge.py:135-214`、`process_supervisor.py:68-74`）
6. **日志 JSON 模板丢 extra 字段** — 结构化字段只存在于 stderr 文本，app.log 里 method/path/status 全丢（`logging_config.py:19-25`）
7. **无写操作审计** — 除 secret_access_logs 外无 audit log；LLM 配置、dsh 启停、settings 写入无痕

---

## 2. 目标与非目标

**目标**

- G1 前端可完成 LLM 配置切换：选 provider（ollama / sensenova / qwen / openai / anthropic / 自定义 compatible）、配 ollama base_url 与模型（在线发现）、配云端密钥、调任务档位与 fallback 顺序，**保存即生效（免重启）**
- G2 每次 LLM 调用（成功+失败）持久化：真实耗时、真实 tokens（可取时）、trace_id、业务场景、provider 解析来源
- G3 API 层每路由调用量/延迟/错误可聚合查询，慢请求与 5xx 有明细
- G4 全部 scheduler job、agent/pi/dsh 运行、敏感写操作有持久化执行记录
- G5 观测看板页：LLM / 服务接口 / 执行记录三视图，SSE 实时 + Toast 告警
- G6 性能红线：观测写入**永不**进入事件循环同步路径（v0.6.3 卡顿教训：`PROGRESS.md` P0-1/P3-1）

**非目标**

- 不引入 OTel Collector / Prometheus 等外部重依赖（单机单进程系统）；日志字段命名向 OTel 对齐，保留将来导出能力
- 不记录请求/响应全文（体积与敏感信息）；只记摘要与元数据
- 不做分布式追踪（进程 + 子进程边界即到头，用 trace_id 关联即可）
- SSE 不做 replay（观测页以拉取为主，SSE 只做增量刷新提示）

---

## 3. 总体架构（五层）

```
┌─ 呈现层  /secnews/observability 三视图 + LlmProviderCard + StatusBar 灯 + Toast
├─ 查询层  /api/obs/* (observability_api) + /api/llm/config|test|ollama/models (llm_config_api)
├─ 聚合层  observability_service.py — 聚合查询 + 告警评估 + TTL 清理
├─ 存储层  llm_usage_log(加列) + 新表 job_runs/agent_runs/process_events/audit_log/
│          api_events/api_metrics_hourly + settings KV(llm.config 等覆盖层)
└─ 采集层  4 个埋点边界（不逐 service 埋点）:
     ① HTTP 中间件 (扩展现有 TraceIDMiddleware)
     ② ai_hub 出口 (gateway + AIService 的统一记录点)
     ③ job 边界 (instrument_job)
     ④ agent/dsh 边界 (agent_bridge + ProcessSupervisor 钩子)
```

原则：**三大采集边界（HTTP 入口、LLM 出口、job/agent 边界）覆盖 90% 观测需求**，service 内部仍用既有 `log_event`（`backend/observability.py:43-60`）补充，不为 81 个 service 逐个埋点。

---

## 4. Workstream A — LLM 配置前端切换（G1，观测的前置）

### 4.1 配置模型与优先级

引入 **settings KV 覆盖层**（沿用 dsh 配置先例 `dsh.endpoint/dsh.command`，`services/dsh/supervisor.py:46-76`）：

```
生效配置 = llm.yaml (基线) ⊕ settings["llm.config"] (覆盖层, JSON)
字段级覆盖: enabled / default_provider / fallback_order / task_overrides
           / providers.<name>.base_url / providers.<name>.models.* / allowed_hosts
优先级:    settings KV > AI_PROVIDER env（保留，调试用）> llm.yaml > 代码默认
```

- 新模块 `backend/services/ai_hub/runtime_config.py`：`get_effective_config()` 返回合并快照 + 各字段来源标注（`yaml|override|env`）；进程内缓存 + 版本号失效（写入时 invalidate + 30s TTL 兜底）。
- `LLMService.config` 从"启动时快照"改为访问合并快照（`gateway.py:56` 的 `self._config` 改为 property 或注入 resolver）；`AIService`、`model_router` 同源。**llm.yaml 仍是仓库真理，settings KV 只做运行时覆盖**，看板提供"重置为 yaml 默认"按钮。

### 4.2 密钥策略（双轨统一，带安全降级）

- 前端配置的云端密钥 **写入 `llm_secrets` 表**（provider 列已就绪，`migrations/074`），运行时解析链改为：
  `llm_secrets（解锁且含该 provider 密钥）→ os.environ[api_key_env] → 无凭据`
- `gateway._get_api_key` / `AIService._resolve_api_key`（`gateway.py:423-432`、`service.py:111-119`）接入该链，并在 llm_calls 记录 `key_source`（secrets|env|none）。
- **降级契约（对应主密钥丢失未决问题）**：`llm_secrets` 未解锁/主密钥不可用时，UI 将 env 来源密钥显示为"来自环境变量 · 只读"，写入路径禁用但不阻塞 env 通道。主密钥恢复前不重置（Q1 禁重置约束不变）。

### 4.3 API 契约（新路由 `backend/api/llm_config_api.py`）

| 端点 | 行为 |
|---|---|
| `GET /api/llm/config` | 合并视图：effective config + 每字段 source 标注 + 密钥存在性掩码（永不回显明文） |
| `PUT /api/llm/config` | schema 校验（复用 `llm_schema.ProviderConfig`）→ egress 校验 → 写 settings KV（+密钥入 llm_secrets）→ invalidate 缓存 → 返回生效预览 |
| `POST /api/llm/config/test` | 用给定 provider/model 发一次最小 generate（"ping"），返回 latency/tokens/error；**记入 llm_usage_log，scene=config_test** |
| `GET /api/llm/ollama/models?base_url=` | **新增模型发现**：GET `{base}/api/tags` 解析 `models[].name` 返回列表（补齐现状只探活不解析的缺口，`service.py:122-131`） |
| `POST /api/llm/providers/{name}/health` | ollama→实测 /api/tags；云端→返回最近滑动窗口成功率（不主动打 API 省额度） |

- egress 动态白名单：`TRUSTED_LLM_HOSTS ∪ settings["llm.allowed_hosts"] ∪ 本地地址（type=ollama 豁免不变，`egress.py:14-15`）`；PUT 时非白名单 host 直接 422，UI 明示"放行=允许凭据发往该主机"。
- 现有 `GET /api/llm/status` 保留不动（两个消费方 `PipelineSettings.tsx:43`、`SentinelSettingsPage.tsx:288` 不破坏），其 observability 块在批次①后升级为持久化口径。

### 4.4 前端 UI

- `PipelineSettings.tsx` 的"模型档位"卡片从硬编码只读（`:115-126`）改为 **LlmProviderCard**（新组件）：
  - 默认 provider 下拉（含 ollama）；选 ollama → base_url 输入 + "测试连接" + 模型下拉（在线发现填充）
  - 选云端 → 密钥输入（写 llm_secrets，掩码回显）或"来自环境变量 · 只读"
  - 任务档位矩阵：3 档（FLASH/STANDARD/HEAVY ↔ t3_chunk_summary/t1_score/t3_summary，`model_router.py:63`）各选 provider+model+max_tokens
  - fallback 顺序：复选 + 上下调序
  - "保存并生效" / "发送测试请求" / "重置为配置文件默认"
- 交互反馈走 Toast（`components/Toast.tsx` 已实现零使用的现状就此终结）；SecretsPage 三处 `window.prompt` 主密钥输入改用现成 `Modal.tsx`（顺带修复，同批次）。

---

## 5. Workstream B — 大模型接口可观测性（G2）

### 5.1 数据模型（迁移 `078_observability_llm.sql`）

`llm_usage_log` 加列（保留旧列兼容，TokenLedger 等既有消费方不受影响）：

```
ok            INTEGER DEFAULT 1      -- 0=失败（此前失败不落库的缺口①）
error         TEXT                   -- 失败摘要[:300]
latency_ms    REAL                   -- 开始写真值（此前恒 0，缺口②）
prompt_tokens INTEGER / completion_tokens INTEGER   -- 可取响应 usage 时用真值
trace_id      TEXT                   -- 关联键（缺口③）
scene         TEXT                   -- 业务场景: t1_score|t3_summary|digest|deep_read|gate_detect|config_test|agent_builtin
config_source TEXT                   -- provider 解析来源: task_override|router|fallback|default
key_source    TEXT                   -- secrets|env|none
索引: (occurred_at), (provider, task, occurred_at), (ok, occurred_at)
```

### 5.2 埋点：统一记录入口

`usage.py` 新增 **`record_llm_call()` 单入口**，替换现散落的 `log_llm_usage`/`log_ai_usage`（注意第三个写入方 `services/cost_monitor.py:68` 一并迁移）：

- 调用点收敛为 6 处 provider 分支的 **finally**（`gateway.py` 四支 + `service.py` 两支）——成功失败都记；
- latency 用 `time.perf_counter()` 真实计时；
- tokens：openai_compatible/openai 从响应 `usage` 取；ollama 从 `prompt_eval_count/eval_count` 取；取不到再按 len//4 估算并标记 `tokens_estimated=1`；
- 失败路径同时保留进程内错误环（`record_llm_error` 不删，作为热路径告警源）。

### 5.3 trace_id 贯穿（缺口③）

`backend/observability.py` 增加 **contextvar** 方案：

```
current_trace_id(): request 中间件 set（已有 request.state.trace_id, middleware.py:36）
                  → job 上下文 set（instrument_job 注入 job:<job_id>:<ts>）
                  → agent 上下文 set（agent_bridge 注入 agent:<agent>:<ts>）
                  → 否则 None（落库时允许 NULL）
```

效果：一次"生成每日日报"可从 job_runs 行 → 多条 llm_calls 行 → 触发的 api_events 全链关联。

### 5.4 查询与口径升级

- `GET /api/obs/llm/calls?limit&provider&task&ok&since` — 明细（含失败）
- `GET /api/obs/llm/summary?window=24h` — 按 provider×model×task 聚合：calls/ok_rate/p50/p95 latency/tokens/cost（SQLite 查询时聚合；本地单机 7 天明细 <1e4 行，**不做预聚合表**，避免过度设计）
- `/api/llm/status` observability 块升级：`recent_errors` 与 `success_rate` 改读 DB 持久窗口（诚实口径从"进程窗口"升级为"24h 真实窗口"），响应结构向后兼容。

---

## 6. Workstream C — 功能服务接口可观测性（G3）

### 6.1 日志修复（缺口⑥，小改动大收益）

`logging_config.py:19-25` 的 JSON serializer 把 `record["extra"]` 并入输出行（现在只挑 5 个固定字段）。修完 `api_request/api_response` 的 method/path/status/duration_ms 才真正落 app.log。

### 6.2 每路由指标（进程内计数 + 定期快照）

- 仿 `backend/metrics/kl_metrics.py` 模式新增 `backend/metrics/api_metrics.py`：按 `(method, path_template, status_class)` 的 counter + 延迟直方图；`path_template` 取 `request.scope["route"].path`（避免记具体 id 造成基数爆炸）。
- 快照：复用一个 5min maintenance job 把窗口聚合写入 `api_metrics_hourly(hour_bucket, method, path, calls, errors, duration_sum, duration_max)`。

### 6.3 慢/错请求明细（迁移 `079` 之 `api_events` 表）

中间件在 `status>=500 或 duration_ms>=SLOW_MS(默认500, settings["obs.slow_ms"] 可调)` 时写 `api_events(trace_id, method, path, status, duration_ms, error, at)`，TTL 7 天。正常请求**不落库**（本地系统无需全量访问日志）。

---

## 7. Workstream D — 执行记录（G4）

### 7.1 通用 job 历史（缺口④，迁移 `079` 之 `job_runs`）

```
job_runs(job_id, started_at, finished_at, status ok|failed, duration_ms, error, trace_id)
索引: (job_id, started_at), (status, started_at)   TTL: 30 天
```

- 改造 `instrument_job`（`jobs/_runtime.py:55-87`）：进入写 running 行（拿 trace_id）、finally 更新状态——成功失败都落库；SSE `job_done` 行为不变。
- job 清单继续复用 `/api/health` 的 scheduler 组件（`health.py:139-158`），历史由 job_runs 补全。

### 7.2 agent / pi / dsh 执行记录（缺口⑤）

```
agent_runs(agent, protocol, task_kind, trigger api|scheduler, ok, status,
           duration_ms, result_excerpt[:500], error, trace_id, started_at)  TTL 30 天
process_events(name, event spawn|exit|restart|stop_requested|crash, pid, uptime_s,
               exit_code, detail, at)                                        TTL 14 天
```

- `agent_bridge.run_agent_task`（`agent_bridge.py:135-214`）：两条通道（外部 CLI 子进程 / builtin→ai_hub）结束都落 `agent_runs`；trace_id 注入后，builtin 的 LLM 调用自动关联。
- `ProcessSupervisor` 增加 on_event 钩子（spawn/exit/restart），`dsh/supervisor.py` 与 dsh control 五端点的 start/stop/restart 操作同步记 `process_events`。
- 已有的结果信封响应结构不变（前端 AgentRunnerCard 不破坏）。

### 7.3 写操作审计（缺口⑦，`audit_log` 表）

```
audit_log(actor web|system|agent:<name>, action, target, detail JSON, trace_id, at)  TTL 90 天
```

埋点端点清单（首批）：`PUT /api/llm/config`、`POST /api/llm/config/test`、`/api/dsh/control/{start,stop,restart,config}`、`/api/settings/*` 写、secrets 的 reveal/rotate（与既有 `secret_access_logs` 并存，后者不动）。

### 7.4 不重建清单（已有持久化记录，看板只做聚合展示）

`collection_runs` / `catchup_runs` / `crawler_runs` / `kl_queue` / `kl_dead_letters` / `token_ledger` / `wiki_events`（kind=agent_write|cli_agent_run）/ `quality_check_logs` / `cg_events` / `alert_events` / `deep_reads`。

---

## 8. 告警设计

复用 `alert_events` 表 + SSE `alert` 事件类型（`alert_service.py:195` 已有发布通道），前端 Toast 消费。规则（settings["obs.alerts"] 可调，内置默认）：

| 规则 | 阈值 | 评估时机 |
|---|---|---|
| LLM 连续失败 | 同 provider 连续 ≥3 次 | `record_llm_call` 失败路径内联评估（实时） |
| LLM 成功率 | 最近 20 次 < 0.8 | 内联 + 5min job 兜底 |
| job 连续失败 | 同 job_id 连续 ≥2 次 | `instrument_job` finally |
| API 5xx 突增 | 5min 内 ≥10 | api_metrics 快照 job |
| ollama 离线但被选为首选 | tags 探测失败且 fallback 实际发生 | 内联（落 fallback 时） |

告警写入 `alert_events` + `publish_event("alert", ...)`，**节流**：同规则 60s 内只发一次 SSE。

---

## 9. 前端看板（G5）

- 新视图 **`/secnews/observability`**（secnews 第七个子路由，`routes/index.tsx:109-117` + `lazy-imports.ts` 同步）：
  - **LLM 视图**：summary 表（仿 `TokenLedger.tsx` 样式）+ 成功率/延迟趋势（echarts）+ calls 明细表（ok/error/latency/trace_id/scene，可按 provider/task 过滤）+ config_source 标注
  - **服务接口视图**：每路由表（calls/errors/avg/p95）+ 慢/错请求明细 + 5min 窗口 5xx 计数
  - **执行记录视图**：jobs 表（最新状态/失败率，点击展开最近 runs）+ agent_runs + process_events 时间线 + audit_log
- **StatusBar**（`secnews/layout/StatusBar.tsx`）加 LLM 状态灯：绿(成功率≥0.9)/黄(0.5-0.9 或发生 fallback)/红(<0.5 或连续失败)，悬停显示最近错误；30s 轮询既有基线。
- **SSE/Toast 接线**：`useSSE.ts` 新增消费 `job_failed`/`alert`/`llm_call_failed`（节流后）→ Toast 通知 + 观测页即时刷新。
- 技术约定：Tailwind + CSS 变量 token、中文文案、组件与测试并置（`Foo.tsx`↔`Foo.test.tsx`）；**实施前按根 AGENTS.md 走设计技能路由（存量 UI 改造 → redesign-existing-projects）**。

---

## 10. 数据保留与性能红线

| 表 | TTL | 清理方式 |
|---|---|---|
| llm_usage_log 明细 | 7 天 | 现有 maintenance job 追加删除段 |
| api_events | 7 天 | 同上 |
| job_runs / agent_runs | 30 天 | 同上 |
| process_events | 14 天 | 同上 |
| audit_log / api_metrics_hourly | 90 天 | 同上 |

性能红线（每条都有 v0.6.3 的教训背书）：

1. 所有观测写 API 端点 **`def`（线程池派发）**，禁止 `async def` 内同步 SQLite（P3-1：14 个 async 端点 RAW 阻断已全改，新代码不得回退）；
2. 埋点失败**永不**影响主流程——记录函数全部 try/except 吞错（沿用 `usage.py:105-106` 的防御风格）；
3. 中间件每请求只做内存计数，DB 写仅限慢/错请求；
4. 聚合查询走索引 + LIMIT，看板默认窗口 24h。

---

## 11. 实施批次（每批独立可交付、独立 commit，显式 pathspec）

| 批次 | 内容 | 交付判据 |
|---|---|---|
| ① 观测地基 | 迁移 078/079 + `record_llm_call` 统一（真实 latency/tokens/trace_id）+ trace contextvar + logging extra 修复 + `instrument_job`/`agent_bridge`/ProcessSupervisor 落库 + TTL 清理 | 重启后失败调用仍可见；`latency_ms` 非 0；一次 digest 的 job_runs↔llm_calls 同 trace_id |
| ② LLM 配置切换 | runtime_config 覆盖层 + `/api/llm/config*` 四端点 + ollama 模型发现 + 密钥接入 llm_secrets（含 env 降级）+ egress 动态白名单 | 前端切 provider 后**免重启**下一次调用生效；非白名单 host 422；config_test 有记录 |
| ③ API 观测 | api_metrics 进程内指标 + 5min 快照 + api_events 慢/错落库 | 看板能回答"哪个路由最慢/5xx 有多少" |
| ④ 看板与告警 | `/secnews/observability` 三视图 + LlmProviderCard + StatusBar 灯 + SSE/Toast + 告警规则 | 三视图数据齐；Toast 真实生效；告警节流 |
| ⑤ 收尾 | `/api/llm/status` 持久口径升级 + SecretsPage prompt→Modal + generate_meta 同步 + CHANGELOG | `generate_meta.py --check` 过；docs Swagger 列新路由 |

每批门禁：`pytest backend/tests/`（基线 3035+新增）+ `ruff check backend/` + 前端 `tsc --noEmit` + `vitest run`（基线 310+新增）+ `vite build` + `python scripts/generate_meta.py --check`。

## 12. 测试设计（新增用例锚点）

- `test_llm_observability.py`：ok/error 双路径落库、latency 真值、ollama usage 真值解析、trace_id 传播（中间件/job/agent 三源）、config_test scene
- `test_llm_config_api.py`：GET 合并视图 source 标注、PUT 写 KV+invalidate（下一次 resolve 生效）、egress 422、ollama models mock、密钥 env 降级
- `test_job_runs.py` / `test_agent_runs.py`：成功/失败/异常三路径、process_events 钩子
- `test_observability_api.py`：三视图端点契约 + TTL 清理
- 前端：`LlmProviderCard.test.tsx`、`SecNewsObservability.test.tsx`

## 13. 风险与开放问题

1. **主密钥丢失未决** → 批次②密钥 UI 必须 env 只读降级；`llm_secrets` 写路径在恢复前保持禁用（`llm-secrets-master-key-lost` 备忘）。
2. **settings KV 与 llm.yaml 漂移** → GET 带 source 标注 + "重置为文件默认"；llm.yaml 注释指向本 PRD，避免后人困惑两处配置。
3. **egress 动态白名单边界** → 仅本机受信操作者经 UI 放行；不放行"任意 host"通配；UI 明示凭据外发风险。
4. **并行会话 git 纪律** → 每批 `git commit <显式路径>`，绝不 `git add -A`（历史事故备忘）。
5. **SSE 无 replay** → 观测页首屏一律拉取，SSE 仅作刷新触发。
6. **视觉前置** → 批次④动 UI 前先走 redesign-existing-projects 设计技能路由。
