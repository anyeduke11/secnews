-- 018_knowledge.sql: v1.4 Phase 1a knowledge tables

-- 知识条目索引 (镜像 knowledge/items/*.md)
CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    domain TEXT,
    topic TEXT,
    type TEXT,
    difficulty TEXT,
    tags TEXT,
    concepts TEXT,
    mastery INTEGER DEFAULT 0,
    compiled INTEGER DEFAULT 0,
    ingested_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 概念索引 (镜像 knowledge/concepts/*.md)
CREATE TABLE IF NOT EXISTS knowledge_concepts (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT,
    source_items TEXT,
    local_wiki_ref TEXT,
    updated_at TEXT NOT NULL
);

-- 知识图谱缓存
CREATE TABLE IF NOT EXISTS knowledge_graph (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 学习计划
CREATE TABLE IF NOT EXISTS knowledge_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    plan_data TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 学习进度
CREATE TABLE IF NOT EXISTS knowledge_progress (
    concept_slug TEXT PRIMARY KEY,
    mastery INTEGER DEFAULT 0,
    last_tested TEXT,
    test_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- 创作日历
CREATE TABLE IF NOT EXISTS content_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    topic TEXT NOT NULL,
    type TEXT,
    status TEXT DEFAULT 'planned',
    source_items TEXT,
    draft_path TEXT,
    platform TEXT,
    published_url TEXT,
    stats TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 创作草稿
CREATE TABLE IF NOT EXISTS content_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    calendar_id INTEGER REFERENCES content_calendar(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 任务队列
CREATE TABLE IF NOT EXISTS knowledge_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    params TEXT,
    result_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Skill 配置 (LLM 模型绑定)
CREATE TABLE IF NOT EXISTS knowledge_skill_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL UNIQUE,
    secret_id INTEGER REFERENCES secrets(id),
    model_override TEXT,
    prompt_template TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
