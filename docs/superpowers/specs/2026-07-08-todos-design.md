# 待办 (Todos) — 设计规格

**状态**: Approved (用户 2026-07-08 三段确认)
**作者**: brainstorming + user
**目标**: 每周复盘, 把收藏的资讯/标讯转成 actionable 任务, 通过紧急/重要双 flag 排期

---

## 1. 背景与目标

### 1.1 背景
现有 `favorites` 表只支持「星标收藏 + xlsx 导出」, 没有 next-step 行动追踪。
用户场景:
- 看到重要的安全漏洞 / 投资标讯 / GitHub 仓库 → ⭐ 收藏
- 收藏多了无法区分「要立即处理」vs「留着参考」
- 每周复盘时, 没有结构化的 action item 列表

### 1.2 目标
提供「待办」面板, 让用户:
1. 从收藏快速转成可执行任务 (保留 source 快照, 防止原资讯被删/过期)
2. 用「紧急/重要」双 flag 做 4 象限排期
3. 跟踪状态 (未完成 → 已完成 → 已归档) 便于每周复盘
4. 手动添加纯文本待办 (会议提醒 / 临时想法)

### 1.3 非目标 (YAGNI)
- 不做硬删除回收, 已归档 todo 永久保留
- 不做协作/分享/标签/截止日期 (本周 spec 不引入)
- 不做 push 通知/邮件提醒
- 不做自动归档 (Sunday 24:00 自动归档 = 上一轮 history 任务的延展, 不在本 spec)

---

## 2. 数据模型

### 2.1 `todos` 表 (migration 011_todos.sql)

```sql
CREATE TABLE todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,           -- 'favorite' | 'manual'
    source_id TEXT,                       -- hotspot_id (favorite 时填, manual 时 NULL)
    -- 快照字段 (原 favorites/hotspots 被删后 todo 仍完整)
    title TEXT NOT NULL,
    url TEXT,
    source TEXT,
    category TEXT,                        -- 'ai'|'security'|'finance'|'startup'|'bid'|'github'/NULL
    -- 优先级 (双 flag, 0/1, 4 种组合)
    urgent INTEGER NOT NULL DEFAULT 0,
    important INTEGER NOT NULL DEFAULT 0,
    -- 备注
    note TEXT,
    -- 状态
    status TEXT NOT NULL DEFAULT 'open',  -- 'open'|'done'|'archived'
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    archived_at TEXT
);
CREATE INDEX idx_todos_status ON todos(status, created_at DESC);
CREATE INDEX idx_todos_priority ON todos(urgent DESC, important DESC, created_at DESC);
CREATE INDEX idx_todos_source ON todos(source_id) WHERE source_type='favorite';
```

### 2.2 字段语义
- `source_type`:
  - `favorite`: 从收藏转来, `source_id` 必填 (hotspot_id)
  - `manual`: 用户手动添加, `source_id` 永远 NULL
- 快照字段 (`title/url/source/category`):
  - favorite: 从 favorites 表拷贝 (避免源被删后 todo 显示空标题)
  - manual: title 必填, url/source/category 可空
- `urgent` / `important`: 0/1, 默认 0 (不紧急不重要)
- `status`:
  - `open`: 默认, 显示在「未完成」
  - `done`: 用户勾选完成, `completed_at` 填
  - `archived`: 用户主动归档, `archived_at` 填
- 状态迁移:
  - `open → done`: 填 `completed_at`
  - `done → archived`: 填 `archived_at` (completed_at 保留)
  - `archived → open`: 清空 `completed_at`/`archived_at` (复活)
  - `open → archived`: 跳过 done, 直接归档 (填 archived_at)

### 2.3 唯一性约束
- **DB 层**: 不加 UNIQUE 约束 (允许 user 加同一 favorite 多次作为多个 task, 未来 flexibility)
- **API 层**: POST /api/todos with `source_type=favorite` + `source_id=X`, 若已存在 → 返回 200 `created=false` + 现有 todo (与 favorites.add 同样的 upsert 语义)

---

## 3. 后端 API

### 3.1 端点清单

| Method | Path | Body / Query | 功能 |
|--------|------|--------------|------|
| GET | `/api/todos` | `?status=open&urgent=1&important=1&limit=200` | 列表 + 多维筛选 |
| GET | `/api/todos/count` | — | 按 status/priority 统计 |
| GET | `/api/todos/available_favorites` | `?limit=200` | 列出「已收藏但未进 todo」的项 (备用入口) |
| POST | `/api/todos` | `{source_type, source_id?, title, url?, source?, category?, urgent?, important?, note?}` | 创建 (favorite-source 重复幂等) |
| PATCH | `/api/todos/{id}` | `{urgent?, important?, status?, note?}` | 部分更新 |
| DELETE | `/api/todos/{id}` | — | 硬删除 |

### 3.2 响应示例
```json
GET /api/todos?status=open&urgent=1
{
  "version": "1.2.0",
  "total": 3,
  "items": [
    {
      "id": 42,
      "source_type": "favorite",
      "source_id": "ai-2026-07-08-001",
      "title": "Palo Alto 被起诉",
      "url": "https://...",
      "source": "安全内参",
      "category": "security",
      "urgent": 1, "important": 1,
      "note": "需要看完整 PDF",
      "status": "open",
      "created_at": "2026-07-08T03:21:00+00:00",
      "updated_at": "2026-07-08T03:21:00+00:00",
      "completed_at": null,
      "archived_at": null
    }
  ]
}
```

```json
GET /api/todos/count
{
  "version": "1.2.0",
  "total": 8,
  "by_status": {"open": 5, "done": 2, "archived": 1},
  "by_priority": {
    "urgent_important": 1,
    "urgent_only": 2,
    "important_only": 1,
    "neither": 4
  }
}
```

### 3.3 关键不变量
- 同步 DB / 文件 IO 走 `asyncio.to_thread` (与 favorites/history 一致)
- `_validate_category` helper 复用 `backend/api/favorites.py` 模式
- 状态迁移在 PATCH 里集中处理 (`_apply_status_transition` 私有方法)
- 错误用 `HTTPException(400/404/500)` + 中文 message

---

## 4. 前端 UI

### 4.1 新文件
- `frontend/src/components/TodosPage.tsx` — 待办主页
- `frontend/src/hooks/useTodos.ts` — CRUD + 筛选 + count
- `frontend/src/components/TodoItem.tsx` — 单条待办行
- `frontend/src/components/AddTodoForm.tsx` — 底部手动添加 (折叠 inline 表单)
- `frontend/src/components/FavoriteToTodoPopover.tsx` — 收藏面板内嵌 popover
- `frontend/src/types/index.ts` — 新增 `TodoItem` / `TodoListResponse` / `TodoCountResponse`

### 4.2 Header 图标

**位置**: 状态栏 │ 📝待办 │ 📚历史 │ ⭐收藏 │ ⚙设置 │ 🌗主题 │ ⬇导出 │ ↻刷新

- 全部纯图标 (与现有 6 个按钮一致), 14×14, stroke=2, strokeLinecap=round
- 图标: 剪贴板 checklist (`M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1Z` + `M16 4h2a2 2 0 0 1 2 2v14...`)
- active 态 (`view === 'todos'`): 复用历史按钮 tint 样式 — `var(--color-ai)` 文字 + `var(--bg-hover)` 背景 + 2px 下划线
- 徽标: `openCount > 0` 时右上角红色圆点 (`#e85d5d`, 紧迫感), > 99 显示 99+

**view 状态机**:
- 旧: `view: 'home' | 'history'`
- 新: `view: 'home' | 'todos' | 'history'`
- 跳转全部通过点 Header 图标, 不在页面内嵌入口
- TodosPage / HistoryPage 各自有「← 返回首页」按钮回 home

### 4.3 TodosPage 布局

```
┌──────────────────────────────────────────────────────────┐
│ [← 返回首页]  📝 待办  本周复盘                          │
├────────────┬─────────────────────────────────────────────┤
│ 左侧 sticky │ 顶部筛选:  [全部][未完成][已完成][已归档]  │
│ 状态分布   │           紧急 ☑  重要 ☑  关键词🔍         │
│ ┌────────┐ ├─────────────────────────────────────────────┤
│ │未完成 5│ │ ☐  🔴 标题1  [源]  [note]  打开  删除       │
│ │已完成12│ │ ☐  🟠 标题2  [源]  [note]  打开  删除       │
│ │已归档 0│ │ ☑  🔵 标题3  [源]  [note]  打开  删除       │
│ │────────│ │ ☐  ⚪ 标题4  [源]  [note]  打开  删除       │
│ │紧急1  │ ├─────────────────────────────────────────────┤
│ │重要2  │ │ [+ 添加手动待办] (展开后是 inline 表单)      │
│ └────────┘ │   title  [紧急☐] [重要☐] note [添加]        │
└────────────┴─────────────────────────────────────────────┘
```

**TodoItem 视觉规格**:
- 左: 圆形 checkbox (点击切 open↔done)
- 中: 标题 (done 状态: 删除线 + 灰色) + 分类徽标 + 信源 + 可选 note (truncate 1 行)
- 右: 4 优先级 chip + 打开原文链接 + 删除按钮

**4 种优先级视觉编码** (P0 = 最优先, P3 = 参考):
- P0: 紧急+重要 = 红色实心 🔴 (top-left Eisenhower quadrant)
- P1: 紧急+不重 = 橙色实心 🟠 (top-right)
- P2: 重要+不急 = 蓝色实心 🔵 (bottom-left)
- P3: 都不 = 灰色空心 ⚪ (bottom-right)

### 4.4 FavoriteToTodoPopover

- FavoritesPanel 每条收藏右侧追加 `→ 待办` 按钮
- 点击 → 原位展开 60-80px panel (不弹 modal, 避免打断浏览)
- 内容: 紧急 ☐ / 重要 ☐ / 备注 textarea / [确认] [取消]
- 确认 → POST → 该条目变绿色 ✓ 已加入 (UI 层: 按钮变 ✓ 已加入态, 防止重复点击; API 层仍允许重复添加, 见 2.3)
- 错误: toast 显示原因

### 4.5 App.tsx 改造
- 顶层 `useTodos` 管理 list + count, 跨页面共享
- 启动时拉一次 `/api/todos/count` 给 Header 徽标
- CRUD 后自动 invalidate count

### 4.6 类型定义 (types/index.ts 新增)
```ts
export type TodoStatus = 'open' | 'done' | 'archived';
export interface TodoItem {
  id: number;
  source_type: 'favorite' | 'manual';
  source_id: string | null;
  title: string;
  url: string | null;
  source: string | null;
  category: string | null;
  urgent: boolean;
  important: boolean;
  note: string | null;
  status: TodoStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  archived_at: string | null;
}
export interface TodoCountResponse {
  total: number;
  by_status: Record<TodoStatus, number>;
  by_priority: {
    urgent_important: number;
    urgent_only: number;
    important_only: number;
    neither: number;
  };
}
```

---

## 5. 测试

### 5.1 后端
- `backend/tests/test_todos_repo.py`:
  - add/upsert (重复 source_id 不创建新行)
  - update priority / status
  - list 筛选 status + urgent + important
  - count by_status / by_priority
  - delete
- `backend/tests/test_todos_api.py`:
  - POST favorite-source 重复幂等 (200 + created=false)
  - PATCH status 迁移时间戳正确
  - GET list 多维筛选
  - GET available_favorites 排除已在 todo 的 source_id

### 5.2 端到端 curl 验证
- `curl -X POST /api/todos -d '{...}'` → 201
- `curl -X POST /api/todos -d '{source_type:favorite, source_id:X}'` (相同 source_id) → 200 created=false
- `curl -X PATCH /api/todos/1 -d '{"status":"done"}'` → completed_at 填
- `curl /api/todos?status=open&urgent=1` → 仅返紧急未完成

### 5.3 前端 (可选, 如现有 vitest 套件)
- `useTodos.test.ts`:
  - add / update / delete 操作 + state 更新
  - filter 组合

---

## 6. 风险 & 缓解

| 风险 | 缓解 |
|------|------|
| FavoritesPanel 加 popover 增加组件复杂度 | 把 popover 抽成单独子组件 + state 提升 |
| view 三态切换可能让 Header 按钮组顺序乱 | 明确 JSX 顺序, UI 一眼看清 |
| source_id 唯一性靠 API 层 (无 DB UNIQUE), 并发可能重复 | SQLite 串行写, 单进程安全; 多进程时再加 partial UNIQUE INDEX |
| 4 象限视觉色编码可能与品牌色冲突 | 用现有 6 大分类色 (red/orange/blue/gray), 与全站一致 |
| 完成/归档后用户找不到入口回看 | TodosPage 顶部 [全部]/[未完成]/[已完成]/[已归档] 4 段筛选 |

---

## 7. 验收标准 (Definition of Done)

- [ ] migration 011_todos.sql 通过 `db.init_db()` 自动执行
- [ ] 6 个 API 端点全部可 curl 调用, 错误返回结构化 message
- [ ] `useTodos` hook 支持 list/count/add/update/delete + 多维筛选
- [ ] Header 显示 📝 待办按钮 (📚历史 左侧), active tint, open count 徽标
- [ ] 点 Header 待办按钮 → 跳转 TodosPage (view='todos')
- [ ] TodosPage: 左侧状态分布 + 顶部筛选 + 列表 + 底部手动添加, 全部可交互
- [ ] FavoritesPanel 每条收藏有 `→ 待办` 按钮, popover 提交后条目变 ✓ 已加入
- [ ] 4 象限视觉色编码生效 (紧急重要=红 / 紧急=橙 / 重要=蓝 / 都不=灰)
- [ ] 后端 pytest 全通过 (含 test_todos_repo + test_todos_api)
- [ ] 前端 TypeScript `tsc --noEmit` exit 0
- [ ] Vite HMR 自动 reload, 浏览器无 console error
- [ ] 端到端: 从首页 ⭐ 收藏 1 条 → 打开收藏面板 → 点 `→ 待办` → 设置紧急+重要 → 打开 Header 待办 → 看到该条为 🔴 P0 → 勾选完成 → 移到 [已完成]
