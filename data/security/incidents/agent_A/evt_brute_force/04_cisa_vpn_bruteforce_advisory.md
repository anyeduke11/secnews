---
source_url: https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a
title: CISA Advisory — MFA 爆破绕过与 VPN 暴力破解事件要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2024-02-07
---

CISA 与合作机构 advisory 描述: 攻击者对未打补丁的 Fortinet/F5/Pulse VPN 设备实施凭据爆破, 并利用 MFA 爆破 (push fatigue) 或旧会话 cookie 复放绕过多因子认证, 获得初始访问后以 valid accounts 在内网注册持久化设备、 枚举 AD 并部署勒索载荷。advisory 列出 indicators: 大量来自 VPS 的登录失败、 同账号多地 OTP 推送。建议强制证书式 VPN 认证、 限速与 MFA 号码匹配。
