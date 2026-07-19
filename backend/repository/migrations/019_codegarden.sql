-- 019_codegarden.sql — Phase 2a CodeGarden MVP
-- PRD: docs/CodeGarden_PRD_v2.0.md (6.2 表结构定义)
-- 校正: PRD 假设的 knowledge_skills 表实际叫 skills (Phase 41 012_skills.sql 创建)

-- ============================================================================
-- cg_projects: 项目主表 (PRD 6.2.1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    type TEXT NOT NULL,              -- web_application / api_service / cli / crawler / library / experiment
    source_type TEXT NOT NULL,       -- vibe / fork / imported / reference
    lifecycle_stage TEXT NOT NULL,   -- ideation / prototype / development / testing / running / maintenance / archived / deprecated
    health_score INTEGER DEFAULT 0,
    local_path TEXT,
    repo_url TEXT,
    upstream_url TEXT,
    upstream_default_branch TEXT,
    commits_behind INTEGER DEFAULT 0,
    commits_ahead INTEGER DEFAULT 0,
    last_synced_at TEXT,
    source_item_id TEXT,             -- 反向溯源 knowledge_items.id (github 资讯转化)
    source_type_detail TEXT,         -- trending / github_search / manual
    tags TEXT NOT NULL DEFAULT '[]',
    tech_stack TEXT NOT NULL DEFAULT '[]',
    domain TEXT,
    priority INTEGER DEFAULT 0,
    active_skill_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    last_activity_at TEXT,
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_projects_lifecycle ON cg_projects(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_cg_projects_source_type ON cg_projects(source_type);
CREATE INDEX IF NOT EXISTS idx_cg_projects_source_item ON cg_projects(source_item_id);
CREATE INDEX IF NOT EXISTS idx_cg_projects_last_activity ON cg_projects(last_activity_at DESC);

-- ============================================================================
-- cg_project_stages: 项目阶段/交付物 (PRD 6.2.2)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_stages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    deliverable_type TEXT,           -- code / doc / test / config / release
    deliverable_url TEXT,
    deliverable_path TEXT,
    commit_sha TEXT,
    status TEXT NOT NULL DEFAULT 'planned',  -- planned / wip / done / skipped
    notes TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_stages_project ON cg_project_stages(project_id, stage_order);

-- ============================================================================
-- cg_project_links: 关联 repo (PRD 6.2.3)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_links (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,         -- upstream / reference / inspiration / dependency
    url TEXT NOT NULL,
    label TEXT,
    commits_behind INTEGER,
    commits_ahead INTEGER,
    last_synced_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cg_links_project ON cg_project_links(project_id);

-- ============================================================================
-- cg_project_activities: 活动日志 (PRD 6.2.4)
-- ============================================================================
CREATE TABLE IF NOT EXISTS cg_project_activities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES cg_projects(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,     -- commit / note / decision / release / status_change / sync
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cg_activities_project ON cg_project_activities(project_id, created_at DESC);

-- ============================================================================
-- skills 表扩展 9 字段 (PRD 6.3.1, 表名校正: knowledge_skills → skills)
-- ============================================================================
ALTER TABLE skills ADD COLUMN skill_type TEXT DEFAULT 'knowledge';
ALTER TABLE skills ADD COLUMN capabilities TEXT;       -- JSON array
ALTER TABLE skills ADD COLUMN constraints_json TEXT;   -- JSON (避开 SQL 关键字 constraints)
ALTER TABLE skills ADD COLUMN output_format TEXT;      -- JSON
ALTER TABLE skills ADD COLUMN system_prompt TEXT;
ALTER TABLE skills ADD COLUMN few_shot_examples TEXT;  -- JSON array
ALTER TABLE skills ADD COLUMN success_metrics TEXT;    -- JSON
ALTER TABLE skills ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE skills ADD COLUMN avg_rating REAL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_skills_skill_type ON skills(skill_type);
