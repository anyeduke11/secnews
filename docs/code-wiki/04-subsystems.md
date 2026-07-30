# 04 — 子系统详解

## 1. Knowledge LLM-Wiki (`knowledge/`)

### 1.1 设计理念

文件系统优先的知识库，.md 文件为 source of truth，SQLite 为读缓存。人机可读可写。

### 1.2 四层金字塔

```
L4: Content (内容创作)
    └─ drafts/  + calendar.json    ← 发布日历

L3: Learning (学习计划)
    └─ tasks/                      ← 任务队列
        ├─ pending/                ← Agent 监控
        ├─ processing/             ← Agent 执行中
        ├─ done/                   ← 已完成
        └─ failed/ + error.md      ← 失败记录

L2: Concepts (概念)
    └─ ~35 个 .md + graph.json     ← 提取的概念实体

L1: Items (知识条目)
    └─ ~405 个 .md                 ← 原始知识条目
```

### 1.3 数据模型 (`_SCHEMA.md`)

**Knowledge Item** (YAML frontmatter):
```yaml
id: "a1b2c3"                        # unique hash
title: "Article Title"
source: "cubox"                     # cubox | bookmark | secnews | secnews_archive
source_url: "https://..."
ingested_at: "2026-07-14T10:00:00Z"
compiled: false

# 分类 (4 维度)
domain: "security"
topic: "zero-trust"
type: "news"                        # news|analysis|paper|tutorial|tool|opinion|github
difficulty: "intermediate"          # beginner|intermediate|advanced|expert

# 标签 (多维)
tags: [rsa-conference, network-security]

# 提取的概念
concepts: [zero-trust-architecture]

# 学习状态
mastery: 0                          # 0-100
last_reviewed: null
review_count: 0

# 关联
related_items: ["d4e5f6"]
project_id: null                    # CodeGarden 反向引用
```

### 1.4 关键文件

| 文件 | 职责 |
|------|------|
| `_MAP.md` | 知识地图 (自动生成索引) |
| `_SCHEMA.md` | 数据模型契约 |
| `SOUL.md` | 角色画像 (从统计数据自动生成) |
| `concepts/graph.json` | 概念关系图 |

### 1.5 同步机制

- `knowledge_watcher.py` (watchdog) 检测 `knowledge/` 目录下 .md 文件变更
- 变更后自动同步到 SQLite (`knowledge_items` / `knowledge_concepts` 表)
- `sync_item_to_db()` / `sync_concept_to_db()` 解析 YAML frontmatter → SQLite
- `write_item_to_md()` 反向写入 SQLite → .md

### 1.6 联邦

支持跨 LLM-Wiki 引用：
- `[[wiki:local:concepts/zero-trust]]` — 引用本地 wiki 概念
- `[[wiki:hotspot:items/a1b2c3]]` — 引用 hotspot wiki 条目

### 1.7 计划任务

| 频率 | 任务 | 说明 |
|------|------|------|
| 每日 02:00 | `compile_daily` | 知识编译 |
| 周日 03:00 | `compile_weekly` | 周度编译 |
| 周日 04:00 | `soul_weekly` | SOUL.md 更新 |
| 周日 05:00 | `migrate_weekly` | 掌握度迁移 |
| 周日 06:00 | `summary_weekly` | 周回顾生成 |
| 每日 06:00 | `stats_daily` | 数据回收 |

---

## 2. CodeGarden (`codegarden/` + `backend/api/codegarden*.py`)

### 2.1 定位

个人代码项目全生命周期管理，分两阶段实现：

| Phase | 版本 | 功能 |
|-------|------|------|
| Phase 1 (2a) | v1.5 | 项目 CRUD、本地扫描、GitHub 导入、Knowledge 桥接 |
| Phase 2b | v1.6 | 服务网格、资源中枢、联动引擎 |

### 2.2 Phase 1 — 项目生命周期

```
项目状态机: scanning → active → testing → archived
              ↑          ↓         ↓
              └──────────┴─────────┘ (任何阶段可直接归档)
```

**API 端点** (`/api/codegarden`):
- `GET/POST /projects` — 项目 CRUD
- `GET /projects/{id}` — 项目详情
- `POST /scan` — 本地扫描
- `POST /github/import` — GitHub 导入
- `POST /from-knowledge` — 从知识库导入
- `POST /sync` — 触发项目同步

**关键服务**:
| 服务 | 文件 | 职责 |
|------|------|------|
| `CodeGardenProjectService` | `codegarden_project_service.py` | 项目 CRUD + 生命周期 |
| `CodeGardenScanner` | `codegarden_scanner.py` | 本地目录扫描 (深度2) |
| `CodeGardenGitHubService` | `codegarden_github_service.py` | GitHub API 导入 |
| `CodeGardenKnowledgeBridge` | `codegarden_knowledge_bridge.py` | Knowledge ↔ CodeGarden |

### 2.3 Phase 2b — 服务网格 / 资源中枢 / 联动引擎

**M2 服务网格** (`cg_services` 表):
- 自动发现：`lsof` / `docker ps` / `pm2 list` 三源扫描，每 5 分钟
- 拓扑图：SVG 渲染 (节点数 <20)
- 操作：重启、日志查看、指标查询

**M3 资源中枢** (`cg_resources` 表):
- 4 类资源：`port` / `domain` / `env_template` / `volume`
- 端口保护：8898 端口禁止释放 (API 返回 403)
- 敏感字段：env_template 复用 secrets_service Fernet 加密

**M4 联动引擎** (`cg_dependencies` + `cg_events` 表):
- 依赖关系：BFS 反向追溯影响分析
- 事件处理：`cg_events.status=pending` → `cg_event_process` job 异步处理 (60s)
- Playbook：YAML 文件存储在 `codegarden/playbooks/`，复用 `knowledge_tasks` 表执行

**API 端点** (`/api/codegarden`, 26 个):
- M2 (10): `/services` CRUD + `/scan` + `/topology` + `/{id}/restart` + `/{id}/logs` + `/{id}/metrics`
- M3 (8): `/resources` CRUD + `/allocate-port` + `/release-port` + `/env-templates`
- M4 (8): `/dependencies` CRUD + `/impact` + `/events` + `/playbooks`

### 2.4 项目属性

```python
cg_projects:
  id, name, absolute_path, marker_file, language, inferred_type,
  tech_stack (JSON array), description, status, source_item_id,
  dependencies (JSON), env_vars, created_at, updated_at
```

---

## 3. Security Knowledge Graph (`backend/security/`)

### 3.1 定位

构建安全知识图谱，关联 CVE / MITRE ATT&CK / 合规等安全实体。

### 3.2 核心组件

| 模块 | 文件 | 职责 |
|------|------|------|
| **SecurityGraphEngine** | `graph.py` | 图谱构建 + 实体增强 |
| **MITRE ATT&CK** | `mitre_attack.py` | STIX 数据同步 |
| **Enricher** | `enricher.py` | CVE/ATT&CK/合规 ID 提取 |
| **Compliance** | `compliance.py` | 合规种子数据 (等保/关基/GDPR) |

### 3.3 实体提取

正则匹配从内容中提取：
- `CVE-\d{4}-\d{4,}` → CVE 编号
- `T\d{4}(\.\d{3})?` → ATT&CK 技术 ID
- 关键词匹配：等保、关基、数据安全法、GDPR 等

### 3.4 前端组件

- `SecurityGraph.tsx` — 力导向图可视化
- `SecurityTimeline.tsx` — 安全事件时间线
- `SecurityEntityDetail.tsx` — 实体详情面板
- `ComplianceMatrix.tsx` — 合规矩阵
- `TermStandardizer.tsx` — 术语标准化

### 3.5 计划任务

| 频率 | 任务 | 说明 |
|------|------|------|
| 周日 04:00 | `mitre_sync` | MITRE ATT&CK STIX 同步 |
| 每 5 分钟 | `security_enrichment` | 安全实体增强 |

---

## 4. v1.7 新增子系统 (Phase 1-3)

### 4.1 标签与自动提取 (Phase 1)

- **tags 表**：多维标签体系 (domain/topic/type/difficulty)
- **tag_rules.json**：自动提取规则配置
- **ExtractService**：从标题/内容自动提取标签
- API: `/api/tags` + `/api/extract`

### 4.2 复习与笔记 (Phase 2)

- **SM-2 间隔复习**：`ReviewService` + `reviews` 表
  - 新概念 24h 内进入复习队列
  - 高评分延长间隔，低评分缩短
- **笔记空间**：`AnnotationService` + `annotations` 表
  - 笔记 CRUD，关联到知识条目
- **技术栈桥接**：`TechStackService` + `tech_stack` 表
  - 从 `cg_projects.tech_stack` JSON 提取技术栈
  - FastAPI 文章 ↔ CodeGarden 项目匹配

### 4.3 告警与搜索 (Phase 3)

- **告警引擎**：`AlertService` + `alerts` 表
  - 11 个 API 端点，规则 CRUD + 告警查询
  - SSE 实时推送告警到前端
  - 新建规则后 60s 内触发
- **统一搜索**：`SearchService` + `/api/search`
  - 跨层搜索 (hotspots + knowledge + projects)
  - LIKE 查询，500ms 内返回
- **模式切换**：`/api/mode/current`
  - brief / scan / deep 模式
  - 每日首次返回 brief digest

---

## 5. 运行与测试

### 5.1 启动

```bash
# 后端
python run.py                          # 默认 0.0.0.0:8000
HOTSPOT_PORT=8999 python run.py        # 自定义端口

# 前端
cd frontend && npm run dev             # 默认 0.0.0.0:8898 (strict)

# 同时启动 (推荐)
# Terminal 1: python run.py
# Terminal 2: cd frontend && npm run dev
```

### 5.2 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `HOTSPOT_HOST` | 0.0.0.0 | 后端监听地址 |
| `HOTSPOT_PORT` | 8000 | 后端端口 |
| `WORKERS` | 1 | uvicorn worker 数 (SQLite 限 1) |
| `HOTSPOT_PROXY_MODE` | off | 代理模式 |
| `HOTSPOT_QUALITY_STRICT_MODE` | false | 质量严格模式 |

### 5.3 依赖安装

```bash
# 后端
cd backend && pip install -r requirements.txt

# 前端
cd frontend && npm install
```

### 5.4 测试

```bash
# 后端 (全量)
.venv/bin/python3 -m pytest backend/tests/ -v

# 后端 (按关键字)
.venv/bin/python3 -m pytest backend/tests/ -k "merge"

# 后端 (单文件)
.venv/bin/python3 -m pytest backend/tests/test_sync_merge.py -v

# 前端 (全量)
cd frontend && npx vitest run

# 前端 (watch)
cd frontend && npx vitest run --watch

# 类型检查
cd frontend && npx tsc --noEmit

# 编译检查
.venv/bin/python3 -m py_compile backend/services/sync_merge.py
```

### 5.5 测试覆盖

| 层 | 测试文件数 | 测试数 |
|----|-----------|--------|
| 后端 | 67 | ~500+ |
| 前端 | ~20 | ~180+ |
| Phase 2b API | 1 | 29 |
| Phase 2b e2e | 1 | 4 |

### 5.6 代理配置

部分采集器需要代理绕过反爬：
- 配置文件：`backend/proxy_config.json` (在 `.gitignore` 中)
- 代理地址：`127.0.0.1:7897`
- `ProxySession` 包装 aiohttp，自动代理路由

---

## 6. 关键设计决策索引

| # | 决策 | 位置 |
|---|------|------|
| 1 | SQLite 线程本地连接，autocommit 模式 | `repository/db.py` |
| 2 | 前端端口固定 8898，`--strictPort` | `frontend/package.json` |
| 3 | Knowledge .md 为 source of truth，SQLite 为读缓存 | `knowledge/` |
| 4 | 三路合并引擎 (base/local/remote) | `services/sync_merge.py` |
| 5 | 质量管线 13 个门禁，loose/strict 双模式 | `quality/pipeline.py` |
| 6 | 异常统一响应 `{code, message, trace_id, version}` | `exceptions.py` |
| 7 | 采集器异常隔离，单源失败不阻塞 | `collectors/base.py` |
| 8 | 拓扑图 SVG 渲染 (非 React Flow) | `frontend/.../ServiceTopology.tsx` |
| 9 | Playbook YAML 不入库，文件存储 | `codegarden/playbooks/` |
| 10 | 事件异步处理 (60s job) | `scheduler/` job 17 |
| 11 | 敏感字段复用 Fernet 加密 | `services/secrets_service.py` |
| 12 | 时区统一 Asia/Shanghai (TimeRange + Cron) | `domain/enums.py` + `scheduler/scheduler.py` |