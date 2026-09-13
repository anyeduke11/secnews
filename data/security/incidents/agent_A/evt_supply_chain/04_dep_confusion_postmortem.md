---
source_url: https://azure.microsoft.com/en-us/resources/3 ways to mitigate risk using private package feeds
title: Dependency Confusion (Alex Birsan) 事件研究要点
fetched_at: 2026-09-13T04:00:00Z
report_date: 2021-02-09
---

Alex Birsan 的 dependency confusion 研究: 当企业内网私有包名与公共仓库重名且解析器优先公网时, 攻击者可注册同名包让 CI 自动拉取恶意版本, install 脚本在构建机上执行 (execution), 读取环境变量与 CI token 并回传攻击者服务器 (exfiltration)。该研究影响 Apple、 Microsoft、 PayPal 等数十家公司, 促使 npm/yarn 引入 scoped registry 与 --no-postinstall 策略。事件完整覆盖 resource development → initial access → execution → collection 链条。
