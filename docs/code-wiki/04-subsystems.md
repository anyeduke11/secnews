# 04 — 子系统详解

> 基准: **v0.7.0**。v0.7 的整体基调: 前端收敛到 workbench 报纸版单入口,
> 后端子系统 (SecNews/KL/CodeGarden/Security/Sync/MCP) 架构不变。

## 1. SecNews 热点聚合 + 安全看板

**聚合层** (core, 永远可用): 8 分类 × 14 collector × 30+ 源 → 12 同步质量门禁 →
SQLite → 趋势 / 统一搜索 / 导出 / 报告。列表排序统一 `ingested_at DESC` (非 published_at)。

**前端呈现** (v0.7.0):

- `/workbench` 报纸版 5 视图是资讯消费主入口 (Briefing 简报 / Pipeline 管线 /
  Knowledge 知识 / Analyze 分析 / Settings 设置)
- `/secnews` 安全看板壳 (extension `secnews`) 下 7 子页:
  - `feed` 信息流 (FeedView: 卡片 + 筛选)
  - `pipeline` 管线 (FunnelBar 漏斗 + QueueCard 队列 + AliveCard 存活 + TokenLedger 账本)
  - `knowledge` 知识 (InboxScanner 收件箱扫描 + WikiBrowser 浏览)
  - `inbox` 收件箱 · `ledger` 账本
  - `analytics` **v0.6 S4-3 新增**: CVE 热力图 + ATT&CK 技术映射 (STIX 子集嵌入)
  - `settings` 设置 (采集/管线设置)
- 后端: `kl_pipeline_api.py` + `secnews_dashboard_api.py` (配 `backend/secnews_dashboard.py`) +
  `cve_analytics.py` (S4-3)
- 路由器 API: `kl_pipeline_heartbeat` (60s 心跳) + `secnews_liveness_sweep`
  (周日 02:00 UTC 书签三态批扫 alive/dead/unknown)
- 整合任务跟踪: `docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6 (Phase 0 已交付 `2592a640`)

**追抓 (catchup)**: 服务启动自动追抓「本周一 00:00 Asia/Shanghai → 当前」, per-source
checkpoint 断点续抓 + 结构化日志 + 数据完整性验证; `catchup_watchdog` job (60s) 看护。
`/api/catchup` 提供手动触发。

## 2. Knowledge LLM-Wiki (`knowledge/`)

### 2.1 分层结构

```
knowledge/
├── items/        # L1 条目层: ~400+ .md (id 命名, frontmatter 驱动, attention_score)
├── concepts/     # L2 概念层: ~35 .md + graph.json (节点/边, 运行时填入)
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

### 2.3 KL 生命周期与认知模式 (v0.7.0 现状)

- **KL 5 阶段**: `raw → refine → link → structure → publish`
  (`kl:*` 前缀, 由 `046_v1.7_lifecycle.sql` 从旧 3 阶段迁移); 触发器 T1-T5 + 心跳见 02 §7
- **认知模式「去 4 留 2」** (v0.7.0):
  - **保留**: DeepReadMode (深读主路径, S4-2 升级为 4 节 LLM 深度分析) ·
    ReviewMode (SM-2 复习主路径)
  - **已删除**: BriefingMode / ScanMode / AlertMode / OutboxMode
    (v0.6 已 @deprecated, v0.7 物理删除) — 功能由 `/workbench` 5 视图承接
- **注意力评分**: 5 维加权 (view_count / dwell_time / scroll_depth / is_favorited /
  annotation_count) → 0-100; `attention_aggregate` job 每 1800s 聚合, 30 天窗口 + 自动清理;
  `AttentionHeatmap` 可视化 (v0.7 保留)
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
- `wiki_items_fts` 写后即时同步 (v0.6.2 P0-3 修复)

## 3. CodeGarden (个人代码项目全生命周期)

目录: `codegarden/` (exports / memory / playbooks / prompts / sdds / specs) +
`backend/api/codegarden.py` (M1) + `backend/api/codegarden_ops.py` (M2-M4 运维层) +
`codegarden_phase14.py` (漂移 + CVE 联动)。

| 里程碑 | 内容 | 关键机制 |
|--------|------|----------|
| **M1 项目核心** (gate `codegarden`=true) | 项目 CRUD / 记忆 / Prompt / SDD / specs; `/from-knowledge` 从知识条目建项目; GitHub 导入; 上游同步 (`cg_upstream_sync` 每日 09:00) | `codegarden_project_service` · `codegarden_github_service` · `codegarden_knowledge_bridge` |
| **M2 服务网格** (gate `codegarden_phase2b`=**false**) | `cg_services` 表 + 自动发现 (lsof/docker/pm2, `cg_service_scan` 300s) + 拓扑 SVG + 日志/指标/重启 | `codegarden_scanner_service` · `codegarden_service_service`; 前端 `service-mesh/` |
| **M3 资源中枢** | `cg_resources` (port/domain/env_template/volume) + 8898 端口保护 + Fernet 加密 (未解锁返回 `******` 脱敏) | `codegarden_resource_service`; 前端 `resource-hub/` (PortPool) |
| **M4 联动引擎** | `cg_dependencies` + `cg_events` 事件总线 (`cg_event_process` 60s) + Playbook YAML 执行 + BFS 影响分析 | `codegarden_orchestration_service`; 前端 `dependency-graph/` + EventBus + PlaybookList |

- 迁移: `019_codegarden.sql` (M1) + `021_codegarden_phase2b.sql` (M2-M4) + `050` (漂移)
- Phase 14 联动: `cg_drift_assess` (技术栈漂移, 3600s, 归属 tech_stack gate) +
  `cve_sync_to_security` (1800s)
- v0.7.0 后前端入口: `/codegarden` (M1) + `/codegarden/phase2b` (M2-M4, gate 默认关);
  旧 `/action/codegarden*` 路由已删, 404 fallback 会导入 `/workbench`
- 详细设计: `docs/CodeGarden_PRD_v1.7.md`

## 4. Security Graph (安全知识图谱)

- **存储**: `security_graph` 表族 (migration 022): SecurityEntity / SecurityEdge / SecurityTerm
  (Pydantic 模型在 `domain/security_models.py`)
- **数据源**:
  - MITRE ATT&CK — STIX bundle 周同步 (`mitre_sync`, 周日 04:00, `security/mitre_attack.py`);
    S4-3 前端以 STIX 子集嵌入做技术映射 (cve_analytics API + `/secnews/analytics`)
  - NVD CVE — 30 分钟同步为 security 实体并桥接 knowledge (`cve_sync_to_security`)
  - 合规种子 — 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 (`security/compliance.py`);
    S4-4 扩展 GDPR + ISO 27001 合规矩阵 (api/compliance.py)
- **引擎**: `SecurityGraphEngine` (`security/graph.py`) 抽取实体 ID 并关联 hotspot/knowledge;
  `enricher.enrich_item / enrich_batch` 供采集后处理调用
- **术语归一**: `terminology_service.py` (SecurityTerm 标准化)
- **深读**: S4-2 `api/deep_read.py` — 4 节 LLM 深度分析报告
  (前端 DeepReadPage, 路由 `/deep/:type/:id`)
- **前端** `components/security/`: SecurityGraph (图谱) / SecurityTimeline /
  SecurityEntityDetail / ComplianceMatrix (合规矩阵) / TermStandardizer (术语标准化)
- **统一**: `security_entity_concept_sync` job (600s) 打通 security 实体 ↔ knowledge 概念
- **gate**: `security_graph` = false — 只影响 mitre_sync / cve_sync 两个 job;
  security / kl_* 路由属 core, 不受影响

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
- **前端**: `/sync` 页 (拆分为 SyncConfigForm / SyncOperations / SyncHistory 等组件);
  gate `sync` = true (开启)

## 6. MCP Server (外部 Agent 接入)

- **双通道**: stdio (`python -m backend.mcp_stdio_main`) + SSE (`/mcp/sse`,
  lifespan 内 `build_mcp_server` + `mount_sse_endpoint`)
- **工具面**: 9 个标准 tool (registry seed, PRIMARY KEY 幂等) + 4 个 agent 副作用 tool
  (`mcp_agent_tools.py`: score_item / enrich_concept / link_items /
  trigger_codegarden_drift) + 5 个 phase5 tool (`mcp_phase5_tools.py`: kl_* / dsh_*) +
  wiki 工具族 (`wiki_tools.py`)
- **配置**: `/api/settings/mcp/*` (前端 MCPSettingsCard); schema 见 `docs/mcp_tools_schema.json`
- **gate**: `mcp` 扩展默认**关闭** (路由 404, SSE 不挂载); 开启需编辑 feature_gates.toml

## 7. DSH 桥接层 (deepseek-harness, 实验性)

- feature gate `dsh` = **false** (v0.6.2 P1-2 降级为实验性)
- `backend/api/dsh_api.py` + `backend/services/dsh/`
  (bridge.py 的 `DSHClient`: health_check / send_task / get_session; session.py; task_router.py)
- 启用条件: ① 设置 `DSH_ENDPOINT` 环境变量 (默认 `http://localhost:3210`)
  ② DeepSeek Harness 实际运行并暴露 `/health` `/api/task` 端点
  ③ 测试 DSH 不可达时**自动降级 llm_service 直连** (无需改业务代码)
- 退役交接工具: `scripts/export_for_dsh.py` / `export_migrations_for_dsh.py`
  (Phase 7 后端退役至 dsh-SecNews 的参考资产, 破坏性步骤已冻结)

## 8. CRM 业绩座舱 (v0.6.0)

- feature gate `crm` = **true** (2026-08-25 用户拍板)
- 后端 `crm_customers_api` (客户 CRUD) / `crm_opportunities_api`
  (商机状态机) / `crm_stats_api` (KPI/图表聚合) + `services/crm_stats_service.py`
- 迁移 `071_crm_cockpit.sql`; 前端 `/crm` (CrmPage + CockpitDashboard +
  CustomerManager + OpportunityManager; `lib/crm.ts` API 封装 + `types/crm.ts`)
- 设计文档: `docs/COCKPIT_PRD.md`
