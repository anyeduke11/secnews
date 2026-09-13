---
source_url: https://hackerone.com/hacktivity
title: HackerOne 公开披露 — SQL Injection RCE 复合漏洞报告要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2023-06-15
---

HackerOne 公开披露案例: 研究者在某 SaaS 应用的搜索接口发现 SQL 注入, 利用 UNION 查询确认数据库结构后, 借助堆叠查询写入 web shell 实现远程代码执行, 随后枚举文件系统发现数据库凭据配置并横向至内网数据库。整个链路覆盖 initial access (exploit public-facing application) → execution (web shell) → persistence (webshell 落地) → collection (拖取用户表) → exfiltration (经 HTTPS 外传)。厂商修复采纳参数化查询与 WAF 规则加固。
