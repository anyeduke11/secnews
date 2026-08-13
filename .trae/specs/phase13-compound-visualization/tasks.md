# Tasks — Phase 13: 复利可视化 + 4 模式 + 规划引导

## 任务清单

### Group A: 复利仪表盘

- [x] Task A1: 创建 `backend/api/kl_compounding_api.py`
  - [x] `GET /api/kl/compounding` — 返回日/周/月趋势 + top concepts + trigger_health + stage_distribution
  - [x] 日趋势：按天统计 `ingested_at` 的 items 数量 + 平均 score
  - [x] 周/月趋势：按周/月聚合
  - [x] Top concepts：从 `knowledge_links` 统计 link_count 排序
  - [x] Trigger health：从 `kl_metrics` 获取 T1-T4 失败数 + 死信量
  - [x] Stage distribution：按 lifecycle 分组计数
  - [x] 注册到 `api/__init__.py`

- [x] Task A2: 创建 `frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx`
  - [x] 日/周/月趋势折线图（使用 recharts LineChart）
  - [x] Top concepts 排名列表
  - [x] 断点告警卡片（T1-T4 失败数 + 死信量）
  - [x] 阶段分布条形图
  - [x] 加载态 + 空态 + 错误态
  - [x] 集成到 `/knowledge/compound` 路由

### Group B: 4 种认知模式 UI

- [x] Task B1: 创建 `frontend/src/components/knowledge/BriefingMode.tsx`
  - [x] 今日摘要卡片（今日 kl:publish 的 items 列表）
  - [x] 数据源健康度显示
  - [x] 空态（无今日发布时引导到扫描模式）
  - [x] 路由 `/knowledge/briefing`

- [x] Task B2: 创建 `frontend/src/components/knowledge/ScanMode.tsx`
  - [x] 分类 + 标签 + 时间筛选列表
  - [x] 复用现有 HotspotGrid 组件逻辑
  - [x] 支持 lifecycle 阶段筛选
  - [x] 路由 `/knowledge/scan`

- [x] Task B3: 创建 `frontend/src/components/knowledge/DeepReadMode.tsx`
  - [x] 文章全屏阅读（标题 + 内容 + 元信息）
  - [x] 右侧栏：触发器状态进度条、关联概念、相关推荐
  - [x] 路由 `/knowledge/deep-read/:id`

- [x] Task B4: 创建 `frontend/src/components/knowledge/AlertMode.tsx`
  - [x] 红色横幅显示未读告警数
  - [x] 告警中心 Inbox（复用 AlertCenter 组件）
  - [x] 路由 `/knowledge/alert`

- [x] Task B5: 更新路由和导航
  - [x] 在 `App.tsx` 注册 4 个新路由
  - [x] 在知识库页面顶部添加模式选择器
  - [x] 确保 4 模式间可切换

### Group C: 触发器状态可视化

- [x] Task C1: 创建 `frontend/src/components/knowledge/LifecycleProgress.tsx`
  - [x] 5 阶段水平进度条组件
  - [x] 已完成（绿色勾）/ 当前（蓝色高亮）/ 待进行（灰色虚线）
  - [x] 各阶段颜色：raw=gray, refine=blue, link=purple, structure=orange, publish=green
  - [x] 可独立使用，接收 `currentStage` prop

- [x] Task C2: 集成 LifecycleProgress 到 DeepReadMode 和详情页
  - [x] 在 DeepReadMode 右侧栏显示
  - [x] 确保从 API 响应的 lifecycle 字段实时渲染

### Group D: KnowledgePlanningPanel

- [x] Task D1: 创建 migration `049_v2.0_planning_actions.sql`
  - [x] `planning_actions` 表（item_id, action_type, priority, status, etc.）
  - [x] `planning_action_log` 表（action_id, event, detail）
  - [x] 索引：status, item_id, created_at, action_id

- [x] Task D2: 创建 `backend/services/planning_service.py`
  - [x] `PlanningService` 类 + `generate_actions()` 方法
  - [x] 5 种规则生成逻辑（raw→read, refine→link, link→refine, structure→publish, publish→review）
  - [x] 去重检查（相同 item_id + action_type + status='pending' 不重复）
  - [x] 写入 planning_actions + planning_action_log 表

- [x] Task D3: 创建 `backend/api/kl_planning_api.py`
  - [x] `GET /api/kl/planning-actions` — 获取规划动作列表（支持 status 过滤）
  - [x] `PUT /api/kl/planning-actions/{id}/status` — 更新动作状态
  - [x] 注册到 `api/__init__.py`

- [x] Task D4: 创建 `frontend/src/components/knowledge/KnowledgePlanningPanel.tsx`
  - [x] 规划动作列表（按优先级排序）
  - [x] 动作类型图标/标签（read, review, link, refine, publish）
  - [x] 标记完成/忽略按钮
  - [x] 空态（无动作时显示建议）
  - [x] 可嵌入仪表盘顶部或侧边栏

### Group E: 调度器扩展

- [x] Task E1: 更新 `backend/scheduler/jobs.py`
  - [x] 新增 `planning_action_check_job()` — 600s 调度
  - [x] 更新 `__all__`

- [x] Task E2: 更新 `backend/scheduler/scheduler.py`
  - [x] job 36 — `planning_action_check`（IntervalTrigger, 600s）

### Group F: 测试

- [x] Task F1: 创建 4 模式组件测试（12 用例）
- [x] Task F2: 创建复利仪表盘测试（6 用例）
- [x] Task F3: 创建 KnowledgePlanningPanel 测试（5 用例）
- [x] Task F4: 创建 planning_action job 测试（8 用例）
- [x] Task F5: 全量回归测试
  - [x] 运行所有 Phase 13 测试（28 用例）
  - [x] 运行 Phase 12 回归测试（46 用例）
  - [x] 运行 Phase 10 回归测试（22 用例）
  - [x] 运行前端全量测试（270 用例）

## 任务依赖

- [Task A1] 无前置（独立）
- [Task A2] 依赖 [Task A1]
- [Task B1/B2/B3/B4] 无前置（独立，可并行）
- [Task B5] 依赖 [Task B1/B2/B3/B4]
- [Task C1] 无前置（独立）
- [Task C2] 依赖 [Task C1, B3]
- [Task D1] 无前置（独立）
- [Task D2] 依赖 [Task D1]
- [Task D3] 依赖 [Task D2]
- [Task D4] 依赖 [Task D3]
- [Task E1/E2] 依赖 [Task D2]
- [Task F1] 依赖 [Task B1/B2/B3/B4, C1]
- [Task F2] 依赖 [Task A2]
- [Task F3] 依赖 [Task D4]
- [Task F4] 依赖 [Task D2]
- [Task F5] 依赖 [Task F1-F4]

## 并行策略

**Group A-C**（核心 UI，可并行）:
- Task A1: 复利 API
- Task B1/B2/B3/B4: 4 模式组件（可并行）
- Task C1: 进度条组件
- Task D1: migration（无前置）

**Group D**（规划面板，无前置但链式）:
- Task D1 → D2 → D3 → D4

**Group E**（调度器，依赖 D2）:
- Task E1/E2: 规划 job 注册

**Group F**（测试，收尾串行）:
- Task F1-F4: 各模块测试（依赖对应模块实现）
- Task F5: 全量回归（依赖所有测试）