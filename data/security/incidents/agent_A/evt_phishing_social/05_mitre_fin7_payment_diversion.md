---
source_url: https://attack.mitre.org/groups/G0046/
title: MITRE ATT&CK G0046 (FIN7) 案例研究摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2021-11-10
---

MITRE ATT&CK G0046 FIN7 案例记录: 该组织以餐饮零售 POS 为主要目标, 后扩展至勒索与支付 diverted fraud。初始访问依赖针对性钓鱼邮件, 附件为带宏的 Word 文档诱导用户执行 macro-enabled payload; 通过计划任务与注册表 run key 持久化, 使用公开渗透测试框架进行内网侦察与横向移动, 最终窃取卡数据或实施支付诈骗。FIN7 的工具链 (HalfOpenScanner、 BOOSTWRITE) 展示了钓鱼起点的完整攻击工业化路径。
