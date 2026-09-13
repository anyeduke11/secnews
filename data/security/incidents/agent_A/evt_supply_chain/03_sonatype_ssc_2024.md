---
source_url: https://www.sonatype.com/state-of-the-software-supply-chain
title: Sonatype State of the Software Supply Chain 2024 要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2024-09-18
---

Sonatype 年度报告统计: npm/PyPI/Maven 生态累计发现超过 51 万个恶意包, typosquatting 与 dependency confusion 是主要投毒手法; 攻击者在包内嵌入 install 脚本实现用户执行 (npm install 即触发), 窃取 CI 凭据与环境变量后横向渗透下游企业构建管道 (persistence)。报告指出仅 2% 项目会在漏洞修复后同步升级依赖。建议启用仓库代理白名单、 namespace 保留与 SBOM 持续比对。
