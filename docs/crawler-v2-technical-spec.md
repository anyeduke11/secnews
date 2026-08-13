# Crawler v2 — 正式技术方案

> **版本**: v0.1
> **日期**: 2026-08-01
> **状态**: 待评审
> **前置文档**: `docs/crawler-v2-design.md`（设计稿，本方案基于其上做批判性修订与补充）
> **范围**: 爬虫体系全链路重构 — 源注册、调度、抓取、解析、质检、去重、存储、观测、迁移

---

## 1. 第一性原理与设计原则

### 1.1 五条不可违背定律

| # | 第一性原理 | 推导约束 | 违反代价 |
|---|-----------|---------|---------|
| FP1 | **资讯源是外部实体，不可控** | 任何源随时可能失败；系统必须假设失败是常态 | 死源反复重试浪费资源，活源延迟 |
| FP2 | **用户注意力是稀缺资源** | 一条高质量信息 > 十条噪声；宁空毋滥 | 用户流失，信任崩塌 |
| FP3 | **系统资源有限** | 死源消耗的 CPU/带宽/时间应被活源复用 | 单机瓶颈，整体吞吐下降 |
| FP4 | **无法测量的系统无法改进** | 每个环节必须可观测 | 故障黑盒，调优靠猜 |
| FP5 | **变更不可避免** | 源改版、反爬升级、策略调整是常态 | 系统僵化，维护成本指数增长 |

### 1.2 设计决策优先级

```
正确性 > 及时性 > 覆盖度 > 资源效率
```

- 抓一条错误信息比晚抓一条正确信息更糟糕
- 覆盖 50 个活源好于覆盖 120 个源但其中 77 个是死的

---

## 2. 架构总览

### 2.1 组件关系

```
┌─────────────────────────────────────────────────────────────────┐
│                      配置层 (Source Registry)                     │
│  crawler_sources 表 + YAML seed + parser 注册表                   │
└──────────────┬──────────────────────────────────────────────────┘
               │ 按源配置读取
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      调度层 (Scheduler)                           │
│  源级周期调度 + 优先级队列 + 失败退避 + 冷却/复活 + 防重锁          │
└──────────────┬──────────────────────────────────────────────────┘
               │ 按优先级出队
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      抓取层 (Fetcher)                             │
│  ┌──────┐  ┌────────┐  ┌──────┐  ┌──────────┐                  │
│  │ RSS  │  │ JSON   │  │ HTML │  │ Browser  │                  │
│  │(httpx)│  │(httpx) │  │(httpx)│  │(crawl4ai)│                  │
│  └──────┘  └────────┘  └──────┘  └──────────┘                  │
│  统一 BackendSession (代理/重试/限速/UA/超时)                     │
└──────────────┬──────────────────────────────────────────────────┘
               │ 原始响应
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      解析器注册表 (Parser Registry)                │
│  每源独立 parser (parse_list + parse_detail) + 版本化 + 测试      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ rss_generic│  │ ithome  │  │ freebuf │  │ ccgp     │ ...    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└──────────────┬──────────────────────────────────────────────────┘
               │ RawItem[]
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      标准化层 (Normalizer)                        │
│  时间统一 UTC + URL 绝对化/去 tracking + 摘要 trafilatura 提取      │
│  标讯结构化字段 (DOM > regex > LLM 兜底)                          │
└──────────────┬──────────────────────────────────────────────────┘
               │ NormalizedItem[]
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      质量门禁 (Quality Gates)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Hard Gate│  │ Soft Gate │  │URL 校验  │  │ 去重     │        │
│  │ (拒绝)   │  │ (扣分)    │  │(全量)    │  │3层)     │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│  → 拒绝条目写入 quality_rejection_log（审计视图）                  │
└──────────────┬──────────────────────────────────────────────────┘
               │ 通过条目
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      存储层 (Storage)                             │
│  raw_items (溯源) → hotspots (展示) + bid_details (结构化)        │
│  raw_items 保留 30 天滚动清理                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流（带错误处理）

```
[调度] → [抓取] ─成功→ [解析] ─成功→ [标准化] → [质检] → [去重] → [存储]
                  │                  │          │
                  ├─超时→ 重试3次→    │          ├─Hard拒绝→ quality_rejection_log
                  │   ─全失败→ 记录   │          └─Soft扣分→ 继续流转
                  │   consecutive_fail│
                  ├─HTTP 4xx/5xx→     ├─解析器崩溃→ 标记 parser_crashed
                  │  记录失败计数     │  禁用该源
                  └─DNS/网络→ 退避   └─解析器超时→ 超时 kill
```

---

## 3. 核心组件详细设计

### 3.1 源注册表 (Source Registry)

#### 3.1.1 数据模型

```sql
CREATE TABLE crawler_sources (
    id                  TEXT PRIMARY KEY,          -- 全局稳定源 ID
    category            TEXT NOT NULL,             -- 'security' | 'ai' | 'bid' | 'finance' | ...
    name                TEXT NOT NULL,             -- 人类可读名称
    kind                TEXT NOT NULL,             -- 'rss' | 'json' | 'html' | 'browser' | 'disabled'
    parser_id           TEXT NOT NULL,             -- 解析器注册名
    url                 TEXT,                      -- 首页/列表页 URL
    feed_url            TEXT,                      -- RSS/Atom URL
    api_url             TEXT,                      -- JSON API URL
    cadence_seconds     INTEGER NOT NULL DEFAULT 300,   -- 抓取周期
    priority            INTEGER NOT NULL DEFAULT 50,    -- 0-100, 高优先先执行
    max_items           INTEGER NOT NULL DEFAULT 50,    -- 单轮上限
    enabled             INTEGER NOT NULL DEFAULT 1,
    use_proxy           TEXT NOT NULL DEFAULT 'auto',   -- 'off' | 'auto' | 'required'
    headers             TEXT,                      -- JSON 自定义请求头
    verify_ssl          INTEGER NOT NULL DEFAULT 1,
    -- 增量抓取缓存
    etag                TEXT,
    last_modified       TEXT,
    last_fetch_at       TEXT,
    -- 健康状态
    last_success_at     TEXT,
    last_yield_at       TEXT,                      -- 最后一次有产出的时间
    last_error          TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until      TEXT,                      -- 冷却结束时间
    health_score        REAL NOT NULL DEFAULT 1.0, -- 0.0-1.0
    status              TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'grace' | 'stale' | 'dead' | 'disabled'
    -- 冷启动标记
    first_fetch         INTEGER NOT NULL DEFAULT 1, -- 首次抓取全量模式
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
```

#### 3.1.2 健康状态机（增强版）

```
                   ┌──────────────────────────────────────┐
                   │             active                    │
                   │  (正常运行，有产出)                     │
                   └───┬──────────────────────────┬────────┘
                       │ 连续失败 3 次              │ 单轮产出 > 0
                       ▼                          │ 重置失败计数
                   ┌──────────────────────┐        │
                   │       stale          │────────┘
                   │  (连续失败，需关注)    │
                   └───┬──────────────────┘
                       │ 连续失败 5 次
                       ▼
                   ┌──────────────────────┐
                   │       dead           │
                   │  (已死，停止调度)      │
                   └───┬──────────────────┘
                       │ 探活成功 (HEAD/GET 200)
                       ▼
                   ┌──────────────────────┐
                   │       grace          │ ◄── 新增
                   │  (观察期，恢复中)      │
                   └───┬──────────────────┘
                       │ 连续 3 轮有产出
                       ▼
                   ┌──────────────────────┐
                   │       active         │
                   └──────────────────────┘
```

**关键差异**:
- 新增 `grace` 状态：探活成功 ≠ 真实恢复，需要观察期验证
- `dead` 状态停止调度，释放资源给其他源
- `grace` 状态按正常周期调度，但不计入"活跃源"统计

#### 3.1.3 冷启动策略

| 场景 | 行为 |
|------|------|
| 新源首次注册 | `first_fetch=1`，`max_items` 翻倍，全量模式 |
| 系统重启 | 从 `crawler_sources` 恢复所有源状态，冷却中的继续冷却 |
| 新用户首次部署 | 种子数据加载后，立即执行一轮全量抓取（不等待周期） |
| 源从 dead 恢复 | 进入 `grace` 状态，观察 3 轮 |

### 3.2 调度器 (Scheduler)

#### 3.2.1 调度规则

| 规则 | 实现 |
|------|------|
| 基础周期 | 每源读 `cadence_seconds`，独立定时 |
| 优先级队列 | 高优先源先执行，同类并发度受限（默认 3） |
| 失败退避 | 连续失败 3 次 → `stale`，5 次 → `dead`，`cooldown_until` 指数增长 |
| 成功恢复 | 一次有产出即回 `active`，重置失败计数 |
| 死源探活 | 每天固定时间 HEAD/GET 探活，恢复后入 `grace` |
| 增量抓取 | 记录 `etag` / `last_modified`，只抓新增 |
| 运行防重 | 全局限流锁 + 每源单实例锁 |
| 资源重分配 | 死源释放的调度槽自动分配给同分类活跃源 |

#### 3.2.2 单源故障隔离

| 故障 | 隔离策略 |
|------|---------|
| 解析器崩溃 | 在 `asyncio.wait_for` 中执行，超时 kill；连续 3 次崩溃 → 禁用源 |
| 解析器内存泄漏 | 考虑 `run_in_executor` 隔离到线程池 |
| 抓取超时 | `BackendSession` 统一超时控制，不阻塞其他源 |
| 网络抖动 | 自动重试 3 次（指数退避），全部失败计入失败计数 |

### 3.3 抓取层 (Fetcher)

#### 3.3.1 统一 BackendSession

`BackendSession`（已在 `backend/collectors/session.py`）必须成为所有抓取路径的唯一入口：

| 特性 | 说明 |
|------|------|
| 协议 | HTTP/HTTPS（httpx async） |
| 代理 | 统一 `proxy_config.json`，每源可覆盖 `use_proxy` |
| 重试 | 指数退避，最多 3 次 |
| 限速 | 每源每秒最多 N 请求 |
| 超时 | 连接 10s + 读取 30s |
| UA | 每源可配置 |
| 增量 | ETag + If-Modified-Since |

**接入路径**:
- RSS: `httpx GET → feedparser.parse(bytes)` — 禁止 `feedparser.parse(url)` 直接联网
- JSON: `httpx GET → resp.json()`
- HTML: `httpx GET → lxml/selectolax` 
- Browser: `crawl4ai AsyncWebCrawler`（单例）

#### 3.3.2 浏览器抓取服务 (BrowserFetchService)

收敛现有三套 crawl4ai 实现为单一服务：

```python
class BrowserFetchService:
    """单一浏览器抓取服务，全局单例"""
    
    crawler: AsyncWebCrawler       # 单例
    semaphore: asyncio.Semaphore   # 全局并发控制（默认 3）
    budget: int                    # 每轮浏览器抓取预算
    stats: dict                    # 使用统计
    
    async def fetch(self, url: str, source_id: str) -> FetchResult:
        """带预算和降级的浏览器抓取"""
        if self.budget <= 0:
            raise NoBudgetError("本轮浏览器预算已用完")
        async with self.semaphore:
            self.budget -= 1
            return await self.crawler.arun(url)
    
    def reset_budget(self, amount: int = 10):
        """每轮开始时重置预算"""
        self.budget = amount
```

**降级链**: `browser → html → 放弃`

### 3.4 解析器注册表 (Parser Registry)

#### 3.4.1 接口规范

```python
class BaseParser:
    parser_id: str          # 全局唯一
    version: str            # semver, 站点改版时递增
    source_id: str          # 关联的源 ID
    
    def parse_list(self, content: str, source: SourceConfig) -> list[RawItem]:
        """解析列表页，返回候选条目"""
        ...
    
    def parse_detail(self, content: str, item: RawItem) -> RawItem:
        """解析详情页，富化条目"""
        ...
```

#### 3.4.2 目录结构

```
backend/parsers/
├── registry.py             # parser_id -> Parser 映射
├── base.py                 # BaseParser + RawItem
├── rss_generic.py          # 通用 RSS parser (version 1.0.0)
├── json_generic.py         # 通用 JSON API parser
├── html_generic.py         # 仅允许配置化 CSS 选择器
├── news/
│   ├── ithome.py           #  ithome 独立 parser
│   ├── freebuf.py
│   └── ...
├── bid/
│   ├── ccgp.py             # 中国政府采购网
│   ├── cebpub.py           # 中国招标投标公共服务平台
│   └── ...
└── tests/                  # 每源独立测试
    ├── test_ithome.py
    ├── test_ccgp.py
    └── ...
```

### 3.5 标准化层 (Normalizer)

#### 3.5.1 标讯字段提取优先级（明确写死）

```
DOM 选择器 > 正则表达式 > LLM 兜底
```

| 字段 | P0 源要求 | P1 源要求 | LLM 兜底限制 |
|------|----------|----------|-------------|
| bid_no | DOM 选择器 | 正则 | 每轮 ≤ 20 次 |
| buyer | DOM 选择器 | 正则 | 同上 |
| region | DOM 选择器 | 正则 | 同上 |
| budget | DOM 选择器 | 正则（可选） | 同上 |
| deadline | DOM 选择器 | 正则（可选） | 同上 |
| bid_status | 标题正则 | 标题正则 | 不启用 LLM |
| industry | 关键词映射 | 关键词映射 | 不启用 LLM |

**LLM 路径约束**:
- 仅当 DOM 和正则都无法提取时才启用
- 每轮总调用次数 ≤ 20
- 每次调用超时 ≤ 5s
- 失败不阻塞主流程，字段留空

### 3.6 质量门禁 (Quality Gates)

#### 3.6.1 分层门禁

| 类型 | 门禁 | 行为 | 审计 |
|------|------|------|------|
| Hard | Schema 校验 | 不通过则拒绝 | 记录到 `quality_rejection_log` |
| Hard | 原文 URL 验证 | 非文章页 URL 拒绝 | 同上 |
| Hard | published_at 有效性 | 无法解析/未来时间拒绝 | 同上 |
| Hard | 噪声黑名单 | 命中黑名单拒绝 | 同上 |
| Hard | 重复条目 | 3 层去重后仍重复拒绝 | 同上 |
| Soft | 标题质量 | 扣分 0-10 | 记录分数 |
| Soft | 摘要质量 | 扣分 0-10 | 同上 |
| Soft | 来源信誉 | 扣分 0-10 | 同上 |
| Soft | 内容相关度 | 扣分 0-10 | 同上 |

#### 3.6.2 URL 全量校验（从抽样改为全量）

```
新条目: 100% 校验
已入库条目: 每 24h 复检一次
校验结果: 写入 crawl_url_checks，不再长期停在 pending
```

#### 3.6.3 审计视图

```sql
CREATE TABLE quality_rejection_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,
    item_title      TEXT NOT NULL,
    item_url        TEXT NOT NULL,
    rejected_by     TEXT NOT NULL,     -- gate 名称
    reason          TEXT NOT NULL,     -- 拒绝原因
    raw_data        TEXT,              -- 原始数据（调试用）
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

每 gate 暴露 `rejection_rate` 指标（rejected / total），异常升高时自动告警。

### 3.7 去重层 (Deduplicator)

三层去重，顺序执行：

| 层 | 算法 | 作用 | 范围 |
|----|------|------|------|
| URL | `canonicalize_url` | 同源同链接去重 | 全库 |
| 标题 | simhash + Hamming < 5 | 跨源近似标题去重 | 最近 30 天 |
| 正文 | content_hash (SHA256) | 详情页与 RSS 混抓去重 | 最近 30 天 |

同 URL 多标题时选 winner 规则：
1. `url_check_status = 'verified'`
2. 来源信誉高
3. 非 fallback 抓取
4. 抓取时间最近

### 3.8 存储层 (Storage)

#### 3.8.1 新增表

| 表 | 用途 | 保留策略 | 与现有表关系 |
|----|------|---------|-------------|
| `crawler_sources` | 源配置 + 健康状态 | 永久 | 替代现有硬编码配置 |
| `raw_items` | 原始抓取数据 | 30 天滚动清理 | `hotspots` 的溯源来源 |
| `crawler_runs` | 每源每轮抓取记录 | 7 天滚动清理 | 聚合生成 `source_stats` |
| `crawl_url_checks` | URL 校验结果 | 7 天滚动清理 | 校验结果 |
| `bid_details` | 标讯结构化字段 | 永久 | 关联 `hotspots.id` |
| `quality_rejection_log` | 质量门禁拒绝记录 | 7 天滚动清理 | 审计用途 |

#### 3.8.2 保留策略

```
raw_items:      30 天 → 自动清理
crawler_runs:   7 天 → 自动清理（统计聚合后原始记录可删）
crawl_url_checks: 7 天 → 自动清理
quality_rejection_log: 7 天 → 自动清理
```

### 3.9 观测层 (Observability)

#### 3.9.1 每源每轮指标

| 指标 | 来源 | 阈值 |
|------|------|------|
| fetched_count | 抓取候选数 | — |
| accepted_count | 通过门禁数 | — |
| rejection_rate | 被拒数 / 总数 | 异常升高 > 30% 告警 |
| http_status | 抓取 HTTP 状态码 | 4xx/5xx 告警 |
| duration_ms | 耗时 | P95 > 30s 告警 |
| parser_version | 使用的解析器版本 | 站点改版时需关注 |
| url_check_pass_rate | URL 校验通过率 | < 80% 告警 |

#### 3.9.2 告警规则

| 告警 | 条件 | 级别 |
|------|------|------|
| 分类有效源数低于阈值 | 某分类活跃源 < 3 | P1 |
| 核心 P0 源连续失败 | 连续失败 5 次 | P1 |
| 单源产出异常偏离 | 产出偏离基线 > 50% | P2 |
| URL 校验失败率异常 | 失败率 > 20% | P2 |
| 标讯命中技术栈/关键词 | 标讯标题含配置的关键词 | 通知 |

---

## 4. 标讯专项设计（修订版）

### 4.1 源分级（修订）

| 级别 | 来源类型 | 策略 | 搜索引擎 |
|------|---------|------|---------|
| P0 | 国家级/权威平台 | 官方列表接口或列表页优先，周期 15-30 分钟 | ❌ 不使用 |
| P1 | 金融/能源/电信等行业平台 | 优先 RSS/JSON，周期 30 分钟 | ❌ 不使用 |
| P2 | 商业聚合平台 | 仅作为补充，必须能拿到原始公告 URL，周期 60 分钟 | ❌ 不使用 |
| ~~P3~~ | ~~搜索引擎发现~~ | ~~已删除。搜索引擎结果无法保证时效性、准确性、可达性~~ | — |

**关键变更**: 删除 P3 搜索引擎路径。搜索引擎仅作为人工发现新源的工具，不进入自动采集。

### 4.2 标讯过期规则（增强）

| 状态 | 展示规则 | 操作 |
|------|---------|------|
| 招标中且未过截止时间 | 正常展示 | — |
| 招标中但已过截止时间 | 标记 `expired` 并隐藏 | 降权，不出现在默认列表 |
| 中标/成交/终止/变更 | 展示但降权 | 更新已有记录（同 bid_no 覆盖更新） |
| 历史过期公告 | 归档 | 不删除，用户可手动查看 |

### 4.3 标讯状态变更更新

同 `bid_no` 的标讯，当状态变更（如"招标中"→"中标"）时：
1. 更新 `hotspots` 现有记录（非新增）
2. 更新 `bid_details` 中的 `bid_status` 和 `updated_at`
3. 如果用户收藏了该标讯，推送状态变更通知

---

## 5. 迁移策略（新增关键章节）

### 5.1 总体原则：并行运行，逐步切流

```
Phase 0: 基础设施 → 新旧并行 → Phase 2: 逐步迁移 → Phase 3: 旧系统下线
```

### 5.2 Phase 0 — 基础设施先行（不改变现有采集逻辑）

**目标**: 建立新架构的数据底座，现有 collector 照常运行

| 步骤 | 内容 | 产出 |
|------|------|------|
| 0.1 | 创建 `crawler_sources` 表 + seed 数据（从现有 collector 反推源配置） | 源注册表就绪 |
| 0.2 | 创建 `raw_items` 表，在现有 upsert 链路旁路写入 raw content | 溯源能力就绪 |
| 0.3 | 创建 `crawler_runs` 表，旁路记录每轮抓取统计 | 观测能力就绪 |
| 0.4 | 统一 `BackendSession` 接入 RSS/HTML 路径 | 基础设施就绪 |
| 0.5 | 创建 `quality_rejection_log` 表，旁路记录被拒条目 | 审计能力就绪 |

**并行运行期**: 新旧架构同时运行，新表只写不读，不影响现有功能。

### 5.3 Phase 1 — 标讯专项修复

**目标**: 解决当前最痛的标讯采集问题

| 步骤 | 内容 | 优先级 |
|------|------|--------|
| 1.1 | 从 `bid_collector.py` 提取 P0 源配置到 `crawler_sources` | P0 |
| 1.2 | 实现 P0 源独立 parser（ccgp, cebpub 等） | P0 |
| 1.3 | 引入 `bid_details` 表，结构化存储标讯字段 | P1 |
| 1.4 | 标讯过期规则上线 | P2 |
| 1.5 | 删除 P3 搜索引擎路径 | P0 |
| 1.6 | 旧 `bid_collector.py` 标记 `deprecated`，仍运行但不写入新数据 | P2 |

### 5.4 Phase 2 — 质量门禁升级

| 步骤 | 内容 |
|------|------|
| 2.1 | Hard/Soft 门禁分层 |
| 2.2 | URL 全量校验（从抽样 10% 改为 100%） |
| 2.3 | 三层去重上线 |
| 2.4 | 审计视图前端 |

### 5.5 Phase 3 — 旧系统下线

**条件**: 新架构连续运行 7 天，输出与旧系统一致（或更好）

| 步骤 | 内容 |
|------|------|
| 3.1 | 关闭旧 collector 调度 |
| 3.2 | 删除 `BaseCollector` 基类（如无引用） |
| 3.3 | 删除 `bid_collector.py` 等已迁移文件 |
| 3.4 | 最终清理 |

---

## 6. 反爬对抗策略

### 6.1 策略分级

| 等级 | 反爬强度 | 应对方案 | 适用源 |
|------|---------|---------|-------|
| L0 | 无反爬 | `httpx` 直连，标准 UA | RSS/开放 API |
| L1 | 简单反爬（UA/Referer 检查） | `BackendSession` 自定义 UA + Referer | 大多数新闻站 |
| L2 | 中等反爬（频率限制/IP 封锁） | 代理 + 限速 + 指数退避 | 政府/行业站 |
| L3 | 强反爬（JS 挑战/TLS 指纹） | `crawl4ai` 浏览器渲染 + `curl_cffi` 可选 | 少数强反爬站 |
| L4 | CAPTCHA/登录 | 不自动处理，标记 `requires_captcha`，通知用户手动处理 | 极少数 |

### 6.2 降级路径

```
L3 (browser) → L2 (proxy + 限速) → L1 (UA) → 放弃
```

---

## 7. 实施路线图

| Phase | 内容 | 预计工期 | 依赖 | 交付物 |
|-------|------|---------|------|--------|
| **0** | 基础设施（源注册表 + raw_items + 观测） | 2-3 天 | 无 | 6 张新表 + seed 数据 + BackendSession 统一接入 |
| **1** | 标讯专项修复 | 3-5 天 | Phase 0 | P0 标讯 parser + bid_details + 过期规则 |
| **2** | 质量门禁升级 | 2-3 天 | Phase 0 | Hard/Soft 分层 + 全量 URL 校验 + 审计视图 |
| **3** | 源级调度 + 健康管理 | 2-3 天 | Phase 0, 2 | 源级调度器 + 健康状态机 + 告警 |
| **4** | 旧系统下线 | 1-2 天 | Phase 1-3 | 旧 collector 清理 + 最终验证 |

**总工期**: 10-16 天

---

## 8. 验收标准

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| 注册源活跃率 | ≥ 80% | `crawler_sources` 中 `status = 'active'` 比例 |
| 资讯抓取延迟 | P95 ≤ 15 分钟 | `crawler_runs` 中从 `started_at` 到 `finished_at` |
| 标讯抓取延迟 | P95 ≤ 30 分钟 | 同上 |
| 新条目 URL 全量校验率 | 100% | `crawl_url_checks` 记录数 / `hotspots` 新条目数 |
| 原文 URL 硬校验通过率 | ≥ 98% | 校验通过数 / 总校验数 |
| 跨源重复率 | ≤ 5% | 三层去重命中数 / 总条目数 |
| 标讯元数据覆盖率 (P0/P1) | ≥ 80% | 有 ≥ 3 个结构化字段的标讯比例 |
| 数据库无合成/搜索/列表 URL | 0 条 | 全量 URL 校验 |
| 单源改版恢复时间 | ≤ 15 分钟 | parser 版本化 + 独立测试 + 热修复 |
| 质量门禁审计可查询 | 是 | `quality_rejection_log` 表可查 |

---

## 9. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| 迁移过程中旧系统故障 | 中 | 高 | Phase 0 并行运行期，旧系统不修改 |
| 新 parser 解析错误导致数据丢失 | 中 | 高 | 新旧架构输出对比，差异收敛后再切流 |
| 官方源改版周期短于开发周期 | 高 | 中 | parser 版本化，15 分钟内可修复 |
| 标讯 P0 源无公开接口 | 中 | 中 | 列表页 + 详情页解析兜底 |
| 强反爬源无法抓取 | 中 | 低 | 浏览器渲染 + 合理频率，仍失败则标记 `requires_captcha` |
| 30 天 raw_items 保留期不够 | 低 | 低 | 可配置，默认 30 天 |