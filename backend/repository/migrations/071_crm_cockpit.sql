-- ============================================================================
-- 071_crm_cockpit.sql — CRM 业绩座舱 (security-cockpit 方案 C 完整移植)
--
-- 背景
-- ----
-- docs/P2_6_COCKPIT_EVAL.md 方案 C 落地: 把 security-cockpit/ 静态设计稿
-- 移植为 hotspot 增值扩展模块 (feature gate `crm`)。
-- 业务域与资讯聚合正交: 客户 / 商机 / 业绩 KPI。
-- 口径与状态机定义见 docs/COCKPIT_PRD.md。
--
-- 设计要点
-- --------
-- - crm_customers: 客户主档 (行业/等级/区域 用于座舱分布图)
-- - crm_opportunities: 商机六态状态机 (PRD §2), cost 字段支撑毛利率
-- - crm_opportunity_events: 阶段迁移留痕 (审计 + 复盘)
-- - 金额单位统一为元 (REAL); 日期为 ISO-8601 TEXT; 时间 UTC isoformat
-- ============================================================================

CREATE TABLE IF NOT EXISTS crm_customers (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT    NOT NULL UNIQUE,               -- 客户名称 (唯一)
    industry             TEXT    NOT NULL DEFAULT '其他',        -- 银行/证券/保险/政府/互联网/能源/医疗/其他
    level                TEXT    NOT NULL DEFAULT 'B',           -- S/A/B/C
    status               TEXT    NOT NULL DEFAULT '活跃',        -- 活跃/续约中/停滞/流失
    region               TEXT    NOT NULL DEFAULT '华东',        -- 区域营收分布维度
    owner                TEXT    NOT NULL DEFAULT '',            -- 负责人
    contact_name         TEXT    NOT NULL DEFAULT '',
    contact_phone        TEXT    NOT NULL DEFAULT '',
    email                TEXT    NOT NULL DEFAULT '',
    contract_start_date  TEXT,                                   -- ISO date
    contract_end_date    TEXT,
    contract_amount      REAL    NOT NULL DEFAULT 0,             -- 元
    nps_score            INTEGER,                                -- 0-10 可空 (NPS KPI 输入)
    notes                TEXT    NOT NULL DEFAULT '',
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_customers_status   ON crm_customers(status);
CREATE INDEX IF NOT EXISTS idx_crm_customers_industry ON crm_customers(industry);

CREATE TABLE IF NOT EXISTS crm_opportunities (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id          INTEGER NOT NULL REFERENCES crm_customers(id) ON DELETE CASCADE,
    name                 TEXT    NOT NULL,
    service_type         TEXT    NOT NULL DEFAULT '安全评估',
    stage                TEXT    NOT NULL DEFAULT '需求沟通',    -- 需求沟通/方案提交/商务谈判/合同签订/赢单/输单
    amount               REAL    NOT NULL DEFAULT 0,             -- 元
    cost                 REAL    NOT NULL DEFAULT 0,             -- 元 (毛利率分母)
    owner                TEXT    NOT NULL DEFAULT '',
    expected_close_date  TEXT,
    description          TEXT    NOT NULL DEFAULT '',
    won_at               TEXT,                                   -- 进入赢单时刻
    lost_reason          TEXT    NOT NULL DEFAULT '',            -- 输单原因
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_opps_customer ON crm_opportunities(customer_id);
CREATE INDEX IF NOT EXISTS idx_crm_opps_stage    ON crm_opportunities(stage);

CREATE TABLE IF NOT EXISTS crm_opportunity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id  INTEGER NOT NULL REFERENCES crm_opportunities(id) ON DELETE CASCADE,
    from_stage      TEXT,                                   -- NULL = 创建
    to_stage        TEXT    NOT NULL,
    note            TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crm_events_opp ON crm_opportunity_events(opportunity_id, created_at);
