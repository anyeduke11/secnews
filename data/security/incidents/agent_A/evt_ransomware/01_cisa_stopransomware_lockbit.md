---
source_url: https://www.cisa.gov/stopransomware/lockbit
title: CISA #StopRansomware: LockBit 2.0 勒索软件 advisory 摘要
fetched_at: 2026-09-13T04:00:00Z
report_date: 2022-02-04
---

FBI 与 CISA 联合发布 LockBit 2.0 勒索软件 advisory。该组织通过 RDP 与 VPN 凭据爆破获取初始访问, 随后利用 PowerSploit、 Mimikatz 进行凭据提取与内网侦察, 通过 SMB 与 RDP 横向移动至域控, 部署 GPO 批量加密前先删除卷影副本 (vssadmin delete shadows) 阻断恢复, 最后窃取敏感数据实施双重勒索并在泄露站点公开不付款受害者数据。advisory 强调备份离线化与 MFA 是最有效的初始访问阻断手段。
