-- ============================================================================
-- 012_skills.sql — Phase 41 Skill 管理
--
-- 背景
-- ----
-- 用户经常需要把"如何在 Agent 里使用某个 skill"的安装指令集中管理,
-- 一键复制到 Agent 上下文。手工记录在外部文档容易丢, 也不便搜索。
--
-- 设计要点
-- --------
-- - name: skill 名称 (必填, e.g. "aihot", "baoyu-cover-image")
-- - url: skill 链接 (e.g. GitHub 仓库, 必填)
-- - install_command: 安装指令 (必填, 一键复制的内容)
-- - description: 简介 (可选)
-- - source: 安装方式分类 ("npx" / "uvx" / "curl" / "git" / "manual"),
--   用于列表筛选; 留空 = "manual"
-- - tags: JSON 字符串数组 (e.g. '["ai","image"]'), 用于标签筛选
-- - 时间戳统一 ISO 8601 UTC
-- ============================================================================

CREATE TABLE IF NOT EXISTS skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    install_command TEXT    NOT NULL,
    description     TEXT,
    source          TEXT    NOT NULL DEFAULT 'manual',
    tags            TEXT    NOT NULL DEFAULT '[]',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_skills_source   ON skills(source);
CREATE INDEX IF NOT EXISTS idx_skills_created  ON skills(created_at DESC);
