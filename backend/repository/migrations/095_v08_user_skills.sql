-- 095_v08_user_skills.sql
-- v0.8 Phase C C3: 用户自建 Skill (Skill Builder)
--
-- user_skills — 用户可视化创建的 skill (上限 50, 软删 + dry-run)
-- 字段契约与 builtin SkillDef 一一对齐 (R1):
--   - id: snake_case 用户自定义 (不允许与 builtin 20 冲突; loader 校验)
--   - skill_type: A/B/C/D (E 操作型 v0.8 不开放, P1-6)
--   - category: operations/compliance/analysis/report (与 builtin 同)
--   - runner: builtin (Phase C 用户 skill 仅支持 builtin runner; pi/claude-code/codex 留 v0.9+)
--   - input_schema/output_schema: JSON (key → Python type __name__ 字符串, 与 builtin 同)
--   - prompt_template: 仅 C/D 类必填 (R1 纪律 3)
--   - target_type: skill_step / api_call (用户 skill 仅支持 builtin 单 target, 不允许 pipeline 多步)
--   - target_module / target_class / target_method: 反射引用, loader importlib.find_spec 校验
--   - enabled: 0/1 软启用 (与 builtin 同, settings.kv 父 gate skill.<id>.enabled)
--   - deleted_at: 软删时间戳 (NULL = 活跃)
--   - audit: 创建者 / 最后修改者 (单用户工作站记 'user')

CREATE TABLE IF NOT EXISTS user_skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    desc TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL CHECK (category IN ('operations', 'compliance', 'analysis', 'report')),
    skill_type TEXT NOT NULL CHECK (skill_type IN ('A', 'B', 'C', 'D')),
    runner TEXT NOT NULL DEFAULT 'builtin' CHECK (runner IN ('builtin', 'pi', 'claude-code', 'codex')),
    timeout_seconds INTEGER NOT NULL DEFAULT 60 CHECK (timeout_seconds BETWEEN 1 AND 3600),
    input_schema_json TEXT NOT NULL DEFAULT '{}',
    output_schema_json TEXT NOT NULL DEFAULT '{}',
    prompt_template TEXT,
    target_type TEXT NOT NULL CHECK (target_type IN ('skill_step', 'api_call')),
    target_module TEXT NOT NULL,
    target_class TEXT,
    target_method TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    created_by TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    deleted_at TEXT
);

-- 用户查询: 列出活跃 (软删过滤)
CREATE INDEX IF NOT EXISTS idx_user_skills_active
    ON user_skills(category, skill_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_skills_enabled
    ON user_skills(enabled) WHERE deleted_at IS NULL;