---
source_url: https://attack.mitre.org/groups/G0050/
title: MITRE ATT&CK G0050 (FIN6) 案例研究摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2020-08-10
---

MITRE ATT&CK G0050 FIN6 案例记录: 该组织早期针对 POS 系统窃取支付卡数据, 后转向大规模 ransomware 部署 (Ryuk/Maze/Triumphant Dachshund)。入侵链: 通过钓鱼获取凭据或利用 RDP 伪造 valid accounts, 使用 PowerShell 与 WMIC 执行编码命令, 利用 AdFind 与 net 命令进行域侦察, 通过 WMI 与 psexec 横向, 建立计划任务持久化, 部署前清理卷影副本, 最终 Ryuk 加密关键服务器。案例展示了 IAB 转租与多阶段 extortion 产业化。
