# Checklist

## Phase 2.1: Hard/Soft Gate 分层
- [x] BaseGate 新增 `gate_type` 属性，类型为 `Literal["hard", "soft"]`
- [x] SchemaGate 设置 `gate_type = "hard"`
- [x] RecencyGate 设置 `gate_type = "hard"`
- [x] NoiseContentGate 设置 `gate_type = "hard"`
- [x] BidRecencyGate 设置 `gate_type = "hard"`
- [x] 其余 8 个 gate 保持 `gate_type = "soft"`
- [x] Pipeline 在 Hard gate 失败时立即拒绝，不继续跑后续门禁
- [x] Pipeline 在 Soft gate 失败时累加扣分，最终评分 < 阈值才拒绝
- [x] 拒绝条目写入 `quality_rejection_log` 表
- [x] 删除 `QualityConfig.url_check_sample_rate` 配置项
- [x] 编译检查通过
- [x] 现有质量门禁测试全部通过

## Phase 2.2: URL 全量校验（100%）
- [x] `CrawlUrlCheckRepo` 实现 `insert()` / `get_unchecked()` / `update_status()`
- [x] `url_batch_check_service.py` 实现批量异步校验（5 并发，指数退避）
- [x] `url_full_check_job` 注册到 scheduler.py（每 5 分钟）
- [x] Job 查询最近 24h 未校验条目并执行校验
- [x] 校验结果写入 `crawl_url_checks` 表
- [x] 更新 `hotspots.url_check_status` 字段
- [x] 编译检查通过
- [x] 调度器启动正常，不报错

## Phase 2.3: 三层去重上线
- [x] `canonicalize_url()` 函数实现 URL 规范化
- [x] 单元测试覆盖各种 URL 变体（尾部斜杠、fragment、www 前缀等）
- [x] `simhash()` 函数实现中文标题特征提取
- [x] simhash Hamming 距离计算正确
- [x] 单元测试验证 simhash 重复检测
- [x] `DuplicateGate` 新增第 2 层（simhash 标题）和第 3 层（content_hash 正文）
- [x] 三层去重顺序：URL → 标题 → 正文
- [x] 编译检查通过
- [x] 去重测试全部通过

## Phase 2.4: 审计视图前端
- [x] `GET /api/quality/rejection-log` 端点实现分页查询
- [x] 支持 gate_name / source_id / date_from / date_to 筛选
- [x] `GET /api/quality/rejection-stats` 端点实现按 gate 聚合统计
- [x] `QualityRejectionPage.tsx` 组件实现表格展示
- [x] 筛选面板：gate 下拉、source 搜索、日期范围
- [x] 统计卡片：总拒绝数、各 gate 拒绝占比
- [x] 集成到前端导航菜单
- [x] 前端编译通过（tsc --noEmit）

## 集成验证
- [x] 后端编译检查通过
- [x] 前端编译检查通过
- [x] 核心测试全部通过