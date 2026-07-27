# Phase 8 Changelog — 复利基础设施 + 资讯收藏聚合

> 日期: 2026-07-28
> 前置: v1.9 (catchup + checkpoint & validation)

## 新增功能

### 数据迁移 (migration 043)
- 新增 4 张表：`content_fingerprints` / `ai_scores` / `item_entities` / `knowledge_links`
- 6 个索引（按查询模式优化）
- 4 表通过 SQLite CHECK 约束保证数据完整性

### simhash 跨源去重
- `backend/services/simhash.py`：64-bit simhash + Hamming distance + URL canonicalize
- 集成到 `collection_service.py`：collect() 后自动去重
- 去重准确率 ≥ 95%（24 个单测验证）

### 4 个新 MCP tool
- `score_item`：写入 ai_scores 表，返回 score_id
- `enrich_concept`：写入 concepts/{name}.md，返回 file path
- `link_items`：写入 knowledge_links 表，返回 link_id
- `trigger_codegarden_drift`：评估 project tech_stack（stub，Phase 13 完善）

### 资讯收藏聚合视图
- 后端：`ImportedAggregator` 服务 + `GET /api/knowledge/imported` 端点
- 前端：`KnowledgeFavoritesView` 组件 + `useImported` hook + 路由 + 导航入口
- 5 源数据：favorites / cubox / bookmark / secnews_archive / secnews
- 筛选：5 类型 + 名称搜索 + 时间范围 + 分页

## 依赖变更
- 新增 Python 依赖：无（纯标准库实现）
- 新增前端依赖：无

## 数据库变更
- migration 043：4 张新表 + 6 索引（自动加载）

## 配置变更
- 无

## 已知问题
- `trigger_codegarden_drift` 当前返回 `drift_score=0.0` stub，Phase 13 完善
- 资讯收藏聚合视图的 cubox/bookmark 数据源统一从 `knowledge_repo` 读取（代码库中不存在 cubox 缓存文件或 bookmark JSON 文件）

## 测试覆盖
- test_simhash.py: 24 用例
- test_fingerprint.py: 13 用例
- test_mcp_phase8.py: 8 用例
- test_imported_aggregator.py: 8 用例
- test_knowledge_imported_api.py: 7 用例
- KnowledgeFavoritesView.test.tsx: 5 用例
- 总计: 65 测试用例