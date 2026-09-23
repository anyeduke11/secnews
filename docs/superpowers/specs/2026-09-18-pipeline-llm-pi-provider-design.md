# 设计：采集管线 LLM 能力 pi 化 + 补齐（方案 B）

- 日期: 2026-09-18
- 状态: 已批准（用户裁决：范围=管线 pi 化+补齐 / 路径=ai_hub pi provider / 补齐三项全做 / 方案 B；裁决点：NER 落 `knowledge_items.entities`、语义门禁用**独立 verdict-only prompt**）
- 关联: `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`（单一权威 PRD，实现前须同步）

## 1. 背景与目标

采集管线当前唯一 LLM 消费点是 t1 打分（`triggers/t1_raw_to_refine.py::_score_with_llm` → `ai_hub.score`）。pi（pi.dev，earendil-works agent harness）在本仓已有 agent_bridge 通道（`config/agents.yaml` pi runner，2026-09-05 实测对齐 pi 0.84.4 NDJSON 协议），但未接入 ai_hub。

目标：
1. pi 成为 ai_hub 第 5 种 provider type，享受既有 fallback/健康窗口/熔断/背压/usage 记账
2. 补齐三项管线 LLM 能力（全 feature gate 默认关）：语义门禁、智能分类增援、NER 实体抽取
3. agent_bridge 通道同步注册 score/classify/ner，dsh 与手动任务可路由

## 2. 总体架构（双通道统一）

```
管线 LLM 任务 ──────────► ai_hub gateway ──► pi provider（新增）
                            (score/summary/     │ 子进程 pi -p --mode json
                             ner/generate)      │ NDJSON 解析（与 agent_bridge 共享纯函数）
dsh / 手动任务 ──────────► agent_bridge ──────┘
                            (task_type=score/classify/ner)
```

红线：ai_hub 仍是唯一 LLM 出口；pi 以 provider 身份进入，不开旁路。agent_bridge 仅扩注册表，不改执行模型。

## 3. pi provider 实现（ai_hub 最小侵入，3 处改动）

### 3.1 llm_schema.py
`ProviderConfig.type` Literal 扩 `"pi"`。pi 认证由 `~/.pi/agent/auth.json` 管理 → 不要求 `api_key_env`；无 `base_url` 语义。

### 3.2 gateway.py `_call_provider`
新增 `elif cfg.type == "pi"` 分支 → `_call_pi(cfg, model, prompt)`：

- 同步子进程 `pi -p --mode json [--model <model>]`，**prompt 经 stdin 传入**（防 ARG_MAX / 注入）；model 为空则不下传 `--model`（用 pi 默认上游）
- `asyncio.to_thread` 包裹进 async 上下文（其余分支为 httpx async）
- NDJSON 解析抽为共享纯函数：从 `agent_bridge._parse_jsonl_events` 提取"事件流 → 最终文本 + stopReason"纯解析部分到独立模块（放 `backend/services/ai_hub/pi_transport.py`），agent_bridge 反向 import 复用，**禁止两处实现**。既有语义保留：role=="user" 事件跳过；stopReason=="error" → raise → 健康窗口/熔断记账自动生效
- 超时：subprocess timeout 用 `cfg.timeout_seconds`
- 并发：复用 `get_semaphore(f"llm:{provider_name}")` 既有背压

**明确不做**：`_call_provider_chat` 不加 pi 分支（Unsupported → fallback 链自动跳下一 provider；deep_read 等 chat 场景继续走既有 provider）。

### 3.3 llm.yaml 示例（文档注明，用户自行启用）

```yaml
providers:
  pi:
    type: "pi"
    models: {score: "", ner: "", summary: ""}   # 空 = pi 默认模型
    timeout_seconds: 60
    max_concurrent: 2
```

### 3.4 agents.yaml
pi runner `task_types: [execute]` → `[execute, score, classify, ner]`。

## 4. 三新能力（全 feature gate 默认关）

### 4.1 语义门禁 — 新 gate `semantic_filter`

- 挂点：`info_filter_gate.filter_items` 内，规则 **neutral**（未命中 deny/allow）的 item → LLM verdict-only 判别 → `reject` 则 drop
- **独立 verdict-only prompt**（用户裁决，不复用 evaluate_article）：
  - `ai_hub/prompts.py` 新增 `_build_semantic_verdict_prompt(content)` → 要求 JSON `{verdict: "allow"|"reject", reason: string}`
  - `ai_hub/tasks.py` 新增 `semantic_verdict(content) -> dict`：走 gateway `generate` 通用漏斗（`task="semantic_filter"`）+ 容错 JSON 解析（沿用 `_parse_eval_json` 风格）；解析失败/异常 → 返回 allow（fail-open，不因门禁故障丢内容）
  - 模型选择：计划阶段核实 `generate` 的 task→model 解析；若不支持任务级 override，则 `ProviderModels` 增 `semantic_filter: str = ""` 字段 + 空值回退 summary 模型
- gate 独立于 `info_filter`（规则层默认开 / 语义层默认关，互不牵连；各自 `_is_enabled()`）
- 同步链路用 `asyncio.run` 包裹（与 t1 `_score_with_llm` 同款既有模式）
- 成本护栏：仅 neutral item 触发；verdict 结果不落 ai_scores（非打分语义，避免语义混杂）

### 4.2 智能分类增援 — 新 gate `ai_classify`

- `auto_classifier.classify_item` 纯函数契约**不动**（测试依赖 + 代码注释明确 no-LLM）
- 同文件新增 `classify_item_with_ai(tags, title, source_url)`：先跑纯规则；`domain` 为 None 时 → `llm_service.generate` 分类 prompt（受限 domain 枚举 + JSON `{domain, type, difficulty}` + 容错解析）→ 任何失败兜底回退纯规则结果
- 消费方（采集落库链）按 gate 决定调哪个入口

### 4.3 NER 实体抽取 — 新 gate `pipeline_ner`

- **ai_hub 零改动**：`gateway.extract_entities`（L350，`_try_order("ner")` + `_resolve_model("ner")`）已完整存在，采集域此前无消费
- 挂点：`t1_raw_to_refine` score 成功后 → `extract_entities(content)` → 落 `knowledge_items.entities`（JSON 数组字符串，用户裁决）
- 新迁移 1 个：`backend/repository/migrations/nnn_item_entities.sql` 加 `entities TEXT` 列（可空）
- 本任务只落库；下游检索/链接消费不在范围

## 5. feature_gates 登记

`backend/config/feature_gates.toml` 新增 `semantic_filter` / `ai_classify` / `pipeline_ner`，**全部默认 false**；gate 随消费点同登记（user_skills 先例）；conftest autouse 全开 fixture 自动覆盖新 gate。

## 6. 前端

- ProviderPanel 读 `/api/llm/status`，pi provider 出现后自动展示；若 status 接口按 type 白名单渲染，补一行标签（计划阶段核实）
- 三 gate 不加 UI 开关，走 toml + `HOTSPOT_FEATURE_GATES` env 覆盖

## 7. 测试策略

| 层 | 用例 |
|---|---|
| 单测 | NDJSON 共享解析纯函数（user 过滤 / stopReason=error / 空流）；llm_schema 接受 `type: "pi"`；`_call_pi`（mock subprocess：stdin 收 prompt、--model 条件下传、超时 raise）；`semantic_verdict` 容错解析 + fail-open；`filter_items` neutral→verdict→drop 全链（mock LLM）；`classify_item_with_ai` 规则 miss 增援 / LLM 失败兜底；t1 NER 落库（迁移后列存在） |
| 回归保证 | 3 gate 全关时行为与现状一致；`test_feature_gates.py` 组合矩阵补 3 gate |
| 命令 | `pytest backend/tests/ -k "pi or semantic or classify or ner"` → 全量 `pytest backend/tests/` → `py_compile` 改动文件 |

## 8. 文档同步义务（实现前/中）

- 单一权威 PRD（`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`）：新增能力区块条目 + 3 gate
- `DEV_LOG` 追加记录（关联本 spec）
- `docs/ARCHITECTURE.md` 若 service 数变化，跑 `python scripts/generate_meta.py` 同步（新增 pi_transport.py 模块不新增 service 文件则数字不变，计划阶段确认）

## 9. 非目标

- 不做 chat/deep_read 场景的 pi 支持
- 不做 NER 下游消费（检索/知识链接）
- 不做三 gate 的前端设置面
- 不动 ai_hub 调用链裁决中的 `gateway._try_order` / `service._resolve_provider` 既有逻辑（仅按既有模式扩展）
- 悬置项不连带：LlmDetectionPanel 死字段、mode API 去留（待用户另行裁决）
