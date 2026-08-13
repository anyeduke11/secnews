# Phase 2b — CodeGarden Service Mesh MVP Spec

> **版本**: v1.6 (Phase 2b)
> **范围**: M2 服务网格 + M3 资源中枢 + M4 联动引擎
> **依赖**: Phase 2a (CodeGarden MVP) 已完成
> **spec 路径**: `.trae/specs/phase2b-service-mesh/`

## 1. 目标

在 Phase 2a 项目看板基础上，补齐本机服务/资源/联动三层能力，使 CodeGarden 从「项目登记簿」升级为「本机工作站」：

- **M2 服务网格**：自动发现本机服务（lsof/docker/pm2），统一查看运行状态、端口、健康检查
- **M3 资源中枢**：管理端口池/域名映射/环境变量模板/存储卷，端口冲突检测
- **M4 联动引擎**：项目/服务依赖图谱 + 事件总线 + Playbook 自动化工作流

## 2. 范围

### 2.1 必做（Phase 2b 内交付）

**M2 服务网格**
- `cg_services` 表 CRUD + 健康检查 + 自动发现
- 9 个 API 端点（services CRUD + restart + topology + logs + metrics）
- 定时任务 `cg_service_scan`（每 5 分钟扫描本机服务）
- 前端：ServiceMesh 主面板 + ServiceTopology 拓扑图（React Flow）

**M3 资源中枢**
- `cg_resources` 表 CRUD（4 类资源：port/domain/env_template/volume）
- 8 个 API 端点（端口池/分配/释放 + 域名映射/卷 + 环境变量模板）
- hotspot 端口 8898 受保护，禁止释放
- 敏感环境变量复用 secrets_service Fernet 加密
- 前端：ResourceHub 主面板 + PortPool 端口池视图

**M4 联动引擎**
- `cg_dependencies` 表（依赖图谱）+ `cg_events` 表（事件总线）
- 依赖图谱 API（CRUD + 影响分析查询）
- 事件总线 API（发布 + 查询 + 订阅 webhook）
- Playbook YAML 存 `codegarden/playbooks/`，执行复用 `knowledge_tasks`
- 前端：DependencyGraph 依赖图谱 + EventBus 事件流 + PlaybookEditor

### 2.2 明确不做（推迟到 Phase 2c/2d）

- AI 协作功能（M7-M12）→ Phase 2c
- 项目归档 30 天自动停止服务（依赖 M5 生命周期）→ Phase 2d
- 跨机服务网格（本 Phase 仅本机）

## 3. 数据模型

### 3.1 新增 4 张表

```sql
-- 迁移文件: 021_codegarden_phase2b.sql

-- M2 服务网格
CREATE TABLE IF NOT EXISTS cg_services (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES cg_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    namespace TEXT,                    -- 如 ai-assistant.web
    type TEXT NOT NULL,                -- http / websocket / grpc / static / database
    runtime TEXT NOT NULL,             -- docker / pm2 / system / bare
    status TEXT NOT NULL,              -- running / stopped / error / unknown
    endpoint_host TEXT,
    endpoint_port INTEGER,
    endpoint_domain TEXT,
    health_check_type TEXT,            -- http / tcp / script
    health_check_path TEXT,
    health_check_interval INTEGER DEFAULT 30,
    cpu_limit TEXT,
    memory_limit TEXT,
    dependencies TEXT,                 -- JSON array of service ids (冗余, 主存 cg_dependencies)
    env_vars TEXT,                     -- JSON
    created_at TEXT NOT NULL,
    last_checked_at TEXT
);

-- M3 资源中枢
CREATE TABLE IF NOT EXISTS cg_resources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,                -- port / domain / env_template / volume
    value TEXT NOT NULL,               -- 端口号 / 域名 / 模板名 / 卷名
    status TEXT NOT NULL,              -- allocated / free / reserved
    owner_service_id TEXT REFERENCES cg_services(id) ON DELETE SET NULL,
    owner_project_id TEXT REFERENCES cg_projects(id) ON DELETE SET NULL,
    metadata TEXT,                     -- JSON
    reserved_until TEXT,
    created_at TEXT NOT NULL
);

-- M4 联动引擎 - 依赖图谱
CREATE TABLE IF NOT EXISTS cg_dependencies (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,         -- project / service
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,         -- project / service
    target_id TEXT NOT NULL,
    dep_type TEXT NOT NULL,            -- code / service / data
    metadata TEXT,                     -- JSON
    created_at TEXT NOT NULL,
    UNIQUE(source_type, source_id, target_type, target_id, dep_type)
);

-- M4 联动引擎 - 事件总线
CREATE TABLE IF NOT EXISTS cg_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,          -- code_push / service_error / port_conflict / dep_update / project_archive
    source_type TEXT NOT NULL,         -- project / service / resource / scheduler
    source_id TEXT NOT NULL,
    payload TEXT,                      -- JSON
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / processed / failed
    created_at TEXT NOT NULL,
    processed_at TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_cg_services_project ON cg_services(project_id);
CREATE INDEX IF NOT EXISTS idx_cg_services_status ON cg_services(status);
CREATE INDEX IF NOT EXISTS idx_cg_resources_type ON cg_resources(type);
CREATE INDEX IF NOT EXISTS idx_cg_resources_owner ON cg_resources(owner_service_id, owner_project_id);
CREATE INDEX IF NOT EXISTS idx_cg_deps_source ON cg_dependencies(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_cg_deps_target ON cg_dependencies(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_cg_events_type ON cg_events(event_type);
CREATE INDEX IF NOT EXISTS idx_cg_events_status ON cg_events(status);
CREATE INDEX IF NOT EXISTS idx_cg_events_created ON cg_events(created_at);
```

### 3.2 同步包扩展

`sync_bundle` 的 `_read_cg_projects_for_sync` 旁追加 `_read_cg_services_for_sync`、`_read_cg_resources_for_sync`、`_read_cg_dependencies_for_sync`、`_read_cg_events_for_sync`。子表（stages/links/activities）继续不跨端。

## 4. API 端点（共 23 个，前缀 `/api/codegarden`）

### 4.1 M2 服务网格（9 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/services` | 服务列表（支持 project_id / status / namespace 过滤） |
| POST | `/services` | 注册服务 |
| GET | `/services/{id}` | 服务详情 |
| PATCH | `/services/{id}` | 更新服务 |
| DELETE | `/services/{id}` | 注销服务 |
| POST | `/services/{id}/restart` | 重启服务（创建 restart task） |
| GET | `/services/topology` | 拓扑图数据（nodes + edges） |
| GET | `/services/{id}/logs` | 日志（tail N 行） |
| GET | `/services/{id}/metrics` | 指标（CPU/内存/响应时间） |

### 4.2 M3 资源中枢（8 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/resources?type=port` | 资源列表（按类型过滤） |
| POST | `/resources` | 创建资源记录 |
| POST | `/resources/ports/allocate` | 智能分配端口（自动避开已占用） |
| POST | `/resources/ports/{port}/release` | 释放端口（8898 受保护，返回 403） |
| GET | `/resources/domains` | 域名映射列表 |
| POST | `/resources/domains` | 创建域名映射 |
| GET | `/resources/volumes` | 存储卷列表（docker volume ls） |
| GET | `/resources/env-templates` | 环境变量模板列表（敏感字段加密） |

### 4.3 M4 联动引擎（6 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dependencies` | 依赖图谱（支持 source_type/source_id 过滤） |
| POST | `/dependencies` | 创建依赖关系 |
| DELETE | `/dependencies/{id}` | 删除依赖关系 |
| GET | `/dependencies/impact?target_id=X` | 影响分析（修改 X 会影响哪些下游） |
| GET | `/events` | 事件列表（支持 event_type / status 过滤） |
| POST | `/events` | 发布事件（自动创建处理 task） |
| GET | `/playbooks` | Playbook 列表（扫 codegarden/playbooks/*.yml） |
| POST | `/playbooks/{name}/run` | 执行 Playbook（创建 task_type=playbook_run） |

## 5. 调度器（新增 2 个 job）

| Job ID | 触发 | 说明 |
|--------|------|------|
| `cg_service_scan` | IntervalTrigger 300s | 扫描本机服务（lsof -i / docker ps / pm2 list），upsert 到 cg_services |
| `cg_event_process` | IntervalTrigger 60s | 处理 pending 事件，触发联动（如 port_conflict → 自动分配新端口） |

## 6. 前端组件

### 6.1 新增组件

```
frontend/src/components/codegarden/
├── ServiceMesh.tsx           # M2 主面板（服务列表 + 状态徽章）
├── ServiceTopology.tsx       # M2 拓扑图（React Flow）
├── ServiceDetailDialog.tsx   # M2 服务详情 + 日志查看
├── ResourceHub.tsx           # M3 主面板（4 类资源 tab）
├── PortPool.tsx              # M3 端口池视图（端口范围网格）
├── DependencyGraph.tsx       # M4 依赖图谱（React Flow）
├── EventBus.tsx              # M4 事件流（实时列表 + 过滤）
└── PlaybookEditor.tsx        # M4 Playbook 编辑器（YAML + 执行历史）
```

### 6.2 React Flow 引入

推翻 Phase 2a 决策 7「不引入 React Flow / Cytoscape.js」，新增依赖：
```bash
npm install reactflow
```
更新 `AGENTS.md` 关键决策节，正式记录决策推翻。

### 6.3 路由扩展

`App.tsx` 新增 3 条路由：
- `/codegarden/services` — ServiceMesh
- `/codegarden/resources` — ResourceHub
- `/codegarden/orchestration` — DependencyGraph + EventBus + PlaybookEditor（tab 切换）

CodeGardenPage 主页加 3 个入口卡片（服务/资源/联动）。

## 7. 关键决策

1. **范围**：全量 M2+M3+M4（PRD 原计划）
2. **拓扑图渲染**：引入 React Flow，推翻 Phase 2a 决策 7
3. **M4 事件存储**：新增 cg_events 表（PRD §5.4.2 原计划）
4. **M4 Playbook 执行**：复用 knowledge_tasks（task_type=playbook_run），不新建 cg_playbook_runs 表
5. **M2 服务发现**：定时扫描（lsof/docker ps/pm2 list），每 5 分钟
6. **M3 端口保护**：hotspot 自身端口 8898 禁止释放，API 返回 403
7. **M3 敏感字段**：env_template 的敏感值复用 secrets_service Fernet 加密，不新建加密体系
8. **依赖关系冗余**：cg_services.dependencies (JSON) 与 cg_dependencies 表并存，前者冗余便于快速渲染，后者是 source of truth
9. **事件处理异步**：cg_events.status=pending → cg_event_process job 异步处理，避免事件发布阻塞
10. **Playbook YAML 不入库**：文件存 codegarden/playbooks/，与 PRD §9.2 数据目录结构一致

## 8. 与 Phase 2a 的关系

| 维度 | Phase 2a | Phase 2b |
|------|----------|----------|
| 数据模型 | 5 张 cg_ 表 | +4 张 cg_ 表（services/resources/dependencies/events） |
| API | 16 端点 | +23 端点 |
| 前端路由 | /codegarden | +3 子路由 |
| 调度器 | job 15 (cg_upstream_sync) | +job 16 (cg_service_scan) +job 17 (cg_event_process) |
| sync_bundle | 含 cg_projects | +services +resources +dependencies +events |
| React Flow | 决策禁止 | 决策推翻，引入 |

## 9. 验收标准

### 9.1 功能验收

- [ ] M2: 服务网格面板显示本机所有运行中服务（lsof/docker/pm2 三源合并）
- [ ] M2: 拓扑图可拖拽节点，显示服务间调用关系
- [ ] M2: 服务详情可查看实时日志（tail -n 100）
- [ ] M3: 端口池视图显示 8000-9999 范围内端口占用状态
- [ ] M3: 分配端口自动避开已占用 + 8898 保护
- [ ] M3: 环境变量模板敏感字段加密存储
- [ ] M4: 依赖图谱显示项目间 code/service/data 三类依赖
- [ ] M4: 发布 port_conflict 事件 → 60s 内自动处理（分配新端口）
- [ ] M4: Playbook YAML 可编辑 + 执行 + 查看历史

### 9.2 技术验收

- [ ] 后端测试：新增 3 个测试文件（test_codegarden_services_api.py / test_codegarden_resources_api.py / test_codegarden_orchestration_api.py）全 PASS
- [ ] 前端测试：新增 3 个组件测试全 PASS
- [ ] e2e 测试：服务注册→资源分配→依赖建立→事件触发全流程
- [ ] 前端 build 0 错误
- [ ] sync_bundle 双向同步 cg_* 新表
- [ ] scheduler job 16/17 注册成功

### 9.3 文档验收

- [ ] AGENTS.md 关键决策节追加 Phase 2b 决策
- [ ] _SCHEMA.md 追加 4 张新表
- [ ] codegarden/ 目录初始化 playbooks/ 子目录
- [ ] PRD v2.0 标注 Phase 2b 已实现节
