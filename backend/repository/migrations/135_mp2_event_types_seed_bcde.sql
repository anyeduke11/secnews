-- ============================================================================
-- 135_mp2_event_types_seed_bcde.sql — MP-2 事件类型种子补齐 (agent-B/C/D/E 6 类)
--
-- 背景
-- ----
-- 117_mp2_event_technique.sql 只种了 agent-A 负责的 5 类通用事件类型;
-- 设计词表 data/security/event_types_seed.json 明确要求 11 类 (8 通用 + 3 金融)。
-- 本 migration 补齐余下 6 类:
--   agent-B: evt_insider_threat / evt_cloud_misconfig / evt_ai_model_poison (general, mid)
--   agent-C: evt_fraud (financial, high)
--   agent-D: evt_data_breach (financial, high)
--   agent-E: evt_regulatory_notice (financial, high)
--
-- 数据来源: data/security/event_types_seed.json (DEV-0216, owner 决议 2026-09-13)
-- 幂等: INSERT OR IGNORE (按 event_types.id PK / security_entities.id PK 判重)
-- 字段语义与 117 完全一致, 不新增列/表。
--
-- 验收: 11 类全部 seed 后, /api/security/entities?entity_type=event_type 返 11 行。
-- ============================================================================

INSERT OR IGNORE INTO event_types (
    id, name_zh, name_en, category, agent_owner, priority,
    description, typical_signals, kill_chain_stages, report_source_pool,
    status, created_at, updated_at
) VALUES
(
    'evt_insider_threat', '内部威胁', 'Insider Threat', 'general', 'B', 'mid',
    '拥有合法权限的内部人员 (员工/合同方/离职未撤权) 的滥用或无意泄露',
    '["insider","malicious insider","data exfil by employee","离职未撤权","内部威胁","数据外发"]',
    '["Collection","Exfiltration","Impact"]',
    '["CERT Insider Threat Center","Ponemon Cost of Insider Threats","MITRE G0007 ( Hidden Lynx ) / G0009 ( Deep Panda )","Dtex 2024 Insider Risk Report"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_cloud_misconfig', '云配置泄露', 'Cloud Misconfiguration Exposure', 'general', 'B', 'mid',
    '云上存储/计算/网络/IAM 因配置错误导致的公开暴露或越权访问, 通常非主动攻击',
    '["S3 bucket public","blob exposed","IAM wildcard","security group open","云存储公开","IAM 越权","kubeconfig 暴露"]',
    '["Reconnaissance","Initial Access","Collection"]',
    '["AWS Security Bulletins","Wiz Cloud Security Reports","Palo Alto Unit 42 cloud threat reports","Netskope Cloud Threat Report"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_ai_model_poison', 'AI 模型投毒', 'AI/ML Model Poisoning', 'general', 'B', 'mid',
    '针对 AI/ML 模型供应链 (训练数据/权重/微调/推理 prompt) 的污染、投毒或越狱, 含 LLM 提示注入',
    '["data poisoning","model poisoning","backdoor attack","prompt injection","jailbreak","模型投毒","提示注入","越狱"]',
    '["Resource Development","Initial Access","Defense Evasion","Impact"]',
    '["MITRE ATLAS (Adversarial Threat Landscape for AI Systems)","OWASP LLM Top 10","NIST AI 100-2 Adversarial ML","Microsoft AI Bug Bounty reports"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_fraud', '反诈 (金融行业特有)', 'Financial Fraud & Scams', 'financial', 'C', 'high',
    '针对金融客户的诈骗: 杀猪盘/虚假投资/冒充客服/虚假贷款/信用卡盗刷/账户接管 (ATO), 强调受害者侧链路而非系统侧',
    '["杀猪盘","虚假投资","冒充客服","虚假贷款","信用卡盗刷","ATO","account takeover","romance scam","pig butchering","pig-butchering","investment scam","技术支持诈骗"]',
    '["Reconnaissance","Resource Development","Initial Access (受害者)","Credential Access","Impact (财务损失)"]',
    '["央行支付结算司通报","中国银行业协会反诈报告","银保监反诈通报","FBI IC3 Elder Fraud & Romance","Interpol Financial Crimes","Chainalysis Crypto Crime Report","FATF 指引: 虚拟资产/VASP 反洗钱与反诈骗 (2021/2023)","GB/T 35273-2020 信息安全技术 个人信息安全规范","JR/T 0051.1/2 金融行业信息安全等级保护实施指引","银联/网联反欺诈规则白皮书与风控年报","巴塞尔协议 III Operatinal risk / 金融犯罪风险指引"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_data_breach', '数据泄露 (金融行业特有)', 'Data Breach (incl. PII Flow)', 'financial', 'D', 'high',
    '客户 PII/账户/交易数据/内部敏感数据的外泄、倒卖或公开, 含员工批量查询与第三方共享失控',
    '["data breach","data leak","PII exposure","员工批量查询","第三方共享失控","客户数据泄露","拖库","撞库拖库"]',
    '["Collection","Exfiltration","Impact (合规/声誉)"]',
    '["央行/银保监数据安全通报","网信办违法违规处置公告","Verizon DBIR data breach section","Have I Been Pwned postmortems","Privacy Affairs breach reports","ISO 27035 信息安全事件管理 (数据泄露响应)","ISO 29100 隐私框架 (PII 处理与泄露通知)","GB/T 20984-2022 信息安全技术 信息安全事件分类分级指南","PCI DSS v4.0 数据泄露响应与 PAN 泄露处置","NIST CSF 2.0 Detect/Respond 事件响应流程"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
),
(
    'evt_regulatory_notice', '监管通报 (金融行业特有)', 'Regulatory Notice / Enforcement', 'financial', 'E', 'high',
    '人民银行/银保监/网信办/证监会/公安网安/工信部等监管口径下发的通报、罚单、风险提示、合规整改要求',
    '["监管通报","风险提示","行政处罚","合规整改","约谈","通报批评","regulatory notice","enforcement action","PBOC notice","NFRA notice","CAC notice"]',
    '["Impact (合规/制度)","Recovery (整改)"]',
    '["中国人民银行公告 (支付结算司/金融稳定局)","国家金融监督管理总局 (NFRA) 通报","中央网信办 (CAC) 通报","中国证监会处罚决定","公安部网安局通报","工信部网安局通报","FATF 互评估报告 (中国/香港/新加坡等司法管辖区)","巴塞尔协议 III / IOSCO 合规监管与处罚案例库","GB/T 22239-2019 信息安全技术 网络安全等级保护基本要求 (等保 2.0)","JR/T 金融行业系列标准 (数据安全/网络安全/信息系统灾难恢复)","IMF 金融稳定报告 (FSB Crypto/Fintech 风险通报)"]',
    'active', strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')
);

-- 同步 seed 到 security_entities (entity_type='event_type'), 供 API 层 list/get 透明
INSERT OR IGNORE INTO security_entities (
    id, entity_type, name, description, external_ref, metadata, created_at, updated_at
) VALUES
('evt_insider_threat', 'event_type', '内部威胁',
    '拥有合法权限的内部人员 (员工/合同方/离职未撤权) 的滥用或无意泄露',
    'mp2://event_types/evt_insider_threat',
    json_object('name_en','Insider Threat','category','general','agent_owner','B','priority','mid'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_cloud_misconfig', 'event_type', '云配置泄露',
    '云上存储/计算/网络/IAM 因配置错误导致的公开暴露或越权访问, 通常非主动攻击',
    'mp2://event_types/evt_cloud_misconfig',
    json_object('name_en','Cloud Misconfiguration Exposure','category','general','agent_owner','B','priority','mid'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_ai_model_poison', 'event_type', 'AI 模型投毒',
    '针对 AI/ML 模型供应链 (训练数据/权重/微调/推理 prompt) 的污染、投毒或越狱, 含 LLM 提示注入',
    'mp2://event_types/evt_ai_model_poison',
    json_object('name_en','AI/ML Model Poisoning','category','general','agent_owner','B','priority','mid'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_fraud', 'event_type', '反诈 (金融行业特有)',
    '针对金融客户的诈骗: 杀猪盘/虚假投资/冒充客服/虚假贷款/信用卡盗刷/账户接管 (ATO), 强调受害者侧链路而非系统侧',
    'mp2://event_types/evt_fraud',
    json_object('name_en','Financial Fraud & Scams','category','financial','agent_owner','C','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_data_breach', 'event_type', '数据泄露 (金融行业特有)',
    '客户 PII/账户/交易数据/内部敏感数据的外泄、倒卖或公开, 含员工批量查询与第三方共享失控',
    'mp2://event_types/evt_data_breach',
    json_object('name_en','Data Breach (incl. PII Flow)','category','financial','agent_owner','D','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
('evt_regulatory_notice', 'event_type', '监管通报 (金融行业特有)',
    '人民银行/银保监/网信办/证监会/公安网安/工信部等监管口径下发的通报、罚单、风险提示、合规整改要求',
    'mp2://event_types/evt_regulatory_notice',
    json_object('name_en','Regulatory Notice / Enforcement','category','financial','agent_owner','E','priority','high'),
    strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));