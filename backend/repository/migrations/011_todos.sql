-- ============================================================================
-- 011_todos.sql — Phase 36 待办 (Todos): 从收藏/手动输入转成可执行任务
--
-- 背景
-- ----
-- 现有 favorites 表只支持「星标收藏 + xlsx 导出」, 没有 next-step 行动追踪。
-- 收藏多了无法区分「要立即处理」vs「留着参考」, 每周复盘时缺乏结构化的
-- action item 列表。
--
-- 设计要点
-- --------
-- - `source_type`:
--     * `favorite` — 从收藏转来, `source_id` 必填 (hotspot_id)
--     * `manual`   — 用户手动添加, `source_id` 永远 NULL
-- - 快照字段 (title/url/source/category):
--     * favorite: 从 favorites 表拷贝 (避免源被删后 todo 显示空标题)
--     * manual:   title 必填, url/source/category 可空
-- - 优先级 (双 flag, 0/1, 4 种组合):
--     * urgent=1 + important=1 → P0 红色
--     * urgent=1 + important=0 → P1 橙色
--     * urgent=0 + important=1 → P2 蓝色
--     * urgent=0 + important=0 → P3 灰色
-- - 状态 (`status`):
--     * `open`     — 默认, 显示在「未完成」
--     * `done`     — 用户勾选完成, `completed_at` 填
--     * `archived` — 用户主动归档, `archived_at` 填
-- - 状态迁移:
--     * `open → done`     填 `completed_at`
--     * `open → archived` 填 `archived_at` (直接归档, 跳过 done)
--     * `done → archived` 填 `archived_at` (completed_at 保留)
--     * `archived → open` 清空 `completed_at` / `archived_at` (复活)
-- - 唯一性约束:
--     * DB 层不加 UNIQUE (允许 user 加同一 favorite 多次作为多个 task)
--     * API 层做 upsert: 重复 favorite-source 返回 200 + created=false
-- ============================================================================

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,                    -- 'favorite' | 'manual'
    source_id TEXT,                                -- hotspot_id (favorite 时填, manual 时 NULL)
    -- 快照字段 (原 favorites/hotspots 被删后 todo 仍完整)
    title TEXT NOT NULL,
    url TEXT,
    source TEXT,
    category TEXT,                                 -- 6 大分类或 NULL
    -- 优先级 (双 flag, 0/1)
    urgent INTEGER NOT NULL DEFAULT 0,
    important INTEGER NOT NULL DEFAULT 0,
    -- 备注
    note TEXT,
    -- 状态
    status TEXT NOT NULL DEFAULT 'open',           -- 'open' | 'done' | 'archived'
    -- 时间戳 (ISO 8601 UTC, 与项目其他表一致)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    archived_at TEXT
);

-- 列表筛选索引: status + created_at DESC
CREATE INDEX IF NOT EXISTS idx_todos_status
    ON todos(status, created_at DESC);

-- 优先级排序索引: 紧急 → 重要 → 新→旧
CREATE INDEX IF NOT EXISTS idx_todos_priority
    ON todos(urgent DESC, important DESC, created_at DESC);

-- 重复检测 partial 索引: 仅 favorite 类型 source_id 需要 O(1) 查重
CREATE INDEX IF NOT EXISTS idx_todos_source
    ON todos(source_id) WHERE source_type = 'favorite';
