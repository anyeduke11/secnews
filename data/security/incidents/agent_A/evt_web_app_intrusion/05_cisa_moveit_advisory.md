---
source_url: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-131a
title: CISA Advisory — MOVEit Transfer SQL 注入批量利用事件摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2023-06-01
---

CISA 关于 Progress MOVEit Transfer 漏洞 (CVE-2023-34362) 的 advisory: 攻击者利用 SQL 注入在面向公众的文件传输服务上实现 RCE, 部署 web shell (human2.aspx) 获取 persistence, 枚举并批量下载企业客户数据 (collection + exfiltration), 涉及上千家组织的供应链式数据外泄。advisory 强调该事件展示了 exploit public-facing application 在 initial access 的破坏力, 建议立即修补、 审计异常 aspx 文件并轮换服务凭据。
