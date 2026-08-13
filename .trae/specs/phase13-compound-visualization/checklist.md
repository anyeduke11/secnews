# Checklist — Phase 13: 复利可视化 + 4 模式 + 规划引导

## 复利仪表盘
- [x] `GET /api/kl/compounding` 返回日/周/月趋势
- [x] `GET /api/kl/compounding` 返回 top concepts 排名
- [x] `GET /api/kl/compounding` 返回 trigger_health 指标
- [x] `GET /api/kl/compounding` 返回 stage_distribution
- [x] KnowledgeCompoundingDashboard 渲染趋势折线图
- [x] KnowledgeCompoundingDashboard 渲染 top concepts 列表
- [x] KnowledgeCompoundingDashboard 渲染断点告警卡片
- [x] KnowledgeCompoundingDashboard 渲染阶段分布图

## 4 种认知模式 UI
- [x] BriefingMode 渲染今日摘要卡片
- [x] BriefingMode 显示数据源健康度
- [x] BriefingMode 空态处理
- [x] ScanMode 渲染分类/标签/时间筛选列表
- [x] ScanMode 支持 lifecycle 阶段筛选
- [x] DeepReadMode 渲染文章全屏阅读
- [x] DeepReadMode 右侧栏显示关联信息
- [x] AlertMode 显示红色横幅 + 未读计数
- [x] AlertMode 渲染告警中心 Inbox
- [x] 4 模式路由正确注册（/knowledge/briefing, /scan, /deep-read/:id, /alert）

## 触发器状态可视化
- [x] LifecycleProgress 组件渲染 5 阶段水平进度条
- [x] 各阶段颜色正确：raw=gray, refine=blue, link=purple, structure=orange, publish=green
- [x] 已完成/当前/待进行状态区分正确
- [x] LifecycleProgress 集成到 DeepReadMode 右侧栏

## KnowledgePlanningPanel
- [x] migration 049 创建 `planning_actions` 表
- [x] migration 049 创建 `planning_action_log` 表
- [x] PlanningService.generate_actions() 实现 5 种规则
- [x] 去重检查（相同 item + action_type + pending 不重复）
- [x] `GET /api/kl/planning-actions` 返回规划动作列表
- [x] `PUT /api/kl/planning-actions/{id}/status` 更新动作状态
- [x] KnowledgePlanningPanel 渲染动作列表
- [x] 标记完成/忽略按钮功能正常

## 调度器
- [x] jobs.py 新增 `planning_action_check_job`（600s）
- [x] scheduler.py job 36 — `planning_action_check`

## 测试
- [x] 4 模式组件测试 12/12 PASS
- [x] 复利仪表盘测试 6/6 PASS
- [x] KnowledgePlanningPanel 测试 5/5 PASS
- [x] planning_action job 测试 8/8 PASS（含 API 测试）
- [x] Phase 12 回归测试 46/46 PASS
- [x] Phase 10 回归测试 22/22 PASS
- [x] 前端全量测试 270/270 PASS