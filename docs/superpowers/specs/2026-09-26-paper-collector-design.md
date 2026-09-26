# 论文抓取能力 — 设计稿 (2026-09-26)

## 1. 目标

为安全从业者引入**学术论文**这一知识源, 补齐"实战资讯 (hotspots) ↔ 学术研究 (papers)"双循环。
论文经独立分类 (paper) 入采集管线, 与既有热点同构消费 (feed 展示/收藏/深读/自动入管)。

## 2. 领域 → arXiv 分类映射 (owner 给定 14 领域, 映射到 arXiv cat)

| 领域 | arXiv cats |
|---|---|
| AI | cs.AI, cs.LG, cs.CL |
| AI 安全 | cs.CR + cs.AI 交叉 → 用 cs.CR 检索词 "adversarial OR LLM security" |
| 网络安全 | cs.CR, cs.NI |
| 数据安全 | cs.CR + "data privacy OR data security" |
| 安全运营 | cs.CR + "security operations OR SOC" |
| 态势感知 | cs.CR + "situational awareness OR threat landscape" |
| 攻击面管理 | cs.CR + "attack surface" |
| 应用安全 | cs.CR + "web security OR application security" |
| 漏洞治理 | cs.CR + "vulnerability" |
| 资产治理 | cs.CR + "asset management OR asset discovery" |
| 信息安全 | cs.CR, cs.MM security |
| 安全架构 | cs.CR + "security architecture" |
| 应急响应 | cs.CR + "incident response" |
| 威胁情报 | cs.CR + "threat intelligence" |

**实现取捨**: arXiv API 支持多 cat OR 查询。为控制条数与区分度, 首批实现为 **paper collector 内置 14 领域检索模板** (每领域一个 query), 单次采集轮转采样 (每轮取 2-3 个领域, 避免单源刷屏), 每条论文落 category='paper' + tags 记领域。

## 3. 架构

### 3.1 新增 Category.PAPER

- `backend/domain/enums.py` 枚举加 `PAPER = "paper"`
- `collection_service.py` collectors dict 加 `Category.PAPER: [ArxivPaperCollector()]`
- 前端 `types/index.ts` CATEGORIES 加 paper (标签 "论文"); SentinelHomePage `tagColorOf` 补 case
- `keywords.py` `_CAT_KEYWORDS` 加 paper 关键词 (供 category_match gate)
- 三个 report service 标签表补 paper

### 3.2 ArxivPaperCollector (backend/collectors/arxiv_paper_collector.py)

- 继承 BaseCollector: `category=PAPER`, `kind='rss'`, `timeout=30`, `max_items=30`
- sources = 14 领域查询 URL 模板 (export.arxiv.org/api/query, Atom), **轮转采样**: `_domain_cursor` 每轮推进, 本轮取 3 个领域的 query
  - *偏差注记 (实现落地)*: cursor 为 **实例属性** 而非设计稿原稿的"类属性" — collector 由 collection_service 长生命周期持有, 实例属性即可跨轮推进且避免与类属性默认值语义混淆
- 解析: 复用 `_fetch_rss` (feedparser 支持 Atom) → title/summary/link/published; arXiv id 写稳定 item id (`arxiv:2107.xxxxx`, 先例 `hn:item:{id}`), 领域键落 `item.source`
  - *偏差注记 (实现落地)*: 领域键 **原样中文** (如 `AI安全`) 而非原稿示例的小写 `ai安全` — 领域键与 `PAPER_DOMAIN_QUERIES`/crawler_sources 行 name 严格对齐, 不做大小写归一; 设计稿 §3.2 的 tags 三要素载体 (`arxiv:` / `领域:` / `论文`) 简化为 `arxiv:<id>` 单 tag 落 item.id (后两元素无消费点, 终审清理)
- 无需 key; 国际源 → `network_zone='international'`, 走代理配置 (与 YouTube 源同语义, 代理未配则 0 产出但健康机不判死? → 保持既有语义: 连续失败会判 dead, 报告中注明需代理)

### 3.3 crawler_sources 注册行

- 14 领域各一行 (kind='rss', media_kind='web', category='paper', api_url=各 query) — 与"crawler_sources 切流"机制对齐 (base.py:498 优先读表), 单领域可独立启停/退役
- enabled 默认 true; health 机自动接管

### 3.4 feature gate

- `feature_gates.toml` 加 `paper = true`? → **不加 gate**: 论文与既有 7 类目同级, 是 category 扩展而非扩展域 (无独立 router/独立 job)。collector 进既有 collect_all_job。若未来量级失控再 gate 化。

### 3.5 终审补充 (2026-09-26 真实拉取验证)

- **sortBy 合法值教训**: arXiv API 对非法 sortBy (误写 `submitted`) **不报错**, 而是返回仅含 1 条 Error entry 的 Atom feed — 3 领域轮转恰凑满 `min_items_threshold`, 垃圾条目会静默入 feed。正确值为 `submittedDate` (测试 `test_paper_domain_queries_shape` 精确断言防回退)
- **节拍锁**: base.collect() 对本轮源并发, 但 arXiv API 官方要求请求间隔 ≥3s, 3 领域并发实测触发 Fastly 限流 (HTTP 406, 无代理直连同样生效) → collector 内 `fetch_source` 以事件循环惰性建锁 (WeakKeyDictionary per-loop) 串行化出网请求, 间隔 3s; 其他 collector 共享 fetchers 基建零改动
- **RecencyGate paper 放行**: arXiv 周末不公告、假期后论文大面积早于本周一, RecencyGate 原硬拒收 (扣 100) 会让论文静默不入库 → paper 类目与 archive 同构软放行 (passed + `recency_warning`), 见 `backend/quality/recency_gate.py`

## 4. 实施任务

- **T1**: Category.PAPER 全注册点 (枚举/dict/keywords/前端 CATEGORIES/tagColor/报表标签) + ArxivPaperCollector (轮转采样 + Atom 解析) + 14 行 crawler_sources 注册 + 测试
- **T2**: 收口 — 真实拉取一轮验证产出 + 全量回归 + DEV-0233 + 落账

## 5. 非目标

- 不做 PDF 全文下载与解析 (摘要级入管足够深读入口; 全文另立项)
- 不做Semantic Scholar/OpenReview 等多源 (arXiv 覆盖 AI+安全主流量; 多源另立项)
- 不新增 feature gate / 不动健康机语义
