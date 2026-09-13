---
source_url: https://attack.mitre.org/groups/G0118/
title: MITRE ATT&CK G0118 (UNC2452 / SolarWinds 事件) 摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2021-04-15
---

MITRE ATT&CK 关于 SolarWinds 事件的案例记录: 攻击者在 resource development 阶段入侵 Orion 构建系统, 通过 SUNBURST 后门化的签名更新实现软件供应链 compromise, 下游约 18000 客户自动安装植入; 植入随后选择性激活, 滥用合法 SAML token 伪造黄金票据访问目标云邮箱 (credential access + collection), 数据经 Mimikatz 提取凭据后分批外传。事件定义了现代供应链攻击的范式: 构建管道污染 + 信标激活 + 云身份滥用。
