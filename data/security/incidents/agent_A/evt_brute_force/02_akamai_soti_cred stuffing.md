---
source_url: https://www.akamai.com/security-research/the-state-of-the-internet
title: Akamai State of the Internet — Credential Stuffing 要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2024-04-10
---

Akamai SOTI 报告统计: 零售与金融 API 流量中 credential stuffing 攻击占比超过 35%, 攻击者用 combolist (数十亿泄露凭据对) 通过自动化脚本撞库, 以 0.1%~1% 的命中率规模化获利; 成功登录后立即执行 gift card 转移或数据遍历 (impact + collection)。报告观察到攻击者使用住宅代理轮换 IP (defense evasion) 绕过速率限制。建议按设备指纹与行为生物特征识别自动化登录, 而非单纯 IP 限速。
