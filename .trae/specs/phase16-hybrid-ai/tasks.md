# Tasks — Phase 16 Hybrid AI

## 任务列表

### Task 16.1: 创建 LLM 配置文件 schema ✅
- [x] 创建 `config/llm.yaml` 配置文件（多 provider + task_overrides + rate_limits + cost_alert + cache）
- [x] 创建 `backend/config/llm_schema.py` 验证逻辑（Pydantic schema）
- [x] 创建 `docs/llm_config.md` 配置文档

### Task 16.2: 实现 LLMService ✅
- [x] 创建 `backend/services/llm_service.py`
  - [x] 多 provider 支持（Ollama/OpenAI/Qwen/Anthropic）
  - [x] `score(content, hotspot_id) -> float` 评分接口
  - [x] `summarize(chunks) -> str` 摘要接口
  - [x] `extract_entities(content) -> list[str]` 实体提取接口
  - [x] `generate(prompt) -> str` 通用生成接口
  - [x] 缓存实现（SQLite `llm_cache` 表，24h TTL）
  - [x] 降级策略（全部 provider 失败时返回 fallback 值）
  - [x] 全局单例 `llm_service`
- [x] 创建 migration `052_v2.0_llm_cache.sql`
  - [x] `llm_cache` 表
  - [x] `llm_usage_log` 表

### Task 16.3: T1 评分任务迁移 ✅
- [x] 修改 `backend/services/triggers/t1_raw_to_refine.py`
  - [x] 注入 `LLMService` 实例
  - [x] 新增 `_score_with_llm(content)` 方法
  - [x] LLM 评分失败时降级为 `DEFAULT_SCORE`（5.0）
  - [x] 保留 `ai_scores` 表写入
- [x] 添加指标 `t1_llm_score_ms`（LLM 评分延迟 histogram）
- [x] 更新 `backend/tests/test_t1_trigger.py` 适配（新增 3 个 LLM 评分测试用例）

### Task 16.4: T3 摘要任务迁移 ✅
- [x] 修改 `backend/services/triggers/t3_link_to_structure.py`
  - [x] 注入 `LLMService` 实例
  - [x] 新增 `_summarize_with_llm(content)` 方法
  - [x] LLM 摘要失败时降级为前 200 字符截取
- [x] 添加指标 `t3_llm_summary_ms`（LLM 摘要延迟 histogram）
- [x] 更新 `backend/tests/test_t3_trigger.py` 适配（新增 3 个 LLM 摘要测试用例）

### Task 16.5: Crawl4ai 集成 ✅
- [x] 创建 `backend/collectors/crawl_config.yaml` 配置
- [x] 创建 `backend/services/proxy_pool.py`
  - [x] `ProxyPool` 类（failover + health_score）
  - [x] `startup_health_check()` 启动自检
  - [x] 代理健康度持久化
- [x] 创建 migration `053_v2.0_proxy_health.sql`
  - [x] `proxy_health_log` 表
- [x] 创建 `backend/parsers/crawl4ai_parser.py`
  - [x] `Crawl4aiParser` 类（统一代理注入）
  - [x] `crawl(url) -> CrawlResult` 主调用
  - [x] 代理故障切换
- [x] 修改 `backend/collectors/hn_collector.py`（评论页面 JS 渲染）
- [x] 修改 `backend/collectors/reddit_collector.py`（Reddit 强制登录态）
- [x] 修改 `bid_collector.py`（政府采购网强反爬）

### Task 16.6: 配置降级矩阵 ✅
- [x] 创建 `backend/config/degradation_matrix.py`
  - [x] 定义 5 种降级场景处理逻辑
  - [x] 启动时加载配置并检测降级状态
  - [x] 暴露 `/api/llm/status` 端点

### Task 16.7: 成本监控 ✅
- [x] 创建 `backend/services/cost_monitor.py`
  - [x] `record_usage(provider, model, task, tokens, cost_usd, latency_ms)`
  - [x] `check_limits() -> bool` 检查日/月 USD 限额
  - [x] 超限额时触发告警（`cost_alert` 事件写入 `cg_events` 表）
- [x] 成本告警策略：`on_exceeded: warn | block | fallback_local`

### Task 16.8: 测试 ✅
- [x] 创建 `backend/tests/test_llm_service.py`（38 个用例，LLMService 多 provider + 缓存 + 降级）
- [x] 创建 `backend/tests/test_crawl4ai_parser.py`（14 个用例，Crawl4aiParser 基础功能）
- [x] 创建 `backend/tests/test_hybrid_ai.py`（25 个用例，T1/T3 Hybrid + DegradationMatrix + CostMonitor）
- [x] 更新 `backend/tests/test_t1_trigger.py` 适配（新增 3 个 LLM 评分测试用例）
- [x] 更新 `backend/tests/test_t3_trigger.py` 适配（新增 3 个 LLM 摘要测试用例）
- [x] 运行全部测试验证：后端 2286 passed, 4 skipped | 前端 34 files, 270 passed | TypeScript 编译通过

## 任务依赖关系
- Task 16.1 → Task 16.2（LLM 配置文件 schema 是 LLMService 的前置）
- Task 16.2 → Task 16.3/16.4/16.7（LLMService 是 T1/T3 迁移和成本监控的前置）
- Task 16.5 可独立进行（Crawl4ai 集成不依赖 LLMService）
- Task 16.6 依赖 Task 16.1/16.2（降级矩阵需要 LLM 配置和 LLMService）
- Task 16.8 依赖所有其他任务

## 并行化建议
- Task 16.1（LLM schema）、Task 16.5（Crawl4ai）可并行
- Task 16.2（LLMService）在 Task 16.1 完成后可开始
- Task 16.3/16.4（T1/T3 迁移）在 Task 16.2 完成后可并行
- Task 16.6/16.7（降级矩阵 + 成本监控）在 Task 16.2 完成后可并行
- Task 16.8（测试）最后执行