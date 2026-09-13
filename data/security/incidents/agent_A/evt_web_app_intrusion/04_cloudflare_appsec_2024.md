---
source_url: https://blog.cloudflare.com/cloudflare-2024-appsec-security-report/
title: Cloudflare 2024 Application Security Report 要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2024-03-20
---

Cloudflare 2024 AppSec 报告统计: 全球流量中约 3% 为恶意利用尝试, 其中 web 攻击以 SQL 注入 (39%) 与 XSS、 路径遍历为主; 每 5 个 API 端点就有 1 个返回敏感数据未做鉴权 (BOLA)。报告观察到攻击者普遍先做目录爆破与指纹识别 (discovery), 再对暴露的管理后台尝试默认凭据与反序列化 exploit, 成功后部署 web shell 或挖矿程序 (impact)。建议全面启用 bot 管理、 API schema 校验与零信任访问。
