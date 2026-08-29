# 04 — 子系统详解

> **本文件是 [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §一"系统总览"中 5 个子系统的细节展开** — 详列 SecNews / Knowledge / CodeGarden / SecurityGraph / SecNews 工作台 + CRM 座舱的功能与数据流。

## 1. SecNews 热点聚合 + 安全看板

**聚合层** (core, 永远可用): 8 分类 × 14 collector × 30+ 源 → 12 同步质量门禁 →
SQLite → 趋势 / 统一搜索 / 导出 / 报告。列表排序统一 `ingested_at DESC` (非 published_at)。

**安全看板** (extension `secnews`, 2026-08 SecNews 整合主线):

- 前端 `/secnews` 壳下 6 子页:
  - `feed` 信息流 (FeedView: 卡片 + 筛选)
  - `pipeline` 管线 (FunnelBar 漏斗 + QueueCard 队列 + AliveCard 存活 + TokenLedger 账本)
  - `knowledge` 知识 (InboxScanner 收件箱扫描 + WikiBrowser 浏览)
  - `inbox` 收件箱 · `ledger` 账本 · `settings` 设置 (采集/管线设置)
- 后端: `kl_pipeline_api.py` + `secnews_dashboard_api.py` (配 `backend/secnews_dashboard.py`)
- 路由器 API: `kl_pipeline_heartbeat` (60s 心跳) + `secnews_liveness_sweep`
  (周日 02:00 UTC 书签三态批扫 alive/dead/unknown)
- 整合任务跟踪: `docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6

**追抓 (catchup)**: 服务启动自动追抓「本周一 00:00 Asia/Shanghai → 当前」, per-source
checkpoint 断点续抓 + 结构化日志 + 数据完整性验证; `catchup_watchdog` job (60s) 看护。
`/api/catchup` 提供手动触发。

## 2. Knowledge LLM-Wiki (`knowledge/`)

### 2.1 分层结构

```
knowledge/
├── items/        # L1 条目层: ~400+ .md (id 命名, frontmatter 驱动, attention_score)
├── concepts/     # L2 概念层: ~35 .md + graph.json (节点/边, 6 边运行时填入)
├── learning/     # L3 学习层: 学习计划 + tasks/ (pending/processing/done/failed)
├── content/      # L4 内容层: calendar.json 发布日历 + 草稿
├── summaries/    # 生成摘要
├── SOUL.md       # 角色画像 (从统计自动生成, weekly_maintenance job)
├── _MAP.md       # 自动索引地图 (map_rebuild_daily job)
└── _SCHEMA.md    # frontmatter schema 权威定义
```

### 2.2 frontmatter 契约 (`_SCHEMA.md`)

条目核心字段: `id / title / source / ingested_at / lifecycle / compiled / domain / topic /
type / difficulty / tags / concepts / mastery / related_items / project_id`。
`project_id` 反向关联 CodeGarden 项目 (知识 → 项目联动)。

### 2.3 KL 生命周期与认知模式

- **KL 5 阶段**: `raw → refine → link → structure → publish`
  (`kl:*` 前缀, 由 `046_v1.7_lifecycle.sql` 从旧 3 阶段迁移); 触发器 T1-T5 + 心跳见 02 §7
- **6 认知模式** (前端 `/knowledge`):
  Briefing 简报 / Scan 扫描 / DeepRead 深度 / Alert 告警 / Outbox 整理 / Review 复习
- **注意力评分**: 5 维加权 (view_count / dwell_time / scroll_depth / is_favorited /
  annotation_count) → 0-100; `attention_aggregate` job 每 1800s 聚合, 30 天窗口 + 自动清理;
  `AttentionHeatmap` 可视化
- **SM-2 间隔复习**: `sm2_reviews` 表 + `sm2_daily_push` job (08:00) + `/api/reviews/due`
- **chunks**: 段落级切分 + FTS5 全文检索 (CJK 分词), `char_start/end` 支持原文跳转
- **编译**: `compile_daily` (02:00) + `compile_consumer` (02:30 规则式消费) → 概念抽取 →
  graph.json → SOUL.md → _MAP.md
- **遗忘**: `retention_decay` (周日 05:30 艾宾浩斯衰减) + `wiki_archiver` (30 天归档
  llm-wiki-2.0/ + retention.json `scheduled_in` 标签驱动)

### 2.4 文件 ↔ DB 同步

- `knowledge_sync.py`: `sync_item_to_db()` (md frontmatter → SQLite) /
  `write_item_to_md()` (DB → md)
- `knowledge_watcher.py`: Watchdog 监听 + debounce, 文件变更自动回灌 SQLite
  (main.py 启动时 `start_watcher()`, 幂等)
- `wiki_fs/`: WikiFs 存储契约 + inbox 隔离 (quarantine) + liveness 三态

## 3. CodeGarden (个人代码项目全生命周期)

目录: `codegarden/` (exports / memory / playbooks / prompts / sdds / specs) +
`backend/api/codegarden.py` (M1) + `backend/api/codegarden_ops.py` (M2-M4 运维层) +
`codegarden_phase14.py` (漂移 + CVE 联动)。

| 里程碑 | 内容 | 关键机制 |
|--------|------|----------|
| **M1 项目核心** (gate `codegarden`) | 项目 CRUD / 记忆 / Prompt / SDD / specs; `/from-knowledge` 从知识条目建项目; GitHub 导入; 上游同步 (`cg_upstream_sync` 每日 09:00) | `codegarden_project_service` · `codegarden_github_service` · `codegarden_knowledge_bridge` |
| **M2 服务网格** (gate `codegarden_phase2b`) | `cg_services` 表 + 自动发现 (lsof/docker/pm2, `cg_service_scan` 300s) + 拓扑 SVG + 日志/指标/重启 | `codegarden_scanner_service` · `codegarden_service_service`; 前端 `service-mesh/` |
| **M3 资源中枢** | `cg_resources` (port/domain/env_template/volume) + 8898 端口保护 + Fernet 加密 (未解锁返回 `******` 脱敏) | `codegarden_resource_service`; 前端 `resource-hub/` (PortPool) |
| **M4 联动引擎** | `cg_dependencies` + `cg_events` 事件总线 (`cg_event_process` 60s) + Playbook YAML 执行 + BFS 影响分析 | `codegarden_orchestration_service`; 前端 `dependency-graph/` + EventBus + PlaybookList |

- 迁移: `019_codegarden.sql` (M1) + `021_codegarden_phase2b.sql` (M2-M4) + `050` (漂移)
- Phase 14 联动: `cg_drift_assess` (技术栈漂移, 3600s) + `cve_sync_to_security` (1800s)
- 详细设计: `docs/CodeGarden_PRD_v1.7.md`

## 4. Security Graph (安全知识图谱)

- **存储**: `security_graph` 表族 (migration 022): SecurityEntity / SecurityEdge / SecurityTerm
  (Pydantic 模型在 `domain/security_models.py`)
- **数据源**:
  - MITRE ATT&CK — STIX bundle 周同步 (`mitre_sync`, 周日 04:00, `security/mitre_attack.py`)
  - NVD CVE — 30 分钟同步为 security 实体并桥接 knowledge (`cve_sync_to_security`)
  - 合规种子 — 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 (`security/compliance.py`)
- **引擎**: `SecurityGraphEngine` (`security/graph.py`) 抽取实体 ID 并关联 hotspot/knowledge;
  `enricher.enrich_item / enrich_batch` 供采集后处理调用
- **术语归一**: `terminology_service.py` (SecurityTerm 标准化)
- **前端** `components/security/`: SecurityGraph (图谱) / SecurityTimeline /
  SecurityEntityDetail / ComplianceMatrix (合规矩阵) / TermStandardizer (术语标准化)
- **统一**: `security_entity_concept_sync` job (600s) 打通 security 实体 ↔ knowledge 概念

## 5. Sync 跨端配置同步 (WebDAV)

- **传输**: 坚果云 WebDAV (`webdav_client.py`); 文件名必须 ASCII
  (`config-YYYY-MM-DD.zip`, 覆盖式)
- **容器**: zip 内 `envelope.json` (Fernet 密文, PBKDF2 master key 派生) +
  `manifest.json` (明文元数据); 打包/解包在 `sync_zip.py`
- **合并**: `three_way_merge` (base/local/remote) — 记录按 key 对齐, 处理删除/新增,
  字段级 last-write-wins, 冲突用 `_conflict_resolved` 或 `updated_at` 决策;
  覆盖 favorites / todos / skills / custom_sources / secrets / reading_states / annotations
- **调度**: 每周一 10:30 Asia/Shanghai (`sync` job) + 启动 catch-up 检查
  (`should_run_catchup`, 本周一 10:30 后未同步则 force pull)
- **加密链路**: `sync_fernet_mixin.py` (fernet key 同步路径, 从 sync_service 拆出避免循环依赖)
- **前端**: `/sync` 页 (拆分为 SyncConfigForm / SyncOperations / SyncHistory 等组件)

## 6. MCP Server (外部 Agent 接入)

- **双通道**: stdio (`python -m backend.mcp_stdio_main`) + SSE (`/mcp/sse`,
  lifespan 内 `build_mcp_server` + `mount_sse_endpoint`)
- **工具面**: 9 个标准 tool (registry seed, PRIMARY KEY 幂等) + 4 个 agent 副作用 tool
  (`mcp_agent_tools.py`: score_item / enrich_concept / link_items /
  trigger_codegarden_drift) + 5 个 phase5 tool (`mcp_phase5_tools.py`: kl_* / dsh_*) +
  wiki 工具族 (`wiki_tools.py`)
- **配置**: `/api/settings/mcp/*` (前端 MCPSettingsCard); schema 见 `docs/mcp_tools_schema.json`
- **gate**: `mcp` 扩展 (关闭时路由 404, SSE 不挂载)

## 7. DSH 桥接层 (deepseek-harness)

- feature gate `dsh`; `backend/api/dsh_api.py` + `backend/services/dsh/`
  (bridge.py 的 `DSHClient`: health_check / send_task / get_session;
  session.py; task_router.py)
- 退役交接工具: `scripts/export_for_dsh.py` / `export_migrations_for_dsh.py`
  (Phase 7 后端退役至 dsh-SecNews 的参考资产, 破坏性步骤已冻结)
- `services/sag_service.py` 为同类外部运行时桥接

## 8. CRM 业绩座舱 (v0.6)

- feature gate `crm`; 后端 `crm_customers_api` (客户 CRUD) / `crm_opportunities_api`
  (商机状态机) / `crm_stats_api` (KPI/图表聚合) + `services/crm_stats_service.py`
- 迁移 `071_crm_cockpit.sql`; 前端 `/crm` (CrmPage + CockpitDashboard +
  CustomerManager + OpportunityManager; `lib/crm.ts` API 封装 + `types/crm.ts`)
