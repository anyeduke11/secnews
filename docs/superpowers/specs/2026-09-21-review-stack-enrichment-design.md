# 复习栈能力丰富 · 设计稿 (Review Stack Enrichment)

> **日期**: 2026-09-21 · **状态**: 已批准 (owner 逐项裁决后整体确认 "按这个方案来")
> **落点**: `/action` 行动页复习栈面板 + 页内全屏 ReviewOverlay
> **关联**: SM-2 链路为 v1.7 Phase 2 既有资产 (migration 026); 本设计不改动 SM-2 算法本身

---

## 1. 背景与问题

`/action` 复习栈面板 ([SentinelActionPage.tsx](../../../frontend/src/components/sentinel/SentinelActionPage.tsx)) 目前能力很薄, 卡在六个结构性短板:

1. **卡片无内容** — 仅渲染裸 `entity_id` (如 `reddit_IT之家_b05ae429e1e2`), 无标题/链接/领域, "记没记住"的自评无从谈起;
2. **无翻卡** — 正面背面不分, 缺 "先回忆再看答案" 的复习动作;
3. **评分无反馈** — SM-2 算出新间隔但 UI 不显示 "下次 N 天后见";
4. **无撤销/稍后/键盘快捷键** — 误评只能将错就错;
5. **无预报与历史** — 仅 "今日 N / 在册 N / 平均 EF" 三个数;
6. **无卡片管理** — 队列只靠 attention 事件自动建卡, 不能手动加卡, 不能暂停/删除。

另有 `/knowledge/review` 的 ReviewMode 翻卡会话 (Phase 17), 只认 `knowledge_item` 类型, hotspot 卡整卡跳过 — 两个复习面各缺一半。

**既有后端资产** (全部保留复用):
- `backend/services/review_service.py`: `sm2_schedule` 纯函数 / `submit_grade` / `list_due` / `stats` / `create_review`
- `backend/repository/reviews_repo.py`: upsert / get / list_due / list_all / delete / count
- `backend/api/reviews.py` (133 行): due / grade / stats / create / get 五端点
- 自动建卡: `attention_events_service.maybe_create_sm2_review` (view/dwell>30s/favorite → `create_review("knowledge_item", id)`)
- 每日推送: `sm2_daily_push_job` (08:00 SSE `review_due`)
- mastery 投影: 评分后单向写 wiki frontmatter

## 2. 裁决记录 (owner, 2026-09-21)

| 问题 | 裁决 |
|---|---|
| 能力范围 | 四方向全选: 卡片可读闭环 / 复习会话体验 / 复习数据面 / 卡片管理能力 |
| 重能力形态 | **面板 + 页内全屏 overlay** (面板保持轻量快速评分; 翻卡会话/预报/历史/管理做成 overlay 弹层, 不动路由) |
| 后端深度 | **完整后端**: 新增 review_log 表 + suspended 列 + 预报/撤销/暂停端点 + list_due 标题解析 |
| 手动加卡入口 | **管理器内搜索加卡** (本批不动 FeedCard/WikiItemBrowser 等外页) |
| 架构分叉 | 方案 A: **单个 ReviewOverlay** 内含三视图 (会话/数据/管理); 否决三独立弹层 (状态管理三份重复/视觉碎片化) |

## 3. 后端设计

### 3.1 Migration 120 (表温度归属: retention.json 权威 — `sm2_reviews` temp=HOT, `review_log` 随行 HOT/main)

```sql
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    grade INTEGER NOT NULL,
    prev_easiness REAL, prev_interval INTEGER, prev_repetitions INTEGER,
    prev_due_at TEXT, prev_last_reviewed_at TEXT, prev_last_grade INTEGER,
    new_easiness REAL NOT NULL, new_interval INTEGER NOT NULL,
    new_repetitions INTEGER NOT NULL, new_due_at TEXT NOT NULL,
    reverted INTEGER NOT NULL DEFAULT 0,   -- 撤销后置 1, 保留痕迹
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rlog_entity ON review_log(entity_type, entity_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_rlog_created ON review_log(created_at DESC);
ALTER TABLE sm2_reviews ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0;
```

- `review_log` 是撤销与统计的唯一真数据源; 每次评分写一条 旧→新 全量快照 (含 prev_last_grade/prev_last_reviewed_at, undo 逐级回退需要)。
- 遵守 DEV-0226 教训: 表归属以 `scripts/retention.json` 为权威 — sm2_reviews 登记为 temp=HOT, review_log 同温度落 main; retention.json 同步补 review_log 条目。
- ALTER TABLE 非 idempotent, 但 schema_version 保证单库只执行一次 (migration 119 同款先例)。

### 3.2 服务层改造 (`review_service.py` + `reviews_repo.py` + 新 `reviews_log_repo.py`)

- `submit_grade`: 评分前读旧状态 → SM-2 计算 → upsert → 写 review_log (旧→新)。失败路径不变。
- `ReviewLogRepository` (新, 遵守 R2 写路径唯一): insert / latest_active(entity) / mark_reverted(id) / list_recent(limit) / retention(days) / grade_distribution(days)。
- `list_due`: SQL 排除 `suspended=1`。
- **enrich 解析** (`review_enrich.py` 新模块, 纯查询): 按 `entity_type` 注册表解析标题 —
  - `hotspot` → `hotspots` (title / url / category / summary→excerpt)
  - `knowledge_item` → `knowledge_items` (title / source_url→url / domain; 无摘要列, excerpt 置空)
  - 未命中或行已删除 → 兜底返回原 entity_id, title=null (前端如实渲染裸 id)
- 新 `stats` 扩展: `retention_30d` (review_log 近 30 天 grade≥3 占比, 无数据返回 null) / `grade_distribution` / `suspended_count`。
- `forecast(days)`: 未来 N 天逐日到期计数 (`date(due_at)` 聚合, 排除 suspended, 含今日)。

### 3.3 API 端点 (`reviews.py` 现有 133 行放不下, 新端点拆 `reviews_manage.py`, 同 prefix `/api/reviews`)

**文件归属规则**: 既有路径 (`/due` `/stats` `/{type}/{id}`) 留在 `reviews.py` 原地扩展; 新路径全部进 `reviews_manage.py`。

| 端点 | 类型 | 语义 |
|---|---|---|
| `GET /due?enrich=1` | 扩展 (reviews.py) | 每条附 `title/url/category/excerpt` |
| `GET /stats` | 扩展 (reviews.py) | 响应增 `retention_30d` / `grade_distribution` / `suspended_count` |
| `GET /forecast?days=7` | 新 (reviews_manage.py) | 未来 7 天每日到期数 |
| `POST /{type}/{id}/undo` | 新 (reviews_manage.py) | 恢复最新一条 `reverted=0` log 的 prev 状态 (含 prev_last_grade/last_reviewed_at) 并标记 reverted; 首评撤销 (prev 为空) = 删除记录; 链式可重复调用逐级回退; 无活跃 log → **409** (评分与 log 在 submit_grade 内原子写入, 不存在 "更新的评分无 log" 状态) |
| `PATCH /{type}/{id}` | 新 (reviews_manage.py) | `{suspended: bool}` 暂停/恢复 |
| `DELETE /{type}/{id}` | 新 (reviews_manage.py) | 删卡 (repo.delete 已有, 补端点) |
| `GET /history?limit=50` | 新 (reviews_manage.py) | review_log 倒序流 (含 reverted 标记) |
| `GET /cards?limit=200` | 新 (reviews_manage.py) | 全部卡片列表 (管理视图表格数据源; 含 suspended 状态, enrich 后返回)。规划期补充: 既有端点只有单卡查询, 管理视图需要全量列表 |

- 遵守 api 层纪律: 文件 ≤150 行 / `_registry.py` 登记 / lazy import / 错误契约扁平 envelope。
- **架构数字**: 拆文件后 routers 86→87, 实施时 `python scripts/generate_meta.py` 同步 ARCHITECTURE.md (CI 有 --check)。

### 3.4 已知边界 (如实记录)

- undo 只回滚 sm2_reviews 队列状态, **不回滚** mastery 投影到 wiki frontmatter 的字段 (下次评分自然覆盖, 影响可忽略)。
- `POST /{type}/{id}` 建卡端点已存在, 管理器搜索加卡直接复用, 不新增。

## 4. 前端设计

### 4.1 面板增强 (轻量, SentinelActionPage 复习栈 section 内)

- 卡片标题化: 主行 enrich 后 title, entity_id 降为副行; 附 "查看原文" 外链 (safeHref 白名单复用)。
- 评分即时反馈: "下次 N 天后见" (grade 响应新 interval)。
- 误评撤销: 评分后 5 秒窗口显示 "撤销" 按钮 (调 undo; 409 时静默隐藏)。
- 键盘 `1 / 3 / 5` 快捷评分 (面板聚焦时)。
- 底部新增 "专注复习 / 卡片管理" 两个 overlay 入口。

### 4.2 ReviewOverlay (新组件族, `components/sentinel/review/`, PascalCase + colocated test)

单弹层三视图, 页内 state 切换:

- **会话视图**: 翻卡 — 正面 = 标题 + 来源 + 领域徽标; 背面 = 摘要 excerpt + SM-2 参数 (EF/间隔/重复/上次评分)。空格翻面, `1/3/5` 评分进下一张。会话结束汇总页: 本次已评数 / 评分分布 / 每张可撤销。
- **数据视图**: 7 日到期预报柱状 / 复习历史流 (review_log 倒序, reverted 条目标记) / 保留率 30d / 评分分布 / 在册+暂停计数。
- **管理视图**: 全部卡片表格 (标题/EF/间隔/到期/状态), 行内 暂停/恢复/删除; 顶部搜索框加卡 — 复用 `GET /api/search?sources=hotspot,knowledge` 检索, 一键 `POST /api/reviews/{type}/{id}` 入栈 (type 按搜索结果来源映射 hotspot/knowledge_item)。

- 视觉纪律: 沿用 sentinel 设计语言, `sentinel-action.css` 扩展 `ac-rv-*` 命名空间; 本批是能力扩展, V2 ACTION FLOOR 视觉契约不动。
- 路由: **零新增路由**, 纯 overlay state, NAV4 四菜单纪律无涉。
- 网络调用: 沿用组件内 `lib/api` (getJSON/postJSON/apiFetch) 先例, 与 SentinelActionPage 同款, 不新增域客户端层。

### 4.3 ReviewMode (/knowledge/review) 处置

本批不动。其 "只认 knowledge_item、hotspot 卡整卡跳过" 是既有 bug, 记为遗留 — 后续可改吃 `/due?enrich=1` 统一解析, 天然受益于本批 enrich。

## 5. 测试与守卫

- **后端**: enrich 解析命中/未命中兜底 / undo 正常+409 两态 / forecast 聚合 / suspended 影响 due 与 forecast / delete 端点 / submit_grade 写 log 断言 / stats 扩展字段 / migration 120 幂等。
- **前端**: ReviewOverlay 翻卡/评分/撤销/三视图切换测试; SentinelActionPage 既有测试更新 (标题渲染/键盘评分/undo 窗口)。
- **守卫**: `generate_meta.py --check` (routers +1 同步) / ruff 触碰文件 / api 行数 ≤150 / 全量 pytest + vitest 回归。

## 6. YAGNI 边界 (本批不做)

- 不动 FeedCard/WikiItemBrowser 等外页嵌入式 "加入复习" 按钮 (留后续批)。
- 不做每日新卡上限/学习计划调度。
- 不做 SM-2 算法参数调优 (算法零改动)。
- 不做 SSE 实时推送到 overlay。
- 不做跨设备同步 schema 扩展 (review_log/suspended 随既有 sync_bundle 策略自然演进, 不在本批范围)。

## 7. 验收口径

1. `/action` 面板卡片显示真实标题, 评分后显示 "下次 N 天后见", 5 秒内可撤销;
2. overlay 会话视图可完整走完 3+ 张翻卡评分, 汇总页可撤销任意一张;
3. 数据视图预报 7 日数值与 review_log/suspended 状态一致;
4. 管理视图可暂停一张卡 → due 队列与预报同步消失该卡; 可搜索加一张新卡并立即出现在栈中;
5. 后端新增测试全绿, 全量回归 0 失败, `generate_meta --check` 过。
