# 03 — 前端详解

## 1. 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.2 | UI 框架 |
| TypeScript | 5.3 | 类型安全 |
| Vite | 5.x | 构建工具 (端口 8898 strict) |
| Tailwind CSS | 3.4 | 原子化 CSS |
| react-router-dom | 6.23 | 客户端路由 |
| ECharts | 6.1 | 复杂图表 (趋势图) |
| Recharts | 3.9 | 声明式图表 |
| Vitest | 2.x | 单元测试 |
| jsdom | 25.x | DOM 模拟 |

## 2. 路由设计 (`src/App.tsx`)

```
<PageLayout>                        ← 外层容器 (ToastProvider + 布局)
  ├─ "/"                 → HomePage (category=all)
  ├─ "/category/:cat"    → HomePage (指定分类)
  ├─ "/todos"            → TodosPage (lazy)
  ├─ "/history"          → HistoryPage (lazy)
  ├─ "/skills"           → SkillsPage (lazy)
  ├─ "/secrets"          → SecretsPage (lazy)
  ├─ "/sync"             → SyncPage (lazy)
  ├─ "/weekly-report"    → WeeklyReportPage (lazy)
  ├─ "/knowledge"        → KnowledgePage (lazy)
  ├─ "/codegarden"       → CodegardenPage (lazy)
  ├─ "/codegarden/phase2b" → CodegardenPhase2bPage (lazy)
  └─ "/reviews"          → ReviewPage (lazy)
```

- 主页 (`/`) 和分类页 (`/category/:cat`) 是**同步加载**的（核心路径）
- 其余页面全部 **React.lazy + Suspense** 懒加载，减少首屏 bundle
- 无路由库之外的导航方案，直接用 `useNavigate()`

## 3. 组件树

```
App
├─ ThemeContext.Provider                  ← 全局主题 (dark/light)
│  └─ PageLayout                         ← ToastProvider + 外层容器
│     ├─ HomePage (核心页面)
│     │  ├─ Header                       ← 顶部栏 (刷新/主题/设置/收藏/todos)
│     │  ├─ SettingsPanel (lazy)         ← 设置面板 (刷新间隔)
│     │  ├─ FavoritesPanel (lazy)        ← 收藏面板
│     │  ├─ CategoryNav                  ← 分类导航 (8 分类 + 一致性漂移)
│     │  ├─ SearchBar                    ← 搜索 + 时间范围
│     │  ├─ RegionFilter                 ← 标讯地区筛选 (仅 bid)
│     │  ├─ StatsPanel                   ← 统计面板
│     │  ├─ TrendChart                   ← 趋势图 (仅 all)
│     │  ├─ HotspotGrid                  ← 热点卡片网格 (分页)
│     │  │  └─ HotspotCard               ← 单条热点卡片
│     │  └─ Footer                       ← 页脚 (数据源 + export 链接)
│     │
│     ├─ TodosPage (lazy)                ← 待办事项
│     ├─ HistoryPage (lazy)              ← 浏览历史
│     ├─ SkillsPage (lazy)               ← Skill 管理
│     ├─ SecretsPage (lazy)              ← 密钥管理
│     ├─ SyncPage (lazy)                 ← 跨端同步配置
│     ├─ WeeklyReportPage (lazy)         ← 周报
│     ├─ KnowledgePage (lazy)            ← 知识库
│     ├─ CodegardenPage (lazy)           ← CodeGarden Phase 1
│     ├─ CodegardenPhase2bPage (lazy)    ← CodeGarden Phase 2b
│     └─ ReviewPage (lazy)               ← SM-2 复习 (v1.7)
```

### 关键子组件目录

```
src/components/
├── codegarden/          ← CodeGarden 组件 (Phase 1 + 2b)
│   ├── ProjectBoard.tsx, ProjectCard.tsx, ProjectDetail.tsx
│   ├── ServiceMesh.tsx, ServiceTopology.tsx
│   ├── ResourceHub.tsx, DependencyGraph.tsx
│   ├── EventBus.tsx, PlaybookList.tsx
│   └── *.test.tsx       ← 组件测试 (22 个)
├── security/            ← 安全知识图谱组件
│   ├── SecurityGraph.tsx, SecurityTimeline.tsx
│   ├── SecurityEntityDetail.tsx, ComplianceMatrix.tsx
│   └── TermStandardizer.tsx
├── favorites/           ← 收藏面板
├── settings/            ← 设置面板
├── sync/                ← 同步页面
└── shared/              ← 共享组件
    └── Icon.tsx         ← 统一 SVG 图标组件
```

## 4. 状态管理 (无全局状态库)

使用 React 原生状态 + 自定义 Hooks，无 Redux/MobX/Zustand。

### 4.1 全局状态 (ThemeContext)

```typescript
// src/App.tsx
interface ThemeContextValue {
  theme: 'dark' | 'light';
  toggleTheme: () => void;
}
```
- 通过 `localStorage` 持久化主题
- `useTheme()` hook 供所有组件消费

### 4.2 核心 Hook

| Hook | 文件 | 职责 |
|------|------|------|
| `useHotspotData` | `hooks/useHotspotData.ts` | 热点列表数据获取、分页、刷新 |
| `useRefreshInterval` | `hooks/useRefreshInterval.ts` | 自动刷新间隔管理 |
| `useTodos` | `hooks/useTodos.ts` | 待办事项 CRUD |
| `useSSE` | `hooks/useSSE.ts` | SSE 实时推送连接 |
| `useReviews` | `hooks/useReviews.ts` | SM-2 复习 (v1.7) |
| `useAnnotations` | `hooks/useAnnotations.ts` | 笔记 CRUD (v1.7) |
| `useAlerts` | `hooks/useAlerts.ts` | 告警管理 (v1.7) |
| `useSearch` | `hooks/useSearch.ts` | 统一搜索 (v1.7) |
| `useSecurityGraph` | `hooks/useSecurityGraph.ts` | 安全图谱数据 |
| `useSync` | `hooks/useSync.ts` | 同步状态 |

### 4.3 数据流模式

```
HomePage (状态所有者)
  ├─ useHotspotData(category, timeRange, keyword, region)
  │    → { items, total, loading, error, refresh, page, ... }
  │
  ├─ useRefreshInterval()
  │    → { interval, setInterval, refreshFromServer }
  │
  ├─ useTodos()
  │    → { count, items, ... }
  │
  ├─ useSSE({ onEvent })
  │    → { connected }
  │    SSE 连接时禁用轮询，断开时恢复
  │
  └─ 本地状态
       ├─ favoritesCount, favoritedIds (Set<string>)
       ├─ consistencyDrift (ConsistencyDrift[])
       ├─ settingsOpen, favoritesOpen
       └─ manualRefreshing
```

## 5. 类型定义 (`src/types/index.ts`)

```typescript
// 核心类型
interface HotspotItem {
  id: string; title: string; summary?: string;
  source: string; url: string; category: string;
  published_at: string; fetched_at: string; ingested_at?: string;
  bid_status?: string; region?: string;
  score?: number; is_fallback: boolean;
  quality_score?: number; quality_flags?: string[];
}

interface CategoryInfo {
  category: string; count: number; label: string; color: string;
}

interface TrendPoint {
  time: string; count: number; category?: string;
}

interface StatsResponse {
  total: number; category_counts: Record<string, number>;
  latest_ingestion?: { count: number; at: string };
  consistency_check?: { drift: ConsistencyDrift[] };
}

interface ConsistencyDrift {
  category: string; label: string;
  nav_count: number; stats_count: number; diff: number;
}
```

## 6. 构建与测试

```bash
# 开发
npm run dev              # Vite :8898 --strictPort --host 0.0.0.0

# 构建
npm run build            # tsc --noEmit + vite build

# 测试
npm run test:run         # Vitest run (全量)
npx vitest run           # 同上
```

## 7. 主题系统

- CSS 变量驱动：`data-theme="dark"` / `data-theme="light"` 设置在 `<html>` 上
- 颜色变量：`--color-ai`, `--color-security`, `--color-finance`, `--text-muted`, `--bg-hover` 等
- 所有组件通过 CSS 变量引用颜色，不硬编码 hex 值