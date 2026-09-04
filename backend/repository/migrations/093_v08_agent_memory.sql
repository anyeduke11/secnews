-- 093_v08_agent_memory.sql
-- v0.8 B3: HITL 反馈 → 偏好挖掘 → 下次执行注入, A→J 闭环
--
-- 两张表配合 backend/services/agent_memory/ 包工作:
--
-- 1. feedback_log — 用户对某次 skill run 的 HITL 反馈
--    record_feedback 时校验 skill_run_id 必须存在于 skill_runs
--    (不存在抛 ValueError), score 1-5 整数。是 recall 评分与
--    prefer_style 偏好挖掘 (score≥4 ×3) 的数据源。
--
-- 2. agent_preferences — 偏好挖掘产物 (PreferenceMiner 规则触发后 upsert)
--    - kind=avoid_skill:  同 skill_id 失败 ≥3 次 → value=skill_id
--    - kind=prefer_runner: 同 runner 成功 ≥5 次 → value=runner 名
--    - kind=prefer_style:  同 skill 反馈 score≥4 ×3 次 → value=关键词摘要
--    evidence 存 JSON 触发证据摘要; UNIQUE(kind, value) 保证幂等
--    (重复 mine 跳过已存在行)。下次执行时由 active_preferences() 注入。

CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_run_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 按 run 维度查反馈 (recall join score) / 按 skill 维度倒序拉反馈历史
CREATE INDEX IF NOT EXISTS idx_feedback_run
    ON feedback_log(skill_run_id);
CREATE INDEX IF NOT EXISTS idx_feedback_skill
    ON feedback_log(skill_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('avoid_skill', 'prefer_runner', 'prefer_style')),
    value TEXT NOT NULL,
    evidence TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(kind, value)
);
