# Phase 16: Hybrid AI — Crawl4ai + 本地 LLM + 外部 Agent 并存

## Why

v2.0 开发进入 M4 阶段，当前 T1 评分依赖外部 Agent 调 `score_item` MCP tool，T3 摘要依赖外部 Agent 调 `enrich_concept`，延迟高且外部 Agent 离线时全部阻塞。引入可选本地 LLM 能力（Ollama/Qwen/OpenAI）和 Crawl4ai 高阶抓取，在本地硬件达标时大幅降低 T1/T3 延迟，同时保留外部 Agent 的 T2/T4 判断能力。

## What Changes

### 16.1 LLM 配置文件 schema
- 创建 `config/llm.yaml` 配置文件，包含:
  - `enabled` 总开关，`default_provider`，`fallback_order` 降级顺序
  - 多个 provider 配置（Ollama/OpenAI/Qwen/Anthropic）
  - 任务级覆盖（`task_overrides` 支持 T1 score / T3 summary 独立配置）
  - 限流与成本控制（`rate_limits` + `cost_alert`）
  - 缓存策略（`cache.ttl_seconds` + `similarity_threshold`）
- 创建 `backend/config/llm_schema.py` 验证逻辑（Pydantic schema）
- 创建 `docs/llm_config.md` 配置文档

### 16.2 LLMService 实现
- 创建 `backend/services/llm_service.py`：
  - `score(content, hotspot_id) -> float`: T1 评分接口，返回 0~10
  - `summarize(chunks) -> str`: T3 摘要接口
  - `extract_entities(content) -> list[str]`: T1 实体提取接口
  - `generate(prompt) -> str`: 通用生成接口
  - 多 provider 路由逻辑（按 `fallback_order` 尝试）
  - 缓存实现（SQLite `llm_cache` 表，24h TTL）
  - 降级策略（全部 provider 失败时返回 fallback 值）
- 创建 migration `052_v2.0_llm_cache.sql`：
  - `llm_cache` 表（cache_key, provider, model, response, cached_at, ttl_seconds）
  - `llm_usage_log` 表（provider, model, task, tokens, cost_usd, latency_ms, occurred_at）

### 16.3 T1 评分任务迁移
- 修改 `backend/services/triggers/t1_raw_to_refine.py`：
  - 注入 `LLMService` 实例，替换 `_get_latest_score()` 的 DB 查询方式
  - 新增 `_score_with_llm(content)` 方法，调用 `llm_service.score()`
  - LLM 评分失败时降级为 `DEFAULT_SCORE`（5.0）
  - 保留 `ai_scores` 表写入（LLM 评分也写入以供审计）
- 添加指标 `t1_llm_score_ms`（LLM 评分延迟 histogram）

### 16.4 T3 摘要任务迁移
- 修改 `backend/services/triggers/t3_link_to_structure.py`：
  - 注入 `LLMService` 实例，替换 `_generate_summary()` 的简单截取方式
  - 新增 `_summarize_with_llm(content)` 方法，调用 `llm_service.summarize()`
  - LLM 摘要失败时降级为当前的前 200 字符截取
- 添加指标 `t3_llm_summary_ms`（LLM 摘要延迟 histogram）

### 16.5 Crawl4ai 集成
- 创建 `backend/parsers/crawl4ai_parser.py`：
  - `Crawl4aiParser` 类，统一代理注入（从 `proxy_config.json` 读取）
  - `crawl(url) -> CrawlResult` 主调用（Playwright + Crawl4ai）
  - 代理故障切换（ProxyPool 模式）
  - 创建 `crawl_config.yaml` 配置（browser/headless/timeout/retry）
- 创建 `backend/services/proxy_pool.py`：
  - `ProxyPool` 类（failover + health_score）
  - `startup_health_check()` 启动自检
  - 代理健康度持久化（`proxy_health_log` 表）
- 创建 migration `053_v2.0_proxy_health.sql`：
  - `proxy_health_log` 表（proxy_url, event, source, health_score, latency_ms, error_message, occurred_at）
- 修改 4 个 collector 使用 Crawl4ai 作为备选抓取方式：
  - `backend/collectors/hn_collector.py`（评论页面 JS 渲染）
  - `backend/collectors/reddit_collector.py`（Reddit 强制登录态）
  - `bid_collector.py`（政府采购网强反爬）
  - `news_article` 场景（未来扩展，当前先创建 parser 框架）

### 16.6 配置降级矩阵
- 创建 `backend/config/degradation_matrix.py`：
  - 定义 5 种降级场景处理逻辑:
    1. 无 `llm.yaml` 文件 → 完全降级为 v1.7 Option A（外部 Agent）
    2. `enabled: false` → 同上，显式禁用
    3. 无 Ollama + 无 API key → T1/T3 报错 5xx
    4. 仅 Ollama → T1/T3 走本地，T2/T4 仍外部
    5. 全部配齐 → 全部走本地，外部 Agent 备用
  - 启动时加载配置并检测降级状态
  - 暴露 `/api/llm/status` 端点返回当前 provider 状态和降级模式

### 16.7 成本监控
- 创建 `backend/services/cost_monitor.py`：
  - `record_usage(provider, model, task, tokens, cost_usd, latency_ms)`
  - `check_limits() -> bool` 检查日/月 USD 限额
  - 超限额时触发告警（`cost_alert` 事件写入 `cg_events` 表）
  - 告警规则：`daily_usd_limit` 和 `monthly_usd_limit` 配置
- 成本告警策略：`on_exceeded: warn | block | fallback_local`

### 16.8 测试
- 创建 `backend/tests/test_llm_service.py`：LLMService 多 provider + 缓存 + 降级
- 创建 `backend/tests/test_crawl4ai_parser.py`：Crawl4aiParser 基础功能
- 创建 `backend/tests/test_hybrid_ai.py`：T1/T3 Hybrid 集成测试
- 更新 `backend/tests/test_t1_trigger.py` 和 `backend/tests/test_t3_trigger.py` 适配 LLMService

## Impact

- **Affected code**:
  - `config/llm.yaml` (新文件)
  - `backend/config/llm_schema.py` (新文件)
  - `backend/config/degradation_matrix.py` (新文件)
  - `backend/services/llm_service.py` (新文件)
  - `backend/services/cost_monitor.py` (新文件)
  - `backend/services/proxy_pool.py` (新文件)
  - `backend/parsers/crawl4ai_parser.py` (新文件)
  - `backend/collectors/hn_collector.py` (修改)
  - `backend/collectors/reddit_collector.py` (修改)
  - `backend/collectors/bid_collector.py` (修改)
  - `backend/services/triggers/t1_raw_to_refine.py` (修改)
  - `backend/services/triggers/t3_link_to_structure.py` (修改)
  - `docs/llm_config.md` (新文件)
  - `backend/repository/migrations/052_v2.0_llm_cache.sql` (新文件)
  - `backend/repository/migrations/053_v2.0_proxy_health.sql` (新文件)
  - `backend/collectors/crawl_config.yaml` (新文件)
- **Breaking changes**: 无（完全向后兼容，无 LLM 配置时降级为 v1.7 Option A）
- **New dependencies**: crawl4ai (pip), playwright (pip)

## Requirements

### LLM 配置文件
- `config/llm.yaml` 支持多 provider 配置（Ollama/OpenAI/Qwen/Anthropic）
- 缺失时系统降级为 v1.7 Option A，不阻塞启动

#### Scenario: 无 LLM 配置启动
- **GIVEN** 系统没有 `config/llm.yaml` 文件
- **WHEN** 后端启动
- **THEN** 日志记录 "LLM config not found, running in v1.7 compatibility mode"
- **AND** T1/T3 继续使用外部 Agent 模式

#### Scenario: 完整 LLM 配置启动
- **GIVEN** `config/llm.yaml` 包含 Ollama + OpenAI 配置
- **WHEN** 后端启动
- **THEN** LLMService 初始化成功，所有 provider 就绪
- **AND** `/api/llm/status` 返回 `{"status": "ready", "default_provider": "ollama", "fallback_order": ["ollama", "qwen", "openai"]}`

### LLMService 评分
- `llm_service.score(content, hotspot_id)` 返回 0~10 浮点数
- 按 `fallback_order` 依次尝试 provider
- 全部失败时返回 `DEFAULT_SCORE`（5.0）
- 缓存命中时直接返回缓存值

#### Scenario: T1 评分成功
- **GIVEN** LLMService 已配置且 Ollama 运行中
- **WHEN** 调用 `llm_service.score("article content", "h-123")`
- **THEN** 返回 0~10 的浮点数
- **AND** 结果写入 `ai_scores` 表 + `llm_cache` 表

#### Scenario: 全部 provider 失败
- **GIVEN** 所有 provider 不可用
- **WHEN** 调用 `llm_service.score("content", "h-123")`
- **THEN** 返回 `DEFAULT_SCORE`（5.0）
- **AND** 日志记录 "All LLM providers failed, falling back to default score"

### T1 评分迁移
- T1 触发器中 LLM 评分替换简单 DB 查询
- LLM 评分失败时降级为 `DEFAULT_SCORE`
- 评分延迟降低 ≥ 60%（vs 外部 Agent 调 `score_item`）

### T3 摘要迁移
- T3 触发器中 LLM 摘要替换简单截取
- LLM 摘要失败时降级为前 200 字符截取
- 摘要延迟降低 ≥ 40%（vs 外部 Agent 调 `enrich_concept`）

### Crawl4ai 集成
- Crawl4aiParser 统一代理注入（从 `proxy_config.json` 读取）
- 代理故障切换（ProxyPool failover 模式）
- 4 个 collector 迁移后抓取成功率 ≥ 80%

#### Scenario: Crawl4ai 抓取成功
- **GIVEN** 目标 URL 需要 JS 渲染
- **WHEN** 调用 `Crawl4aiParser.crawl(url)`
- **THEN** 返回包含 title/content/markdown 的 CrawlResult
- **AND** 代理健康度记录成功

#### Scenario: 代理全部失败
- **GIVEN** 所有代理不可用
- **WHEN** 调用 `Crawl4aiParser.crawl(url)`
- **THEN** 抛异常，标记 source_dead
- **AND** 24h 后 source_revival_check 重试

### 成本监控
- 每次 LLM 调用记录 token 数和估算成本
- 超日/月限额时触发告警
- 告警策略支持 warn / block / fallback_local

#### Scenario: 超日限额
- **GIVEN** 当日已消耗 $5.0（`daily_usd_limit: 5.0`）
- **WHEN** 下一次 LLM 调用
- **THEN** 根据 `on_exceeded` 策略：warn（记录日志并继续）/ block（拒绝调用）/ fallback_local（切换到 Ollama）

### 降级矩阵
- 5 种降级场景全部定义并测试通过
- 启动时检测降级状态并记录日志
- `/api/llm/status` 端点暴露降级模式

## Performance Targets

| 任务 | 目标 | 当前值 |
|------|------|--------|
| T1 评分 (Ollama qwen2.5:7b) | < 500ms / 条 | ~2-5s（外部 Agent） |
| T1 评分 (OpenAI gpt-4o-mini) | < 300ms / 条 | ~2-5s（外部 Agent） |
| T3 摘要 (Ollama qwen2.5:14b) | < 3s / 条 | ~5-10s（外部 Agent） |
| Crawl4ai 单页抓取 | < 8s | 当前无 Crawl4ai |