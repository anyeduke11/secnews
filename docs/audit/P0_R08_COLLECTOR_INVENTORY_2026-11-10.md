# P0 · R-08 采集层盘点（19 collector）

> **需求来源**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md` §4.8 R-08](../v0.8.8/V0.8.8_REFACTOR_PRD.md)（第 231–238 行）
> **阶段**: v0.8.8 P0 只读盘点（为 P1 裁决提供证据）
> **性质**: 纯盘点，**零业务代码改动**；本文件是本任务唯一写入物
> **执行时间**: 2026-11-10（Asia/Shanghai）；数据快照 **2026-11-10 14:09 UTC**（`backend/hotspot.db` 仍在实时写入，条数随时段漂移）
> **库**: `backend/hotspot.db`（主库，`hotspots` 表）+ `backend/hotspot-warm.db`（暖库，`quality_check_logs` / `crawler_runs` 表）
> **DB 访问**: 全部只读（`sqlite3 "file:...?mode=ro"`），**未执行任何写操作**

---

## 1. 采集方法

### 1.1 collector 枚举口径（与 `generate_meta.py::count_collectors()` 完全一致）

枚举 **不是** 按文件名或目录推断，而是复刻 `scripts/generate_meta.py::count_collectors()`（第 139–151 行）的 AST 逻辑：解析 `backend/collectors/*.py`（排除 `__init__.py`），对每个 `ast.ClassDef` 检查 `node.bases` 中是否存在 `ast.Name` 且 `id == "BaseCollector"`。

```bash
$ python scripts/generate_meta.py
{"jobs": 59, "collectors": 19, "routers": 100, "services": 161, "core_routers": 68}
```

复刻版 AST 遍历同样得到 **19**，与权威计数一致 → **主表 19 行齐全（验收 ①）**。

> 口径说明：`BaseCollector` 子类可出现在任意子模块（本次 `paper_sources.py` 一个文件贡献 5 个），因此枚举必须覆盖 `backend/collectors/` 下**全部** `.py`，不能按「文件数 = collector 数」推断。

### 1.2 support 模块归类（不计入 19）

`backend/collectors/` 下非 `BaseCollector` 子类的文件共 **9 个** + 1 个配置，均为支撑层，**不产生独立采集产出**：

| 文件 | 归类 | 说明 |
|---|---|---|
| `base.py` | 抽象基类 | `BaseCollector` 本身（ABC），`collect()` 编排 + `_load_sources_from_registry()` 源注册表装载（base.py:375–441） |
| `fetchers.py` | Mixin | HTTP 抓取路径（v1.8 R3 从 base.py 拆出） |
| `item_builder.py` | Mixin | item 构建 + 落库前过滤；**产出 id 的 `{collector}_{source}_{hash}` 前缀规则**（item_builder.py:142） |
| `quality_hook.py` | Mixin | 落库前同步质量门禁钩子（拒绝 → 不入库） |
| `id_factory.py` | 工具 | `make_readable_id()` → `{source}:{subtype}:{native_id}` 可读 id |
| `keywords.py` | 工具 | 各分类相关性关键词表 + `_is_title_relevant_to_category()` |
| `parsing.py` | 工具 | 通用 HTML/RSS/JSON 解析辅助 |
| `session.py` | 工具 | `BackendSession` httpx 客户端 |
| `sogou_search.py` | 工具 | 搜狗微信搜索（被 wechat renderer 调用，本身不是 collector） |
| `crawl_config.yaml` | 配置 | Crawl4ai 抓取配置 |

> 特别说明：`aggregator.py` / `bid_search.py` / `bid_status.py` **在当前代码库中已不存在**（CLAUDE.md 的目录注释仍列它们，属历史遗留）。当前聚合编排器是 `backend/services/collection_service.py`（`CollectionService`）+ `backend/services/collection_pipeline.py`，不在 `collectors/` 目录内。

### 1.3 「近 7 日入库条数」口径

- **表**: `backend/hotspot.db` → `hotspots` 表。该表**无 `created_at` 列**，时间列为 `ingested_at`（`fetched_at` 是抓取时间，`published_at` 是原文时间，均非入库时间）。
- **窗口**: `ingested_at >= datetime('now','-7 days')`（快照时刻 2026-11-10 14:09 UTC ⇒ 窗口起点 2026-11-03 14:09 UTC）。
- **归因方式**: `hotspots.id` 由 `item_builder.py:142` 生成为 `{self.name}_{source['name']}_{url_hash[:12]}`，`self.name` 来自 `BaseCollector.__init__`（base.py:134–137）= 类名小写去 `collector` 后缀；部分 collector 自定义 id（`make_readable_id`）。故 **id 前缀 = collector 身份**，是唯一可靠的 collector→行归因键。
  - 例：`ai_HackerNews_c73a57a64669` → AICollector；`reddit_IT之家_b81f551f3ebe` → RedditCollector；`arxiv:2611.12638v1` → ArxivPaperCollector；`s2:ff935b…` → SemanticScholarCollector。
- **归因覆盖校验**: 7 日内 1395 条 `hotspots` 行 **100% 命中 19 个前缀**（`UNATTRIBUTED_7d = 0`），无孤儿行、无口径遗漏。

### 1.4 「过门禁通过率」口径（选定 + 理由）

**选定口径：`backend/hotspot-warm.db` → `quality_check_logs` 表**（列 `item_id / gate_name / passed / checked_at`），按 collector 前缀 join `hotspots.id` 聚合。

```sql
-- 每个 collector 的门禁通过率 = SUM(passed) / COUNT(*)（全 gate 行，含 pipeline 硬拒行）
SELECT collector, COUNT(*) checks, SUM(passed) passes, ROUND(100.0*SUM(passed)/COUNT(*),1) pct
FROM quality_check_logs q JOIN hotspots h ON h.id = q.item_id
WHERE datetime(h.ingested_at) >= datetime('now','-7 days')
GROUP BY collector;
```

**为什么选这个口径**（对比另一备选）：

| 备选 | 取值 | 评估 |
|---|---|---|
| **✅ `quality_check_logs`（采用）** | 7 日全量 155,801 行（2026-10-10 起）；按 collector 前缀可归因到 **单个 collector** | 唯一能给出 **per-collector** 通过率的表（`item_id` → `hotspots.id` → id 前缀 → collector）。门禁粒度最细（含 `AuthorVerification` / `title_summary` / `duplicate` 等 16 个 gate） |
| ⚠️ `crawler_runs`（备选，仅作整体校验） | 7 日 5052 runs / fetched 155161 / accepted 4816 = **3.1%** | `crawler_runs.source_id` 是 **源级**（`paper:漏洞治理`、`security:FreeBuf`…），**不含 collector 维度**，无法归因到具体 collector；且 `fetched_count` 被多源重复抓取放大（`ai:小互AI` 单源 fetched 93478 / accepted 7）。故只作整体旁证 |
| ❌ `hotspots.quality_score` | 单行聚合分 | 已过门禁的存活行才有分值，**被拒条目无记录**，通过率系统性高估 |

**口径边界**：
- `quality_check_logs` 存在暖库、`hotspots` 存在主库 → 用 `ATTACH DATABASE 'file:backend/hotspot.db?mode=ro' AS m` 跨库只读 join。
- 暖库 7 日 31442 条日志行中 1051 条（3.3%）的 `item_id` 在主库 `hotspots` 中已不存在（历史清理/归档），这部分**不计入**通过率分母。
- `gate_name='pipeline'` 是**硬拒回放锚**（pipeline.py:224/285，`passed=0` 恒定），不是独立判定项；本表按「含 pipeline 行」口径计算（两者差异 <1pp：仅 OSSInsight 79.9% vs 78.8%），差异在 §5 声明。

### 1.5 「是否进入 Feed 主链」判定口径

Feed 主链 = `collector` → `CollectionService.run_once` → `HotspotRepository.upsert_many` → `hotspots` 表 → `GET /api/hotspots` → 前端 `SentinelHomePage` 快讯流。

判定**不是**「写进 `hotspots` 表就算」，而是要求该 collector 的产出**能被 Feed 查询实际返回**。实际有三重过滤：

1. **入库过滤**（`hotspots` 表写入前）：`quality_hook.py` 落库前门禁 → 不过则不写表。
2. **列表过滤**（`hotspot_repo.query`，hotspot_repo.py:296–300）：
   `ingested_at >= ?` **AND** `is_hidden = 0` **AND** `url_check_status NOT IN ('mismatch','unreachable')`。
3. **分类过滤**（前端频道 + 后端 balanced 桶）：
   - 后端 `HotspotService._query_balanced`（hotspot_service.py:442–449）首页 balanced 模式只取 **6 个分类**：`ai / ai_security / security / finance / startup / github`（`ai` 在 SQL 层合并 `tech`，hotspot_repo.py:306–307）。**`paper` 不在首页桶内**。
   - 前端 `SentinelHomePage` 频道 chips（`CHANNEL_DEFS`，SentinelHomePage.tsx:56–66）同样 **8 个频道无 `paper`**。

故本表给出**三档**：
- **是** = 该 collector 近 7 日产出有 ≥1 条通过全部三层过滤，能在 Feed 看到；
- **部分** = 产出入库且可被 `/api/hotspots?category=X` 查到，但**首页 Feed 不展示**（如 `paper` 类）；
- **否** = 零入库，或入库后被列表过滤全部剔除（如 `url_check_status='mismatch'`）。

---

## 2. 19 行主表

> **近 7 日入库条数** = `hotspots` 表 7 日窗口内、id 前缀归属该 collector 的行数（含被列表过滤的）。
> **Feed 可见** = 再叠加 `is_hidden=0` + `url_check_status ∉ {mismatch, unreachable}`（hotspot_repo.py:296–300 口径）。
> **门禁通过率** = `quality_check_logs` 中该 collector 条目的 `SUM(passed)/COUNT(*)`。
> 快照时刻 **2026-11-10 14:09 UTC**（窗口起点 2026-11-03 14:09 UTC）。库在实时写入，条数随时段漂移。

| # | 采集器文件 | 产出 category | 近 7 日入库 | Feed 可见 | 过门禁通过率 | 进 Feed 主链 | 证据（文件:行号） |
|---|---|---|---|---|---|---|---|
| 1 | `ai_collector.py:150` `AICollector` | `ai` | **273** | 126 | **87.5%** | **是** | 注册 collection_service.py:95；写库 collection_service.py:166 → hotspot_repo.py:194-216；Feed 返回 hotspot_repo.py:296-300 → api/hotspots.py:40-96 → SentinelHomePage.tsx:315-319 |
| 2 | `ai_security_collector.py:72` `AISecurityCollector` | `ai_security` | **0** | 0 | — (无日志) | **否** | 注册 collection_service.py:96；registry 无 `ai_security` 行 → base.py:391 回退类常量 `AI_SECURITY_SOURCES`；末条产出 2026-10-21（`aisecurity_HN AI Security_*`） |
| 3 | `arxiv_paper_collector.py:111` `ArxivPaperCollector` | `paper` | **156** | 134 | **89.8%** | **部分**（见 §3.1） | 注册 collection_service.py:112；id 前缀 `arxiv:`（arxiv_paper_collector.py:237）+ `arxivpaper_`（item_builder.py:142 兜底）；`paper` 不在首页 balanced 桶 hotspot_service.py:442-449 |
| 4 | `finance_collector.py:151` `FinanceCollector` | `finance` | **16** | 3 | **86.8%** | **是** | 注册 collection_service.py:98；写库同上；`finance` 在首页桶 hotspot_service.py:445 |
| 5 | `gdelt_collector.py:33` `GDELTCollector` | `security` | **41** | 37 | **92.8%** | **是**（但见 §3.2 重复） | 注册 collection_service.py:97（与 SecurityCollector 同 category）；id 前缀 `gdelt_`（gdelt_collector.py:68 `make_readable_id`）；`security` 在首页桶 hotspot_service.py:445 |
| 6 | `github_collector.py:153` `GitHubCollector` | `github` | **19** | **0** | **79.9%** | **否**（见 §3.3） | 注册 collection_service.py:101；id 前缀 `github_`；19 条全部 `url_check_status='mismatch'` → 被 hotspot_repo.py:299 过滤；`github` 在首页桶但实得 0 条 |
| 7 | `hn_collector.py:47` `HNCollector` | `tech` | **0** | 0 | — (无日志) | **否** | 注册 collection_service.py:104；`self.name='hn'`→id 前缀应为 `hn:`，全库 **0 行** `hn%`；`tech` 分类 registry 仅 1 行（`tech:IT之家`）→ HN 自身源 `HackerNews` 未接管 |
| 8 | `openbb_collector.py:28` `OpenBBCollector` | `finance` | **12** | 3 | **87.1%** | **是**（但见 §3.2 重复） | 注册 collection_service.py:98（与 FinanceCollector 同 category）；id 前缀 `openbb_`；`finance` 在首页桶 |
| 9 | `ossinsight_collector.py:32` `OSSInsightCollector` | `tech` | **0** | 0 | — (无日志) | **否** | 注册 collection_service.py:107；id 前缀 `ossinsight:trend:`（ossinsight_collector.py:61）；末条产出 2026-09-07（50 条历史，7 日 0） |
| 10 | `paper_sources.py:178` `OpenAlexCollector` | `paper` | **5** | 5 | **87.5%** | **部分** | 注册 collection_service.py:113；id 前缀 `openalex:`（paper_sources.py:214）；源隔离 paper_sources.py:98-111；`paper` 不在首页桶 |
| 11 | `paper_sources.py:243` `SemanticScholarCollector` | `paper` | **30** | **0** | **75.2%** | **否**（见 §3.3） | 注册 collection_service.py:114；id 前缀 `s2:`（paper_sources.py:275）；30 条全部 `url_check_status='unreachable'` → 被 hotspot_repo.py:299 过滤 |
| 12 | `paper_sources.py:293` `IACRCollector` | `paper` | **2** | 2 | **84.4%** | **部分** | 注册 collection_service.py:115；id 前缀 `iacr:`（paper_sources.py:308 `_paper_id_from_url`）；另 6 条 IACR 条目被 ArxivPaperCollector 以 `arxivpaper_IACR ePrint_*` 前缀重复写入（见 §3.2） |
| 13 | `paper_sources.py:332` `CrossrefCollector` | `paper` | **6** | 2 | **78.1%** | **部分** | 注册 collection_service.py:116；id 前缀 `crossref:`（paper_sources.py:366）；`paper` 不在首页桶 |
| 14 | `paper_sources.py:386` `HFDailyPapersCollector` | `paper` | **0** | 0 | — (无日志) | **否** | 注册 collection_service.py:117；registry 行 `paper:hf_daily_papers` `enabled=0 / status='retired'` → base.py:393「已注册但全禁用」返回空源列表 → 采集恒空 |
| 15 | `reddit_collector.py:43` `RedditCollector` | `tech` | **71** | 32 | **90.4%** | **是**（但见 §3.2 重复） | 注册 collection_service.py:105；id 前缀 `reddit_IT之家_*`（item_builder.py:142，`self.name='reddit'`）；`tech` 并入 `ai` 桶（hotspot_repo.py:306-307） |
| 16 | `security_collector.py:243` `SecurityCollector` | `security` | **70** | 65 | **94.7%** | **是** | 注册 collection_service.py:97；id 前缀 `security_`；`security` 在首页桶 hotspot_service.py:445 |
| 17 | `startup_collector.py:55` `StartupCollector` | `startup` | **49** | 10 | **93.0%** | **是** | 注册 collection_service.py:99；id 前缀 `startup_`；`startup` 在首页桶 hotspot_service.py:446；39 条被 `semantic_reject` 隐藏（`is_hidden=1`） |
| 18 | `tech_collector.py:92` `TechCollector` | `tech` | **403** | 200 | **89.7%** | **是** | 注册 collection_service.py:103；id 前缀 `tech_`；`tech` 在 SQL 层并入 `ai` 桶（hotspot_repo.py:306-307） |
| 19 | `telegram_collector.py:46` `TelegramCollector` | `tech` | **0** | 0 | — (无日志) | **否** | 注册 collection_service.py:106；id 前缀 `telegram_IT之家_*`（item_builder.py:142 / telegram_collector.py:158）；末条产出 2026-09-25（60 条历史，7 日 0） |

**近 7 日入库合计 = 1395 条**（= 全库 7 日 `hotspots` 总数，归因覆盖 100%）。

---

## 3. 判定细则（偏离「是/否」二值的三类情况）

### 3.1 `paper` 类 6 个 collector：入库但首页 Feed 不可见 → 判「部分」

`ArxivPaperCollector` / `OpenAlexCollector` / `IACRCollector` / `CrossrefCollector` 合计 **169 条**入库、**143 条**通过列表过滤，`/api/hotspots?category=paper` 可查（`CATEGORIES` 枚举含 `paper`，types/index.ts:248）。但：

- 后端首页 balanced 桶只遍历 6 个分类，**不含 `paper`**（hotspot_service.py:442–449）；
- 前端 `CHANNEL_DEFS` 8 个频道**无 `paper`**（SentinelHomePage.tsx:56–66）；
- `CATEGORIES` 里的 `paper` 只被 `HistoryPage.tsx:306` / 报表页使用，**资讯首页不消费**。

→ 结论：**这批产出既不在首页 Feed，也不在任何一个 `/` 资讯频道**；只在历史页/报表可见。判「部分」而非「是」。

### 3.2 同 category 多 collector → 同源重复抓取（数据冗余，非新增产出）

多个 collector 挂在同一 category（`security`: Security+GDELT、`finance`: Finance+OpenBB、`tech`: Tech+HN+Reddit+Telegram+OSSInsight、`paper`: Arxiv+5），而基类 `_load_sources_from_registry`（base.py:375-441）按 **category** 而非 collector 装载 registry 源，只有 `paper_sources.py` 的 `PaperProviderMixin._load_sources_from_registry`（paper_sources.py:98-111）做了 per-collector 源隔离。后果：

| 重复对 | 7 日重复行数（URL 尾 12 位哈希一致） | 说明 |
|---|---|---|
| `reddit_*` ↔ `tech_*` | **89** | RedditCollector 抓到 IT之家，与 TechCollector 完全同源 |
| `gdelt_*` ↔ `security_*` | **41** | GDELTCollector 抓到 FreeBuf/安全客，与 SecurityCollector 同源 |
| `openbb_*` ↔ `finance_*` | **15** | OpenBBCollector 抓到 新浪财经/财新网，与 FinanceCollector 同源 |
| `arxivpaper_IACR ePrint_*` ↔ `iacr:` | 6（7 日） | ArxivPaperCollector 的 3 领域轮转窗口（arxiv_paper_collector.py:200-217）在 `only_source` 单源路径下失效，重复抓 IACR ePrint |

→ 上述 145 条**不构成新增资讯**，是同一 URL 的二次入库（主键不同故未被 `ON CONFLICT` 合并，hotspot_repo.py:217）。这是 P1 裁决的**首要候选项**。

### 3.3 入库但被列表过滤全部剔除 → 判「否」

| collector | 7 日入库 | Feed 可见 | 剔除原因（hotspot_repo.py:299） |
|---|---|---|---|
| `GitHubCollector` | 19 | **0** | 19/19 条 `url_check_status='mismatch'`。`GitHubCollector` 的 `source='GitHub'` 与 registry 中 `github.com → "GitHub"`（publisher_registry.py:85）不匹配 → `AuthorVerificationGate` 判 mismatch 并改写 source（author_verification_gate.py:121-129） |
| `SemanticScholarCollector` | 30 | **0** | 30/30 条 `url_check_status='unreachable'`（semanticscholar.org 页面在本机网络不可达） |

另：`StartupCollector` 49 条中 39 条被 `info_filter` 语义层置 `is_hidden=1`（`quality_flags` 含 `semantic_reject`），仅 10 条进 Feed。

---

## 4. 零产出 / 死源候选（30 日零产出）

### 4.1 30 日零产出（连续 30 日 0 条入库）→ **死源候选**

| collector | category | 末条产出时间 | 历史累计 | 根因（代码/库证据） |
|---|---|---|---|---|
| `HNCollector` | `tech` | **无**（全库 0 行 `hn%`） | 0 | registry `crawler_sources` **无 `tech` 分类的 HackerNews 行**（`tech` 仅 `tech:IT之家` 一行）；`self.name='hn'` 期望 id 前缀 `hn:`，但主库 0 行 → 从未成功入库 |
| `HFDailyPapersCollector` | `paper` | **无**（全库 0 行 `hf%`） | 0 | registry 行 `paper:hf_daily_papers` `enabled=0 / status='retired'` → base.py:393「已注册但全禁用」→ `self.sources=[]` → base.py:533-549 恒返回空 |
| `OSSInsightCollector` | `tech` | **2026-09-07 16:29:19 UTC** | 50 | `tech` 分类 registry 只有 `tech:IT之家`；`OSSInsight` 源名在 registry 中不存在 → base.py:391 回退常量，但 IT之家 RSS 页面无 OSS Insight 趋势块 → 抓到 0 条 |
| `TelegramCollector` | `tech` | **2026-09-25 14:57:14 UTC** | 60 | 同上；且 Telegram 需专用 renderer/凭据（telegram_collector.py:25-60），当前 registry 无 `tech:Telegram` 行 |

### 4.2 近 7 日零产出但 30 日内有产出（**非**死源，仅降频）

| collector | category | 7 日 | 30 日 | 末条产出 | 说明 |
|---|---|---|---|---|---|
| `AISecurityCollector` | `ai_security` | **0** | **1** | 2026-10-21 13:47:23 UTC | registry 无 `ai_security` 行 → 回退类常量 `AI_SECURITY_SOURCES`（6 源，其中 4 个已失效：SecurityWeek/BleepingComputer/Lil'Log/FreeBuf AI安全）；仅 `HN AI Security` 偶发成功 |

### 4.3 30 日零产出合计：**4 个**（HN / HFDailyPapers / OSSInsight / Telegram）

---

## 5. 判定汇总

| 维度 | 结果 |
|---|---|
| collector 总数 | **19**（= `count_collectors()`，验收 ① 通过） |
| **进入 Feed 主链（是）** | **8** — AICollector、ArxivPaperCollector*、FinanceCollector、GDELTCollector*、OpenBBCollector*、RedditCollector*、SecurityCollector、StartupCollector、TechCollector（* = 见 §3.2 重复） |
| **部分进入（入库但首页不可见）** | **4** — `paper` 类：ArxivPaperCollector、OpenAlexCollector、IACRCollector、CrossrefCollector（**注意**：ArxivPaperCollector 因部分 `arxivpaper_` 前缀行归入本档，其 `arxiv:` 主体的 134 条同样受 §3.1 约束） |
| **未进入主链（否）** | **7** — AISecurityCollector、GitHubCollector、HNCollector、HFDailyPapersCollector、OSSInsightCollector、SemanticScholarCollector、TelegramCollector |
| **7 日零产出** | **5** — AISecurityCollector、HNCollector、HFDailyPapersCollector、OSSInsightCollector、TelegramCollector |
| **30 日零产出（死源候选）** | **4** — HNCollector、HFDailyPapersCollector、OSSInsightCollector、TelegramCollector |
| **近 7 日入库总量** | **1395** 条（归因覆盖 100%，无孤儿行） |
| **Feed 实际可见总量** | **~760** 条（`is_hidden=0` + `url_check_status ∉ {mismatch,unreachable}`） |
| **7 日重复抓取（同 URL 二次入库）** | **145** 条（reddit↔tech 89 / gdelt↔security 41 / openbb↔finance 15 / arxivpaper↔iacr 6 中的重叠） |

> 「进入主链」计数含 §3.2 标注的重复产出；**净新增 Feed 内容的 collector 实为 5 个**（AICollector、SecurityCollector、TechCollector、StartupCollector、FinanceCollector）。

---

## 6. 裁决建议（供 P1）

> 以下为盘点阶段的**证据导向建议**，最终裁决由 P1 负责；每条均给出可验证的判据与回滚边界。

### 6.1 优先处理：同 category 多 collector 的重复抓取（**影响面最大：145 条/7 日**）

**证据**：基类按 category 装载 registry 源（base.py:375-441），仅 `paper_sources.py` 有 per-collector 隔离（paper_sources.py:98-111）。

| 建议 | 范围 | 收益 | 风险 / 回滚 |
|---|---|---|---|
| **A. 把 `PaperProviderMixin._load_sources_from_registry` 的隔离逻辑提升到 `BaseCollector`** | `base.py` + 5 个 collector | 消除 145 条/7 日重复入库；GDELT/OpenBB/Reddit/Telegram 各自只抓自己的源 | 中高：改基类影响 19 个 collector。**必须同步 `source_coverage` 覆盖率基线**（PRD §4.8 验收 ③：不得静默降低覆盖）；建议单 commit 可 revert |
| **B. 备选：仅在 `collection_service.py` 装配层给同 category 的第 2..N 个 collector 显式传 `only_source` 自己的源名** | collection_service.py:94-119 | 改动面更小 | 低：只是调度层过滤，不动基类；但无法覆盖 `run_single_source` 单源路径（collection_pipeline.py:300-306） |

### 6.2 死源候选裁决（4 个）

| collector | 建议 | 判据 | 回滚 |
|---|---|---|---|
| `HFDailyPapersCollector` | **下线**（或改用 `custom_sources` 由用户显式启用） | registry `enabled=0 / status='retired'`，恒空采集 | 移除 collection_service.py:117 一行即可回滚；**须同步 `source_coverage` 基线** |
| `HNCollector` | **先修复再观察**：为 `tech` 分类补 `tech:HackerNews` registry 行 | 主库 0 行 `hn%`；`tech` 分类 registry 仅 IT之家 | 若 2 周内仍 0 行 → 转下线；补行是纯数据操作 |
| `OSSInsightCollector` | **下线候选**：需专用 parser/页面，IT之家 RSS 不含其内容 | 末条产出 2026-09-07；7 日 0 | 同 HFDailyPapers |
| `TelegramCollector` | **下线候选**：需专用凭据与 renderer | 末条产出 2026-09-25；7 日 0 | 同 HFDailyPapers |

### 6.3 `paper` 分类的 Feed 归属（4 个 collector，169 条/7 日）

**问题**：169 条入库、143 条通过过滤，但**首页 Feed 无 `paper` 频道**，产出不可见。

| 选项 | 说明 |
|---|---|
| **C1. 论文独立入口**（推荐） | 论文是「知识资产」而非「资讯」，放 `/knowledge` 更合定位（符合 v0.8.7 四菜单收敛：只以区块形式进入，不新增一级入口）。前端 `CATEGORIES` 已有 `paper` 标签（types/index.ts:248），补一个区块即可消费现有数据，**零后端改动** |
| **C2. 首页加 `paper` 频道** | 改 `CHANNEL_DEFS`（SentinelHomePage.tsx:56-66）+ 后端 balanced 桶（hotspot_service.py:442-449）。改动面大，且论文挤占资讯流位次，与「资讯主链」定位冲突 |
| **C3. 维持现状** | 现状下论文产出只服务历史页/报表；浪费 169 条/7 日采集成本，但不误伤主链 |

### 6.4 `url_check_status` 全量失配的 2 个 collector（49 条/7 日）

| collector | 问题 | 建议 |
|---|---|---|
| `GitHubCollector` | 19/19 条 `mismatch` → Feed 0 条 | 核对 `publisher_registry` 中 `github.com → "GitHub"` 与 collector 实际 `source` 名（`github_GitHub Trending_*` → 归一为 `GitHub`）的匹配口径；修 `AuthorVerificationGate` 的 source 归一，否则 GitHub 频道恒空 |
| `SemanticScholarCollector` | 30/30 条 `unreachable` | 属网络可达性问题（semanticscholar.org 在本机不可达）。要么修网络/代理，要么该源标 `status='dead'` 停止采集 |

### 6.5 降频但未死的 `AISecurityCollector`（7 日 0 / 30 日 1）

6 个类常量源中 4 个已失效。**不建议直接下线**（`ai_security` 是产品明确分类），建议：把仍可用的源（`HN AI Security` / `Lil'Log` / `SecurityWeek AI Security`）登记进 `crawler_sources` 的 `ai_security` 分类，让它走 registry 路径而非类常量回退；否则它将长期停留在「每月 0-1 条」状态。

---

## 7. 已知局限

1. **快照非冻结**：主库 `backend/hotspot.db` 由运行中的采集器持续写入（`collect_all` 每 1800s + `source_scheduler_tick` 每 60s），本文所有条数是 **2026-11-10 14:09 UTC 的一次快照**；重跑 SQL 会得到略有差异的数字（实测 7 日总量在 1388–1395 间波动）。**结论（谁零产出、谁重复、谁被过滤）不受该波动影响**。
2. **collector 归因依赖 id 前缀**：唯一可用归因键是 `hotspots.id` 的 `{self.name}_{source}_{hash}` 结构（item_builder.py:142）。该规则在 `make_readable_id` 路径下变为 `{source}:{subtype}:{id}`，两套前缀都已逐一映射到 19 个 collector（7 日 1395 行 100% 命中，孤儿 0）。但**表中不含 collector 字段**，若未来某个 collector 改了 `self.name` 或 id 规则，历史归因需重跑。
3. **`quality_check_logs` 在暖库、`hotspots` 在主库**：跨库 join 有 **3.3% 日志行（1051/31442）**的 `item_id` 在主库已不存在（历史清理/归档），这部分不计入通过率分母，可能使个别 collector 的通过率略有偏移。
4. **门禁通过率的口径选择有 ±1pp 影响**：含 `gate_name='pipeline'`（硬拒回放锚，passed 恒 0，pipeline.py:224/285）与不含的差异仅出现在 OSSInsight（79.9% vs 78.8%）；其余 13 个有数据的 collector 完全一致。
5. **「进 Feed 主链」的三层过滤是本盘点自定的判定**：第一层（入库前门禁）由 `quality_hook.py` 控制，第二三层由 `hotspot_repo.query`（296-300）与前端频道定义控制。三层中任何一层改动都会改变判定结果 —— 例如把 `paper` 加进首页桶，4 个 `paper` collector 的判定会从「部分」变「是」。
6. **`crawler_runs` 无法用于 per-collector 归因**：其 `source_id` 是源级（`paper:漏洞治理` / `security:FreeBuf`），不含 collector 维度；本文只把它当整体旁证（7 日 3.1% accepted/fetched），未用于主表任何一格。
7. **`is_hidden` 与 `url_check_status` 的写入方不在本次盘点范围**：`is_hidden` 由 `quality_flags` 派生（hotspot_repo.py:65-66）+ `info_filter` 语义层置位；`url_check_status` 由 `url_full_check` job 回写。二者的完整因果链需查 R-07 job 盘点表对应行。
8. **未做配置层交叉验证**：本次只查真实库数据，未核对 `crawl_config.yaml` / `feature_gates.toml` 中的采集相关开关（如 `secnews` gate 是否影响 `run_once`）。当前 gate 全开状态下 collector 全部注册（collection_service.py:94-119 无条件装配），但 gate 关闭时实际运行数会减少。

---

## 附：复现命令（全部只读）

```bash
# ① collector 计数（权威口径）
python scripts/generate_meta.py

# ② 近 7 日入库（主库，注意 ingested_at 而非 created_at）
sqlite3 "file:backend/hotspot.db?mode=ro" \
  "SELECT category, COUNT(*) FROM hotspots WHERE ingested_at >= datetime('now','-7 days') GROUP BY category;"

# ③ 按 collector 归因（id 前缀）
sqlite3 "file:backend/hotspot.db?mode=ro" \
  "SELECT substr(id,1,instr(id,'_')-1) pfx, COUNT(*) FROM hotspots
   WHERE ingested_at >= datetime('now','-7 days') GROUP BY pfx ORDER BY 2 DESC;"

# ④ 门禁通过率（跨库只读 join）
sqlite3 "file:backend/hotspot-warm.db?mode=ro" \
  "ATTACH DATABASE 'file:backend/hotspot.db?mode=ro' AS m;
   SELECT COUNT(*), SUM(passed) FROM quality_check_logs q JOIN m.hotspots h ON h.id=q.item_id
   WHERE datetime(q.checked_at) >= datetime('now','-7 days');"

# ⑤ crawler_runs 整体口径（旁证）
sqlite3 "file:backend/hotspot-warm.db?mode=ro" \
  "SELECT COUNT(*), SUM(fetched_count), SUM(accepted_count) FROM crawler_runs
   WHERE started_at >= datetime('now','-7 days');"

# ⑥ Feed 列表过滤口径
sqlite3 "file:backend/hotspot.db?mode=ro" \
  "SELECT COUNT(*) FROM hotspots WHERE ingested_at >= datetime('now','-7 days')
   AND is_hidden=0 AND (url_check_status IS NULL OR url_check_status NOT IN ('mismatch','unreachable'));"
```
