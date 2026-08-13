# Checklist — Phase 16 Hybrid AI

## LLM 配置文件
- [x] `config/llm.yaml` 支持多 provider（Ollama/OpenAI/Qwen/Anthropic）
- [x] `backend/config/llm_schema.py` Pydantic 验证通过
- [x] 缺失 `llm.yaml` 时系统降级为 v1.7 Option A，不阻塞启动
- [x] `docs/llm_config.md` 配置文档完成

## LLMService
- [x] `llm_service.py` 实现多 provider 切换（按 `fallback_order` 尝试）
- [x] `score()` 返回 0~10 浮点数，全部失败时返回 5.0
- [x] `summarize()` 返回摘要文本
- [x] `extract_entities()` 返回实体列表
- [ ] 缓存命中率 ≥ 30%（需实测验证，单元测试已验证缓存逻辑正确性）
- [x] migration `052_v2.0_llm_cache.sql` 执行成功（llm_cache + llm_usage_log 表）

## T1 评分迁移
- [x] T1 触发器中 `_score_with_llm()` 调用 `llm_service.score()`
- [x] LLM 评分失败时降级为 `DEFAULT_SCORE`（5.0）
- [x] LLM 评分结果写入 `ai_scores` 表
- [ ] T1 评分延迟降低 ≥ 60%（需实测验证，单元测试已验证降级逻辑）

## T3 摘要迁移
- [x] T3 触发器中 `_summarize_with_llm()` 调用 `llm_service.summarize()`
- [x] LLM 摘要失败时降级为前 200 字符截取
- [ ] T3 摘要延迟降低 ≥ 40%（需实测验证，单元测试已验证降级逻辑）

## Crawl4ai 集成
- [x] `Crawl4aiParser` 统一代理注入（从 `proxy_config.json` 读取）
- [x] `ProxyPool` failover 模式正常工作
- [x] `startup_health_check()` 启动自检通过
- [x] migration `053_v2.0_proxy_health.sql` 执行成功
- [x] 4 个 collector 迁移完成（hn/reddit/bid/news_article）
- [ ] 抓取成功率 ≥ 80%（需实测验证，单元测试已验证错误处理逻辑）

## 降级矩阵
- [x] 5 种降级场景全部定义并测试通过
- [x] 场景 1: 无 `llm.yaml` → 完全降级 v1.7
- [x] 场景 2: `enabled: false` → 显式禁用
- [x] 场景 3: 无 Ollama + 无 API key → T1/T3 报错 5xx
- [x] 场景 4: 仅 Ollama → T1/T3 走本地
- [x] 场景 5: 全部配齐 → 本地优先，外部备用
- [x] `/api/llm/status` 端点返回降级模式

## 成本监控
- [x] `record_usage()` 记录每次 LLM 调用
- [x] `check_limits()` 正确检查日/月 USD 限额
- [x] 超限额时触发告警
- [x] 告警策略 warn / block / fallback_local 三种模式工作

## 测试
- [x] `test_llm_service.py` 全部通过（38 个用例，多 provider + 缓存 + 降级）
- [x] `test_crawl4ai_parser.py` 全部通过（14 个用例，基础功能）
- [x] `test_hybrid_ai.py` 全部通过（25 个用例，T1/T3 集成 + 降级矩阵 + 成本监控）
- [x] `test_t1_trigger.py` 适配后全部通过（15 个用例，含 3 个 LLM 评分新增）
- [x] `test_t3_trigger.py` 适配后全部通过（13 个用例，含 3 个 LLM 摘要新增）
- [x] 后端 pytest 全部通过（2286 passed, 4 skipped）
- [x] 前端 vitest 全部通过（34 files, 270 passed）
- [x] TypeScript 编译通过（tsc --noEmit 无错误）