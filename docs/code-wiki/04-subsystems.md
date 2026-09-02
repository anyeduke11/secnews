# 04 — 子系统详解

> 基准: **v0.7.4-cleanup (Batch ⑨, 2026-09-01)**。前端收敛到哨兵终端 + SecNews 统一工作台,
> 后端子系统 (SecNews/KL/CodeGarden/Security/Sync/MCP/DSH/CRM) 架构不变, 观测子系统为 v0.7 新增。

## 0. 哨兵终端 (v0.7.1+, 首页)

- **定位**: 独立全屏的前端壳, **不走 PageLayout**, `SentinelShell` 提供布局 (含 `SentinelRail` 导航)
- **页面** (详见 03 §3): `/` 态势首页 · `/judge` 判断 + `/judge/graph` 图谱 ·
  `/action` 行动 · `/garden` 花园 · `/sentinel/settings` 设置
- **唯一入口**: 根路径 `/` 与 `*` fallback 均落哨兵首页; 扩展关闭时旧深链不白屏
- 组件 scoped 在 `.sentinel` 命名空间, 不污染全局样式; 各页独立 .css (sentinel.css / -action / -garden / -graph / -judge / -settings)
- 导航出口 → `/secnews` 统一工作台 (桌面端业务主入口)

## 1. SecNews 热点聚合 + 统一工作台

**聚合层** (core, 永远可用): 8 分类 × 14 collector × 30+ 源 → 12 同步质量门禁 →
SQLite → 趋势 / 统一搜索 / 导出 / 报告。列表排序统一 `ingested_at DESC`。

**前端呈现** (v0.7.4):

- `/secnews` 统一工作台 (extension `secnews`) 7 tab:
  - `feed` 信息流 (FeedView + DigestCard 简报)
  - `pipeline` 管线 (FunnelBar 漏斗 + QueueCard + AliveCard + TokenLedger 账本)
  - `knowledge` 知识 (InboxScanner + WikiBrowser)
  - `analyze` 研判 (SecNewsAnalyze)
  - `analytics` CVE 热力图 + ATT&CK 技术映射 (STIX 子集嵌入)
  - `observability` **v0.7.3 新增**: 观测看板 (见 §9)
  - `settings` 设置 (采集源 + 管线 + LLM provider + dsh 启停 + pi agent)
- 后端: `kl_pipeline_api.py` + `secnews_dashboard_api.py` (配 `backend/secnews_dashboard.py`) +
  `cve_analytics.py` (S4-3) + `observability_router.py` (S4-5/v0.7)
- 路由器 API: `kl_pipeline_heartbeat` (60s) + `secnews_liveness_sweep` (周日书签三态批扫)

**追抓 (catchup)**: 启动自动追抓「本周一 00:00 Asia/Shanghai → 当前」, per-source
checkpoint 断点续抓 + 数据完整性验证; `catchup_watchdog` job (60s) 看护; `/api/catchup` 手动触发。

## 2. Knowledge LLM-Wiki (`llm-wiki-2.0/`, 唯一根)

### 2.1 目录结构 (v0.6.3 P4 后)

```
llm-wiki-2.0/
├── items/        # L1 条目层: 4149 .md (id 命名, frontmatter 驱动, attention_score)
├── concepts/     # L2 概念层: 96 .md + graph.json (节点/边, 运行时填入)
├── learning/     # L3 学习层: 2062 文件 (学习计划 + tasks/)
├── content/      # L4 内容层: calendar.json 发布日历 + 草稿 (16 文件)
├── summaries/    # 生成摘要 (8 文件)
├── soul.md       # 角色画像 (从统计自动生成, weekly_maintenance job)
├── _MAP.md       # 自动索引地图 (map_rebuild_daily job)
├── _SCHEMA.md    # frontmatter schema 权威定义
├── inbox/ quarantine/ digest/ sources/ schema/   # 系统目录
└── retention.json  # 遗忘策略配置
```

路径唯一来源: `backend/wiki_fs/paths.py` (全部基于 `resolve_wiki_root()`, env `HOTSPOT_WIKI_ROOT` 可覆盖)。

### 2.2 frontmatter 契约

条目核心字段: `id / title / source / ingested_at / lifecycle (kl:*) / compiled / domain / topic /
type / difficulty / tags / concepts / mastery / related_items / project_id`。

### 2.3 KL 生命周期与认知模式

- **KL 5 阶段**: `kl:raw → kl:refine → kl:link → kl:structure → kl:publish`; 触发器 T1-T5 + 心跳 (02 §7)
- **认知模式「去 4 留 2」**: 保留 DeepReadMode (S4-2 四节 LLM 深度分析) + ReviewMode (SM-2);
  已删 4 认知模式 (功能由 /secnews 承接)
- **注意力评分**: 5 维加权 → 0-100; `attention_aggregate` (1800s) 聚合, 30 天窗口 + 自动清理
- **SM-2**: `sm2_reviews` + `sm2_daily_push` (08:00) + `/api/reviews/due`
- **chunks**: 段落级切分 + FTS5 (CJK), `char_start/end` 原文跳转
- **遗忘**: `retention_decay` (周日 05:30) + `wiki_archiver` (30 天归档)

### 2.4 文件 ↔ DB 同步

- `knowledge_sync.py`: `sync_item_to_db()` / `write_item_to_md()`
- `knowledge_watcher.py`: Watchdog + debounce 自动回灌 (main.py `start_watcher()` 幂等)
- `wiki_fs/store.py`: WikiFs + inbox 隔离 (quarantine) + liveness 三态; `read_item` mtime+size 缓存 (35×)

## 3. CodeGarden (个人代码项目全生命周期)

目录: `codegarden/` (exports / memory / playbooks / prompts / sdds / specs) +
`backend/api/codegarden.py` (M1) + `codegarden_ops.py` (M2-M4) + `codegarden_phase14.py` (漂移+CVE)。

| 里程碑 | 内容 | 关键机制 |
|--------|------|----------|
| **M1 项目核心** (gate `codegarden`=true) | 项目 CRUD / 记忆 / Prompt / SDD / specs; `/from-knowledge`; GitHub 导入; 上游同步 (`cg_upstream_sync` 09:00) | `codegarden_project_service` · `codegarden_github_service` · `codegarden_knowledge_bridge` |
| **M2 服务网格** (gate `codegarden_phase2b`=**true**, Batch ⑧ 开闸) | `cg_services` + 自动发现 (lsof/docker/pm2, `cg_service_scan` 300s) + 拓扑 SVG + 日志/指标/重启 | `codegarden_scanner_service` · `codegarden_service_service`; 前端 `service-mesh/` |
| **M3 资源中枢** | `cg_resources` (port/domain/env_template/volume) + 8898 端口保护 + Fernet 加密 (未解锁 `******`) | `codegarden_resource_service`; 前端 `resource-hub/` (PortPool) |
| **M4 联动引擎** | `cg_dependencies` + `cg_events` (`cg_event_process` 60s) + Playbook YAML + BFS 影响分析 | `codegarden_orchestration_service`; 前端 `dependency-graph/` + EventBus + PlaybookList |

- 迁移: 019 (M1) + 021 (M2-M4) + 050 (漂移)
- Phase 14: `cg_drift_assess` (3600s) + `cve_sync_to_security` (1800s)
- 前端入口: `/codegarden` (M1) + `/codegarden/phase2b` (M2-M4)
- 详细设计: `docs/CodeGarden_PRD_v1.7.md`

## 4. Security Graph (安全知识图谱, gate 已开)

- **存储**: `security_graph` 表族 (migration 022): SecurityEntity / SecurityEdge / SecurityTerm
  (Pydantic 模型在 `domain/security_models.py`)
- **数据源**:
  - MITRE ATT&CK — STIX bundle 周同步 (`mitre_sync`, 周日 04:00, `security/mitre_attack.py`);
    S4-3 前端 STIX 子集嵌入 (cve_analytics API + `/secnews/analytics`)
  - NVD CVE — 30 分钟同步 (`cve_sync_to_security`) 桥接 knowledge
  - 合规种子 — 等保 2.0 / 关基 / 数安法 / 网安法 / 个保法 + S4-4 GDPR / ISO 27001 (`api/compliance.py`)
- **引擎**: `SecurityGraphEngine` (`security/graph.py`) + `enricher.enrich_item / enrich_batch`
- **术语归一**: `terminology_service.py`
- **深读**: S4-2 `api/deep_read.py` — 4 节 LLM 分析 (前端 `/deep/:type/:id`)
- **前端** `components/security/`: SecurityGraph / SecurityEntityDetail / ComplianceMatrix
- **统一**: `security_entity_concept_sync` (600s); 图谱页: `/judge/graph` (哨兵) + `/secnews/analytics`

## 5. Sync 跨端配置同步 (WebDAV)

- **传输**: 坚果云 WebDAV (`webdav_client.py`); 文件名必须 ASCII (`config-YYYY-MM-DD.zip`)
- **容器**: zip 内 `envelope.json` (Fernet 密文) + `manifest.json` (明文)
- **合并**: `three_way_merge` (base/local/remote) — 记录按 key 对齐, 字段级 last-write-wins;
  覆盖 favorites / todos / skills / custom_sources / secrets(含 llm_secrets, sync_write 审计) /
  reading_states / annotations
- **调度**: 每周一 10:30 Asia/Shanghai (`sync`) + 启动 catch-up (`should_run_catchup`)
- **加密链路**: `sync_fernet_mixin.py` (fernet key 同步路径, 从 sync_service 拆出避免循环依赖)
- **前端**: `/sync` (SyncConfigForm / SyncOperations / SyncHistory); gate `sync`=true

## 6. MCP Server (外部 Agent 接入)

- **双通道**: stdio (`python -m backend.mcp_stdio_main`) + SSE (`/mcp/sse`, lifespan 挂载)
- **工具面**: 9 标准 tool (registry seed 幂等) + 4 agent 副作用 tool (`mcp_agent_tools.py`) +
  5 phase5 tool (`mcp_phase5_tools.py`: kl_* / dsh_*) + wiki 工具族 (`wiki_tools.py`)
- **配置**: `/api/settings/mcp/*` (前端 MCPSettingsCard)
- **gate**: `mcp` 扩展默认**关闭** (路由 404, SSE 不挂载)

## 7. DSH 认知大脑 (受管子进程, v0.6.3 内置化)

- feature gate `dsh` = **true** (v0.6.3 起内置化; 未配置启动命令时如实 `not_configured`)
- **子进程宿主**: `process_supervisor` (spawn/stop/poll/auto-restart/重启上限, 5 个 process_events 写入点)
  + `dsh/supervisor.py` (配置持久化 settings KV + `autostart_if_configured` lifespan 钩子)
- **控制面**: `/api/dsh/control/*` 5 端点 + 前端 `/settings?cat=pipeline` DshControlCard 一键启停 (10s 轮询; v0.7.x SettingsHub 已从 `/secnews/settings` 合并)
- **pi 执行 agent**: `agent_bridge` (jsonl/stream-json 协议 + workspace 锁定 codegarden/ + builtin→ai_hub) + `/api/agents/*` (AgentRunnerCard)
- **不可达自动降级** llm_service 直连 (无需改业务代码)

## 8. CRM 业绩座舱 (v0.6.0)

- feature gate `crm` = **true**
- 后端 `crm_customers_api` / `crm_opportunities_api` (商机状态机) / `crm_stats_api` (KPI 聚合)
  + `services/crm_stats_service.py`
- 迁移 `071_crm_cockpit.sql`; 前端 `/crm` (CrmPage + CockpitDashboard + CustomerManager +
  OpportunityManager; `lib/crm.ts` + `types/crm.ts`)
- 设计文档: `docs/COCKPIT_PRD.md`

## 9. Observability 观测闭环 (v0.7, 基础设施)

**定位**: 无条件基础设施 (无 feature gate), 观察 API/LLM/Job/Agent/Process/Audit 六类执行。

| 层 | 组件 | 说明 |
|----|------|------|
| 追踪 | `backend/observability.py` | trace_id ContextVar; `log_event()` 结构化事件 |
| 落表 | `observability_records.py` | `record_api_call` / `record_audit` / `start-finish_job_run` / `start-finish_agent_run` / `record_process_event`; 全 def + swallow |
| 采集 | `TraceIDMiddleware` | HTTP 请求注入 + 收尾落 api_events; path_template (route.path); 双层防御 |
| 采样 | `observability_sampling.py` | success 10% / error 100% / slow 100% (env 可覆盖; 测试环境强制 100%) |
| 聚合 | `observability_aggregator` job (60min) | api_events 2h → api_metrics_hourly (hour+path_template 主键) |
| 阈值 | `observability_thresholds.py` + `observability_threshold_check` job | 4 类规则 (api/llm/job/audit) warn/critical; cooldown 15min 防风暴; 写 observability_alerts + audit_log |
| 告警 | `alert_channels.py` + `alert_dispatcher.py` | 5 通道: status_bar / webhook / email / slack / 飞书 / 钉钉 (HMAC 签名); alert_deliveries 落审计 |
| API | `/api/observability/*` (observability_router.py) | summary / recent / timeseries / llm-usage / alerts(+ack) / thresholds(GET/PUT) / sampling |
| 前端 | `/secnews/observability` + StatusBar | ObservabilityDashboard (概览/慢路径/事件) + ActiveAlertsBanner + ThresholdEditor; SSE 推送 + 轮询兜底; StatusBar obs 1h 段 + 🚨/⚠ 角标 |
| TTL | `observability_ttl` job (1h) | 6 张表按 7d/30d/14d/90d 清理 |

**关键决策**: ① 阻塞 async→def 线程池派发 (P3-1 教训); ② record_* 失败永不阻塞业务 (PRD §10 红线);
③ ContextVar Token 必须捕获 (丢 Token = 业务崩); ④ loguru `serialize=True` 与测试同构;
⑤ aggregator 用 Python 两步走 (SQLite correlated subquery 不能引用外层别名)。

**数据流全景**: 请求/任务 → trace_id → record_* 落表 → 聚合 → 阈值评估 → 告警分发 →
前端看板 (详见 01 §5.4)。观测事件同时经 SSE (`/api/events`) 推送到面板 (Batch ⑧ D3)。