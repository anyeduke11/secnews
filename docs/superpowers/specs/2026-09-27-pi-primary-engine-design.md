# 设计：pi 升为 ai_hub 主力引擎 (pi-primary-engine)

- 日期: 2026-09-27
- 状态: 已批准（owner 裁决: "pi 取代原来的 aihub，然后使用 pi 实现三期重构" — 立项解读见 §2）
- 关联:
  - `docs/superpowers/specs/2026-09-18-pipeline-llm-pi-provider-design.md`（前序: pi 以第 5 种 provider type 进入 ai_hub, 已全部落地, 台账勾选滞后）
  - `docs/superpowers/plans/2026-09-22-settings-refactor.md`（后续批次: 设置页三期重构, 本设计完成后按既有计划执行）
  - `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`（单一权威 PRD）

## 1. 背景与现状实测 (2026-09-27)

09-18 方案 B 已全部落地（代码/配置/gate 三处核实）: `pi_transport.py` 存在、`llm_schema.py` Literal 含 `pi`、`gateway._call_provider` 有 pi 分支、agents.yaml 注册 score/classify/ner、三 gate (`semantic_filter`/`ai_classify`/`pipeline_ner`) 已登记并于 2026-09-19 开闸。**但 pi 至今没有任何路由指向**:

- `config/llm.yaml`: `default_provider: sensenova`；`fallback_order: [ollama, sensenova, qwen, openai]` — pi 不在链上
- `gateway._call_provider_chat` 无 pi 分支 → chat 场景（deep_read 重排即在此路径, gateway.py L173）Unsupported → 永远落到既有 provider

即: pi 管道已铺好, 水龙头没接。本设计 = 接水龙头。

## 2. owner 裁决解读（立项口径）

"pi 取代原来的 aihub" =

1. pi 升为**主力引擎**: `default_provider: pi` + `fallback_order` pi 带头 + chat 路径补 pi 分支
2. 既有 provider 链 (ollama/sensenova/qwen/openai) **降为兜底, 不物理删除** — pi 子进程 / `~/.pi/agent/auth.json` 失效 / 上游 429 时必须有无害兜底; "取代"语义 = 主力地位更替, 非清场
3. "然后使用 pi 实现三期重构" = pi 主力化批次完成后, 按既有 `2026-09-22-settings-refactor.md` 计划执行设置页三期（该计划 0/56 未开工, 本设计不重复规划, 完成后原样开工）

**红线放行范围**: llm.yaml 配置路由 + `_call_provider_chat` additive 分支。`gateway._try_order` / `service._resolve_provider` 既有逻辑不动（与 09-18 同款纪律: 按既有模式扩展, 不改判定链）。

## 3. 改动点

### 3.1 config/llm.yaml（主力化核心, 纯配置）

```yaml
default_provider: pi         # 2026-09-27 owner 裁决: pi 主力 (AI_PROVIDER env 仍可覆盖)
fallback_order:
  - pi            # 主力: 子进程 pi -p --mode json, claude-sonnet-4-5
  - ollama        # 兜底1: 本地零成本 (pi 失效时首选)
  - sensenova     # 兜底2: 唯一持凭据云端
  - qwen
  - openai
```

- `default_provider` 消费方: AIService 门禁 (evaluate/gate_detect) 取 default → 门禁 LLM 调用随之切到 pi 子进程（延迟升高可接受, 单机工作站）
- `AI_PROVIDER` env 覆盖机制不变, 临时切回无需改文件

### 3.2 gateway `_call_provider_chat` pi 分支（additive）

- `pi_transport.py` 增纯函数 `serialize_messages_to_prompt(messages) -> str`: 历史轮次文本化（`[user] ...\n[assistant] ...`）+ 最后一条 user 为当前提问; 空 messages → ValueError（走既有异常路径记健康窗口）
- `_call_provider_chat` 在既有 `else: raise ValueError` 之前加 `elif cfg.type == "pi":` → `asyncio.to_thread(run_pi_print, serialized_prompt, model, cfg.timeout_seconds)`
- 失败照常上抛 → fallback 循环自然降级到下一 provider

### 3.3 明确不做

- 不物理删除既有 provider 配置（§2.2 兜底底线）
- 不动 `_try_order` / `_resolve_provider` / 场景重排（deep_read HEAVY 档逻辑原样, pi 进入后自然参与重排）
- 不动 image 档（sensenova-u1.5-lite 专属, pi 无图像语义）
- 三期重构不在本批次（后续按 09-22 计划原样执行）

## 4. 测试策略

| 层 | 用例 |
|---|---|
| 单测 | `serialize_messages_to_prompt`（多轮/单轮/非 user 收尾/空 messages）; `_call_provider_chat` pi 分支（mock run_pi_print: 收到序列化 prompt + model 下传; 失败上抛）; llm.yaml 解析冒烟（default_provider==pi 且 fallback[0]==pi, 防回归锚） |
| 回归 | `pytest backend/tests/ -k "llm or gateway or ai_hub or pi"`; 全量 0 failed（注意: 若既有测试断言 default_provider==sensenova 需同步修正 — 计划阶段核实） |
| 实弹 | dev server 起, `/api/llm/status` 确认 pi 在链首; 触发一次真实 score/summary, usage 记账 provider=pi |

## 5. 文档同步义务（收口时）

- 单一权威 PRD: 能力条目补一句"pi 主力化（2026-09-27 owner 裁决, 既有链降兜底）"
- `DEV_LOG.md` 追加 [DEV-0234]（关联本 spec + 计划）
- 09-18 计划文件头补台账勘误横幅（勾选未回填但已落地 — 立项时已完成, 不占本批次）

## 6. 后续批次

设置页三期重构: `docs/superpowers/plans/2026-09-22-settings-refactor.md` 原样开工（P1 前端 IA → P2 后端修正 → P3 namespace 治理, 三期独立交付独立回归）。与 pi 主力化无代码耦合, 仅序次依赖（owner 指定 pi 先行）。
