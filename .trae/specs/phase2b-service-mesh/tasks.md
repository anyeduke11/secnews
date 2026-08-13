# Phase 2b — CodeGarden Service Mesh 任务分解

> **spec**: `.trae/specs/phase2b-service-mesh/spec.md`
> **Group 划分**: A(schema) → B(repo) → C(service) → D(api) → E(scheduler) → F(sync_bundle) → G(frontend) → H(test)

## Group A: DB Schema

### Task A1: 迁移文件 021_codegarden_phase2b.sql

**Files:**
- Create: `backend/repository/migrations/021_codegarden_phase2b.sql`

注: db.py 的 _apply_migrations 自动扫描 migrations/*.sql 按字典序加载，无需修改 db.py。

- [ ] **Step 1**: 创建迁移文件，含 4 张表（cg_services / cg_resources / cg_dependencies / cg_events）+ 8 个索引，SQL 内容见 spec §3.1
- [ ] **Step 2**: 手动执行迁移验证：`.venv/bin/python -c "from backend.repository.db import init_db; init_db()"`
- [ ] **Step 3**: sqlite3 验证 4 张表存在：`sqlite3 backend/hotspot.db ".tables" | grep cg_`
- [ ] **Step 4**: Commit: `feat(codegarden): A1 add 4 cg_ tables for Phase 2b (services/resources/dependencies/events)`

### Task A2: _SCHEMA.md 扩展

**Files:**
- Modify: `knowledge/_SCHEMA.md`

- [ ] **Step 1**: 追加 cg_services / cg_resources / cg_dependencies / cg_events 4 张表的字段定义
- [ ] **Step 2**: Commit: `docs(codegarden): A2 extend _SCHEMA.md with Phase 2b tables`

## Group B: Repository 层

### Task B1: CodegardenServiceRepository

**Files:**
- Create: `backend/repository/codegarden_service_repo.py`
- Create: `backend/tests/test_codegarden_service_repo.py`

- [ ] **Step 1**: 实现 CodegardenServiceRepository（cg_services 表 CRUD + 多维筛选 list(project_id/status/namespace) + upsert_from_scan）
- [ ] **Step 2**: 写 12 个单测（CRUD 7 + list 筛选 3 + upsert_from_scan 2）
- [ ] **Step 3**: 运行：`.venv/bin/python -m pytest backend/tests/test_codegarden_service_repo.py -v`
- [ ] **Step 4**: Commit: `feat(codegarden): B1 add CodegardenServiceRepository + 12 unit tests`

### Task B2: CodegardenResourceRepository

**Files:**
- Create: `backend/repository/codegarden_resource_repo.py`
- Create: `backend/tests/test_codegarden_resource_repo.py`

- [ ] **Step 1**: 实现 CodegardenResourceRepository（cg_resources 表 CRUD + 按 type 筛选 + find_free_port + release_port）
- [ ] **Step 2**: 写 10 个单测（CRUD 5 + find_free_port 3 + release 2）
- [ ] **Step 3**: 运行：`.venv/bin/python -m pytest backend/tests/test_codegarden_resource_repo.py -v`
- [ ] **Step 4**: Commit: `feat(codegarden): B2 add CodegardenResourceRepository + 10 unit tests`

### Task B3: CodegardenDependencyRepository + CodegardenEventRepository

**Files:**
- Create: `backend/repository/codegarden_orchestration_repo.py`
- Create: `backend/tests/test_codegarden_orchestration_repo.py`

- [ ] **Step 1**: 实现 CodegardenDependencyRepository（cg_dependencies CRUD + impact_analysis 递归查询）+ CodegardenEventRepository（cg_events CRUD + list_pending + mark_processed）
- [ ] **Step 2**: 写 14 个单测（dependencies 8 + events 6）
- [ ] **Step 3**: 运行：`.venv/bin/python -m pytest backend/tests/test_codegarden_orchestration_repo.py -v`
- [ ] **Step 4**: Commit: `feat(codegarden): B3 add dependency + event repositories + 14 unit tests`

## Group C: Service 层

### Task C1: CodegardenServiceService（服务网格业务）

**Files:**
- Create: `backend/services/codegarden_service_service.py`

- [ ] **Step 1**: 实现 CodegardenServiceService（委托 repo + scan_local_services 调 lsof/docker/pm2 + restart_service 创建 task + get_logs 调 docker logs/tail + get_metrics 调 psutil）
- [ ] **Step 2**: scan_local_services 子方法：_scan_lsof() / _scan_docker() / _scan_pm2()，各返回 [{name, port, pid, runtime}] 列表，合并后 upsert_from_scan
- [ ] **Step 3**: restart_service 创建 knowledge_tasks (task_type=service_restart, params={service_id, action:restart})
- [ ] **Step 4**: Commit: `feat(codegarden): C1 add CodegardenServiceService with local scan + restart + logs + metrics`

### Task C2: CodegardenResourceService（资源中枢业务）

**Files:**
- Create: `backend/services/codegarden_resource_service.py`

- [ ] **Step 1**: 实现资源 CRUD + allocate_port（避开已占用 + 8898 保护 + 8000-9999 范围）+ release_port（8898 拒绝 403）+ encrypt_env_template（复用 secrets_service Fernet）
- [ ] **Step 2**: allocate_port 算法：扫描 cg_resources.type=port 已分配 + lsof 实时占用，返回最小可用端口
- [ ] **Step 3**: env_template 敏感字段加密：value JSON 中 key 含 password/secret/token 的字段用 Fernet 加密
- [ ] **Step 4**: Commit: `feat(codegarden): C2 add CodegardenResourceService with port allocation + env encryption`

### Task C3: CodegardenOrchestrationService（联动引擎业务）

**Files:**
- Create: `backend/services/codegarden_orchestration_service.py`

- [ ] **Step 1**: 实现 依赖图谱 CRUD + impact_analysis（递归查 cg_dependencies.target_id=X 的所有上游 source）+ 事件发布/查询 + Playbook YAML 解析与执行
- [ ] **Step 2**: publish_event 同时创建 knowledge_tasks (task_type=event_handler, params={event_id})
- [ ] **Step 3**: run_playbook 解析 YAML steps[]，创建 knowledge_tasks (task_type=playbook_run, params={playbook_name, steps})
- [ ] **Step 4**: Commit: `feat(codegarden): C3 add orchestration service with impact analysis + event bus + playbook`

## Group D: API 层

### Task D1: codegarden_services.py 路由（M2，9 端点）

**Files:**
- Create: `backend/api/codegarden_services.py`
- Modify: `backend/main.py` (include_router)

- [ ] **Step 1**: 实现 9 个端点（services CRUD + restart + topology + logs + metrics），prefix=/api/codegarden
- [ ] **Step 2**: 在 backend.main.app 中 include_router(codegarden_services.router)
- [ ] **Step 3**: Commit: `feat(codegarden): D1 add 9 service mesh API endpoints`

### Task D2: codegarden_resources.py 路由（M3，8 端点）

**Files:**
- Create: `backend/api/codegarden_resources.py`
- Modify: `backend/main.py`

- [ ] **Step 1**: 实现 8 个端点（resources 列表/创建 + ports allocate/release + domains CRUD + volumes + env-templates）
- [ ] **Step 2**: release_port 对 8898 返回 403
- [ ] **Step 3**: include_router
- [ ] **Step 4**: Commit: `feat(codegarden): D2 add 8 resource hub API endpoints`

### Task D3: codegarden_orchestration.py 路由（M4，8 端点）

**Files:**
- Create: `backend/api/codegarden_orchestration.py`
- Modify: `backend/main.py`

- [ ] **Step 1**: 实现 8 个端点（dependencies CRUD + impact + events list/publish + playbooks list/run）
- [ ] **Step 2**: include_router
- [ ] **Step 3**: Commit: `feat(codegarden): D3 add 8 orchestration engine API endpoints`

### Task D4: API 单测（25 测试）

**Files:**
- Create: `backend/tests/test_codegarden_services_api.py` (9 测试)
- Create: `backend/tests/test_codegarden_resources_api.py` (8 测试)
- Create: `backend/tests/test_codegarden_orchestration_api.py` (8 测试)

- [ ] **Step 1**: 写 25 个 API 测试，复用 test_codegarden_api.py 的 fixture 模式
- [ ] **Step 2**: 运行：`.venv/bin/python -m pytest backend/tests/test_codegarden_*_api.py -v`
- [ ] **Step 3**: Commit: `test(codegarden): D4 add 25 API tests for Phase 2b endpoints`

## Group E: Scheduler

### Task E1: cg_service_scan_job（job 16）

**Files:**
- Modify: `backend/scheduler/jobs.py`

- [ ] **Step 1**: 新增 cg_service_scan_job async 函数，调 CodegardenServiceService.scan_local_services()
- [ ] **Step 2**: 在 __all__ 追加
- [ ] **Step 3**: Commit: `feat(codegarden): E1 add cg_service_scan_job (every 5min)`

### Task E2: cg_event_process_job（job 17）

**Files:**
- Modify: `backend/scheduler/jobs.py`

- [ ] **Step 1**: 新增 cg_event_process_job async 函数，查 cg_events.status=pending，按 event_type 路由到处理器（port_conflict → allocate_port + 通知）
- [ ] **Step 2**: 在 __all__ 追加
- [ ] **Step 3**: Commit: `feat(codegarden): E2 add cg_event_process_job (every 60s)`

### Task E3: scheduler.py 注册 job 16 + 17

**Files:**
- Modify: `backend/scheduler/scheduler.py`

- [ ] **Step 1**: 注册 job 16: IntervalTrigger(seconds=300, id="cg_service_scan")
- [ ] **Step 2**: 注册 job 17: IntervalTrigger(seconds=60, id="cg_event_process")
- [ ] **Step 3**: 验证：`.venv/bin/python -c "import asyncio; from backend.scheduler.scheduler import HotspotScheduler; s=HotspotScheduler(None); ..."` (启动后检查 jobs)
- [ ] **Step 4**: Commit: `feat(codegarden): E3 register scheduler jobs 16/17`

## Group F: sync_bundle 扩展

### Task F1: sync_bundle 加入 4 张新表

**Files:**
- Modify: `backend/services/sync_bundle.py`

- [ ] **Step 1**: 追加 _read_cg_services_for_sync / _read_cg_resources_for_sync / _read_cg_dependencies_for_sync / _read_cg_events_for_sync 4 个辅助函数
- [ ] **Step 2**: 追加 _apply_cg_services / _apply_cg_resources / _apply_cg_dependencies / _apply_cg_events 4 个 apply 函数
- [ ] **Step 3**: build_bundle 的 records dict 追加 4 个 key
- [ ] **Step 4**: apply_bundle 追加 4 个表的 upsert
- [ ] **Step 5**: 在 sync_merge.validate_bundle 的 list 检查中追加 4 个 key
- [ ] **Step 6**: Commit: `feat(codegarden): F1 extend sync_bundle with 4 new cg_ tables`

### Task F2: sync_merge 3-way merge 扩展

**Files:**
- Modify: `backend/services/sync_merge.py`

- [ ] **Step 1**: three_way_merge 的 list-typed 循环追加 4 张表（cg_services / cg_resources / cg_dependencies / cg_events）
- [ ] **Step 2**: key_fn 定义：cg_services 用 id / cg_resources 用 type+value / cg_dependencies 用 source+target+dep_type / cg_events 用 id
- [ ] **Step 3**: 运行：`.venv/bin/python -m pytest backend/tests/test_sync_merge.py -v`
- [ ] **Step 4**: Commit: `feat(codegarden): F2 extend sync_merge with 4 new tables (3-way merge)`

## Group G: 前端

### Task G1: 引入 React Flow + 类型定义

**Files:**
- Modify: `frontend/package.json` (npm install reactflow)
- Create: `frontend/src/types/codegarden_phase2b.ts`

- [ ] **Step 1**: `cd frontend && npm install reactflow`
- [ ] **Step 2**: 定义 CgService / CgResource / CgDependency / CgEvent / Playbook 类型
- [ ] **Step 3**: Commit: `feat(codegarden): G1 add reactflow dep + Phase 2b types`

### Task G2: useCodegardenServices hook

**Files:**
- Create: `frontend/src/hooks/useCodegardenServices.ts`

- [ ] **Step 1**: 实现 hook（list services + filters + restart + topology）
- [ ] **Step 2**: Commit: `feat(codegarden): G2 add useCodegardenServices hook`

### Task G3: useCodegardenResources hook

**Files:**
- Create: `frontend/src/hooks/useCodegardenResources.ts`

- [ ] **Step 1**: 实现 hook（list resources + allocate port + release port + env-templates）
- [ ] **Step 2**: Commit: `feat(codegarden): G3 add useCodegardenResources hook`

### Task G4: useCodegardenOrchestration hook

**Files:**
- Create: `frontend/src/hooks/useCodegardenOrchestration.ts`

- [ ] **Step 1**: 实现 hook（list dependencies + impact analysis + events + playbooks）
- [ ] **Step 2**: Commit: `feat(codegarden): G4 add useCodegardenOrchestration hook`

### Task G5: ServiceMesh 主面板

**Files:**
- Create: `frontend/src/components/codegarden/ServiceMesh.tsx`

- [ ] **Step 1**: 实现 服务列表（name/namespace/type/runtime/status/endpoint）+ 状态徽章 + 刷新按钮 + 切换到拓扑图视图
- [ ] **Step 2**: Commit: `feat(codegarden): G5 add ServiceMesh panel`

### Task G6: ServiceTopology 拓扑图

**Files:**
- Create: `frontend/src/components/codegarden/ServiceTopology.tsx`

- [ ] **Step 1**: 用 React Flow 渲染 nodes（services） + edges（dependencies），按 runtime 分色，status running=绿/stopped=灰/error=红
- [ ] **Step 2**: Commit: `feat(codegarden): G6 add ServiceTopology (React Flow)`

### Task G7: ServiceDetailDialog 服务详情

**Files:**
- Create: `frontend/src/components/codegarden/ServiceDetailDialog.tsx`

- [ ] **Step 1**: 实现 详情弹窗（元数据网格 + 日志 tail + metrics 图表 + restart 按钮）
- [ ] **Step 2**: Commit: `feat(codegarden): G7 add ServiceDetailDialog with logs + metrics`

### Task G8: ResourceHub 主面板

**Files:**
- Create: `frontend/src/components/codegarden/ResourceHub.tsx`

- [ ] **Step 1**: 实现 4 tab（端口/域名/卷/环境变量）+ 端口分配/释放按钮
- [ ] **Step 2**: Commit: `feat(codegarden): G8 add ResourceHub panel (4 tabs)`

### Task G9: PortPool 端口池视图

**Files:**
- Create: `frontend/src/components/codegarden/PortPool.tsx`

- [ ] **Step 1**: 实现 端口范围网格（8000-9999，每格 100 端口）+ 颜色映射（free=绿/allocated=红/reserved=黄/8898=蓝保护）
- [ ] **Step 2**: Commit: `feat(codegarden): G9 add PortPool view (8000-9999 grid)`

### Task G10: DependencyGraph 依赖图谱

**Files:**
- Create: `frontend/src/components/codegarden/DependencyGraph.tsx`

- [ ] **Step 1**: 用 React Flow 渲染 项目+服务节点 + 三类依赖边（code=蓝/service=绿/data=橙），点击节点显示 impact 分析
- [ ] **Step 2**: Commit: `feat(codegarden): G10 add DependencyGraph (React Flow)`

### Task G11: EventBus 事件流

**Files:**
- Create: `frontend/src/components/codegarden/EventBus.tsx`

- [ ] **Step 1**: 实现 事件实时列表（type/source/status/created_at）+ 按 type 筛选 + 手动发布事件按钮
- [ ] **Step 2**: Commit: `feat(codegarden): G11 add EventBus stream panel`

### Task G12: PlaybookEditor

**Files:**
- Create: `frontend/src/components/codegarden/PlaybookEditor.tsx`

- [ ] **Step 1**: 实现 Playbook YAML 编辑器（左侧列表 + 右侧编辑区）+ 执行按钮 + 执行历史查看
- [ ] **Step 2**: Commit: `feat(codegarden): G12 add PlaybookEditor with YAML edit + run history`

### Task G13: 路由 + CodegardenPage 入口卡片

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/CodegardenPage.tsx`
- Modify: `frontend/src/components/Header.tsx`

- [ ] **Step 1**: App.tsx 追加 3 条路由：/codegarden/services /codegarden/resources /codegarden/orchestration
- [ ] **Step 2**: CodegardenPage 加 3 个入口卡片
- [ ] **Step 3**: Header 加 3 个子导航或下拉
- [ ] **Step 4**: Commit: `feat(codegarden): G13 add 3 routes + CodegardenPage entry cards + Header nav`

### Task G14: 前端 build 验证

**Files:** 无修改

- [ ] **Step 1**: `cd frontend && npm run build`
- [ ] **Step 2**: 验证 0 errors（预计 modules 数 +30 左右）
- [ ] **Step 3**: Commit（如有修复）: `fix(codegarden): G14 frontend build cleanup`

## Group H: 测试套件

### Task H1: API 单测（已在 D4 完成）

- [ ] **Step 1**: 验证 test_codegarden_services_api.py / test_codegarden_resources_api.py / test_codegarden_orchestration_api.py 全 PASS（25 测试）

### Task H2: 前端组件测试

**Files:**
- Create: `frontend/src/components/codegarden/ServiceMesh.test.tsx`
- Create: `frontend/src/components/codegarden/PortPool.test.tsx`
- Create: `frontend/src/components/codegarden/DependencyGraph.test.tsx`

- [ ] **Step 1**: 每个 test 文件 6-8 个测试（render / filter / click / mock fetch）
- [ ] **Step 2**: `cd frontend && npx vitest run src/components/codegarden`
- [ ] **Step 3**: Commit: `test(codegarden): H2 add 3 frontend component test files (20+ tests)`

### Task H3: e2e 测试 — 服务→资源→依赖→事件全流程

**Files:**
- Create: `backend/tests/test_codegarden_phase2b_e2e.py`

- [ ] **Step 1**: 测试场景：创建 project → 注册 service → 分配 port → 建立依赖 → 发布事件 → 验证事件被处理
- [ ] **Step 2**: 运行：`.venv/bin/python -m pytest backend/tests/test_codegarden_phase2b_e2e.py -v`
- [ ] **Step 3**: Commit: `test(codegarden): H3 add e2e test for service→resource→dependency→event flow`

## Group I: 文档与收尾

### Task I1: AGENTS.md 更新

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1**: 关键决策节追加 Phase 2b：记录决策 1-10
- [ ] **Step 2**: 「明确不做」节标记 M2/M3/M4 已实现
- [ ] **Step 3**: Commit: `docs(codegarden): I1 update AGENTS.md with Phase 2b decisions`

### Task I2: codegarden/playbooks/ 目录初始化

**Files:**
- Create: `codegarden/playbooks/.gitkeep`
- Create: `codegarden/playbooks/example.yml`

- [ ] **Step 1**: 创建目录 + 示例 Playbook（9 步：clone → npm install → test → build → 分配端口 → pm2 start → nginx → 注册服务网格 → 通知）
- [ ] **Step 2**: Commit: `feat(codegarden): I2 init codegarden/playbooks/ with example.yml`

### Task I3: PRD v2.0 标注 Phase 2b 已实现

**Files:**
- Modify: `docs/CodeGarden_PRD_v2.0.md`

- [ ] **Step 1**: §11.1 路线图表格 Phase 2b 行追加「✓ 已实现」标注
- [ ] **Step 2**: Commit: `docs(codegarden): I3 mark Phase 2b as done in PRD v2.0`

## 总计

- **任务数**: 26 (A:2 + B:3 + C:3 + D:4 + E:3 + F:2 + G:14 + H:3 + I:3)
- **预期 commit 数**: 26
- **预期新增表**: 4
- **预期新增 API**: 25
- **预期新增前端组件**: 8
- **预期新增测试**: 80+ (25 API + 20+ frontend + 14 repo + 24 service-level + 3 e2e)
