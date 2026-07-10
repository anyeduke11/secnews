# 热点地图 · 规范方案（SPEC）v3.1

> 文档类型：功能与接口规范
> 关联：[ARCHITECTURE.md](../ARCHITECTURE.md) · [CHECKLIST.md](./CHECKLIST.md) · [TASKS.md](./TASKS.md) · [RCA.md](./RCA.md)
> 版本：2026-07-05
> 范围：基于架构优化方案 v3.0 的功能/接口/性能/可靠性 规范
> 重大变更: **v3.1 (2026-07-05) Phase 13 — 撤销所有 fallback 合成数据,确立"原文链接硬约束"**

---

## 〇、变更摘要（v3.1 必读）

| 主题 | v3.0 (旧) | v3.1 (新) | 触发 |
|---|---|---|---|
| Fallback 合成 URL | 5 个 collector 各自返回 `https://example.com/{cat}/{i}` 硬编码占位 | **全部撤销**,`BaseCollector._fallback()` 默认返回 `[]`,子类不实现 | Phase 13 用户明确禁止"把搜索工作推给用户" |
| 标讯 fallback | Phase 12 改为 Google 搜索 URL (`https://www.google.com/search?q=...`) | **撤销**,真实优先于"假装有数据" | Phase 13 截图反馈 Google 搜索能找到真实公告,验证此方案对用户极不友好 |
| 源全部失败时行为 | 走 fallback,服务"正常"响应 | **直接返回 `[]`**,UI 显示"该分类暂无可用资讯" | 用户原话:"如果没有真实链接说明资讯和标讯有问题" |
| 原文链接硬约束 | 仅 §3.1 字段约束 (合法 URL) | **新增 §3 整章规范**,写死到 SPEC | 用户要求"将这条写死到 SPEC 中" |
| 验收 §10.1 | "6 个领域全部有数据 (fallback 视为通过)" | **删除**,改为"6 个领域**全部有真实链接**" | 同上 |

**v3.1 的核心原则**: **真实优先于"假装有数据"**。宁可某个分类显示"暂无可用资讯",也不能用合成 / 搜索 URL 欺骗用户。

---

## 一、项目边界

### 1.1 定位

IT人员专属工作站 — 单人本地使用的多领域热点聚合看板，覆盖七大领域（科技/AI、网络安全、金融/投资、独立开发/创业、招标资讯、GitHub 项目、IT/科技），支持分类筛选、关键词搜索、24小时趋势分析、静态 HTML 导出、周报洞察、跨端同步。

### 1.2 范围内

- ✅ 7 个领域的数据采集、解析、入库
- ✅ 暗/亮双主题 React 看板
- ✅ 分类 / 时间 / 关键词过滤
- ✅ 24 小时热度趋势图
- ✅ 静态 HTML 导出
- ✅ HTTP/SOCKS 代理配置 + 连通性测试
- ✅ 5 分钟自动刷新 + 手动刷新
- ✅ SQLite 本地持久化（重启不丢数据）
- ✅ 收藏功能（7 个分类）
- ✅ XLSX 导出收藏
- ✅ 待办管理（4 象限）
- ✅ LLM 密钥加密管理
- ✅ WebDAV 跨端同步（坚果云）
- ✅ 周报自动生成 + AI 洞察（v1.3.0）
- ✅ SSE 实时推送 + 轮询降级（v1.3.0）
- ✅ 前端 URL 路由（v1.3.0）
- ✅ 标讯地区筛选（v1.3.0）

### 1.3 范围外

- ❌ 多用户 / 多租户
- ❌ 账号系统 / 鉴权
- ❌ 数据写入外部 API / 第三方推送
- ❌ 移动端原生 App（小程序方案见 IMPROVEMENT_PLAN.md）
- ❌ 分布式部署
- ❌ 国际化 i18n（仅中文）
- ❌ **任何形式的合成 / 占位 / 搜索 URL 兜底**（v3.1 新增,见 §3）

---

## 二、核心功能规格

### 2.1 数据采集

| 项 | 规格 |
|---|---|
| 采集频率 | 5 分钟 / 次（可配置，默认 300s） |
| 并发模型 | `asyncio.gather` 并发抓取，DB 串行写（用 `asyncio.to_thread` 跑 sync DB 避免阻塞 event loop） |
| 单源超时 | 30 秒 |
| 全局超时 | 60 秒 |
| 抓取策略 | **Phase 11**: crawl4ai (Playwright + Chromium) 优先 → 失败 fallback aiohttp。`USE_CRAWL4AI=0` 默认走 aiohttp,`=1` 启用 crawl4ai |
| **源全部失败时** | **`collect()` 直接返回 `[]`**。**不**调 `_fallback()`,**不**返回合成数据。日志记录 "all sources failed, returning []" |
| **备用数据** | **Phase 13 撤销**。`BaseCollector._fallback()` 默认 `return []`,6 个 collector 子类均不实现 |
| 单源失败隔离 | 单源失败不影响其他源,失败信息记入 `SourceResult.error_msg` |

### 2.2 分类规格

| ID | 名称 | 色值（统一） | 数据源 |
|---|---|---|---|
| `all` | 全部热点 | `#00c96a` | — |
| `ai` | 科技 / AI | `#00bcd4` | HackerNews / 量子位 / 36氪AI / 机器之心 |
| `security` | 网络安全 | `#e85d5d` | KrebsOnSecurity / TheHackerNews / 安全客 / FreeBuf / 嘶吼 |
| `finance` | 金融 / 投资 | `#f0c929` | 新浪财经 / 东方财富 / 华尔街见闻 / 雪球 / 财新网 |
| `startup` | 独立开发 / 创业 | `#7c6aff` | 36氪 / 虎嗅 / 投资界 / IT桔子 |
| `bid` | 招标资讯 | `#e8891a` | 30+ 国家级 / 行业级 / 商业级招标平台 |
| `github` | GitHub 项目 | `#6e7681` | GitHub Trending / Star History |

**前后端色值统一**：以上色值**唯一权威源**，前后端不得有第二份硬编码。

### 2.3 数据展示

| 功能 | 规格 |
|---|---|
| 列表项数 | 默认 100 / 页，可配 1-200 |
| 分页 | cursor 模式（`?cursor=<published_at>_<id>&limit=100`） |
| 排序 | `published_at DESC` 为主键（按文章真实发布时间,不按 fetch time） |
| 搜索 | 全文检索（FTS5），支持中文 unicode61 分词 |
| 时间筛选 | 24h / 3d / 7d / 30d |
| 分类筛选 | 7 个分类（含 all） |
| 卡片点击 | 跳转到 **真实原文链接**（见 §3 硬约束） |
| 空分类 | UI 显示"该分类暂无可用资讯"（v3.1 新增,不再有 fallback 假数据） |

### 2.4 趋势分析

| 项 | 规格 |
|---|---|
| 粒度 | 1 小时 / 桶 |
| 范围 | 最近 24 小时 |
| 类别 | 5 个领域（不含 all / github / general） |
| 统计源 | **仅** `is_fallback=False` 的数据 |
| 重算频率 | 1 小时 / 次 |
| 图表类型 | 堆叠柱状图（Recharts） |
| **发布时间提取** | **Phase 12 修复**: 从 HTML 页面级 (`<meta>`, JSON-LD, `<time>`, URL slug) 提取真实 `published_at`,避免全部 = fetch time 导致分布全在 0 时刻 |

### 2.5 静态导出

| 项 | 规格 |
|---|---|
| 路径 | `/api/export` |
| 产物 | 完整 HTML（含趋势图 + 统计 + 卡片） |
| 生成策略 | 后台预生成，**每 30 分钟一次** + ETag 缓存 |
| 主题 | 跟随系统设置（深/亮） |
| 评分标签 | **不显示** HOT/WARM/NEW（与 DESIGN_GUIDE 一致） |
| **卡片链接** | 必须是真实原文链接（见 §3） |

### 2.6 代理管理

| 项 | 规格 |
|---|---|
| 模式 | off / auto / manual |
| 协议 | HTTP / HTTPS / SOCKS5 |
| 白名单 | 支持通配符（`*.cn` / `baidu.com` / `localhost`） |
| 系统检测 | Windows 注册表 + 环境变量 |
| 连通性测试 | 11 个海外站点，按 5 类别分组展示结果 |
| 热更新 | 配置保存后立即生效（关闭旧 session） |

### 2.7 数据质量门禁

> 9 个门禁在 `Collector.collect()` 与 `Repository.upsert()` 之间运行

| # | 门禁 | 模式 | 拒绝条件 | 默认行为 |
|---|---|---|---|---|
| 1 | Schema 验证 | 同步 | 必填字段缺失、URL 非法、datetime 无效 | reject（硬错误） |
| 2 | 内容质量 | 同步 | 标题 < 5 或 > 500 字符；摘要 < 10 或 > 500 字符；含 spam 关键词；乱码 | warn |
| 3 | 分类匹配 | 同步 | 标题+摘要不含目标分类关键词 | warn |
| 4 | 标题-摘要一致性 | 同步 | 摘要不含标题核心实体 | warn |
| 5 | URL 可达性 | 同步 | HEAD 请求非 2xx、软 404、跳转链 > 3 次 | warn |
| 6 | URL 内容验证 | **异步** | 抓页面后关键词匹配度 < 40% | warn + 更新 `quality_score` |
| 7 | 来源信誉 | 同步 | 来源在黑名单、`current_score < 30` | reject |
| 8 | 作者验证 | 同步 | URL 域名不匹配 source 字段 | warn + 改写 source |
| 9 | 跨源去重 | 同步 | URL hash 已存在 或 标题相似度 > 85% | mark as duplicate |

**严格模式**（`quality.strict_mode=true`）：将 warn 全部升级为 reject
**宽松模式**（默认）：warn 时只打 flag 不阻止入库

### 2.8 质量配置

| key | 默认 | 说明 |
|---|---|---|
| `quality.strict_mode` | `false` | 全局严格开关 |
| `quality.min_score` | `30` | 严格模式下低于此分 reject |
| `quality.url_check_enabled` | `true` | 异步 URL 内容验证总开关 |
| `quality.url_check_sample_rate` | `0.1` | 异步抽样率（0-1） |
| `quality.url_check_timeout` | `8` | 单 URL 超时（秒） |
| `quality.category_keywords` | 见 [ARCHITECTURE §6.4.5](../ARCHITECTURE.md) | 分类关键词 JSON |

---

## 三、原文链接硬约束 (v3.1 写死,不可撤销)

> **本节是 SPEC 最高优先级约束。所有 v3.0 历史描述与本节冲突的,以本节为准。**

### 3.1 核心规则

**资讯 / 标讯卡片上的"原文链接"必须是用户在浏览器中点开就能直接读到该条资讯真实正文的链接。**

具体含义:

1. **必须**是资讯 / 标讯的**真实原文 URL**(article page / 公告页 / commit 详情页 / project homepage)
2. **禁止**提供以下形式的 URL 作为原文链接:
   - **占位符 URL**:`https://example.com/...` / `https://placeholder.com/...` / 任何测试/合成域名
   - **搜索 URL**:`https://www.google.com/search?q=...` / `https://www.bing.com/search?q=...` / 任何搜索引擎查询页
   - **首页 / 列表页 / tag 聚合页**:`https://example.com/category/news` / `https://example.com/tag/xxx`(必须先经 `FinalUrlGate` 下钻到具体文章页)
   - **任意 404 / 不可达 URL**
3. **如果** 实在拿不到真实 URL,**该条 item 应当被丢弃**(不写入数据库、不展示在 UI)
4. UI 显示"该分类暂无可用资讯" **是** 正常且可接受的空状态, **不** 视为 bug

### 3.2 适用范围

| 维度 | 范围 |
|---|---|
| 适用 | `HotspotItem.url` 字段、收藏导出 XLSX 的"原文链接"列、静态 HTML 导出的卡片 `<a href>`、API 响应 |
| 不适用 | API 内部 trace (e.g. `source_url#crawler=crawl4ai`) — 这只是 debug 标记,不是用户可见链接 |

### 3.3 实现要求

#### 3.3.1 采集层 (`backend/collectors/`)

- `BaseCollector._fallback()` **必须**返回 `[]`,子类 **不得** 实现覆盖
- 6 个 collector (ai / security / finance / startup / bid / github) **不** 实现 `_fallback()`
- `BaseCollector.collect()` 在以下场景**直接**返回 `[]`,**不**调任何 fallback:
  - 无 `sources` 配置
  - 所有源 `error_msg is not None` 或 `item_count == 0`
  - 总 item 数 `< min_items_threshold` (默认 3,bid 源 5)
- 爬取失败 / 抓取为空 **不**是"应当返回 fallback"的合法理由

#### 3.3.2 抓取层 (crawl4ai / aiohttp)

- `crawl4ai` (`USE_CRAWL4AI=1`) 优先用于反爬强 / JS 渲染的源 (e.g. bid 中文政府网站)
- `aiohttp` 默认 fallback,适合静态 HTML 源
- **任一**抓取方式返回的 URL,经 `_parse_html` 解析后必须满足 §3.1 规则

#### 3.3.3 质量门禁

- `FinalUrlGate` (门禁 #10,v3.1 新增) 负责对 tag / 列表页 URL 下钻到真实文章页,失败 → item 丢弃
- `UrlValidityGate` 拒绝不可达 / 软 404 URL
- `UrlContentGate` 验证抓回的页面内容与标题/摘要相关,匹配度 < 40% → warn + 降分

#### 3.3.4 数据清理

- 一次性脚本 `scripts/redrill_tag_urls.py` 用 `FinalUrlGate` 重新下钻历史数据
- 一次性脚本 `scripts/backfill_krebs_articles.py` 清理 krebsonsecurity.com 噪声标题
- 一次性脚本 `scripts/purge_synthetic_urls.py` (v3.1 新增) 清理数据库中所有 is_fallback=True 残留

### 3.4 反例 (禁止的行为)

| 反例 | 错误做法 | 正确做法 |
|---|---|---|
| bid fallback 占位符 | `url = "https://example.com/bid/security/{i}"` | 抓不到就 drop item,UI 显示空状态 |
| bid Google 搜索 URL | `url = "https://www.google.com/search?q=..."` | 同上,真实优先 |
| Krebs 标题噪声 | 把 "99 comments" 当标题 | 优先匹配 `<h1 class="entry-title">`,过滤评论数锚点 |
| qbitai tag 页 | `url = "https://www.qbitai.com/tag/worldclaw"` | 调 `FinalUrlGate` 下钻到 `https://www.qbitai.com/2026/07/442447.html` |
| GitHub trending 主页 | `url = "https://github.com/trending"` | 提取 `/owner/repo` 真实项目链接 |

### 3.5 验收

- [x] `BaseCollector._fallback()` 默认返回 `[]`
- [x] 6 个 collector 不实现 `_fallback()`
- [x] `BaseCollector.collect()` 全源失败 / 不足时返回 `[]`,无合成数据
- [x] `test_bug_fixes_published_at.py` 中 `TestFallbackReturnsEmpty` 覆盖所有 6 个 collector
- [x] 全量测试 500+ 通过
- [x] DB 中无 `is_fallback=True` 残留
- [x] UI 6 个分类均能展示真实链接,无 example.com / google.com

### 3.6 历史教训 (来自 Phase 12)

> 2026-07-05 Phase 12 修 Bug 1 时,把 bid fallback URL 从 `https://example.com/bid/security/{i}` 改为 Google 搜索 URL,认为这样"真实可访问,用户点击能搜到真实信息"。
>
> **结果**: 2026-07-05 用户截图反馈,Google 搜索能直接搜到真实公告(`shbid.com` / `bankofchina.com` / `gpx-template` / `kfqgw.beijing.gov.cn`),用户明确反对"把搜索工作推给用户":
>
> > 资讯的原文链接必须是原文真实链接,如果没有真实链接说明资讯和标讯有问题,禁止提供搜索字眼让用户自己搜索资讯。
>
> **Phase 13 撤销该方案**。详见 [RCA.md §1](./RCA.md#1-fallback-合成-url-出现-2-次)。

---

## 四、数据契约

### 4.1 HotspotItem

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `id` | string | ✅ | 主键，来源内唯一 | 例：`ai_hn_12345` |
| `title` | string | ✅ | 1-500 字符 | 标题 |
| `summary` | string | ❌ | ≤500 字符 | 摘要，可空 |
| `source` | string | ✅ | 1-50 字符 | 数据源名 |
| `url` | string | ✅ | **真实原文 URL** (见 §3 硬约束) | 卡片跳转链接 |
| `category` | enum | ✅ | `ai`/`security`/`finance`/`startup`/`bid`/`github` | 分类 |
| `published_at` | datetime | ✅ | UTC, tz-aware | **真实发布时间**(非 fetch time) |
| `score` | int | ❌ | 0-100 | 热度评分 |
| `fetched_at` | datetime | ✅ | UTC, tz-aware | 入库时间 |
| `is_fallback` | bool | ✅ | **v3.1 后必须 `False`** (fallback 已撤销) | 历史字段保留以兼容 |
| `quality_score` | int | ✅ | 默认 100，0-100 | 质量评分 |
| `quality_flags` | list[string] | ✅ | 默认 [] | 质量标记 |
| `quality_checked_at` | datetime | ❌ | UTC, tz-aware | 质量检查时间 |
| `url_check_status` | enum | ❌ | `pending`/`verified`/`mismatch`/`skipped` | 异步 URL 内容验证状态 |

### 4.2 TrendPoint

| 字段 | 类型 | 说明 |
|---|---|---|
| `label` | string | X 轴标签（"现在" / "1小时前" / ...） |
| `hours_ago` | int | 0-23 |
| `category` | string | `ai` / `security` / `finance` / `startup` / `bid` |
| `count` | int | 该桶该类别的真实（非 fallback）数量 |

### 4.3 CollectionRun

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 自增 |
| `category` | string | 分类 |
| `started_at` | datetime | 开始时间 |
| `finished_at` | datetime | 结束时间 |
| `status` | enum | `success` / `partial` / `failed` |
| `item_count` | int | 成功入库数 |
| `fallback_count` | int | fallback 数 (v3.1 后恒为 0) |
| `error_msg` | string | 错误信息（nullable） |

### 4.4 Settings（键值对）

| key | value 类型 | 说明 |
|---|---|---|
| `proxy.mode` | `off`/`auto`/`manual` | 代理模式 |
| `proxy.http` | string | HTTP 代理 URL |
| `proxy.https` | string | HTTPS 代理 URL |
| `proxy.socks` | string | SOCKS 代理 URL |
| `proxy.no_proxy` | string | 白名单，逗号分隔 |
| `theme` | `dark`/`light` | 主题 |
| `cache.ttl_seconds` | int | 缓存 TTL |
| `collect.interval_seconds` | int | 采集间隔 |

---

## 五、API 契约

### 5.1 通用规范

- **版本**：路径无 `/v1/`，响应中通过 `version="1.3.0"` 字段传达
- **Content-Type**：`application/json; charset=utf-8`
- **时区**：所有时间字段 UTC + `Z` 后缀
- **错误格式**：
  ```json
  { "code": "INVALID_PARAM", "message": "...", "trace_id": "..." }
  ```

### 5.2 端点清单

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/hotspots` | 热点列表（cursor 分页） |
| GET | `/api/hotspots/{id}` | 单条详情 |
| GET | `/api/trends` | 24h 趋势 |
| GET | `/api/categories` | 分类元数据 |
| GET | `/api/health` | 健康检查（增强版） |
| GET | `/api/stats` | 内部统计 |
| GET | `/api/export` | 静态 HTML 导出 |
| GET | `/api/proxy/settings` | 获取代理配置 |
| PUT | `/api/proxy/settings` | 更新代理配置 |
| GET | `/api/proxy/test` | 代理连通性测试 |
| GET/POST/DELETE | `/api/favorites` | 收藏管理 |
| GET | `/api/favorites/count` | 收藏统计 |
| GET | `/api/favorites/export` | 收藏 XLSX 导出 |

### 5.3 GET /api/hotspots

**请求参数**：
| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `category` | enum | ❌ | `all` | 分类 |
| `time_range` | enum | ❌ | `7d` | `24h`/`3d`/`7d`/`30d` |
| `keyword` | string | ❌ | — | 搜索词，1-100 字符 |
| `cursor` | string | ❌ | — | 分页游标 |
| `limit` | int | ❌ | 100 | 1-200 |

**响应**：
```json
{
  "items": [HotspotItem, ...],
  "total": 1234,
  "category_counts": { "ai": 200, "security": 150, ... },
  "next_cursor": "1717392000_ai_hn_12345",
  "fetched_at": "2026-07-05T12:00:00Z",
  "cache_hit": true,
  "version": "1.3.0"
}
```

### 5.4 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `INVALID_PARAM` | 参数越界/类型错误 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 429 | `RATE_LIMITED` | 触发限流 |
| 500 | `INTERNAL` | 内部异常（附 `trace_id`） |
| 503 | `SOURCE_UNAVAILABLE` | 所有源失败（v3.1 行为: 返回空列表,HTTP 200,不返回 503） |

---

## 六、性能规格

### 6.1 性能预算

| 指标 | 目标 | 测量方法 |
|---|---|---|
| 启动时间（冷启动） | < 3s | 进程启动到 `/api/health` 返回 200 |
| `/api/hotspots` P95 | < 200ms | 100k 数据集 |
| `/api/hotspots`（缓存命中） | < 50ms | LRU 命中 |
| `/api/trends` P95 | < 100ms | — |
| `/api/categories` | < 5ms | 静态缓存 |
| `/api/export` | < 50ms | 预生成文件直出 |
| 内存占用 | < 200MB | 10k 数据集 |
| DB 大小 | < 50MB / 10万条 | 包含 FTS 索引 |
| **collect 期间 API 延迟** | **< 500ms (P95)** | `asyncio.to_thread` 隔离 sync DB 操作 |

### 6.2 容量上限

| 维度 | 设计上限 | 软上限（性能拐点） |
|---|---|---|
| 热点总量 | 1,000,000 | 100,000 |
| 收藏分类数 | 20 | 5 |
| 数据源数 | 100 | 20 |
| 单源 item 数 | 200 | 50 |
| 代理白名单条目 | 1000 | 50 |

---

## 七、可靠性规格

### 7.1 数据可靠性

| 指标 | 要求 |
|---|---|
| 进程崩溃数据丢失 | **0 条**（WAL + 5s 落盘） |
| 数据保留期 | **永久保留**（不自动清理历史热点） |
| 磁盘写满保护 | 仅依赖磁盘容量；如需手动清理，提供 CLI 工具 `python -m backend.tools.purge --before YYYY-MM-DD` |
| 备份策略 | 每日 3:00 备份，保留 7 份 |
| 单点故障 | 无（除磁盘） |
| **合成数据 (v3.1)** | **0 条**。DB 中 `is_fallback=True` 数据**必须**为 0,定期检查 |

### 7.2 服务可靠性

| 指标 | 要求 |
|---|---|
| 服务可用性 | ≥ 99%（本地单人使用,崩溃可手动重启） |
| 故障恢复时间 | < 5s（无外部依赖） |
| 单源故障隔离 | 单源失败不影响其他源 + 主服务 |
| **网络完全断开 (v3.1)** | **不**走 fallback。`collect()` 返回 `[]`,UI 显示空状态,服务**正常**响应 (HTTP 200) |

### 7.3 错误处理

| 层级 | 策略 |
|---|---|
| 采集器 | **永不**抛异常上抛。**永不**调 `_fallback()` 返回合成数据。失败 → 该源 item_count=0,该源 record in `SourceResult.error_msg`,其他源继续 |
| Repository | 写失败重试 3 次（指数退避），仍失败则保留旧数据 |
| API 层 | 统一异常 handler,返回结构化错误 + trace_id |
| 调度器 | 任务失败不杀死调度,下次继续 |

---

## 八、可观测性规格

### 8.1 日志

- 库：`loguru`
- 格式：JSON Lines
- 轮转：单文件 50MB，保留 5 个
- 必含字段：`ts, level, module, msg, trace_id, category, duration_ms, item_count`
- 位置：`backend/logs/app.log`

### 8.2 健康检查（`/api/health`）

```json
{
  "status": "ok",
  "version": "1.3.0",
  "uptime_s": 3600,
  "db": {
    "size_mb": 12.3,
    "items": 1234,
    "wal": "ok",
    "integrity": "ok"
  },
  "scheduler": {
    "running": true,
    "last_collect_at": "2026-07-05T12:00:00Z",
    "next_collect_at": "2026-07-05T12:05:00Z"
  },
  "collectors": {
    "ai":       { "last_status": "success", "last_items": 80, "last_run": "..." },
    "security": { "last_status": "partial", "last_items": 60, "last_run": "..." }
  },
  "cache": { "hit_rate": 0.92, "size": 64 },
  "proxy": { "mode": "auto", "ok": true }
}
```

### 8.3 内部统计（`/api/stats`）

| 字段 | 说明 |
|---|---|
| `total_items` | 当前 DB 总数 |
| `items_by_category` | 分类分布 |
| `collection_runs_24h` | 24h 采集次数 |
| `success_rate_24h` | 24h 成功率 |
| `cache_hit_rate` | 缓存命中率 |
| `avg_collect_duration_ms` | 平均采集耗时 |
| `last_fallback_at` | 最后走 fallback 的时间 (v3.1 后恒为 `null`) |
| `version` | API 版本号（`"1.3.0"`） |

---

## 九、可扩展性规格

### 9.1 新增数据源

**工作量目标**：≤ 30 分钟

**强制要求**：
- 继承 `BaseCollector`
- 实现 `fetch()`(默认实现 `BaseCollector.fetch_source` 即可覆盖绝大多数源)
- **不**实现 `_fallback()`(v3.1 硬约束)
- 颜色使用 `CATEGORY_CONFIG` 常量
- 遵循 Pydantic 强类型

### 9.2 新增分类

**工作量目标**：≤ 1 小时

**步骤**：
1. 在 `CATEGORIES` 中添加（前后端同步）
2. 分配色值
3. 创建对应的 collector
4. 更新 DB schema（如有）
5. 更新 DESIGN_GUIDE

### 9.3 新增 API

- 在 `backend/api/` 新增 router
- 在 `main.py` 中 `app.include_router(...)`
- 前端 `openapi-typescript` 重新生成类型
- 同步更新 CHECKLIST 验证项

### 9.4 演进路径

| 触发条件 | 演进动作 |
|---|---|
| P95 > 500ms 或数据 > 100k | Redis 替换 LRU |
| 多端并发 | PostgreSQL 替换 SQLite |
| 采集源 > 20 | 拆独立 worker 进程 |
| 全文高亮需求 | ES 替代 FTS5 |
| 标讯拿不到真实 URL | **优先**启用 crawl4ai (`USE_CRAWL4AI=1`),增强 Playwright 反爬策略;**不**引入搜索 URL 兜底 |
| 单源反爬持续 1 周 | 加入 `dead` 源名单(Phase 9 招标源质量门禁) |

---

## 十、兼容性规格

### 10.1 数据兼容

- 旧 `cache_data.json` 数据通过 migration 脚本导入
- 旧 item **不**自动打 `is_fallback=True` (v3.1 行为变更;改为回填到 `is_fallback=False` 但 url_check_status='pending' 等待验证)
- DB schema 变更使用 migration 机制（自增版本号）
- **v3.1 migration 007_purge_synthetic_urls.sql**: 清空 DB 中 `is_fallback=True` 的所有数据,删除 `_fallback` 残留

### 10.2 接口兼容

- 旧 `?limit=100` 兼容（无 cursor 等同首页）
- 旧 `/api/categories` 响应字段不变
- 旧 `/api/health` 基础字段保留（新增字段在 `db/cache/proxy` 子对象内）

### 10.3 前端兼容

- 旧 `next` 字段 → 新 `next_cursor`
- 旧 `category_counts` 字段名不变
- 旧 `fetchedAt` → 新 `fetched_at`（**破坏性变更**,前端同步重命名）

---

## 十一、验收标准

### 11.1 功能验收

- [x] 6 个领域全部有真实数据(无合成 URL)
- [x] **6 个领域全部有真实链接**(v3.1 新增;**不**允许 example.com / google.com 兜底)
- [x] 分类筛选、关键词搜索、时间筛选正常
- [x] 趋势图正确显示 24h 分布(按 `published_at` 真实发布时间)
- [x] 静态导出可访问,主题跟随系统
- [x] 代理配置可保存、可测试、可热更新
- [x] 自动刷新（5min）正常运行
- [x] 9 个质量门禁全部生效
- [x] 严格模式下,质量差的 item 被拒绝入库
- [x] 宽松模式下,质量差的 item 带 `quality_flags` 入库
- [x] 异步 URL 内容验证抽样执行,状态可查
- [x] **空分类 UI 显示"该分类暂无可用资讯"(v3.1 新增)**

### 11.2 性能验收

- [x] 1k / 10k / 100k 三档数据集 P95 < 200ms
- [x] 启动时间 < 3s
- [x] 内存占用 < 200MB(10k 数据集)
- [x] DB 大小 < 50MB / 10万条
- [x] **collect 期间 API 延迟 P95 < 500ms**(v3.1 新增;`asyncio.to_thread` 隔离 sync DB)

### 11.3 可靠性验收

- [x] 进程崩溃后重启数据零丢失
- [x] 单源失败不影响其他源
- [x] **网络断开时返回 `[]` 不走 fallback**(v3.1 新增)
- [x] 24h 试运行无未捕获异常
- [x] **DB 中 is_fallback=True 计数 = 0**(v3.1 新增)

### 11.4 工程验收

- [x] 单元测试覆盖率 > 60%
- [x] DESIGN_GUIDE 与代码无冲突
- [x] 前后端分类色值一致
- [x] API 错误码规范 100% 遵守
- [x] 所有配置项可通过 SQLite settings 表管理

---

## 十二、参考文档

| 文档 | 说明 |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | 架构设计 |
| [DESIGN_GUIDE.md](../DESIGN_GUIDE.md) | UI/UX 设计规范 |
| [README.md](../README.md) | 快速开始 |
| [CHECKLIST.md](./CHECKLIST.md) | 实施检查清单 |
| [TASKS.md](./TASKS.md) | 任务分解 |
| [RCA.md](./RCA.md) | **5why + RCA 根因分析 (v3.1 新增)** |
| `.web_builder/plan.md` | 旧版项目计划（历史归档） |

---

**变更记录**

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-04 | v3.0 | 基于架构优化方案 v3.0 重写；引入 Pydantic 强类型、SQLite FTS5、cursor 分页、is_fallback 标记 |
| 2026-07-05 | v3.1 | **Phase 13 重大变更**: 撤销所有 fallback 合成 URL;新增 §3 原文链接硬约束(写死);6 个 collector 不再实现 `_fallback()`;`collect()` 全源失败时返回 `[]`;新增 FinalUrlGate (#10);`asyncio.to_thread` 隔离 sync DB;UI 空分类显示"暂无可用资讯" |
