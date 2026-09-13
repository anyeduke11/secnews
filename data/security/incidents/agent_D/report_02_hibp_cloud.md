# 事件报告语料 02 — Have I Been Pwned: 云配置失控致金融数据外泄复盘

- **source_url**: https://haveibeenpwned.com/PwnedWebsites
- **fetched_at**: 2026-09-13
- **event_class_hint**: data_breach (原始分类: breach postmortem / cloud misconfiguration)
- **industry**: financial
- **agent_owner**: D

## 报告摘要

Have I Been Pwned 收录的多起金融科技平台泄露复盘显示共同模式: 运维将对象存储桶设为公开可读, 桶内含明文数据库连接串与访问密钥, 外部人员无需凭据即可遍历下载全部客户档案。复盘指出扫描器在配置错误暴露后数小时内即完成全量抓取, 数据随后被打包出现在地下论坛交易。

## 关键事实 (evidence 池)

- "运维将对象存储桶设为公开可读"
- "桶内含明文数据库连接串与访问密钥"
- "扫描器在配置错误暴露后数小时内即完成全量抓取"
- "数据随后被打包出现在地下论坛交易"
