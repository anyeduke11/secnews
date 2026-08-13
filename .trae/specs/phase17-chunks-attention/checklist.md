# Checklist — Phase 17 Chunks + Attention + 6 模式完整

## Migration
- [x] `054_v2.0_chunks.sql` 包含 `knowledge_chunks` 表（item_id FK + chunk_index + content + char_start/end + summary）
- [x] `054_v2.0_chunks.sql` 包含 `knowledge_chunks_fts` FTS5 虚拟表
- [x] `054_v2.0_chunks.sql` 包含 `attention_events` 表（item_id + event_type + detail_json）
- [x] `054_v2.0_chunks.sql` 包含 `ALTER TABLE knowledge_items ADD COLUMN attention_score`
- [x] migration 文件已创建，待执行

## Chunks API
- [x] `GET /api/knowledge/chunks/{item_id}` 返回正确 chunk 列表
- [x] `GET /api/knowledge/chunks/search?q=keyword` FTS5 搜索返回正确结果
- [x] `POST /api/knowledge/chunks/generate/{item_id}` 正确切分并写入
- [x] router 注册到 `backend/api/__init__.py`

## Attention Score
- [x] `attention_scorer.py` 实现 5 维度加权（view_count/dwell_time/scroll_depth/is_favorited/annotation_count）
- [x] `score(item_id) -> int` 返回 0~100 整数
- [x] `batch_score()` 批量更新全量 item
- [x] 结果正确写入 `knowledge_items.attention_score`

## Attention 事件采集
- [x] `POST /api/attention/events` 接受 6 种事件类型（view/dwell/scroll/favorite/annotation/share）
- [x] 事件正确写入 `attention_events` 表
- [x] router 注册到 `backend/api/__init__.py`

## Attention 聚合 job
- [x] `attention_aggregate_job` 注册到 scheduler（IntervalTrigger 1800s）
- [x] 30 天窗口内事件正确聚合
- [x] 过期事件正确清理

## AttentionHeatmap 组件
- [x] 30 天 × 24 小时热力图渲染
- [x] 颜色深浅表示 attention 密度
- [x] 点击单元格跳转到对应日期简报
- [x] 集成在 BriefingMode 侧边栏（compact 模式）

## 整理模式（Outbox）
- [x] 清单视图按 attention_score 降序排列
- [x] 批量操作（标记已读、归档）正常工作
- [x] 过滤（lifecycle / 日期 / 评分）正常工作

## 复习模式（SM-2）
- [x] 卡片翻转界面（正面 title，背面 content/summary）
- [x] 自评 [0-5] 按钮触发评分
- [x] `GET /api/reviews/due` 返回到期复习队列
- [x] `POST /api/reviews/grade` 正确更新 sm2_reviews 表
- [x] 复用 v1.7 `review_service.py` 的 SM-2 算法

## Chunk 级 UI
- [x] DeepReadMode 高亮显示 chunk 段落边界
- [x] DeepReadMode 点击跳转到原文对应段落
- [x] BriefingMode 显示 chunk 摘要预览
- [x] ScanMode 显示 attention_score 徽章

## 路由 + 导航
- [x] `/knowledge/outbox` → OutboxMode 路由正确
- [x] `/knowledge/review` → ReviewMode 路由正确
- [x] `/knowledge/heatmap` → AttentionHeatmap 路由正确
- [x] KnowledgeTabs 显示 6 个标签（简报/扫描/深度/告警/整理/复习）

## 测试
- [x] `test_chunks_api.py` 全部通过（chunk CRUD + FTS5 + 生成 8/8 用例）
- [x] `test_attention_scorer.py` 全部通过（5 维度加权 + 聚合 5/5 用例）
- [x] `test_attention_events.py` 全部通过（事件上报 + 限额 5/5 用例）
- [x] 前端新组件测试全部通过（AttentionHeatmap 5 + OutboxMode 7 + ReviewMode 4 = 16 用例）
- [x] 4 模式组件测试更新后全部通过（37 文件 286 测试）
- [x] 后端 pytest 全部通过（18/18 新测试，无 regression）
- [x] 前端 vitest 全部通过（37 files, 286 passed）
- [x] TypeScript 编译通过（tsc --noEmit 无错误）