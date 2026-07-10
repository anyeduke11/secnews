# 热点地图 · 改进计划 v1.3.0

> 文档类型：版本改进计划
> 关联：[ARCHITECTURE.md](../ARCHITECTURE.md) · [SPEC.md](./SPEC.md) · [TASKS.md](./TASKS.md)
> 版本：2026-07-10
> 基线版本：v1.2.0
> 目标版本：v1.3.0
> 定位：IT人员专属工作站 — 多领域热点聚合 + 待办管理 + 周报洞察 + 跨端同步

---

## 一、改进背景与目标

### 1.1 当前版本 (v1.2.0) 现状

v1.2.0 已实现 7 领域 30+ 信源采集、10 层质量门禁、收藏/待办/密钥管理/WebDAV 同步等核心功能，但在以下维度存在明确短板：

| # | 局限 | 影响 |
|---|------|------|
| 1 | 采集器 HTML 正则解析强耦合站点 DOM | 站点改版即失效，修复成本高 |
| 2 | 前端无路由，状态机式视图切换 | URL 不可直达，无前进后退 |
| 3 | 前端零测试 | 改动无回归保障 |
| 4 | 同步冲突仅 last-write-wins，无用户感知 | 数据静默覆盖，不可追溯 |
| 5 | 坚果云配置体验不佳 | 需手动填多个字段 |
| 6 | 配置密钥重启即丢失 | 每次需重新 unlock |
| 7 | 无周报/洞察功能 | 缺少数据化分析和预测能力 |
| 8 | 无实时推送 | 采集完成后需等轮询刷新 |
| 9 | ~~无移动端适配~~ | 已取消，后续独立规划 |
| 10 | 标讯无地区筛选 | 无法按地域聚焦 |

### 1.2 v1.3.0 目标

| 维度 | 目标 |
|------|------|
| 采集稳定性 | 单源改版修复时间从 2h 降至 15min，RSS 优先覆盖率 > 80% |
| 前端工程化 | URL 路由 + Vitest 测试框架 + ≥15 个测试用例 |
| 同步体验 | 坚果云一键配置 + 冲突可视化裁决 + 增量同步 |
| 数据洞察 | 周报自动生成 + AI 洞察（可选）+ 趋势预测 |
| 配置安全 | master_key OS keychain 持久化 + 有效期前端提示 |
| 实时性 | SSE 推送 + 轮询降级 |
| 移动端 | ~~Web 响应式适配 + 小程序设计方案~~ | 已取消 |
| 标讯增强 | 地区筛选 |

### 1.3 不变的原则

延续 ARCHITECTURE.md v3.0 的设计原则：

- **本地优先**：SQLite 仍是唯一主存储
- **简单胜过复杂**：不引入 Redis/PostgreSQL/Celery/Docker
- **单人使用**：不考虑多用户并发，但需处理跨端同步冲突
- **真实优先**：宁可显示"暂无可用资讯"，不用合成数据

---

## 二、改进项总览

| Phase | 名称 | 优先级 | 依赖 | 工期 | 状态 |
|-------|------|--------|------|------|------|
| P1 | 采集器稳定性重构 | P0 | 无 | 5d | ⬜ |
| P2 | 前端路由 + 前端测试 | P0 | 无 | 3d | ⬜ |
| P3 | 同步机制完善（坚果云） | P1 | 无 | 3d | ⬜ |
| P4 | 周报功能 | P1 | P1 | 5d | ⬜ |
| P5 | 配置保密增强 | P1 | 无 | 1d | ⬜ |
| P6 | 实时推送 SSE | P2 | P2 | 2d | ⬜ |
| P7 | ~~移动端适配~~ | — | — | — | ⚪ 已取消 |
| P8 | 标讯地区筛选 | P2 | P1 | 1d | ⬜ |
| **合计** | | | | **20d** | |

---

## 三、Phase 1：采集器稳定性重构（5d）

### 3.1 问题分析

当前采集器脆弱性根因：

| 问题 | 位置 | 影响 |
|------|------|------|
| `_parse_html` 用正则匹配 `<a href="..." title="...">` | `base.py:402-638` | 属性顺序变化即失效 |
| 特定解析器硬编码 DOM 结构 | 各 collector | 站点改版即断裂 |
| RSS 覆盖率低 | 仅小互AI/部分安全站有 `rss_url` | 大量源走脆弱的 HTML 解析 |
| crawl4ai 重量级依赖 | 需 Playwright+Chromium | 未安装时降级到 aiohttp 基本抓不到 |
| 解析逻辑与采集逻辑混合 | 单文件 800+ 行 | 难以独立维护和测试 |

### 3.2 改进策略：三层解析架构

```
优先级降级链：RSS/Atom → JSON API → DOM Parser (lxml) → 正则 fallback → crawl4ai
```

### 3.3 任务分解

#### T-1-01：引入 lxml 替换正则解析（2d）

**改动文件**：`backend/collectors/base.py`

| 步骤 | 改动 | DoD |
|------|------|-----|
| 1 | `requirements.txt` 新增 `lxml>=5.0` | 依赖安装成功 |
| 2 | `base.py` 新增 `from lxml import html as lxml_html` | import 无报错 |
| 3 | 重写 `_parse_html` 默认实现：`lxml_html.fromstring()` → CSS Selector 查询 | 正则不再作为主解析路径 |
| 4 | 保留正则作为 lxml 解析异常时的 fallback | fallback 路径有测试覆盖 |
| 5 | 更新 `backend/tests/test_base_collector.py` | 新旧测试全部通过 |

**关键约束**：`_parse_html` 签名和返回类型 `tuple[list[HotspotItem], SourceResult]` 不变。

**lxml 解析策略**：

```python
def _parse_html(self, html: str, source: dict) -> tuple[list[HotspotItem], SourceResult]:
    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        # fallback 到正则
        return self._parse_html_regex(html, source)

    # CSS Selector 优先级链
    selectors = [
        'h1.entry-title a', 'h2.entry-title a',   # WordPress
        'a[rel="bookmark"]',                         # 通用 bookmark
        '.post-title a', '.article-title a',         # 常见 class
        'h2 a', 'h3 a',                              # 标题内链接
    ]
    for sel in selectors:
        links = tree.cssselect(sel)
        if links:
            return self._extract_from_links(links, source)

    # 最终 fallback
    return self._parse_html_regex(html, source)
```

#### T-1-02：RSS 优先策略补全（1d）

**改动文件**：各 collector 的 `SOURCES` 配置

`fetch_source` 已有 RSS 路由优先逻辑（`rss_url` 存在 → `_fetch_rss`），只需补全各源的 RSS URL。

| Collector | 需补全 RSS 的源 | 预期 RSS URL |
|-----------|----------------|-------------|
| AICollector | 量子位 | `https://www.jiqizhixin.com/rss` |
| AICollector | 机器之心 | `https://www.jiqizhixin.com/rss` |
| AICollector | 36氪AI | `https://36kr.com/feed` |
| SecurityCollector | 安全客 | `https://api.anquanke.com/data/v1/rss` |
| SecurityCollector | FreeBuf | `https://www.freebuf.com/feed` |
| SecurityCollector | 嘶吼 | `https://www.4hou.com/feed` |
| FinanceCollector | 华尔街见闻 | `https://wallstreetcn.com/rss` |
| StartupCollector | 36氪 | `https://36kr.com/feed` |
| StartupCollector | 虎嗅 | `https://www.huxiu.com/rss/0.xml` |
| TechCollector | IT之家 | `https://www.ithome.com/rss/` |

**DoD**：7 个 collector 中至少 5 个的核心源有 `rss_url` 配置。

#### T-1-03：解析器版本化（1d）

**新增目录**：`backend/parsers/`

```
backend/parsers/
├── __init__.py
├── base_parser.py          # BaseSourceParser(ABC)
├── aihot_parser.py         # AIhot JSON API
├── jin10_parser.py         # 金十数据 JS 变量
├── clsd_parser.py          # 财联社电报
├── 36kr_parser.py          # 36氪列表页
├── freebuf_parser.py       # FreeBuf
└── itjuzi_parser.py        # IT桔子
```

```python
class BaseSourceParser(ABC):
    source_id: str
    version: str = "1.0.0"

    @abstractmethod
    def parse(self, content: str, url: str, content_type: str = "html") -> list[RawItem]: ...

    def validate(self, items: list[RawItem]) -> list[RawItem]:
        return [it for it in items if len(it.title) >= 8 and it.url]
```

**改动**：`BaseCollector.fetch_source` 中 `_parse_html`/`_parse_json` 调用改为查找 `source_id` 对应的 parser 实例。无对应 parser 时降级到默认 lxml 解析。

**DoD**：至少 3 个源有独立 parser 文件，可独立测试。

#### T-1-04：采集健康度监控（1d）

**改动文件**：`backend/scheduler/jobs.py` + `backend/api/sources.py` + `frontend/src/components/Header.tsx`

| 步骤 | 改动 | DoD |
|------|------|-----|
| 1 | `collect_all_job` 末尾新增健康度检查：连续失败 ≥3 次的源写入 `source_reputation.alert=True` | alert 字段可查询 |
| 2 | `GET /api/sources/alerts` 返回告警源列表 | API 返回正确 |
| 3 | Header 新增采集状态指示器：🟢全成功 / 🟡部分失败 / 🔴全失败 | hover 显示失败源名称 |

### 3.4 验收标准

- [ ] 所有 7 个 collector 的核心源均有 RSS 或 JSON API 优先路径
- [ ] `_parse_html` 使用 lxml CSS Selector，正则仅作 fallback
- [ ] `backend/parsers/` 目录至少 3 个独立 parser
- [ ] 采集失败时 Header 有视觉反馈
- [ ] `pytest backend/tests/` 全部通过
- [ ] 新增 `backend/tests/test_parsers.py` 覆盖 parser 逻辑

---

## 四、Phase 2：前端路由 + 前端测试（3d）

### 4.1 前端路由迁移（1.5d）

#### T-2-01：安装 react-router-dom

```bash
cd frontend && npm install react-router-dom
```

#### T-2-02：App.tsx 路由重构

**当前** (`frontend/src/App.tsx`)：
```tsx
const [view, setView] = useState<AppView>('home');
{view === 'todos' ? <TodosPage /> : ...}
```

**目标**：
```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/todos" element={<TodosPage />} />
    <Route path="/history" element={<HistoryPage />} />
    <Route path="/skills" element={<SkillsPage />} />
    <Route path="/secrets" element={<SecretsPage />} />
    <Route path="/sync" element={<SyncPage />} />
    <Route path="/weekly-report" element={<WeeklyReportPage />} />
    <Route path="/category/:cat" element={<HomePage />} />
  </Routes>
</BrowserRouter>
```

**迁移步骤**：

| 步骤 | 改动 | 文件 |
|------|------|------|
| 1 | `App.tsx` 用 `<BrowserRouter><Routes>` 包裹 | `App.tsx` |
| 2 | 6 个视图映射为独立路由 | `App.tsx` |
| 3 | `Header.tsx` 的 `view` + `onSetView` 替换为 `useLocation()` + `useNavigate()` | `Header.tsx` |
| 4 | 各子组件中的 `onSetView` 调用替换为 `navigate()` | 各组件 |
| 5 | 删除 `AppView` 类型定义 | `App.tsx` |

**Vite 配置无需改动**，`@vitejs/plugin-react` 自动处理 SPA historyApiFallback。

#### T-2-03：Header 导航改造

| 改动 | 说明 |
|------|------|
| `view` prop → `useLocation()` | 判断当前活跃路由 |
| `onSetView()` → `useNavigate()` | 导航切换 |
| `<Link>` 或 `navigate()` | 替代所有 `setView` 调用 |
| 浏览器前进/后退 | 自动支持 |

### 4.2 前端测试体系（1.5d）

#### T-2-04：测试框架搭建

```bash
cd frontend && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @testing-library/user-event
```

`vite.config.ts` 新增：
```ts
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test/setup.ts',
}
```

**新增文件**：`frontend/src/test/setup.ts`
```ts
import '@testing-library/jest-dom';
import { vi } from 'vitest';

const mockFetch = vi.fn();
global.fetch = mockFetch;

export { mockFetch };
```

#### T-2-05：测试用例编写

| 优先级 | 测试目标 | 文件 | 用例数 |
|--------|----------|------|--------|
| P0 | 工具函数 | `types/index.test.ts` | 6 |
| P0 | 核心 Hook | `hooks/useHotspotData.test.ts` | 5 |
| P1 | 组件渲染 | `components/HotspotCard.test.tsx` | 4 |
| P1 | 组件渲染 | `components/Header.test.tsx` | 3 |
| P2 | 路由集成 | `App.test.tsx` | 3 |

**用例明细**：

`types/index.test.ts`：
- `getCategoryColor('ai')` 返回正确色值
- `formatRelativeTime()` 各时间区间格式化
- `getQualityColor()` 各分值段颜色
- `getBidStatusColor()` 各状态颜色
- `getCategoryLabel()` 中文标签映射
- 边界值：未知分类、负数分值

`hooks/useHotspotData.test.ts`：
- 初始加载返回数据
- 切换 category 清空缓存重置 page
- 分页 fetchPage 正确传递 cursor
- loading 状态正确切换
- error 状态正确设置

`components/HotspotCard.test.tsx`：
- 渲染分类色条
- 渲染收藏按钮
- 质量分显示
- 标讯状态 badge

`components/Header.test.tsx`：
- 导航高亮当前路由
- 计数徽标显示
- 主题切换按钮

`App.test.tsx`：
- 默认路由渲染首页
- `/todos` 渲染待办页
- 未知路由重定向首页

#### T-2-06：CI 集成

`package.json` scripts 新增：
```json
"test": "vitest",
"test:run": "vitest run",
"test:coverage": "vitest run --coverage"
```

### 4.3 验收标准

- [ ] `npm run test:run` 全部通过
- [ ] 6 个视图均有 URL 路由，刷新不丢失视图
- [ ] 浏览器前进/后退正常工作
- [ ] `/category/ai` 可直达 AI 分类页
- [ ] 至少 15 个前端测试用例通过
- [ ] `npm run build` 无错误

---

## 五、Phase 3：同步机制完善（3d）

### 5.1 坚果云一键配置（0.5d）

#### T-3-01：SyncPage 快速配置按钮

**改动文件**：`frontend/src/components/SyncPage.tsx`

| 步骤 | 改动 | DoD |
|------|------|-----|
| 1 | 新增"坚果云快速配置"按钮 | 按钮可见 |
| 2 | 点击后预填 `https://dav.jianguoyun.com/dav` | URL 自动填充 |
| 3 | 仅需用户输入：邮箱/用户名 + 应用专用密码 | 2 个字段即可提交 |
| 4 | 提交后自动 `PROPFIND` 验证连通性 | 成功/失败有反馈 |

### 5.2 同步频率可配置（0.5d）

#### T-3-02：sync_configs 新增 frequency 字段

**改动文件**：`backend/repository/sync_configs_repo.py` + `backend/scheduler/scheduler.py`

**新增迁移**：`019_sync_frequency.sql`
```sql
ALTER TABLE sync_configs ADD COLUMN sync_frequency TEXT DEFAULT 'weekly';
-- 值: manual / daily / weekly / after_collect
```

| 频率 | 触发方式 |
|------|----------|
| `manual` | 仅手动触发 |
| `daily` | 每日 10:30 Asia/Shanghai |
| `weekly` | 每周一 10:30 Asia/Shanghai（当前默认） |
| `after_collect` | 采集完成后自动增量同步 |

**改动**：`scheduler.py` 的 sync job 根据 frequency 动态调整 trigger。

### 5.3 冲突可视化与裁决（1d）

#### T-3-03：冲突查询 API

**改动文件**：`backend/api/sync.py`

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/sync/conflicts` | 返回未解决冲突列表（base/local/remote 三方值） |
| POST | `/api/sync/conflicts/resolve` | 提交裁决 `{record_type, record_key, choice: "local"|"remote"}` |

**冲突数据结构**：
```json
{
  "conflicts": [
    {
      "record_type": "todos",
      "record_key": "hotspot::ai_hn_12345",
      "base": {"title": "旧标题", "status": "pending"},
      "local": {"title": "本地修改", "status": "doing"},
      "remote": {"title": "远端修改", "status": "done"},
      "local_updated_at": "2026-07-09T10:00:00Z",
      "remote_updated_at": "2026-07-09T11:00:00Z"
    }
  ],
  "total": 1
}
```

#### T-3-04：冲突裁决前端面板

**改动文件**：`frontend/src/components/SyncPage.tsx`

```
┌─────────────────────────────────────────┐
│  同步冲突 (2 项待解决)                      │
├─────────────────────────────────────────┤
│  待办: "修复安全漏洞"                       │
│  本地: status=doing, deadline=7/12       │
│  远程: status=pending, deadline=7/15     │
│  [保留本地]  [保留远程]                     │
├─────────────────────────────────────────┤
│  自定义源: "安全客RSS"                      │
│  本地: url=https://a.example.com/feed    │
│  远程: url=https://b.example.com/feed    │
│  [保留本地]  [保留远程]                     │
└─────────────────────────────────────────┘
```

### 5.4 同步状态指示（0.5d）

#### T-3-05：Header 同步状态图标

**改动文件**：`frontend/src/components/Header.tsx` + `frontend/src/hooks/useSync.ts`

| 状态 | 图标 | 行为 |
|------|------|------|
| 同步中 | 🔄 旋转动画 | 不可点击 |
| 同步成功 | ✅ 绿色 | 2s 后消失 |
| 同步冲突 | ⚠️ 黄色 | 点击跳转 SyncPage 冲突面板 |
| 同步失败 | ❌ 红色 | hover 显示错误信息 |
| 未配置 | 无图标 | — |

### 5.5 Bundle 增量压缩（0.5d）

#### T-3-06：增量 diff 同步

**改动文件**：`backend/services/sync_service.py`

| 当前 | 目标 |
|------|------|
| 整个 bundle 加密上传 (~50KB) | 仅上传 diff (~5KB) |

**实现**：`build_bundle` 时为每条记录计算 `hash = md5(json.dumps(record, sort_keys=True))`，下次同步时只包含 hash 变更的记录。远端收到后 merge 到完整 bundle。

### 5.6 验收标准

- [ ] 坚果云一键配置：2 个字段即可完成
- [ ] 同步频率可配置：manual/daily/weekly/after_collect
- [ ] 冲突可在前端逐条裁决
- [ ] Header 显示同步状态
- [ ] Bundle 体积减少 80%+
- [ ] `pytest backend/tests/test_sync_api.py` 全部通过

---

## 六、Phase 4：周报功能（5d）

### 6.1 数据层（2d）

#### T-4-01：新增数据库表

**新增迁移**：`016_weekly_reports.sql`

```sql
CREATE TABLE weekly_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start        TEXT NOT NULL,
    week_end          TEXT NOT NULL,
    category_summary  TEXT NOT NULL,
    bid_summary       TEXT,
    trend_weekly      TEXT NOT NULL,
    top_items         TEXT NOT NULL,
    source_health     TEXT,
    favorites_insight TEXT,
    ai_insight        TEXT,
    generated_at      TEXT NOT NULL,
    version           TEXT DEFAULT '1.0',
    UNIQUE(week_start)
);
CREATE INDEX idx_wr_week ON weekly_reports(week_start DESC);
```

#### T-4-02：趋势历史快照表

**问题**：`trend_snapshots` 每次 rebuild 覆盖，无法回溯周级数据。

**新增迁移**：`017_trend_daily_snapshots.sql`

```sql
CREATE TABLE trend_daily_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    category      TEXT NOT NULL,
    count         INTEGER NOT NULL,
    UNIQUE(snapshot_date, category)
);
CREATE INDEX idx_tds_date ON trend_daily_snapshots(snapshot_date DESC);
```

#### T-4-03：新增 Repository

**新增文件**：`backend/repository/weekly_report_repo.py`

```python
class WeeklyReportRepository:
    def save(self, report: dict) -> int: ...
    def get_by_week(self, week_start: str) -> Optional[dict]: ...
    def list_reports(self, limit: int = 12) -> list[dict]: ...
    def get_latest(self) -> Optional[dict]: ...
```

**新增文件**：`backend/repository/trend_daily_repo.py`

```python
class TrendDailyRepository:
    def save_snapshot(self, date: str, data: list[dict]) -> int: ...
    def get_range(self, start: str, end: str) -> list[dict]: ...
```

#### T-4-04：新增 Scheduler Job — 日级快照

**改动文件**：`backend/scheduler/scheduler.py` + `backend/scheduler/jobs.py`

```python
# job 7: 日级趋势快照（每日 00:05 Asia/Shanghai）
self.scheduler.add_job(
    jobs.trend_daily_snapshot_job,
    trigger=CronTrigger(hour=0, minute=5, timezone=SHANGHAI_TZ),
    id="trend_daily_snapshot",
    name="daily trend snapshot",
    replace_existing=True,
)
```

### 6.2 服务层（1.5d）

#### T-4-05：WeeklyReportService

**新增文件**：`backend/services/weekly_report_service.py`

```python
class WeeklyReportService:
    async def generate(self, week_start: str) -> dict:
        """聚合本周数据生成周报"""
        week_end = self._week_end(week_start)
        return {
            "week_start": week_start,
            "week_end": week_end,
            "category_summary": self._aggregate_categories(week_start, week_end),
            "trend_weekly": self._aggregate_trends(week_start, week_end),
            "top_items": self._top_items(week_start, week_end, limit=10),
            "bid_summary": self._aggregate_bids(week_start, week_end),
            "source_health": self._aggregate_source_health(week_start, week_end),
            "favorites_insight": self._aggregate_favorites(week_start, week_end),
            "ai_insight": await self._generate_ai_insight(week_start, week_end),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _aggregate_categories(self, start: str, end: str) -> dict:
        """按分类聚合：总量、Top来源、平均质量分"""
        ...

    def _aggregate_trends(self, start: str, end: str) -> list[dict]:
        """7天日级趋势（从 trend_daily_snapshots）"""
        ...

    def _top_items(self, start: str, end: str, limit: int) -> list[dict]:
        """按 score 排名的 Top N 热点"""
        ...

    def _aggregate_bids(self, start: str, end: str) -> dict:
        """标讯统计：总量/按状态/按地区"""
        ...

    def _aggregate_source_health(self, start: str, end: str) -> dict:
        """来源健康度：成功率/产出量"""
        ...

    def _aggregate_favorites(self, start: str, end: str) -> dict:
        """收藏洞察：本周收藏数/分类分布"""
        ...

    async def _generate_ai_insight(self, start: str, end: str) -> Optional[dict]:
        """调用 LLM 生成周报摘要 + 趋势预测（可选）"""
        if not self.secrets_service.is_unlocked():
            return None
        data = self._prepare_llm_context(start, end)
        prompt = self._build_weekly_prompt(data)
        response = await self._call_llm(prompt)
        return {"summary": response, "model": self.llm_model}
```

**AI Prompt 模板**：
```
你是一位 IT 行业分析师。请基于以下本周数据，生成结构化周报：

## 本周数据概览
{category_summary}
{trend_weekly}
{top_items}
{bid_summary}

## 输出要求
1. 本周总结（200字以内）
2. 三个关键趋势（各50字）
3. 下周预测（100字，基于趋势外推）
4. 建议关注领域（1-3个，附理由）

输出格式：JSON
```

### 6.3 API 层（0.5d）

#### T-4-06：周报 API

**新增文件**：`backend/api/weekly_report.py`

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/weekly-report/latest` | 最近一周报告 |
| GET | `/api/weekly-report?week=2026-W28` | 指定周报告 |
| GET | `/api/weekly-report/list` | 历史周报列表 |
| POST | `/api/weekly-report/generate` | 手动触发生成 |
| POST | `/api/weekly-report/generate-with-ai` | 手动触发含 AI 洞察的生成 |

### 6.4 前端（1d）

#### T-4-07：WeeklyReportPage

**新增文件**：`frontend/src/components/WeeklyReportPage.tsx`

**新增 Hook**：`frontend/src/hooks/useWeeklyReport.ts`

**路由**：`/weekly-report`

**页面布局**：

```
┌──────────────────────────────────────────────────────┐
│  周报 2026-W28                    [← 上一周] [下一周 →]  │
├──────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 本周总量  │ │ 环比变化  │ │ 标讯数量  │ │ 收藏数量  │ │
│  │   1,234  │ │  +12.3%  │ │    89    │ │    15    │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├──────────────────────────────────────────────────────┤
│  7 天趋势 (堆叠面积图 — Recharts)                       │
├──────────────────────────────────────────────────────┤
│  分类占比 (饼图)          │  Top 10 热点 (列表)          │
│  ██ AI 35%               │  1. GPT-5 发布...          │
│  ██ 安全 25%             │  2. CVE-2026-xxxx...       │
│  ██ 金融 20%             │  3. ...                    │
│  ██ 其他 20%             │                             │
├──────────────────────────────────────────────────────┤
│  标讯统计                                               │
│  总量: 89  |  进行中: 23  |  已截止: 66  |  地区分布: ...  │
├──────────────────────────────────────────────────────┤
│  AI 洞察 [生成]                                         │
│  本周 AI 领域持续升温，GPT-5 发布带动相关资讯增长 40%。    │
│  网络安全方面，APT 攻击趋势上升，建议关注零信任方案。       │
│  下周预测：AI Agent 相关资讯将成为热点...                  │
└──────────────────────────────────────────────────────┘
```

#### T-4-08：新增 Scheduler Job — 周报自动生成

**改动文件**：`backend/scheduler/scheduler.py`

```python
# job 8: 周报自动生成（每周一 08:00 Asia/Shanghai）
self.scheduler.add_job(
    jobs.weekly_report_job,
    trigger=CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=SHANGHAI_TZ),
    id="weekly_report",
    name="generate weekly report (Mon 08:00)",
    replace_existing=True,
)
```

### 6.5 预测场景

| 预测类型 | 数据基础 | 方法 | 展示 |
|----------|----------|------|------|
| 热度预测 | 4 周 `trend_daily_snapshots` | 线性外推 + 分类权重 | 下周趋势预览图 |
| 标讯预测 | 8 周 bid 数据 | 周期性模式匹配 | "预计下周 X 地区有 N 条标讯" |
| 领域趋势 | 4 周分类占比变化率 | 变化率排序 | "AI 持续升温 / 金融降温" |

### 6.6 验收标准

- [ ] 每周一 08:00 自动生成周报
- [ ] 前端可查看任意历史周报
- [ ] 周报包含：趋势图、分类占比、Top10、标讯统计、来源健康度
- [ ] AI 洞察可选生成（密钥解锁时可用，未解锁时跳过）
- [ ] `trend_daily_snapshots` 每日自动快照
- [ ] `pytest backend/tests/test_weekly_report.py` 全部通过

---

## 七、Phase 5：配置保密增强（1d）

### 7.1 master_key 持久化（0.5d）

#### T-5-01：OS keychain 持久化

**改动文件**：`backend/services/secrets_service.py`

**实现**：

```python
def _persist_master_key(self, master_key: str) -> None:
    encrypted = self._encrypt_for_storage(master_key)
    try:
        import keyring
        keyring.set_password("hotspot", "master_key", encrypted)
        return
    except Exception:
        pass
    # fallback: 加密后存入 settings 表
    SettingsRepository().set("master_key_encrypted", encrypted)

def _load_master_key(self) -> Optional[str]:
    try:
        import keyring
        encrypted = keyring.get_password("hotspot", "master_key")
        if encrypted:
            return self._decrypt_from_storage(encrypted)
    except Exception:
        pass
    # fallback: 从 settings 表读取
    encrypted = SettingsRepository().get("master_key_encrypted")
    if encrypted:
        return self._decrypt_from_storage(encrypted)
    return None
```

`requirements.txt` 新增 `keyring>=24.0`（可选依赖，`try/except` 降级）。

### 7.2 密钥有效期前端提示（0.5d）

#### T-5-02：Header 密钥倒计时

**改动文件**：`frontend/src/components/Header.tsx` + `frontend/src/hooks/useSecrets.ts`

| 步骤 | 改动 | DoD |
|------|------|-----|
| 1 | `/api/secrets/status` 响应新增 `ttl_remaining_seconds` 字段 | API 返回正确 |
| 2 | `useSecrets` hook 新增 `ttlRemaining` 状态 | hook 暴露字段 |
| 3 | Header 密钥图标旁显示剩余时间 | <5min 时红色闪烁 |
| 4 | 即将过期（<60s）弹出提示 | 用户可感知 |

### 7.3 验收标准

- [ ] macOS 上 master_key 自动持久化到 Keychain
- [ ] 无 keyring 时降级到 settings 表加密存储
- [ ] 进程重启后无需重新 unlock（keychain 模式）
- [ ] Header 显示密钥剩余有效时间

---

## 八、Phase 6：实时推送 SSE（2d）

### 8.1 后端 SSE Endpoint（1d）

#### T-6-01：SSE 事件总线

**新增文件**：`backend/api/events.py`

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()
_event_subscribers: list[asyncio.Queue] = []

async def publish_event(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": data, "ts": ...})
    dead = []
    for q in _event_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _event_subscribers.remove(q)

@router.get("/api/events")
async def sse_events():
    queue = asyncio.Queue(maxsize=100)
    _event_subscribers.append(queue)
    async def stream():
        try:
            while True:
                data = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {data}\n\n"
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            if queue in _event_subscribers:
                _event_subscribers.remove(queue)
    return StreamingResponse(stream(), media_type="text/event-stream")
```

**改动文件**：`backend/services/collection_service.py`

采集完成后调用 `publish_event("collect_done", {"categories": [...], "count": N})`。

#### T-6-02：main.py 注册路由

**改动文件**：`backend/main.py`

```python
from backend.api.events import router as events_router
app.include_router(events_router)
```

### 8.2 前端 EventSource Hook（0.5d）

#### T-6-03：useSSE Hook

**新增文件**：`frontend/src/hooks/useSSE.ts`

```typescript
export function useSSE(onEvent: (type: string, data: any) => void) {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource('/api/events');
      es.onopen = () => setConnected(true);
      es.onmessage = (e) => {
        try {
          const { type, data } = JSON.parse(e.data);
          onEvent(type, data);
        } catch {}
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
      };
    } catch {
      setConnected(false);
    }
    return () => es?.close();
  }, [onEvent]);

  return { connected };
}
```

### 8.3 轮询降级（0.5d）

#### T-6-04：App.tsx 推送/轮询自适应

**改动文件**：`frontend/src/App.tsx`

```typescript
const { connected: sseConnected } = useSSE((type, data) => {
  if (type === 'collect_done') refresh();
});

// SSE 已连接时禁用轮询；断开时恢复轮询
useEffect(() => {
  if (sseConnected) return; // SSE 推送，不需要轮询
  const ms = Math.max(refreshInterval, 1) * 60 * 1000;
  const timer = setInterval(() => refresh(), ms);
  return () => clearInterval(timer);
}, [sseConnected, refreshInterval, refresh]);
```

### 8.4 验收标准

- [ ] 采集完成后前端 1s 内收到推送并自动刷新
- [ ] SSE 断开时自动降级到轮询
- [ ] SSE 重连后恢复推送模式
- [ ] 多标签页不重复刷新（EventSource 各自独立，但 refresh 有防抖）

---

## 九、Phase 7：移动端适配（3d）

### 9.1 Web 端响应式改造（2d）

#### T-7-01：Header 移动端重构（1d）

**改动文件**：`frontend/src/components/Header.tsx`

| 断点 | 布局 |
|------|------|
| ≥768px | 保持现有横排布局 |
| <768px | Logo + 汉堡菜单按钮 + 底部 Tab 导航 |

**底部 Tab 导航**：
```
┌─────────────────────────────────┐
│  首页  │  待办  │  收藏  │  更多  │
└─────────────────────────────────┘
```

"更多"弹出菜单：历史、Skill、密钥、同步、设置、导出。

#### T-7-02：卡片与布局响应式（0.5d）

| 改动 | 文件 | 说明 |
|------|------|------|
| HotspotCard 字号 | `HotspotCard.tsx` | 固定 px → `text-sm`/`text-xs` Tailwind 响应式类 |
| 卡片触摸区域 | `HotspotCard.tsx` | `min-h-[44px]` 确保触摸友好 |
| TrendChart | `TrendChart.tsx` | <640px 简化为折线图或隐藏 |
| SearchBar | `SearchBar.tsx` | <640px 全宽 + 折叠展开 |

#### T-7-03：Tailwind 断点增强（0.5d）

**改动文件**：`frontend/tailwind.config.js`

```js
theme: {
  extend: {
    screens: {
      'xs': '480px',
      // sm/md/lg/xl/2xl 保留默认
    },
  }
}
```

### 9.2 小程序方案设计（1d，仅输出设计文档）

#### T-7-04：小程序设计文档

**输出文件**：`docs/MINI_PROGRAM_DESIGN.md`

| 维度 | 方案 |
|------|------|
| 框架 | Taro 3 (React 语法) |
| 共享层 | `hooks/` + `types/` + API 调用逻辑直接复用 |
| 不可复用 | 所有 Tailwind CSS 需重写为小程序样式 |
| 页面 | 首页(资讯/标讯/收藏 3 Tab) + 待办页 + 设置页 |
| 推送 | 微信订阅消息模板 |
| 离线 | 本地 Storage 缓存最近 100 条 |
| API | 后端不变，小程序 HTTP 直连 `http://<server-ip>:8000/api` |

### 9.3 验收标准

- [ ] <768px 屏幕上 Header 自动切换为汉堡菜单 + 底部 Tab
- [ ] 卡片触摸区域 ≥44px
- [ ] Chrome DevTools 移动端模拟器（iPhone 14 / Pixel 7）测试通过
- [ ] 小程序设计文档完成

---

## 十、Phase 8：标讯地区筛选（1d）

### 10.1 后端改造

#### T-8-01：BidCollector 地区提取

**改动文件**：`backend/collectors/bid_collector.py`

| 步骤 | 改动 | DoD |
|------|------|-----|
| 1 | 解析招标公告中的地区信息（省/市级） | 至少覆盖省级行政区 |
| 2 | 写入 `HotspotItem` 新增字段 `region` | 字段非空率 > 60% |

#### T-8-02：数据库迁移

**新增迁移**：`018_hotspot_region.sql`

```sql
ALTER TABLE hotspots ADD COLUMN region TEXT;
CREATE INDEX idx_hotspot_region ON hotspots(category, region);
```

#### T-8-03：API 扩展

**改动文件**：`backend/api/hotspots.py`

`GET /api/hotspots?category=bid&region=北京` 新增 `region` 查询参数。

### 10.2 前端筛选

#### T-8-04：BidCollector 分类地区筛选

**改动文件**：`frontend/src/components/CategoryNav.tsx` 或 `HotspotGrid.tsx`

Bid 分类下新增地区筛选下拉框，选项从 API 动态获取。

### 10.3 验收标准

- [ ] 标讯卡片显示地区标签
- [ ] 可按地区筛选标讯
- [ ] 至少覆盖省级行政区

---

## 十一、数据库迁移清单

| 迁移文件 | Phase | 内容 |
|----------|-------|------|
| `016_weekly_reports.sql` | P4 | 周报表 |
| `017_trend_daily_snapshots.sql` | P4 | 日级趋势快照表 |
| `018_hotspot_region.sql` | P8 | hotspots 新增 region 字段 |
| `019_sync_frequency.sql` | P3 | sync_configs 新增 sync_frequency 字段 |

---

## 十二、新增文件清单

| 文件 | Phase | 说明 |
|------|-------|------|
| `backend/parsers/__init__.py` | P1 | 解析器包 |
| `backend/parsers/base_parser.py` | P1 | 解析器基类 |
| `backend/parsers/aihot_parser.py` | P1 | AIhot JSON API 解析器 |
| `backend/parsers/jin10_parser.py` | P1 | 金十数据解析器 |
| `backend/parsers/clsd_parser.py` | P1 | 财联社解析器 |
| `backend/api/events.py` | P6 | SSE 事件端点 |
| `backend/api/weekly_report.py` | P4 | 周报 API |
| `backend/repository/weekly_report_repo.py` | P4 | 周报数据访问 |
| `backend/repository/trend_daily_repo.py` | P4 | 日级趋势数据访问 |
| `backend/services/weekly_report_service.py` | P4 | 周报业务逻辑 |
| `frontend/src/hooks/useSSE.ts` | P6 | SSE Hook |
| `frontend/src/hooks/useWeeklyReport.ts` | P4 | 周报 Hook |
| `frontend/src/components/WeeklyReportPage.tsx` | P4 | 周报页面 |
| `frontend/src/test/setup.ts` | P2 | 测试 setup |
| `frontend/src/types/index.test.ts` | P2 | 类型工具测试 |
| `frontend/src/hooks/useHotspotData.test.ts` | P2 | 核心 Hook 测试 |
| `frontend/src/components/HotspotCard.test.tsx` | P2 | 卡片组件测试 |
| `frontend/src/components/Header.test.tsx` | P2 | Header 测试 |
| `frontend/src/App.test.tsx` | P2 | 路由集成测试 |
| `docs/MINI_PROGRAM_DESIGN.md` | P7 | 小程序设计文档 |

---

## 十三、依赖变更清单

| 依赖 | 版本 | Phase | 说明 |
|------|------|-------|------|
| `lxml` | >=5.0 | P1 | HTML DOM 解析替代正则 |
| `keyring` | >=24.0 | P5 | OS keychain 持久化（可选） |
| `react-router-dom` | ^6.x | P2 | 前端路由 |
| `vitest` | ^1.x | P2 | 前端测试框架 |
| `@testing-library/react` | ^14.x | P2 | React 组件测试 |
| `@testing-library/jest-dom` | ^6.x | P2 | DOM 断言扩展 |
| `@testing-library/user-event` | ^14.x | P2 | 用户交互模拟 |
| `jsdom` | ^24.x | P2 | Vitest DOM 环境 |

---

## 十四、实施路线图

```
Week 1-2:  P1 (采集器稳定性) ───────────────────────────── 5d
Week 2-3:  P2 (前端路由+测试) ───────────────────────────── 3d
Week 3-4:  P3 (同步完善) ───────────────────────────────── 3d
Week 4:    P5 (配置保密) ───────────────────────────────── 1d
Week 4-6:  P4 (周报功能) ───────────────────────────────── 5d
Week 6-7:  P6 (SSE推送) ────────────────────────────────── 2d
Week 7-8:  P6 (SSE推送) ────────────────────────────────── 2d
Week 8:    P8 (标讯地区) ───────────────────────────────── 1d
```

**关键依赖链**：
```
P1(采集器) → P8(标讯地区)
P2(前端路由) → P6(SSE) → P7(移动端)
P1(采集器) → P4(周报)
P3(同步) 独立
P5(保密) 独立
```

**可并行组**：
- Week 3-4：P3 + P5 可并行
- Week 5-6：P4 + P6 可并行

---

## 十五、风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | lxml 解析某些站点仍失败 | 中 | 中 | 保留正则 fallback + RSS 优先策略兜底 |
| 2 | react-router 迁移引入状态管理回归 | 低 | 中 | 逐视图迁移，每步 `npm run test:run` 验证 |
| 3 | 周报 AI 洞察 LLM 调用不稳定 | 高 | 低 | AI 洞察标记为可选，失败不影响基础周报生成 |
| 4 | SSE 长连接在代理环境下不稳定 | 中 | 低 | 自动降级到轮询，用户无感知 |
| 5 | 坚果云 WebDAV 流量限制 | 低 | 中 | Bundle 增量压缩 + 频率限制 |
| 6 | 小程序审核被拒 | 中 | 中 | 先出 Web 移动端，小程序作为后续独立迭代 |
| 7 | 迁移文件编号冲突 | 低 | 中 | 严格按 Phase 顺序分配编号，合并时检查 |

---

## 十六、版本发布标准

v1.3.0 发布前必须满足：

1. ✅ 所有 P0/P1 Phase (P1-P5) 验收标准通过
2. ✅ 后端 `pytest --cov` 覆盖率 ≥ 60%
3. ✅ 前端 `npm run test:run` 全部通过
4. ✅ `npm run build` 无错误
5. ✅ 数据库迁移 016-019 全部可执行且幂等
6. ✅ 7 个领域全部有真实链接（不含 fallback）
7. ✅ 坚果云同步端到端测试通过
8. ✅ 周报自动生成 + AI 洞察可选生成
9. ✅ Chrome DevTools 移动端模拟器测试通过

---

## 附录 A：与 v1.2.0 架构变更对照

| 组件 | v1.2.0 | v1.3.0 |
|------|--------|--------|
| HTML 解析 | 正则 | lxml CSS Selector + 正则 fallback |
| RSS 覆盖 | ~20% | >80% |
| 前端路由 | useState 状态机 | react-router-dom |
| 前端测试 | 零 | Vitest + Testing Library |
| 同步冲突 | last-write-wins 静默 | 可视化裁决面板 |
| 同步频率 | 固定每周一 | manual/daily/weekly/after_collect |
| 密钥持久化 | 仅内存 | OS keychain + settings 表 fallback |
| 周报 | 无 | 自动生成 + AI 洞察 |
| 实时推送 | 5min 轮询 | SSE + 轮询降级 |
| 移动端 | 无适配 | 响应式 + 小程序设计 |
| 标讯 | 无地区 | 省级地区筛选 |
| 解析器 | 与 collector 混合 | 独立 `parsers/` 目录版本化 |
| Scheduler Jobs | 6 个 | 8 个（+日级快照 +周报生成） |

## 附录 B：参考文档

- [ARCHITECTURE.md](../ARCHITECTURE.md) — 架构优化方案 v3.0
- [SPEC.md](./SPEC.md) — 功能与接口规范 v3.1
- [TASKS.md](./TASKS.md) — 任务分解 v3.0
- [DESIGN_GUIDE.md](../DESIGN_GUIDE.md) — 设计规范
- [RUNBOOK.md](./RUNBOOK.md) — 运维手册