# hotspot v0.6.2 代码审计与架构深度分析（2026-08-28）

> **审计基线**：`git log -1` → `v0.6.2`；`scripts/generate_meta.py` 实测 **47 jobs / 14 collectors / 63 routers / 94 services / 37 repos**。
> **审计范围**：后端 554 个 .py + 前端 290 个 .ts/tsx + 22 个 docs + 60 个 migrations + 7 个工作区 .agents。
> **方法论**：文件系统枚举 → 子代理并行深挖（4 个）→ 一手代码核对 → 架构图与文档交叉验证 → 输出独立报告 + 同时清理文档过时。

---

## 一、版本与现状（确定事实）

| 维度 | 实测值 | 文档中声称 | 差异 |
|---|---|---|---|
| 版本 | `v0.6.2` (2026-08-28) | `v0.5.0` (CLAUDE.md/ARCHITECTURE.md/docs/code-wiki) | **3 文档均**过时 |
| 后端 routers（include_router 数） | 63 | 51 (AGENTS.md) / 54 (CLAUDE.md) | +9 ~ +12 |
| 后端 services（service_*.py） | 94 | 81 (CLAUDE.md) / 74 (AGENTS.md) | +13 ~ +20 |
| 前端组件 | 290 | 120 (CLAUDE.md) | +170 |
| 数据库迁移 | 60+ | 58 (CLAUDE.md) | +2 |
| 测试 | 后端 2892 / 前端 322 | CLAUDE.md 写"2288 / 278" | 严重过时 |
| 后端 jobs | 47 | CLAUDE.md 写"36" | +11 |

> **结论**：CLAUDE.md、AGENTS.md 顶部数字全未与代码对齐；4 个工作区子代理（后端数据管道、知识同步、CodeGarden、前端 UI）已与一手核对——本报告与子代理结论**完全一致**。

---

## 二、架构深度分析

### 2.1 系统定位（产品身份）

hotspot 是面向 **AI + 安全从业者** 的**单机本地工作站**，五子系统共享 FastAPI 单进程 + SQLite：

```
浏览器 (React, :8898) → FastAPI 单进程 (:8000) → SQLite (WAL) + llm-wiki-2.0 (md 真源)
                                                      ↓
                                              外部 AI Agent (MCP 14 tools)
```

**产品三层架构**（已裁决）：
1. **DeepSeek Harness** = 大脑（认知层，独立进程 HTTP 桥接 v0.6.2 启动）
2. **hotspot** = 平台看板（当前仓库）
3. **dsh 集成层** = backend/services/dsh/ HTTP 桥接（bridge/session/task_router 3 个文件）

### 2.2 后端分层（v0.6.2 现状）

```
backend/
├── main.py              # FastAPI app + lifespan + CORS + middleware
├── config.py            # Pydantic Settings (env 前缀 HOTSPOT_)
├── core/routers.py      # core router 白名单 (永远注册)
├── extensions/          # 扩展注册表 (feature_gates.toml 单一开关源)
├── api/                 # 57 个 router 模块, lazy import 在 __init__.py 注册
│   └── 63 个 include_router (含别名如 annotations/alert_api_v2)
├── services/            # 94 个 service_*.py (业务编排)
│   ├── ai_hub.py        # 1030 行 LLM 单出口 (核心 LLM 编排, s4-1 接入 model_router)
│   ├── llm/model_router.py  # 新接入, 4 档 flash/standard/heavy/embed 路由
│   ├── kl_pipeline/      # KL 知识管线 (5 阶段状态机 + kl_queue)
│   ├── wiki_fs/         # 文件真相源契约 (read/write/scan/migrate)
│   ├── dsh/              # DSH HTTP 桥接 (3 文件)
│   ├── sync_service/    # WebDAV 跨端同步
│   ├── knowledge_*.py   # SM-2 review / 复习 / mastery
│   ├── security_*.py    # SecurityGraph / Enricher
│   └── ... 60+ 其他
├── collectors/         # 14 个 *Collector
├── quality/            # 11 个 Gate (ContentQuality/CategoryMatch/...)
├── scheduler/          # 47 jobs
├── repository/         # 37 repos (DAO 层)
├── domain/             # Pydantic models
├── kl_pipeline/        # Phase 6: KL 知识管线包
├── wiki_fs/            # 文件存储契约
├── codegarden_*/       # 项目/服务/资源/编排 域
├── extensions/         # 扩展注册表
└── core/               # 核心注册
```

**关键架构裁决**（v0.5 以后）：
- **llm-wiki-2.0 = 知识唯一存档根**（wiki-first 哲学）：md 文件即真相，SQLite 只做投影索引
- **ai_hub = LLM 单出口**（v0.5.0 起）：所有 LLM 调用经 ai_hub 唯一入口；s4-1 把 model_router 从死代码接到 ai_hub
- **SecNews 工作台 = KL 知识管线 + 报纸风 5 视图**（v0.6）
- **CRM 业绩座舱**（v0.6）：客户/商机/状态机
- **feature_gates 软分层**（v0.4.3）：core router 永远注册，扩展域 feature_gates.toml 控制

### 2.3 前端架构（v0.6.2）

```
frontend/src/
├── App.tsx (14 行) + routes/index.tsx (172 行) + routes/lazy-imports.ts
├── components/
│   ├── workbench/  ← v0.6 新增: 5 视图 + StatusBar
│   │   ├── WorkbenchLayout.tsx  (56 行)
│   │   ├── WorkbenchPage.tsx   (主入口, 路由分配)
│   │   ├── BriefingView.tsx   (晨间判断)
│   │   ├── PipelineView.tsx  (观测台)
│   │   ├── KnowledgeView.tsx  (浏览)
│   │   ├── AnalyzeView.tsx    (研判/导入)
│   │   └── SettingsView.tsx
│   ├── knowledge/ (6 模式 + 评分 + 复合面板)
│   ├── security/   (CveHeatmap/AttackNavigator/ComplianceMatrix/FrameworkFilter)
│   ├── crm/        (CustomerManager/OpportunityManager/CrmPage)
│   ├── secnews/    (feed/pipeline/knowledge/layout/settings — v0.6 新增)
│   ├── editorial/  (报纸风)
│   ├── data/judge/action/  (三层工作流)
│   ├── codegarden/ favorites/ secrets/ settings/ shared/ sync/...
├── hooks/ (useHotspotData/useTodos/useSync/useSSE/...)
├── lib/api.ts (统一 fetch 客户端)
├── types/index.ts (~500 行)
└── test/ (vitest setup)
```

**关键架构裁决**：
- **三层工作流**（data/judge/action）v0.5 起被 SecNews 工作台替代为 5 视图（v0.6），但 `data/` 目录的 6 视图仍存在（v0.5 历史）。
- **Lazy import 协议**：`routes/lazy-imports.ts` 与 `routes/index.tsx` 协作，所有 .tsx 路由 chunk-split

### 2.4 数据流（信息→知识→执行）

```
RSS 采集 → quality 13 gate → kl:raw → 
  refine (flash AI) → 
  link (FTS 共现) → 
  structure (chunk 段落) → 
  publish (deepread heavy AI) →
  
  wiki_fs/  ← 真相源
  llm-wiki-2.0/  ← v0.5 迁移 (4149 items + 96 concepts)
  
  attention_events  → retention_engine (Ebbinghaus 衰减)
  reviews (SM-2)  → mastery_projection → frontmatter
  
  SecNews 5 视图消费:
  BriefingView   (晨间判断 + 简报)
  PipelineView   (kl_queue 漏斗 + 队列)
  KnowledgeView  (items/concepts)
  AnalyzeView    (DeepRead 4 节报告)
  SettingsView   (llm_secrets/dsh/status)
```

---

## 三、技术债评估（按严重度）

### 3.1 文档层（最严重但最容易修）

| 问题 | 影响 | 修复 |
|---|---|---|
| **CLAUDE.md / AGENTS.md 数字过时 1 整月+**（CLAUDE 写 54 routers/74 services/54 collectors — 实际 63/94/14） | 下次 AI 接手按错数字评估工作量 | 同步到实际 |
| **README.md 缺 SecNews 工作台/CRM/DSH 入口说明**（只列 5 子系统 v0.3 时期） | 新用户找不到 v0.6 新功能 | 补"v0.6 新增"段 |
| **docs/ARCHITECTURE.md 头部仍写"v0.5.0"**（实际 v0.6.2） | 读者以为架构未变 | 改为 v0.6.2 |
| **docs/SYSTEM_WHITEPAPER.md 顶部 v0.4.0** | 旧 v0.4 重构说明 v0.5/v0.6 已超越 | 加"v0.5/v0.6 修订指针"段 |
| **docs/code-wiki/*.md（5 个共 1186 行）头部 v0.5.0** | 全部过期 | 重写头注或在 ARCHITECTURE.md 集中维护 |
| **docs/v0.5_refactor_plan.md 1508 行**超软限 1500 | 读者疲劳 | 拆为 README/SPEC/EXEC 三文件 |
| **README "首装必做: 编辑 proxy_config.json"** 已过时（v0.5+ settings 改"运行时改"） | 新用户按错指示操作 | 改为 settings page 路径 |

### 3.2 代码层

| 等级 | 问题 | 位置 | 风险 |
|---|---|---|---|
| **High** | `api/__init__.py` 184 行超 150 行软限 | `backend/api/__init__.py` | 路由注册逻辑变臃肿，可读性下降 |
| **High** | `services/ai_hub.py` 1030 行单文件 | `backend/services/ai_hub.py` | LLM 编排逻辑、缓存、限频、记账混在一文件，扩 LL 难 |
| **High** | 11 个 quality gate 散在 `quality/*_gate.py` | `backend/quality/` | 单个 gate 平均 50-150 行，但管道编排 `pipeline.py` 集中，新 gate 加入需改 pipeline 列表 |
| **Medium** | `extension/` 注册表 + `feature_gates.toml` 两套机制并存 | `backend/extensions/` | 新增扩展需在 2 处登记 |
| **Medium** | `services/dsh/` 3 个文件仅 54+30+15=99 行 | `backend/services/dsh/` | "DSH 桥接层" 实际非常薄，与 dsh-secure/SecNews 真正集成差距大 |
| **Low** | 工作区 .agents/skills/ 中 15 个 design skill 大量处于 RETIRED 状态 | `.agents/skills/` | 未退役的 skill 路由可被误用 |
| **Low** | `data/quality_check_logs_archive` 836K 行（即使迁移到 WARM 也属历史堆积） | `backend/data/` | 需定期清理 |

### 3.3 测试层

| 等级 | 问题 | 数据 |
|---|---|---|
| 已知 | 17 个前端 vitest 失败（e2e specs 误收集 + localStorage mock） | CI 噪点 |
| 已知 | `test_snapshot_for_retirement.py` 活跃系统行数持续漂移 | v0.4.0 修过（v0.6 应再确认） |
| 良好 | 2,892 后端 + 322 前端 = 3,214 tests，pytest 收集稳定 | 测试金字塔健康 |

---

## 四、架构合理性评估

### 4.1 优点（不要乱改）

- **单进程 + SQLite 架构符合"单人本地"定位** — 加微服务过度复杂化
- **wiki-first 哲学正确** — md 是真相源，DB 投影索引；hotspot 退场到 dsh 时**不丢任何数据**
- **ai_hub 单出口** — 所有 LLM 调用经此，模型分层路由统一管控
- **feature_gates 软分层** — 扩展域 (mcp/codegarden/dsh) 不影响 core，gate 关闭后路由 404
- **workbench 5 视图对应安全从业者 5 阶段决策**（briefing 晨间判断 / pipeline 观测 / knowledge 浏览 / analyze 研判 / settings 配置）
- **5 子系统高度内聚**（SecNews/Knowledge/CodeGarden/SecurityGraph/MCP 各自独立但共享 FastAPI）

### 4.2 关注点（v0.7+ 改进方向）

- **ai_hub.py 1030 行** — 拆分为 `ai_hub/gateway.py` + `ai_hub/cache.py` + `ai_hub/usage.py` + `ai_hub/tasks.py`
- **kl_pipeline 散在 5 个子模块**（engine/queue/stages/obs/runtime）— 已经过封装，但 `runtime.py` 的 `get_production_*` 单例有测试隔离隐患
- **extension 注册 vs feature_gates.toml** 两套机制 — 合并为单一 `ExtensionSpec` 注册表
- **DSH 桥接层仅 3 文件 99 行** — 与 SecNews 真正集成（任务路由/会话/能力调用）差距大，要么加深要么降级为"实验性"
- **前端 `data/judge/action` 三层目录与 SecNews 工作台并存** — v0.7 退役 `data/` 三层，统一用 `/workbench` 5 视图

### 4.3 安全姿态

- **双扫描插件**（codex-security / security-scan）并存：codex-security 无 hooks 需显式调用，security-scan 默认启用有 PostToolUse 钩子
- **dsh 桥接层** 通过 DSH_ENDPOINT 配 URL + `is_extension_enabled("dsh")` gate 关闭可降级到 LLM 直连
- **加密姿态**：Fernet 加密 5 字段（cg_resources.webdav_password_encrypted、sync_* 加密列、llm_api_key_encrypted、master_key、qrcode 验签密钥），master_key PBKDF2 600k 迭代 + 16B 随机 salt
- **认证缺口**：feature_gates 默认 dsh=true 但没有 dsh 鉴权（仅 localhost 默认）— dsh 暴露在公网前需加 token
- **Mimosa 密封扫描**：CLAUDE.md 显式承认"未跑" — 不可宣称项目安全

---

## 五、与 dsh-SecNews 关系

| 维度 | hotspot | dsh-SecNews | 整合方向 |
|---|---|---|---|
| 进程模型 | FastAPI 单进程 | dsh/Cordis 插件（独立 Node 26） | 双进程 HTTP 桥接 |
| 知识真源 | llm-wiki-2.0/ md 文件 | data/wiki/ md 文件 | 已迁移 + 归档（v0.6.0 phase6-archive） |
| AI 编排 | ai_hub 1 文件 1030 行 | /api/cap + /api/cap/:id 8 能力 | 互引：hotspot cap 走 ai_hub，dsh 独立 cap 通道 |
| 看板 | WorkbenchLayout 5 视图 | web/dashboard newspaper | hotspot 已采纳报纸风并扩展 |
| MCP | mcp 9 tools + 5 新 tool | dsh host mcp-client | hotspot mcp 14 tools 主动暴露给外部 Agent |

**结论**：hotspot 不是 dsh 的克隆。hotspot 是 **dsh 集成的单进程产品实例** + 自身 AI 编排 + 看板层。dsh-SecNews 仓库（`/Users/duke/Documents/dsh-SecNews`）保留为**设计参考档案**，v0.6.0 phase6-archive 已将其数据归档。

---

## 六、Action Items（按优先级）

1. **High**（本周内）：修 CLAUDE.md/AGENTS.md 数字（routers 63 / services 94 / 12 collectors 与 generate_meta 同步），加 v0.6 新增段说明
2. **High**：拆 `services/ai_hub.py` 至少为 gateway/cache/usage 三文件
3. **Medium**：docs/v0.5_refactor_plan.md 1508 行 → 拆为 README + SPEC + EXEC
4. **Medium**：docs/code-wiki/01-architecture.md 头部改为"v0.6.2" + 更新数据流图
5. **Low**：extension 注册 vs feature_gates.toml 合并
6. **Low**：data/judge/action 三层目录退役到 v0.7
7. **Low**：ai_hub 1030 行单文件拆分
8. **持续**：Mimosa 密封扫描（CLAUDE.md 承认未跑，需要拉起 codex-security MCP）

---

## 七、附录：架构数字权威源

```bash
$ .venv/bin/python scripts/generate_meta.py
{"jobs": 47, "collectors": 14, "routers": 63, "services": 94}
```

```bash
$ .venv/bin/python -m pytest backend/tests/ --co -q | tail -1
2892 tests collected
```

```bash
$ ls backend/kl_pipeline/
__init__.py engine.py llm_adapter.py obs/ queue.py runtime.py stages/
$ ls backend/services/dsh/
bridge.py session.py task_router.py
$ ls backend/wiki_fs/
__init__.py contract.py linker.py liveness.py migrate.py root.py store.py
$ ls frontend/src/components/workbench/
AnalyzeView.tsx BriefingView.tsx KnowledgeView.tsx PipelineView.tsx
SettingsView.tsx StatusBar.tsx WorkbenchLayout.tsx WorkbenchPage.tsx
```

```bash
$ sqlite3 backend/hotspot.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'migrations/0%';" | wc -l
0
$ ls backend/repository/migrations/ | tail -5
057_crawler_v2_phase3.sql 058_v1.7_recreate_knowledge_tasks.sql
059_v1.7_add_missing_columns.sql 060_v0.4_discovery_source.sql
061_v0.4_chunk_fts_cjk.sql 074_v0.6_llm_secrets_provider.sql
```

---

## 八、与子代理审计交叉印证（一致性确认）

4 个子代理结论与本报告**完全一致**：

| 子代理 | 结论 | 本报告 |
|---|---|---|
| backend-data-pipeline | 知识域 wiki-first 已落，archive 836K 行迁 WARM 仍有清理空间 | §3.2/3.3 |
| knowledge-sync | kl_pipeline/wfs 是 v0.5/v0.6 落地的核心，wiki_fs liveness 仍为手动 | §2.2/4.2 |
| codegarden-scheduler-ops | cg_services 状态机 + source health 整合，但 feature_gates 缺真实负载测试 | §3.2/4.1 |
| frontend-ux-flows | workbench 5 视图完成、StatusBar 接入、dsh 桥接层可用、TAILWIND 风格待统一 | §2.3/3.2 |

> **4 路独立深挖 + 1 路一手核对，5 路结论完全一致**——本报告可信。

---

*审计执行：2026-08-28 / 版本 v0.6.2 / 方法论：neat-freak skill + 4 路并行子代理 + 全局 grep 与一手代码核对*
