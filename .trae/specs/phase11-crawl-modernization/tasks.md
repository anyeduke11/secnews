# Tasks — Phase 11: 抓取层现代化

## 任务清单

- [ ] Task 1: BackendSession — httpx 统一 HTTP 客户端
  - [ ] 创建 `backend/collectors/session.py`（BackendSession 类）
  - [ ] 实现 GET 方法（proxy + retry + rate-limit + timeout）
  - [ ] 导出模块到 `__init__.py`
  - [ ] 测试文件 `backend/tests/test_backend_session.py`（5 用例）

- [ ] Task 2: 可读 ID 工厂
  - [ ] 创建 `backend/collectors/id_factory.py`（`make_readable_id()`）
  - [ ] 测试文件 `backend/tests/test_id_factory.py`（3 用例）

- [ ] Task 3: trafilatura 集成
  - [ ] 创建 `backend/parsers/trafilatura_parser.py`（`extract_content()`）
  - [ ] 测试文件 `backend/tests/test_trafilatura.py`（3 用例）

- [ ] Task 4: HN Collector
  - [ ] 创建 `backend/collectors/hn_collector.py`
  - [ ] 源配置：Firestore JSON API，top 30 stories
  - [ ] 使用可读 ID (`hn:item:{id}`)
  - [ ] 5 测试用例

- [ ] Task 5: Reddit Collector
  - [ ] 创建 `backend/collectors/reddit_collector.py`
  - [ ] 源配置：Reddit JSON API，r/all top 25
  - [ ] 使用可读 ID (`reddit:post:{id}`)
  - [ ] 5 测试用例

- [ ] Task 6: OpenBB Collector
  - [ ] 创建 `backend/collectors/openbb_collector.py`
  - [ ] 源配置：OpenBB RSS feed
  - [ ] 使用可读 ID (`openbb:article:{id}`)
  - [ ] 5 测试用例

- [ ] Task 7: Telegram Collector
  - [ ] 创建 `backend/collectors/telegram_collector.py`
  - [ ] 源配置：公开频道 HTML 抓取
  - [ ] 使用可读 ID (`telegram:post:{id}`)
  - [ ] 5 测试用例

- [ ] Task 8: GDELT Collector
  - [ ] 创建 `backend/collectors/gdelt_collector.py`
  - [ ] 源配置：GDELT JSON API
  - [ ] 使用可读 ID (`gdelt:article:{id}`)
  - [ ] 5 测试用例

- [ ] Task 9: OSS Insight Collector
  - [ ] 创建 `backend/collectors/ossinsight_collector.py`
  - [ ] 源配置：OSS Insight 趋势页
  - [ ] 使用可读 ID (`ossinsight:trend:{id}`)
  - [ ] 5 测试用例

- [ ] Task 10: JSON pipeline_config
  - [ ] 创建 `config/pipeline.json`
  - [ ] 创建 `config/pipeline.schema.json`（可选）
  - [ ] 添加到配置加载

- [ ] Task 11: 全量回归测试
  - [ ] 运行所有 Phase 11 测试
  - [ ] 运行现有 collector 回归测试
  - [ ] 验证新旧 collector 共存

## 任务依赖

- [Task 1] 无前置（基础组件）
- [Task 2] 无前置
- [Task 3] 无前置
- [Task 4-9] 各自独立，可并行
- [Task 10] 无前置
- [Task 11] 依赖 [Task 1-10]

## 并行策略

**Group A**（独立基础组件，可并行）:
- Task 1: BackendSession
- Task 2: 可读 ID 工厂
- Task 3: trafilatura 集成
- Task 10: pipeline_config

**Group B**（6 个 collector，可并行）:
- Task 4-9: 6 collectors（各自独立）

**Group C**（收尾，串行）:
- Task 11: 全量回归测试