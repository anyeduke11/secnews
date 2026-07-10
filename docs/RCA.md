# 热点地图 · 5why + RCA 根因分析 (Phase 13)

> 文档类型：根因分析报告
> 关联：[SPEC.md](./SPEC.md) · [CHECKLIST.md](./CHECKLIST.md) · [TASKS.md](./TASKS.md)
> 版本：2026-07-05
> 范围：复盘 2026-07-04 至 2026-07-05 期间**出现 ≥ 2 次的问题**,用 5why 追溯根因,并输出 SPEC 规范要求,避免再犯

---

## 〇、问题总览

| # | 问题 | 出现次数 | 最终修复 | SPEC 写入 | RCA 编号 |
|---|---|---|---|---|---|
| 1 | fallback 合成 URL(占位符 / 搜索) | **3** | Phase 13 全部撤销 | §3 原文链接硬约束 | [§1](#1-fallback-合成-url-出现-3-次) |
| 2 | 标讯拿不到真实 URL(海外 IP 限制) | **4** | Phase 11 + 13 启用 crawl4ai | §2.1, §3.3.2, §9.4 | [§2](#2-标讯拿不到真实-url-出现-4-次) |
| 3 | 24h 趋势图为空(published_at = fetch time) | **2** | Phase 12 修 HTML 提取 | §2.4, §3.3.2 | [§3](#3-24h-趋势图为空-出现-2-次) |
| 4 | 数据加载失败 500(sync DB 阻塞) | **3** | Phase 8 加 asyncio.to_thread | §6.1, §7.3 | [§4](#4-数据加载失败-500-出现-3-次) |
| 5 | uvicorn orphan workers 抢端口 | **3** | Phase 8 / 11 用 `Get-CimInstance` 杀子进程 | RUNBOOK.md | [§5](#5-uvicorn-orphan-workers-抢端口-出现-3-次) |
| 6 | GitHub 卡片跳 tag 页 / 列表页 | **2** | Phase 9.2 加 FinalUrlGate | §2.7 门禁 #9 | [§6](#6-卡片跳转到-tag页列表页-出现-2-次) |
| 7 | 标题被噪声污染("99 comments" 当标题) | **2** | Phase 10 改 _parse_html 优先 entry-title | §3.4 反例表 | [§7](#7-标题被噪声污染-出现-2-次) |
| 8 | crawl4ai 集成但未启用(默认 USE_CRAWL4AI=0) | **2** | Phase 13 文档化启用步骤 | §2.1, §9.4 | [§8](#8-crawl4ai-集成但未默认启用-出现-2-次) |

---

## 1. fallback 合成 URL (出现 3 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 3 (2026-07-04) | 5 个 collector (ai/security/finance/startup/bid) 各自实现 `_fallback()`,返回 `https://example.com/{cat}/{i}` 占位符 |
| Phase 9 (2026-07-04) | GitHub collector 加入,fallback 用 `_extract_repo_url` 从 title 提取 owner/repo,避免 404 |
| Phase 12 (2026-07-05) | 修 Bid 反馈 "占位符 404",改为 Google 搜索 URL (`https://www.google.com/search?q={title} 招标&hl=zh-CN`) |
| Phase 13 (2026-07-05) | **用户截图反馈**: Google 搜索能直接搜到真实公告(shbid.com / bankofchina.com / gpx-template / kfqgw.beijing.gov.cn)。用户原话:"禁止提供搜索字眼让用户自己搜索资讯"。**全部撤销** |

### 5why 分析

1. **为什么** Phase 12 改用 Google 搜索 URL?
   → 因为 example.com 占位符是 404,用户点了没反应。Google 搜索至少"真实可访问,点了能搜到东西"。
2. **为什么** 这种"至少能搜到东西"的方案仍然不行?
   → 因为它把"信息查找"的负担推给用户。用户的期望是:点开卡片 → 直接读原文 → 不要再搜。
3. **为什么** Phase 3 一开始就用 example.com 占位符?
   → 因为没有真实数据时,UI 不该是空的。开发者默认"有点东西总比没强"。
4. **为什么** 这种"先填点东西"的习惯根深蒂固?
   → 因为 SPEC §6.2 明确写"网络完全断开 → 全走 fallback,服务正常响应",把 fallback 当成"必做"。
5. **为什么** SPEC 把 fallback 写成了"必做"?
   → 因为"系统永远不能返回空"是过时的设计教条。在用户视角,**"空"比"假数据"更可接受**。该教条没经过用户验证。

### 根因 (RCA)

> **设计教条没经过用户验证**。开发者以"系统永远不能返回空"为前提,设计了多层 fallback 兜底(占位 → 搜索 → ...)。但用户的真实期望是"真实优先,空状态可接受"。

### 反思: 为什么同一个问题出现 3 次?

- **占位符 → 搜索**: 都属于"假数据兜底"的变种。开发者只改了 URL 形式,没改"必须提供数据"的底层假设。
- **没找到第一性原理**: 真问题是"为什么源拿不到数据?",而不是"用什么 URL 顶替"。
- **没去问用户**: Phase 12 改 Google 搜索前没问"你接受点击后跳到 Google 搜索页吗?",假设用户能接受。

### SPEC 规范要求 (v3.1 §3 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| `BaseCollector._fallback()` 必须返回 `[]`,子类不得实现 | §3.3.1 | `test_bug_fixes_published_at.py::TestFallbackReturnsEmpty` 6 个 collector 全部覆盖 |
| `BaseCollector.collect()` 全源失败时返回 `[]`,**不**调任何 fallback | §3.3.1 | `TestCollectReturnsEmptyOnAllSourcesFailed::test_collect_no_sources_returns_empty` |
| UI 空分类显示"该分类暂无可用资讯",**不**视为 bug | §2.3, §11.1 | 手动验收 |
| 任何 PR 修改 fallback 行为 **必须**附"用户验收截图" | (新增) | PR review 检查项 |
| 任何 PR 新增合成 URL(`example.com` / `google.com/search` / `bing.com/search`) **必须**拒绝 | (新增) | CI 跑 `grep -rn "example.com\|google.com/search" backend/collectors/` 应无业务代码命中 |

---

## 2. 标讯拿不到真实 URL (出现 4 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 9 (2026-07-04) | 招标源 8 → 30+ 渠道,加四线 AND/OR 关键词过滤 |
| Phase 9.1 (2026-07-04) | bid collector fallback 改为 `https://example.com/bid/security/{i}` |
| Phase 12 (2026-07-05) | 改 fallback 为 Google 搜索 |
| Phase 13 (2026-07-05) | **用户截图**: Google 能搜到 `shbid.com` / `bankofchina.com` / `gpx-template` / `kfqgw.beijing.gov.cn`,证明真实源**可访问**,问题是抓取手段不够强 |

### 5why 分析

1. **为什么** bid 拿不到真实 URL?
   → 中国大陆招标网站(中国政府采购网 / 央采 / 国电网 / 移动 B2B)对海外 IP 限流 / 反爬强,aiohttp 拿到的 HTML 经常是反爬拦截页。
2. **为什么** 海外 IP 会被限流?
   → 招标网站风控识别"非大陆 IP 频繁请求"是爬虫行为,直接返回验证码 / 空内容 / 假数据。
3. **为什么** 不直接用国内代理?
   → 代理是用户配置项,不能假设一定有;且国内代理稳定性参差。
4. **为什么** aiohttp 拿不到真实内容?
   → 因为这些网站大量用 JS 渲染 / WebSocket 推送 / 字体反爬,aiohttp 只发 HTTP GET,拿不到渲染后的 DOM。
5. **为什么** 不直接用 Playwright / 浏览器渲染?
   → 因为之前没集成。Phase 11 才集成 crawl4ai,且默认 `USE_CRAWL4AI=0`,生产环境没启用。

### 根因 (RCA)

> **反爬强的源用纯 HTTP 抓取,拿不到真实内容**。fallback 链(占位 → 搜索)都是治标,真正治本的是**让爬虫能拿到真实数据**(Playwright + Chromium 渲染)。

### 反思: 为什么同一个问题出现 4 次?

- **每次都在 fallback 链上修补**,没去验证"主路径能不能拿到真实数据"。
- **没做端到端验证**: 30+ 招标源里,实际能拿到的有几个?占比多少?需要 dashboard 看到。
- **crawl4ai 集成后默认关闭**: `USE_CRAWL4AI=0` 让 90% 测试场景跑 aiohttp,生产环境也保持关闭,等于"装上但不用"。

### SPEC 规范要求 (v3.1 §2.1, §3.3.2, §9.4 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| 抓取策略:crawl4ai (Playwright) 优先 → 失败 fallback aiohttp | §2.1 | `BaseCollector.fetch_source` 已实现 |
| 反爬强 / JS 渲染的源(bid 中文政府网站)**必须**用 crawl4ai | §3.3.2 | 默认 `USE_CRAWL4AI=1` 时验证 |
| 标讯拿不到真实 URL 时:**优先**启用 crawl4ai 增强,**不**引入搜索 URL 兜底 | §9.4 | 用户反馈后第一时间想到 crawl4ai,**不**想到 Google 搜索 |
| 单源反爬持续 1 周 → 加入 `dead` 源名单(Phase 9 招标源质量门禁) | §9.4 | 监控指标 |

---

## 3. 24h 趋势图为空 (出现 2 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 5 (2026-07-04) | 上线 24h 趋势图,但用户反映"趋势图总是空的" |
| Phase 12 (2026-07-05) | 根因:所有 hotspot `published_at` 都 = fetch time,分布全在 0 时刻。修复:在 `_parse_html` 提取页面级发布时间 |

### 5why 分析

1. **为什么** 趋势图是空的?
   → 因为 `trend_repo.rebuild()` 按 `published_at` 分桶,所有数据 `published_at = fetch time`,全部集中到 0 时刻。
2. **为什么** 所有 `published_at` 都 = fetch time?
   → 因为 `_build_items` 只在 `raw["published_at"]` 缺失时用 `now()`,而原始抓取流程根本没填 `published_at`。
3. **为什么** 原始抓取流程没填 `published_at`?
   → 因为列表页 HTML 没有"每篇文章的发布时间",只有"页面更新时间",开发者没处理这种情况。
4. **为什么** 列表页没有"每篇文章发布时间"是常见现象?
   → 因为列表页设计就是"标题 + 链接 + 简短摘要",发布详情在子页。这是个普遍模式,不是 bug。
5. **为什么** 之前没识别到"页面级发布时间"这种兜底?
   → 因为架构图里没显式区分"页面级时间" vs "单条 item 时间",导致实现走偏。

### 根因 (RCA)

> **列表/索引页没有单条 item 发布时间是普遍模式,代码没处理页面级时间兜底**。架构图里也没明确"页面级时间"这一概念,导致设计阶段就遗漏。

### 反思: 为什么同一个问题出现 2 次?

- **趋势图空但没告警**: 数据进来了、UI 没崩,所以没被监控到,直到用户主动反馈。
- **schema 设计**: `published_at` 字段语义模糊("发布时间" = 页面? = 单条?),开发各按各的理解实现。

### SPEC 规范要求 (v3.1 §2.4, §3.3.2 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| `published_at` 语义: 列表页用页面级时间,详情页用文章时间 | §3.3.2 | 单元测试覆盖 8 种 pattern (JSON-LD / meta / time / URL slug) |
| 趋势图 24h 分布必须显示真实小时分布,**不**能全部集中 0 时刻 | §2.4 | E2E 测试验证 `bucket 0h` < 30% (非 fallback 数据) |
| 抓取流程如果无法获得 `published_at`,**不**允许 fallback 到 `now()`,应当 drop item 或用页面级时间 | §3.3.1 | 代码 review 检查项 |

---

## 4. 数据加载失败 500 (出现 3 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 7 (2026-07-05) | 试运行 9min 段发现:collect 期间 `/api/hotspots` P95 21s+,部分请求 500 |
| Phase 8 (2026-07-05) | 第一次修复: 把 sync urllib 提到 thread pool |
| Phase 8.5 (2026-07-05) | **完全修复**: 7 个文件 (collection_service / jobs / hotspots / trends / categories / health / quality / export) 全部用 `asyncio.to_thread` 包 sync DB |

### 5why 分析

1. **为什么** collect 期间 API 会 500?
   → 因为 `collect_all_job` 在 event loop 里跑,内部调 `repo.upsert_many` 这种 sync sqlite 操作,阻塞 21-23s。
2. **为什么** 阻塞 21s+?
   → 因为 SQLite 写 50+ 个 item + 重建 trend 桶 + 写 collection_run 表,串行执行无 thread pool。
3. **为什么** 不在子进程跑 collect?
   → 因为 collect 需要 scheduler 协调,跨进程传递事件状态复杂。
4. **为什么** FastAPI 跑 collect 任务?
   → 因为 scheduler 是单进程,跟 FastAPI 共享 event loop,设计上耦合。
5. **为什么** 设计时没考虑 collect 期间 API 可用性?
   → 因为"本地单人使用,反正只有我访问"的假设没被验证;试运行才发现 collect 期间 API 完全卡死。

### 根因 (RCA)

> **scheduler / FastAPI 共享 event loop + sync sqlite 操作**导致 collect 期间 API 全卡。设计时假设"本地单人用不会有问题",试运行才暴露。

### 反思: 为什么同一个问题出现 3 次?

- **Phase 7 → Phase 8**: 只修了"URL validity gate 的 sync urllib",没修其他 sync DB 调用,治标不治本。
- **Phase 8 → Phase 8.5**: 才意识到"所有 sync DB 操作都要包 to_thread",一次性改 7 个文件。

### SPEC 规范要求 (v3.1 §6.1, §7.3 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| 所有 sync DB 操作**必须**用 `asyncio.to_thread` 包裹,无论调用频率 | §7.3 | 代码 review 检查项 + lint rule |
| collect 期间 API 延迟 P95 < 500ms | §6.1 | 试运行压测报告 |
| 任何新增 sync 阻塞操作(> 100ms) 必须先评估并放到 thread pool | §7.3 | 架构 review 检查项 |

---

## 5. uvicorn orphan workers 抢端口 (出现 3 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 7 (2026-07-05) | uvicorn master 杀掉后,`--multiprocessing-fork` 子进程仍占端口 8000,重启失败 |
| Phase 8 (2026-07-05) | 用 `Get-NetTCPConnection -LocalPort 8000 -State Listen | Stop-Process` 修复 |
| Phase 11 (2026-07-05) | 复发:crawl4ai 集成后重启,子进程还是没杀干净,需用 `Get-CimInstance Win32_Process` 找 `--multiprocessing-fork` 子进程一起 kill |

### 5why 分析

1. **为什么** 杀 master 后子进程还活着?
   → 因为 `uvicorn --workers 4` 用 multiprocessing.spawn 启动子进程,master 退出信号不向下传递。
2. **为什么** 退出信号不向下传递?
   → 因为 uvicorn master 进程是"软退出"(收到 SIGTERM 后只清理自己),子进程在 spawn 后脱离了父进程控制。
3. **为什么** 用 multiprocessing.spawn 而不是 fork?
   → 因为 Windows 不支持 fork,默认走 spawn (Phase 0 早期决策)。
4. **为什么** Windows 默认 spawn?
   → 因为跨平台兼容性: Linux/macOS 用 fork,Windows 用 spawn,uvicorn 抽象了差异但留下隐患。
5. **为什么** 没在 PowerShell stop 脚本里处理子进程?
   → 因为开发在 Linux / WSL 上,Windows 上的 spawn 行为是后来才发现。

### 根因 (RCA)

> **uvicorn `--workers N` 在 Windows 用 spawn 模式,master 退出信号不传给子进程**。本地 stop 脚本没考虑 Windows spawn 行为。

### 反思: 为什么同一个问题出现 3 次?

- **跨平台测试不足**: 脚本在 Linux 跑没事,Windows 上反复复发。
- **stop 脚本不够鲁棒**: 没显式遍历子进程,只 Stop-Process master PID。
- **uvicorn 文档不清晰**: Windows spawn 行为没在 uvicorn 文档里强调。

### SPEC 规范要求 (v3.1 RUNBOOK.md 已写死,本节总结)

| 规范 | 来源 | 验收 |
|---|---|---|
| Windows stop 脚本**必须**用 `Get-CimInstance Win32_Process | Where-Object CommandLine -like '*--multiprocessing-fork*' | Stop-Process` 杀子进程 | RUNBOOK.md | 手动验证 |
| 任何 restart 操作**必须**先 `Get-NetTCPConnection -LocalPort 8000 -State Listen` 确认端口空闲 | RUNBOOK.md | 手动验证 |
| uvicorn 生产配置: 用 `gunicorn` 替代 uvicorn master (gunicorn 退出信号正确传递) | RUNBOOK.md (v3.2+) | 后续 phase |

---

## 6. 卡片跳转到 tag页/列表页 (出现 2 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 9.2 (2026-07-05) | 用户反馈 qbitai 卡片跳到 `qbitai.com/tag/worldclaw` 而不是文章 `qbitai.com/2026/07/442447.html` |
| Phase 9.2 (2026-07-05) | 修复:加 FinalUrlGate,自动下钻 tag/列表页到真实文章页,失败 → drop item |

### 5why 分析

1. **为什么** URL 抓到的是 tag 页?
   → 因为 qbitai 主页的卡片结构是 "title + 链接到 tag 页"(SEO 设计,tag 页聚合相关文章)。
2. **为什么** 用户期望跳到文章页?
   → 因为 tag 页是"分类聚合",用户点开想看的是"该篇文章正文",不是"这个 tag 下的所有文章"。
3. **为什么** 之前没识别到这种"中间层 URL"?
   → 因为默认 `_parse_html` 只看 `<a href>`,不区分"tag 链接" vs "article 链接"。
4. **为什么** 难区分?
   → 因为 DOM 结构上 tag 链接和 article 链接可能长得一样(都是 `<a href="...">title</a>`)。
5. **为什么** 不用 URL pattern 区分?
   → 因为不同站 pattern 不一样(qbitai 用 `/tag/`,hn 用 `/item?id=`,wordpress 用 `?p=`),硬编码 pattern 不可行。

### 根因 (RCA)

> **默认 `_parse_html` 把所有 `<a href>` 当 article 链接,没区分"中间聚合层"(tag / category / search page)**。

### 反思: 为什么同一个问题出现 2 次?

- **qbitai 是首批,后来又复现**: 6 个域名有 12 个 landing pattern,需要持续维护 pattern 库。
- **没在测试覆盖所有已知 pattern**: 单元测试只覆盖了 qbitai 当时的情况。

### SPEC 规范要求 (v3.1 §2.7 门禁 #9, §3.3.3 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| `FinalUrlGate` 是默认门禁之一,QualityGatePipeline 中 **必须** 包含 | §2.7 | `pipeline.DEFAULT_GATES` 验证 |
| 任何新数据源接入,如果 URL 命中已知 landing pattern (`/tag/`, `/category/`, `/search?q=`, `/topic/`, `/topics/`, `/collection/`)**必须**走 FinalUrlGate 下钻 | §3.3.3 | 单元测试 |
| FinalUrlGate 下钻失败 → item drop,**不**保留 tag 页 URL | §3.3.3 | 单元测试 |

---

## 7. 标题被噪声污染 (出现 2 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 10 (2026-07-05) | 用户反馈 krebsonsecurity.com 标题被误抓为 "99 comments" |
| Phase 10 (2026-07-05) | 修复: 优先匹配 `<h1 class="entry-title">` (WordPress 标准),过滤 "X comments" / "Permalink to" |

### 5why 分析

1. **为什么** "99 comments" 被当标题?
   → 因为 `<a>17 Comments</a>` 链接到 `#comments`,正则匹配时它的 text 长度 11 字符,落在 8-80 字符的标题长度区间。
2. **为什么** 评论数链接和文章标题链接长度会重叠?
   → 因为 WordPress 模板里评论数通常 1-3 位数字 + "Comments" 共 10-15 字符,正好和短标题重叠。
3. **为什么** 之前没过滤?
   → 因为默认 `_parse_html` 只看长度,不识别语义(评论数 / Permalink / Skip to content / About 等都不是标题)。
4. **为什么** 不直接选 `<h1>` / `<h2>` 内的链接?
   → 因为有些站点标题不在 `<h1>` 内(WordPress 用 `<h2 class="entry-title">`)。
5. **为什么** 不为每个站写专门的 parser?
   → 因为 30+ 个站,工作量太大;统一 parser 应当兼顾。

### 根因 (RCA)

> **默认 `_parse_html` 用长度阈值判标题,没识别"评论数"这种语义噪声**。

### 反思: 为什么同一个问题出现 2 次?

- **krebsonsecurity 是首批,后来又复现**: 实际是同类问题(噪声链接被当标题)在其他站又出现。
- **噪声 pattern 没穷举**: 第一次只过滤 "X comments" 和 "Permalink to",后来又发现其他 pattern。

### SPEC 规范要求 (v3.1 §3.4 反例表已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| 标题提取优先 WordPress `entry-title` 标签,fallback 常规 `<a>` 模式 | §3.4 反例表 | 单元测试覆盖 6 个站 |
| 噪声 pattern 过滤列表 (`X comments` / `Permalink to` / `Skip to content` / `About` / 锚点 URL `#comments`) | §3.4 | `test_html_parser.py` |
| 任何 PR 新增数据源,**必须**附 `_parse_html` 单元测试,覆盖至少 5 条噪声 case | (新增) | PR review 检查项 |

---

## 8. crawl4ai 集成但未默认启用 (出现 2 次)

### 时间线

| 时间 | 事件 |
|---|---|
| Phase 11 (2026-07-05) | 集成 crawl4ai (Playwright + Chromium),可选用 `USE_CRAWL4AI=1` 切换 |
| Phase 13 (2026-07-05) | **用户反馈**: 标讯拿不到真实 URL,问 crawl4ai 是不是没启用。根因: 默认 `USE_CRAWL4AI=0`,生产环境一直没切到 `1` |
| Phase 14 (2026-07-06) | **已激活**: `.venv/bin/python -m playwright install chromium` + `.venv/bin/python run.py` + `USE_CRAWL4AI=1`。新增精细化路由(`source.renderer="crawl4ai"`)+ Semaphore 并发控制(默认 3)+ crawl4ai→aiohttp fallback。资讯类(ai/security/finance/startup)采集正常,bid/github 仍被 anti-bot 拦截(`Structural: minimal_text`),需后续更强反爬策略 |

### 5why 分析

1. **为什么** 集成了 crawl4ai 但默认关闭?
   → 因为测试环境没装 Chromium / Playwright,默认开会让 CI 跑不起来。
2. **为什么** 测试环境不装 Chromium?
   → 因为 Chromium 依赖重 (~150MB),CI 启动慢。
3. **为什么** 不分开"测试环境"和"生产环境"配置?
   → 因为本地单人使用,没区分;config.py 没有 `ENV=production` 这种 switch。
4. **为什么** 生产环境也没手动开?
   → 因为文档没强调"生产环境**必须** USE_CRAWL4AI=1",用户也不知道要开。
5. **为什么** 文档没强调?
   → 因为 Phase 11 交付时只关注"集成成功",没关注"启用步骤是否清晰"。

### 根因 (RCA)

> **Phase 11 集成只完成"代码层面",没完成"运维层面"(默认启用、文档强调)**。`USE_CRAWL4AI=0` 是测试便利的默认,但生产没主动切到 `1`。

### 反思: 为什么同一个问题出现 2 次?

- **交付不完整**: "集成" ≠ "能用"。文档 / 默认值 / 运维步骤没跟上。
- **没在 README 强调**: `pip install crawl4ai; crawl4ai-setup; USE_CRAWL4AI=1 python run.py` 这套步骤散落在多个文件,没有 README quick start。

### SPEC 规范要求 (v3.1 §2.1, §9.4 已写死)

| 规范 | 来源 | 验收 |
|---|---|---|
| README.md 显式说明:`USE_CRAWL4AI=1` 是生产推荐值,默认 0 是为了 CI | §2.1 | README 必含 `## 启用 crawl4ai` 章节 |
| 反爬强 / JS 渲染的源(bid 中文政府网站)**必须**用 crawl4ai | §3.3.2 | 默认 `USE_CRAWL4AI=1` 时验证 |
| 任何 PR 新增"集成"类依赖(crawl4ai / playwright / ...),**必须**同时改 README + config.py 默认值建议 | (新增) | PR review 检查项 |

---

## 总结:Phase 13 提取的元规则

从 8 个 RCA 提取的**元规则** (元 = 跨问题通用):

| 元规则 | 解释 | 落地到 SPEC |
|---|---|---|
| **真实优先于"假装有数据"** | UI 空状态可接受,合成 URL 不可接受 | §3 |
| **PR 必须附"用户验收截图"** | 设计教条(系统永远不能空)是错的,用户视角验证才是准绳 | §1 RCA, §3.5 |
| **CI grep 拦截合成 URL** | 任何 `example.com` / `google.com/search` / `bing.com/search` 出现在 `backend/collectors/` 是红色警告 | §1 RCA |
| **架构 review 检查 sync 阻塞** | 任何 sync 阻塞操作(> 100ms)必须先评估 thread pool | §4 RCA, §7.3 |
| **跨平台测试在 Windows 上验证** | PowerShell stop 脚本必须有 `Get-CimInstance` 杀子进程 | §5 RCA, RUNBOOK.md |
| **新数据源接入测试覆盖 ≥ 5 噪声 case** | `_parse_html` 默认实现有局限,新增源必须穷举噪声 | §7 RCA, §3.4 |
| **集成类依赖同步改 README** | 集成 ≠ 能用,文档/默认值/运维步骤必须跟上 | §8 RCA, §2.1 |

---

## 参考

- [SPEC.md §3 原文链接硬约束](./SPEC.md#三原文链接硬约束-v31-写死不可撤销)
- [SPEC.md §11 验收标准](./SPEC.md#十一验收标准)
- [CHECKLIST.md](./CHECKLIST.md)
- [TASKS.md](./TASKS.md)
- [RUNBOOK.md](./RUNBOOK.md)
