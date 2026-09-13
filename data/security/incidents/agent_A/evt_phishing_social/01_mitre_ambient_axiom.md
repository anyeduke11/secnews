---
source_url: https://attack.mitre.org/groups/G0001/
title: MITRE ATT&CK G0001 (Axiom) 案例研究摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2019-07-01
---

MITRE ATT&CK G0001 Axiom 案例记录: 该组织长期针对媒体与工程机构实施间谍活动。初始访问以 spear phishing 邮件携带恶意附件为主, 收件人打开后用户执行伪装成文档的 dropper, 建立持久化计划任务; 通过伪造登录页与键盘记录窃取 valid credentials (credential access), 再用窃取凭据登录 webmail 与 VPN 扩大访问。Axiom 大量使用公开工具 (Poison Ivy RAT) 与编码 payload 规避检测, 是 spearphishing attachment 手法的经典教材。
