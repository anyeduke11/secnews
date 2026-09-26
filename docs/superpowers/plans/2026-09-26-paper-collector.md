# 论文抓取 — 实施计划 (2026-09-26)

**Spec**: `docs/superpowers/specs/2026-09-26-paper-collector-design.md`
**Base**: main 当前 HEAD · **Branch**: paper-collector

## Task 1: Category.PAPER + ArxivPaperCollector + 源注册

**Files**: `backend/domain/enums.py`、`backend/services/collection_service.py`、`backend/collectors/arxiv_paper_collector.py`（新）、`backend/collectors/__init__.py`、`backend/collectors/keywords.py`、`backend/tests/test_arxiv_paper_collector.py`（新）、`frontend/src/types/index.ts`、`frontend/src/components/sentinel/SentinelHomePage.tsx`（tagColorOf）、三个 report service

- [x] 枚举 PAPER + collectors dict + keywords + 前端 CATEGORIES/tagColorOf + 报表标签
- [x] ArxivPaperCollector: 14 领域查询模板 + 轮转采样（类级 cursor, 每轮 3 领域）+ Atom 解析（复用 _fetch_rss）+ arxiv id/领域写 tags + international zone
- [x] crawler_sources 14 行注册（category='paper', kind='rss', api_url=各领域 query）——migration 或启动注入, 按 crawler_sources 现有写入先例
- [x] 测试: Atom 解析（fixture feed）/轮转采样断言/领域 tag/category 关键词命中/注册点齐备（generate_meta collectors 13→14）
- [x] 全量回归 + tsc/vitest + generate_meta + ruff

## Task 2: 收口

- [x] 真实拉取一轮（curl arxiv API 验证 + 可选跑 collector 一次看产出）+ DEV-0233 + 计划落账 + PRD 判断

## 全局约束

- 不动 ai_hub; 复用 _fetch_rss/fetchers 基建; 国际源标注代理依赖; 不新增 feature gate

## 实施记录 (2026-09-26 收口, DEV-0233)

- **commits**: 1d34b03 计划 / 07c1e46 全量实现 (Batch A, 审查 Approved) / 本 commit 收口 (真实验证 + DEV-0233 + 本落账)
- **真实拉取验证结论 (Task 2 核心)**:
  - arXiv API **直连可达** (http 301→https, 无需代理; proxy_config 为空不影响)
  - curl 验证抓出 `sortBy=submitted` 为**非法值** (合法: relevance / lastUpdatedDate / submittedDate); 误值不报错而是返回仅含 1 条 Error entry 的 Atom feed——3 领域轮转恰凑满 `min_items_threshold=3`, **垃圾条目会静默入 feed**。本 commit 修正: 采集器常量 + migration 123 种子 (append-only 追加 125 替换修复, 123 在本机已应用且 schema_version 无内容校验) + 测试精确断言 (`sortBy=submitted&` 负向断言防前缀误匹配回退)
  - 真实 collect() 实测: tmp DB 进程内非 mock 跑通, 单轮产出 27 条 (AI 5 / AI安全 12 / 网络安全 10, 质量门禁后截断 max_items=30), 字段完整 (id=`arxiv:<id>` / source=领域键 / category=paper / title 压平 / url=arxiv.org/abs 链接 / published_at); 样例: 《The Fly That Stopped: Mushroom-Body-Inspired Habituation as a Reward-Free Scheduling Prior for Autonomous Penetration Testing》 https://arxiv.org/abs/2609.29126v1 ; 《AERIAL: Adversarial Evaluation of Robustness in Accuracy-Preserving Low-Precision EEG Decoders》 https://arxiv.org/abs/2609.30037v1
  - **arXiv 限流发现**: Fastly 边缘对突发并发 (base.collect 的 gather 3 域同时出网) 施加 IP 级瞬态 406 (空 body, X-Cache MISS, 分钟级衰减); 采集器内加类级节拍锁 (`_PACE_LOCK`, 3s 间隔, 串行化本 collector 出网, 共享 fetchers 基建零改动) 后实测一轮全通过。生产 cadence=3600s 每小时仅 3 请求, 余量充足
- **PRD 判断**: paper 为新**资讯类目** (非设置能力); 单权威 PRD 无类目清单段落, 仅第 6 章架构表有 Collectors 计数行 → 已同步 13→14 并注明 arXiv 单源。该表 Routers/Services/Migrations 计数在本分支前已漂移 (pre-existing, 归 generate_meta 注册链管), 不在本次 surgical 范围
- **parked minors** (不阻断, 留后续):
  1. 预过滤词表大小写敏感召回偏紧 (item_builder `_title_relevant` 路径, 论文标题常见首字母大写专有名词漏匹配)
  2. `_paper_tags` 目前仅 tags[0] 被消费 (item.id), tags[1]/tags[2] 落点已由 source/category 承载, 函数本体为死代码 (保留作设计稿 §3.2 契约锚)
  3. 设计稿 cursor 偏差: 稿写"类属性 `_domain_cursor`", 实现为实例属性 (collector 长生命周期实例, 实例属性才对; 类属性会被子类/多实例共享污染)
  4. arXiv 边缘对 >1req/3s 持续活动 (如连续多轮测试) 会分钟级拉黑 IP——单轮 3 请求/小时远低于阈值, 但若未来加大每轮领域数需同步放宽节拍
