# SecNews v1.7 用户指南

> **版本**: v1.7
> **日期**: 2026-08-01

## 5 触发器说明

### T1: raw→refine (每 60s)
- 扫描 `kl:raw` 状态的 items
- simhash 去重 (Hamming < 5)
- 提取标签 (concepts JSON → tags)
- 迁移到 `kl:refine` 状态

### T2: refine→link (每 120s)
- 扫描 `kl:refine` 状态的 items
- 发现共享 concept → 建立 knowledge_links
- 双向关联 (a→b 与 b→a 同时建立)
- 迁移到 `kl:link` 状态

### T3: link→structure (每 600s)
- 扫描 `kl:link` 状态的 items
- 关联数 ≥ 3 的 items 推进
- 迁移到 `kl:structure` 状态

### T4: structure→publish (每 1800s)
- 扫描 `kl:structure` 状态的 items
- 评分 ≥ 8 的 items 自动发布
- 迁移到 `kl:publish` 状态

### T5: publish→refine (手动触发)
- 回滚已发布的 items 到 refine 状态
- 保留用户编辑内容

## 4 认知模式

### 简报模式 (Briefing)
- 一句话摘要 + 3 篇关键文章
- 数据源状态概览
- 入口: `/knowledge/briefing`

### 扫描模式 (Scan)
- 快速浏览知识库最新 items
- 按 lifecycle 状态筛选
- 入口: `/knowledge/scan`

### 深度阅读模式 (Deep Read)
- 单条 item 全文阅读
- 生命周期可视化边栏
- 入口: `/knowledge/deep-read/:id`

### 告警模式 (Alert)
- AlertCenter 告警列表
- 规则配置界面
- 入口: `/knowledge/alert`

## 复利仪表盘

- 日/周/月趋势图
- Top concepts 排行
- 7 天无推进告警
- 入口: `/knowledge`

## 子系统联动

### Tech Stack Drift 评估
- POST `/api/codegarden/drift/assess` 触发评估
- 自动发现 knowledge 中新技术
- 对比 CodeGarden 项目 tech_stack
- 生成 drift 评估报告

### CVE 同步
- POST `/api/cve/sync` 触发同步
- item_entities → security_entities 同步
- 自动去重 + metadata 更新