-- ============================================================================
-- 117_mp2_event_technique.sql — MP-2 安全事件类型实例化 (5 表 + 5 类 seed)
--
-- 背景
-- ----
-- MP-2 立项 (DEV-0215) 与设计稿定稿 (DEV-0214): 为 11 类安全事件类型 (8 通用 + 3 金融)
-- 建立结构化"典型技战法链"。LLM 抽取 → owner 人审落库。
--
-- 设计要点
-- --------
-- - 5 张表:
--     1) incident_reports        — 报告语料 (公开报告 + LLM 生成摘要)
--     2) event_technique_candidates — LLM 抽取候选池 (owner_status='pending')
--     3) event_technique_map     — owner 审定终态 (技战法链)
--     4) event_types             — 事件类型种子 (本 migration 只种 agent-A 5 类,
--                                   agent-B/C/D/E 各自 commit 自己 seed 的部分,
--                                   主会话 merge 顺序 A→B→C→D→E)
--     5) audit_log_mp2_review    — owner 人审审计链 (actor='owner'/'agent_A' 等)
--
-- - agent_owner 字段标识本 migration 由哪个 agent 提交 (主会话 merge 时按 A→E 顺序
--   依次应用, 保证 agent_owner 标识一致)
--
-- - 幂等: 所有 CREATE 用 IF NOT EXISTS; INSERT 用 OR IGNORE (按 entity_id / source_url /
--   UNIQUE 三元组判重)
--
-- - FK: 不引外键依赖 attack_techniques 表 (解耦 MP-1, service 层 enforce)
--
-- 本文件由 agent-A 提交, agent_owner='A', 5 类种子:
--   evt_ransomware / evt_phishing_social / evt_web_app_intrusion /
--   evt_supply_chain / evt_brute_force
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) incident_reports — 报告语料库 (含公开 URL 与 LLM 生成摘要)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident_reports (
    id TEXT PRIMARY KEY,                    -- ULID
    source_url TEXT NOT NULL,               -- 公开报告 URL 或 stable identifier
    title TEXT,                             -- 报告标题
    fetched_at TEXT NOT NULL,               -- ISO 8601
    report_date TEXT,                       -- 报告原始日期
    event_class_hint TEXT,                  -- 报告原始分类的初判 (LLM 不作终判)
    report_md TEXT NOT NULL,                -- 报告原文 (可截取关键段落 100~300 字)
    checksum TEXT NOT NULL,                 -- sha256 of report_md
    agent_owner TEXT NOT NULL DEFAULT 'A',  -- 哪个 agent 提交 (A/B/C/D/E)
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_url)
);
CREATE INDEX IF NOT EXISTS idx_ir_event_class ON incident_reports(event_class_hint);
CREATE INDEX IF NOT EXISTS idx_ir_agent_owner ON incident_reports(agent_owner);

-- ----------------------------------------------------------------------------
-- 2) event_technique_candidates — LLM 抽取候选池 (owner 审定前)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_technique_candidates (
    id TEXT PRIMARY KEY,                    -- ULID
    event_type_id TEXT NOT NULL,            -- security_entities.entity_id (event_type)
    technique_id TEXT NOT NULL,             -- ATT&CK Txxxx
    stage TEXT NOT NULL,                    -- initial_access / execution / ... (自由短串, 不强制 enum)
    confidence REAL NOT NULL,               -- 0.0~1.0 (<0.4 不入候选池)
    evidence_quote TEXT NOT NULL,           -- ≤120 字原文片段 (必须 source_report.report_md 子串)
    rationale TEXT,                         -- ≤80 字理由
    source_report_id TEXT NOT NULL,         -- incident_reports.id
    llm_model TEXT NOT NULL,                -- e.g. 'gpt-4o-mini' / 'mock-extract-v1'
    llm_run_at TEXT NOT NULL,
    owner_status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | edited | rejected
    owner_action_at TEXT,
    owner_action_by TEXT DEFAULT 'owner',
    reject_reason TEXT,
    auto_reject_reason TEXT,                -- 程序化校验失败原因
    agent_owner TEXT NOT NULL DEFAULT 'A',
    UNIQUE (event_type_id, technique_id, source_report_id)  -- 同源同位置只一条
);
CREATE INDEX IF NOT EXISTS idx_etc_event_type ON event_technique_candidates(event_type_id);
CREATE INDEX IF NOT EXISTS idx_etc_owner_status ON event_technique_candidates(owner_status);
CREATE INDEX IF NOT EXISTS idx_etc_technique ON event_technique_candidates(technique_id);
CREATE INDEX IF NOT EXISTS idx_etc_agent_owner ON event_technique_candidates(agent_owner);

-- ----------------------------------------------------------------------------
-- 3) event_technique_map — owner 审定终态 (技战法链 — 渲染用)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_technique_map (
    id TEXT PRIMARY KEY,                    -- ULID
    event_type_id TEXT NOT NULL,
    technique_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    note TEXT,                              -- owner 可编辑
    candidate_id TEXT,                      -- 追溯链: 来源 candidate
    source_report_id TEXT,                  -- 追溯链: 来源报告
    approved_at TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT 'owner',
    owner_audit_chain TEXT,                 -- JSON: [{ts, action, by, prev_status, note}]
    agent_owner TEXT NOT NULL DEFAULT 'A',
    UNIQUE (event_type_id, technique_id, stage)  -- 同 event_type 同 stage 同一 technique 只一条
);
CREATE INDEX IF NOT EXISTS idx_etm_event_type ON event_technique_map(event_type_id);
CREATE INDEX IF NOT EXISTS idx_etm_technique ON event_technique_map(technique_id);
CREATE INDEX IF NOT EXISTS idx_etm_agent_owner ON event_technique_map(agent_owner);

-- ----------------------------------------------------------------------------
-- 4) event_types — 事件类型种子 (agent-A 5 类)
-- ----------------------------------------------------------------------------
-- 本表为 security_entities 的 entity_type='event_type' 实体种子,
-- 5 agent 各自 commit 自己的部分, 主会话按 A→B→C→D→E 顺序 merge.
-- agent-A 仅种自己负责的 5 类, 避免冲突.
CREATE TABLE IF NOT EXISTS event_types (
    id TEXT PRIMARY KEY,                    -- evt_ransomware 等
    name_zh TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,                 -- general | financial
    agent_owner TEXT NOT NULL,              -- A | B | C | D | E
    priority TEXT NOT NULL,                 -- high | mid
    description TEXT NOT NULL,
    typical_signals TEXT NOT NULL,          -- JSON array
    kill_chain_stages TEXT NOT NULL,        -- JSON array
    report_source_pool TEXT NOT NULL,       -- JSON array
    status TEXT NOT NULL DEFAULT 'active',  -- active | deprecated
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_et_agent_owner ON event_types(agent_owner);
CREATE INDEX IF NOT EXISTS idx_et_category ON event_types(category);

-- 5 类种子 (agent-A 负责的 5 类高优先级通用事件类型)
-- 数据来源: data/security/event_types_seed.json (DEV-0216, owner 决议 2026-09-13)
-- OR IGNORE: 多 agent merge 时若已存在则跳过 (entity_id PK 已保证)
INSERT OR IGNORE INTO event_types (
    id, name_zh, name_en, category, agent_owner, priority,
    description, typical_signals, kill_chain_stages, report_source_pool,
    status, created_at, updated_at
) VALUES
(
    'evt_ransomware', '勒索软件', 'Ransomware', 'general', 'A', 'high',
    '通过加密/窃取数据索要赎金的攻击, 通常伴随双阶段勒索 (窃取+公开)',
    '["ransom","encrypt","lockbit","blackcat","cl0p","双重勒索","数据公开"]',
    '["Initial Access","Execution","Lateral Movement","Exfiltration","Impact"]',
    '["MITRE Case Studies G0050 (FIN6)","CrowdStrike 2024 Global Threat Report","Verizon DBIR 2024","CISA #StopRansomware advisories"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_phishing_social', '钓鱼社工', 'Phishing & Social Engineering', 'general', 'A', 'high',
    '通过邮件/IM/语音伪装身份诱导用户泄露凭据/执行恶意附件/转账',
    '["phishing","spear phishing","vishing","smishing","BEC","business email compromise","钓鱼","冒充"]',
    '["Reconnaissance","Resource Development","Initial Access","Credential Access"]',
    '["MITRE G0001 ( Axiom ) / G0046 (FIN7)","Anti-Phishing Working Group reports","Verizon DBIR social engineering section","FBI IC3 BEC reports"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_web_app_intrusion', 'Web 应用入侵', 'Web Application Intrusion', 'general', 'A', 'high',
    '针对 Web 应用漏洞 (注入/反序列化/越权/SSRF) 的入侵, 通常导致数据泄露或后门植入',
    '["sql injection","rce","ssrf","xxe","deserialization","auth bypass","IDOR","Web 入侵","SQL 注入","SSRF"]',
    '["Initial Access","Execution","Persistence","Collection","Exfiltration"]',
    '["OWASP Top 10 case studies","HackerOne disclosed reports","PortSwigger Web Security Academy","Cloudflare 2024 AppSec report"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_supply_chain', '供应链投毒', 'Supply Chain Compromise', 'general', 'A', 'high',
    '通过污染上游依赖 (代码包/构建工具/更新通道/供应商远程访问) 实现下游批量入侵',
    '["supply chain","dependency confusion","typosquatting","build compromise","update hijack","供应链","投毒","依赖混淆"]',
    '["Resource Development","Initial Access","Execution","Persistence"]',
    '["MITRE G0118 ( SolarWinds )","Sonatype State of Software Supply Chain 2024","ENISA Threat Landscape Supply Chain","XZ Utils backdoor (CVE-2024-3094) postmortems"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_brute_force', '暴力破解', 'Brute Force & Credential Stuffing', 'general', 'A', 'high',
    '针对凭据 (账号密码/口令/MFA bypass) 的规模化尝试, 包括字典/撞库/OTP 劫持',
    '["brute force","credential stuffing","password spray","MFA bypass","暴力破解","撞库","口令喷洒"]',
    '["Credential Access","Initial Access"]',
    '["Microsoft Digital Defense Report","Akamai State of the Internet Security","Shape AI Threat Report","F5 Labs credential stuffing"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
);

-- 同步 seed 到 security_entities (entity_type='event_type'), 供 API 层 list/get 透明
INSERT OR IGNORE INTO security_entities (
    id, entity_type, name, description, external_ref, metadata, created_at, updated_at
) VALUES
('evt_ransomware', 'event_type', '勒索软件',
    '通过加密/窃取数据索要赎金的攻击, 通常伴随双阶段勒索 (窃取+公开)',
    'mp2://event_types/evt_ransomware',
    json_object('name_en','Ransomware','category','general','agent_owner','A','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_phishing_social', 'event_type', '钓鱼社工',
    '通过邮件/IM/语音伪装身份诱导用户泄露凭据/执行恶意附件/转账',
    'mp2://event_types/evt_phishing_social',
    json_object('name_en','Phishing & Social Engineering','category','general','agent_owner','A','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_web_app_intrusion', 'event_type', 'Web 应用入侵',
    '针对 Web 应用漏洞 (注入/反序列化/越权/SSRF) 的入侵, 通常导致数据泄露或后门植入',
    'mp2://event_types/evt_web_app_intrusion',
    json_object('name_en','Web Application Intrusion','category','general','agent_owner','A','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_supply_chain', 'event_type', '供应链投毒',
    '通过污染上游依赖 (代码包/构建工具/更新通道/供应商远程访问) 实现下游批量入侵',
    'mp2://event_types/evt_supply_chain',
    json_object('name_en','Supply Chain Compromise','category','general','agent_owner','A','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_brute_force', 'event_type', '暴力破解',
    '针对凭据 (账号密码/口令/MFA bypass) 的规模化尝试, 包括字典/撞库/OTP 劫持',
    'mp2://event_types/evt_brute_force',
    json_object('name_en','Brute Force & Credential Stuffing','category','general','agent_owner','A','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- ----------------------------------------------------------------------------
-- 5) audit_log_mp2_review — owner 人审审计 (独立表, 不复用 audit_log 以免污染)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log_mp2_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,                    -- 'owner' / 'agent_A' 等
    action TEXT NOT NULL,                   -- 'approve' / 'reject' / 'edit' / 'batch_approve'
    target_type TEXT NOT NULL,              -- 'event_technique_candidate' / 'event_technique_map'
    target_id TEXT NOT NULL,                -- candidate_id 或 map_id
    event_type_id TEXT,                     -- 关联 event_types.id (便于按类审计)
    detail TEXT,                            -- JSON: 变更前后 / 拒绝原因 / 批量统计
    trace_id TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log_mp2_review(actor);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log_mp2_review(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log_mp2_review(event_type_id);
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_log_mp2_review(occurred_at);
