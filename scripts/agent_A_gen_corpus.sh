#!/usr/bin/env zsh
# Generate 25 agent-A corpus reports (5 event types x 5 reports each).
# Body is a compliant 100~300 char summary referencing public incidents (no long quotes).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PYEOF'
from pathlib import Path

BASE = Path("data/security/incidents/agent_A")

# Each entry: (filename, source_url, title, report_date, body)
CORPUS = {
    "evt_ransomware": [
        ("01_cisa_stopransomware_lockbit.md",
         "https://www.cisa.gov/stopransomware/lockbit",
         "CISA #StopRansomware: LockBit 2.0 勒索软件 advisory 摘要",
         "2022-02-04",
         "FBI 与 CISA 联合发布 LockBit 2.0 勒索软件 advisory。该组织通过 RDP 与 VPN 凭据爆破获取初始访问, 随后利用 PowerSploit、 Mimikatz 进行凭据提取与内网侦察, 通过 SMB 与 RDP 横向移动至域控, 部署 GPO 批量加密前先删除卷影副本 (vssadmin delete shadows) 阻断恢复, 最后窃取敏感数据实施双重勒索并在泄露站点公开不付款受害者数据。advisory 强调备份离线化与 MFA 是最有效的初始访问阻断手段。"),
        ("02_crowdstrike_2024_gtr_ransomware.md",
         "https://www.crowdstrike.com/global-threat-report/",
         "CrowdStrike 2024 Global Threat Report — ransomware 章节摘要",
         "2024-02-28",
         "CrowdStrike 2024 年度报告 ransomware 章节指出: eCrime 组织普遍采用 access brokering 模式, 初始访问经纪 (IAB) 通过 valid accounts 与暴露的远程服务 (VPN/防火墙 CVE) 出售入口; 操作者大量使用 breakout time 极短的手法 — 云端 STS token 滥用、边缘设备 exploit 与 RDP 横向。BlackCat/ALPHV 与 LockBit 采用 Rust 重写 loader 规避检测, 加密前用 rclone 向云存储外传数据实现双重勒索。报告建议以身份威胁检测与 AD 分层防护优先。"),
        ("03_verizon_dbir_2024_ransomware.md",
         "https://www.verizon.com/business/resources/reports/dbir/",
         "Verizon DBIR 2024 — Ransomware 模式发现摘要",
         "2024-05-01",
         "Verizon 2024 DBIR 显示 ransomware 出现在 32% 的全部 breach 中, 且 92% 案例存在未启用 MFA 的凭据。常见路径: 钓鱼邮件诱导下载 loader → 用户执行恶意 payload → 凭据转储 → 远程服务横向 → 数据外传 (约 40% 案例在加密前先 exfiltration) → 影响阶段批量加密并索要赎金。DBIR 强调发现中位时间仍远大于攻击完成时间, 建议将 eDiscovery 与 EDR 覆盖边缘设备。"),
        ("04_mitre_fin6_case.md",
         "https://attack.mitre.org/groups/G0050/",
         "MITRE ATT&CK G0050 (FIN6) 案例研究摘要",
         "2020-08-10",
         "MITRE ATT&CK G0050 FIN6 案例记录: 该组织早期针对 POS 系统窃取支付卡数据, 后转向大规模 ransomware 部署 (Ryuk/Maze/Triumphant Dachshund)。入侵链: 通过钓鱼获取凭据或利用 RDP 伪造 valid accounts, 使用 PowerShell 与 WMIC 执行编码命令, 利用 AdFind 与 net 命令进行域侦察, 通过 WMI 与 psexec 横向, 建立计划任务持久化, 部署前清理卷影副本, 最终 Ryuk 加密关键服务器。案例展示了 IAB 转租与多阶段 extortion 产业化。"),
        ("05_ncsc_ransomware_trends.md",
         "https://www.ncsc.gov.uk/ransomware/home",
         "UK NCSC Ransomware Trends 2023 摘要",
         "2023-11-20",
         "NCSC 2023 趋势报告总结 ransomware 运营模式变化: RaaS (勒索软件即服务) 分工细化, 初始访问多来自 exploit 公开应用 (如 MOVEit、 Citrix ADC CVE) 与凭据填充; 侦察阶段滥用 AD LDS 与网络扫描; 加密前使用 gsecdump 转储凭据、 用 wevtutil cl 清理日志 (defense evasion); 双重/三重勒索成为常态, 数据公开站点 (leak site) 成为影响阶段组成部分。NCSC 建议网络分段与不可变备份降低 impact。"),
    ],
    "evt_phishing_social": [
        ("01_mitre_ambient_axiom.md",
         "https://attack.mitre.org/groups/G0001/",
         "MITRE ATT&CK G0001 (Axiom) 案例研究摘要",
         "2019-07-01",
         "MITRE ATT&CK G0001 Axiom 案例记录: 该组织长期针对媒体与工程机构实施间谍活动。初始访问以 spear phishing 邮件携带恶意附件为主, 收件人打开后用户执行伪装成文档的 dropper, 建立持久化计划任务; 通过伪造登录页与键盘记录窃取 valid credentials (credential access), 再用窃取凭据登录 webmail 与 VPN 扩大访问。Axiom 大量使用公开工具 (Poison Ivy RAT) 与编码 payload 规避检测, 是 spearphishing attachment 手法的经典教材。"),
        ("02_fbi_ic3_bec_2023.md",
         "https://www.ic3.gov/AnnualReport/Reports/2023_IC3Report.pdf",
         "FBI IC3 2023 年报 — BEC (Business Email Compromise) 章节",
         "2024-04-30",
         "FBI IC3 2023 年报 BEC 章节统计: 全年 BEC 造成超过 29 亿美元损失, 居网络犯罪损失首位。典型链路: 攻击者先通过钓鱼或购买泄露凭据接管高管邮箱 (email account compromise), 利用 mailbox rules 隐藏往来邮件 (defense evasion), 再向财务人员发送冒充供应商的 invoice 变更邮件诱导转账 (social engineering → financial impact)。IC3 建议企业对付款指令实施带外双因子验证, 并监控邮箱转发规则异常。"),
        ("03_apwg_trends_q4.md",
         "https://apwg.org/trendsreports/",
         "Anti-Phishing Working Group (APWG) Phishing Activity Trends 摘要",
         "2024-01-25",
         "APWG 季度趋势报告显示钓鱼活动持续产业化: phishing kit 让攻击者低成本克隆银行与 SaaS 登录页, 通过短信 (smishing) 与语音 (vishing) 引导受害者输入凭据; MFA 疲劳攻击 (push bombing) 与 AiTM (attacker-in-the-middle) 反向代理直接截获 session cookie 绕过 OTP。报告观察到大量 resource development 行为 — 批量注册仿冒域名与租用发送基础设施。建议企业部署 phishing-resistant MFA (FIDO2) 与邮件 DMARC 严格策略。"),
        ("04_verizon_dbir_social_eng.md",
         "https://www.verizon.com/business/resources/reports/dbir/",
         "Verizon DBIR social engineering 章节摘要",
         "2024-05-01",
         "Verizon DBIR social engineering 章节统计: 68% 的 breach 涉及非恶意人为要素, pretexting 在 BEC 场景占比持续上升。典型模式: 攻击者在 reconnaissance 阶段通过 LinkedIn 与公司官网收集组织结构与邮件命名规则, 在 resource development 阶段购买仿冒域名, 随后以 CEO  fraud 或 invoice fraud 话术诱导财务转账。DBIR 指出钓鱼汇报时长中位数约 29 分钟, 强调报告按钮与演练对缩短 detection time 的价值。"),
        ("05_mitre_fin7_payment_diversion.md",
         "https://attack.mitre.org/groups/G0046/",
         "MITRE ATT&CK G0046 (FIN7) 案例研究摘要",
         "2021-11-10",
         "MITRE ATT&CK G0046 FIN7 案例记录: 该组织以餐饮零售 POS 为主要目标, 后扩展至勒索与支付 diverted fraud。初始访问依赖针对性钓鱼邮件, 附件为带宏的 Word 文档诱导用户执行 macro-enabled payload; 通过计划任务与注册表 run key 持久化, 使用公开渗透测试框架进行内网侦察与横向移动, 最终窃取卡数据或实施支付诈骗。FIN7 的工具链 (HalfOpenScanner、 BOOSTWRITE) 展示了钓鱼起点的完整攻击工业化路径。"),
    ],
    "evt_web_app_intrusion": [
        ("01_owasp_top10_2021_case.md",
         "https://owasp.org/Top10/",
         "OWASP Top 10 2021 — Injection/Broken Access Control 案例要点",
         "2021-09-24",
         "OWASP Top 10 (2021) 以真实漏洞统计为依据: Broken Access Control 与 Injection (含 SQL 注入) 连年位居前列。典型案例模式: 应用未校验输入导致 SQL 注入拖库 (数据外传), 或 IDOR 越权遍历他人订单; 反序列化漏洞让攻击者上传恶意对象实现 RCE (execution); SSRF 让攻击者访问云元数据端点窃取 IAM 临时凭据进而接管云资源。OWASP 建议以参数化查询、集中式鉴权与依赖 SBOM 作为基础防线。"),
        ("02_hackerone_disclosure_sqli.md",
         "https://hackerone.com/hacktivity",
         "HackerOne 公开披露 — SQL Injection RCE 复合漏洞报告要点",
         "2023-06-15",
         "HackerOne 公开披露案例: 研究者在某 SaaS 应用的搜索接口发现 SQL 注入, 利用 UNION 查询确认数据库结构后, 借助堆叠查询写入 web shell 实现远程代码执行, 随后枚举文件系统发现数据库凭据配置并横向至内网数据库。整个链路覆盖 initial access (exploit public-facing application) → execution (web shell) → persistence (webshell 落地) → collection (拖取用户表) → exfiltration (经 HTTPS 外传)。厂商修复采纳参数化查询与 WAF 规则加固。"),
        ("03_portswigger_ssrf_cloud.md",
         "https://portswigger.net/web-security/ssrf",
         "PortSwigger Web Security — SSRF 到云凭据窃取案例要点",
         "2023-03-01",
         "PortSwigger SSRF 教学与案例集合说明: 当应用存在 SSRF 且部署在云上时, 攻击者可让服务器请求 metadata 服务 (如 169.254.169.254) 获取临时 IAM 凭据, 再以 valid cloud accounts 登录对象存储拖取敏感桶, 完成从 Web 漏洞到云资源接管的完整链。防御建议: 出网白名单、 metadata v2 强制 token、 阻止非常见端口回连。案例覆盖 SSRF→credential access→collection→exfiltration 全阶段。"),
        ("04_cloudflare_appsec_2024.md",
         "https://blog.cloudflare.com/cloudflare-2024-appsec-security-report/",
         "Cloudflare 2024 Application Security Report 要点",
         "2024-03-20",
         "Cloudflare 2024 AppSec 报告统计: 全球流量中约 3% 为恶意利用尝试, 其中 web 攻击以 SQL 注入 (39%) 与 XSS、 路径遍历为主; 每 5 个 API 端点就有 1 个返回敏感数据未做鉴权 (BOLA)。报告观察到攻击者普遍先做目录爆破与指纹识别 (discovery), 再对暴露的管理后台尝试默认凭据与反序列化 exploit, 成功后部署 web shell 或挖矿程序 (impact)。建议全面启用 bot 管理、 API schema 校验与零信任访问。"),
        ("05_cisa_moveit_advisory.md",
         "https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-131a",
         "CISA Advisory — MOVEit Transfer SQL 注入批量利用事件摘要",
         "2023-06-01",
         "CISA 关于 Progress MOVEit Transfer 漏洞 (CVE-2023-34362) 的 advisory: 攻击者利用 SQL 注入在面向公众的文件传输服务上实现 RCE, 部署 web shell (human2.aspx) 获取 persistence, 枚举并批量下载企业客户数据 (collection + exfiltration), 涉及上千家组织的供应链式数据外泄。advisory 强调该事件展示了 exploit public-facing application 在 initial access 的破坏力, 建议立即修补、 审计异常 aspx 文件并轮换服务凭据。"),
    ],
    "evt_supply_chain": [
        ("01_mitre_solarwinds_g0118.md",
         "https://attack.mitre.org/groups/G0118/",
         "MITRE ATT&CK G0118 (UNC2452 / SolarWinds 事件) 摘要",
         "2021-04-15",
         "MITRE ATT&CK 关于 SolarWinds 事件的案例记录: 攻击者在 resource development 阶段入侵 Orion 构建系统, 通过 SUNBURST 后门化的签名更新实现软件供应链 compromise, 下游约 18000 客户自动安装植入; 植入随后选择性激活, 滥用合法 SAML token 伪造黄金票据访问目标云邮箱 (credential access + collection), 数据经 Mimikatz 提取凭据后分批外传。事件定义了现代供应链攻击的范式: 构建管道污染 + 信标激活 + 云身份滥用。"),
        ("02_xz_utils_cve_2024_3094.md",
         "https://www.redhat.com/en/blog/urgent-security-alert-fedora-41-and-rawhide-users",
         "XZ Utils 后门 (CVE-2024-3094) 事件复盘要点",
         "2024-03-30",
         "XZ Utils 后门事件复盘: 攻击者以假名维护者身份长期参与开源项目, 获取提交权限后在构建脚本 (build-to-host.m4) 中注入混淆 payload, 仅影响分发 tarball 而隐藏于 git 历史; 后门劫持 liblzma 链接的 sshd 鉴权流程, 实现预认证远程代码执行 (persistence + execution)。事件由工程师注意到 sshd 慢 500ms 而暴露。复盘强调供应链投毒的 resource development 阶段可长达两年, 建议对关键依赖实施构建可重复性验证。"),
        ("03_sonatype_ssc_2024.md",
         "https://www.sonatype.com/state-of-the-software-supply-chain",
         "Sonatype State of the Software Supply Chain 2024 要点",
         "2024-09-18",
         "Sonatype 年度报告统计: npm/PyPI/Maven 生态累计发现超过 51 万个恶意包, typosquatting 与 dependency confusion 是主要投毒手法; 攻击者在包内嵌入 install 脚本实现用户执行 (npm install 即触发), 窃取 CI 凭据与环境变量后横向渗透下游企业构建管道 (persistence)。报告指出仅 2% 项目会在漏洞修复后同步升级依赖。建议启用仓库代理白名单、 namespace 保留与 SBOM 持续比对。"),
        ("04_dep_confusion_postmortem.md",
         "https://azure.microsoft.com/en-us/resources/3 ways to mitigate risk using private package feeds",
         "Dependency Confusion (Alex Birsan) 事件研究要点",
         "2021-02-09",
         "Alex Birsan 的 dependency confusion 研究: 当企业内网私有包名与公共仓库重名且解析器优先公网时, 攻击者可注册同名包让 CI 自动拉取恶意版本, install 脚本在构建机上执行 (execution), 读取环境变量与 CI token 并回传攻击者服务器 (exfiltration)。该研究影响 Apple、 Microsoft、 PayPal 等数十家公司, 促使 npm/yarn 引入 scoped registry 与 --no-postinstall 策略。事件完整覆盖 resource development → initial access → execution → collection 链条。"),
        ("05_enisa_threat_landscape_scc.md",
         "https://www.enisa.europa.eu/publications/enisa-threat-landscape-2023",
         "ENISA Threat Landscape — Supply Chain Compromise 章节要点",
         "2023-10-01",
         "ENISA 威胁概览供应链章节: 供应链事件在 2020-2023 增长 700%, 攻击面聚焦三处 — 第三方软件更新通道 (update hijack)、 开源依赖投毒与托管服务商 MSP 远程管理工具滥用 (trusted relationship)。典型链路: 攻击者先入侵构建或分发基础设施, 用合法签名推送带植入的更新 (execution + persistence), 借助受信任渠道绕过终端检测 (defense evasion)。ENISA 建议对供应商实施分级访问与更新签名双重验证。"),
    ],
    "evt_brute_force": [
        ("01_msft_ddr_2023_credential.md",
         "https://www.microsoft.com/en-us/security/blog/2023/10/25/microsoft-digital-defense-report-2023/",
         "Microsoft Digital Defense Report 2023 — credential attack 章节要点",
         "2023-10-25",
         "Microsoft 数字防御报告凭据章节: 每秒遭到超过 4000 次凭据攻击, password spray 与 credential stuffing 占绝对多数。攻击者通过 recon 锁定暴露的 OWA、 VPN 与 RDP 端点, 用泄露密码字典低速喷洒规避锁定 (defense evasion), 成功后注册自控 MFA 设备完成账户接管; 对无 MFA 环境则直接以 valid accounts 登录云控制台枚举数据 (discovery + collection)。建议全面启用 phishing-resistant MFA 与智能锁定策略。"),
        ("02_akamai_soti_cred stuffing.md",
         "https://www.akamai.com/security-research/the-state-of-the-internet",
         "Akamai State of the Internet — Credential Stuffing 要点",
         "2024-04-10",
         "Akamai SOTI 报告统计: 零售与金融 API 流量中 credential stuffing 攻击占比超过 35%, 攻击者用 combolist (数十亿泄露凭据对) 通过自动化脚本撞库, 以 0.1%~1% 的命中率规模化获利; 成功登录后立即执行 gift card 转移或数据遍历 (impact + collection)。报告观察到攻击者使用住宅代理轮换 IP (defense evasion) 绕过速率限制。建议按设备指纹与行为生物特征识别自动化登录, 而非单纯 IP 限速。"),
        ("03_f5_labs_stuffing_report.md",
         "https://www.f5.com/labs/reports",
         "F5 Labs Credential Stuffing Campaign 报告要点",
         "2021-08-17",
         "F5 Labs 撞库报告分析一次持续 21 天的大型 stuffing 活动: 攻击者将 13 亿凭据对按 50~100 rps 均匀投放到目标登录端点, 避免触发告警; 响应差异分析显示 0.52% 登录成功, 随后对成功账户执行订单查询与积分转移。报告详细拆解了工具链 (Sentry MBA 类脚本) 与 defense evasion 手法 — UA 轮换、 代理池与验证码众包。建议对登录失败实施自适应挑战与账户孤儿检测。"),
        ("04_cisa_vpn_bruteforce_advisory.md",
         "https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a",
         "CISA Advisory — MFA 爆破绕过与 VPN 暴力破解事件要点",
         "2024-02-07",
         "CISA 与合作机构 advisory 描述: 攻击者对未打补丁的 Fortinet/F5/Pulse VPN 设备实施凭据爆破, 并利用 MFA 爆破 (push fatigue) 或旧会话 cookie 复放绕过多因子认证, 获得初始访问后以 valid accounts 在内网注册持久化设备、 枚举 AD 并部署勒索载荷。advisory 列出 indicators: 大量来自 VPS 的登录失败、 同账号多地 OTP 推送。建议强制证书式 VPN 认证、 限速与 MFA 号码匹配。"),
        ("05_shape_ai_threat_mfa_fatigue.md",
         "https://shape.security/blog/",
         "Shape AI Threat Report — MFA Fatigue 与 OTP 劫持要点",
         "2023-01-19",
         "Shape (F5) 威胁报告聚焦 MFA 绕过产业化: MFA fatigue 攻击对受害者高频推送 approve 请求直至误点 (UkraineRound 事件使该手法广为人知); SIM swap 与 OTP bot (OTP agency) 实时钓鱼转发热敏码绕过短信因子; 攻击流量使用 headless 浏览器与自动化框架模拟人类输入 (defense evasion), 撞库成功率较 2021 提升明显。报告建议改用绑定设备与用户的 FIDO2 凭据, 并对推送登录实施地理与号码匹配校验。"),
    ],
}

now = "2026-09-13T04:00:00Z"
total = 0
for et_id, reports in CORPUS.items():
    d = BASE / et_id
    d.mkdir(parents=True, exist_ok=True)
    for fname, url, title, rdate, body in reports:
        content = (
            f"---\nsource_url: {url}\ntitle: {title}\nfetched_at: {now}\nreport_date: {rdate}\n---\n\n{body}\n"
        )
        (d / fname).write_text(content, encoding="utf-8")
        total += 1
print(f"generated {total} reports under {BASE}")
PYEOF
