-- 137_drop_four_domains.sql — 四域整体删除 (工坊 / 技能库 / 密钥 / 同步)
-- 2026-11-19, owner 裁决「真·全删」: 四域前后端 + 接口 + service + gate + 表全删。
--
-- 本迁移按 append-only 纪律追加 DROP TABLE (历史迁移文件一律保留不动)。
--
-- 覆盖四组表:
--   1. 工坊 (CodeGarden)     — cg_projects / cg_project_* / cg_dependencies /
--                              cg_resources / cg_services / cg_events / cg_drift_assessments
--   2. 技能库 (skills)       — skills / skill_runs / user_skills / knowledge_skill_config
--   3. 密钥 (secrets)        — llm_secrets / secret_access_logs / encryption_keys
--   4. 同步 (sync)           — sync_configs / sync_history / sync_states
--   + 随技能域内部运行时退役的孤儿表 (worker / loop / feedback / playbook / trigger):
--      worker_runs / dead_letter / loop_checkpoints / feedback_log /
--      agent_preferences / playbook_runs / playbook_schedules / trigger_tickets
--
-- FK 处置 (依 126_foreign_keys_off_note.sql 规约 + 112_remove_bid_data 先例):
--   连接级 PRAGMA foreign_keys=ON 时, DROP 被引用父表会触发子表 ON DELETE CASCADE,
--   把销毁范围扩散到计划外。本脚本首尾成对关闭/恢复 FK, 阻断级联扩散。
--   注: encryption_keys 是 llm_secrets 的 FK 父表 — 两者同批删除, 顺序无关。
--   trigger_tickets 被 llm_secrets 之外的 legacy_hold 链路引用, 该链路已随
--   技能域退役, 一并删除。
--
-- 幂等: 全部 DROP ... IF EXISTS; 已删除的库重跑本脚本无副作用。

PRAGMA foreign_keys = OFF;

-- ── 1. 工坊域 (CodeGarden) ──────────────────────────────────────────
DROP TABLE IF EXISTS cg_project_activities;
DROP TABLE IF EXISTS cg_project_links;
DROP TABLE IF EXISTS cg_project_stages;
DROP TABLE IF EXISTS cg_dependencies;
DROP TABLE IF EXISTS cg_resources;
DROP TABLE IF EXISTS cg_services;
DROP TABLE IF EXISTS cg_events;
DROP TABLE IF EXISTS cg_drift_assessments;
DROP TABLE IF EXISTS cg_projects;

-- ── 2. 技能库域 (skills / skill_registry / skill_builder) ──────────
DROP TABLE IF EXISTS knowledge_skill_config;
DROP TABLE IF EXISTS user_skills;
DROP TABLE IF EXISTS skill_runs;
DROP TABLE IF EXISTS skills;

-- ── 3. 密钥域 (secrets / llm_secrets / master key) ─────────────────
DROP TABLE IF EXISTS secret_access_logs;
DROP TABLE IF EXISTS llm_secrets;
DROP TABLE IF EXISTS encryption_keys;

-- ── 4. 同步域 (sync) ───────────────────────────────────────────────
DROP TABLE IF EXISTS sync_history;
DROP TABLE IF EXISTS sync_states;
DROP TABLE IF EXISTS sync_configs;

-- ── 5. 技能域内部运行时孤儿表 (worker / loop / feedback / playbook / trigger) ──
DROP TABLE IF EXISTS dead_letter;
DROP TABLE IF EXISTS worker_runs;
DROP TABLE IF EXISTS loop_checkpoints;
DROP TABLE IF EXISTS feedback_log;
DROP TABLE IF EXISTS agent_preferences;
DROP TABLE IF EXISTS playbook_runs;
DROP TABLE IF EXISTS playbook_schedules;
DROP TABLE IF EXISTS trigger_tickets;

-- ── 6. 存量告警规则: tech_stack_cve 数据源随工坊域消失 ────────────────
-- 048 种子规则 tech_stack_cve 读取 cg_projects.tech_stack; 该表已 DROP, 规则永久失效。
-- append-only: 不删历史规则行, 仅置 enabled=0 使其退出评估 (AlertEngine._load_rules 只取 enabled=1)。
UPDATE alert_rule_definitions SET enabled = 0 WHERE rule_type = 'tech_stack_cve';

PRAGMA foreign_keys = ON;
