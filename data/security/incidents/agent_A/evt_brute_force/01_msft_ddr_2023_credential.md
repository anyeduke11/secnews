---
source_url: https://www.microsoft.com/en-us/security/blog/2023/10/25/microsoft-digital-defense-report-2023/
title: Microsoft Digital Defense Report 2023 — credential attack 章节要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2023-10-25
---

Microsoft 数字防御报告凭据章节: 每秒遭到超过 4000 次凭据攻击, password spray 与 credential stuffing 占绝对多数。攻击者通过 recon 锁定暴露的 OWA、 VPN 与 RDP 端点, 用泄露密码字典低速喷洒规避锁定 (defense evasion), 成功后注册自控 MFA 设备完成账户接管; 对无 MFA 环境则直接以 valid accounts 登录云控制台枚举数据 (discovery + collection)。建议全面启用 phishing-resistant MFA 与智能锁定策略。
