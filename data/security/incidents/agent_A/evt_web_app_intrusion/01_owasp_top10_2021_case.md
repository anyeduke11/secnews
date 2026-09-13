---
source_url: https://owasp.org/Top10/
title: OWASP Top 10 2021 — Injection/Broken Access Control 案例要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2021-09-24
---

OWASP Top 10 (2021) 以真实漏洞统计为依据: Broken Access Control 与 Injection (含 SQL 注入) 连年位居前列。典型案例模式: 应用未校验输入导致 SQL 注入拖库 (数据外传), 或 IDOR 越权遍历他人订单; 反序列化漏洞让攻击者上传恶意对象实现 RCE (execution); SSRF 让攻击者访问云元数据端点窃取 IAM 临时凭据进而接管云资源。OWASP 建议以参数化查询、集中式鉴权与依赖 SBOM 作为基础防线。
