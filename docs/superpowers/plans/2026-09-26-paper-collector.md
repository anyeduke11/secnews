# 论文抓取 — 实施计划 (2026-09-26)

**Spec**: `docs/superpowers/specs/2026-09-26-paper-collector-design.md`
**Base**: main 当前 HEAD · **Branch**: paper-collector

## Task 1: Category.PAPER + ArxivPaperCollector + 源注册

**Files**: `backend/domain/enums.py`、`backend/services/collection_service.py`、`backend/collectors/arxiv_paper_collector.py`（新）、`backend/collectors/__init__.py`、`backend/collectors/keywords.py`、`backend/tests/test_arxiv_paper_collector.py`（新）、`frontend/src/types/index.ts`、`frontend/src/components/sentinel/SentinelHomePage.tsx`（tagColorOf）、三个 report service

- [ ] 枚举 PAPER + collectors dict + keywords + 前端 CATEGORIES/tagColorOf + 报表标签
- [ ] ArxivPaperCollector: 14 领域查询模板 + 轮转采样（类级 cursor, 每轮 3 领域）+ Atom 解析（复用 _fetch_rss）+ arxiv id/领域写 tags + international zone
- [ ] crawler_sources 14 行注册（category='paper', kind='rss', api_url=各领域 query）——migration 或启动注入, 按 crawler_sources 现有写入先例
- [ ] 测试: Atom 解析（fixture feed）/轮转采样断言/领域 tag/category 关键词命中/注册点齐备（generate_meta collectors 13→14）
- [ ] 全量回归 + tsc/vitest + generate_meta + ruff

## Task 2: 收口

- [ ] 真实拉取一轮（curl arxiv API 验证 + 可选跑 collector 一次看产出）+ DEV-0233 + 计划落账 + PRD 判断

## 全局约束

- 不动 ai_hub; 复用 _fetch_rss/fetchers 基建; 国际源标注代理依赖; 不新增 feature gate
