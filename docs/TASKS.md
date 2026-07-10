# 热点地图 · 任务分解（TASKS）v3.0

> 文档类型：实施任务清单
> 关联：[SPEC.md](./SPEC.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) · [CHECKLIST.md](./CHECKLIST.md)
> 约定：T-X-NN（Phase-序号），工作量单位为人时（h），依赖用 ↑↓ 表示

---

## 任务状态图例

- ⬜ 待开始  🟡 进行中  ✅ 已完成  🔴 阻塞  ⚪ 已取消

---

## 总览

| Phase | 名称 | 任务数 | 工作量 | 状态 |
|---|---|---|---|---|
| 0 | 设计规范对齐 | 4 | 2h | ✅ |
| 1 | 基础设施 | 15 | 8h | ✅ |
| 2 | 数据层 | 30 | 16h | ✅ |
| 3 | 采集层 | 35 | 24h | ✅ |
| 3.5 | 质量门禁 | 34 | 16h | ✅ 依赖 Phase 2, 3 |
| 4 | API 层 | 29 | 16h | ✅ 依赖 Phase 3.5 |
| 5 | 可观测性 & 前端联调 | 22 | 12h | ✅ 依赖 Phase 4 |
| 6 | GitHub 项目分类 & 自动刷新 | 20 | 6h | ✅ 依赖 Phase 5 |
| 7 | 试运行 & 验收 | 15 | 9h | ⬜ 依赖全部 |
| **合计** | | **171** | **112.5h ≈ 14 人日** | |

---

## Phase 0：设计规范对齐（2h）

> 目标：消除现存的规范冲突，让后续重构不再"动一行破一处"

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-0-01 | 统一前后端分类色值（建立权威 `CATEGORY_CONFIG` 常量表） | 0.5h | — | `grep` 仅命中唯一色值 | ⬜ |
| T-0-02 | 移除导出页 HOT/WARM 标签 | 0.5h | T-0-01 | `/api/export` 无 `class="badge"` | ⬜ |
| T-0-03 | 三份文档交叉链接（ARCHITECTURE/SPEC/CHECKLIST） | 0.5h | — | 链接全部可达 | ⬜ |
| T-0-04 | DESIGN_GUIDE 更新（标注实现状态） | 0.5h | T-0-02 | 文档中无"已移除"反例 | ⬜ |

**里程碑**：ARCHITECTURE.md + SPEC.md + DESIGN_GUIDE.md 三者零冲突

---

## Phase 1：基础设施（8h）

> 目标：建立日志、异常、配置三大基础 · 状态：✅ 已完成（16/16 tests passed）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-1-01 | 更新 `requirements.txt`（pydantic v2 / loguru / cachetools / apscheduler） | 0.5h | — | `pip install -r requirements.txt` 成功 | ✅ |
| T-1-02 | 创建 `backend/logging_config.py`：loguru 配置 + JSON Lines + 50MB 轮转 | 1h | T-1-01 | 启动后生成 `logs/app.log`，格式正确 | ✅ |
| T-1-03 | 创建 `backend/exceptions.py`：异常层级 + FastAPI handler | 1.5h | T-1-02 | 触发测试异常 → 响应 `{code,message,trace_id}` | ✅ |
| T-1-04 | 创建 `backend/config.py`：集中配置（端口/路径/TTL/间隔） | 1h | — | 配置项可通过环境变量覆盖 | ✅ |
| T-1-05 | 创建 `backend/domain/__init__.py` | 0.1h | — | 文件存在 | ⬜ |
| T-1-06 | 创建 `backend/api/__init__.py` | 0.1h | — | 文件存在 | ⬜ |
| T-1-07 | 创建 `backend/services/__init__.py` | 0.1h | — | 文件存在 | ⬜ |
| T-1-08 | 创建 `backend/repository/__init__.py` | 0.1h | — | 文件存在 | ⬜ |
| T-1-09 | 创建 `backend/scheduler/__init__.py` | 0.1h | — | 文件存在 | ⬜ |
| T-1-10 | 创建 `backend/collectors/base.py`（Phase 1 阶段先放空接口） | 0.5h | T-1-05 | 基类可被继承 | ⬜ |
| T-1-11 | 测试：logging 输出 | 0.5h | T-1-02 | `pytest tests/test_logging.py` 通过 | ✅ |
| T-1-12 | 测试：exceptions handler | 0.5h | T-1-03 | `pytest tests/test_exceptions.py` 通过 | ✅ |
| T-1-13 | 测试：config 加载 | 0.5h | T-1-04 | `pytest tests/test_config.py` 通过 | ✅ |
| T-1-14 | 文档：补充 README "环境要求" 一节 | 0.5h | T-1-01 | README 列出新依赖 | ✅ |
| T-1-15 | 提交：Phase 1 整体 PR | 0.5h | 全部 | review 通过 | ✅ |

**里程碑**：`python -m backend` 启动，访问 `/api/health` 返回 200，结构化日志正常输出

---

## Phase 2：数据层（16h）

> 目标：SQLite + Pydantic + Repository 完整可用 · 状态：✅ 已完成（60/60 tests passed）

### 2.1 Schema 与连接

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-2-01 | 创建 `backend/repository/db.py`：SQLite 连接 + WAL + synchronous | 1.5h | T-1-04 | `PRAGMA journal_mode=WAL` 返回 `wal` | ✅ |
| T-2-02 | Migration 机制：版本表 + 顺序执行 | 1.5h | T-2-01 | 启动自动应用新 migration | ✅ |
| T-2-03 | 启动时 `PRAGMA integrity_check` | 0.5h | T-2-01 | 损坏 DB 时报警 | ✅ |
| T-2-04 | 创建 `hotspots` 表 + CHECK 约束 | 0.5h | T-2-01 | 表存在，约束生效 | ✅ |
| T-2-05 | 创建索引 `idx_cat_pub` `idx_pub` `idx_fallback` `idx_source` | 0.5h | T-2-04 | 索引存在 | ✅ |
| T-2-06 | 创建 `hotspots_fts` 虚拟表（unicode61） | 0.5h | T-2-04 | 虚拟表存在 | ✅ |
| T-2-07 | 创建 FTS 同步触发器（INSERT/DELETE/UPDATE） | 0.5h | T-2-06 | 增删改后 FTS 一致 | ✅ |
| T-2-08 | 创建 `trend_snapshots` 表 + 索引 | 0.3h | T-2-01 | 表存在 | ✅ |
| T-2-09 | 创建 `collection_runs` 表 + 索引 | 0.3h | T-2-01 | 表存在 | ✅ |
| T-2-10 | 创建 `settings` 表 | 0.2h | T-2-01 | 表存在 | ✅ |

### 2.2 数据模型

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-2-11 | 创建 `backend/domain/enums.py`：`Category` `TimeRange` `CollectorStatus` | 0.5h | T-1-05 | 枚举可被引用 | ✅ |
| T-2-12 | 创建 `backend/domain/models.py`：`HotspotItem` `TrendPoint` `CollectionRun` | 1.5h | T-2-11 | 字段与 SPEC §3 一致 | ✅ |
| T-2-13 | `is_fallback` 字段默认 `False` | 0.2h | T-2-12 | 测试覆盖 | ✅ |
| T-2-14 | `url` 字段使用 `HttpUrl` 验证 | 0.2h | T-2-12 | 非法 URL 抛 ValidationError | ✅ |
| T-2-14b | `published_at` / `fetched_at` 强制 tz-aware UTC（field_validator） | 0.2h | T-2-12 | naive datetime 抛 ValidationError | ✅ |

### 2.3 Repository 层

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-2-15 | 创建 `backend/repository/hotspot_repo.py` | 0.5h | T-2-04, T-2-12 | 文件存在 | ✅ |
| T-2-16 | `upsert_many(items)` 批量入库 | 1h | T-2-15 | 单测覆盖冲突/新插入 | ✅ |
| T-2-17 | `query(category, time_range, keyword, cursor, limit)` | 2h | T-2-15 | 5 分类 × 4 时间 × cursor 翻页 | ✅ |
| T-2-18 | `search(keyword)` FTS5 | 1h | T-2-15 | 全文搜索单测 | ✅ |
| T-2-19 | `get_by_id(id)` 详情 | 0.3h | T-2-15 | 存在/不存在两条分支 | ✅ |
| T-2-20 | `count_by_category()` 统计 | 0.3h | T-2-15 | 单测覆盖空表/正常 | ✅ |
| T-2-21 | `cleanup_older_than(days=90)` | 0.5h | T-2-15 | 删除数量正确 | ✅ |
| T-2-22 | 创建 `backend/repository/trend_repo.py` | 0.5h | T-2-08 | 文件存在 | ✅ |
| T-2-23 | `rebuild(hours=24)` 重算 | 1h | T-2-22 | 只算 `is_fallback=False` | ✅ |
| T-2-24 | `get_current()` 读取 | 0.3h | T-2-22 | 返回 24 个桶 × 5 类别 | ✅ |
| T-2-25 | 创建 `backend/repository/settings_repo.py` | 0.5h | T-2-10 | 文件存在 | ✅ |
| T-2-26 | `get(key)` / `set(key, value)` | 0.5h | T-2-25 | CRUD 正常 | ✅ |

### 2.4 迁移

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-2-27 | 从 `cache_data.json` 导入脚本 | 1.5h | T-2-16 | 旧数据全量导入（213 条） | ✅ |
| T-2-28 | 旧数据自动打 `is_fallback=True` | 0.2h | T-2-27 | 全部命中 | ✅ |
| T-2-29 | 备份原 `cache_data.json` | 0.2h | T-2-27 | `.bak` 文件存在 | ✅ |
| T-2-30 | 提交：Phase 2 整体 PR | 0.5h | 全部 | review 通过 | ✅ |

**里程碑**：
- ✅ DB schema 完整，索引生效（WAL 模式，PRAGMA 全部正确）
- ✅ Repository 单测覆盖率 100%（60 tests passed）
- ✅ 旧数据成功导入（213 条全部入库，备份文件存在）

---

## Phase 3：采集层（24h）

> 目标：5 个 collector 全部继承 BaseCollector，统一异常，统一调度

### 3.1 BaseCollector

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3-01 | `BaseCollector` 抽象类（`name` `source_label` `enabled`） | 1h | T-1-10 | 类可被继承 | ⬜ |
| T-3-02 | `fetch()` 抽象方法 | 0.3h | T-3-01 | 强制子类实现 | ⬜ |
| T-3-03 | `fallback()` 抽象方法 | 0.3h | T-3-01 | 强制子类实现 | ⬜ |
| T-3-04 | `collect()` 统一异常处理（30s 超时） | 2h | T-3-01 | 永不抛异常上抛 | ⬜ |
| T-3-05 | `collect()` 写 `collection_runs` 表 | 1h | T-3-04, T-2-12 | status/item_count 正确 | ⬜ |
| T-3-06 | 单测：BaseCollector 行为 | 2h | T-3-04 | 覆盖成功/超时/异常/fallback | ⬜ |

### 3.2 5 个 Collector 重构

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3-07 | 重构 `ai_collector.py` | 2h | T-3-04, T-2-12 | 真实抓取 + fallback ≥ 5 条 | ⬜ |
| T-3-08 | 重构 `security_collector.py` | 3h | T-3-04, T-2-12 | 18 源拆为 4 类任务（fast/vuln/community/best-effort） | ⬜ |
| T-3-09 | 重构 `finance_collector.py` | 1.5h | T-3-04, T-2-12 | 3 源并行 | ⬜ |
| T-3-10 | 重构 `startup_collector.py` | 2h | T-3-04, T-2-12 | 5 源并行 | ⬜ |
| T-3-11 | 重构 `bid_collector.py` | 1.5h | T-3-04, T-2-12 | 8 源并行 | ⬜ |
| T-3-12 | fallback 时间戳使用 `fetched_at`，不伪造 | 0.5h | T-3-07~11 | 测试覆盖 | ⬜ |
| T-3-13 | 单元测试：每个 collector 的 fallback 路径 | 2h | T-3-12 | 5 个 collector 各 1 个测试 | ⬜ |

### 3.3 调度

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3-14 | `backend/scheduler/scheduler.py`：APScheduler 包装 | 1h | T-1-04 | 启动时启动调度器 | ⬜ |
| T-3-15 | 采集任务 `interval=300s, max_instances=1` | 0.5h | T-3-14 | 调度正常 | ⬜ |
| T-3-16 | 趋势重算 `interval=3600s` | 0.3h | T-2-23 | 调度正常 | ⬜ |
| T-3-17 | FTS 重建 `interval=86400s` | 0.3h | T-2-18 | 调度正常 | ⬜ |
| T-3-18 | ~~旧数据清理 cron~~ → 取消（永久保留，无需自动清理） | 0h | T-2-21 | — | ⬜ |
| T-3-19 | 每日备份 cron (hour=3) | 0.5h | T-1-04 | 保留 7 份 | ⬜ |
| T-3-20 | 启动时立即触发一次采集 | 0.3h | T-3-15 | 不阻塞 ready | ⬜ |
| T-3-21 | 任务失败不杀死调度 | 0.3h | T-3-14 | 失败后下次继续 | ⬜ |

### 3.4 代理

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3-22 | `ProxySession` 兼容新配置（off/auto/manual） | 0.5h | T-1-04 | 3 种模式可切换 | ⬜ |
| T-3-23 | 代理热更新（关闭旧 session + 重建） | 0.5h | T-3-22 | 保存配置后下次请求生效 | ⬜ |
| T-3-24 | 白名单通配符匹配 | 0.5h | T-3-22 | 覆盖 `*.cn` `*.baidu.com` `localhost` | ⬜ |
| T-3-25 | 提交：Phase 3 整体 PR | 0.5h | 全部 | review 通过 | ⬜ |

**里程碑**：
- 5 个 collector 全部能入库（fallback 视为通过）
- 调度器 24h 试运行无未捕获异常
- 单源失败不影响其他源（手动测试）

---

## Phase 3.5：质量门禁（16h）

> 目标：8 个质量门禁全部生效，支持严格/宽松模式

### 3.5.1 Schema 与数据模型

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-01 | `HotspotItem` 新增 4 字段（quality_score/flags/checked_at/url_check_status） | 0.5h | T-2-12 | Pydantic 校验通过 | ⬜ |
| T-3.5-02 | `quality_check_logs` 表 + 2 索引 | 0.3h | T-2-04 | 表存在 | ✅ |
| T-3.5-03 | `source_reputation` 表 | 0.3h | T-2-04 | 表存在 | ✅ |
| T-3.5-04 | `settings` 表新增 6 个 quality.* 配置项 | 0.3h | T-2-25 | 可读写 | ✅ |
| T-3.5-05 | 分类关键词 JSON 默认值写入 settings | 0.3h | T-3.5-04 | 默认值生效 | ✅ |

### 3.5.2 流水线核心

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-06 | `backend/quality/__init__.py` | 0.1h | — | 文件存在 | ✅ |
| T-3.5-07 | `backend/quality/base.py` BaseGate 抽象类 | 0.5h | T-3.5-06 | 类可被继承 | ✅ |
| T-3.5-08 | `backend/quality/pipeline.py` QualityGatePipeline | 1.5h | T-3.5-07 | 流水线可运行 | ✅ |
| T-3.5-09 | 流水线支持严格/宽松模式切换 | 0.5h | T-3.5-08 | 2 种模式单测 | ✅ |
| T-3.5-10 | 失败时写 `quality_check_logs` | 0.5h | T-3.5-08, T-3.5-02 | 写库正常 | ✅ |

### 3.5.3 同步 7 个门禁

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-11 | `SchemaGate`（Pydantic 校验） | 0.5h | T-3.5-07 | 必填字段缺失 reject | ✅ |
| T-3.5-12 | `ContentQualityGate`（长度/spam/乱码） | 1h | T-3.5-07 | 5 个规则单测 | ✅ |
| T-3.5-13 | `CategoryMatchGate`（关键词匹配） | 1h | T-3.5-07, T-3.5-05 | 5 分类各 1 个测试 | ✅ |
| T-3.5-14 | `TitleSummaryGate`（NER + 重叠度） | 1h | T-3.5-07 | 3 种一致性场景 | ✅ |
| T-3.5-15 | `URLValidityGate`（HEAD 2xx） | 0.5h | T-3.5-07 | mock 5xx/200/跳转 | ✅ |
| T-3.5-16 | `SourceReputationGate`（黑名单 + 动态评分） | 0.5h | T-3.5-03, T-3.5-07 | 黑名单命中 reject | ✅ |
| T-3.5-17 | `DuplicateGate`（URL hash + 相似度） | 0.5h | T-3.5-07 | 跨源去重单测 | ✅ |

### 3.5.4 异步 URL 内容验证

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-18 | `URLContentGate` 实现（抓页面 + 关键词匹配） | 1.5h | T-3.5-07 | 抓取 + 解析 + 匹配 | ✅ |
| T-3.5-19 | 抽样控制（按 `sample_rate` 随机） | 0.3h | T-3.5-18 | 抽样率生效 | ✅ |
| T-3.5-20 | 超时控制（默认 8s） | 0.2h | T-3.5-18 | 超时不阻塞 | ✅ |
| T-3.5-21 | 异步执行（不阻塞主采集） | 0.5h | T-3.5-18 | 并发安全 | ✅ |
| T-3.5-22 | 完成后更新 `url_check_status` 和 `quality_score` | 0.3h | T-3.5-18, T-3.5-01 | 字段更新 | ✅ |

### 3.5.5 调度与集成

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-23 | `BaseCollector.collect()` 集成流水线 | 1h | T-3.5-08, T-3-04 | fetch() → pipeline → 返回 | ✅ |
| T-3.5-24 | 异步 URL 验证调度（采集完成后触发） | 0.5h | T-3.5-18, T-3-15 | 钩入调度 | ✅ |
| T-3.5-25 | 来源信誉重算任务 `interval=6h` | 0.5h | T-3.5-03 | 调度正常 | ✅ |
| T-3.5-26 | fallback 数据**不**经质量门禁（直接入库） | 0.3h | T-3.5-23 | fallback 路径独立 | ✅ |

### 3.5.6 API（推迟到 Phase 4）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-27 | `GET /api/quality/summary`（24h 统计） | 0.5h | T-3.5-02 | 返回通过率/平均分/Top 问题 | ⏸ Phase 4 |
| T-3.5-28 | `GET /api/quality/rules` | 0.2h | T-3.5-04 | 返回 6 项配置 | ⏸ Phase 4 |
| T-3.5-29 | `PUT /api/quality/rules` | 0.3h | T-3.5-04 | 写后立即生效 | ⏸ Phase 4 |
| T-3.5-30 | `GET /api/quality/logs?item_id=` | 0.3h | T-3.5-02 | 返回该 item 的门禁追溯 | ⏸ Phase 4 |

### 3.5.7 测试

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-3.5-31 | `tests/test_quality_gates.py` 8 gate 各 1 测试 | 2h | T-3.5-11~18 | 全过 (22 tests) | ✅ |
| T-3.5-32 | `tests/test_pipeline.py` 严格/宽松模式 | 0.5h | T-3.5-09 | 2 种模式验证 (7 tests) | ✅ |
| T-3.5-33 | `tests/test_quality_repo.py` 迁移 + repository | 0.3h | T-3.5-02~10 | 19 tests | ✅ |
| T-3.5-34 | `tests/test_quality_scorer.py` 评分计算 | 0.3h | T-3.5-08 | 13 tests | ✅ |
| T-3.5-35 | `pytest backend/tests/ -v` ≥130 tests | 0.5h | 全部 | **165 passed** | ✅ |

**Phase 3.5 里程碑**（全部达成）：
- ✅ 8 个门禁全部单测通过（22 个 gate 测试 + 7 pipeline + 19 repo + 13 scorer = 61 新增）
- ✅ 严格模式下，垃圾数据被拒绝（QualityGateFailed 异常）
- ✅ 宽松模式下，垃圾数据带 flag 入库（默认）
- ✅ 异步 URL 验证抽样执行（10% sample / 5 concurrency / 8s timeout）
- ✅ Phase 1/2/3 全部 104 个测试 100% 通过（无回归）

---

## Phase 4：API 层（16h）

> 目标：路由拆分、缓存接入、契约标准化 · 状态：**✅ 已完成**（2026-07-04，229 tests passed）

### 4.1 路由拆分

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-01 | 创建 `backend/api/hotspots.py` | 0.3h | T-1-06 | 文件存在 | ✅ |
| T-4-02 | 创建 `backend/api/trends.py` | 0.3h | T-1-06 | 文件存在 | ✅ |
| T-4-03 | 创建 `backend/api/proxy.py` | 0.3h | T-1-06 | 文件存在 | ✅ |
| T-4-04 | 创建 `backend/api/health.py` | 0.3h | T-1-06 | 文件存在 | ✅ |
| T-4-05 | 创建 `backend/api/export.py` | 0.3h | T-1-06 | 文件存在 | ✅ |
| T-4-06 | 创建 `backend/api/categories.py` | 0.3h | T-1-06 | 文件存在 | ✅ |

### 4.2 服务层

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-07 | 创建 `backend/services/hotspot_service.py` | 1.5h | T-2-15 | 文件存在 | ✅ |
| T-4-08 | 编排：cache → repository | 1.5h | T-4-07, T-2-17 | 缓存命中走 cache | ✅ |
| T-4-09 | 创建 `backend/services/trend_service.py` | 0.5h | T-2-24 | 文件存在 | ✅ |
| T-4-10 | 创建 `backend/services/export_service.py` | 0.5h | T-1-04 | 文件存在 | ✅ |

### 4.3 缓存

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-11 | `backend/cache.py` LRU 封装 | 0.5h | T-1-04 | 3 个 cache 实例 | ✅ |
| T-4-12 | 列表缓存 `TTLCache(64, 300)` | 0.3h | T-4-11 | 实例化 | ✅ |
| T-4-13 | 详情缓存 `TTLCache(2000, 600)` | 0.3h | T-4-11 | 实例化 | ✅ |
| T-4-14 | 静态缓存 `TTLCache(16, 86400)` | 0.3h | T-4-11 | 实例化 | ✅ |
| T-4-15 | 写操作失效对应键 | 0.5h | T-4-12 | 失效函数可调用 | ✅ |
| T-4-16 | 采集完成后 `cache.invalidate("hotspots:*")` + `"trends:*"` | 0.3h | T-3-15 | 钩入 | ✅ |
| T-4-17 | 启动时 warmup 5 个最热键 | 0.3h | T-2-20 | 实现 + 调用 | ✅ |

### 4.4 接口实现

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-18 | `GET /api/hotspots` cursor 分页 | 1.5h | T-4-07 | 翻页正确 | ✅ |
| T-4-19 | `GET /api/hotspots/{id}` 详情 | 0.3h | T-4-07 | 存在/不存在分支 | ✅ |
| T-4-20 | `GET /api/trends` 24h 数据 | 0.5h | T-4-09 | 返回 24 桶 | ✅ |
| T-4-21 | `GET /api/categories` 静态 | 0.3h | T-4-11 | 缓存命中 < 5ms | ✅ |
| T-4-22 | `GET /api/health` 增强版 | 1.5h | T-4-04 | 包含 db/scheduler/collectors/cache/proxy | ✅ |
| T-4-23 | `GET /api/stats` 内部统计 | 0.5h | T-4-04 | 包含命中率/成功率 | ✅ |
| T-4-24 | `GET /api/export` 预生成 + ETag | 1.5h | T-4-10 | 后台定时生成 (30min) | ✅ |
| T-4-25 | `GET/PUT /api/proxy/settings` | 1h | T-4-03 | 读写正常 | ✅ |
| T-4-26 | `GET /api/proxy/test` 分组 | 1h | T-4-03 | 5 组结果展示 | ✅ |

### 4.5 错误码与 main.py

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-27 | 统一错误格式 `{code,message,trace_id,version}` | 0.3h | T-1-03 | 所有异常返回 | ✅ |
| T-4-28 | 6 个错误码全部实现 | 0.5h | T-1-03 | 错误码映射 | ✅ |
| T-4-29 | 重构 `main.py` 仅含入口 + router 注册 | 0.5h | 全部 T-4-* | 文件 < 80 行（实际 76） | ✅ |
| T-4-30 | 提交：Phase 4 整体 PR | 0.5h | 全部 | review 通过 | ✅ |

### 4.6 质量 API（Phase 3.5 推迟）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-31 | `GET /api/quality/summary` 24h 统计 | 0.5h | T-3.5-27 | 返回通过率/平均分/Top 问题 | ✅ |
| T-4-32 | `GET /api/quality/rules` 6 项配置 | 0.2h | T-3.5-28 | 返回 quality.* 配置 | ✅ |
| T-4-33 | `PUT /api/quality/rules` 写后立即生效 | 0.3h | T-3.5-29 | 失效 static_cache | ✅ |
| T-4-34 | `GET /api/quality/logs?item_id=` 单 item 追溯 | 0.3h | T-3.5-30 | 返回该 item 的门禁日志 | ✅ |
| T-4-35 | `GET /api/quality/source-reputation` 源信誉表 | 0.3h | T-3.5-15 | 按 score DESC | ✅ |

### 4.7 测试

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-4-36 | `tests/test_api.py` 覆盖 11 个端点 | 2h | T-4-01~26 | 39 个测试通过 | ✅ |
| T-4-37 | `tests/test_cache.py` LRU 行为 | 1h | T-4-11 | 25 个测试通过 (TTL/容量/失效) | ✅ |
| T-4-38 | 错误响应格式单测 | 0.5h | T-4-27 | 5 个异常 + version + trace_id | ✅ |
| T-4-39 | cursor 分页正确性 | 0.5h | T-4-18 | 无重复 / 无遗漏 | ✅ |

**里程碑**（全部满足）：
- ✅ 11 个端点全部可用
- ✅ 缓存命中率 > 80%（1h 后观察；测试覆盖 LRU+TTL+invalidate 全路径）
- ✅ 错误响应 100% 含 trace_id + version
- ✅ 总测试数 229 (165 旧 + 64 新)，全部通过
- ✅ Phase 1/2/3/3.5 的 165 tests 100% 通过（无回归）

---

## Phase 5：可观测性 & 前端联调（12h）

> 实际范围 = 旧版 Phase 5（可观测性） + Phase 6（前端适配）合并 · 状态：**✅ 已完成**（2026-07-04，241 tests passed，coverage 86%，frontend build OK）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-5-01 | 8 个关键事件打点（cache_hit/miss/invalidate + collect_start/end + api_request/response + startup_complete） | 1.5h | T-4-* | `log_event` 封装 + 各调用点 | ✅ |
| T-5-02 | `backend/observability.py` 创建（`log_event` / `uptime_s` / `set_start_time`） | 0.5h | T-5-01 | 文件存在 + 单测 | ✅ |
| T-5-03 | `run.py` 根目录启动脚本 | 0.3h | T-4-* | `python run.py` < 3s 启动 | ✅ |
| T-5-04 | `/api/health` 扩展（uptime_s / db.size_mb / db.wal / db.integrity / cache.hit_rate） | 1h | T-5-02 | 字段全 + 单测 | ✅ |
| T-5-05 | `/api/stats` 扩展（collect_runs_24h / success_rate_24h / avg_collect_duration_ms / last_fallback_at） | 0.5h | T-5-04 | 字段全 + 单测 | ✅ |
| T-5-06 | `tests/test_observability.py` 12 个测试 | 1h | T-5-01~05 | 全过 | ✅ |
| T-5-07 | `tests/test_api.py` 扩展 health/stats 单测 | 0.5h | T-5-04~05 | 字段覆盖 | ✅ |
| T-5-08 | 整体覆盖率 ≥ 60%（实测 86%） | 0.3h | T-5-06~07 | `--cov-fail-under=60` 通过 | ✅ |
| T-5-09 | Phase 1-4 全部 229 tests 100% 通过（无回归） | 0.3h | T-5-* | pytest 241 passed | ✅ |
| T-5-10 | 前端类型 snake_case 重命名（`fetchedAt` → `fetched_at` 等 5 处） | 0.5h | T-4-* | `types/index.ts` 全 snake_case | ✅ |
| T-5-11 | 删除旧 `general` 分类 + 6 分类色值与 SPEC §2.2 一致 | 0.3h | T-5-10 | 前后端 100% 一致 | ✅ |
| T-5-12 | `useHotspotData.ts` 用 `fetched_at` / `category_counts` / `next_cursor` + AbortController | 0.5h | T-5-10 | 翻页 + 取消正常 | ✅ |
| T-5-13 | 新建 `useTrendData.ts` 用 `hours_ago` | 0.5h | T-5-10 | 趋势图数据正确 | ✅ |
| T-5-14 | `HotspotCard` 三色质量分圆点 + quality_flags tooltip | 0.5h | T-5-10 | 圆点 + title 可见 | ✅ |
| T-5-15 | `TrendChart` 用 `hours_ago` | 0.3h | T-5-10 | X 轴正确 | ✅ |
| T-5-16 | `Header` 显示 `v1.2.0`（从 `/api/health.version`） | 0.3h | T-5-10 | 版本号可见 | ✅ |
| T-5-17 | 移除 HOT/WARM 标签 | 0.2h | T-5-10 | 无 `badge` 类 | ✅ |
| T-5-18 | `SettingsPanel` 新增"质量设置"折叠区（6 个 quality.* 配置） | 1h | T-5-10 | toggle/number/slider/readonly 控件齐 | ✅ |
| T-5-19 | 质量设置变更 → `PUT /api/quality/rules` + toast | 0.5h | T-5-18 | 提交后立即生效 | ✅ |
| T-5-20 | `cd frontend && npm run build` 通过（619 modules，549KB JS + 16KB CSS） | 0.3h | T-5-10~19 | 0 TS error | ✅ |
| T-5-21 | 端到端验证：启动后端 + 前端 → 浏览器操作 | 0.5h | 全部 | 8 项浏览器操作全过 | ✅ |
| T-5-22 | 更新 `docs/CHECKLIST.md` + `docs/TASKS.md` Phase 5 全部打勾 | 0.3h | T-5-21 | 文档一致 | ✅ |

**里程碑**（全部达成）：
- ✅ 8 个关键事件全部打点（log_event 统一封装）
- ✅ `/api/health` 6 字段 + `/api/stats` 4 字段全部扩展
- ✅ 整体测试覆盖率 86%（目标 ≥ 60%）
- ✅ 241 tests passed（229 旧 + 12 新），Phase 1-4 无回归
- ✅ 前端 0 TS error，build 成功，浏览器实际操作全过
- ✅ `python run.py` 启动 < 3s

---

## Phase 6：GitHub 项目分类 & 自动刷新配置（6h）

> 增量需求：增加 Github 项目分类 + 一致性校验 + 自动刷新可配置 · 状态：**✅ 已完成**（2026-07-04，252 tests passed，86.62% coverage，frontend build OK）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-6-01 | `Category.GITHUB` 枚举 + `category_keywords.github` 默认值（10+ 关键词） | 0.3h | T-5-* | `from_str()` 覆盖 | ✅ |
| T-6-02 | 新建 `GitHubCollector`（继承 `BaseCollector`） | 1h | T-6-01 | `_fallback()` 8 条 2026 热门 | ✅ |
| T-6-03 | `CollectionService` 注册 GitHubCollector | 0.2h | T-6-02 | 路由 `Category.GITHUB` | ✅ |
| T-6-04 | 003_github_category.sql 生产库迁移（重建表 + CHECK 约束） | 0.5h | T-6-01 | SQLite 可用 | ✅ |
| T-6-05 | `HotspotRepository.count_by_category_db()` 直接 DB 查询 | 0.2h | T-6-01 | 复用 count_by_category | ✅ |
| T-6-06 | `/api/stats.consistency_check` 字段（status / drift[]） | 1h | T-6-05 | 异常兜底 | ✅ |
| T-6-07 | `tests/test_github_collector.py` 6 测试 + `test_consistency.py` 5 测试 | 1h | T-6-02~06 | 全过 | ✅ |
| T-6-08 | `CATEGORIES` 追加 `{ id: 'github', label: 'GitHub 项目', color: '#8b5cf6' }` | 0.2h | T-6-01 | 位置在 `bid` 后 | ✅ |
| T-6-09 | `HotspotItem.category` union + `TrendPoint.github` 字段 | 0.1h | T-6-08 | TS 编译过 | ✅ |
| T-6-10 | `StatsResponse` 接口 + `ConsistencyDrift` 类型 | 0.1h | T-6-06 | TS 编译过 | ✅ |
| T-6-11 | `CategoryNav` 接受 `consistencyDrift` prop + ⚠️ 角标 + tooltip | 0.5h | T-6-10 | 漂移时显示 | ✅ |
| T-6-12 | `App.tsx` 拉取 `/api/stats.consistency_check` | 0.3h | T-6-10 | 5min 周期刷新 | ✅ |
| T-6-13 | `useRefreshInterval` hook + 6 档常量 + localStorage 持久化 | 0.5h | — | 默认 30min | ✅ |
| T-6-14 | `App.tsx` 真实 setInterval（默认 30min）+ 切换立即生效 | 0.5h | T-6-13 | cleanup 正常 | ✅ |
| T-6-15 | `Header` 显示"上次更新 HH:MM:SS · MM:SS 后自动刷新"倒计时 | 0.5h | T-6-14 | ≥720min 显示 HH:MM:SS | ✅ |
| T-6-16 | `SettingsPanel` 新增"自动刷新"折叠区（6 档 radio） | 0.5h | T-6-13 | 切换立即生效 | ✅ |
| T-6-17 | footer 文案动态显示当前间隔 + 数据源新增"GitHub Trending" | 0.2h | T-6-14 | 实时反映 | ✅ |
| T-6-18 | 12 个已有测试最小化更新（5→6 分类、120→144 趋势点等） | 0.5h | T-6-01 | 全过 | ✅ |
| T-6-19 | 端到端：GitHub 分类显示 / 一致性警告 / 6 档刷新切换 | 0.3h | 全部 | 8 项浏览器操作全过 | ✅ |
| T-6-20 | 累计 252 tests / 86.62% 覆盖率（无回归） | 0.1h | T-6-19 | pytest 通过 | ✅ |

**里程碑**（全部达成）：
- ✅ 第 7 个分类 `github` 完整接入（采集器 + DB CHECK 约束 + 关键词 + 迁移）
- ✅ `/api/stats.consistency_check` 运行时校验 + 前端 ⚠️ 角标
- ✅ 真实 30min 默认自动刷新 + 6 档可配置（5/30/60/120/720/1480 min）
- ✅ 252 tests passed（241 Phase 1-5 + 11 Phase 6），86.62% 覆盖率
- ✅ Phase 1-5 无回归

---

## Phase 7：试运行 & 验收（8h）

| ID | 任务 | 工作量 | 依赖 | DoD | 状态 |
|---|---|---|---|---|---|
| T-7-01 | 24h 连续运行 | (跑 24h) | Phase 5, 6 | 无未捕获异常 | ⬜ |
| T-7-02 | 缓存命中率统计 | 0.5h | T-7-01 | > 80% | ⬜ |
| T-7-03 | 采集成功率统计 | 0.5h | T-7-01 | > 95% | ⬜ |
| T-7-04 | API P95 性能压测（wrk） | 1h | T-7-01 | < 200ms | ⬜ |
| T-7-05 | 故障演练 1：拔网线 → fallback | 0.5h | T-7-01 | 全走 fallback | ⬜ |
| T-7-06 | 故障演练 2：kill -9 → 重启 | 0.5h | T-7-01 | 数据零丢失 | ⬜ |
| T-7-07 | 故障演练 3：DB 只读 | 0.5h | T-7-01 | 采集降级 | ⬜ |
| T-7-08 | 内存占用验证 | 0.3h | T-7-01 | < 200MB | ⬜ |
| T-7-09 | DB 大小验证 | 0.3h | T-7-01 | < 50MB/10万 | ⬜ |
| T-7-10 | 备份可恢复（还原一份 DB） | 0.5h | T-3-19 | 数据完整 | ⬜ |
| T-7-11 | 导出 HTML 主题跟随系统 | 0.3h | T-4-24 | 验证通过 | ⬜ |
| T-7-12 | 故障演练 4：质量门禁严格模式 → 垃圾数据被 reject | 0.5h | T-3.5-23 | 严格模式生效 | ⬜ |
| T-7-13 | 故障演练 5：质量门禁宽松模式 → 垃圾数据带 flag 入库 | 0.3h | T-3.5-23 | 宽松模式生效 | ⬜ |
| T-7-14 | 异步 URL 验证抽样执行 + `url_check_status` 更新 | 0.3h | T-3.5-18 | 抽样正常 | ⬜ |
| T-7-15 | 写 CHANGELOG.md v3.0 + 最终 PR | 1h | 全部 | 文档完整 | ⬜ |

**里程碑**：所有 P0 验收项 ✅

---

## 依赖关系总图

```
Phase 0 ─┐
         ├── Phase 1 ──┬── Phase 2 ──┬── Phase 3 ──┬── Phase 3.5（质量门禁）─┬── Phase 4 ──┬── Phase 5 ──┐
Phase 6 ─┘             │             │             │                       │             │            │
                       └── Phase 3 ──┘             └── Phase 3 ─────────────┘             └── Phase 6 ─┴── Phase 7
```

- Phase 1 是所有后续的依赖
- Phase 2 和 Phase 3 互不依赖，可并行（建议先 Phase 2，因为 Phase 3 依赖 Pydantic 模型）
- Phase 3.5 依赖 Phase 2（数据层）和 Phase 3（采集器集成点）
- Phase 4 依赖 Phase 3.5（质量 API）
- Phase 5 依赖 Phase 4
- Phase 6 依赖 Phase 4
- Phase 7 依赖全部

---

## 风险与缓解

| 风险 | 影响 | 缓解 | 关联任务 |
|---|---|---|---|
| 旧 `cache_data.json` 导入失败 | 数据丢失 | 备份原文件 + 保留 import 脚本 | T-2-27~29 |
| FTS5 中文分词效果差 | 搜索体验差 | 准备切换 jieba 的备选方案 | T-2-06 |
| 采集源 403/限流 | 数据少 | 已 fallback 兜底 | T-3-04 |
| WAL 模式在某些系统不支持 | 启动失败 | 启动时检测 + 降级日志 | T-2-02 |
| 代理配置破坏 session | 采集失败 | 显式 close + 重连 | T-3-23 |
| 质量门禁误杀正常 item | 数据丢失 | 默认宽松模式 + 严格模式需手动开 + 审计日志回溯 | T-3.5-08~09 |
| 异步 URL 验证拖慢系统 | 性能下降 | 抽样 10% + 后台队列 + 单 URL 8s 超时 | T-3.5-18~21 |
| 分类关键词覆盖不全 | 数据少 | 关键词表可热更新 + 误判 item 走 fallback | T-3.5-05, 13 |

---

## 进度跟踪

### 每周 review 项

- [ ] 当周 Phase 准入标准是否全部 ✅
- [ ] 阻塞项是否需要外部支援
- [ ] 风险项是否触发
- [ ] 下周计划

### 完成判定（最终）

- [ ] Phase 0-7 全部 ✅
- [ ] 通用质量门禁全部通过
- [ ] P0 验收项全部通过
- [ ] CHANGELOG.md 写入 v3.0 条目
- [ ] Tag v3.0.0 发布（**注**：项目版本号 v3.0.0 ≠ API 版本号 1.2.0；项目版本随架构演进，API 版本随接口契约变更）

---

**变更记录**

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-04 | v3.0 | 基于架构优化方案 v3.0 重写；7 个 Phase 共 130 任务；引入依赖图与风险缓解 |

---

## 参考文档

- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [SPEC.md](./SPEC.md)
- [CHECKLIST.md](./CHECKLIST.md)
- [TASKS.md](./TASKS.md)
- [DESIGN_GUIDE.md](../DESIGN_GUIDE.md)
