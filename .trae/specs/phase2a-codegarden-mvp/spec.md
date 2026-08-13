# Phase 2a — CodeGarden MVP

**状态**: 待批准
**日期**: 2026-07-19
**前置**: Phase 1j 完成（45 commits, compiled 17.1%, 96 concepts）
**基线**: `docs/CodeGarden_PRD_v2.0.md` (v2.0, 1685 行)
**Token 预算**: ~28,000 / 30,000 session budget

## 目标

落地 CodeGarden 子系统的最小可用版本（MVP），解决两个最高优先级痛点：

1. **vibecoding 交付成果状态不清晰** — 自己产出的代码项目没有统一看板
2. **二次开发 github 项目管理缺失** — fork 上游后无法跟踪更新、commit 差异

并打通 hotspot 的核心协同通道：**GitHub 资讯 → 二开候选源 → CodeGarden 项目**。

## 范围

| Task | 优先级 | 类型 | 描述 |
|------|--------|------|------|
| A1 | P0 | DB | 迁移 `019_codegarden.sql`：cg_projects + cg_project_stages + cg_project_links + cg_project_activities + skills 表扩展字段 |
| A2 | P1 | 基础设施 | `codegarden/` 数据目录初始化 + `.gitkeep` |
| A3 | P2 | 设计对齐 | `knowledge/_SCHEMA.md` 扩展 `project_id` 可选字段说明 |
| B1 | P0 | 后端 | `backend/repository/codegarden_repo.py` — CodegardenProjectRepository CRUD + 多维筛选 |
| B2 | P0 | 测试 | `backend/tests/test_codegarden_repo.py` — repo 层单测 |
| C1 | P0 | 后端 | `backend/services/codegarden_project_service.py` — 业务逻辑 + lifecycle 切换 + activities 写入 |
| C2 | P0 | 后端 | `backend/services/codegarden_github_service.py` — GitHub REST API 客户端（repo metadata + compare commits） |
| C3 | P0 | 后端 | `backend/services/codegarden_knowledge_bridge.py` — 资讯→项目转化 + candidates 列表 |
| D1 | P0 | 后端 | `backend/api/codegarden.py` — 路由：CRUD + 状态切换 + GitHub 导入 + from-knowledge + candidates + 上游同步 + timeline/activities |
| D2 | P0 | 后端 | 注册路由到 `backend/api/__init__.py` |
| D3 | P0 | 测试 | `backend/tests/test_codegarden_api.py` — API 层单测 |
| E1 | P1 | 调度 | `backend/scheduler/jobs.py` 新增 `cg_upstream_sync_job`（job 15） |
| E2 | P1 | 调度 | `backend/scheduler/scheduler.py` 注册 job 15（每日 09:00 Asia/Shanghai） |
| F1 | P1 | 同步 | `backend/services/sync_bundle.py` build/apply 加入 cg_projects 数据 |
| G1 | P0 | 前端 | `frontend/src/types/codegarden.ts` — TypeScript 类型 |
| G2 | P0 | 前端 | `frontend/src/hooks/useCodegardenProjects.ts` — 数据 hook |
| G3 | P0 | 前端 | `frontend/src/components/codegarden/ProjectBoard.tsx` — 看板主页 |
| G4 | P0 | 前端 | `frontend/src/components/codegarden/ProjectCard.tsx` — 项目卡片 |
| G5 | P0 | 前端 | `frontend/src/components/codegarden/ProjectDetail.tsx` — 详情页 |
| G6 | P0 | 前端 | `frontend/src/components/codegarden/GithubImportDialog.tsx` — 导入对话框 |
| G7 | P0 | 前端 | `frontend/src/components/codegarden/FromKnowledgeDialog.tsx` — 从知识库导入 |
| G8 | P0 | 前端 | `frontend/src/components/codegarden/UpstreamStatus.tsx` — 上游状态组件 |
| G9 | P0 | 前端 | `frontend/src/pages/CodegardenPage.tsx` + App.tsx 路由 |
| G10 | P0 | 前端 | KnowledgePage 集成「加入 CodeGarden」CTA（仅 type=github） |
| G11 | P1 | 前端 | Header 导航增加 CodeGarden 入口 |
| H1 | P0 | 测试 | API 单测：CRUD + 状态切换 + from-knowledge 转化 + candidates |
| H2 | P1 | 测试 | 前端组件测试：ProjectCard 渲染 + 状态显示 |
| H3 | P0 | 测试 | e2e 测试：资讯→项目转化全流程 |

## 分组与依赖

```
Group A (DB + 基础设施) → Group B (Repo) → Group C (Service) → Group D (API)
                                                                              ↓
                                                       Group E (Scheduler) ← (并行)
                                                       Group F (Sync bundle) ← (并行)
                                                                              ↓
                                                       Group G (前端) → Group H (测试)
```

- **Group A** (Task A1-A3): DB schema + 目录初始化，所有后续依赖
- **Group B** (Task B1-B2): Repo 层 + 单测
- **Group C** (Task C1-C3): Service 层（项目业务 / GitHub API / 知识桥接）
- **Group D** (Task D1-D3): API 路由 + 注册 + 单测
- **Group E** (Task E1-E2): Scheduler job 15 注册
- **Group F** (Task F1): 同步包扩展（cg_projects 纳入跨端同步）
- **Group G** (Task G1-G11): 前端 UI 全套
- **Group H** (Task H1-H3): 测试套件（API + 组件 + e2e）

## 成功标准

1. DB schema 5 张 cg_ 表 + skills 表 9 个新字段创建成功（`PRAGMA table_info(cg_projects)` 返回 24 列）
2. API 16 个端点全部可用（GET/POST/PATCH/DELETE 项目 + 状态切换 + GitHub 导入 + metadata 预览 + from-knowledge 幂等 + candidates + 上游同步 + timeline + activities + upstream 详情）
3. 项目接入时间 < 5 分钟（从输入 GitHub URL 到完成注册）
4. 资讯→项目转化路径可用（知识详情页 CTA + CodeGarden 候选列表双入口）
5. 上游同步定时任务每日 09:00 自动触发（job 15 注册成功）
6. cg_projects 数据纳入跨端同步包（build/apply 双向）
7. 前端 build 0 错误（`npm run build` 通过）
8. 后端单测全部通过（`pytest backend/tests/test_codegarden_*.py -v`）
9. e2e 测试通过：资讯→from-knowledge→cg_projects 记录创建→source_item_id 反向溯源可查
10. PRD 11.3 成功指标 8 项中 7 项满足（"资讯→项目转化率 > 5%" 推迟到 Phase 2b 数据积累后验证）

## 关键决策

### 决策 1: 表名校正 — 扩展 `skills` 而非 PRD 假设的 `knowledge_skills`

PRD v2.0 第 6.3.1 节假设扩展 `knowledge_skills` 表，但 hotspot 实际表名是 `skills`（Phase 41 迁移 012_skills.sql 创建，无 `knowledge_` 前缀）。Phase 2a 校正为扩展 `skills` 表，加 9 个新字段（`skill_type` / `capabilities` / `constraints_json` / `output_format` / `system_prompt` / `few_shot_examples` / `success_metrics` / `usage_count` / `avg_rating`）。

### 决策 2: cg_projects.id 用 TEXT UUID 而非 INTEGER AUTOINCREMENT

与 hotspot 既有 `knowledge_items.id` (TEXT) 模式一致，便于跨端同步（无自增冲突）。`uuid.uuid4()` 生成。

### 决策 3: knowledge_tasks 表 task_type 扩展无需 schema 变更

`knowledge_tasks.task_type` 是 TEXT 字段（无 CHECK 约束），扩展枚举值 `project_sync` 是约定层面，无需 ALTER TABLE。

### 决策 4: GitHub REST API 客户端复用 httpx 模式

参考 `backend/collectors/github_collector.py` 的 httpx + BaseCollector 模式，但 CodeGarden 走 GitHub REST API（不是 HTML 抓取），需 token 鉴权。token 从 `secrets_service` 获取（key name: `github_token`）。

### 决策 5: 上游同步走任务队列而非直接调用

`POST /api/codegarden/projects/{id}/sync` 创建 `knowledge_tasks` 记录（task_type=project_sync, params={project_id}），由 watchdog 或手动执行。避免 HTTP 请求阻塞（GitHub API 调用可能 10s+）。

### 决策 6: 同步包只含 cg_projects 主表，不含 stages/links/activities

减少同步包体积。子表数据通过前端实时拉取，不跨端同步。后续 Phase 2b 如有需求再扩展。

### 决策 7: 前端不引入 React Flow / Cytoscape.js

Phase 2a 不需要拓扑图（服务网格是 Phase 2b 范围），前端只用 Tailwind + 既有组件模式，避免引入新依赖。

### 决策 8: knowledge_items frontmatter project_id 字段不强制

`project_id` 是可选字段，仅在 item 已转化为 cg_projects 时写入。`_SCHEMA.md` 文档化但不强制 schema 校验（避免既有 409 items 全部需要回填）。

### 决策 9: source_item_id 反向溯源无需外键约束

`cg_projects.source_item_id` 是 TEXT 字段，逻辑上指向 `knowledge_items.id`，但不加 FOREIGN KEY 约束（避免删除 knowledge_item 时连带删除 project）。应用层负责一致性。

### 决策 10: GitHub token 缺失时优雅降级

GitHub 导入/上游同步功能在 token 缺失时返回 424 Failed Dependency（不是 500），前端显示「请在 Secrets 页面配置 github_token」提示。其他 CRUD 功能不受影响。

## 风险

| 风险 | 缓解 |
|------|------|
| GitHub API 速率限制（未认证 60/h，认证 5000/h） | 强制 token；定时同步间隔 24h；缓存 commits 信息 |
| 前端组件数量多（11 个）导致 token 超预算 | Group G 分多次 commit；G6/G7/G8 优先级 P0 但可后置到 Phase 2b |
| e2e 测试需要真实 GitHub API 调用 | 用 mock httpx 响应（pytest httpx mocking），不依赖外网 |
| skills 表扩展字段破坏既有 Phase 41 功能 | 所有新字段 DEFAULT NULL/0；既有 INSERT 不传新字段时默认值生效 |

## 不在范围内（推迟到后续 Phase）

- 服务网格（M2）— Phase 2b
- 资源中枢（M3）— Phase 2b
- 联动引擎（M4）— Phase 2b
- AI 协作层（M6-M12）— Phase 2c
- 生命周期健康度评分（M5）— Phase 2d
- 项目→知识反向沉淀（PRD 9.3.2）— Phase 2d
- SOUL.md 项目状态节 — Phase 2d
