# Tasks — Phase 17 Chunks + Attention + 6 模式完整

## 任务列表

### Task 17.1: knowledge_chunks 表 migration
- [x] 创建 `backend/repository/migrations/054_v2.0_chunks.sql`
  - [x] `knowledge_chunks` 表（id, item_id, chunk_index, content, char_start, char_end, summary, created_at）
  - [x] `knowledge_chunks_fts` FTS5 虚拟表
  - [x] `knowledge_items` 表新增 `attention_score` 列（INTEGER DEFAULT 0）
- [x] 创建 `attention_events` 表（id, item_id, event_type, detail_json, created_at）

### Task 17.2: Chunk 级 API + FTS5
- [x] 创建 `backend/api/knowledge_chunks_api.py`
  - [x] `GET /api/knowledge/chunks/{item_id}` — 返回 item 的所有 chunk
  - [x] `GET /api/knowledge/chunks/search?q=...` — FTS5 搜索
  - [x] `POST /api/knowledge/chunks/generate/{item_id}` — 手动触发切分
- [x] 注册 router 到 `backend/api/__init__.py`

### Task 17.3: attention_score 计算
- [x] 创建 `backend/services/attention_scorer.py`
  - [x] 5 维度加权（view_count/dwell_time/scroll_depth/is_favorited/annotation_count）
  - [x] `score(item_id) -> int` 返回 0~100
  - [x] `batch_score()` 批量更新
  - [x] 写入 `knowledge_items.attention_score`

### Task 17.4: Attention 事件采集 API
- [x] 创建 `backend/api/attention_events_api.py`
  - [x] `POST /api/attention/events` — 事件上报
  - [x] 事件类型：view/dwell/scroll/favorite/annotation/share
- [x] 注册 router 到 `backend/api/__init__.py`

### Task 17.5: Attention 聚合 job
- [x] 修改 `backend/scheduler/jobs.py` 新增 `attention_aggregate_job()`
- [x] 修改 `backend/scheduler/scheduler.py` 注册 job（IntervalTrigger 1800s）
- [x] 30 天窗口 + 过期清理

### Task 17.6: AttentionHeatmap 组件
- [x] 创建 `frontend/src/components/knowledge/AttentionHeatmap.tsx`
  - [x] 30 天 × 24 小时热力图
  - [x] 点击单元格跳转到对应日期简报
  - [x] 集成到 BriefingMode 侧边栏

### Task 17.7: 整理模式（Outbox）UI
- [x] 创建 `frontend/src/components/knowledge/OutboxMode.tsx`
  - [x] 清单视图 + attention_score 降序排序
  - [x] 批量操作（标记已读、归档）
  - [x] 过滤（lifecycle / 日期 / 评分）

### Task 17.8: 复习模式（SM-2）UI
- [x] 创建 `frontend/src/components/knowledge/ReviewMode.tsx`
  - [x] 卡片翻转界面
  - [x] 自评 [0-5] 按钮
  - [x] 复用 `review_service.py` + `sm2_reviews` 表
  - [x] 到期复习队列 API：`GET /api/reviews/due`
  - [x] 评分提交 API：`POST /api/reviews/grade`

### Task 17.9: Chunk 级 UI
- [x] 修改 `DeepReadMode.tsx`：chunk 段落高亮 + 点击跳转
- [x] 修改 `BriefingMode.tsx`：chunk 摘要预览
- [x] 修改 `ScanMode.tsx`：attention_score 徽章

### Task 17.10: 路由 + 导航
- [x] 修改 `frontend/src/App.tsx`：新增 `/knowledge/outbox`、`/knowledge/review`、`/knowledge/heatmap` 路由
- [x] 修改 `KnowledgeTabs.tsx`：6 个标签（简报/扫描/深度/告警/整理/复习）

### Task 17.11: 测试
- [x] 创建 `backend/tests/test_chunks_api.py`（chunk CRUD + FTS5 + 生成）
- [x] 创建 `backend/tests/test_attention_scorer.py`（5 维度加权 + 聚合）
- [x] 创建 `backend/tests/test_attention_events.py`（事件上报 + 限额）
- [x] 创建前端测试：`AttentionHeatmap.test.tsx` / `OutboxMode.test.tsx` / `ReviewMode.test.tsx`
- [x] 更新现有 4 模式组件测试
- [x] 运行全部测试验证

## 任务依赖关系
- Task 17.1（migration）→ Task 17.2（chunks API）
- Task 17.1（migration）→ Task 17.4（attention events 表）
- Task 17.4（事件采集）→ Task 17.3（attention_score 计算）
- Task 17.3（attention_score）→ Task 17.5（聚合 job）
- Task 17.3/17.4 → Task 17.6（AttentionHeatmap）
- Task 17.3 → Task 17.7（Outbox 排序需要 attention_score）
- Task 17.2（chunks API）→ Task 17.9（chunk UI）
- Task 17.6/17.7/17.8 → Task 17.10（路由 + 导航）
- Task 17.11 依赖所有其他任务

## 并行化建议
- Task 17.1（migration）可独立启动
- Task 17.8（SM-2 UI）不依赖 attention 体系，可与其他任务并行
- Task 17.2（chunks API）→ Task 17.9（chunk UI）串行
- Task 17.4（事件采集）→ Task 17.3（scorer）→ Task 17.5（聚合 job）串行
- Task 17.6/17.7（热图 + 整理）在 Task 17.3 完成后可并行
- Task 17.11（测试）最后执行