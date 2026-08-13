# Tasks

## Phase 2.1: Hard/Soft Gate 分层
- [x] Task 2.1.1: BaseGate 新增 `gate_type` 属性（`"hard"` | `"soft"`），默认 `"soft"`
  - 为每个现有 gate 设置 gate_type：SchemaGate/RecencyGate/NoiseContentGate/BidRecencyGate → `"hard"`，其余 → `"soft"`
- [x] Task 2.1.2: Pipeline 逻辑改造
  - Hard gate 失败 → 立即 `accepted=False`，写入 `quality_rejection_log`，跳过后续门禁
  - Soft gate 失败 → 累加扣分，最终评分 < 阈值才拒绝
  - 拒绝原因记录首个失败的 Hard gate 名称
- [x] Task 2.1.3: 质量门禁配置更新
  - 删除 `QualityConfig.url_check_sample_rate` 配置项
  - 新增 `QualityConfig.hard_gate_ids` 可配置硬门禁列表

## Phase 2.2: URL 全量校验（100%）
- [x] Task 2.2.1: 创建 `CrawlUrlCheckRepo` 仓储层
  - `insert(item_id, url, status_code, title_match_score)` — 写入 `crawl_url_checks`
  - `get_unchecked(since_minutes)` — 查询最近 N 分钟未校验的条目
  - `update_status(item_id, status_code, title_match_score)` — 更新校验结果
- [x] Task 2.2.2: 创建 `url_batch_check_service.py` 批量校验服务
  - 异步批量校验：5 并发，指数退避，最多 2 次重试
  - 调用 `URLValidityGate._head_status` / `_get_status` 进行校验
  - 更新 `hotspots.url_check_status` 和 `crawl_url_checks` 表
- [x] Task 2.2.3: 创建 `url_full_check_job` 调度任务（每 5 分钟）
  - 查询最近 24h 内 `url_check_status IS NULL` 的条目
  - 调用批量校验服务
  - 注册到 scheduler.py
- [x] Task 2.2.4: 移除 `QualityConfig.url_check_sample_rate` 及相关引用

## Phase 2.3: 三层去重上线
- [x] Task 2.3.1: 创建 `canonicalize_url()` URL 规范化函数
  - 规则：移除尾部斜杠、小写 host、移除 fragment、移除 `www.` 前缀
  - 单元测试覆盖各种 URL 变体
- [x] Task 2.3.2: 创建 `simhash()` 标题重复检测函数
  - 中文 tokenize → 特征向量 → simhash 值
  - Hamming 距离计算
  - 单元测试验证
- [x] Task 2.3.3: 更新 `DuplicateGate` 支持三层去重
  - 第 1 层：URL canonicalization 比较
  - 第 2 层：simhash 标题（Hamming < 5），范围最近 30 天
  - 第 3 层：content_hash 正文（查询 `raw_items` 表），范围最近 30 天
  - 新增 `simhash_threshold` 参数

## Phase 2.4: 审计视图前端
- [x] Task 2.4.1: 创建 `GET /api/quality/rejection-log` API 端点
  - 分页查询 `quality_rejection_log` 表
  - 筛选参数：gate_name, source_id, date_from, date_to, page, page_size
  - 按 `created_at DESC` 排序
- [x] Task 2.4.2: 创建 `GET /api/quality/rejection-stats` API 端点
  - 按 gate 名称聚合统计拒绝次数
  - 按日期聚合拒绝率趋势
- [x] Task 2.4.3: 创建 `QualityRejectionPage.tsx` 前端组件
  - 表格展示 rejection log 记录（source_id, item_title, rejected_by, reason, created_at）
  - 筛选面板：gate 下拉选择、source 搜索、日期范围选择
  - 统计卡片：总拒绝数、各 gate 拒绝占比、拒绝率趋势图
- [x] Task 2.4.4: 集成到前端导航菜单

# Task Dependencies
- [Task 2.1.2] depends on [Task 2.1.1]
- [Task 2.2.2] depends on [Task 2.2.1]
- [Task 2.2.3] depends on [Task 2.2.2]
- [Task 2.3.3] depends on [Task 2.3.1, Task 2.3.2]
- [Task 2.4.1] depends on [Task 2.1.2] (gate 名称定义)
- [Task 2.4.2] depends on [Task 2.4.1]
- [Task 2.4.3] depends on [Task 2.4.1, Task 2.4.2]
- [Task 2.4.4] depends on [Task 2.4.3]