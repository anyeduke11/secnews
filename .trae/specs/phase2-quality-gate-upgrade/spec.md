# Phase 2: 质量门禁升级 Spec

## Why

当前质量门禁系统存在三个问题：
1. **门禁无分层** — 所有门禁同等对待，Schema 校验失败和标题质量差走相同逻辑，无法区分"硬拒绝"和"软扣分"
2. **URL 校验仅抽样** — 10% 抽样率导致大量无效/不可达 URL 入库，影响用户体验
3. **去重层单一** — 仅 URL hash + 标题 Jaccard，缺少 simhash 跨源标题去重和 content_hash 正文去重
4. **审计无前端** — `quality_rejection_log` 表已写入但无可视化查看界面

## What Changes

### Phase 2.1 — Hard/Soft Gate 分层

- **BaseGate 新增 `gate_type` 属性**：`"hard"` | `"soft"`
  - Hard gate 失败 → 立即拒绝，写入 `quality_rejection_log`，不继续跑后续门禁
  - Soft gate 失败 → 累加扣分，最终评分 < 阈值才拒绝
- **Hard Gate 列表**：
  - `SchemaGate` — Schema 校验不通过
  - `RecencyGate` — 时效性校验（本周一 00:00 之前发布的资讯）
  - `NoiseContentGate` — 噪音内容（备案/版权/招聘等）
  - `BidRecencyGate` — 标讯时效性（标题年份段）
- **Soft Gate 列表**：
  - `ContentQualityGate`, `CategoryMatchGate`, `TitleSummaryGate`
  - `URLValidityGate`, `SourceReputationGate`, `AuthorVerificationGate`
  - `FinalUrlGate`, `DuplicateGate`
- **Pipeline 逻辑变更**：
  - Hard gate 失败 → `PipelineResult.accepted = False`，立即抛异常
  - Soft gate 失败 → 累加扣分，最终决定
  - 拒绝条目写入 `quality_rejection_log`（已有逻辑，复用）
- **BREAKING**: `PipelineResult` 中 rejected_by 字段现在记录首个失败的 Hard gate 名称

### Phase 2.2 — URL 全量校验（100%）

- 创建 `CrawlUrlCheckRepo` 仓储层，写入 `crawl_url_checks` 表
- 创建 `url_full_check_job` 调度任务（每 5 分钟跑一次）
  - 查询最近 24h 内入库且尚未校验的 `hotspots` 条目
  - 对每个条目执行 HEAD 请求（5s 超时）
  - 结果写入 `crawl_url_checks`（item_id, url, status_code, checked_at）
  - 更新 `hotspots.url_check_status` = `verified` / `unreachable`
- 创建 `url_batch_check_service.py` 批量校验服务
  - 并发控制：5 并发，指数退避
  - 失败重试：最多 2 次
- 移除 `QualityConfig.url_check_sample_rate` 配置（不再需要抽样率）

### Phase 2.3 — 三层去重上线

- **第 1 层 — URL 规范化**：
  - 创建 `canonicalize_url()` 函数
  - 规则：移除尾部斜杠、小写 host、移除 fragment、移除 `www.` 前缀
  - 在 `DuplicateGate` 中应用 canonical URL 进行去重比较
- **第 2 层 — simhash 标题去重**：
  - 创建 `simhash()` 计算函数
  - 标题 tokenize → 特征向量 → simhash 值
  - Hamming 距离 < 5 视为重复
  - 范围：最近 30 天的标题
  - 存储 simhash 值到 `raw_items` 表或独立的 `url_checks` 表
- **第 3 层 — content_hash 正文去重**：
  - 使用 `raw_items.content_hash`（SHA256 of full content）
  - 同内容不同 URL → 去重
  - 范围：最近 30 天
- **DuplicateGate 更新**：
  - 新增 `simhash_threshold` 参数（默认 5）
  - 新增 `content_hash_dedup` 开关
  - 三层顺序：URL → 标题 → 正文

### Phase 2.4 — 审计视图前端

- 创建 `QualityRejectionPage.tsx` 前端组件
  - 表格展示 `quality_rejection_log` 记录
  - 筛选条件：gate 名称、source_id、日期范围
  - 统计指标：各 gate 拒绝次数、拒绝率趋势
- 创建 `QualityRejectionApi` API 端点
  - `GET /api/quality/rejection-log` — 分页查询 rejection log
  - `GET /api/quality/rejection-stats` — 按 gate 聚合统计
  - 注册到 `api/quality.py`
- 集成到前端导航

## Impact

- Affected specs: 质量门禁系统、URL 校验系统、去重系统、审计视图
- Affected code:
  - `backend/quality/base.py` — BaseGate 新增 gate_type
  - `backend/quality/pipeline.py` — Hard/Soft 分层逻辑
  - `backend/quality/duplicate_gate.py` — 三层去重增强
  - `backend/repository/` — 新增 CrawlUrlCheckRepo
  - `backend/services/` — 新增 url_batch_check_service.py
  - `backend/scheduler/jobs.py` — 新增 url_full_check_job
  - `backend/quality/config.py` — 移除 url_check_sample_rate
  - `frontend/src/components/` — 新增 QualityRejectionPage.tsx
  - `backend/api/quality.py` — 新增 rejection log 端点

## ADDED Requirements

### Requirement: Hard/Soft Gate 分层
The system SHALL classify quality gates into hard (immediate reject) and soft (score-based).

#### Scenario: Hard gate failure
- **WHEN** a Hard gate (Schema, Recency, NoiseContent, BidRecency) fails
- **THEN** the item is immediately rejected, written to `quality_rejection_log`, and no further gates are checked

#### Scenario: Soft gate failure
- **WHEN** a Soft gate fails
- **THEN** the score deduction is accumulated, and the item is only rejected if the final score is below the threshold

### Requirement: URL 全量校验
The system SHALL perform URL validity checks on 100% of new items, not just a sample.

#### Scenario: New item URL check
- **WHEN** a new item is inserted into hotspots
- **THEN** within 5 minutes, the URL check job runs a HEAD request and writes results to `crawl_url_checks`

#### Scenario: URL check result
- **WHEN** the URL check completes
- **THEN** `hotspots.url_check_status` is updated to `verified` or `unreachable`

### Requirement: 三层去重
The system SHALL implement three-layer deduplication: URL canonicalization, simhash title, and content_hash body.

#### Scenario: URL canonicalization
- **WHEN** two items have URLs that differ only by trailing slash or fragment
- **THEN** they are considered duplicates

#### Scenario: simhash title dedup
- **WHEN** two items have titles with simhash Hamming distance < 5
- **THEN** they are considered duplicates

### Requirement: 审计视图前端
The system SHALL provide a frontend page to view quality rejection logs.

#### Scenario: View rejection log
- **WHEN** a user navigates to the quality rejection page
- **THEN** they see a table of rejected items, filterable by gate, source, and date

## MODIFIED Requirements

### Requirement: QualityGatePipeline
The pipeline SHALL run Hard gates first, and if any Hard gate fails, skip remaining Soft gates for that item.

### Requirement: URLValidityGate
The gate SHALL remain as a Soft gate (score deduction), while a separate scheduler job handles the 100% URL check.