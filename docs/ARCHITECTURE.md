# 热点地图 · 架构优化方案 v3.0

> 目标：单人使用、轻量级、高性能、稳健可靠、后续扩展性强
> 范围：后端采集 / 存储 / API / 缓存 / 可观测性 全栈重构
> 文档版本：2026-07-04
> 改进计划：[IMPROVEMENT_PLAN.md](./docs/IMPROVEMENT_PLAN.md) (v1.3.0)

---

## 一、目标与原则

### 1.1 业务定位

| 维度 | 目标 |
|---|---|
| 用户量 | 单人本地使用（同一时刻 1 个客户端） |
| 部署 | 单机一键启动，零外部依赖 |
| 数据量 | 优雅支撑 1k → 100k+ 条热点 |
| 启动时间 | < 3s（含冷启动） |
| API 响应 | P95 < 200ms（缓存命中 < 50ms） |
| 故障恢复 | 服务重启数据零丢失；外部源失败不影响整体可用 |

### 1.2 设计原则

1. **本地优先**（Local-First）：所有数据落本地 SQLite，进程崩溃/重启不丢
2. **简单胜过复杂**：单进程、嵌入式存储、零外部服务
3. **写入一次，查询多次**：写入路径重，读取路径极致轻
4. **优雅退化**：单个数据源失败不阻塞其他源；外部网络故障不阻塞缓存读取
5. **可观测但不重型**：结构化日志 + 简单 metrics，**不引入** Prometheus/Grafana
6. **可扩展不预留**：通过抽象类扩展新源，**不为不确定的分布式需求预留接口**

---

## 二、当前架构问题回顾

| # | 问题 | 影响 |
|---|---|---|
| 1 | `cache_data.json` 全量缓存文件 | 数据 10k+ 读盘即超 200ms |
| 2 | `filter_items` 内存级遍历 + 排序 | 每次请求 O(N log N) |
| 3 | HTML 导出动态拼接无模板引擎 | 导出页无主题联动 |
| 4 | 采集器职责混杂（抓取+解析+备用） | 800 行单文件难维护 |
| 5 | 备用数据时间戳倒推造假 | 污染趋势统计 |
| 6 | 进程内单例采集任务 | 慢请求阻塞所有 API |
| 7 | 前后端分类色值不一致（`#00e676` vs `#00c96a`） | 设计规范与实现脱节 |
| 8 | 导出页仍含 HOT/WARM 评分 | 与 DESIGN_GUIDE 冲突 |
| 9 | 零测试 | 改一处坏全局 |
| 10 | 无结构化日志、无错误聚合 | 故障排查靠肉眼 |

---

## 三、目标架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                       Browser (React SPA)                         │
│   Header / CategoryNav / SearchBar / StatsPanel / TrendChart      │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP / JSON
┌────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI 进程 (单进程)                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  API Router    │  │ LRU Cache      │  │  Settings Panel  │   │
│  │  /api/*        │←→│  (in-process)  │  │  /api/proxy/*    │   │
│  └────────┬───────┘  └────────────────┘  └──────────────────┘   │
│           │                                                       │
│  ┌────────▼─────────────────────────────────────────────────┐   │
│  │              Domain Service Layer                          │   │
│  │   HotspotService  ·  TrendService  ·  ExportService       │   │
│  └────────┬──────────────────────────────────────────────────┘   │
│           │                                                       │
│  ┌────────▼─────────┐         ┌────────────────────────────┐    │
│  │  Repository      │←────────│  Scheduler (APScheduler)   │    │
│  │  (SQLite + WAL)  │         │  - 5min: 增量采集           │    │
│  └────────▲─────────┘         │  - 1h:   趋势重算           │    │
│           │                   │  - 24h:  备份 + vacuum     │    │
│  ┌────────┴─────────┐         └────────────────────────────┘    │
│  │  Collector Pool  │                  │                         │
│  │  5 × BaseCollector │←────────────────┘                         │
│  │  (并行、隔离、降级) │                                           │
│  └──────────────────┘                                            │
└──────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        ▼                                         ▼
   ┌─────────┐                              ┌──────────┐
   │ SQLite  │                              │ 日志文件  │
   │ *.db    │                              │ logs/*.log│
   └─────────┘                              └──────────┘
```

### 3.1 关键组件说明

| 组件 | 选型 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 已使用，async + OpenAPI 生态成熟 |
| 主存储 | **SQLite（WAL 模式）** | 零部署、强 SQL、FTS5 全文检索、单文件易备份 |
| 调度 | APScheduler（AsyncIO） | 单进程内调度，无外部 MQ |
| 缓存 | `cachetools.TTLCache`（进程内） | 写入直通，TTL 5min，命中率 > 90% |
| 日志 | `loguru` | 结构化、自动轮转、单文件易查询 |
| HTTP 客户端 | `aiohttp`（保留 ProxySession） | 已稳定 |
| 前端 | React（不变） | 仅调整 API 契约 |

### 3.2 显式不引入

| 不引入 | 原因 |
|---|---|
| Redis / Memcached | 单人本地，进程内 LRU 已够 |
| PostgreSQL / MySQL | 单文件 SQLite 部署成本更低 |
| Celery / Arq / Dramatiq | 进程内 APScheduler 足够，复杂度 -50% |
| Elasticsearch | SQLite FTS5 满足 100k 级全文检索 |
| Docker / K8s | 个人项目，over-engineering |
| Prometheus / Grafana | 单人无需时序监控，log + 简单健康检查足够 |

---

## 四、架构决策记录（ADR）

### ADR-001：采用 SQLite 作为唯一主存储

**决策：** 全部热点数据、趋势快照、采集元信息、用户配置均存 SQLite。

**理由：**
- 单文件 `hotspot.db`，备份 = `cp hotspot.db backup.db`
- WAL 模式下支持并发读 + 单写
- FTS5 虚拟表支持中文分词（tokenizer='unicode61' + 自定义词典）
- 单库支持到 GB 级 → 100 万条热点毫无压力
- p95 查询 < 5ms（带索引）

**后果：**
- 单进程单写：APScheduler 调度采集任务串行化即可
- 多机部署不适用（但单人场景不需要）

### ADR-002：进程内 APScheduler 调度

**决策：** 采集、趋势计算、备份等任务全部在 FastAPI 进程内调度。

**理由：**
- 任务量 < 10 个，APScheduler 完全够用
- 无外部 MQ 依赖，重启即恢复
- 与 FastAPI 共享 asyncio 事件循环

**落地：**
```python
scheduler = AsyncIOScheduler()
scheduler.add_job(collect_all, 'interval', minutes=5, id='collect', max_instances=1)
scheduler.add_job(rebuild_trends, 'interval', hours=1, id='trends')
scheduler.add_job(daily_backup, 'cron', hour=3, id='backup')
```

### ADR-003：写入直通 + 进程内 LRU 缓存

**决策：** 所有写操作同时更新 DB 与 LRU；读操作优先 LRU，未命中再查 DB。

**缓存层级：**
```
L1: 进程内 TTLCache（maxsize=128, ttl=300s）  ← 热点查询
L2: SQLite 查询（含索引）                    ← 冷数据 / 复杂查询
L3: 文件 fallback（断电恢复）                 ← 启动时 warmup
```

**失效策略：**
- 写操作：`cache.pop(key)` + 写 DB
- TTL 到期：自动重查 DB 回填
- 采集完成后：`cache.clear()` 全量失效（避免过期数据）

### ADR-004：强类型 Item Schema（Pydantic）

**决策：** 全栈使用 Pydantic v2 模型定义 item，禁止裸 dict 跨层传递。

```python
class HotspotItem(BaseModel):
    id: str                       # "ai_hn_12345"
    title: str                    # 必填，1-500 字符
    summary: Optional[str] = None # ≤500 字符
    source: str                   # 数据源名
    url: HttpUrl                  # 必须是合法 URL
    category: Literal['ai','security','finance','startup','bid']
    published_at: datetime        # UTC，tz-aware
    score: int = Field(0, ge=0, le=100)
    fetched_at: datetime          # 入库时间
    is_fallback: bool = False     # ★ 关键：标记备用数据，不参与趋势
```

**好处：**
- 采集器解析时即失败暴露脏数据
- 趋势统计可基于 `is_fallback=False` 过滤
- 前后端类型生成（`openapi-typescript`）

### ADR-005：采集器抽象

**决策：** 所有 collector 继承 `BaseCollector`，统一接口、统一异常、统一监控。

```python
class BaseCollector(ABC):
    name: str                                          # "ai" / "security" ...
    source_label: str                                  # "科技/AI"
    enabled: bool = True

    @abstractmethod
    async def fetch(self) -> list[HotspotItem]: ...

    async def collect(self) -> list[HotspotItem]:
        try:
            items = await asyncio.wait_for(self.fetch(), timeout=30)
            return [self._normalize(it) for it in items]
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            log.warning(f"[{self.name}] fetch failed: {e}")
            return await self.fallback()               # 必须实现
```

**强制要求：**
- 每个 collector 必须实现 `fallback()` → 返回 `is_fallback=True` 的 item
- 失败时绝不抛异常上抛，必须降级到 fallback
- 每次 `collect()` 调用必须打点：`duration, count, fallback_count`

---

## 五、数据模型

### 5.1 SQLite Schema

```sql
-- 主表
CREATE TABLE hotspots (
    id           TEXT PRIMARY KEY,         -- 来源内唯一 ID
    title        TEXT NOT NULL,
    summary      TEXT,
    source       TEXT NOT NULL,            -- "aihot" / "Hacker News" / ...
    url          TEXT NOT NULL,
    category     TEXT NOT NULL CHECK(category IN
                    ('ai','security','finance','startup','bid')),
    published_at INTEGER NOT NULL,         -- epoch 秒
    score        INTEGER DEFAULT 0,
    fetched_at   INTEGER NOT NULL,
    is_fallback  INTEGER DEFAULT 0,        -- 0/1
    is_hidden    INTEGER DEFAULT 0         -- 用户手动隐藏
);
CREATE INDEX idx_cat_pub   ON hotspots(category, published_at DESC);
CREATE INDEX idx_pub       ON hotspots(published_at DESC);
CREATE INDEX idx_fallback  ON hotspots(is_fallback, category);

-- 全文检索
CREATE VIRTUAL TABLE hotspots_fts USING fts5(
    id UNINDEXED, title, summary, content='hotspots', content_rowid='rowid'
);
-- 触发器同步
CREATE TRIGGER hotspots_ai AFTER INSERT ON hotspots BEGIN
  INSERT INTO hotspots_fts(rowid, id, title, summary)
  VALUES (new.rowid, new.id, new.title, new.summary);
END;
-- 类似 AFTER DELETE / UPDATE

-- 趋势快照（每小时重算）
CREATE TABLE trend_snapshots (
    bucket_at    INTEGER PRIMARY KEY,      -- 桶起始时间 epoch
    hours_ago    INTEGER NOT NULL,         -- 0-23
    category     TEXT NOT NULL,
    count        INTEGER NOT NULL
);
CREATE INDEX idx_trend_lookup ON trend_snapshots(hours_ago, category);

-- 采集运行日志（轻量级 metrics）
CREATE TABLE collection_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,
    started_at   INTEGER NOT NULL,
    finished_at  INTEGER,
    status       TEXT,                     -- 'success' / 'partial' / 'failed'
    item_count   INTEGER DEFAULT 0,
    fallback_count INTEGER DEFAULT 0,
    error_msg    TEXT
);
CREATE INDEX idx_run_time ON collection_runs(started_at DESC);

-- 用户偏好 / 代理配置（替代 proxy_config.json）
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### 5.2 索引选择理由

| 查询 | 索引 |
|---|---|
| `category=X ORDER BY published_at DESC LIMIT 100` | `idx_cat_pub` |
| `WHERE title LIKE '%kw%'` | `hotspots_fts` FTS5 |
| `WHERE published_at > ts` | `idx_pub` |
| 趋势图查询 | `idx_trend_lookup` |

### 5.3 关键约束

- `category` 仅允许枚举值（CHECK 约束）
- `url` 应用层校验（SQLite 不支持 URL 类型）
- `is_fallback=1` 的数据**不进入** FTS 索引、不进入趋势统计

---

## 六、采集层

### 6.1 调度策略

| 任务 | 频率 | 触发 | 任务时长上限 |
|---|---|---|---|
| 全量采集 | 5 min | interval | 60s |
| 趋势重算 | 1 h | interval | 10s |
| 数据库备份 | 3:00 | cron | 30s |
| FTS 重建 | 24 h | cron | 60s |
| 旧数据清理 | — | — | —（永久保留，无自动清理；如需手动清理使用 CLI 工具） |
| 静态导出预生成 | 30 min | interval | 10s |

### 6.2 采集并发模型

```python
async def collect_all():
    started = time.time()
    collectors = [c for c in ALL_COLLECTORS if c.enabled]
    results = await asyncio.gather(
        *[c.collect() for c in collectors],
        return_exceptions=True
    )
    # 统一入库（单写者）
    for collector, result in zip(collectors, results):
        if isinstance(result, Exception):
            log.error(f"[{collector.name}] {result}")
            continue
        await repo.upsert_many(result, category=collector.name)
    log.info(f"collect_all done in {time.time()-started:.2f}s")
```

**关键原则：**
- `asyncio.gather` 并发抓取，DB 写入串行化
- 单个 collector 失败不影响其他
- 全部完成后才更新 `last_collected_at`

### 6.3 故障降级矩阵

| 故障 | 检测 | 降级动作 |
|---|---|---|
| 单个外部源超时 | `asyncio.TimeoutError` | 该源 fallback，其他源继续 |
| 单个外部源 5xx | HTTP 状态码 | 同上 |
| DNS 失败 | `ClientConnectorError` | 标记该源 30min 内不再尝试 |
| 整个网络断开 | 全部 5 源失败 | 全走 fallback，alert 记录 |
| SQLite 写失败 | `sqlite3.OperationalError` | 重试 3 次 → 报警 + 关闭采集任务 |
| 解析异常 | `ValidationError` | 跳过该条，记录到 `collection_runs.error_msg` |
| 质量门禁失败（严格模式） | 任一 sync gate fail | 拒绝入库 + 记录到 `quality_check_logs` |

### 6.4 质量门禁层

> 位置：`Collector.fetch()` 与 `Repository.upsert()` 之间
> 模式：同步 7 道门禁（快）+ 异步 1 道门禁（深度 URL 内容验证，可选）
> 失败处理：reject / warn 二选一（按 `quality.strict_mode` 配置）

#### 6.4.1 8 个门禁

| # | 门禁 | 同步/异步 | 拒绝条件 | 实现 |
|---|---|---|---|---|
| 1 | Schema 验证 | 同步 | 必填字段缺失、URL 非法、datetime 无效 | Pydantic 校验 |
| 2 | 内容质量 | 同步 | 标题 < 5 或 > 200 字符、摘要 < 10 或 > 500 字符、含 spam 关键词 | 规则引擎 |
| 3 | 分类匹配 | 同步 | 标题+摘要不含目标分类关键词 | 关键词库 |
| 4 | 标题-摘要一致性 | 同步 | 摘要不含标题核心实体、字符重叠度 < 30% | NER + 重叠度 |
| 5 | URL 可达性 | 同步 | HEAD 请求非 2xx、软 404、跳转链 > 3 次 | aiohttp HEAD |
| 6 | URL 内容验证 | **异步** | 抓页面后关键词匹配度 < 40% | aiohttp GET + 解析 |
| 7 | 来源信誉 | 同步 | 来源在黑名单、信誉分 < 30 | 信誉表 + 动态评分 |
| 8 | 跨源去重 | 同步 | URL hash 已存在 或 标题相似度 > 85% | URL hash + 相似度 |

#### 6.4.2 流水线实现

```python
class QualityGatePipeline:
    """在 collector 内部运行"""
    SYNC_GATES = [SchemaGate, ContentQualityGate, CategoryMatchGate,
                  TitleSummaryGate, URLValidityGate, SourceReputationGate,
                  DuplicateGate]
    ASYNC_GATES = [URLContentGate]  # 异步、抽样

    async def run(self, items: list[HotspotItem]) -> list[HotspotItem]:
        passed = []
        for item in items:
            flags = []
            for gate_cls in self.SYNC_GATES:
                gate = gate_cls()
                result = await gate.check(item)
                if result.status == 'fail':
                    if self.config.strict_mode:
                        log.warning(f"rejected by {gate.name}: {result.reason}")
                        break  # 拒绝入库
                    else:
                        flags.append(f"{gate.name}:{result.reason}")
                elif result.flags:
                    flags.extend(result.flags)
            else:
                # 全部通过
                item.quality_score = self._calc_score(flags)
                item.quality_flags = flags
                item.quality_checked_at = datetime.utcnow()
                passed.append(item)
        return passed
```

#### 6.4.3 新增 Schema 字段

```python
class HotspotItem(BaseModel):
    # ... 已有字段
    quality_score: int = 100                    # 0-100，越低问题越多
    quality_flags: list[str] = []               # ['short_title', 'low_url_quality', ...]
    quality_checked_at: Optional[datetime] = None
    url_check_status: Optional[str] = None      # 'pending'/'verified'/'mismatch'/'skipped'
```

#### 6.4.4 新增表

```sql
-- 质量审计日志（追溯每条 item 的门禁结果）
CREATE TABLE quality_check_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       TEXT,
    source        TEXT,
    category      TEXT,
    gate          TEXT NOT NULL,           -- 'schema'/'content'/'category'/...
    status        TEXT NOT NULL,           -- 'pass'/'warn'/'fail'/'skip'
    score         INTEGER,                 -- 该门禁给分（0-100）
    reason        TEXT,
    checked_at    INTEGER NOT NULL
);
CREATE INDEX idx_qclog_item ON quality_check_logs(item_id);
CREATE INDEX idx_qclog_time ON quality_check_logs(checked_at DESC);

-- 来源信誉（动态评分）
CREATE TABLE source_reputation (
    source        TEXT PRIMARY KEY,
    domain        TEXT,
    base_score    INTEGER DEFAULT 70,
    current_score INTEGER DEFAULT 70,      -- 动态调整
    total_items   INTEGER DEFAULT 0,
    accepted      INTEGER DEFAULT 0,
    rejected      INTEGER DEFAULT 0,
    last_updated  INTEGER
);
```

#### 6.4.5 新增配置（settings 表）

| key | 类型 | 默认 | 说明 |
|---|---|---|---|
| `quality.strict_mode` | bool | `false` | true=拒绝 / false=warn+flag |
| `quality.min_score` | int | 50 | 低于此分拒绝（严格模式生效时） |
| `quality.url_check_enabled` | bool | `true` | 异步 URL 内容验证总开关 |
| `quality.url_check_sample_rate` | float | 0.1 | 异步抽样率（0-1） |
| `quality.url_check_timeout` | int | 8 | 单 URL 超时（秒） |
| `quality.category_keywords` | json | 见下 | 分类关键词表 |

**分类关键词默认配置**（可在 settings 表覆盖）：
```json
{
  "ai":       ["AI", "大模型", "LLM", "GPT", "Claude", "Gemini", "Llama", "深度学习", "神经网络", "机器学习", "开源模型", "Agent", "RAG", "AIGC", "Diffusion", "Sora", "Transformer", "NVIDIA", "GPU", "CUDA"],
  "security": ["漏洞", "CVE", "黑客", "渗透", "入侵", "勒索", "APT", "数据泄露", "加密", "防火墙", "XSS", "CSRF", "SOC", "XDR", "零信任", "等保", "ATT&CK", "红队", "蓝队", "恶意软件"],
  "finance":  ["A股", "港股", "美股", "基金", "股票", "汇率", "央行", "降准", "降息", "IPO", "财报", "上市公司", "沪指", "深成", "恒生", "标普", "纳指", "大宗商品", "金价", "油价"],
  "startup":  ["SaaS", "独立开发", "Indie Hacker", "Show HN", "Launch HN", "MRR", "ARR", "订阅", "产品上线", "Beta", "副业", "自由职业", "远程工作", "产品发布", "种子轮", "A轮"],
  "bid":      ["招标", "采购", "中标", "投标", "公告", "磋商", "询价", "公开招标", "竞争性谈判", "资格预审", "政府采购", "央企", "运营商", "电力"]
}
```

#### 6.4.6 新增 API

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/quality/summary` | 整体质量概况（通过率、平均分、Top 问题） |
| GET | `/api/quality/rules` | 查看门禁配置 |
| PUT | `/api/quality/rules` | 更新门禁配置 |
| GET | `/api/quality/logs?item_id=` | 单条 item 的门禁追溯 |

#### 6.4.7 调度任务

| 任务 | 频率 | 触发 | 说明 |
|---|---|---|---|
| 异步 URL 内容验证 | 持续 | 采集完成后 | 抽样检查，更新 `url_check_status` |
| 来源信誉重算 | 6 h | interval | 基于过去 7 天的门禁结果重算 `current_score` |

---

## 七、API 层

### 7.1 接口清单

| Method | Path | 说明 | 缓存键 |
|---|---|---|---|
| GET | `/api/hotspots` | 热点列表（支持分页） | `hotspots:{cat}:{time}:{kw}:{cursor}` |
| GET | `/api/hotspots/{id}` | 单条详情 | `item:{id}` |
| GET | `/api/trends` | 24h 趋势 | `trends:current` |
| GET | `/api/categories` | 分类元数据 | `categories`（静态，永久缓存） |
| GET | `/api/health` | 健康检查 | 无缓存 |
| GET | `/api/stats` | 后台统计（采集次数、命中率） | 无缓存 |
| GET | `/api/export` | 静态 HTML 导出 | 预生成文件 |
| GET/PUT | `/api/proxy/settings` | 代理配置 | 写后失效 `cache.clear()` |
| GET | `/api/proxy/test` | 代理连通性测试 | 无缓存 |

### 7.2 `/api/hotspots` 契约

**请求：**
```
GET /api/hotspots
  ?category=ai|security|finance|startup|bid|all  (default: all)
  &time_range=24h|3d|7d|30d                        (default: 7d)
  &keyword=xxx                                      (optional)
  &cursor=<published_at>_<id>                       (optional, 分页用)
  &limit=100                                        (max 200)
```

**响应：**
```json
{
  "items": [ HotspotItem, ... ],
  "total": 1234,
  "category_counts": { "ai": 200, "security": 150, ... },
  "next_cursor": "1717392000_ai_hn_12345",     // null 表示无更多
  "fetched_at": "2026-07-04T12:00:00Z",
  "cache_hit": true
}
```

**关键变化：** 引入 `cursor` 分页，避免一次性返回大列表。

### 7.3 错误码规范

| HTTP | code | 含义 |
|---|---|---|
| 400 | `INVALID_PARAM` | 参数越界/类型错误 |
| 404 | `NOT_FOUND` | ID 不存在 |
| 429 | `RATE_LIMITED` | 触发本地限流 |
| 500 | `INTERNAL` | 内部异常（含 trace_id 便于查询日志） |
| 503 | `SOURCE_UNAVAILABLE` | 所有源失败（仍在降级服务） |

### 7.4 性能预算

| 接口 | 缓存命中 | 未命中 |
|---|---|---|
| `/api/hotspots` | < 50ms | < 200ms |
| `/api/trends` | < 30ms | < 100ms |
| `/api/categories` | < 5ms | < 5ms |
| `/api/export` | 静态文件直出 < 50ms | — |

---

## 八、缓存层

### 8.1 缓存键规范

```
hotspots:{category}:{time_range}:{keyword_hash}:{cursor}
item:{id}
trends:current
categories
```

### 8.2 失效策略

| 事件 | 失效动作 |
|---|---|
| 采集完成 | `cache.pop("hotspots:*")` 全清 |
| 代理设置变更 | `cache.clear()` 全清 |
| 用户手动隐藏 | 仅失效 `hotspots:all:*` |
| 进程启动 | 从 SQLite warmup 5 个最热键 |

### 8.3 LRU 配置

```python
from cachetools import TTLCache

# 主列表缓存
list_cache = TTLCache(maxsize=64, ttl=300)     # 5min TTL
# 详情缓存
item_cache = TTLCache(maxsize=2000, ttl=600)    # 10min TTL
# 静态数据
static_cache = TTLCache(maxsize=16, ttl=86400)  # 24h
```

---

## 九、可靠性设计

### 9.1 数据持久化

- **WAL 模式**：`PRAGMA journal_mode=WAL` → 崩溃安全 + 并发读
- **同步级别**：`PRAGMA synchronous=NORMAL` → 性能与安全平衡
- **定期 checkpoint**：每 1h 触发 `PRAGMA wal_checkpoint(TRUNCATE)`
- **每日备份**：3:00 复制 `hotspot.db` → `backups/hotspot-{date}.db`（保留 7 份）

### 9.2 进程启动恢复

```python
async def startup():
    await repo.connect()
    # warmup 关键缓存
    await warmup_cache()
    # 启动调度
    scheduler.start()
    log.info(f"Service ready in {time.time()-start:.2f}s")
```

启动序列：
1. 打开 SQLite → 检测/修复
2. 应用 schema migration
3. 启动后台调度器
4. 立刻触发一次 collect（不阻塞 ready）
5. warmup 缓存
6. 监听端口

### 9.3 错误处理

| 层级 | 策略 |
|---|---|
| 采集器 | 永不抛异常上抛，必须 fallback |
| Repository | 重试 3 次（指数退避），仍失败则保留旧数据 |
| API 层 | 统一异常处理器，返回结构化错误 + trace_id |
| 调度器 | 任务失败不杀死调度，下次继续 |

### 9.4 健康检查增强

```json
GET /api/health
{
  "status": "ok",
  "uptime_s": 3600,
  "db": { "size_mb": 12.3, "items": 1234, "wal": "ok" },
  "scheduler": { "running": true, "last_collect_at": "...", "next_collect_at": "..." },
  "collectors": {
    "ai":       { "last_status": "success", "last_items": 80, "last_run": "..." },
    "security": { "last_status": "partial", "last_items": 60, "last_run": "..." },
    ...
  },
  "cache":   { "hit_rate": 0.92, "size": 64 },
  "proxy":   { "mode": "auto", "ok": true }
}
```

---

## 十、可观测性

### 10.1 日志规范

- 库：`loguru`
- 格式：JSON Lines
- 轮转：单文件 50MB，保留 5 个
- 字段：`ts, level, module, msg, trace_id, category, duration_ms, item_count`

**示例：**
```json
{"ts":"2026-07-04T12:00:00Z","level":"INFO","module":"ai_collector",
 "msg":"collect done","category":"ai","duration_ms":3200,
 "item_count":78,"fallback_count":0}
```

### 10.2 轻量级指标（不进 Prometheus）

写入 `collection_runs` 表 + 内存计数器：

| 指标 | 来源 | 展示位置 |
|---|---|---|
| 每次采集耗时 | `collection_runs.finished_at - started_at` | `/api/health` |
| 缓存命中率 | 内存 `hits / (hits+misses)` | `/api/health` |
| 趋势数据完整度 | `trend_snapshots` 最新 bucket | `/api/health` |
| 失败率 | `collection_runs WHERE status='failed' / total` | `/api/health` |

---

## 十一、可扩展性设计

### 11.1 添加新数据源

**工作量：~30 分钟**

```python
# 1. 新建文件 backend/collectors/new_category_collector.py
class NewCategoryCollector(BaseCollector):
    name = "newcat"
    source_label = "新分类"

    async def fetch(self) -> list[HotspotItem]:
        async with ProxySession() as session:
            async with session.get("https://example.com/api") as r:
                data = await r.json()
                return [self._to_item(x) for x in data["items"]]

    def _to_item(self, raw) -> HotspotItem:
        return HotspotItem(
            id=f"newcat_{raw['id']}",
            title=raw["title"],
            url=raw["url"],
            category="newcat",
            published_at=parse_dt(raw["date"]),
            ...
        )

    async def fallback(self) -> list[HotspotItem]:
        return [...]  # 至少 5 条

# 2. 注册到 collectors/__init__.py
ALL_COLLECTORS.append(NewCategoryCollector())

# 3. 更新 frontend CATEGORIES
# 4. 分配分类色（与 design-taste 协商）
# 5. 重启服务（或热加载）
```

### 11.2 添加新分类色

修改 `frontend/src/types/index.ts` 中 `CATEGORIES`，**色值必须同步到后端** `CATEGORY_CONFIG` 常量（可由 openapi-typescript 自动同步避免漂移）。

### 11.3 添加新 API

- 在 `backend/api/` 下新增 router
- 在 `main.py` 中 `app.include_router(...)`
- 前端 `openapi-typescript` 重新生成类型

### 11.4 演进路径（按需触发）

| 触发条件 | 演进动作 |
|---|---|
| 数据量 > 100k 或 P95 > 500ms | 引入 Redis 替换 LRU |
| 多端同时使用 | 引入 PostgreSQL + 进程间锁 |
| 采集源 > 20 个 | 拆出独立采集 worker（独立进程） |
| 需要全文高亮 | 引入 ES 替代 FTS5 |

---

## 十二、目录结构（目标态）

```
hotspot-map/
├── backend/
│   ├── main.py                      # FastAPI 入口
│   ├── config.py                    # 路径、TTL、端口等配置
│   ├── domain/
│   │   ├── models.py                # Pydantic 模型
│   │   ├── enums.py                 # Category, TimeRange
│   ├── api/
│   │   ├── hotspots.py              # /api/hotspots*
│   │   ├── trends.py                # /api/trends
│   │   ├── proxy.py                 # /api/proxy/*
│   │   ├── health.py                # /api/health, /api/stats
│   │   └── export.py                # /api/export
│   ├── services/
│   │   ├── hotspot_service.py       # 业务编排
│   │   ├── trend_service.py
│   │   └── export_service.py
│   ├── repository/
│   │   ├── db.py                    # SQLite 连接 + 迁移
│   │   ├── hotspot_repo.py          # CRUD + FTS
│   │   ├── trend_repo.py
│   │   └── settings_repo.py
│   ├── collectors/
│   │   ├── base.py                  # BaseCollector 抽象
│   │   ├── ai_collector.py
│   │   ├── security_collector.py
│   │   ├── finance_collector.py
│   │   ├── startup_collector.py
│   │   └── bid_collector.py
│   ├── scheduler/
│   │   ├── jobs.py                  # 任务定义
│   │   └── scheduler.py             # APScheduler 包装
│   ├── proxy/
│   │   ├── config.py                # 代理配置（合并）
│   │   └── session.py               # ProxySession
│   ├── cache.py                     # 进程内 LRU
│   ├── logging_config.py            # loguru 配置
│   ├── exceptions.py                # 自定义异常 + handler
│   ├── tests/                       # 单元测试
│   │   ├── test_repository.py
│   │   ├── test_collectors.py
│   │   └── test_api.py
│   └── hotspot.db                   # SQLite 数据库
├── frontend/                        # 仅调整 API 契约，不动 UI
└── docs/
    ├── ARCHITECTURE.md              # 本文档
    ├── DATA_SCHEMA.md               # Item schema 定义
    └── RUNBOOK.md                   # 运维手册
```

---

## 十三、风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|---|
| 1 | SQLite 写锁阻塞 | 低 | 中 | WAL 模式 + 串行化写入队列 |
| 2 | 单进程崩溃 | 低 | 高 | 调度任务用 `try/except` 隔离，崩溃只丢当次任务 |
| 3 | 磁盘写满 | 极低 | 高 | 每日 backup + vacuum + 无自动清理（用户自管） |
| 4 | 时区混乱 | 中 | 中 | 全部 UTC 入库，前端按本地时区显示 |
| 5 | FTS5 中文分词差 | 中 | 低 | unicode61 tokenizer 够用；进阶可换 jieba |
| 6 | 代理热更新不生效 | 中 | 低 | 显式 `session.close()` + 重连检测 |
| 7 | 备用数据污染趋势 | 已发生 | 中 | `is_fallback` 字段 + 趋势查询过滤 |
| 8 | 设计规范与代码漂移 | 中 | 中 | openapi-typescript + 色值常量表 |
| 9 | 质量门禁误杀正常 item | 中 | 中 | 默认宽松模式 + 灰度切严格 + 审计日志回溯 |
| 10 | 异步 URL 验证拖慢系统 | 中 | 低 | 抽样 10% + 后台队列 + 超时 8s |
| 11 | 分类关键词覆盖不全 | 高 | 中 | 关键词表可热更新 + 误判 item 走 fallback 不入库 |

---

## 十四、实施计划

### Phase 1：基础设施（1 天）
- [ ] 建 `docs/` 目录，输出本文档
- [ ] 引入 loguru、cachetools、APScheduler、pydantic v2
- [ ] 建 `backend/logging_config.py` 结构化日志
- [ ] 建 `backend/exceptions.py` + 全局 handler

### Phase 2：数据层（2 天）
- [ ] 建 `backend/repository/db.py`：SQLite + WAL + migration
- [ ] 建 `backend/domain/models.py`：Pydantic models
- [ ] 建 `backend/repository/hotspot_repo.py`：CRUD + FTS5
- [ ] 写迁移脚本，从 `cache_data.json` 导入历史数据
- [ ] **关键决策**：`is_fallback` 字段对历史备用数据打标

### Phase 3：抽象与采集层重构（3 天）
- [ ] 建 `backend/collectors/base.py` BaseCollector
- [ ] 重构 5 个 collector 实现 fallback
- [ ] 建 `backend/scheduler/` 任务调度
- [ ] 接入代理感知（保留 ProxySession）

### Phase 4：API 层重构（2 天）
- [ ] 拆 `main.py` → `api/` 多 router
- [ ] 实现 cursor 分页
- [ ] 接入 LRU 缓存
- [ ] 实现 `/api/health` 增强版

### Phase 5：可观测性 + 测试（2 天）
- [ ] 写 `test_repository.py` 覆盖核心 SQL
- [ ] 写 `test_collectors.py` 至少覆盖 base + 1 个真实源
- [ ] 写 `test_api.py` 覆盖 3 个核心接口
- [ ] 完成 RUNBOOK.md

### Phase 6：前端适配（0.5 天）
- [ ] 适配新 `/api/hotspots` 响应（含 `next_cursor`）
- [ ] 适配 `/api/health` 状态展示（可选）
- [ ] 修正前后端分类色值不一致
- [ ] 移除导出页 HOT/WARM 标签

### Phase 7：试运行（1 天）
- [ ] 跑 24h，观察采集成功率、缓存命中率、P95
- [ ] 模拟网络断开 / 数据源失败 → 验证降级
- [ ] 模拟进程崩溃 → 验证启动恢复

**总计：~10 人日**

---

## 十五、验收标准

架构优化完成的判据：

1. ✅ `python -m backend` 单条命令启动，无外部依赖
2. ✅ 数据 1k → 10k → 100k 三档下，API P95 全部 < 200ms
3. ✅ 单个 collector 失败时其他源正常入库
4. ✅ 进程崩溃后重启，数据零丢失
5. ✅ 添加新数据源可在 30 分钟内完成
6. ✅ 单元测试覆盖率 > 60%（重点：repository + collector base）
7. ✅ DESIGN_GUIDE.md 与代码无冲突
8. ✅ 所有 API 错误响应符合统一错误码规范

---

**附录 A：术语表**
- **fallback 数据**：外部源失败时返回的预置数据，必须打标
- **cursor 分页**：基于 `(published_at, id)` 游标的分页，避免 OFFSET 性能问题
- **WAL 模式**：Write-Ahead Logging，SQLite 的并发优化模式
- **写入直通**（write-through）：写操作同时更新缓存与存储

**附录 B：参考**
- [SQLite WAL 模式](https://www.sqlite.org/wal.html)
- [Pydantic v2 文档](https://docs.pydantic.dev/latest/)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [cachetools](https://github.com/tkem/cachetools)

## 参考文档

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [SPEC.md](./docs/SPEC.md)
- [CHECKLIST.md](./docs/CHECKLIST.md)
- [TASKS.md](./docs/TASKS.md)
- [DESIGN_GUIDE.md](./DESIGN_GUIDE.md)
