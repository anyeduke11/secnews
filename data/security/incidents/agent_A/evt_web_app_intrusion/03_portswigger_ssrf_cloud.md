---
source_url: https://portswigger.net/web-security/ssrf
title: PortSwigger Web Security — SSRF 到云凭据窃取案例要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2023-03-01
---

PortSwigger SSRF 教学与案例集合说明: 当应用存在 SSRF 且部署在云上时, 攻击者可让服务器请求 metadata 服务 (如 169.254.169.254) 获取临时 IAM 凭据, 再以 valid cloud accounts 登录对象存储拖取敏感桶, 完成从 Web 漏洞到云资源接管的完整链。防御建议: 出网白名单、 metadata v2 强制 token、 阻止非常见端口回连。案例覆盖 SSRF→credential access→collection→exfiltration 全阶段。
