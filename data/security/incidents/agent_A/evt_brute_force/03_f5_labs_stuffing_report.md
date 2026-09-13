---
source_url: https://www.f5.com/labs/reports
title: F5 Labs Credential Stuffing Campaign 报告要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2021-08-17
---

F5 Labs 撞库报告分析一次持续 21 天的大型 stuffing 活动: 攻击者将 13 亿凭据对按 50~100 rps 均匀投放到目标登录端点, 避免触发告警; 响应差异分析显示 0.52% 登录成功, 随后对成功账户执行订单查询与积分转移。报告详细拆解了工具链 (Sentry MBA 类脚本) 与 defense evasion 手法 — UA 轮换、 代理池与验证码众包。建议对登录失败实施自适应挑战与账户孤儿检测。
