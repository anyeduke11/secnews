# Crawl4AI × ai\_hub 整合方案 — 渲染前段 + LLM 单出口

> 类型: **设计文档**（未实施 · 供实施参考）| 日期: 2026-09-01 | 状态: 方案定稿待排期
> 关联: [`docs/crawler-v2-technical-spec.md`](crawler-v2-technical-spec.md)（抓取 v2）·
> [`docs/llm_config.md`](llm_config.md)（LLM 配置）· [`docs/code-wiki/05-running.md`](code-wiki/05-running.md)

## 1. 背景与问题

### 1.1 现状：crawl4ai 双集成、双开关、均默认关闭

仓库当前存在**两套互不知情的 crawl4ai 集成**：

| 集成         | 位置                                                     | 开关源                                                    | 现状                                                                                  |
| ---------- | ------------------------------------------------------ | ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| ① 渲染取 HTML | `backend/utils/crawl4ai_client.py`（`fetch_html`）       | env `USE_CRAWL4AI`（默认 `0`）                             | `renderer="crawl4ai"` 的源（新浪财经/东财/GitHub Trending）实跑全部退化为裸 aiohttp                   |
| ② 详情页抓取    | `backend/parsers/crawl4ai_parser.py`（`Crawl4aiParser`） | `collectors/crawl_config.yaml` 的 `enabled`（默认 `false`） | `crawl()` 恒返回 disabled；且每次 `async with AsyncWebCrawler()` **新建浏览器实例**（启动 5-10s，无单例） |

其结果：**crawl4ai 能力在当前版本实际未生效**，JS 渲染/反爬场景仍然空缺（对应 `renderer="disabled"` 放弃的一批源：36kr/雪球/华尔街见闻/IT桔子等）。

### 1.2 隐忧：crawl4ai 的 `LLMExtractionStrategy` 会绕过 ai\_hub

crawl4ai v0.7+ 的 `LLMExtractionStrategy` 本质是 **openai-compatible 客户端**（内部经 litellm/openai client 直呼 `/chat/completions`）。若直接启用会同时违反三条既有红线：

1. **\[services/AGENTS.md 硬约束] 所有 LLM 调用必须经** **`ai_hub`**，禁止直连 provider SDK — 直连即破坏 LLM 单出口。
2. **\[egress 白名单]** **`check_credential_egress`（`ai_hub/egress.py`）** — 直连外部域名的请求不经过审查，凭据可被任意 base\_url 带走。
3. **\[可观测性]** **`record_llm_call`** **→** **`llm_usage_log`** — 绕过后 provider/model/key\_source/latency/scene 全部丢失，观测看板（llm error\_rate 阈值、cost、采样）对该路径盲区。

### 1.3 方案目标

- 让 crawl4ai 的 **LLM 能力统一走 ai\_hub**，全程可监测、可审查、可管控。

- 分两步落地：**第 1 步纯渲染整合（默认路径，零新增端点）** + **第 2 步 ai\_hub OpenAI-compatible 网关（按需路径）**。

## 2. 架构约束（不可违反）

| # | 约束                                                                                                                                | 出处                                            |
| - | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1 | 所有 LLM 调用经 `ai_hub`；禁止直接 import provider SDK                                                                                      | `backend/services/AGENTS.md` §硬约束 5           |
| 2 | LLM 出站 base\_url 必须过 `check_credential_egress`                                                                                    | `backend/services/ai_hub/egress.py`           |
| 3 | 每次 LLM 调用写 `llm_usage_log`（`record_llm_call`：provider/model/task/prompt/response/ok/latency\_ms/scene/config\_source/key\_source） | `backend/services/ai_hub/usage.py`            |
| 4 | 路由文件 ≤150 行 · 全部 lazy import · 新 router 不与 core 白名单重叠                                                                             | `backend/api/_registry.py` + root `AGENTS.md` |
| 5 | 单进程 · 零外部服务（不引入 Redis/RabbitMQ/Postgres）                                                                                          | 产品裁决                                          |
| 6 | 新 collector 不实现 `_fallback()`（Phase 13 硬约束，不合成假数据）                                                                                | `backend/collectors/base.py`                  |

## 3. 第 1 步：crawl4ai 纯渲染整合（默认路径）

> 目标：让 crawl4ai 真正生效，且其 LLM 工作 **全部落在既有 ai\_hub 合约内**——本步不引入任何新 LLM 通道。

### 3.1 前置：统一双配置源为单一真相

- **真相源**：`backend/collectors/crawl_config.yaml`（已含 enabled/browser/headless/timeout/concurrent/retry/anti\_bot/cache 字段）。

- **改 ①**：`utils/crawl4ai_client.py` 不再读 `USE_CRAWL4AI` env 字面量，改为惰性读取 `crawl_config.yaml`（`enabled` ⇒ 是否可用；`concurrent_requests` ⇒ 信号量大小；`timeout_seconds` ⇒ 超时）。删除 env 双轨，保留 `is_available()` 每次重读语义（测试 monkeypatch 仍旧生效）。

- **改 ②**：`parsers/crawl4ai_parser.py` 去掉每次 `async with AsyncWebCrawler()`，复用 `utils/crawl4ai_client.get_client()` 进程级单例（启动成本一次化，并发仍受信号量约束）。

- **开关默认值**：`crawl_config.yaml` 保持 `enabled: true` 作为生产默认（测试环境经 env/`conftest` 隔离）。

### 3.2 渲染产物接入现有管线（无 LLM in-loop）

```
renderer="crawl4ai" 的源
  → crawl4ai 渲染取 fully-rendered HTML（GET 单例 + 信号量）
  → 复用 _parse_html（lxml CSS → 正则 fallback）或 markdown 蒸馏（Optional）
  → _build_items → 质量门禁（12 gate，含 AIQualityGate）→ upsert
LLM 后处理（不变，全部已在 ai_hub 内）:
  - AIQualityGate 启发式 + LLM 检测   → ai_hub
  - 分类/实体/摘要/深读（KL 管线）     → ai_hub 现有 score/summarize/extract_entities/generate
```

- 提取策略**默认非 LLM**：crawl4ai 的 `JsonCssExtractionStrategy`（结构化）或 markdown 蒸馏即可覆盖"列表页拿标题/URL/时间"的绝大多数场景；hotspot 抓取目标就是列表/链路级数据，不需要 LLM-in-loop。

- **明确不做**：本步不启用 `LLMExtractionStrategy`。

### 3.3 验收标准

- `fetch_html` 读 YAML 配置生效；两处 crawl4ai 集成共用同一单例与同一开关。

- 既有 crawl4ai 单测（`test_crawl4ai_client.py` / `test_crawl4ai_parser.py` / `test_crawl4ai_parser.py`）与 collector 回归全绿；CI 无 Chromium 环境自动走 aiohttp 路径（`is_available()` 假 ⇒ 行为不变）。

- `renderer="crawl4ai"` 源在生产抓取日志中 `crawler=crawl4ai`（现有 `#crawler=` trace 语义）。

## 4. 第 2 步：ai\_hub OpenAI-compatible 网关（按需路径）

> 目标：为"规则提取也搞不定的模糊正文块"提供 LLM-in-loop 提取，且**只存在一条出站 LLM 通道**。
> 做法：ai\_hub 暴露一个本地 OpenAI-compatible 端点，crawl4ai 的 `LLMExtractionStrategy` 指向它——"打到自己家门口"。

### 4.1 端点定义

```
POST /api/aihub/v1/chat/completions        # 仅监听 127.0.0.1（本地回环），不可公网暴露
Content-Type: application/json
```

**请求体（OpenAI 最小子集）**：

```jsonc
{
  "model": "sensenova/sensenova-6.8-flash-lite",   // 命名约定: "<provider>/<model>"
  "messages": [{"role": "user", "content": "提取以下内容为 JSON..."}],
  "max_tokens": 500,          // 可选
  "temperature": 0.0,         // 可选
  "response_format": { "type": "json_object" }   // 可选；见 §4.6 兼容回退
}
```

**响应体（OpenAI 最小子集）**：

```jsonc
{
  "id": "chatcmpl-...",
  "choices": [{ "message": { "role": "assistant", "content": "..." } }],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }  // 估算占位
}
```

错误统一 `{"error": {"message": "...", "type": "..."}}`；HTTP 状态：模型未映射 400 / provider 全失败 502 / 超时 504。

### 4.2 内部流程（6 步，全部 `def` + 现有线程池语义）

```
1. 解析 model "<provider>/<model>" → (provider_name, model)；无 "/" 或 provider 未注册 → 400
2. model_router 路由（复用 route_model，新增档位见 §4.5）→ 确定最终 (provider, model)
3. 拼接 payload（messages[-1].content 作 prompt；max_tokens/temperature 透传）
4. → LLMService._call_provider(cfg, model, prompt, provider_name=...)   // httpx 出站 + egress 审查
5. record_llm_call(scene="crawl4ai_extract", config_source=..., key_source=..., latency_ms=...)
6. 回写 OpenAI 格式；失败抛 ai_hub 统一包装（502/504）
```

> 关键点：调用发生在**进程内**，天然复用 `record_llm_call`——可监测性 = 现有观测体系，无需新增指标通道。

### 4.3 安全边界

| 项    | 措施                                                                                         |
| ---- | ------------------------------------------------------------------------------------------ |
| 暴露范围 | 仅绑 `127.0.0.1`；CORS 不开；反向代理配置禁止转发（运维 note）                                                 |
| 鉴权   | 本地回环免鉴权（无多用户）；若未来开放 loopback 之外需加本地 token                                                  |
| 出站   | 进站无外联（打 ai\_hub 内部），仍受 `check_credential_egress` 管束；**crawl4ai 直连外部 = 唯一需要堵死的洞，本方案从根上不存在** |
| 滥用面  | 请求体大小上限（prompt ≤ 64KB 截断 400）；`max_tokens` 上限；并发沿用 ai\_hub 既有 `max_concurrent`             |

### 4.4 model\_router 接入

- `config/llm.yaml` 新增档位约定（不新增 provider，仅映射关系）：

  - `crawl4ai_extract`（或复用 `task_overrides` 的通用档）→ (provider, model, temperature, max\_tokens)

- `model_router.route_model(task, config=...)` 增加 `crawl4ai_extract` 分支；缺省回落 `default_provider`。

- 注意与既有 `t1_score`/`t3_summary`/`t3_chunk_summary` override 不重叠（命名空间独立）。

### 4.5 缓存

- 复用 `ai_hub/cache.py` 的 `get/set_llm_cache`：以 `(scene, model, user_content)` 为 key，TTL 沿用 24h；

- crawl4ai 侧若传 `bypass_cache` 语义则跳过缓存（可选实现，非必须）。

### 4.6 `response_format` 兼容回退（重点风险）

crawl4ai 的 LLM 提取需要 **json\_object / json\_schema** 输出。当前默认 provider **sensenova 是否支持** **`response_format`** **未知**：

- **探测**：实施前先发一条带 `response_format={"type":"json_object"}` 的探针请求验证。

- **回退策略**（不支持时，网关内做两层）：

  1. 丢弃 `response_format`，在 prompt 尾部追加"**只输出合法 JSON，不要额外文字**"指令；
  2. 响应解析复用 `ai_hub/prompts.py` 既有的 `_parse_*`（JSON 提取/容错），失败按 502 返回。

- 该回退对任何 provider 一视同仁，避免把 provider 差异泄漏给 crawl4ai。

### 4.7 crawl4ai 侧配置（消费方）

```python
from crawl4ai.extraction_strategy import LLMExtractionStrategy
strategy = LLMExtractionStrategy(
    provider="openai/sensenova-6.8-flash-lite",     # litellm 语法；网关按 http base_url 转发
    api_token="local-aihub-placeholder",            # 凭据在网关内部解析，此处任何值不落库
    base_url="http://127.0.0.1:8000/api/aihub/v1",  # 指向本地网关
    schema=MyItem.model_json_schema(),              # crawl4ai 生成 json_schema
)
```

### 4.8 可监测性清单（承诺项）

| 观测点                                                      | 来源                                      |
| -------------------------------------------------------- | --------------------------------------- |
| 每次提取的 provider/model/ok/latency/scene=`crawl4ai_extract` | `record_llm_call` → `llm_usage_log`（现有） |
| key\_source（env/secrets/none）与 config\_source            | 现有 `_key_source`/`_config_source`，零新增   |
| 错误率/耗时阈值告警（llm.error\_rate warn10%/crit30%）              | `observability_threshold_check`（现有）     |
| 采集链路 trace 关联（trace\_id 传播至网关记录）                         | `instrument_job`/TraceIDMiddleware（现有）  |

## 5. 第 1 步 ↔ 第 2 步决策边界

| 触发条件                                | 走哪条                                   |
| ----------------------------------- | ------------------------------------- |
| 98% 抓取场景：列表页取标题/URL/时间、JS 渲染、反爬     | **第 1 步**（纯渲染 + 现有 ai\_hub 后处理）       |
| 出现正文块模糊、CSS 无法收敛、需要 LLM 结构化理解的少数源   | **第 2 步**（网关 + LLMExtractionStrategy） |
| 启用成本明显大于收益（sensenova 探测失败 / 出网预算敏感） | 保留第 1 步，网关做 feature-flag 可关（见 §6）     |

## 6. 风险与回退

| 风险                                           | 缓解                                            |
| -------------------------------------------- | --------------------------------------------- |
| sensenova 不支持 `response_format`              | §4.6 双层回退（指令 + JSON 解析）；探测先行                  |
| 网关被误当通用 LLM API 滥用                           | 请求体/并发上限 + 127.0.0.1 绑定 + 打点 scene 区分（观测可审计）  |
| crawl4ai 版本 API 波动（LLMExtractionStrategy 参数） | 消费侧延迟 import + 采购版本 pin（`requirements.lock`）  |
| 两道开关叠加混乱（第 1 步的 YAML 与第 2 步的 flag）           | 单一 YAML 真相源；第 2 步做成独立小节 + 默认 `enabled: false` |
| 回归风险（既有 collector 行为变化）                      | 全部改动以"行为不变、能力增强"为前提；现有 3 个 crawl4ai 测试文件先行绿   |

## 7. 测试计划

| 层                 | 用例                                                                                                                                                                   |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 单元（网关）            | model 映射合法/非法 400 · messages 折叠为 prompt · max\_tokens/temperature 透传 · response\_format 探测+回退链 · 错误包装 502/504 · 请求体超限 400 · 打点字段断言（scene/config\_source/key\_source） |
| 单元（router 注册）     | 新 router 不与 core 白名单重叠；lazy import 成立                                                                                                                                |
| 集成（crawl4ai → 网关） | mock `LLMExtractionStrategy(base_url=本地网关)` 全链路提取 → 断言 llm\_usage\_log 落行 1 条、scene 正确                                                                               |
| 回归                | 全量 pytest（含 3 个 crawl4ai 测试文件）+ 观测集成测试（middleware→aggregator→summary 不受影响）                                                                                           |

## 8. 实施步骤清单（Checklist）

**第 1 步（纯渲染整合）**

- [ ] ① `crawl4ai_client.py` 改读 `crawl_config.yaml` 单一真相源（删 env 双轨，保 `is_available()` 重读语义）

- [ ] ② `crawl4ai_parser.py` 复用 `get_client()` 单例（删每次 `async with` 新建）

- [ ] ③ `crawl_config.yaml` 生产默认 `enabled: true`（测试隔离经 conftest/env）

- [ ] ④ 回归：3 个 crawl4ai 测试文件 + `test_collectors.py` 相关用例全绿

- [ ] ⑤ 新增用例：YAML 开关生效 / 单例复用 / 降级 aiohttp 语义不变

**第 2 步（ai\_hub 网关，按需）**

- [ ] ① 探针：验证 sensenova `response_format` 支持度（决定 §4.6 回退是否默认启用）

- [ ] ② 新 router `aihub_gateway.py`（≤150 行，lazy import，core 白名单登记）

- [ ] ③ `model_router` 加 `crawl4ai_extract` 档位 + `llm.yaml` 映射

- [ ] ④ 网关单测（§7 单元用例）+ `test_feature_gates` 路由计数同步

- [ ] ⑤ 集成测试：crawl4ai `LLMExtractionStrategy` → 本地网关 → `llm_usage_log` 断言

- [ ] ⑥ `generate_meta.py` 重写 + `--check` 绿；ruff / pytest / tsc / vitest 全量绿

> 边界声明：本方案不引入新数据库表、不新增 feature gate 注册（网关不可用时全集回落第 1 步路径）、不改变 `config/llm.yaml` provider 清单、不触碰 `llm_secrets` 解析链。

