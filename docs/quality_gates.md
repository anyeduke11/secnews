# Hotspot 质量门禁文档

> 仓库: `/Users/duke/Documents/hotspot`
> 文档版本: 1.3.0 (Phase 26 同步)
> 最后更新: 2026-07-07

---

## 1. 概述

Hotspot 质量门禁是采集后、入库前的一道核心防线。每条 `HotspotItem` 必须经过 **9 道同步门禁** (score 0-100) + **1 道异步门禁** (URL Content) 验证后,才能进入 SQLite 主表。

### 1.1 模式

| 模式 | 行为 |
|------|------|
| `loose` (默认) | 失败打 flag + 扣分,仍入库 |
| `strict` | 失败打 flag + 扣分;`final_score < min_score` 时 `accepted=False`,调用方拒绝入库 |

### 1.2 评分机制

- 每条 `HotspotItem` 初始 `quality_score = 100`
- 每道门禁按规则扣分(penalty 0-30 不等)
- 通过 `compute_final_score()` 累加
- `quality_flags: list[str]` 记录所有失败原因
- 门禁执行结果写 `quality_check_logs` 表(可审计)

### 1.3 触发流程

```text
APScheduler.collect_all_job (5min 周期)
  → CollectionService.run_once()
    → Collector.collect() → 抓取
      → _build_items() 解析为 HotspotItem
      → _run_quality_gates() 9 道同步门禁
    → upsert_many() 批量入库
    → url_content_check_job 5min 后异步抽样 10% 跑 url_content_gate
```

---

## 2. 9 道同步门禁

### 2.1 SchemaGate · Pydantic 二次校验

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/schema_gate.py` |
| 触发 | 必跑,流水线第一个 |
| 行为 | 重新跑 Pydantic v2 `HotspotItem` 校验 |
| 失败标志 | `schema_invalid` |
| 扣分 | 0 (走 Pydantic 失败直接抛异常,不走 pipeline) |
| 关键约束 | `published_at` / `fetched_at` 必须是 tz-aware UTC;`url` 必须是有效 HttpUrl;`category` 必须在 7 枚举内 (`ai/security/finance/startup/bid/github/tech`) |

**设计动机:** 抓取侧可能传 dirty 数据,二次 Pydantic 校验是最后一道 schema 防线。

---

### 2.2 ContentQualityGate · 内容质量

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/content_quality_gate.py` |
| 行为 | 检查标题/摘要长度 + spam 词 + 乱码 |
| 失败标志 | `title_too_short` / `title_too_long` / `summary_too_long` / `content_spam` / `content_garbled` |
| 扣分 | 10-25 |

**规则:**
- 标题长度 1-500 字符(过短=导航/按钮,过长=站名拼接)
- 摘要长度 ≤ 500 字符
- spam 黑名单:`点击查看` / `>>>` / `查看更多` / `入驻` / `阅读全文` / `赞助` 等导航 CTA
- 乱码检测:unicode 替换字符 / 控制字符比例

**Phase 25 P1:** 提取到 `_NAV_CTA_RE` 模块级常量,新增 `_is_title_relevant_to_category()` 复用。

---

### 2.3 CategoryMatchGate · 分类关键词匹配

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/category_match_gate.py` |
| 行为 | 标题 + 摘要必须命中分类关键词 ≥ 1 个 |
| 失败标志 | `category_mismatch` |
| 扣分 | 30 (重罪) |

**关键词配置:** `backend/quality/config.py::DEFAULT_CATEGORY_KEYWORDS`

| 分类 | 关键词数 | 覆盖 |
|---|---|---|
| `ai` | 26 | LLM/GPT/大模型/机器学习/AGI/ChatGPT 等 |
| `security` | 36 | 漏洞/APT/0day/CVE/渗透/红蓝对抗等 |
| `finance` | 23 | A 股/港股/美股/基金/利率/财报等 |
| `startup` | 17 | 融资/估值/IPO/独角兽/早期等 |
| `bid` | 138 (4 大业务线 + 行业线) | 安全服务/安全产品/运维平台/标讯词 + 采购语境 + 行业语境 |
| `github` | 12 | github/trending/repo/awesome/llm/rust/agent |
| `tech` | ~50 (Phase 25 P1 新增) | IT/数码/手机/电脑/硬件/系统/Apple/华为/小米/发布会等 |

**特殊处理:** `bid` 分类使用四线 AND/OR 体系(每条业务线内 OR,与采购语境词 AND)+ 行业关键词 + 2026 时效过滤。

---

### 2.4 TitleSummaryGate · 标题-摘要一致性

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/title_summary_gate.py` |
| 行为 | 标题与摘要的关键词重叠度 ≥ 10% |
| 失败标志 | `title_summary_low_overlap` |
| 扣分 | 15 |

**算法:** 中文 jieba 切词后,Jaccard 相似度 / Levenshtein 比对。

**设计动机:** 防止"标题是 A 内容是 B"(常见于 SEO 站,摘要堆关键词诱导点击)。

---

### 2.5 URLValidityGate · URL 可达性

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/url_validity_gate.py` |
| 行为 | 同步 urllib HEAD 检查,2xx/3xx 通过;4xx/5xx/超时/连接失败 → flag ``url_unreachable``,扣 25 分 |
| 失败标志 | `url_unreachable` |
| 扣分 | 25 |

**实现:** 同步 ``urllib.request`` 发请求,5s 超时,ssl 默认。  
**HEAD 不支持 fallback:** 收到 405/501 时自动重试 GET。  
**调用上下文:** ``BaseCollector._run_quality_gates`` 通过 ``asyncio.to_thread`` 把整个 pipeline 放到 thread pool 跑,sync urllib 不会阻塞 event loop。  
**严格模式:** score < min_score 拒绝入库;loose 模式打 flag+扣分但仍入库。  
**后续:** 失败的 item ``url_check_status`` 在异步 ``url_content_check_job`` 中也会被更新为 ``unreachable`` 供前端过滤。

---

### 2.6 SourceReputationGate · 来源信誉

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/source_reputation_gate.py` |
| 行为 | 黑名单 + 动态评分 |
| 失败标志 | `blacklisted_source` / `low_reputation` |
| 扣分 | 30 (黑名单) / 5-20 (低信誉) |

**信誉计算:** `source_reputation` 表存最近 7d 各源:
- 抓取成功率 (50%)
- 有效 item 比例 (30%)
- 连续失败次数惩罚 (20%)

**黑名单:** `SOURCE_BLACKLIST` (e.g. `www.easyaq.com` 旧版) + `qualisys.publisher_registry` 中 `author_unknown` 命中。

---

### 2.7 AuthorVerificationGate · 作者核实 (Phase 9)

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/author_verification_gate.py` |
| 行为 | 校验 `claimed` 字段(发布者声明) 是否与 URL 域名一致 |
| 失败标志 | `author_unknown` / `author_mismatch` |
| 扣分 | 5-10 (轻度) |

**机制:**
1. 提取 URL 的 `netloc`
2. 在 `PUBLISHER_REGISTRY` (80+ 条目) 中查最长 suffix 匹配
3. 对比 `claimed` 与 canonical name
4. ALIASES 字典做模糊匹配(包含缩写)

**Phase 21 扩充:** 35+ 域名注册(虎嗅/IT桔子/安全内参/E安全/奇安信等)。

**示例:**
- `https://www.4hou.com/posts/abc` + claimed=`嘶吼` → 命中
- `https://csrc.gov.cn/...` + claimed=`中国证监会` → 命中
- `https://example.com/article` + claimed=`小道消息` → author_unknown

---

### 2.8 FinalUrlGate · 最终 URL 下钻 (Phase 9.2)

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/final_url_gate.py` |
| 行为 | 对 `url` 做二次下钻,从 landing 页(tag/搜索/作者/分类)解析出真实文章 URL |
| 失败标志 | `final_url_unresolved` / `final_url_redirect_loop` |
| 扣分 | 10-15 |

**实现:** `final_url_resolver.py` 用 BeautifulSoup 解析 landing 页,寻找:
- `<article>` 标签
- `<a class="title">` 类命名
- 列表第一条/最后一条
- 走 crawl4ai 渲染兜底

**典型场景:** `https://www.freebuf.com/author/xxx` → 跳转到该作者最新文章。

---

### 2.9 DuplicateGate · 重复检测

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/duplicate_gate.py` |
| 行为 | URL hash 命中 + 标题 Jaccard 相似度 ≥ 0.8 |
| 失败标志 | `duplicate_url` / `duplicate_title` |
| 扣分 | 25 |

**实现:**
1. 预查询 DB 中 `existing_urls` / `existing_titles` 集合
2. URL 标准化后 SHA1 hash 比对
3. 标题 jieba 切词 → 词集合 → Jaccard = |A ∩ B| / |A ∪ B|
4. Phase 8 Addendum: 用 `url_title_pairs` 解决"同 URL 不同 title"歧义,按 reputation 选 winner

**设计动机:** 多源抓取同一新闻(36氪 + 量子位 都有)会重复入库,需要去重。

---

### 2.10 BidRecencyGate · 标讯时效 (Phase 20)

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/bid_recency_gate.py` |
| 行为 | 标讯类 `published_at` 距今 ≤ 180 天 |
| 失败标志 | `bid_too_old` |
| 扣分 | 30 |

**配置:** 通过 `QualityConfig.bid_max_age_days` 调整(默认 180)。

**例外:** `bid_status` 为 `historical_bid` 的会被 quality_flags 标记,后续 `hotspot_repo.query` 用 `quality_flags NOT LIKE '%historical_bid%'` 过滤(Phase 22 修复)。

---

## 3. 1 道异步门禁

### 3.1 URLContentGate · 异步抽样 (Phase 11)

| 项 | 值 |
|---|---|
| 文件 | `backend/quality/url_content_gate.py` |
| 触发 | `url_content_check_job` 每 5min 抽样 10% 已入库 item |
| 行为 | 抓真实 URL 正文 → 提取关键词 → 验证与标题/摘要一致 |
| 失败标志 | `content_mismatch` |
| 扣分 | 20 |

**实现:** Playwright/crawl4ai 渲染 + BeautifulSoup 解析,异步跑不阻塞主采集。

**结果:** 写 `url_check_status` 字段(`pending`/`verified`/`mismatch`/`skipped`/`unreachable`)。

**设计动机:** 抓取页与落地页可能不一致(登录墙/反爬),需二次验证。

---

## 4. Pipeline 编排

```python
# backend/quality/pipeline.py
class QualityGatePipeline:
    DEFAULT_GATES: tuple[type[BaseGate], ...] = (
        SchemaGate,             # 1. 二次 Pydantic
        ContentQualityGate,     # 2. 长度/spam/乱码
        CategoryMatchGate,      # 3. 分类关键词
        TitleSummaryGate,       # 4. 标题-摘要一致
        URLValidityGate,        # 5. URL HEAD
        SourceReputationGate,   # 6. 来源信誉
        AuthorVerificationGate, # 7. 作者核实
        FinalUrlGate,           # 8. 最终 URL 下钻
        DuplicateGate,          # 9. 重复检测
        BidRecencyGate,         # 10. 标讯时效
    )
```

**运行模式:** 顺序执行,每道扣分累加,最终 `final_score = 100 - Σpenalty`,`accepted = final_score >= min_score`。

**配置注入:** `QualityConfig(category_keywords=..., mode=loose, bid_max_age_days=180)`。

---

## 5. 评分与 Flag 汇总

### 5.1 Flag 优先级

| 级别 | Flag | 行为 |
|---|---|---|
| 重罪 | `category_mismatch` / `bid_too_old` / `duplicate_url` / `blacklisted_source` | 扣 25-30 分,严格模式拒绝 |
| 中罪 | `content_spam` / `content_garbled` / `url_unreachable` | 扣 15-20 分 |
| 轻罪 | `title_summary_low_overlap` / `final_url_unresolved` / `author_unknown` | 扣 5-15 分 |

### 5.2 软过滤项 (不入 flags,仅影响展示)

- `_NAV_CTA_RE` 匹配: 直接在 `_build_items` 阶段过滤,不进入 quality 流程
- 标题过短(< 8 字符): `title_too_short`,不展示在主视图

---

## 6. 关键文件

```
backend/quality/
├── __init__.py
├── base.py                 BaseGate + GateContext
├── pipeline.py             QualityGatePipeline (9 门禁编排)
├── config.py               QualityConfig + QualityMode + DEFAULT_CATEGORY_KEYWORDS
├── scorer.py               compute_final_score / is_acceptable / merge_flags
├── schema_gate.py          1. Pydantic 二次校验
├── content_quality_gate.py 2. 长度 + spam + 乱码
├── category_match_gate.py  3. 分类关键词
├── title_summary_gate.py   4. 标题-摘要一致性
├── url_validity_gate.py    5. URL HEAD
├── source_reputation_gate.py 6. 来源信誉
├── author_verification_gate.py 7. 作者核实 (Phase 9)
├── final_url_gate.py       8. 最终 URL 下钻 (Phase 9.2)
├── final_url_resolver.py   8 实现细节
├── duplicate_gate.py       9. 重复检测
├── bid_recency_gate.py     10. 标讯时效 (Phase 20)
├── url_content_gate.py     异步. URL 内容验证
├── publisher_registry.py   7 的支撑: 80+ 域名 → canonical name 映射
├── source_coverage.py      源覆盖度评估 (Phase 9)
└── jobs.py                 异步门禁调度 (5min 抽样)
```

---

## 7. 配置

### 7.1 `QualityConfig` (Pydantic)

```python
class QualityConfig(BaseModel):
    mode: QualityMode = QualityMode.LOOSE
    min_score: int = 60               # strict 模式阈值
    category_keywords: dict[str, list[str]]  # 7 分类关键词
    bid_max_age_days: int = 180       # 标讯时效
    nav_cta_blacklist: list[str]      # 导航 CTA 黑名单
    enable_url_content_check: bool = True  # 异步门禁开关
```

### 7.2 调整方式

- 运行时:`/api/quality` 端点 GET 读 / POST 改
- 代码层:`backend/quality/config.py` 修改默认值
- 测试覆盖:`backend/tests/test_quality_*.py` (15+ 文件, 100+ 测试)

---

## 8. 监控与告警

- **失败率告警:** `source_stats` 表中 `zero_yield_runs / total_runs > 0.5` 触发 `dead` 状态
- **失联告警:** 连续 5 次采集 0 条 → 状态从 `active` 变 `dead`
- **质量告警:** 批次 `accepted < 50%` 时 `collection_runs` 记 `quality_alert=True`
- **API 暴露:** `/api/quality/rules` 列出当前所有门禁规则

---

## 9. Phase 演进

| Phase | 门禁变更 |
|---|---|
| 1-7 | Schema / ContentQuality / CategoryMatch / TitleSummary / URLValidity / SourceReputation / Duplicate |
| 9 | + AuthorVerification (publisher_registry 80+ 域名) |
| 9.2 | + FinalUrlGate (landing 页下钻) |
| 11 | + URLContentGate (异步抽样) |
| 20 | + BidRecencyGate (180 天标讯时效) |
| 25 P1 | + tech 分类关键词 (50+) |
| 26 | + 小互AI RSS 走 rss_url 路由,经 SchemaGate 校验入库 |

---

## 10. 测试

`backend/tests/` 下 15+ 质量相关测试文件:

- `test_schema_gate.py` · Pydantic 二次校验
- `test_content_quality_gate.py` · spam / 长度
- `test_category_match_gate.py` · 7 分类关键词
- `test_title_summary_gate.py` · Jaccard 相似度
- `test_url_validity_gate.py` · HTTP HEAD
- `test_source_reputation_gate.py` · 黑名单
- `test_author_verification_gate.py` · publisher_registry
- `test_final_url_gate.py` · 下钻
- `test_duplicate_gate.py` · URL hash + jaccard
- `test_bid_recency_gate.py` · 标讯时效
- `test_quality_pipeline.py` · 9 门禁编排
- `test_quality_repo.py` · 配置 + keyword 数 (7 类, ≥ 30 个)
- `test_url_content_gate.py` · 异步抽样

**当前测试数:** 604 passed (含 quality 相关 100+)

---

## 11. 常见问题

**Q: 为什么 `category_mismatch` 扣 30 分这么重?**
A: 抓取器可能因为抓取失败、HTML 变化而把任意标题塞进该分类,30 分保证严重错分会被 strict 模式拒绝入库。

**Q: `bid_too_old` 会让历史标讯无法入库吗?**
A: 会的,这是 Phase 20 的设计——历史标讯(>180 天)通常是已经结束的招标,展示给用户无意义。但 `bid_status='historical_bid'` 的条目有 special handling(Phase 22 修复)。

**Q: 异步 URLContent 抽样 10% 会不会漏检?**
A: 会,但目标是"高概率抓到",不是"全检"。下一轮 5min 周期会抽样另外 10%,一小时覆盖 60% 库。

**Q: 如何新增一个门禁?**
A:
1. 继承 `BaseGate` 实现 `async def evaluate(self, item, ctx) -> GateResult`
2. 在 `pipeline.py::DEFAULT_GATES` 注册
3. 写测试 `test_<name>_gate.py`
4. 如需配置,扩展 `QualityConfig`

---

## 12. 引用

- Pipeline 编排: [pipeline.py](file:///Users/duke/Documents/hotspot/backend/quality/pipeline.py)
- 门禁基类: [base.py](file:///Users/duke/Documents/hotspot/backend/quality/base.py)
- 评分工具: [scorer.py](file:///Users/duke/Documents/hotspot/backend/quality/scorer.py)
- 域名注册表: [publisher_registry.py](file:///Users/duke/Documents/hotspot/backend/quality/publisher_registry.py)
- 架构文档: [architecture.html](file:///Users/duke/Documents/hotspot/architecture.html)
- 信源清单: [sources.html](file:///Users/duke/Documents/hotspot/sources.html)
