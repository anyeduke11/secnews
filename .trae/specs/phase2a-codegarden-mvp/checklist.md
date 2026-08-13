# Phase 2a CodeGarden MVP — 验证清单

> 执行规则：每完成一个 Task，勾选对应行；每个 Group 结束跑回归测试；全部完成后执行 Section 6 全量验证。

---

## 1. DB schema + 基础设施 (Group A)

- [x] A1.1 迁移文件 `019_codegarden.sql` 创建（5 张 cg_ 表 + skills 扩展 9 字段）
- [x] A1.2 `init_db()` 启动时迁移自动应用（无报错）
- [x] A1.3 `PRAGMA table_info(cg_projects)` 返回 **25** 列（校正：spec 写 24，实际 25 含 `archived_at`）
- [x] A1.4 `PRAGMA table_info(skills)` 含新增 9 字段（skill_type / capabilities / constraints_json / output_format / system_prompt / few_shot_examples / success_metrics / usage_count / avg_rating）
- [x] A2.1 `codegarden/` 目录创建（含 `.gitkeep`）
- [x] A3.1 `knowledge/_SCHEMA.md` 追加 `project_id` 可选字段说明
- [x] **Group A 回归**：`init_db()` 通过 + 既有 Phase 1j 测试不受影响

---

## 2. Repo + Service + API (Group B-D)

### 2.1 Repo 层

- [x] B1.1 `codegarden_repo.py` 创建，含 `CodegardenProjectRepository` 类
- [x] B1.2 CRUD 完整：create / get / list / update / delete / archive / restore
- [x] B1.3 多维筛选：lifecycle / source_type / type / domain / source_item_id / keyword
- [x] B1.4 lifecycle 状态切换 + activities 写入
- [x] B1.5 stages 管理（auto-increment stage_order）
- [x] B2.1 `test_codegarden_repo.py` 通过（含筛选 + lifecycle 跳转 + 反向溯源）

### 2.2 Service 层

- [x] C1.1 `codegarden_project_service.py` 创建
- [x] C1.2 `_LEGAL_TRANSITIONS` 8 阶段跳转表定义
- [x] C1.3 `request_upstream_sync()` 写入 `knowledge_tasks` (task_type=project_sync)
- [x] C2.1 `codegarden_github_service.py` 创建
- [x] C2.2 `fetch_repo_metadata(url)` 返回 `RepoMetadata` dataclass
- [x] C2.3 `compare_commits(repo_url, base, head)` 返回 `CompareResult` dataclass
- [x] C2.4 `GithubTokenMissingException` / `GithubRateLimitException` 异常类
- [x] C2.5 token 从 `secrets_service.get_secret_value("github_token")` 获取
- [x] C3.1 `codegarden_knowledge_bridge.py` 创建
- [x] C3.2 `list_candidates()` 返回 type=github 的未转化 knowledge_items
- [x] C3.3 `create_from_knowledge(item_id, source_type, local_path)` 创建 cg_projects
- [x] C3.4 `_update_item_frontmatter_project_id()` best-effort 写入

### 2.3 API 层

- [x] D1.1 `api/codegarden.py` 创建，16 个端点全部定义
- [x] D1.2 `APIRouter(prefix="/api/codegarden", tags=["codegarden"])`
- [x] D1.3 `asyncio.to_thread` 包装同步 DB 操作
- [x] D1.4 GitHub token 缺失返回 **424** 状态码（不是 500）
- [x] D1.5 from-knowledge API 返回 201（新建）/ 200（幂等返回已存在）
- [x] D2.1 `api/__init__.py` 注册 codegarden router
- [x] D3.1 `test_codegarden_api.py` 17 个测试全部通过
- [x] D3.2 含 `_seed_knowledge_item()` fixture（type=github）
- [x] **Group D 回归**：`pytest backend/tests/test_codegarden_*.py -v` 全 PASS

### 2.4 16 个端点清单

- [x] `GET    /api/codegarden/projects` — 列表 + 多维筛选
- [x] `POST   /api/codegarden/projects` — 创建项目
- [x] `GET    /api/codegarden/projects/{id}` — 详情
- [x] `PATCH  /api/codegarden/projects/{id}` — 更新
- [x] `DELETE /api/codegarden/projects/{id}` — 删除
- [x] `POST   /api/codegarden/projects/{id}/lifecycle` — 状态切换 (body: {to, note})
- [x] `POST   /api/codegarden/projects/{id}/archive` — 归档
- [x] `POST   /api/codegarden/projects/{id}/restore` — 恢复
- [x] `GET    /api/codegarden/projects/{id}/timeline` — 阶段时间线
- [x] `GET    /api/codegarden/projects/{id}/activities` — 活动日志
- [x] `GET    /api/codegarden/github/metadata?url=...` — 元数据预览 (前端 G6 调用)
- [x] `POST   /api/codegarden/github/import` — GitHub 导入 (body: {repo_url, ...})
- [x] `GET    /api/codegarden/candidates` — 候选列表 (type=github 未转化)
- [x] `POST   /api/codegarden/from-knowledge` — 从知识库转化 (body: {item_id, ...}, 幂等)
- [x] `POST   /api/codegarden/projects/{id}/sync` — 触发上游同步（创建 task）
- [x] `GET    /api/codegarden/projects/{id}/upstream` — 上游状态详情

---

## 3. Scheduler + Sync bundle (Group E-F)

- [x] E1.1 `cg_upstream_sync_job` 函数定义（遍历 fork 项目创建 sync 任务）
- [x] E2.1 `scheduler.py` 注册 job 15（`CronTrigger(hour=9, timezone=SHANGHAI_TZ)`）
- [x] E2.2 启动后 `scheduler.get_jobs()` 含 15 个 job（含 cg_upstream_sync_job）
- [x] F1.1 `sync_bundle.build_bundle()` 含 `codegarden_projects` key
- [x] F1.2 `_apply_cg_projects(items)` upsert by id (ON CONFLICT DO UPDATE)
- [x] F1.3 `apply_bundle()` 调用 `_apply_cg_projects`
- [x] F1.4 同步包**只含主表**（不含 stages/links/activities，符合决策 6）
- [x] **Group E-F 回归**：手动触发 `cg_upstream_sync_job()` 无报错

---

## 4. 前端 UI (Group G)

### 4.1 基础类型 + Hook

- [x] G1.1 `types/codegarden.ts` 创建（CgProject + 5 个 Request/Response 接口 + 3 个 dataclass）
- [x] G1.2 `LIFECYCLE_COLORS` / `LIFECYCLE_LABELS` / `SOURCE_TYPE_LABELS` 常量定义
- [x] G1.3 `npx tsc --noEmit` 通过
- [x] G2.1 `useCodegardenProjects.ts` 创建
- [x] G2.2 返回 items / total / loading / error + 4 个 filter + 11 个操作函数
- [x] G2.3 AbortController 处理 + 250ms debounce（参考 useSkills 模式）

### 4.2 组件

- [x] G3.1 `ProjectBoard.tsx` — 6 列看板（ideation→maintenance，archived/deprecated 不列）
- [x] G4.1 `ProjectCard.tsx` — 卡片显示 name + description + tags + tech_stack
- [x] G4.2 fork 项目 commits_behind > 0 时显示 ↓N 红色徽章
- [x] G4.3 显示「→ 推进到下一阶段」按钮（非 maintenance/deprecated 阶段）
- [x] G5.1 `ProjectDetail.tsx` — 详情弹窗（含元数据 + tags + lifecycle 切换 + timeline + activities）
- [x] G5.2 fork 项目 + upstream_url 时显示 UpstreamStatus 组件
- [x] G6.1 `GithubImportDialog.tsx` — 表单含 repo_url / source_type / type / tags / tech_stack 等
- [x] G6.2 「预览」按钮调用 `/api/codegarden/github/metadata` 显示 stars / default_branch
- [x] G6.3 token 缺失时显示「未配置 github_token」错误提示
- [x] G7.1 `FromKnowledgeDialog.tsx` — 列出 candidates + 单选 + source_type 选择
- [x] G7.2 候选列表只含未转化 item（C3 SQL 过滤已转化的，前端不需要 `converted` 字段）
- [x] G8.1 `UpstreamStatus.tsx` — 显示 commits_behind / ahead / last_synced_at / upstream_url
- [x] G8.2 「立即同步」按钮触发 onSync

### 4.3 页面集成

- [x] G9.1 `CodegardenPage.tsx` 创建，组合 Board + Detail + 2 个 Dialog
- [x] G9.2 App.tsx 追加 `/codegarden` 路由
- [x] G9.3 `npm run build` 通过
- [x] G10.1 `ItemDetailDialog.tsx` 在 type=github 时显示「🌱 加入 CodeGarden」CTA
- [x] G10.2 CTA 调用 `/api/codegarden/from-knowledge` (source_type=reference)
- [x] G11.1 `Header.tsx` 追加 CodeGarden 导航按钮（在「知识管理」之后）
- [x] G11.2 `ViewRoute` 类型扩展含 `'/codegarden'`
- [ ] **Group G 回归**：`npm run build` 0 错误 + 浏览器访问 `/codegarden` 渲染正常

---

## 5. 测试 (Group H)

- [x] H1.1 `pytest backend/tests/test_codegarden_api.py` 17 测试全 PASS
- [x] H1.2 (可选) api.codegarden 覆盖率 >= 80%
- [x] H2.1 `ProjectCard.test.tsx` 8 测试全 PASS
- [x] H2.2 测试覆盖：display_name 渲染 / source_type 徽章 / commits_behind 显示+隐藏 / onClick / onTransition / maintenance 阶段无推进按钮 / health_score 显示
- [x] H3.1 `test_codegarden_e2e.py` 3 测试全 PASS
- [x] H3.2 e2e 验证完整路径：knowledge_item → candidates (转化前可见) → from-knowledge (201) → cg_projects.source_item_id 反向溯源 → candidates (转化后不可见) → 重复转化幂等 (200) → 非 github item 拒绝 (400)

---

## 6. 全量回归 + 收尾 (Task I1)

### 6.1 后端

- [x] `pytest backend/tests/ -v --tb=short` 全 PASS（Phase 1j + Phase 2a）
- [ ] 既有 Phase 41 skills 功能未破坏（skills 表扩展字段 DEFAULT NULL/0 生效）
- [ ] 既有 Phase 1j knowledge_items 功能未破坏
- [ ] `curl http://127.0.0.1:8000/api/codegarden/projects` 返回 `{"version":..., "total":0, "items":[]}`
- [ ] `curl http://127.0.0.1:8000/api/codegarden/candidates` 返回候选列表
- [x] Scheduler 启动后 15 个 job 注册（含 cg_upstream_sync_job）

### 6.2 前端

- [ ] `npm run build` 0 错误
- [ ] `npx vitest run` 全 PASS
- [ ] 浏览器访问 `http://localhost:8898/codegarden` 显示看板（空状态）
- [x] Header 出现 CodeGarden 入口按钮（icon 🌱）
- [ ] KnowledgePage 打开任意 type=github 的 item 详情，出现「🌱 加入 CodeGarden」CTA

### 6.3 集成验证

- [ ] 在 `/codegarden` 点「+ GitHub 导入」→ 输入 repo URL → 预览成功（需先配置 github_token）→ 导入 → 看板出现新卡片
- [ ] 在 `/codegarden` 点「+ 从知识库」→ 选择 github 候选 → 加入 → 看板出现新卡片 + candidates 列表中该 item 已移除（C3 SQL 过滤）
- [ ] 在 `/codegarden` 重复转化同一 item → 提示「该项目已在 CodeGarden 中」（幂等 200）
- [ ] 在 `/knowledge` 打开 type=github item → 点「🌱 加入 CodeGarden」→ 成功提示 → CodeGarden 看板出现新卡片
- [ ] 点卡片 → 详情弹窗 → 切换 lifecycle 状态 → 卡片移动到新列 + 活动日志新增记录
- [ ] fork 项目详情 → 点「立即同步」→ 提示「已触发同步 (task #N)」+ knowledge_tasks 表新增 project_sync 任务

### 6.4 文档 + commit

- [x] 所有 commit message 格式：`feat(codegarden): <task-id> <短描述>` 或 `test(codegarden): <task-id> <短描述>`
- [ ] `git log --oneline | grep codegarden | wc -l` >= 20（A1 + A2 + A3 + B1 + B2 + C1 + C2 + C3 + D1 + D2 + D3 + E1 + E2 + F1 + G1-G11 + H2 + H3 = 22 个 commit）
- [ ] `git status` 干净（除可能的 .trae/specs/ 外）
- [ ] 未推送到 GitHub（用户要求手动 push）

---

## 7. 关键决策验证

| # | 决策 | 验证方式 | 状态 |
|---|------|----------|------|
| 1 | 表名 `skills` 而非 `knowledge_skills` | `PRAGMA table_info(skills)` 含 9 个新字段 | [ ] |
| 2 | cg_projects.id 用 TEXT UUID | `SELECT id FROM cg_projects LIMIT 1` 返回 UUID 格式 | [ ] |
| 3 | knowledge_tasks.task_type 扩展无需 schema 变更 | `INSERT INTO knowledge_tasks (..., task_type='project_sync', ...)` 成功 | [ ] |
| 4 | GitHub REST API + httpx | 代码导入 `httpx`，无 `requests` 库 | [ ] |
| 5 | 上游同步走任务队列 | `POST /sync` 创建 knowledge_tasks 记录而非直接调用 | [ ] |
| 6 | 同步包只含 cg_projects 主表 | `build_bundle()` 不含 cg_project_stages/links/activities | [ ] |
| 7 | 不引入 React Flow / Cytoscape | `frontend/package.json` 无新依赖 | [ ] |
| 8 | frontmatter project_id 不强制 | 既有 409 items 不需要回填，新转化 item 才写入 | [ ] |
| 9 | source_item_id 无外键约束 | 删除 knowledge_item 不连带删除 project | [ ] |
| 10 | GitHub token 缺失返回 424 | `curl -X POST /api/codegarden/github/import` 返回 424（未配置 token 时） | [ ] |

---

## 8. 风险验证

| 风险 | 缓解措施 | 验证 |
|------|----------|------|
| GitHub API 速率限制 | 强制 token + 24h 间隔 + 缓存 | [ ] 单元测试用 mock httpx，不依赖外网 |
| 前端 11 个组件 token 超预算 | Group G 分多次 commit | [ ] 每个 Task 独立 commit，避免上下文堆积 |
| e2e 测试需要真实 GitHub API | mock httpx 响应 | [ ] test_codegarden_e2e.py 不发起真实 HTTP 调用 |
| skills 表扩展破坏 Phase 41 | 新字段 DEFAULT NULL/0 | [ ] 既有 SkillRepository 测试全 PASS |

---

## 9. 不在范围内（明确推迟）

- [x] ~~服务网格（M2）~~ — Phase 2b
- [x] ~~资源中枢（M3）~~ — Phase 2b
- [x] ~~联动引擎（M4）~~ — Phase 2b
- [x] ~~AI 协作层（M6-M12）~~ — Phase 2c
- [x] ~~生命周期健康度评分（M5）~~ — Phase 2d
- [x] ~~项目→知识反向沉淀（PRD 9.3.2）~~ — Phase 2d
- [x] ~~SOUL.md 项目状态节~~ — Phase 2d
- [x] ~~资讯→项目转化率 > 5% 验证~~ — Phase 2b 数据积累后

---

## 10. 完成标志

**Phase 2a MVP 完成的充要条件**：

1. ✅ 上述 1-9 节所有 `[ ]` 勾选为 `[x]`
2. ✅ 后端全量测试 PASS（既有 + 新增）
3. ✅ 前端 build 0 错误
4. ✅ 浏览器烟测 4 项核心路径可用（GitHub 导入 / 从知识库导入 / lifecycle 切换 / 触发同步）
5. ✅ commit 数 >= 22，message 格式统一
6. ✅ spec 决策 1-10 全部验证通过

满足上述 6 项后，Phase 2a MVP 视为完成，可进入 Phase 2b 规划。
