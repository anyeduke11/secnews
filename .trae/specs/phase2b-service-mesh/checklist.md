# Phase 2b — CodeGarden Service Mesh 验证清单

> **spec**: `.trae/specs/phase2b-service-mesh/spec.md`
> **tasks**: `.trae/specs/phase2b-service-mesh/tasks.md`

## 1. 数据模型

- [ ] 1.1 迁移文件 `020_codegarden_phase2b.sql` 创建 4 张表（cg_services / cg_resources / cg_dependencies / cg_events）
- [ ] 1.2 8 个索引全部创建（cg_services_project / cg_services_status / cg_resources_type / cg_resources_owner / cg_deps_source / cg_deps_target / cg_events_type / cg_events_status / cg_events_created）
- [ ] 1.3 db.py init_db 加载 020 迁移
- [ ] 1.4 sqlite3 验证 4 张表存在 + 字段完整
- [ ] 1.5 _SCHEMA.md 追加 4 张表定义

## 2. Repository 层

- [ ] 2.1 CodegardenServiceRepository 实现 CRUD + list(project_id/status/namespace) + upsert_from_scan
- [ ] 2.2 CodegardenResourceRepository 实现 CRUD + list(type) + find_free_port + release_port
- [ ] 2.3 CodegardenDependencyRepository 实现 CRUD + impact_analysis
- [ ] 2.4 CodegardenEventRepository 实现 CRUD + list_pending + mark_processed
- [ ] 2.5 test_codegarden_service_repo.py 12/12 PASS
- [ ] 2.6 test_codegarden_resource_repo.py 10/10 PASS
- [ ] 2.7 test_codegarden_orchestration_repo.py 14/14 PASS

## 3. Service 层

- [ ] 3.1 CodegardenServiceService 实现 scan_local_services (lsof + docker + pm2) + restart + get_logs + get_metrics
- [ ] 3.2 CodegardenResourceService 实现 allocate_port (避开已占用 + 8898 保护) + encrypt_env_template
- [ ] 3.3 CodegardenOrchestrationService 实现 impact_analysis + publish_event + run_playbook

## 4. API 层

- [ ] 4.1 codegarden_services.py 注册 9 端点（services CRUD + restart + topology + logs + metrics）
- [ ] 4.2 codegarden_resources.py 注册 8 端点（resources + ports allocate/release + domains + volumes + env-templates）
- [ ] 4.3 codegarden_orchestration.py 注册 8 端点（dependencies CRUD + impact + events list/publish + playbooks list/run）
- [ ] 4.4 backend.main.app include_router 3 个新 router
- [ ] 4.5 OpenAPI schema 含全部 25 个新端点
- [ ] 4.6 release_port 对 8898 返回 403
- [ ] 4.7 test_codegarden_services_api.py 9/9 PASS
- [ ] 4.8 test_codegarden_resources_api.py 8/8 PASS
- [ ] 4.9 test_codegarden_orchestration_api.py 8/8 PASS

## 5. Scheduler

- [ ] 5.1 cg_service_scan_job 函数实现（调 scan_local_services）
- [ ] 5.2 cg_event_process_job 函数实现（处理 pending 事件）
- [ ] 5.3 scheduler.py 注册 job 16 (IntervalTrigger 300s)
- [ ] 5.4 scheduler.py 注册 job 17 (IntervalTrigger 60s)
- [ ] 5.5 jobs.__all__ 含 cg_service_scan_job / cg_event_process_job
- [ ] 5.6 启动后 scheduler.get_scheduler().get_jobs() 含 cg_service_scan / cg_event_process

## 6. sync_bundle 扩展

- [ ] 6.1 _read_cg_services_for_sync / _read_cg_resources_for_sync / _read_cg_dependencies_for_sync / _read_cg_events_for_sync 4 个函数实现
- [ ] 6.2 _apply_cg_services / _apply_cg_resources / _apply_cg_dependencies / _apply_cg_events 4 个函数实现
- [ ] 6.3 build_bundle 返回的 records 含 4 个新 key
- [ ] 6.4 apply_bundle 处理 4 个新表
- [ ] 6.5 sync_merge.validate_bundle 检查 4 个新 key
- [ ] 6.6 sync_merge.three_way_merge 处理 4 个新表
- [ ] 6.7 test_sync_merge.py 全 PASS（扩展后无回归）

## 7. 前端

- [ ] 7.1 npm install reactflow 成功
- [ ] 7.2 codegarden_phase2b.ts 类型定义完整
- [ ] 7.3 useCodegardenServices hook 实现
- [ ] 7.4 useCodegardenResources hook 实现
- [ ] 7.5 useCodegardenOrchestration hook 实现
- [ ] 7.6 ServiceMesh.tsx 主面板（列表 + 状态徽章 + 拓扑切换）
- [ ] 7.7 ServiceTopology.tsx (React Flow 渲染 nodes + edges)
- [ ] 7.8 ServiceDetailDialog.tsx (元数据 + 日志 + metrics + restart)
- [ ] 7.9 ResourceHub.tsx (4 tab: 端口/域名/卷/环境变量)
- [ ] 7.10 PortPool.tsx (8000-9999 网格 + 颜色映射 + 8898 保护色)
- [ ] 7.11 DependencyGraph.tsx (React Flow + 三类依赖边 + impact 分析)
- [ ] 7.12 EventBus.tsx (实时列表 + 筛选 + 发布)
- [ ] 7.13 PlaybookEditor.tsx (YAML 编辑 + 执行 + 历史)
- [ ] 7.14 App.tsx 3 条新路由注册
- [ ] 7.15 CodegardenPage 3 个入口卡片
- [ ] 7.16 Header 子导航
- [ ] 7.17 npm run build 0 错误

## 8. 测试

- [ ] 8.1 后端单测全 PASS（含 Phase 2a + Phase 2b 新增）
- [ ] 8.2 前端 vitest 全 PASS
- [ ] 8.3 前端 build 0 错误
- [ ] 8.4 e2e 测试 (test_codegarden_phase2b_e2e.py) PASS

## 9. 烟测路径

- [ ] 9.1 访问 /codegarden/services → 看到本机运行中服务列表（lsof/docker/pm2 三源合并）
- [ ] 9.2 切换到拓扑图 → 节点可拖拽 + 边显示依赖关系
- [ ] 9.3 点击服务节点 → 详情弹窗 + 日志 tail + restart 按钮
- [ ] 9.4 访问 /codegarden/resources → 端口池 tab 显示 8000-9999 占用状态
- [ ] 9.5 点击「分配端口」→ 返回最小可用端口 + 端口池对应格子变红
- [ ] 9.6 尝试释放 8898 → 返回 403 + 错误提示
- [ ] 9.7 访问 /codegarden/orchestration → 依赖图谱显示项目+服务节点 + 三类依赖边
- [ ] 9.8 点击节点 → 显示 impact 分析（下游影响 N 个项目）
- [ ] 9.9 EventBus tab → 发布 port_conflict 事件 → 60s 内 status 变 processed
- [ ] 9.10 PlaybookEditor → 加载 example.yml → 点击执行 → knowledge_tasks 新增 playbook_run task

## 10. 文档

- [ ] 10.1 AGENTS.md 关键决策节追加 Phase 2b 决策 1-10
- [ ] 10.2 AGENTS.md「明确不做」节标记 M2/M3/M4 已实现
- [ ] 10.3 codegarden/playbooks/ 目录初始化 + example.yml
- [ ] 10.4 PRD v2.0 §11.1 Phase 2b 行标注「✓ 已实现」
- [ ] 10.5 _SCHEMA.md 4 张新表定义完整

## 11. Commit 与提交

- [ ] 11.1 commit 数 ≥ 26 (按 Task 粒度)
- [ ] 11.2 git status 干净（除 .env / knowledge/ / export_cache/ 等运行时产物）
- [ ] 11.3 每个 commit message 符合格式: `feat/test/fix/docs/codegarden(scope): ...`

## 12. 回归

- [ ] 12.1 Phase 2a 既有功能无回归（test_codegarden_api.py / test_codegarden_repo.py / test_codegarden_e2e.py 全 PASS）
- [ ] 12.2 sync_bundle 双向同步 cg_* 8 张表（Phase 2a 5 张 + Phase 2b 4 张 - 重叠 cg_projects = 8）
- [ ] 12.3 既有 15 个 scheduler jobs 无回归 + 新增 job 16/17
- [ ] 12.4 前端既有路由无回归（/codegarden 仍可访问）
