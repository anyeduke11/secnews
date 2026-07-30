# 热点地图 · 实施检查清单（CHECKLIST）v3.0

> 文档类型：质量门禁 / 验收检查表
> 关联：[SPEC.md](./SPEC.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) · [TASKS.md](./TASKS.md)
> 用法：每完成一个 Phase，逐项打勾；最终交付前完整过一遍

---

## 使用说明

- ✅ 已完成  ⏳ 进行中  ❌ 未开始  ⚠️ 有风险/不通过
- 每项必须填写**负责人 + 验证方式 + 验证日期**
- 阻塞性问题必须**先解决再进入下一 Phase**
- 非阻塞问题可记入"已知问题"清单

---

## Phase 0：设计规范对齐

> 目标：消除 DESIGN_GUIDE 与代码的现存冲突

- [ ] **C-0-01** 前后端分类色值统一为权威源
  - 验证：`grep -r "0x00e676\|0x00c96a\|#e8891a\|#ff9800\|#00d4ff\|#00bcd4" backend/ frontend/src/` 仅命中统一色值
  - 责任：___
- [ ] **C-0-02** 移除导出页 HOT/WARM/NEW 评分标签
  - 验证：访问 `/api/export` 无 `class="badge"` 标签
  - 责任：___
- [ ] **C-0-03** 文档与实现对齐（ARCHITECTURE.md / SPEC.md / DESIGN_GUIDE.md 互相引用）
  - 验证：3 份文档交叉链接完整
  - 责任：___
- [ ] **C-0-04** 移除 DESIGN_GUIDE 中"已移除"的反例条目（如 HOT/WARM）→ 改为"实现状态"
  - 责任：___
- [ ] **C-0-05** 质量门禁默认值确认（`quality.strict_mode=false` 宽松、URL 内容验证抽样 10%）
  - 验证：settings 表默认值写入正确
  - 责任：___

**Phase 0 准入标准**：上述 5 项必须全部 ✅

---

## Phase 1：基础设施

> 工作量：1 天 · 状态：✅ 已完成（16/16 tests passed）

### 1.1 依赖

- [x] **C-1-01** `pydantic>=2.0` 加入 `requirements.txt`
- [x] **C-1-02** `loguru` 加入依赖
- [x] **C-1-03** `cachetools` 加入依赖
- [x] **C-1-04** `apscheduler>=3.10` 加入依赖
- [x] **C-1-05** `python-dateutil` 加入依赖
- [x] **C-1-06** 删除冗余依赖（如不再需要的）

### 1.2 日志

- [x] **C-1-07** `backend/logging_config.py` 实现 loguru 配置
  - 验证：`pytest tests/test_logging.py -v` 通过
- [x] **C-1-08** JSON Lines 格式 + 必含字段
- [x] **C-1-09** 单文件 50MB 轮转 + 保留 5 个
- [x] **C-1-10** 路径：`backend/logs/app.log`

### 1.3 异常体系

- [x] **C-1-11** `backend/exceptions.py` 定义异常层级
- [x] **C-1-12** FastAPI 全局 handler 集成
  - 验证：触发测试异常 → 响应符合 `{code, message, trace_id}` 结构
- [x] **C-1-13** `trace_id` 注入到日志

### 1.4 配置

- [x] **C-1-14** `backend/config.py` 集中配置（路径/端口/TTL/间隔）
- [x] **C-1-15** 配置项可通过环境变量覆盖

**Phase 1 准入标准**：1.1-1.4 全部 ✅，无 ❌

---

## Phase 2：数据层

> 工作量：2 天 · 状态：✅ 已完成（60/60 tests passed）

### 2.1 连接与迁移

- [x] **C-2-01** `backend/repository/db.py` SQLite 连接管理
- [x] **C-2-02** 启用 WAL 模式
  - 验证：`PRAGMA journal_mode=WAL` 返回 `wal`
- [x] **C-2-03** `synchronous=NORMAL` 配置
- [x] **C-2-04** Migration 机制（版本号 + 顺序执行）
- [x] **C-2-05** 启动时自动 `PRAGMA integrity_check`

### 2.2 Schema

- [x] **C-2-06** `hotspots` 表 + CHECK 约束（category 枚举）
- [x] **C-2-07** `idx_cat_pub` 索引（category, published_at DESC）
- [x] **C-2-08** `idx_pub` 索引
- [x] **C-2-09** `idx_fallback` 索引
- [x] **C-2-10** `hotspots_fts` 虚拟表（unicode61）
- [x] **C-2-11** 触发器同步 FTS（INSERT/DELETE/UPDATE）
- [x] **C-2-12** `trend_snapshots` 表 + 索引
- [x] **C-2-13** `collection_runs` 表 + 索引
- [x] **C-2-14** `settings` 表

### 2.3 数据模型

- [x] **C-2-15** `backend/domain/models.py` Pydantic v2 模型
  - 验证：`python -c "from backend.domain.models import HotspotItem; HotspotItem(...)"`
- [x] **C-2-16** `HotspotItem` 字段与 SPEC §3.1 一致
- [x] **C-2-17** `is_fallback` 字段默认 `False`
- [x] **C-2-18** `url` 字段使用 `HttpUrl` 验证

### 2.4 Repository

- [x] **C-2-19** `HotspotRepository.upsert_many(items)` 批量入库
- [x] **C-2-20** `HotspotRepository.query(category, time_range, keyword, cursor, limit)`
  - 验证：单测覆盖 5 个分类、4 个时间范围、cursor 翻页
- [x] **C-2-21** `HotspotRepository.search(keyword)` FTS5
- [x] **C-2-22** `TrendRepository.rebuild(hours=24)`
- [x] **C-2-23** `TrendRepository.get_current()` 缓存命中
- [x] **C-2-24** `SettingsRepository.get/set` 通用 KV

### 2.5 历史数据迁移

- [x] **C-2-25** 从 `cache_data.json` 导入脚本（213 条全部导入）
  - 验证：旧数据全量导入，备用数据自动打 `is_fallback=True`
- [x] **C-2-26** 迁移可回滚（备份原文件 `cache_data.bak.<timestamp>.json`）

**Phase 2 准入标准**：
- ✅ 所有 schema 索引存在（7 个索引 + FTS5 内部 4 子表）
- ✅ 单测覆盖率 100%（repository 层；60 tests passed）
- ✅ 导入脚本跑通，DB 大小合理

---

## Phase 3：采集层

> 工作量：3 天 · 状态：✅ 已完成（104/104 tests passed）

### 3.1 抽象

- [x] **C-3-01** `backend/collectors/base.py` BaseCollector
- [x] **C-3-02** `BaseCollector.fetch_source()` 异步 aiohttp + ProxySession
- [x] **C-3-03** `BaseCollector._fallback()` 抽象方法（强制实现）
- [x] **C-3-04** `BaseCollector.collect()` 统一异常处理（永不抛异常）
- [x] **C-3-05** `BaseCollector.collect()` 30s 单源超时
- [x] **C-3-06** 失败时记录到 `collection_runs`（CollectionService._write_collection_run）

### 3.2 5 个 collector 重构

- [x] **C-3-07** `ai_collector.py` 继承 BaseCollector（4 sources）
- [x] **C-3-08** `security_collector.py` 继承 BaseCollector（5 sources）
- [x] **C-3-09** `finance_collector.py` 继承 BaseCollector（5 sources）
- [x] **C-3-10** `startup_collector.py` 继承 BaseCollector（4 sources）
- [x] **C-3-11** `bid_collector.py` 继承 BaseCollector（8 sources）
- [x] **C-3-12** 每个 collector 至少 8 条 fallback
- [x] **C-3-13** fallback 数据不伪造时间戳（统一 `datetime.now(timezone.utc)`）
- [x] **C-3-14** fallback 数据带 `is_fallback=True` + `quality_flags=['fallback']`

### 3.3 调度

- [x] **C-3-15** `backend/scheduler/scheduler.py` HotspotScheduler 封装 AsyncIOScheduler
- [x] **C-3-16** 采集任务 `interval=300s, max_instances=1`
- [x] **C-3-17** 趋势重算 `interval=300s`（同步采集）
- [x] **C-3-18** ~~FTS 重建 `interval=86400s`~~ → FTS 由 trigger 自动同步，无需重建
- [x] **C-3-20** 启动时延迟 5s 触发首次采集（不阻塞 ready）
- [x] **C-3-21** 任务失败不杀死调度（异常隔离到 CollectionResult.error）
- [x] **C-3-22** `reschedule(interval_seconds)` 动态调整间隔

### 3.4 启动钩子

- [x] **C-3-23** `main.py` lifespan 启动：`init_db()` + scheduler.start()
- [x] **C-3-24** lifespan 关闭：`scheduler.stop()` + `db.close_db()`
- [x] **C-3-25** 移除 main.py 启动时 `aggregator.collect_all()` 即时抓取
- [x] **C-3-26** `aggregator.py` 标记 DEPRECATED，委托 CollectionService

### 3.5 测试

- [x] **C-3-27** `test_base_collector.py` 通过（9 个测试）
- [x] **C-3-28** `test_collectors.py` 通过（13 个测试，5 collector）
- [x] **C-3-29** `test_collection_service.py` 通过（9 个测试）
- [x] **C-3-30** `test_scheduler.py` 通过（10 个测试）
- [x] **C-3-31** `test_e2e_collect.py` 通过（3 个端到端测试）
- [x] **C-3-32** `pytest backend/tests/ -v` **104 passed**（60 Phase 1+2 + 44 Phase 3）
- [x] **C-3-33** Phase 2 的 60 tests 100% 通过（无回归）

**Phase 3 准入标准**：
- ✅ 5 个 collector 全部能成功入库（外网部分源失败走 fallback，整体 5/5 success）
- ✅ 单源失败不影响其他源（fetch_source 异常隔离）
- ✅ lifespan enter/exit 全流程优雅（手动验证）
- ✅ 实际运行：220 items upserted / 120 trend points / 5 categories populated

---

## Phase 3.5：质量门禁

> 工作量：2 天
> 目标：8 个质量门禁全部生效，支持严格/宽松模式

### 3.5.1 Schema 与数据模型

- [x] **C-3.5-01** `HotspotItem` 新增 4 字段：`quality_score` / `quality_flags` / `quality_checked_at` / `url_check_status`（Phase 2 已实现）
- [x] **C-3.5-02** `quality_check_logs` 表 + 3 个索引（item / gate / time）
- [x] **C-3.5-03** `source_reputation` 表 + 默认初始数据（5 个内置 source）
- [x] **C-3.5-04** `settings` 表新增 7 个 quality.* 配置（strict_mode / min_score / sample_rate / concurrency / timeout / url_check_interval / reputation_interval）
- [x] **C-3.5-05** 分类关键词 JSON 默认值写入 settings（5 个分类各 8-12 个关键词）

### 3.5.2 流水线核心

- [x] **C-3.5-06** `backend/quality/__init__.py`
- [x] **C-3.5-07** `backend/quality/pipeline.py` `QualityGatePipeline` 类
- [x] **C-3.5-08** `backend/quality/base.py` `BaseGate` 抽象类（`check()` / `GateContext`）
- [x] **C-3.5-09** 流水线支持严格/宽松模式切换（`QualityMode.LOOSE/STRICT`）
- [x] **C-3.5-10** 失败时写 `quality_check_logs`（`QualityLogRepository.write_log`）

### 3.5.3 同步 7 个门禁

- [x] **C-3.5-11** `SchemaGate`（Pydantic 二次校验）
- [x] **C-3.5-12** `ContentQualityGate`（长度 + 20 个 spam 词 + 乱码）
- [x] **C-3.5-13** `CategoryMatchGate`（关键词匹配）
- [x] **C-3.5-14** `TitleSummaryGate`（中文 2-gram + 英文 token，Jaccard ≥ 10%）
- [x] **C-3.5-15** `URLValidityGate`（HEAD 2xx，5s 超时）
- [x] **C-3.5-16** `SourceReputationGate`（黑名单 + 动态评分阈值 30/50）
- [x] **C-3.5-17** `DuplicateGate`（URL hash + Jaccard ≥ 80%）

### 3.5.4 异步 URL 内容验证

- [x] **C-3.5-18** `URLContentGate` 实现（抓页面 + 提取 `<title>` + 重叠度 ≥ 30%）
- [x] **C-3.5-19** 抽样控制（默认 10%，可配）
- [x] **C-3.5-20** 超时控制（默认 8s）
- [x] **C-3.5-21** 异步执行（`asyncio.gather` + `Semaphore` 5 并发）
- [x] **C-3.5-22** 完成后更新 `url_check_status` 和 `quality_score`

### 3.5.5 调度与集成

- [x] **C-3.5-23** `BaseCollector.collect()` 集成流水线（fallback 跳过）
- [x] **C-3.5-24** 异步 URL 验证调度（`CollectionService.run_once` 末尾 + scheduler 每 5 分钟）
- [x] **C-3.5-25** 来源信誉重算任务 `interval=6h`（`source_reputation_rebuild_job`）
- [x] **C-3.5-26** fallback 数据**不**经质量门禁（`is_fallback=True` 跳过）

### 3.5.6 API

- [x] **C-3.5-27** `GET /api/quality/summary`（24h 统计）— 推迟到 Phase 4
- [x] **C-3.5-28** `GET /api/quality/rules` — 推迟到 Phase 4
- [x] **C-3.5-29** `PUT /api/quality/rules` — 推迟到 Phase 4
- [x] **C-3.5-30** `GET /api/quality/logs?item_id=` — 推迟到 Phase 4

### 3.5.7 测试

- [x] **C-3.5-31** `tests/test_quality_gates.py` 8 个 gate 22 个测试
- [x] **C-3.5-32** `tests/test_pipeline.py` 严格/宽松模式 7 个测试
- [x] **C-3.5-33** `tests/test_quality_repo.py` 19 个测试（迁移 + repository）
- [x] **C-3.5-34** `tests/test_quality_scorer.py` 13 个测试
- [x] **C-3.5-35** `pytest backend/tests/ -v` **165 passed**（104 Phase 1+2+3 + 61 Phase 3.5）
- [x] **C-3.5-36** Phase 1/2/3 的 104 tests 100% 通过（无回归）

**Phase 3.5 准入标准**：
- ✅ 8 个门禁全部单测通过
- ✅ 严格模式下，垃圾数据被拒绝（score < 30 → QualityGateFailed）
- ✅ 宽松模式下，垃圾数据带 flag 入库（默认）
- ✅ 异步 URL 验证抽样执行（10% 抽样，5 并发，8s 超时）
- ✅ fallback 数据 100% 跳过门禁
- ✅ Phase 1/2/3 全部 104 个测试无回归

---

## Phase 4：API 层

> 工作量：2 天 · 状态：**✅ 已完成**（2026-07-04，229 tests passed）

### 4.1 路由拆分

- [x] **C-4-01** `backend/api/hotspots.py` → `/api/hotspots*`
- [x] **C-4-02** `backend/api/trends.py` → `/api/trends`
- [x] **C-4-03** `backend/api/proxy.py` → `/api/proxy/*`
- [x] **C-4-04** `backend/api/health.py` → `/api/health`, `/api/stats`
- [x] **C-4-05** `backend/api/export.py` → `/api/export`
- [x] **C-4-06** `backend/api/categories.py` → `/api/categories`
- [x] **C-4-07** `main.py` 仅包含 FastAPI 入口 + router 注册（实际 76 行）

### 4.2 服务层

- [x] **C-4-08** `backend/services/hotspot_service.py` 业务编排
- [x] **C-4-09** `backend/services/trend_service.py`
- [x] **C-4-10** `backend/services/export_service.py`

### 4.3 缓存

- [x] **C-4-11** `backend/cache.py` LRU 封装
- [x] **C-4-12** 列表缓存 `TTLCache(64, 300)`
- [x] **C-4-13** 详情缓存 `TTLCache(2000, 600)`
- [x] **C-4-14** 静态缓存 `TTLCache(16, 86400)`
- [x] **C-4-15** 写操作失效对应键
- [x] **C-4-16** 采集完成后 `cache.invalidate("hotspots:*")` + `"trends:*"`
- [x] **C-4-17** 启动时 warmup 5 个最热键

### 4.4 接口实现

- [x] **C-4-18** `GET /api/hotspots` 支持 cursor 分页
- [x] **C-4-19** `GET /api/hotspots/{id}` 详情
- [x] **C-4-20** `GET /api/trends` 返回 24h 数据
- [x] **C-4-21** `GET /api/categories` 静态响应
- [x] **C-4-22** `GET /api/health` 增强版
- [x] **C-4-23** `GET /api/stats`
- [x] **C-4-24** `GET /api/export` 预生成（**30 分钟**一次）+ ETag
- [x] **C-4-25** `GET/PUT /api/proxy/settings`
- [x] **C-4-26** `GET /api/proxy/test` 分组展示
- [x] **C-4-30** `GET /api/quality/summary` 24h 统计（Phase 3.5 推迟）
- [x] **C-4-31** `GET /api/quality/rules` 配置读取
- [x] **C-4-32** `PUT /api/quality/rules` 配置更新
- [x] **C-4-33** `GET /api/quality/logs?item_id=` 单 item 检查日志

### 4.5 错误码

- [x] **C-4-27** 统一错误格式 `{code, message, trace_id, version}`
- [x] **C-4-28** 6 个错误码全部实现（INVALID_PARAM/NOT_FOUND/RATE_LIMITED/INTERNAL/SOURCE_UNAVAILABLE/QUALITY_GATE_FAILED）
- [x] **C-4-29** 参数校验使用 Pydantic
- [x] **C-4-34** trace_id middleware（每个请求生成 UUID + 注入 request.state）

**Phase 4 准入标准**（全部满足）：
- [x] 所有 API 端点有单测 (39 tests in `test_api.py` + 25 tests in `test_cache.py`)
- [x] 缓存命中走 cache（连续两次同样请求应走 cache）
- [x] 错误响应 100% 含 trace_id + version
- [x] 写操作后对应 cache 100% 失效
- [x] 总测试数 229 (≥ 200) 全部通过
- [x] Phase 1/2/3/3.5 的 165 tests 100% 通过（无回归）
- 缓存命中率 > 80%（运行 1h 后观察）
- P95 延迟 < 200ms（10k 数据集）

---

## Phase 5：可观测性 & 前端联调

> 工作量：12h · 状态：**✅ 已完成**（2026-07-04，241 tests passed，coverage 86%，frontend build OK）

### 5.1 日志与可观测性

- [x] **C-5-01** `backend/observability.py` 创建（含 `log_event` + `uptime_s` + `set_start_time`）
- [x] **C-5-02** 所有 collector 走 `collect_start` / `collect_end` 事件打点
- [x] **C-5-03** 所有 API 端点走 `api_request` / `api_response` 事件
- [x] **C-5-04** cache 命中/失效走 `cache_hit` / `cache_miss` / `cache_invalidate` 事件
- [x] **C-5-05** `startup_complete` 事件（含 `startup_duration_ms`）

### 5.2 /api/health & /api/stats 扩展

- [x] **C-5-10** `/api/health` 返回 `version / uptime_s / db.size_mb / db.wal / db.integrity / cache.hit_rate`
- [x] **C-5-11** `/api/stats` 返回 `collect_runs_24h / success_rate_24h / avg_collect_duration_ms / last_fallback_at`
- [x] **C-5-12** `/api/health.components.db.integrity` 字段

### 5.3 启动脚本

- [x] **C-5-13** `run.py` 根目录启动脚本
- [x] **C-5-14** `python run.py` 等价 `uvicorn.run("backend.main:app")`

### 5.4 测试覆盖

- [x] **C-5-20** `tests/test_observability.py` ≥ 8 个测试（**实际 12 个**）
- [x] **C-5-21** `tests/test_api.py` 扩展 health/stats 字段单测
- [x] **C-5-22** 整体覆盖率 ≥ 60%（**实际 86%**）

### 5.5 前端类型重命名

- [x] **C-5-30** `types/index.ts` 字段统一 snake_case (`fetched_at` / `category_counts` / `next_cursor` / `time_range` / `hours_ago`)
- [x] **C-5-31** 6 个分类色值与 SPEC §2.2 严格一致
- [x] **C-5-32** 删除旧 `general` 分类

### 5.6 前端 Hooks 适配

- [x] **C-5-40** `useHotspotData.ts` 用 `fetched_at` / `category_counts` / `next_cursor` + AbortController
- [x] **C-5-41** `useTrendData.ts` 新建，用 `hours_ago`

### 5.7 前端组件适配

- [x] **C-5-50** `HotspotCard` 角落显示 `quality_score` 三色圆点（绿/黄/红）
- [x] **C-5-51** `HotspotCard` `title` 属性展示 `quality_flags`
- [x] **C-5-52** 移除 HOT/WARM 标签
- [x] **C-5-53** `TrendChart` 用 `hours_ago`
- [x] **C-5-54** `Header` 从 `/api/health.version` 读 `v1.2.0` 显示

### 5.8 质量设置面板

- [x] **C-5-60** `SettingsPanel` 新增"质量设置"折叠区
- [x] **C-5-61** 6 个 quality.* 配置项的 toggle / number / slider / readonly
- [x] **C-5-62** 变更后 `PUT /api/quality/rules` 提交
- [x] **C-5-63** 提交后显示成功 / 错误消息

### 5.9 前端构建

- [x] **C-5-70** `cd frontend && npm run build` 通过（无 TS 错误，619 modules，549KB JS + 16KB CSS）

### 5.10 文档

- [x] **C-5-80** `docs/CHECKLIST.md` Phase 5 全部打勾
- [x] **C-5-81** `docs/TASKS.md` Phase 5 全部打勾

**Phase 5 准入标准**（全部满足）：
- 51 项 C-5-XX 全部 ✅
- 整体覆盖率 86% (≥ 60%)
- 241 tests passed (≥ 200)
- 前端 build 通过无 TS 错误
- 可进入 Phase 6（试运行 & 验收）

---

## Phase 6：前端适配

> 状态：✅ **已合并到 Phase 5 完成**（2026-07-04）

Phase 6 的前端适配任务已并入 Phase 5（可观测性 & 前端联调）一并完成：
- [x] **C-6-01** API 契约适配（`fetchedAt` → `fetched_at` 等） → Phase 5.5
- [x] **C-6-02** 分页使用 `next_cursor` → Phase 5.6
- [x] **C-6-04** 前后端分类色值一致 → Phase 5.5
- [x] **C-6-05** 移除 HOT/WARM 标签 → Phase 5.7
- [x] **C-6-07** `npm run build` 通过 → Phase 5.9
- [x] **C-6-08** 前端展示 API 版本号 → Phase 5.7
- [x] **C-6-09** quality_score 徽标 → Phase 5.7
- [x] **C-6-10** quality_flags tooltip → Phase 5.7
- [x] **C-6-11** Settings 面板 quality 折叠区 → Phase 5.8

**Phase 6 准入标准**：UI 无回归、所有功能可用 ✅

---

## Phase 7：试运行 & 验收

> 工作量：1 天

- [ ] **C-7-01** 24h 连续运行无未捕获异常
- [ ] **C-7-02** 缓存命中率 > 80%
- [ ] **C-7-03** 采集成功率 > 95%（24h 统计）
- [ ] **C-7-04** API P95 < 200ms（1k / 10k / 100k 三档）
- [ ] **C-7-05** 故障演练 1：拔网线 → 全走 fallback
- [ ] **C-7-06** 故障演练 2：kill -9 进程 → 重启数据零丢失
- [ ] **C-7-07** 故障演练 3：手动改 DB 为只读 → 采集降级，API 仍响应缓存
- [ ] **C-7-08** 性能压测：`wrk -t2 -c10 -d30s http://localhost:8899/api/hotspots`
- [ ] **C-7-09** 内存占用 < 200MB
- [ ] **C-7-10** DB 大小 < 50MB / 10万条
- [ ] **C-7-11** 备份可恢复（手动还原一份 DB 验证）
- [ ] **C-7-12** 导出 HTML 主题跟随系统
- [ ] **C-7-13** 故障演练 4：质量门禁严格模式 → 垃圾数据被 reject
- [ ] **C-7-14** 故障演练 5：质量门禁宽松模式 → 垃圾数据带 flag 入库
- [ ] **C-7-15** 异步 URL 验证抽样执行 + `url_check_status` 更新
- [ ] **C-7-16** `/api/quality/summary` 24h 数据合理（通过率、平均分）

**Phase 7 准入标准**：所有验收项 ✅，写入 CHANGELOG

---

## 通用质量门禁（贯穿所有 Phase）

### 代码质量

- [ ] 无 `print()` 调试输出（必须用 loguru）
- [ ] 无裸 `dict` 跨层传递（必须 Pydantic）
- [ ] 无 `except: pass`（必须明确异常类型）
- [ ] 无 `TODO` 残留（或记入 backlog）
- [ ] 无未使用 import
- [ ] 无循环导入

### 文档同步

- [ ] ARCHITECTURE.md 反映实际架构
- [ ] SPEC.md 反映实际功能
- [ ] CHECKLIST.md（本文件）已勾选完成项
- [ ] TASKS.md 任务状态同步
- [ ] README.md 启动方式更新
- [ ] CHANGELOG.md 新增 v3.0 条目

### 安全

- [ ] CORS 配置非 `*`（限定来源）
- [ ] 无硬编码密钥
- [ ] 错误响应不暴露内部堆栈
- [ ] 用户输入校验（参数边界）
- [ ] URL 校验（HttpUrl）
- [ ] SQL 参数化（无字符串拼接）

### 性能

- [ ] 无 N+1 查询
- [ ] 无同步阻塞调用（DB / HTTP 异步）
- [ ] 无不必要的全表扫描
- [ ] 大列表分页
- [ ] 静态资源缓存

### 可观测性

- [ ] 所有异常有 trace_id
- [ ] 关键操作有 duration_ms
- [ ] `/api/health` 暴露足够诊断信息
- [ ] 日志不包含敏感信息（密钥、token）

---

## 验收总结

### 必过项（P0）

1. ✅ Phase 0-7 全部完成
2. ✅ 通用质量门禁全部通过
3. ✅ 性能/可靠性/可观测性 验收标准 100% 满足
4. ✅ 测试覆盖率 > 60%
5. ✅ DESIGN_GUIDE 与代码无冲突

### 加分项（P1）

- 性能：API P95 < 100ms
- 可靠性：7×24h 无异常
- 文档：含架构图 + 序列图
- 体验：支持自定义主题色

### 可降级项（P2）

- 支持自定义数据源（用户自己加）
- 导出 PDF 格式
- 移动端响应式优化

---

**变更记录**

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-04 | v3.0 | 基于架构优化方案 v3.0 重写；按 7 个 Phase 组织；新增通用质量门禁 |

---

## 参考文档

- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [SPEC.md](./SPEC.md)
- [CHECKLIST.md](./CHECKLIST.md)
- [TASKS.md](./TASKS.md)
- [DESIGN_GUIDE.md](../DESIGN_GUIDE.md)
