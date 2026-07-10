# 热点地图浏览器插件化二次开发方案

> **文档版本**: v1.0 | **日期**: 2026-07-10  
> **项目名称**: Hotspot Browser Extension (热点地图浏览器插件)  
> **基于**: [热点地图](http://localhost:8898) v1.2.0 — 多域热点聚合仪表盘  
> **目标**: 将 FastAPI + React SPA 全栈应用二次开发为 Chromium 内核浏览器插件

---

## 目录

1. [项目概述与背景分析](#一项目概述与背景分析)
2. [架构设计](#二架构设计)
3. [采集层实现方案（核心方案）](#三采集层实现方案核心方案)
4. [质量门禁简约版](#四质量门禁简约版)
5. [存储层设计](#五存储层设计)
6. [数据流设计](#六数据流设计)
7. [Service Worker 生命周期管理](#七service-worker-生命周期管理)
8. [UI / UX 设计](#八ui--ux-设计)
9. [权限与安全](#九权限与安全)
10. [实施路线图](#十实施路线图)
11. [文件清单与改动量评估](#十一文件清单与改动量评估)
12. [风险与对策](#十二风险与对策)
13. [附录：数据源采集对照表](#十三附录数据源采集对照表)

---

## 一、项目概述与背景分析

### 1.1 原始项目能力

热点地图是一个多域热点聚合仪表盘，核心能力：

| 模块 | 能力 |
|------|------|
| **多源采集** | 7 分类 × 20+ 数据源，覆盖 AI / 安全 / 金融 / 创业 / 标讯 / GitHub / 科技 |
| **质量门禁** | 9 级管道（Schema → Recency → Content → Category → Title → URL → Reputation → Author → FinalUrl） |
| **数据存储** | SQLite + WAL + FTS5 全文搜索 |
| **API 层** | FastAPI 13 个 router（热点 / 趋势 / 收藏 / 待办 / 设置 / 密钥 / Skill / 同步等） |
| **前端** | React SPA 21 个组件（Header / CategoryNav / SearchBar / HotspotGrid / TrendChart / 设置 / 收藏 / 待办 / Skill / 密钥 / 同步） |
| **扩展能力** | WebDAV 同步、LLM 密钥管理、AI Skill 安装、跨端配置同步 |

### 1.2 插件化动机

| 痛点 | 当前问题 | 插件化解决 |
|------|---------|-----------|
| 部署门槛 | 需要 Python 3.10+ / FastAPI / uvicorn | 一键安装，零依赖 |
| 进程管理 | 需手动启动/守护服务进程 | 浏览器自动管理 |
| 断网使用 | 服务停止后完全不可用 | IndexedDB 本地缓存，完全离线 |
| 浏览器集成 | 无右键菜单 / Badge / 通知 | 原生集成所有浏览器 API |
| 启动速度 | 后端冷启动 ~3s | 点击即用，即时渲染 |

### 1.3 架构迁移策略

```
原始架构:                          插件架构:
┌──────────────────┐              ┌──────────────────────────────┐
│ Python FastAPI   │              │ Service Worker               │
│  ├─ collectors/  │  ──移植──>   │  ├─ collectors/ (TS 重写)    │
│  ├─ quality/     │  ──移植──>   │  ├─ quality/ (TS 重写)       │
│  ├─ repository/  │  ────>      │  └─ indexed-db.ts            │
│  └─ services/    │  ────>      │       (逻辑内联到 collector)   │
├──────────────────┤              ├──────────────────────────────┤
│ React SPA (Vite) │  ──复用─>   │ Popup / Options / New Tab    │
│  21 个组件       │  90% 复用    │ (React + Vite + @crxjs)      │
├──────────────────┤              ├──────────────────────────────┤
│ SQLite + FTS5    │  ────>      │ IndexedDB + 内存搜索         │
└──────────────────┘              └──────────────────────────────┘
```

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Browser Extension                               │
│                                                                         │
│  ┌──────────────────────┐     ┌──────────────────────────────────────┐  │
│  │    Popup (弹窗)      │     │    Background Service Worker         │  │
│  │  ┌────────────────┐  │     │  ┌──────────────────────────────┐   │  │
│  │  │ Header         │  │     │  │ Collector Scheduler          │   │  │
│  │  │ CategoryNav    │  │     │  │  ├─ alarms["collect"] 5min   │   │  │
│  │  │ SearchBar      │  │     │  │  ├─ alarms["trends"]  1h    │   │  │
│  │  │ HotspotGrid    │  │     │  │  └─ alarms["cleanup"]  24h  │   │  │
│  │  │ TrendChart     │  │     │  └────────────┬─────────────────┘   │  │
│  │  │ StatsPanel     │  │     │               │                      │  │
│  │  │ FavoritesPanel │  │     │  ┌────────────▼─────────────────┐   │  │
│  │  │ TodosPanel     │  │     │  │ 7 Collectors (TS)            │   │  │
│  │  └────────────────┘  │     │  │  ├─ AICollector (5 sources)  │   │  │
│  │  (400×600px)         │     │  │  ├─ SecurityCollector (5)    │   │  │
│  └──────────────────────┘     │  │  ├─ FinanceCollector (4)     │   │  │
│                                │  │  ├─ StartupCollector (4)    │   │  │
│  ┌──────────────────────┐     │  │  ├─ BidCollector (30+)       │   │  │
│  │   Options (设置页)    │     │  │  ├─ GitHubCollector (3)     │   │  │
│  │   - 数据源管理        │     │  │  └─ TechCollector (1)       │   │  │
│  │   - 刷新间隔          │     │  └────────────┬─────────────────┘   │  │
│  │   - 密钥配置          │     │               │                      │  │
│  │   - WebDAV           │     │  ┌────────────▼─────────────────┐   │  │
│  │   - 主题              │     │  │ Quality Pipeline (简约5级)    │   │  │
│  └──────────────────────┘     │  │  Schema → Recency → Category  │   │  │
│                                │  │  → Duplicate → Reputation    │   │  │
│  ┌──────────────────────┐     │  └────────────┬─────────────────┘   │  │
│  │  New Tab (可选替换)   │     │               │                      │  │
│  └──────────────────────┘     │  ┌────────────▼─────────────────┐   │  │
│                                │  │     IndexedDB 存储层         │   │  │
│                                │  │  ├─ hotspots (主表, 带索引)   │   │  │
│                                │  │  ├─ favorites (收藏)         │   │  │
│                                │  │  ├─ todos (待办)             │   │  │
│                                │  │  ├─ trends (趋势桶)          │   │  │
│                                │  │  ├─ settings (设置)          │   │  │
│                                │  │  ├─ secrets (加密密钥)        │   │  │
│                                │  │  └─ meta (采集进度/时间戳)    │   │  │
│                                │  └─────────────────────────────┘   │  │
│                                └──────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │              chrome.alarms · storage · notifications            │    │
│  │              contextMenus · declarativeNetRequest               │    │
│  └────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 框架 | React 18 + TypeScript | UI 渲染 |
| 构建 | Vite + @crxjs/vite-plugin | 扩展构建，自动 manifest |
| 样式 | Tailwind CSS 3.4 | 与原始项目一致 |
| 存储 | idb (IndexedDB wrapper) | 结构化数据持久化 |
| 设置 | chrome.storage.sync/local | 用户偏好 + 密钥 |
| 定时 | chrome.alarms | 后台采集调度 |
| 图表 | Recharts | 趋势可视化（复用） |
| 图标 | lucide-react | 轻量图标 |
| 测试 | Vitest + @testing-library/react | 单元测试 |

### 2.3 目录结构

```
hotspot-extension/
├── public/
│   └── icons/
│       ├── icon16.png
│       ├── icon48.png
│       ├── icon128.png
│       └── icon.svg                    # 含活跃脉冲动画的 SVG
├── src/
│   ├── manifest.ts                     # manifest.json 生成配置
│   ├── background/                     # Service Worker
│   │   ├── service-worker.ts           # 入口: alarms / messages / install
│   │   ├── scheduler.ts                # 采集调度逻辑
│   │   ├── indexed-db.ts              # IndexedDB schema + CRUD
│   │   ├── collectors/                 # 7 个采集器 (TS 移植)
│   │   │   ├── base-collector.ts       # 抽象基类: fetch/fetchRss/parseHtml/buildItems
│   │   │   ├── ai-collector.ts         # AI 资讯 (HackerNews/量子位/36氪AI/机器之心/AIhot)
│   │   │   ├── security-collector.ts   # 安全资讯 (THN/安全客/FreeBuf/嘶吼/PortSwigger)
│   │   │   ├── finance-collector.ts    # 金融资讯 (新浪/东方/财联社/金十)
│   │   │   ├── startup-collector.ts    # 创业资讯 (36氪/虎嗅/投资界/IT桔子)
│   │   │   ├── bid-collector.ts        # 标讯 (30+ 招标平台)
│   │   │   ├── github-collector.ts     # GitHub Trending
│   │   │   └── tech-collector.ts       # IT/科技 (IT之家)
│   │   ├── quality/                    # 简约版质量门禁
│   │   │   ├── pipeline.ts
│   │   │   └── gates/
│   │   │       ├── schema-gate.ts
│   │   │       ├── recency-gate.ts
│   │   │       ├── category-match-gate.ts
│   │   │       ├── duplicate-gate.ts
│   │   │       └── source-reputation-gate.ts
│   │   └── types.ts                    # 后台专用类型
│   ├── popup/                          # 弹窗页面 (核心入口)
│   │   ├── index.html
│   │   ├── main.tsx
│   │   ├── App.tsx                     # 入口 (适配 400×600 弹窗)
│   │   ├── components/                 # 复用原始组件, 适配弹窗尺寸
│   │   │   ├── Header.tsx
│   │   │   ├── CategoryNav.tsx
│   │   │   ├── SearchBar.tsx
│   │   │   ├── HotspotGrid.tsx
│   │   │   ├── HotspotCard.tsx
│   │   │   ├── StatsPanel.tsx
│   │   │   ├── TrendChart.tsx
│   │   │   ├── FavoritesPanel.tsx
│   │   │   └── SettingsPanel.tsx
│   │   └── hooks/                      # React hooks (调 IndexedDB 而非 fetch API)
│   │       ├── useHotspots.ts
│   │       ├── useFavorites.ts
│   │       ├── useTodos.ts
│   │       └── useTrends.ts
│   ├── options/                        # 设置页 (全尺寸)
│   │   ├── index.html
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   └── pages/
│   │       ├── DataSourcesPage.tsx
│   │       ├── SyncPage.tsx
│   │       ├── SecretsPage.tsx
│   │       └── AboutPage.tsx
│   ├── newtab/                         # 新标签页 (可选)
│   │   ├── index.html
│   │   └── main.tsx
│   ├── shared/                         # 前后台共享代码
│   │   ├── types.ts                    # 类型定义 (从原始前端直接复制)
│   │   ├── constants.ts                # 色值 / 分类 / 时间选项
│   │   └── utils.ts                    # 工具函数
│   └── assets/
│       └── styles/
│           └── globals.css             # Tailwind + CSS 变量
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── package.json
└── README.md
```

---

## 三、采集层实现方案（核心方案）

### 3.1 三类数据源及采集方式

原始 20+ 数据源按抓取方式分为三类：

#### 类型 A: RSS 源（插件首选 — 最稳定）

**为什么优先选 RSS**：结构稳定、自带发布时间、无需 JS 渲染、无 CORS 问题

| 原始源 | RSS URL | 原始方式 | 插件方式 |
|--------|---------|---------|---------|
| HackerNews | `https://hnrss.org/newest` | HTML | RSS |
| TheHackerNews | `https://feeds.feedburner.com/TheHackersNews` | HTML | RSS |
| 安全客 | `https://api.anquanke.com/data/v1/rss` | HTML | RSS |
| FreeBuf | `https://www.freebuf.com/feed` | HTML | RSS |
| 嘶吼 | `https://www.4hou.com/feed` | HTML | RSS |
| 量子位 | `https://www.qbitai.com/feed` | crawl4ai → RSS 替代 | RSS |
| 机器之心 | `https://www.jiqizhixin.com/rss` | HTML | RSS |
| 36氪 | `https://36kr.com/feed` | HTML | RSS |
| 虎嗅 | `https://www.huxiu.com/rss/0.xml` | HTML | RSS |
| IT之家 | `https://www.ithome.com/rss/` | HTML | RSS |
| 奇安信 | `https://ti.qianxin.com/feed` | HTML | RSS |
| SANS ISC | `https://isc.sans.edu/dailypodcast.xml` | HTML | RSS |

**TS 实现**:

```typescript
// src/background/collectors/base-collector.ts

async function fetchRss(rssUrl: string, sourceName: string): Promise<RawItem[]> {
  const resp = await fetch(rssUrl, {
    headers: { "User-Agent": "HotspotExtension/1.0" },
    signal: AbortSignal.timeout(12000),  // 12s 超时
  });
  if (!resp.ok) return [];

  const xml = await resp.text();
  const doc = new DOMParser().parseFromString(xml, "text/xml");

  // 同时支持 RSS 2.0 (<item>) 和 Atom (<entry>)
  const entries = [
    ...Array.from(doc.querySelectorAll("item")),
    ...Array.from(doc.querySelectorAll("entry")),
  ];

  return entries
    .map(entry => {
      const title = getElementText(entry, "title")?.trim();
      const link = getElementText(entry, "link")?.trim();
      const summary = getElementText(entry, "description, summary, content\\:encoded")?.trim();
      const pubDate = getElementText(entry, "pubDate, published, updated");
      // 处理 content:encoded 的 CDATA
      const encoded = entry.querySelector("content\\:encoded, content");
      const fullContent = encoded?.textContent?.trim() || summary;
      return { title, url: link, summary: fullContent, published_at: pubDate };
    })
    .filter(it => it.title && it.url);
}

function getElementText(parent: Element, selectors: string): string | null {
  for (const sel of selectors.split(", ")) {
    const el = parent.querySelector(sel);
    if (el?.textContent) return el.textContent;
  }
  return null;
}
```

#### 类型 B: JSON API 源（次优选 — 直接 fetch）

| 原始源 | API URL | 插件方式 |
|--------|---------|---------|
| AIhot | `https://aihot.virxact.com/api/public/items?mode=all&take=30` | fetch JSON |
| GitHub Trending | `https://api.github.com/search/repositories?q=created:>YYYY-MM-DD&sort=stars` | fetch JSON |
| 东方财富 | 自有 JSON API | fetch JSON |

```typescript
async function fetchJsonApi(apiUrl: string, headers?: Record<string, string>): Promise<any> {
  const resp = await fetch(apiUrl, {
    headers: { "User-Agent": "HotspotExtension/1.0", Accept: "application/json", ...headers },
    signal: AbortSignal.timeout(12000),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
```

#### 类型 C: HTML 解析源（最后手段 — DOMParser）

| 原始源 | 原始方式 | 插件方式 |
|--------|---------|---------|
| 投资界 (pedaily.cn) | HTML | RSS 优先, fallback DOMParser |
| 财联社 (cls.cn) | HTML+JS | DOMParser SSR |
| 金十数据 | JS var | 正则提取 |
| 中国政府采购网 | crawl4ai | 第三方聚合站替代 |

```typescript
function parseHtmlLinks(html: string, baseUrl: string): RawItem[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const links = Array.from(doc.querySelectorAll("a[href]"));
  return links
    .map(a => ({
      title: (a.textContent || "").trim(),
      url: resolveUrl(a.getAttribute("href") || "", baseUrl),
      summary: "",
      published_at: null,
    }))
    .filter(it => it.title && it.url && it.title.length >= 8 && !isNavCta(it.title))
    .slice(0, 50);
}
```

### 3.2 三层 fallback 采集策略

每个 Collector 内部按优先级尝试三种数据源：

```typescript
// src/background/collectors/base-collector.ts
// 三层降级采集

interface SourceConfig {
  name: string;
  url: string;
  rssUrl?: string;       // 优先级 1
  apiUrl?: string;        // 优先级 2
  score: number;
  renderer?: "rss" | "json" | "html" | "disabled";
  headers?: Record<string, string>;    // API 专用 headers
  parseJson?: (data: any) => RawItem[]; // JSON 解析器 (子类注入)
}

async function fetchSource(source: SourceConfig): Promise<FetchResult> {
  // ★ 优先级 1: RSS (最可靠)
  if (source.rssUrl) {
    try {
      const items = await fetchRss(source.rssUrl, source.name);
      if (items.length > 0) return { items, source: source.name, error: null };
    } catch (err) {
      console.warn(`[${source.name}] RSS failed, fallback to API/HTML`);
    }
  }

  // ★ 优先级 2: JSON API (次可靠)
  if (source.apiUrl && source.parseJson) {
    try {
      const data = await fetchJsonApi(source.apiUrl, source.headers);
      const items = source.parseJson(data);
      if (items.length > 0) return { items, source: source.name, error: null };
    } catch (err) {
      console.warn(`[${source.name}] API failed, fallback to HTML`);
    }
  }

  // ★ 优先级 3: HTML 解析 (最后手段)
  if (source.renderer !== "disabled") {
    try {
      const html = await fetchHtml(source.url);
      const items = parseHtmlLinks(html, source.url);
      if (items.length > 0) return { items, source: source.name, error: null };
    } catch (err) {
      console.warn(`[${source.name}] HTML failed`);
    }
  }

  return { items: [], source: source.name, error: "all strategies failed" };
}
```

### 3.3 7 个 Collector 的具体实现

#### AICollector — 5 源

```typescript
// src/background/collectors/ai-collector.ts

export class AICollector extends BaseCollector {
  readonly name = "ai";
  readonly category = "ai";
  readonly maxItems = 50;
  readonly sources: SourceConfig[] = [
    {
      name: "HackerNews",
      url: "https://news.ycombinator.com/",
      rssUrl: "https://hnrss.org/newest?points=50",  // ≥50 分
      score: 80,
    },
    {
      name: "量子位",
      url: "https://www.qbitai.com/",
      rssUrl: "https://www.qbitai.com/feed",  // ★ 替代 crawl4ai
      score: 78,
    },
    {
      name: "36氪AI",
      url: "https://36kr.com/information/AI",
      rssUrl: "https://36kr.com/feed",
      score: 75,
      renderer: "rss",  // RSS 替代
    },
    {
      name: "机器之心",
      url: "https://www.jiqizhixin.com/",
      rssUrl: "https://www.jiqizhixin.com/rss",
      score: 75,
    },
    {
      name: "AIhot",
      url: "https://aihot.virxact.com/",
      apiUrl: "https://aihot.virxact.com/api/public/items?mode=all&take=30",
      score: 80,
      renderer: "json",
      headers: { "User-Agent": "HotspotExtension/1.0", Accept: "application/json" },
      parseJson: (data: any): RawItem[] => {
        // AIhot API 响应: { items: [{ id, title, url, source, publishedAt, summary }] }
        return (data.items || []).map((item: any) => ({
          title: item.title,
          url: item.url,
          summary: item.summary,
          published_at: item.publishedAt,
        }));
      },
    },
  ];
}
```

#### SecurityCollector — 5 源

```typescript
// 全走 RSS, 是最稳定的分类
export class SecurityCollector extends BaseCollector {
  readonly name = "security";
  readonly category = "security";
  readonly maxItems = 60;
  readonly sources: SourceConfig[] = [
    { name: "TheHackerNews", url: "https://thehackernews.com/",
      rssUrl: "https://feeds.feedburner.com/TheHackersNews", score: 82 },
    { name: "安全客", url: "https://www.anquanke.com/",
      rssUrl: "https://api.anquanke.com/data/v1/rss", score: 75 },
    { name: "FreeBuf", url: "https://www.freebuf.com/",
      rssUrl: "https://www.freebuf.com/feed", score: 75 },
    { name: "嘶吼", url: "https://www.4hou.com/",
      rssUrl: "https://www.4hou.com/feed", score: 70 },
    { name: "PortSwigger", url: "https://portswigger.net/",
      rssUrl: "https://portswigger.net/feed", score: 72 },
  ];
}
```

#### FinanceCollector — 4 源

```typescript
export class FinanceCollector extends BaseCollector {
  readonly name = "finance";
  readonly category = "finance";
  readonly maxItems = 40;
  readonly sources: SourceConfig[] = [
    { name: "新浪财经", url: "https://finance.sina.com.cn/",
      rssUrl: "https://feed.mix.sina.com.cn/feed/scroll/feed/49/finance/json", score: 75 },
    { name: "东方财富", url: "https://www.eastmoney.com/",
      apiUrl: "https://push2.eastmoney.com/api/qt/ulist.np/get",
      score: 75, renderer: "json",
      parseJson: (d: any) => parseEastMoney(d) },
    // 财联社与金十需要特殊处理 — 见 3.4
  ];
}
```

#### BidCollector — 30+ 源

原始项目有 30+ 招标源，插件化策略：
- **主源**: 中国采购与招标网 (`chinabidding.com.cn`)、采招网 (`bidcenter.com.cn`) — DOMParser
- **RSS 替代**: 部分聚合站有 RSS 输出
- **关键词过滤**: 保留网络安全/AI安全相关招标（复用原始 `SECURITY_KEYWORDS` 体系）

#### GitHubCollector — 3 层降级

```typescript
export class GitHubCollector extends BaseCollector {
  readonly name = "github";
  readonly category = "github";
  readonly maxItems = 30;
  readonly sources: SourceConfig[] = [
    {
      name: "GitHub API",
      url: "https://api.github.com",
      apiUrl: "https://api.github.com/search/repositories?q=created:>{date}&sort=stars&order=desc&per_page=30",
      score: 85,
      renderer: "json",
      headers: { Accept: "application/vnd.github.v3+json" },
      parseJson: (data: any) => parseGitHubApi(data),
    },
    // ★ 降级层: GitHub Trending HTML
    {
      name: "GitHub Trending",
      url: "https://github.com/trending",
      score: 80,
      renderer: "html",
    },
  ];
}
```

#### TechCollector — 1 源

```typescript
export class TechCollector extends BaseCollector {
  readonly name = "tech";
  readonly category = "tech";
  readonly maxItems = 120;
  readonly sources: SourceConfig[] = [
    { name: "IT之家", url: "https://www.ithome.com/list/",
      rssUrl: "https://www.ithome.com/rss/", score: 80 },
  ];
}
```

### 3.4 特殊源处理方案

以下源在原始项目中需要 crawl4ai（Playwright JS 渲染），插件中的替代方案：

| 原始源 | 问题 | 插件方案 |
|--------|------|---------|
| **量子位** (qbitai.com) | 原标注 crawl4ai | 站点实际已有 SSR + RSS `qbitai.com/feed` |
| **36氪AI** (36kr.com) | 原标注 crawl4ai | SSR 可用 + RSS `36kr.com/feed` |
| **酷安** (coolapk.com) | 原标注 crawl4ai | 使用酷安开放 API |
| **GitHub Trending** | 需要 JS 渲染 | 3 层降级：API (Token) → 第三方 API → HTML |
| **中国政府采购网** | 反爬严谨 | 改用 `chinabidding.com.cn`、`bidcenter.com.cn` 等 |
| **财联社** | HTML+JS 混合 | DOMParser 解析 SSR 结构 |
| **金十数据** | JS var 赋值 | 正则提取 flash_newest.js |

### 3.5 采集调度

```typescript
// src/background/scheduler.ts

const COLLECT_INTERVAL = 5;     // 5 分钟增量采集
const FULL_COLLECT_INTERVAL = 60; // 1 小时全量采集
const TREND_INTERVAL = 60;      // 1 小时趋势重算
const CLEANUP_INTERVAL = 1440;  // 24 小时清理

// 安装时初始化
chrome.runtime.onInstalled.addListener(async () => {
  await initIndexedDB();          // 创建数据库 schema
  await fullCollect();            // 立即全量采集
  chrome.action.setBadgeBackgroundColor({ color: "#00c96a" });

  chrome.alarms.create("collect", { periodInMinutes: COLLECT_INTERVAL });
  chrome.alarms.create("full-collect", { periodInMinutes: FULL_COLLECT_INTERVAL });
  chrome.alarms.create("compute-trends", { periodInMinutes: TREND_INTERVAL });
  chrome.alarms.create("cleanup", { periodInMinutes: CLEANUP_INTERVAL });
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  switch (alarm.name) {
    case "collect":     await incrementalCollect(); break;
    case "full-collect": await fullCollect(); break;
    case "compute-trends": await computeTrends(); break;
    case "cleanup":     await cleanupOldData(30); break; // 保留 30 天
  }
});
```

---

## 四、质量门禁简约版

从原始 9 级管道精简为 5 级，去掉需要外网验证的 `FinalUrlGate` 和 `URLValidityGate`：

```typescript
// src/background/quality/pipeline.ts

export interface QualityContext {
  existingUrls: Set<string>;
  existingTitles: string[];
  mode: "loose" | "strict";  // loose=打标仍入库, strict=拒绝
}

export async function runQualityPipeline(
  items: RawItem[],
  context: QualityContext
): Promise<HotspotItem[]> {
  const valid: HotspotItem[] = [];

  for (const item of items) {
    // 1. SchemaGate — 字段完整性
    if (!item.title || !item.url || !item.published_at) continue;
    if (item.title.length < 8 || item.title.length > 500) continue;

    // 2. RecencyGate — 时效校验 (早于本周一拒收)
    const weekStart = getCurrentWeekStart(); // Asia/Shanghai 周一 00:00
    const pubDate = new Date(item.published_at);
    if (isNaN(pubDate.getTime()) || pubDate < weekStart) continue;

    // 3. CategoryMatchGate — 关键词匹配
    if (!matchCategory(item.title, item.category)) continue;

    // 4. DuplicateGate — 同 URL 去重
    const urlKey = normalizeUrl(item.url);
    if (context.existingUrls.has(urlKey)) continue;

    // 5. SourceReputationGate — 来源可信度评分
    const reputationScore = getSourceReputation(item.source);

    valid.push({
      id: generateId(item),
      title: item.title.slice(0, 500),
      summary: (item.summary || "").slice(0, 500) || null,
      source: item.source,
      url: item.url,
      category: item.category as any,
      published_at: pubDate.toISOString(),
      fetched_at: new Date().toISOString(),
      ingested_at: new Date().toISOString(),
      score: reputationScore,
      quality_score: reputationScore,
      quality_flags: [],
      is_fallback: false,
      bid_status: extractBidStatus(item.title),
    });
  }

  return valid;
}
```

---

## 五、存储层设计

### 5.1 IndexedDB Schema

使用 `idb` 库封装 IndexedDB：

```typescript
// src/background/indexed-db.ts
import { openDB, DBSchema, IDBPDB } from "idb";

interface HotspotDB extends DBSchema {
  hotspots: {
    key: string;          // id (组合: "{collector}_{source}_{index}")
    value: HotspotItem;
    indexes: {
      "by-category": string;     // category
      "by-ingested": string;     // ingested_at (排序)
      "by-category-ingested": [string, string]; // [category, ingested_at]
      "by-source": string;       // source
    };
  };
  favorites: {
    key: number;          // autoIncrement id
    value: FavoriteItem;
    indexes: {
      "by-hotspot-id": string;   // hotspot_id
      "by-category": string;     // category
      "by-favorited-at": string; // favorited_at
    };
  };
  todos: {
    key: number;
    value: TodoItem;
    indexes: {
      "by-status": string;
      "by-urgency": number;
    };
  };
  trends: {
    key: string;          // "{category}_{hour}" composite
    value: TrendPoint;
    indexes: {
      "by-category": string;
    };
  };
  meta: {
    key: string;          // key name
    value: any;           // JSON value
  };
}

export async function initDB(): Promise<IDBPDB<HotspotDB>> {
  return openDB<HotspotDB>("hotspot-extension", 1, {
    upgrade(db, oldVersion, newVersion) {
      if (oldVersion < 1) {
        // hotspots 表
        const hs = db.createObjectStore("hotspots", { keyPath: "id" });
        hs.createIndex("by-category", "category");
        hs.createIndex("by-ingested", "ingested_at");
        hs.createIndex("by-category-ingested", ["category", "ingested_at"]);
        hs.createIndex("by-source", "source");

        // favorites 表
        const fav = db.createObjectStore("favorites", {
          keyPath: "id",
          autoIncrement: true,
        });
        fav.createIndex("by-hotspot-id", "hotspot_id", { unique: true });
        fav.createIndex("by-category", "category");
        fav.createIndex("by-favorited-at", "favorited_at");

        // todos 表
        const todo = db.createObjectStore("todos", {
          keyPath: "id",
          autoIncrement: true,
        });
        todo.createIndex("by-status", "status");
        todo.createIndex("by-urgency", "urgent");

        // trends 表
        const tr = db.createObjectStore("trends", { keyPath: "id" });
        tr.createIndex("by-category", "category");

        // meta 表
        db.createObjectStore("meta");
      }
    },
  });
}
```

### 5.2 关键查询

```typescript
// 列表查询 (cursor-based pagination, 替代 SQLite 的 cursor 分页)

async function queryHotspots(params: {
  category?: string;
  timeRange: "24h" | "3d" | "7d" | "30d";
  keyword?: string;
  cursor?: string | null;
  limit?: number;
}): Promise<{ items: HotspotItem[]; nextCursor: string | null; total: number }> {
  const db = await getDB();
  const timeStart = getTimeRangeStart(params.timeRange);

  let indexName: string;
  let range: IDBKeyRange;

  if (params.category && params.category !== "all") {
    indexName = "by-category-ingested";
    range = IDBKeyRange.bound(
      [params.category, timeStart.toISOString()],
      [params.category, "\uffff"],
    );
  } else {
    indexName = "by-ingested";
    range = IDBKeyRange.lowerBound(timeStart.toISOString());
  }

  const limit = params.limit || 100;
  const items: HotspotItem[] = [];
  let cursor = await db.transaction("hotspots")
    .store.index(indexName)
    .openCursor(range, "prev");  // DESC

  // 如果有 cursor 参数, 跳到指定位置
  if (params.cursor) {
    // cursor 格式: base64({id, ingested_at})
    const { id, ts } = decodeCursor(params.cursor);
    while (cursor && (cursor.key > ts || (cursor.key === ts && cursor.primaryKey >= id))) {
      cursor = await cursor.continue();
    }
  }

  let count = 0;
  while (cursor && items.length < limit) {
    if (params.keyword) {
      // 关键词过滤 (标题/摘要)
      const matches = cursor.value.title.includes(params.keyword) ||
        (cursor.value.summary || "").includes(params.keyword);
      if (!matches) { cursor = await cursor.continue(); continue; }
    }
    items.push(cursor.value);
    cursor = await cursor.continue();
    count++;
  }

  const nextCursor = items.length === limit
    ? encodeCursor(items[items.length - 1])
    : null;

  return { items, nextCursor, total: count };
}
```

### 5.3 搜索实现

替代原始 FTS5 全文搜索，使用 IndexedDB 游标 + 内存过滤：

- **标题搜索**: `title.includes(keyword)` — 足够快（单次查询 < 50ms）
- **高级搜索**（可选）: 用 `Array.filter` 在内存中组合多条件

---

## 六、数据流设计

### 6.1 安装初始化流

```
用户安装插件
     │
     ▼
chrome.runtime.onInstalled
     │
     ├── initIndexedDB()        → 创建表, 应用 schema 版本
     ├── fullCollect()          → 立即采集7分类全部数据
     ├── chrome.alarms.create() → 注册定时器
     ├── chrome.contextMenus.create() → "添加到热点收藏"
     │
     ▼
Popup 首次打开:
     ├── chrome.runtime.sendMessage("GET_HOTSPOTS", { category: "all" })
     │       │
     │       ▼ SW: 查询 IndexedDB → 返回数据
     │
     └── 渲染 HotspotGrid (骨架屏 → 数据展示)
```

### 6.2 日常使用流

```
用户点击插件图标
     │
     ▼
Popup 打开 (400×600)
     │
     ├── sendMessage("GET_HOTSPOTS", { category: "all", timeRange: "7d" })
     │       │
     │       ▼  SW: 打开 IndexedDB → queryHotspots() → 返回
     │
     ├── 渲染 Header / CategoryNav / SearchBar / HotspotGrid
     │
     ├── 用户切换分类 "security"
     │       │
     │       ▼  sendMessage("GET_HOTSPOTS", { category: "security" })
     │           → 复用 IndexedDB (数据已在本地) → 即时切换
     │
     ├── 用户点击卡片
     │       │
     │       ▼  chrome.tabs.create({ url: item.url })
     │
     ├── 用户收藏
     │       │
     │       ▼  sendMessage("TOGGLE_FAVORITE", { hotspotId })
     │           → SW: IndexedDB.favorites.put()
     │
     └── 用户搜索
             │
             ▼  sendMessage("GET_HOTSPOTS", { keyword: "漏洞" })
                 → SW: IndexedDB 游标 + 内存过滤
```

### 6.3 后台采集流

```
chrome.alarms.onAlarm("collect")   (每 5 分钟)
     │
     ▼
SW 唤醒 → incrementalCollect()
     │
     ├── 读取 meta.lastFetchedAt
     │
     ├── Promise.all([  ← 并行7分类
     │     AICollector.collect()      → 5个源并行
     │     SecurityCollector.collect() → 5个源并行
     │     FinanceCollector.collect()  → 4个源并行
     │     StartupCollector.collect()  → 4个源并行
     │     BidCollector.collect()      → 30+源并行
     │     GitHubCollector.collect()   → 3层降级
     │     TechCollector.collect()     → 1源
     │   ])
     │     │
     │     ▼ (每个 collector 内部)
     │     fetchSource(source) → 三层尝试 (RSS→API→HTML)
     │                              │
     │                              ▼
     │                         Quality Pipeline (5级)
     │                              │
     │                              ▼
     │                         IndexedDB.hotspots.put() ← 立即写库
     │
     ├── 更新 meta.lastFetchedAt
     ├── 更新 chrome.action.badgeText = "新增 N"
     └── SW 进入休眠
```

---

## 七、Service Worker 生命周期管理

这是插件化的**最大技术风险**，必须严格遵守以下规则：

### 7.1 生命周期约束

```
Chromium Service Worker 行为:
  - 空闲约 30 秒 → 终止 (terminate)
  - chrome.alarms 触发 → 重新启动
  - 重新启动 → 全局状态全部丢失
  - fetch 请求会延长存活，但完成后很快被终止
```

### 7.2 应对策略

#### 原则 1：每条结果独立持久化，不在内存累积

```typescript
// ❌ 错误做法
let tempItems: HotspotItem[] = [];  // SW 终止后丢失

// ✅ 正确做法
async function collectAndStore(collector: BaseCollector): Promise<void> {
  for (const source of collector.sources) {
    try {
      const result = await fetchSource(source);
      if (result.items.length === 0) continue;

      // 每个源的解析结果立即写库，不等其他源
      const valid = await runQualityPipeline(result.items, context);
      await bulkPut("hotspots", valid);
    } catch (err) {
      console.warn(`[${source.name}] failed:`, err);
      // 单源失败不影响其他源
    }
  }
}
```

#### 原则 2：每个 collector 独立 try-catch

```typescript
async function fullCollect(): Promise<void> {
  const collectors = [new AICollector(), new SecurityCollector(), ...];

  for (const collector of collectors) {
    try {
      await collectAndStore(collector);  // 内部已逐源持久化
    } catch (err) {
      console.error(`[${collector.name}] catastrophic failure:`, err);
      // 单分类崩溃不阻塞其他
    }
  }
}
```

#### 原则 3：超时保护

```typescript
// 每个源单独超时，避免一个慢源拖死全部分类
async function fetchSourceWithTimeout(
  source: SourceConfig,
  timeoutMs = 15000
): Promise<FetchResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchSource(source, controller.signal);
  } finally {
    clearTimeout(timer);
  }
}
```

#### 原则 4：中断恢复

```typescript
// 每个 collector 完成后记录 checkpoint
interface CollectCheckpoint {
  collector: string;
  source: string;
  completed: boolean;
  startedAt: string;
}

// 下次 SW 启动时检查是否有未完成的采集
chrome.runtime.onStartup.addListener(async () => {
  const incomplete = await db.getAll("checkpoints");
  if (incomplete.some(c => !c.completed)) {
    await resumeIncompleteCollection();
  }
});
```

---

## 八、UI / UX 设计

### 8.1 弹窗布局 (400×600px)

```
┌─────────────────────────────────┐
│ 🔥 热点地图  ✚12  ⚙️  ★  🌙   │  Header (56px)
├─────────────────────────────────┤
│ 全部·AI·安全·金融·创业·标讯·GitHub│  CategoryNav (44px, 横向滚动)
├─────────────────────────────────┤
│ 🔍 搜索关键词... [7天 ▼]       │  SearchBar (48px)
├─────────────────────────────────┤
│ ┌─────────────────────────────┐ │
│ │ [AI] 标题1   来源·5分钟前  ★ │ │
│ │ 摘要内容...                  │ │
│ ├─────────────────────────────┤ │
│ │ [安全] 标题2  来源·1小时前 ★ │ │
│ │ ...                         │ │  HotspotGrid
│ ├─────────────────────────────┤ │  (虚拟滚动, 视口渲染)
│ │ [金融] 标题3                │ │
│ │ ...                         │ │
│ │           ~ 更多 ~          │ │
│ └─────────────────────────────┘ │
├─────────────────────────────────┤
│ AI 23  安全 18  金融 12  ...   │  StatsPanel (36px)
│ 共 156 条    📊 趋势           │
└─────────────────────────────────┘
```

### 8.2 三种尺寸适配

| 模式 | 尺寸 | 触发 | 展示内容 |
|------|------|------|---------|
| **弹窗** | 400×600px | 点击图标 | 热点列表 + 快速操作 |
| **弹窗宽版** | 600×800px | 点击「展开」 | 增加趋势简图 + StatsPanel |
| **Options 全屏** | 浏览器窗口 | 右键→选项 / 点击「完整版」 | 所有功能 + 设置 |

### 8.3 主题系统

直接复用原始 `data-theme` 系统：

```css
[data-theme="dark"] {
  --bg-primary: #0f0f1a;
  --bg-card: #1a1a2e;
  --text-primary: #e0e0e0;
  --text-muted: #888899;
  --border-color: #2a2a3e;
  --color-ai: #00bcd4;
  --color-security: #e85d5d;
  --color-finance: #f0c929;
  --color-startup: #7c6aff;
  --color-bid: #e8891a;
  --color-github: #8b5cf6;
  --color-tech: #ff9800;
}
```

### 8.4 图标 Badge 规则

| 状态 | Badge 文字 | 背景色 |
|------|-----------|--------|
| 无新资讯 | 空 | — |
| 有新资讯 (N < 100) | `N` | `#00c96a` 绿 |
| 新增很多 (N ≥ 100) | `99+` | `#00c96a` 绿 |
| 采集异常 | `!` | `#e85d5d` 红 |

### 8.5 右键菜单

```typescript
// 安装时注册
chrome.contextMenus.create({
  id: "add-to-hotspot-favorites",
  title: "添加到热点收藏",
  contexts: ["link"],
});

// 点击处理
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "add-to-hotspot-favorites" && info.linkUrl) {
    await addExternalFavorite({
      title: info.selectionText || info.linkUrl,
      url: info.linkUrl,
      source: "manual",
    });
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon48.png",
      title: "热点地图",
      message: "已添加到收藏",
    });
  }
});
```

---

## 九、权限与安全

### 9.1 Manifest V3 权限

```json
{
  "manifest_version": 3,
  "name": "热点地图",
  "version": "1.0.0",
  "description": "多域热点聚合 — AI/安全/金融/标讯/GitHub 一站式浏览",
  "action": {
    "default_popup": "popup/index.html",
    "default_icon": { "16": "icons/icon16.png", "48": "icons/icon48.png", "128": "icons/icon128.png" },
    "default_title": "热点地图"
  },
  "background": {
    "service_worker": "background/service-worker.js",
    "type": "module"
  },
  "options_page": "options/index.html",
  "permissions": [
    "storage",
    "alarms",
    "notifications",
    "contextMenus"
  ],
  "host_permissions": [
    "https://hnrss.org/*",
    "https://news.ycombinator.com/*",
    "https://www.qbitai.com/*",
    "https://36kr.com/*",
    "https://aihot.virxact.com/*",
    "https://feeds.feedburner.com/*",
    "https://api.anquanke.com/*",
    "https://www.freebuf.com/*",
    "https://www.4hou.com/*",
    "https://portswigger.net/*",
    "https://www.jiqizhixin.com/*",
    "https://www.huxiu.com/*",
    "https://www.pedaily.cn/*",
    "https://www.itjuzi.com/*",
    "https://www.ithome.com/*",
    "https://api.github.com/*",
    "https://github.com/*",
    "https://feed.mix.sina.com.cn/*",
    "https://*.bidcenter.com.cn/*",
    "https://*.chinabidding.com.cn/*"
  ]
}
```

> **注意**: Chrome Web Store 审核要求说明每个 host_permission 的用途。建议在商店描述中明确列出所有数据源。

### 9.2 密钥安全

原始项目的 LLM API Key 加密存储方案，插件中适配为：

```typescript
// 密钥用 chrome.storage.sync 加密存储 (跨设备同步)
// 加密算法: AES-GCM (Web Crypto API)

async function encryptApiKey(apiKey: string, masterKey: string): Promise<void> {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw", enc.encode(masterKey), "PBKDF2", false, ["deriveKey"]
  );
  const derivedKey = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: enc.encode("hotspot-extension"), iterations: 100000, hash: "SHA-256" },
    keyMaterial, { name: "AES-GCM", length: 256 }, false, ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, derivedKey, enc.encode(apiKey)
  );

  await chrome.storage.sync.set({
    [`secret_${name}`]: {
      iv: Array.from(iv),
      data: Array.from(new Uint8Array(encrypted)),
      model, base_url,
    }
  });
}
```

---

## 十、实施路线图

### Phase 1: 核心可运行 (建议 5-7 天)

| 阶段 | 任务 | 产出 | 预估工时 |
|------|------|------|---------|
| 1.1 | Vite + @crxjs 脚手架搭建, manifest.json 配置 | 可编译空插件 | 0.5 天 |
| 1.2 | IndexedDB schema + CRUD 封装 | `indexed-db.ts` | 0.5 天 |
| 1.3 | BaseCollector 抽象基类 (fetch, fetchRss, parseHtml, buildItems) | `base-collector.ts` | 1 天 |
| 1.4 | AICollector + SecurityCollector + TechCollector (全 RSS) | 3 个采集器 | 1 天 |
| 1.5 | 简约质量门禁 (Schema + Recency + Duplicate + CategoryMatch) | `pipeline.ts` | 0.5 天 |
| 1.6 | 调度器 (chrome.alarms + 全量采集 + 增量采集) | `scheduler.ts` | 0.5 天 |
| 1.7 | Popup UI 核心组件 (Header / CategoryNav / HotspotGrid / HotspotCard) | 弹窗可浏览 | 1 天 |
| 1.8 | Popup ↔ Service Worker 消息通道 | 全链路联通 | 0.5 天 |
| 1.9 | Badge 更新 + SearchBar | 基础体验完整 | 0.5 天 |

**Phase 1 可交付物**: 安装后弹窗展示 AI / Security / Tech 三类热点，支持分类切换、关键词搜索、Badge 计数

### Phase 2: 功能补齐 (建议 5-7 天)

| 阶段 | 任务 | 预估工时 |
|------|------|---------|
| 2.1 | FinanceCollector + StartupCollector + BidCollector + GitHubCollector | 1.5 天 |
| 2.2 | SourceReputationGate 完善 | 0.5 天 |
| 2.3 | 收藏系统 (IndexedDB + UI) | 0.5 天 |
| 2.4 | 待办系统 (IndexedDB + UI) | 0.5 天 |
| 2.5 | TrendChart (小时级重算 + Recharts 图表) | 1 天 |
| 2.6 | FavoritesPanel + TodosPanel 适配弹窗 | 0.5 天 |
| 2.7 | 右键菜单 + 通知推送 | 0.5 天 |
| 2.8 | Options 设置页 (数据源/Sync/密钥) | 1 天 |

**Phase 2 可交付物**: 7 分类完整采集 + 收藏/待办/趋势 + 右键菜单 + 通知

### Phase 3: 全量优化 (建议 3-5 天)

| 阶段 | 任务 | 预估工时 |
|------|------|---------|
| 3.1 | New Tab 可选替换 | 0.5 天 |
| 3.2 | WebDAV 同步 (移植 sync_service) | 1 天 |
| 3.3 | 密钥管理 + Skill 管理 | 1 天 |
| 3.4 | 导出静态 HTML | 0.5 天 |
| 3.5 | 用户引导 (onboarding page) | 0.5 天 |
| 3.6 | 端到端测试 + 性能优化 | 1 天 |

**Phase 3 可交付物**: 功能特征与原始项目对齐的完整浏览器插件

### 总计预估工时

| Phase | 天数 | 核心产出 |
|-------|------|---------|
| Phase 1 | 5-7 天 | 核心浏览体验可用 |
| Phase 2 | 5-7 天 | 完整分类 + 收藏/待办/趋势 |
| Phase 3 | 3-5 天 | 全量功能对齐原始项目 |
| **合计** | **13-19 天** | **完整浏览器插件** |

---

## 十一、文件清单与改动量评估

### 11.1 直接从原始项目复用的文件

| 文件 | 路径 (原始) | 路径 (插件) | 复用率 | 改动说明 |
|------|-----------|-----------|--------|---------|
| `types/index.ts` | `frontend/src/types/` | `src/shared/types.ts` | 100% | 直接复制 |
| `constants.ts` | 从 types.ts 提取 | `src/shared/constants.ts` | 100% | 拆分为独立文件 |
| `index.css` | `frontend/src/` | `src/assets/styles/globals.css` | 100% | 直接复制 |
| `tailwind.config.js` | `frontend/` | `tailwind.config.js` | 100% | 直接复制 |
| `Header.tsx` | `frontend/src/components/` | `src/popup/components/` | 90% | 适配弹窗尺寸 |
| `CategoryNav.tsx` | `frontend/src/components/` | `src/popup/components/` | 90% | 横向滚动适配 |
| `SearchBar.tsx` | `frontend/src/components/` | `src/popup/components/` | 95% | 微调 |
| `HotspotGrid.tsx` | `frontend/src/components/` | `src/popup/components/` | 70% | 分页改为虚拟滚动 |
| `HotspotCard.tsx` | `frontend/src/components/` | `src/popup/components/` | 100% | 直接复制 |
| `StatsPanel.tsx` | `frontend/src/components/` | `src/popup/components/` | 95% | 微调 |
| `TrendChart.tsx` | `frontend/src/components/` | `src/popup/components/` | 95% | 微调 |
| `LoadingSkeleton.tsx` | `frontend/src/components/` | `src/popup/components/` | 100% | 直接复制 |
| `FavoritesPanel.tsx` | `frontend/src/components/` | `src/popup/components/` | 70% | 数据源改为 IndexedDB |
| `SettingsPanel.tsx` | `frontend/src/components/` | `src/popup/components/` | 60% | 改为 chrome.storage |
| `TodosPage.tsx` | `frontend/src/components/` | `src/popup/components/` | 70% | 数据源改为 IndexedDB |
| `package.json` (deps) | `frontend/` | `package.json` | 100% | 相同依赖 |

### 11.2 需要重写的文件

| 文件 | 原始路径 | 插件路径 | 说明 |
|------|---------|---------|------|
| `app.tsx` (路由) | `frontend/src/App.tsx` | `src/popup/App.tsx` | 替换 fetch 为 message 通信 |
| `useHotspotData.ts` | `frontend/src/hooks/` | `src/popup/hooks/useHotspots.ts` | 改为调 IndexedDB |
| `useFavorites.ts` | — (原始在组件内) | `src/popup/hooks/useFavorites.ts` | 新写 |
| `useTodos.ts` | `frontend/src/hooks/useTodos.ts` | `src/popup/hooks/useTodos.ts` | 改为调 IndexedDB |
| `useTrends.ts` | `frontend/src/hooks/` | `src/popup/hooks/useTrends.ts` | 改为调 IndexedDB |

### 11.3 需要移植 (Python → TS) 的文件

| 文件 | 原始路径 (Python) | 插件路径 (TS) | 说明 |
|------|------------------|--------------|------|
| BaseCollector | `backend/collectors/base.py` | `src/background/collectors/base-collector.ts` | 核心移植 |
| AICollector | `backend/collectors/ai_collector.py` | `src/background/collectors/ai-collector.ts` | 全 RSS 化 |
| SecurityCollector | `backend/collectors/security_collector.py` | `src/background/collectors/security-collector.ts` | 全 RSS 化 |
| FinanceCollector | `backend/collectors/finance_collector.py` | `src/background/collectors/finance-collector.ts` | 需特殊处理 |
| StartupCollector | `backend/collectors/startup_collector.py` | `src/background/collectors/startup-collector.ts` | 全 RSS 化 |
| BidCollector | `backend/collectors/bid_collector.py` | `src/background/collectors/bid-collector.ts` | 关键词体系保留 |
| GitHubCollector | `backend/collectors/github_collector.py` | `src/background/collectors/github-collector.ts` | 3 层降级 |
| TechCollector | `backend/collectors/tech_collector.py` | `src/background/collectors/tech-collector.ts` | RSS + HTML |
| QualityPipeline | `backend/quality/pipeline.py` | `src/background/quality/pipeline.ts` | 简化为 5 级 |
| SchemaGate | `backend/quality/schema_gate.py` | `src/background/quality/gates/schema-gate.ts` | 简化 |
| RecencyGate | `backend/quality/recency_gate.py` | `src/background/quality/gates/recency-gate.ts` | 保留 |
| CategoryMatchGate | `backend/quality/category_match_gate.py` | `src/background/quality/gates/category-match-gate.ts` | 保留 |
| DuplicateGate | `backend/quality/duplicate_gate.py` | `src/background/quality/gates/duplicate-gate.ts` | 本地版 |
| SourceReputationGate | `backend/quality/source_reputation_gate.py` | `src/background/quality/gates/source-reputation-gate.ts` | 保留 |
| BidStatus | `backend/collectors/bid_status.py` | 内联到 bid-collector.ts | 标题正则提取 |
| WebDAV Sync | `backend/services/sync_service.py` | `src/background/sync/webdav-client.ts` | 保留 |

### 11.4 需要新写的文件

| 文件 | 路径 | 说明 |
|------|------|------|
| `service-worker.ts` | `src/background/` | SW 入口: alarms / messages / install |
| `scheduler.ts` | `src/background/` | 采集调度逻辑 |
| `indexed-db.ts` | `src/background/` | IndexedDB schema + CRUD |
| `manifest.ts` | `src/` | Manifest V3 配置 |

### 11.5 代码量统计

| 类别 | 文件数 | 代码行数 (估计) | 来源 |
|------|--------|----------------|------|
| 直接复用 (前端) | 16 个 | ~3,500 行 | 原始前端 |
| 重写 (前端适配) | 5 个 | ~1,000 行 | 原始前端改 |
| 移植 (Python → TS) | 14 个 | ~2,500 行 | 原始后端 |
| 新写 | 4 个 | ~500 行 | 全新 |

**总计**: ~7,500 行代码 | **复用率**: ~60%

---

## 十二、风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | **Service Worker 短生命周期** (< 30s 空闲被终止) | 高 | 高 | 每个 collector/source 独立 try-catch，结果即时写 IndexedDB；使用 chrome.alarms 重调度 |
| 2 | **部分源 CORS 限制** (浏览器 fetch 被源站拒绝) | 中 | 中 | RSS 源基本无 CORS 问题；HTML 源使用 `declarativeNetRequest` 修改请求头；必要时用 `offscreen` 文档代理 |
| 3 | **36氪/量子位等 JS 渲染源** | 中 | 中 | 原 crawl4ai 依赖 → 用 RSS 替代 (已验证两站均有 RSS) |
| 4 | **IndexedDB 容量限制** | 低 | 中 | 单条 ~2KB × 10 万条 ≈ 200MB；设置 30 天自动清理 |
| 5 | **Chrome 商店审核** (host_permissions过多) | 中 | 高 | 按需声明域名；在商店描述中说明每个域名的用途 |
| 6 | **标讯反爬** (ccgp.gov.cn) | 中 | 低 | 改用 chinabidding.com.cn 等聚合站作为主源 |
| 7 | **GitHub API 限频** (免费 60 req/h) | 中 | 中 | 3 层降级策略 (API → 第三方 → HTML)，用户可配置 Token |
| 8 | **插件尺寸过大** | 低 | 低 | 预估 < 5MB；无 node_modules 依赖 (Vite 打包已 tree-shaking) |

---

## 十三、附录：数据源采集对照表

### 完整数据源采集方式清单

| # | 数据源 | 分类 | 原始方式 | 插件方式 | 可靠度 | RSS 可用 |
|---|--------|------|---------|---------|--------|---------|
| 1 | HackerNews | AI | HTML | RSS (hnrss.org) | ⭐⭐⭐⭐⭐ | ✅ |
| 2 | 量子位 (qbitai.com) | AI | crawl4ai | RSS (qbitai.com/feed) | ⭐⭐⭐⭐ | ✅ |
| 3 | 36氪AI | AI | crawl4ai | RSS (36kr.com/feed) | ⭐⭐⭐⭐ | ✅ |
| 4 | 机器之心 | AI | HTML | RSS (jiqizhixin.com/rss) | ⭐⭐⭐⭐⭐ | ✅ |
| 5 | AIhot | AI | JSON API | JSON API (直接复用) | ⭐⭐⭐⭐⭐ | — |
| 6 | TheHackerNews | 安全 | HTML | RSS (feedburner) | ⭐⭐⭐⭐⭐ | ✅ |
| 7 | 安全客 | 安全 | HTML | RSS (anquanke.com/rss) | ⭐⭐⭐⭐⭐ | ✅ |
| 8 | FreeBuf | 安全 | HTML | RSS (freebuf.com/feed) | ⭐⭐⭐⭐⭐ | ✅ |
| 9 | 嘶吼 (4hou.com) | 安全 | HTML | RSS (4hou.com/feed) | ⭐⭐⭐⭐⭐ | ✅ |
| 10 | PortSwigger | 安全 | HTML | RSS (portswigger.net/feed) | ⭐⭐⭐⭐⭐ | ✅ |
| 11 | SANS ISC | 安全 | HTML | RSS (isc.sans.edu/dailypodcast.xml) | ⭐⭐⭐⭐⭐ | ✅ |
| 12 | 新浪财经 | 金融 | HTML | RSS feed mix | ⭐⭐⭐⭐ | ✅ |
| 13 | 东方财富 | 金融 | HTML | JSON API | ⭐⭐⭐⭐ | — |
| 14 | 财联社 | 金融 | HTML+JS | DOMParser SSR | ⭐⭐⭐ | — |
| 15 | 金十数据 | 金融 | JS var | 正则提取 | ⭐⭐⭐ | — |
| 16 | 36氪 (创业) | 创业 | HTML | RSS (36kr.com/feed) | ⭐⭐⭐⭐⭐ | ✅ |
| 17 | 虎嗅 | 创业 | HTML | RSS (huxiu.com/rss) | ⭐⭐⭐⭐⭐ | ✅ |
| 18 | 投资界 | 创业 | HTML | DOMParser | ⭐⭐⭐ | — |
| 19 | IT桔子 | 创业 | HTML | DOMParser | ⭐⭐⭐ | — |
| 20 | 中国政府采购网 | 标讯 | crawl4ai | 聚合站替代 | ⭐⭐⭐ | — |
| 21 | 采招网 (bidcenter) | 标讯 | HTML | DOMParser | ⭐⭐⭐⭐ | — |
| 22 | 中国采购与招标网 | 标讯 | HTML | DOMParser | ⭐⭐⭐⭐ | — |
| 23 | GitHub Trending | GitHub | crawl4ai | 3 层降级 (API→HTML) | ⭐⭐⭐⭐ | — |
| 24 | IT之家 | 科技 | HTML | RSS (ithome.com/rss) | ⭐⭐⭐⭐⭐ | ✅ |
| 25 | 奇安信威胁情报 | 安全 | HTML | RSS (ti.qianxin.com/feed) | ⭐⭐⭐⭐⭐ | ✅ |
| 26 | 稀土掘金 | 科技 | HTML | RSS (juejin.cn/rss) | ⭐⭐⭐⭐⭐ | ✅ |

> **统计**: 26 个源中，16 个 (62%) 有稳定的 RSS/API，7 个 (27%) 可用 DOMParser，3 个 (11%) 需要特殊处理。

---

## 总结

| 维度 | 结论 |
|------|------|
| **可行性** | ✅ 完全可行。62% 数据源有 RSS/API，不需 JS 渲染 |
| **最大挑战** | Service Worker 生命周期管理 (SW ≤30s 被终止) |
| **核心策略** | 每条数据即时写 IndexedDB，不依赖内存状态 |
| **推荐起步** | Phase 1 先做 AI + Security + Tech (全 RSS)，快速验证端到端 |
| **预期工时** | 13-19 人日 (单人全栈) |
| **代码复用** | ~60% (前端组件 90% 复用，后端采集逻辑 60% 移植) |
| **最终产出** | Chrome 商店可发布的完整浏览器插件 |
