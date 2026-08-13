# Phase 17: Chunks + Attention Heatmap + 6 模式完整

## Why

v2.0 收尾 Phase。Phase 13 已实施 4/6 认知模式（简报/扫描/深度/告警），但缺少 chunk 段落级引用和 attention_score 注意力热图，且整理模式（Outbox）和复习模式（SM-2）尚未接入 UI。本 Phase 完成全 6 种认知模式并补齐 chunks + attention 基础设施。

## What Changes

### 17.1 knowledge_chunks 表 migration
- 创建 `backend/repository/migrations/054_v2.0_chunks.sql`
- 新增 `knowledge_chunks` 表：
  - `id` / `item_id` (FK → knowledge_items.id) / `chunk_index` / `content` / `char_start` / `char_end` / `summary` / `created_at`
  - 唯一约束 `(item_id, chunk_index)`
  - FTS5 虚拟表 `knowledge_chunks_fts` (content, summary)

### 17.2 Chunk 级 API + FTS5
- 新增 `backend/api/knowledge_chunks_api.py`：
  - `GET /api/knowledge/chunks/{item_id}` — 返回某 item 的所有 chunk
  - `GET /api/knowledge/chunks/search?q=...` — FTS5 搜索，返回 chunk_index + 上下文
  - `POST /api/knowledge/chunks/generate/{item_id}` — 手动触发 chunk 切分（复用 trafilatura 段落）
- 修改 `search_knowledge` MCP tool 支持 chunk_index 返回

### 17.3 Chunk 级 UI
- 修改 `DeepReadMode.tsx`：高亮显示 chunk 段落边界，点击跳转到原文对应段落
- 在 `BriefingMode.tsx` 和 `ScanMode.tsx` 中显示 chunk 摘要预览

### 17.4 attention_score 计算
- 创建 `backend/services/attention_scorer.py`：
  - 5 维度加权评分：view_count (权重 0.25) / dwell_time (0.25) / scroll_depth (0.15) / is_favorited (0.20) / annotation_count (0.15)
  - `score(item_id) -> float` 返回 0~100 整数
  - `batch_score()` 批量更新
  - 结果写入 `knowledge_items.attention_score` 字段（新增列）

### 17.5 Attention 事件采集
- 创建 `backend/api/attention_events_api.py`：
  - `POST /api/attention/events` — 前端埋点上报
  - 事件类型：`view` / `dwell` / `scroll` / `favorite` / `annotation` / `share`
  - 事件写入 `attention_events` 表（新表）

### 17.6 Attention 聚合 job
- 新增 scheduler job: `attention_aggregate_job` — IntervalTrigger(seconds=1800) 每 30 分钟
- 聚合逻辑：读取 `attention_events` → 按 item_id 聚合 → 写入 `knowledge_items.attention_score`
- 保留 30 天窗口，过期事件清理

### 17.7 AttentionHeatmap 组件
- 创建 `frontend/src/components/knowledge/AttentionHeatmap.tsx`：
  - 30 天 × 24 小时热力图
  - 颜色深浅表示 attention 密度
  - 点击单元格跳转到对应日期的简报模式
  - 集成到 BriefingMode 侧边栏

### 17.8 整理模式（Outbox）UI
- 创建 `frontend/src/components/knowledge/OutboxMode.tsx`：
  - 清单视图：按 attention_score 降序排列待处理 item
  - 批量操作：标记已读、归档、生成摘要
  - 过滤：按 lifecycle 阶段 / 日期范围 / 评分

### 17.9 复习模式（SM-2）UI
- 创建 `frontend/src/components/knowledge/ReviewMode.tsx`：
  - 卡片翻转界面（正面 title，背面 content/summary）
  - 自评按钮 [0-5] 打分
  - 复用已有 `review_service.py` 的 SM-2 算法
  - 复用已有 `sm2_reviews` 表
  - 到期复习队列：`GET /api/reviews/due`
  - 提交评分：`POST /api/reviews/grade`

### 17.10 4 模式 UI 完善
- BriefingMode：集成 AttentionHeatmap 侧边栏
- ScanMode：显示 attention_score 徽章
- DeepReadMode：chunk 高亮 + 跳转
- AlertMode：与 attention_score 联动（高 attention 项优先显示）

### 17.11 路由 + 导航
- 新增前端路由：
  - `/knowledge/outbox` → OutboxMode
  - `/knowledge/review` → ReviewMode
  - `/knowledge/heatmap` → AttentionHeatmap
- 更新 KnowledgeTabs 导航栏：6 个标签（简报/扫描/深度/告警/整理/复习）

### 17.12 测试
- 后端测试：`test_chunks_api.py` / `test_attention_scorer.py` / `test_attention_events.py`
- 前端测试：`OutboxMode.test.tsx` / `ReviewMode.test.tsx` / `AttentionHeatmap.test.tsx`
- 更新现有 4 模式组件测试

## Impact

- **Affected code**:
  - `backend/repository/migrations/054_v2.0_chunks.sql` (新)
  - `backend/api/knowledge_chunks_api.py` (新)
  - `backend/api/attention_events_api.py` (新)
  - `backend/services/attention_scorer.py` (新)
  - `backend/scheduler/scheduler.py` (修改, 新增 attention_aggregate_job)
  - `backend/scheduler/jobs.py` (修改, 新增 attention_aggregate_job)
  - `backend/api/__init__.py` (修改, 注册新 router)
  - `frontend/src/components/knowledge/AttentionHeatmap.tsx` (新)
  - `frontend/src/components/knowledge/OutboxMode.tsx` (新)
  - `frontend/src/components/knowledge/ReviewMode.tsx` (新)
  - `frontend/src/components/knowledge/BriefingMode.tsx` (修改)
  - `frontend/src/components/knowledge/ScanMode.tsx` (修改)
  - `frontend/src/components/knowledge/DeepReadMode.tsx` (修改)
  - `frontend/src/components/knowledge/AlertMode.tsx` (修改)
  - `frontend/src/components/knowledge/KnowledgeTabs.tsx` (修改)
  - `frontend/src/App.tsx` (修改, 新路由)
- **Breaking changes**: 无
- **New dependencies**: 无

## Requirements

### knowledge_chunks 表
The system SHALL provide chunk-level paragraph storage for knowledge items.

#### Scenario: 创建 chunk
- **GIVEN** 一个 knowledge_item 有 content
- **WHEN** POST `/api/knowledge/chunks/generate/{item_id}`
- **THEN** 系统使用 trafilatura 段落切分，逐段写入 `knowledge_chunks` 表
- **AND** 返回 chunks 列表

#### Scenario: FTS5 搜索 chunk
- **GIVEN** `knowledge_chunks` 表有数据
- **WHEN** GET `/api/knowledge/chunks/search?q=keyword`
- **THEN** 返回匹配的 chunk 列表，含 item_id, chunk_index, content 片段

### attention_score
The system SHALL compute attention scores using 5 weighted dimensions.

#### Scenario: 事件上报
- **GIVEN** 用户阅读某知识条目
- **WHEN** 前端发送 `POST /api/attention/events { item_id, event_type: "view", ... }`
- **THEN** 事件写入 `attention_events` 表

#### Scenario: 聚合计算
- **GIVEN** `attention_events` 表有 30 天内事件
- **WHEN** `attention_aggregate_job` 运行
- **THEN** 计算每条 item 的 attention_score = Σ(维度值 × 权重)
- **AND** 写入 `knowledge_items.attention_score`

### 6 认知模式完整
The system SHALL provide all 6 cognitive modes in the UI.

#### Scenario: 整理模式
- **GIVEN** 用户登录
- **WHEN** 导航到 `/knowledge/outbox`
- **THEN** 显示 attention_score 降序排列的待处理 items
- **AND** 支持批量操作（标记已读、归档）

#### Scenario: 复习模式
- **GIVEN** 用户有到期复习的 items
- **WHEN** 导航到 `/knowledge/review`
- **THEN** 显示卡片翻转界面
- **AND** 用户评分后调用 `POST /api/reviews/grade`

## Performance Targets

| 任务 | 目标 | 当前值 |
|------|------|--------|
| chunk 切分 1000 字文章 | < 500ms | 无 |
| attention 聚合全量 items | < 30s | 无 |
| AttentionHeatmap 渲染 | < 200ms | 无 |
| FTS5 搜索 10000 chunk | < 100ms | 无 |