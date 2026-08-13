# 知识管理 · 资讯收藏聚合视图 实施计划

## Context

hotspot 知识管理页面（`/knowledge`）目前有 4 大领域：信息导入 / 处理数据 / 知识库编译 / 知识复利。信息导入页有 4 个 action card（Cubox 同步 / 浏览器书签 / Obsidian vault / 冲突快照），用户希望**新增第 5 个 action card「资讯收藏」**，点击后打开新页面 `/knowledge/favorites`，统一展示所有"已导入资讯"（Cubox + 书签 + 收藏 + 历史资讯），支持：

- 按名称搜索
- 按类型筛选：科技/AI、网络安全、GitHub、标讯、其他
- 按时间范围筛选
- 分页

**约束**：
- 不影响现有 4 大领域结构与流程（用户已确认"不影响现在结构和流程"）
- 入口在信息导入页 → 第 5 个 action card
- 数据源 = favorites ∪ knowledge_items（source IN 'cubox'/'bookmark'/'secnews'/'secnews_archive'）

---

## 关键数据源分析

| 数据源 | 表 | source 字段值 | 现有查询能力 |
|---|---|---|---|
| **UI 收藏** | `favorites` | category (ai/security/finance/startup/bid/github) | `list(category, limit)` —— 无 name 搜索 / 无时间范围 / 无分页 |
| **Cubox 导入** | `knowledge_items` | `source='cubox'` | `list_items(source='cubox', since, until, limit, offset)` —— 无 name 搜索 |
| **书签导入** | `knowledge_items` | `source='bookmark'` | 同上 |
| **历史资讯导入** | `knowledge_items` | `source='secnews_archive'` | 同上 |
| **收藏 promote** | `knowledge_items` | `source='secnews'` | 同上（与 favorites URL 重叠） |

**去重策略**：同一 URL 在 favorites 和 knowledge_items 都存在，**favorites 胜出**（更详细字段，含 created_via + favorited_at）。

---

## 后端改动 (3 处)

### 1. 新 service: `backend/services/imported_aggregator.py`

```python
def list_imported(
    keyword: str | None = None,
    type_filter: str | None = None,   # ai | security | github | bid | other | all
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """聚合 favorites + knowledge_items, 按 URL 去重 (favorites 优先)"""
    # 1. 查 favorites (主结果) - 全字段
    fav_items = query_favorites(keyword, type_filter, since, until, limit+offset+100)
    fav_urls = {it['url'] for it in fav_items}
    
    # 2. 查 knowledge_items - 排除 favorites 已包含的 URL
    ki_items = query_knowledge_items(
        sources=['cubox', 'bookmark', 'secnews', 'secnews_archive'],
        keyword=keyword, type_filter=type_filter,
        since=since, until=until, exclude_urls=fav_urls,
        limit=limit+offset+100
    )
    
    # 3. 标准化 schema, 合并排序 (ingested_at DESC), 切片
    merged = sorted(fav_items + ki_items, key=lambda x: x['ingested_at'], reverse=True)
    page = merged[offset:offset+limit]
    return {"items": page, "total": len(merged), "has_more": len(merged) > offset+limit}
```

**标准化 schema** (`ImportedItem`):
```python
{
  "id": "fav:abc123" | "ki:def456",
  "origin": "favorite" | "cubox" | "bookmark" | "secnews_archive" | "secnews",
  "title": "...",
  "url": "...",
  "category": "ai" | "security" | ... | "other",
  "type_label": "科技/AI" | "网络安全" | ... | "其他",
  "tags": ["ai-coding", "langchain"],
  "ingested_at": "2026-07-26T...",
  "summary": "...",  # 仅 knowledge_items 有
  "lifecycle": "kl:raw" | None,
  "created_via": "ui" | "mcp" | "agent" | None
}
```

**type 字段映射**:
- `ai` ↔ source IN ('ai', 'secnews', 'secnews_archive' where topic in ai/tech) → "科技/AI"
- `security` → "网络安全"
- `github` → "GitHub"
- `bid` → "标讯"
- `finance` / `startup` → "其他"

### 2. 新 API endpoint: `backend/api/knowledge_imported.py`

```python
router = APIRouter(prefix="/api/knowledge/imported", tags=["knowledge-imported"])

@router.get("")
async def list_imported(
    keyword: Optional[str] = Query(None, max_length=200),
    type: Optional[str] = Query(None, regex="^(ai|security|github|bid|other|all)$"),
    since: Optional[str] = Query(None, description="ISO datetime"),
    until: Optional[str] = Query(None, description="ISO datetime"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await asyncio.to_thread(
        _build_imported_payload, keyword, type, since, until, limit, offset
    )
```

**注册路由**: 在 `backend/api/__init__.py:register_routers` 的列表中追加 `knowledge_imported.router`

### 3. 复用现有 repository 方法

- `FavoriteRepository.list(category, limit)` —— **扩展**：增加 `keyword`、`since`、`until` 参数，内部用 `title LIKE ?` + `favorited_at` BETWEEN
- `knowledge_repo.list_items(source, since, until, limit, offset)` —— 已有，**扩展**：增加 `keyword` 参数（`title LIKE ?`），增加 `exclude_urls` 参数（`source_url NOT IN (...)`）

---

## 前端改动 (5 处)

### 1. 新页面组件: `frontend/src/components/knowledge/KnowledgeFavorites.tsx`

```
[Hero 区域] - 描述"资讯收藏"用途
[筛选条] - 名称搜索 input + 类型 chips (5 个) + 时间 range picker + 重置按钮
[统计条] - 共 N 条 / 当前 X-Y 条 / origin 分布
[列表区] - ImportedItem 卡片，悬浮展开 origin 标签
[分页] - 上一页/下一页 + 跳转
[空态/错误] - <EmptyState> + error banner
```

**复用模式**：
- 布局：`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-3` 卡片列表
- 筛选条：`btn-ghost` + active 底边下划线（HistoryPage L293-316 模式）
- Toast: inline 模式（同 KnowledgeImport）
- 加载态：`<p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>加载中…</p>`
- 错误条：`color-mix(in srgb, var(--color-error) 12%, transparent)` 背景
- 时间 range: 用 `<input type="date">` 两个

### 2. 新 hook: `frontend/src/hooks/useImported.ts`

```typescript
export function useImported(params: {
  keyword: string;
  type: string;
  since: string;
  until: string;
  page: number;
  pageSize: number;
}) {
  // 300ms debounce keyword
  // useState { items, total, has_more, loading, error }
  // useEffect 触发 fetch
  // useCallback reset
  // 支持分页跳转
}
```

**复用 `useSearch.ts` debounce 模式**（300ms setTimeout ref）

### 3. 新增 5th action card: `KnowledgeImport.tsx` L411 后追加

在 L411 `</section>` 闭合标签**之前**插入第 5 个 `<div className="rounded-... ">` action card：

```tsx
{/* 资讯收藏 (新) */}
<div className="rounded-[var(--radius-md)] p-3.5" style={...}>
  <div className="flex items-center gap-2 mb-2">
    <span className="w-6 h-6 rounded-md ..."><Icon size={12}>★</Icon></span>
    <h4 className="text-xs font-bold">资讯收藏</h4>
    <span className="text-[10px]">所有已导入资讯</span>
  </div>
  <p className="text-[11px] mb-3">聚合 Cubox、书签、收藏、历史资讯导入的全部条目，支持搜索/筛选/分页。</p>
  <button
    onClick={() => navigate('/knowledge/favorites')}
    className="btn-ghost px-3 py-1.5 text-xs"
    style={{ color: 'var(--area-accent)' }}
  >
    查看资讯收藏
  </button>
</div>
```

**重要**：
- 用 `useNavigate()` from react-router-dom
- grid 改为 `md:grid-cols-2` 保持 2 列（5 个 card 第 5 个单独占一行）—— 用 `md:col-span-2` 让 5th card 跨满整行，符合截图红框位置

### 4. 路由注册: `App.tsx` L401 后追加

```tsx
<Route path="favorites" element={<Suspense fallback={<PageFallback />}><KnowledgeFavorites /></Suspense>} />
```

### 5. 测试: `frontend/src/components/knowledge/KnowledgeFavorites.test.tsx`

参考 `KnowledgeTabs.test.tsx` 模式（`MemoryRouter` 包裹）+ `HotspotGrid.test.tsx` 模式（不 mock fetch，传 props 断言）：

- 渲染筛选条
- type chip 切换
- keyword debounce 触发 fetch
- 分页跳转
- 空态 / 错误态
- `useNavigate` 调用（mock useNavigate，断言 5th card 点击触发跳转）

---

## 文件清单

| 类型 | 文件 | 状态 |
|---|---|---|
| 后端 service | `/Users/duke/Documents/hotspot/backend/services/imported_aggregator.py` | 🆕 新建 |
| 后端 API | `/Users/duke/Documents/hotspot/backend/api/knowledge_imported.py` | 🆕 新建 |
| 后端路由注册 | `/Users/duke/Documents/hotspot/backend/api/__init__.py` | ✏️ 加 1 行 |
| 后端 repo 扩展 | `/Users/duke/Documents/hotspot/backend/repository/favorite_repo.py` | ✏️ `list()` 加 keyword/since/until 参数 |
| 后端 repo 扩展 | `/Users/duke/Documents/hotspot/backend/repository/knowledge_repo.py` | ✏️ `list_items()` 加 keyword + exclude_urls |
| 后端测试 | `/Users/duke/Documents/hotspot/backend/tests/test_imported_aggregator.py` | 🆕 新建 |
| 前端页面 | `/Users/duke/Documents/hotspot/frontend/src/components/knowledge/KnowledgeFavorites.tsx` | 🆕 新建 |
| 前端 hook | `/Users/duke/Documents/hotspot/frontend/src/hooks/useImported.ts` | 🆕 新建 |
| 前端 action card | `/Users/duke/Documents/hotspot/frontend/src/components/knowledge/KnowledgeImport.tsx` | ✏️ 加 5th card + useNavigate import |
| 前端路由 | `/Users/duke/Documents/hotspot/frontend/src/App.tsx` | ✏️ 加 1 行 Route |
| 前端测试 | `/Users/duke/Documents/hotspot/frontend/src/components/knowledge/KnowledgeFavorites.test.tsx` | 🆕 新建 |

---

## 实施步骤

1. **后端 service + API + 路由注册** (3 文件)
   - `imported_aggregator.py` 实现聚合 SQL + 去重
   - `knowledge_imported.py` API endpoint
   - `__init__.py` 注册路由
   - **验证**: `curl /api/knowledge/imported?type=ai` 返回 200 + 数组

2. **后端 repository 扩展** (2 文件)
   - `favorite_repo.list()` 加 keyword/since/until
   - `knowledge_repo.list_items()` 加 keyword + exclude_urls
   - **验证**: 单测覆盖 3 种 filter 组合

3. **后端测试** (1 文件)
   - `test_imported_aggregator.py` - 覆盖去重 / 5 类型 / 时间范围 / 关键词
   - **验证**: `pytest backend/tests/test_imported_aggregator.py -v` 全过

4. **前端 hook** (1 文件)
   - `useImported.ts` 300ms debounce + 分页
   - **验证**: `tsc --noEmit` 通过

5. **前端页面组件** (1 文件)
   - `KnowledgeFavorites.tsx` - 筛选条 + 列表 + 分页
   - **验证**: 手动在 dev server 打开 `/knowledge/favorites` 渲染正常

6. **KnowledgeImport 5th card + 路由注册** (2 文件)
   - `KnowledgeImport.tsx` 加 card + useNavigate
   - `App.tsx` 加 Route
   - **验证**: 点击 5th card 跳转到 `/knowledge/favorites`

7. **前端测试** (1 文件)
   - `KnowledgeFavorites.test.tsx`
   - **验证**: `npx vitest run KnowledgeFavorites` 全过

8. **端到端验证**
   - 启动后端 + 前端 dev server
   - 访问 `/knowledge/import` → 看到 5th card "资讯收藏"
   - 点击 → 跳转 `/knowledge/favorites` → 显示导入列表
   - 切换 type chip、输入关键词、选时间范围 → 列表实时过滤
   - 翻页 → URL 变化（如有） + 列表更新

---

## 风险与边界

1. **同一 URL 在 favorites + knowledge_items 双写** —— 服务层用 `exclude_urls` 过滤；favorites 优先保留
2. **大表性能** —— 初始 50/页 + offset 分页，全表扫描风险；5000 条以内可接受，超出后改为 cursor 分页（与 hotspots 一致）
3. **source 字段语义模糊** —— `secnews` 实际来自 favorites promote，UI 显示统一为 "已收藏"（origin='favorite'），避免混淆
4. **5 类型映射** —— `finance`/`startup` 在用户列表里没提到，合并为 "其他" 兜底 chip
5. **时间字段** —— favorites 用 `favorited_at`，knowledge_items 用 `ingested_at`，统一映射为 `ingested_at`

---

## 验证

- 后端: `pytest backend/tests/test_imported_aggregator.py -v`
- 前端类型: `cd frontend && npx tsc --noEmit`
- 前端测试: `cd frontend && npx vitest run KnowledgeFavorites`
- 全量回归: `cd frontend && npx vitest run`
- e2e: 启动后端 + 前端，手动点 5th card → 跳转 → 筛选 → 翻页
