# P0 · R-07 调度层盘点（59 job）

> **需求来源**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md` §4.7](../v0.8.8/V0.8.8_REFACTOR_PRD.md)（R-07）
> **阶段**: v0.8.8 P0 只读盘点（为 P1 裁决提供证据）
> **性质**: 纯盘点，**零业务代码改动**；本文件是本任务唯一写入物
> **执行时间**: 2026-11-10（Asia/Shanghai）
> **Python 解释器**: `/Users/duke/Documents/hotspot/.venv/bin/python3`

---

## 1. 采集方法

### 1.1 枚举口径（与 `generate_meta.py::count_jobs()` 完全一致）

job 枚举 **不是**按文件名或 `scheduler/jobs/` 目录推断，而是复刻 `scripts/generate_meta.py::count_jobs()` 的 AST 逻辑：解析 `backend/scheduler/scheduler.py`，对所有 `ast.Call` 节点中 `node.func.attr == "add_job"` 计数。

```bash
$ .venv/bin/python3 -c "from scripts.generate_meta import count_jobs; print(count_jobs())"
59
```

复刻版 AST 遍历（含 `if _is_job_enabled(...)` 守卫栈）同样得到 **59**，与权威计数一致 → **59 行表格齐全（验收 ①）**。

> 口径说明：`add_job` 只出现在 `backend/scheduler/scheduler.py`，故「注册点 = 59」与「运行时 `scheduler.get_jobs()` 返回数」在 gate 全开时相等；gate 关闭时**注册数不变、实际运行数减少**（gate 判定见 §3）。

### 1.2 工具与命令

| 目的 | 方法 |
|---|---|
| job 枚举 + trigger + gate 守卫 | `ast.parse(scheduler.py)` + 守卫栈遍历，输出 `(job_id, func, trigger, gate_cond, lineno)` |
| gate 归属 | 读 `backend/extensions/__init__.py::JOB_TO_EXTENSION`（由 `EXTENSION_JOBS` 反向派生）→ `is_extension_enabled(ext)` → `backend/config/feature_gates.toml` |
| job 实现体 | AST 提取 59 个 job 函数的源码体（`ast.get_source_segment`），逐个追调用链 |
| 写入表 | 正则扫 `INSERT INTO / UPDATE / DELETE FROM`，再回溯到 `backend/repository/migrations/*.sql` 确认**真实表名**（表名不猜） |
| 下游消费方 | 全仓文本扫描 `backend/api/` `backend/services/` `backend/repository/` `backend/scheduler/` `frontend/src/`（排除 `__pycache__` / `.mimosa` 基线快照 / `*.db`），落到**文件 + 行号** |

### 1.3 关键约束遵守

- **gate 绑定不按文件名猜**：全部经 `scheduler.py::_is_job_enabled()` → `JOB_TO_EXTENSION` → `feature_gates.toml` 三跳确认。
- **IntervalTrigger 换算为实际秒数**并标注来源（硬编码常量 / config 字段名 + 默认值）。
- **CronTrigger 写出 cron 表达式与时区**（注意：`SHANGHAI_TZ` = `Asia/Shanghai`；少数写死字符串 `"Asia/Shanghai"`；`secnews_liveness_sweep` 用 `"UTC"`）。
- 「写入表无任何读取方」严格定义：**除写入方自身外，全仓（后端 api/service/repository/scheduler + 前端 src）无任何读取该表/该产出的代码路径**。仅有测试读取 → 仍计为「无生产读取方」。

---

## 2. 59 行主表

> **触发方式**列格式：`interval Ns`（秒）+ 来源；`cron <表达式>` + 时区。
> **归属 gate** 列格式：`core`（无扩展归属，`_is_job_enabled` 恒 True）或 `扩展:<name>（gate=enabled/disabled）`。

| # | job id | 触发方式 | 归属 gate | 写入表 | 下游消费方 | 是否闭环必需 |
|---|---|---|---|---|---|---|
| 1 | `collect_all` | interval 1800s（`config.collect_interval_seconds`，默认 1800；运行时可由 `reschedule()` 动态改） | core | `hotspots`（`hotspot_repo.upsert_many`）、`collection_runs`、`crawler_runs`、`raw_items`、`quality_check_logs`、`crawl_url_checks`、`source_reputation`、`trend_snapshots`、`hotspot_tags`、`tags`、`knowledge_chunks`；另经 post-ingest 链写 `v1_materials` / `v1_signals` / `v1_knowledge` | `backend/api/hotspots.py`（`GET /api/hotspots`）→ `frontend/src/components/sentinel/SentinelHomePage.tsx` / `useHotspotData`；`backend/api/health.py`（collection_runs）；`backend/api/categories.py` | **是** — 资讯获取主链唯一入口，Feed 数据源 |
| 2 | `source_reputation_rebuild` | interval 21600s（`config.quality_reputation_interval_seconds`，默认 21600） | core | `source_reputation`（`SourceReputationRepository.rebuild_all`） | `backend/quality/source_reputation_gate.py`（采集质量门禁读信誉分）；`backend/api/quality_rejection_api.py` | **是** — 质量门禁 L1 输入，缺失则信誉门禁失效 |
| 3 | `catchup_watchdog` | interval 60s（硬编码常量 60） | core | `collection_runs`（`mark_run_failed_watchdog` UPDATE status/finished_at）；enqueue 时写 `catchup_runs` | `backend/api/health.py`（`/api/health` 暴露 `last_orphan_recovery_at`）；`backend/api/catchup.py`（`GET /api/catchup/status`） | **是** — 孤儿 run 收口，防采集轮次永久卡死 |
| 4 | `source_revival_check` | cron `hour=3, minute=0`（Asia/Shanghai） | core | `crawler_sources`（`UPDATE status='grace' / 'dead'`、consecutive_failures、cooldown_until） | `backend/api/source_stats_api.py`（`GET /api/sources/stats`）；`backend/api/source_system_api.py` | **否** — 死源复活属运营辅助，源已失效时无下游业务价值；`collect_all` 天然跳过 dead 源 |
| 5 | `collect_validations_cleanup` | cron `hour=4, minute=0`（Asia/Shanghai） | core | `collect_validations`（UPDATE `resolved_at`，不物理删除） | `backend/api/catchup.py:195`（`GET /api/catchup/status` → `list_recent_validations`） | **否** — 仅防表膨胀；不清理亦不影响 correctness（读取侧已过滤 resolved） |
| 6 | `url_full_check` | interval 900s（硬编码常量 900） | core | `crawl_url_checks`（INSERT/UPDATE）、`hotspots.url_check_status` | `backend/services/source_alerter.py:118`（`http_status` / `url_check` 告警规则读 `crawl_url_checks` JOIN `crawler_runs`）；`backend/quality/url_content_gate.py` 间接读 `hotspots.url_check_status` | **是** — URL 有效性是 14 质量门禁之一，且驱动源告警 |
| 7 | `source_scheduler_tick` | interval 60s（硬编码常量 60） | core | `crawler_sources`（`UPDATE cadence/updated_at`）；实际采集经 `collection_service.run_one_source` → `hotspots` / `crawler_runs` | `backend/api/source_stats_api.py`（`GET /api/sources/health/v2`）；`backend/api/source_system_api.py` | **是** — per-source 差异化节奏的实际驱动者 |
| 8 | `v1_signal_intake_tick` | interval 1800s（`config.collect_interval_seconds`，默认 1800） | core | `v1_materials`、`v1_signals`、`v1_knowledge`；另 `hotspots.is_hidden`（语义补偿隐藏） | `backend/api/v1_signals_api.py:28`（`GET /api/v1/signals`）→ `frontend/src/api/v1.ts:679` → `frontend/src/components/v1/panels/SignalPanel.tsx`；`backend/services/command_bar_service.py` / `judgment_service.py` / `knowledge_ai.py` 读 `v1_materials` | **是** — 七段链路 Signal 段的唯一生产入口 |
| 9 | `source_probe` | cron `hour=3, minute=30`（Asia/Shanghai） | core | `crawler_sources`（`update_health_state`：status/enabled/consecutive_failures） | `backend/api/source_stats_api.py`（`POST /api/sources/{id}/probe` 同路径）；`backend/services/source_alerter.py` 读 `crawler_sources` | **否** — 死源探活为运营辅助；`source_revival_check` 已覆盖同类语义，二者功能重叠（C 档候选） |
| 10 | `source_alert_eval` | interval 300s（硬编码常量 300） | core | `source_alerts`（INSERT level/message/detail） | `backend/api/source_stats_api.py:85`（`GET /api/sources/alerts`）→ `frontend/src/api/sources.ts:186` | **否** — 告警可由手动 probe 触发替代；无阈值升级路径 |
| 11 | `source_health_check` | interval 900s（硬编码常量 900） | core | **无直接写表**（`source_health_service.check_all_health` 全 SELECT：读 `hotspots` / `crawler_runs` / `crawler_sources`） | `backend/api/source_health_api.py`（`GET /api/sources/health`）；`backend/api/source_stats_api.py` | **待裁** — 纯只读 job，与 API 端点实时查询功能重叠；保留则需证明其计算（口径）不可由 API 复现 |
| 12 | `auto_extract_alert` | interval 60s（硬编码常量 60） | core | `hotspot_tags` + `tags`（TagRepository upsert）；`alerts`（`alert_service.evaluate_hotspot` 触发规则时 INSERT）；`alert_events` | `backend/api/extract.py`（tags 查询）；`backend/api/alert_api.py`（alerts/alerts v2）→ `frontend/src/components/.../Alert*`；`backend/services/alert_service.py` 读 `hotspots` | **是** — 标签是 Feed 分类与兴趣引擎的输入；告警是资讯域告警面 |
| 13 | `kl_pipeline_heartbeat` | interval 60s（硬编码常量 60） | core | `kl_queue`（drain_due 改 status）；sweep 时重入队 | `backend/services/triggers/t1_raw_to_refine.py` 等 4 个 trigger 读 `kl_queue` 候选；`backend/api/kl_compounding_api.py`（`kl_dead_letters`） | **是** — KL 管线消费泵，wiki-first 编译链的 heartbeat |
| 14 | `secnews_liveness_sweep` | cron `day_of_week=sun, hour=2, minute=0`（**UTC**） | 扩展:`secnews`（gate=enabled） | **无直接写表** — 只改写 md frontmatter（`liveness` 字段，wiki_fs.liveness） | `backend/wiki_fs/liveness.py:140 liveness_counts`（观测台 S1-4）；md 为知识库真源，被 `knowledge_sync` 投影 | **待裁** — 扩展域；书签名存活的运营价值依赖 S1-3 观测台是否在用 |
| 15 | `kl_trigger_t1` | interval 60s（硬编码常量 60） | core | `kl_queue`（kl:raw → kl:refine 推进）；写 md frontmatter + `wiki_events`；`ai_scores` | `backend/services/triggers/t2_refine_to_link.py`（读 kl:refine 候选）；`backend/api/kl_pipeline_api.py` | **是** — 七段链路 Knowledge 段编译链 T1 段 |
| 16 | `kl_trigger_t2` | interval 120s（硬编码常量 120） | core | `kl_queue`（kl:refine → kl:link）；`knowledge_links` | `backend/services/triggers/t3_link_to_structure.py`；`backend/api/kl_compounding_api.py`（knowledge_links） | **是** — 编译链 T2 段 |
| 17 | `kl_dead_letter_retry` | interval 600s（硬编码常量 600） | core | **无直接写表** — 仅读 `kl_dead_letters`（`list_active_count`）做阈值告警（>50 warn） | `backend/api/kl_compounding_api.py`（`kl_dead_letters` 查询端点）；`backend/services/retry_policy.py` | **否** — docstring 明写「当前阶段仅做阈值告警，真正的重试逻辑后续引入」；只读 job |
| 18 | `kl_trigger_t3` | interval 600s（硬编码常量 600） | core | `kl_queue`（kl:link → kl:structure）；md frontmatter | `backend/services/triggers/t4_structure_to_publish.py`；`backend/api/kl_pipeline_api.py` | **是** — 编译链 T3 段 |
| 19 | `kl_trigger_t4` | interval 1800s（硬编码常量 1800） | core | `kl_queue`（kl:structure → kl:publish）；md frontmatter；`ai_scores` | `backend/api/knowledge.py`（knowledge_items 列表，`lifecycle='kl:publish'`）；`backend/services/triggers/t4_structure_to_publish.py` 后续被 `content_draft_generation` 消费 | **是** — 编译链终点，产出 published 知识 |
| 20 | `planning_action_check` | interval 600s（硬编码常量 600） | core | `planning_actions`（INSERT/UPDATE）、`planning_action_log`（事件流水） | `backend/api/kl_planning_api.py:20`（`GET /api/kl/planning-actions`）+ `:32`（PUT status）→ `frontend/src/components/sentinel/SentinelActionPage.tsx:178/224`（判读待办段） | **是** — 行动菜单「判读待办」数据源（v0.8.8 R-15 已保留该区块） |
| 21 | `compile_daily` | cron `hour=2`（minute 默认 0，Asia/Shanghai） | core | `knowledge_tasks`（INSERT pending 编译任务，pending 去重） | `backend/services/compiler.py::consume_compile_tasks`（由 job 22 消费）；`backend/api/knowledge.py` | **是** — 编译链生产者，与 job 22 构成生产/消费对 |
| 22 | `compile_consumer` | cron `hour=2, minute=30`（Asia/Shanghai） | core | `knowledge_tasks`（UPDATE status）；`knowledge_items`（分类 + lifecycle 流转 + md 回写）；`ai_scores`；`knowledge_concepts` | `backend/api/knowledge.py`（知识条目列表/详情）→ `frontend/src/api/knowledge.ts` | **是** — 编译链消费者，与 job 21 构成生产/消费对 |
| 23 | `knowledge_classify` | interval 1800s（硬编码常量 1800） | core | `knowledge_items`（UPDATE domain/type/difficulty/topic，不回写 md） | `backend/api/knowledge.py`（条目分类字段）→ `frontend/src/api/knowledge.ts`；`backend/services/planning_service.py`（读 domain） | **是** — 分类是规划动作与推荐的前置条件 |
| 24 | `knowledge_stub_backfill` | interval 21600s（硬编码常量 21600） | core | `knowledge_items`（UPDATE title/topic）；md 正文回写（`ai_write_back`） | `backend/api/knowledge.py`（条目列表/详情展示 title/topic） | **待裁** — 补全历史空壳条目；只影响存量数据一次性修复，不产生新能力 |
| 25 | `knowledge_chunk_generation` | interval 1800s（硬编码常量 1800） | core | `knowledge_chunks`（INSERT；FTS5 触发器自动索引 `knowledge_chunks_fts`） | `backend/api/knowledge_chunks_api.py`（`GET /api/knowledge/chunks/{id}`）→ `frontend/src/api/knowledge.ts:198` | **是** — FTS5 全文检索的唯一数据来源（无 chunk 则检索恒空） |
| 26 | `wiki_archiver` | cron `hour=3, minute=50`（Asia/Shanghai） | core | `knowledge_items`（UPDATE `lifecycle='kl:archived'`）；md 落 `llm-wiki-2.0/items/` + `sources/` + `retention.json`；`wiki_events` | `llm-wiki-2.0/` md 为知识域唯一真相源，被 `knowledge_sync` 投影（job 27）；`backend/api/knowledge.py` | **是** — wiki-first 存储哲学的归档侧执行者 |
| 27 | `wiki_projection_rebuild` | cron `hour=4, minute=10`（Asia/Shanghai） | core | `knowledge_items`（全量 upsert + 孤儿清理）、`knowledge_concepts`（全量 upsert） | `backend/api/knowledge.py`（`GET /api/knowledge/items`）；`backend/services/map_updater.py`（读 concepts） | **是** — wiki-first 契约的机制化兑现（md→SQLite 投影可重建） |
| 28 | `retention_decay` | cron `day_of_week=sun, hour=5, minute=30`（Asia/Shanghai） | core | **无直接写表** — 改写 `llm-wiki-2.0/retention.json`（Ebbinghaus `current_score`） | `backend/services/retention_engine.py`（自身读改写）；`scripts/check_retention_decay.py`（CI 校验 ≥0.7 占比）；`backend/services/knowledge_reuse.py`（衰减语义消费） | **是** — 记忆衰减语义实现（wiki-first，真源非表） |
| 29 | `sm2_daily_push` | cron `hour=8, minute=0`（Asia/Shanghai） | core | **无直接写表** — 只读 `sm2_reviews`（`review_service.list_due`），产出 SSE 事件 `review_due` | `backend/core/events.py::publish_event` → SSE → `frontend/src/components/knowledge/KnowledgeHubPage.tsx:99`（到期计数）；`frontend/src/contexts/I18nContext.tsx:243`（`kb.review_due`） | **是** — 复习到期推送是 SM-2 复利驱动器的用户触达面 |
| 30 | `map_rebuild_daily` | cron `hour=2, minute=0`（Asia/Shanghai） | core | **无直接写表** — 改写 `llm-wiki-2.0/_MAP.md` | `backend/services/knowledge_sync.py` / `backend/wiki_fs/paths.py`；`llm-wiki-2.0/_MAP.md` 供人查阅与 skill 消费（`backend/services/skill_registry/builtin.py`） | **否** — 派生索引，可随时重建；`_MAP.md` 为文档产物不影响运行 |
| 31 | `attention_aggregate` | interval 1800s（硬编码常量 1800） | core | `attention_events`（DELETE >30d）；`knowledge_items.attention_score`（批量 UPDATE） | `backend/api/attention_events_api.py`（`GET /api/attention/events`）→ `frontend/src/api/knowledge.ts:271`；`attention_score` 被 job 45 作候选排序键 | **是** — 注意力评分是「知识→内容」驱动链的排序输入 |
| 32 | `cg_upstream_sync` | cron `hour=9`（minute 默认 0，Asia/Shanghai） | 扩展:`codegarden`（gate=enabled） | `knowledge_tasks`（INSERT task_type='project_sync'） | `backend/services/codegarden_project_service.py`（watchdog/TaskExecutor 执行）；`backend/api/codegarden.py:407` | **否** — 扩展域；仅服务 CodeGarden 项目生命周期，与七段主干无交集 |
| 33 | `cg_service_scan` | interval 300s（硬编码常量 300） | 扩展:`codegarden_phase2b`（gate=enabled） | `cg_services`（upsert 本机 lsof/docker/pm2 服务） | `backend/api/codegarden_ops.py:166`（`GET /api/codegarden/services`）；`backend/services/codegarden_orchestration_service.py`；`frontend/src/components/sentinel/SentinelGardenPage.tsx`（R-14 待退役页） | **否** — 扩展域；R-14 退役泳道页后前端消费方进一步减少 |
| 34 | `cg_event_process` | interval 60s（硬编码常量 60） | 扩展:`codegarden_phase2b`（gate=enabled） | `cg_events`（UPDATE status/processed_at/error_message） | `backend/api/codegarden_ops.py`（事件列表）；`backend/services/codegarden_orchestration_service.py`；`backend/services/cost_monitor.py` | **否** — 扩展域；MVP 实现「所有事件类型直接标记成功」，无实际 handler 分发 |
| 35 | `cg_drift_assess` | interval 3600s（硬编码常量 3600） | 扩展:`tech_stack`（gate=enabled） | `cg_drift_assessments`（INSERT/UPDATE） | `backend/api/codegarden_phase14.py`（漂移评估查询端点）；`backend/services/codegarden_drift.py` | **否** — 扩展域；技术栈漂移评估非七段主干 |
| 36 | `mitre_sync` | cron `day_of_week=sun, hour=4, minute=0`（Asia/Shanghai） | 扩展:`security_graph`（gate=enabled） | `security_entities`、`security_edges`（增量 upsert） | `backend/api/security.py:38/88`（`GET /api/security/entities`、`/graph`）→ `frontend/src/components/security/SecurityGraph.tsx`；`backend/security/graph.py:89/120` | **是** — 安全图谱 MITRE 侧数据源（`/knowledge/process` 菜单） |
| 37 | `cve_sync_to_security` | interval 1800s（硬编码常量 1800） | 扩展:`security_graph`（gate=enabled） | `security_entities`（INSERT/UPDATE，entity_type='cve'） | `backend/api/cve_analytics.py:34`（最近 CVE 清单）；`backend/api/security.py` | **是** — CVE 侧安全图谱数据源 |
| 38 | `security_entity_concept_sync` | interval 600s（硬编码常量 600） | core | `security_entities`（INSERT）、`item_entities`（INSERT）、`knowledge_concepts`（高频实体 → concept） | `backend/api/codegarden_phase14.py:50/115`（item_entities↔security_entities 双向）；`backend/api/knowledge_concepts.py`（concept 链接）；`backend/api/security.py` | **是** — 安全域与知识域命名空间统一，`/knowledge/process` 跨域互引的前提 |
| 39 | `secrets_rotation_check` | cron `hour=9, minute=0`（Asia/Shanghai） | core | `settings`（kv: `secrets.rotation.last_notified_at`）；`audit_log`（action='secrets.rotation_reminded'）；`observability_alerts`（经 `alert_dispatcher.dispatch`） | `backend/api/secrets_rotation_api.py`；`backend/api/observability_metrics_api.py:89`（alerts/active）→ `frontend/src/components/secnews/observability/ActiveAlertsBanner.tsx` | **是** — 主密钥轮换提醒，安全基线必需 |
| 40 | `mp2_extract` | cron `hour=3, minute=30`（Asia/Shanghai） | 扩展:`security_graph`（gate=enabled） | `event_technique_candidates`（INSERT owner_status='pending'）；`incident_reports`（读） | `backend/api/event_technique_api.py:62`（`GET /api/event-technique/candidates`）；`backend/services/attack_label_service.py`（审定后 `event_technique_map`） | **否** — 候选池需人工审定才生效，且非七段主干 |
| 41 | `daily_snapshot` | cron `hour=0, minute=30`（**UTC**） | core | `trend_daily_snapshots`（INSERT，ON CONFLICT 覆盖） | `backend/repository/weekly_report_repo.py:121`（`get_range`）→ `backend/services/weekly_report_service.py:103`（`generate_report` 组装 trend_weekly）→ `backend/api/weekly_report.py:22`（`GET /api/weekly-report/latest`） | **否** — 产出仅被周报（job 42）消费；R-03 裁决 `weekly_report` router 后，唯一消费路径收窄到 `/api/reports/weekly/*`（该路径读 `hotspots` 不读 `trend_daily_snapshots`） |
| 42 | `weekly_report` | cron `day_of_week=mon, hour=2, minute=0`（**UTC**） | core | `weekly_reports`（INSERT/UPDATE，ON CONFLICT week_start） | `backend/api/weekly_report.py:14/22/28`（`GET /api/weekly-report*`）— **前端 0 调用点**；`backend/services/skill_registry/builtin.py:476` 引用 `weekly_report_overview_service`（该 service 读 `hotspots` 不读 `weekly_reports`） | **否** — `weekly_reports` 表唯一读取方是 R-03 待退役的 router；PRD 附录 A.1 已确证 `weekly_report` router 无前端调用点 |
| 43 | `stats_daily` | cron `hour=6`（minute 默认 0，Asia/Shanghai） | core | **无直接写表** — 只读 `content_calendar`（`stats_recycle_service.recycle_stats`），平台 API 未接入故**仅 log** | 无（`content_calendar` 读取方另有 `backend/api/content.py` + `frontend/src/components/ContentCalendar.tsx`，与本 job 产出无关） | **否** — 降级实现：`recycled` 恒 0、`skipped` 恒 N，无任何实际回收 |
| 44 | `digest_generator` | cron `hour=8, minute=0`（Asia/Shanghai） | core | `digests`（INSERT/UPDATE summary/item_ids/summary_md）；md 落 `llm-wiki-2.0/digest/` | `backend/api/digests.py:76/87/39`（`GET /api/digests`、`/latest`、`/priority`）→ `frontend/src/hooks/useDigest.ts:24`、`frontend/src/components/sentinel/PriorityDigestCard.tsx:46` | **是** — 资讯菜单简报卡数据源（R-15 资讯菜单结构优化的复用对象） |
| 45 | `content_draft_generation` | interval 21600s（硬编码常量 21600） | core | `content_drafts`（create_draft 落盘 + `knowledge_repo`）；`content_calendar`（自动排期 +7d） | `backend/api/content.py:60/79`（`GET/POST /api/content/drafts`）→ `frontend/src/components/ContentDraftList.tsx:25/64`；`frontend/src/components/ContentCalendar.tsx:6` | **是** — 知识→内容闭环的唯一自动产出通道 |
| 46 | `sync` | cron `day_of_week=mon, hour=10, minute=30`（Asia/Shanghai） | 扩展:`sync`（gate=enabled） | `sync_history`（INSERT status='error'/'ok'）；`sync_states`；`cg_projects` / `cg_services` / `tags` / `hotspot_tags` / `reading_states` / `annotations` 等（`sync_bundle` 反序列化落库） | `backend/api/sync.py`；`backend/api/maintenance_db_api.py`（sync_history）→ `frontend/src/components/SyncPage.tsx`；`backend/services/sync_merge.py` | **否** — 跨端配置同步为单机单用户场景的**可选**能力，非七段闭环必需 |
| 47 | `weekly_maintenance` | cron `day_of_week=sun, hour=4`（minute 默认 0，Asia/Shanghai） | core | `SOUL.md`（md）；`knowledge/summaries/weekly-*.md`（md）；`v1_knowledge`（scheduled_migrate_job）；按 `scripts/retention.json` 台账批量 truncate：`ai_scores` `annotations` `catchup_checkpoints` `catchup_runs` `cg_dependencies` `cg_events` `collect_validations` `collection_runs` `content_calendar` `content_drafts` `content_fingerprints` `coverage_runs` `crawl_url_checks` 等 | `backend/api/knowledge.py`（knowledge_items）；`llm-wiki-2.0/SOUL.md`（skill_registry 消费）；`backend/api/catchup.py`（catchup_runs）；`backend/api/content.py`（content_calendar/drafts） | **是** — 组合 job：SOUL 画像 + 周回顾 + 库瘦身 + 备份轮转，缺任一子链则周维度闭环断 |
| 48 | `telemetry_window` | cron `day_of_week=sun, hour=5`（minute 默认 0，Asia/Shanghai） | core | 按 `scripts/retention.json` 台账（`scheduled_in == "telemetry_window"`）：`crawler_runs`（truncate 7d）、`raw_items`（truncate 7d）、`quality_check_logs`（archive → `quality_check_logs_archive`，21d 三档） | `backend/api/quality_api.py`（读 `quality_check_logs` + `raw_items`）；`backend/api/maintenance_retention_api.py:49`（qcl purge）；`backend/services/source_health_service.py`（读 `crawler_runs`） | **是** — WARM 层无限增长会拖垮主库（`quality_check_logs` 是主膨胀源），属运维必需 |
| 49 | `daily_db_backup` | cron `hour=4, minute=30`（Asia/Shanghai） | core | **无直接写表** — 写文件：`backups/hotspot-{ts}.db` / `hotspot-warm-{ts}.db` / `hotspot-cold-{ts}.db` / `.knowledge.zip` / `backup-manifest-{ts}.json` | `backend/services/backup_verify_service.py`（job 50 读备份文件校验）；`backend/api/maintenance_db_api.py`（手动备份/恢复）；`scripts/check_backup_chain.py`（CI 链路校验） | **是** — 数据可恢复性底线 |
| 50 | `backup_verify` | cron `day_of_week=mon, hour=2, minute=0`（Asia/Shanghai） | core | `audit_log`（失败留痕 `record_audit("backup_verify.failed")`） | `backend/api/observability_audit_api.py`（audit_log 查询）；`backend/api/observability_metrics_api.py` | **是** — 灾难检查自身失效会静默（v0.8.2 Y-A4 引入原因） |
| 51 | `observability_ttl` | interval 3600s（硬编码常量 3600） | core | DELETE（TTL 清理）：`job_runs` 30d、`agent_runs` 30d、`process_events` 14d、`audit_log` 90d、`api_events` 7d、`observability_alerts` 30d；另回收超时 v1 evidence intent | `backend/api/ops_runs_api.py`（job_runs）；`backend/api/observability_metrics_api.py`（api_events/alerts）；`backend/api/observability_audit_api.py`（audit_log）；`backend/api/agent_runs`（agent_runs） | **是** — 观测表无限累积（DEV-0321 记录过 TTL 停摆事故） |
| 52 | `observability_aggregator` | interval 3600s（硬编码常量 3600），start_date 偏移 +5min | core | `api_metrics_hourly`（INSERT OR REPLACE，幂等） | `backend/api/observability_metrics_api.py:63`（`GET /api/observability/timeseries`）→ `frontend/src/components/secnews/observability/ObservabilityDashboard.tsx`；`backend/services/observability_query_service.py` | **是** — p50/p95 指标唯一来源（M-9 链路耗时指标依赖） |
| 53 | `observability_threshold_check` | interval 3600s（硬编码常量 3600），start_date 偏移 +10min | core | `observability_alerts`（INSERT，含 cooldown 去重）；`audit_log`（action='threshold.breach'） | `backend/api/observability_metrics_api.py:89`（`GET /api/observability/alerts/active`）+ `:99`（ack）→ `frontend/src/components/secnews/observability/ActiveAlertsBanner.tsx:69` | **是** — 阈值告警的生产者；被 job 52 的聚合结果驱动 |
| 54 | `profile_decay` | cron `hour=3, minute=0`（Asia/Shanghai） | core | `personal_profile`（UPDATE `weight = weight * 0.95` + `decayed_at`） | `backend/api/mcp_adapters.py:37-41`（读 `personal_profile`）；`backend/services/feedback_service.py:67`（`profile_service.record_feedback`）；`backend/api/feedback_api.py:60`（`GET /api/feedback/profile`） | **否** — 权重衰减是兴趣引擎 L3 微调；`interest_engine` gate 已关闭该域的影响面有限 |
| 55 | `worker_queue_pump` | interval 60s（硬编码常量 60） | core | `trigger_tickets`（UPDATE status='done'/'failed'/'pending'、attempts、finished_at） | `backend/api/skill_registry_api.py:139`（入队侧 `trigger_gate.submit`）；`backend/services/trigger_gate/worker.py`；`backend/services/skill_runner/result.py`、`backend/services/playbook_engine/core.py`（读回执） | **是** — skill/playbook 触发的唯一出队泵（`trigger_gate` gate=enabled） |
| 56 | `legacy_hold_reap` | cron `day_of_week=mon, hour=4, minute=30`（Asia/Shanghai） | core | `trigger_tickets`（UPDATE status='legacy_hold'）；`audit_log`（action='ticket.legacy_hold'） | `backend/api/observability_audit_api.py`（audit_log）；`backend/services/trigger_gate/core.py`（读 status） | **待裁** — F01 收口的一次性治理；pending 票据已归零后为空转，但 pending 仍会由新 skill 入队产生 |
| 57 | `knowledge_review_due` | cron `hour=4, minute=0`（Asia/Shanghai） | core | `v1_cases`（UPDATE `tags_json` 追加 `knowledge_review_due:{id}` marker） | `backend/api/v1_cases` 案件查询（`backend/api/mcp_operations.py:43` `list_cases`）；`frontend/src/api/v1.ts` Case 段（`getCaseAggregate`） | **是** — SK-06 复查到期 → Case blocker，是「知识→行动」闭环的自动推进机制 |
| 58 | `legacy_promote_due` | **interval 60min**（APScheduler 字符串 trigger `trigger="interval", minutes=60`） | core | `v1_knowledge`（UPDATE status='published'，CAS + revision+1，走 `knowledge_legacy_bridge.promote_legacy`）；`v1_legacy_promote_log`（INSERT 防重） | `backend/api/legacy_migrate_v1_api.py:145/154`（`GET .../promote-log`）；`backend/api/v1_knowledge_query_api.py`（published 知识查询） | **否** — legacy 5 态 → published 的后台 promote，源是 v0.8 之前的旧数据；随 legacy 域收敛可退役 |
| 59 | `legacy_migrate_resume` | **interval 30min**（APScheduler 字符串 trigger `trigger="interval", minutes=30`） | core | `v1_legacy_mapping`（读 status='failed'；promote 时 UPDATE status）；`v1_knowledge`（promote 连带） | `backend/api/legacy_migrate_v1_api.py`（mapping 查询端点）；`backend/api/legacy_items_migrate_api.py` | **否** — 与 job 58 同族；legacy 迁移链的历史补数，源数据收敛后可退役 |

---

## 3. gate 归属统计与「无 gate 归属 job = 0」验证

### 3.1 判定链（三跳，非文件名猜测）

```
scheduler.py::_is_job_enabled(job_id)
  → backend/extensions/__init__.py::JOB_TO_EXTENSION   (由 EXTENSION_JOBS 反向派生)
    → is_extension_enabled(ext)
      → backend/config/feature_gates.toml  [extensions] 节
```

`JOB_TO_EXTENSION` 中共 **9 个 job** 有扩展归属；其余 50 个 `ext is None` → `_is_job_enabled` 恒 True → **core**。

### 3.2 分布统计

| 归属 | job 数 | job id |
|---|---|---|
| **core**（无扩展归属，恒启用） | **50** | collect_all、source_reputation_rebuild、catchup_watchdog、source_revival_check、collect_validations_cleanup、url_full_check、source_scheduler_tick、v1_signal_intake_tick、source_probe、source_alert_eval、source_health_check、auto_extract_alert、kl_trigger_t1、kl_trigger_t2、kl_dead_letter_retry、kl_trigger_t3、kl_trigger_t4、planning_action_check、compile_daily、compile_consumer、knowledge_classify、knowledge_stub_backfill、knowledge_chunk_generation、wiki_archiver、wiki_projection_rebuild、retention_decay、sm2_daily_push、map_rebuild_daily、attention_aggregate、security_entity_concept_sync、secrets_rotation_check、daily_snapshot、weekly_report、stats_daily、digest_generator、content_draft_generation、weekly_maintenance、telemetry_window、daily_db_backup、backup_verify、observability_ttl、observability_aggregator、observability_threshold_check、profile_decay、worker_queue_pump、legacy_hold_reap、knowledge_review_due、legacy_promote_due、legacy_migrate_resume |
| 扩展:`codegarden`（enabled） | 1 | cg_upstream_sync |
| 扩展:`codegarden_phase2b`（enabled） | 2 | cg_service_scan、cg_event_process |
| 扩展:`tech_stack`（enabled） | 1 | cg_drift_assess |
| 扩展:`security_graph`（enabled） | 3 | mitre_sync、cve_sync_to_security、mp2_extract |
| 扩展:`secnews`（enabled） | 2 | kl_pipeline_heartbeat、secnews_liveness_sweep |
| 扩展:`sync`（enabled） | 1 | sync |
| **合计** | **59**（50 core + 9 扩展） | |

### 3.3 验收 ② 验证：无 gate 归属的 job 数 = **0** ✅

- 59 个 job **全部**有明确归属：50 个 core（`_is_job_enabled` 恒 True）+ 9 个显式扩展 gate（`JOB_TO_EXTENSION` 覆盖）。
- 9 个扩展 job 的 gate 状态（读 `feature_gates.toml`）：`codegarden=true`、`codegarden_phase2b=true`、`tech_stack=true`、`security_graph=true`、`secnews=true`、`sync=true` → **当前全部 enabled**。
- 注：`feature_gates.toml` 共 16 个 gate，其中 15 开 1 关（`mcp=false`）。**`mcp` 不占任何 job**（`EXTENSION_JOBS` 无 mcp 条目），故 9 个扩展 job + 50 core 覆盖全部 59。

---

## 4. 「写入表无任何读取方」的 job 清单 + 裁决建议

> 判定标准：除写入方自身（含其 repo 层）外，**全仓后端 api/service/repository/scheduler + 前端 src 均无读取路径**。仅有测试读取 → 计为「无生产读取方」。

### 4.1 强候选（产出物完全无生产读取方）

| job id | 写入表 / 产出 | 唯一读取方现状 | 裁决建议 | 理由 |
|---|---|---|---|---|
| `weekly_report` (#42) | `weekly_reports` | 仅 `backend/api/weekly_report.py`（5 端点）读取；**前端 0 调用点**（`/api/reports/weekly/*` 走 `weekly_report_overview_service`，读的是 `hotspots` 而非 `weekly_reports`）。PRD 附录 A.1 已把 `weekly_report` router 判为 A 档（仅删 router） | **下线**（连带 job，见 4.3） | 表的唯一消费方是待退役 router；job 本身每周一产出无人读的报告。**但需与 R-03 同 commit 处置**：R-03 明确要求「保留 `weekly_report_service.py` 与 `digest.py` 调度链」，与本裁决冲突 → **须在 P1 裁决表中显式对齐** |
| `daily_snapshot` (#41) | `trend_daily_snapshots` | 仅 `weekly_report_repo.py:121 get_range` → `weekly_report_service.py:103 generate_report`（即 job 42 的组装步骤）→ job 42 的 router | **下线**（与 job 42 同批） | 唯一消费链终点是 `weekly_reports` 表；job 42 下线后本 job 产出彻底无读取方 |
| `stats_daily` (#43) | **无直接写表**（只读 `content_calendar` 且仅 log） | 无产出可读 | **下线** | 平台 API 未接入，`recycled` 恒 0、`skipped` 恒 N，零实际效果；纯 60s/6h 定时 log 噪声 |
| `kl_dead_letter_retry` (#17) | **无直接写表**（只读 `kl_dead_letters` 做 >50 阈值告警） | 产出 = 日志告警，无结构化消费 | **观察**（不立即下线） | 只读监控 job，告警有运维价值；但 docstring 明写「真正重试逻辑后续引入」→ 若 P2 消融确认无人在看该 warn，可转下线 |
| `map_rebuild_daily` (#30) | **无直接写表**（改写 `llm-wiki-2.0/_MAP.md`） | `_MAP.md` 供人查阅 / skill 消费；`backend/wiki_fs/paths.py:73` 标注为「Deprecated single-file artefacts」 | **观察** | wiki-first 哲学下 md 是真源；但 `_MAP.md` 是派生索引可随时重建 → 候选「降频」（每日 → 每周）而非下线 |
| `source_health_check` (#11) | **无直接写表**（全 SELECT） | 产出仅日志；数据面另有 `backend/api/source_health_api.py` 实时查询 | **观察** | 与 API 端点功能重叠。判定「待裁」：需证明其口径（含 24h 窗口聚合）不可由 API 复现，否则应转 API-only |
| `security_entity_concept_sync` (#38) → 部分 | `item_entities` | `backend/api/codegarden_phase14.py:50/115`（漂移评估 + CVE 双向同步） | **保留** | 跨域互引有真实 API 消费方 |
| `mp2_extract` (#40) | `event_technique_candidates` | `backend/api/event_technique_api.py:62`（`GET /api/event-technique/candidates`） | **保留** | 有 API 消费方（候选审阅入口）；但扩展域 + 需人工审定 → **闭环必需性判「否」**（非七段主干），属产品取舍而非技术孤立 |
| `profile_decay` (#54) | `personal_profile` | `backend/api/mcp_adapters.py:37-41`、`backend/api/feedback_api.py:60` | **保留**（技术）；**闭环必需性判「否」** | 有读取方，但 `mcp` gate 当前为 false，`/api/feedback/profile` 走 `feedback_log` 而非 `personal_profile` → 实际读取面窄 |
| `collect_validations_cleanup` (#5) | `collect_validations`（仅 UPDATE resolved_at） | `backend/api/catchup.py:195` 有读取方（`GET /api/catchup/status`） | **保留** | 有读取方；判「否」仅因是防膨胀而非必需功能 |
| `source_alert_eval` (#10) | `source_alerts` | `backend/api/source_stats_api.py:85` → `frontend/src/api/sources.ts:186` | **保留** | 有前端消费方；判「否」是产品取舍 |
| `cg_service_scan` (#33) | `cg_services` | `backend/api/codegarden_ops.py:166` | **保留** | 有 API 消费方；R-14 退役泳道页后前端消费减少，但 `/codegarden` 扩展页仍在 |
| `cg_event_process` (#34) | `cg_events` | `backend/api/codegarden_ops.py` | **保留** | 有 API 消费方 |
| `cg_drift_assess` (#35) | `cg_drift_assessments` | `backend/api/codegarden_phase14.py` | **保留** | 有 API 消费方 |
| `cg_upstream_sync` (#32) | `knowledge_tasks` | `backend/api/codegarden.py:407`（同类触发）+ `codegarden_project_service.py` | **保留** | 有消费方 |
| `sync` (#46) | 多表（sync_history / sync_states / cg_projects / cg_services / tags / hotspot_tags / reading_states / annotations） | `backend/api/sync.py` → `frontend/src/components/SyncPage.tsx` | **保留** | 有前端消费方；判「否」是「单机单用户可选能力」的产品定位 |
| `legacy_hold_reap` (#56) | `trigger_tickets` + `audit_log` | `backend/api/observability_audit_api.py`（audit_log）；`trigger_gate/core.py`（status） | **观察** | 写入表有读取方；判「待裁」是因 pending 票据来源已变（legacy F01 批次） |
| `legacy_promote_due` (#58) / `legacy_migrate_resume` (#59) | `v1_legacy_promote_log` / `v1_legacy_mapping` / `v1_knowledge` | `backend/api/legacy_migrate_v1_api.py:145/154`（promote-log 端点） | **观察** | 有 API 读取方，但属 legacy 历史数据收口链；随 legacy 域收敛可退役 |

### 4.2 无「完全无读取方」的 job 复核结论

逐条复核后：**59 个 job 中，不存在「写入表完全无任何读取方（含 API / 前端 / service）」的 job**。
- 上表 4.1 中标「无直接写表」的 6 个 job（`source_health_check` / `kl_dead_letter_retry` / `map_rebuild_daily` / `retention_decay` / `sm2_daily_push` / `stats_daily` / `daily_db_backup`）均为**只读或只写文件**，其产出要么是 md/JSON 文件（wiki-first 真源），要么是 SSE 事件（`sm2_daily_push` 有前端消费），要么是备份文件（job 50 读），要么无产出（`stats_daily` / `kl_dead_letter_retry`）。
- **真正的「产出物无读取方」只有 3 个**：`weekly_report`（`weekly_reports` 表，前端 0 调用）、`daily_snapshot`（`trend_daily_snapshots`，唯一消费链终点是 `weekly_report`）、`stats_daily`（无产出）。

### 4.3 裁决建议汇总

| 建议 | job | 数量 | 处置要点 |
|---|---|---|---|
| **下线** | `weekly_report` (#42)、`daily_snapshot` (#41)、`stats_daily` (#43) | 3 | `weekly_report`+`daily_snapshot` 必须**同批**（互为唯一消费链），且需先与 R-03 的「保留 service 与 digest 调度链」约束对齐；`stats_daily` 独立可下线 |
| **观察**（P2 消融后定） | `kl_dead_letter_retry` (#17)、`map_rebuild_daily` (#30)、`source_health_check` (#11)、`secnews_liveness_sweep` (#14)、`knowledge_stub_backfill` (#24)、`legacy_hold_reap` (#56) | 6 | 消融口径：关闭对应 job 后跑 T2+T5，观测「零失败且零观测变化」→ 降级为下线 |
| **保留**（但闭环必需性判「否」，供 P1 产品取舍） | `source_revival_check` (#4)、`collect_validations_cleanup` (#5)、`source_probe` (#9)、`source_alert_eval` (#10)、`cg_upstream_sync` (#32)、`cg_service_scan` (#33)、`cg_event_process` (#34)、`cg_drift_assess` (#35)、`mp2_extract` (#40)、`sync` (#46)、`profile_decay` (#54)、`legacy_promote_due` (#58)、`legacy_migrate_resume` (#59) | 13 | 保留技术可达性（有真实 API/前端读取方），闭环必需性判「否」交 P1 裁决；其中 9 个为扩展域 job |

---

## 5. 「是否闭环必需」统计

| 判定 | job 数 | 说明 |
|---|---|---|
| **是** | **37** | 核心链路必需（资讯获取 → 知识沉淀 → 落地执行）+ 观测/备份/运维底线 |
| **否** | **18** | 无下游消费 / 仅历史补数 / 扩展域非主干 / 可选能力 |
| **待裁** | **4** | 需 P2 消融或产品决策才能定性 |
| **合计** | **59** ✅ | 与 §2 主表逐行一致，无重叠、无遗漏 |

明细（按 §2 主表 # 序号）：

- **是（37）**：1, 2, 3, 6, 7, 8, 12, 13, 15, 16, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29, 31, 36, 37, 38, 39, 44, 45, 47, 48, 49, 50, 51, 52, 53, 55, 57
- **否（18）**：4, 5, 9, 10, 17, 30, 32, 33, 34, 35, 40, 41, 42, 43, 46, 54, 58, 59
- **待裁（4）**：11, 14, 24, 56

**「是」（37）分组说明**（各 job 只归一组，计数与 # 序号完全一致）：
- 资讯获取链（7）：1 collect_all、2 source_reputation_rebuild、3 catchup_watchdog、6 url_full_check、7 source_scheduler_tick、8 v1_signal_intake_tick、12 auto_extract_alert
- 知识沉淀链（12）：13 kl_pipeline_heartbeat、15/16/18/19 kl_trigger_t1~t4、21 compile_daily、22 compile_consumer、23 knowledge_classify、25 knowledge_chunk_generation、26 wiki_archiver、27 wiki_projection_rebuild、28 retention_decay
- 行动/落地链（4）：20 planning_action_check、29 sm2_daily_push、31 attention_aggregate、45 content_draft_generation
- 安全图谱链（3）：36 mitre_sync、37 cve_sync_to_security、38 security_entity_concept_sync
- 运维与观测底线（11）：39 secrets_rotation_check、44 digest_generator、47 weekly_maintenance、48 telemetry_window、49 daily_db_backup、50 backup_verify、51 observability_ttl、52 observability_aggregator、53 observability_threshold_check、55 worker_queue_pump、57 knowledge_review_due

> 分组小计 7 + 12 + 4 + 3 + 11 = **37** ✅（无重叠、无遗漏，与「是（37）」序号清单完全一致）

---

## 6. 已知不确定项

| # | 不确定项 | 缺什么证据 | 建议补证方式 |
|---|---|---|---|
| 1 | **`weekly_report` / `daily_snapshot` 是否可下线** | 与 R-03 硬性要求「保留 `weekly_report_service.py` 与 `digest.py` 调度链」冲突；R-03 验收② 要求「`digest` job 仍正常执行（调度日志可见 `take_daily_snapshot` 计数）」——而 `take_daily_snapshot` 正是 job 41 | **P1 裁决表必须显式对齐**：若 R-03 保留 job 41，则 job 42 的唯一消费链仍在，`weekly_reports` 表不能因「无前端调用」就判死。需用户提供裁决 |
| 2 | **`weekly_reports` 表是否真的零消费** | `backend/api/weekly_report.py` 5 个端点仍在注册（`_registry_core.py:52/85`），可能存在文档/运维手工调用（RUNBOOK 未逐条核验） | 查 `docs/RUNBOOK.md` / `docs/ADMIN_MANUAL.md` 中 `/api/weekly-report` 引用；查 `backend/data/` 与 skill_registry 内置 skill 是否调用 |
| 3 | **runtime 实际 job 数 ≠ 59** | 本盘点为**注册期静态**枚举；`_is_job_enabled` 在 `start()` 时求值（启动期快照），且 `feature_gates.toml` 支持 `HOTSPOT_FEATURE_GATES` env 覆盖 | 启动后 `GET /api/health` 或 `scheduler.get_jobs()` 读运行时数；本次为只读盘点，未启动服务 |
| 4 | **`collect_all` 的 post-ingest 链写入表清单** | `collect_all` 内串 11 个子任务（含 `_auto_intake_tick` / `_news_alert_tick` / `_pick_score_tick` / `_rejection_explain_tick` 四个 2026-09/10 新增链，函数体不在 `backend/scheduler/jobs/` 内） | 已追到主表 `hotspots`/`collection_runs` 等；四个新链的具体写表未逐条展开（其产出均在 `hotspots`/`alert_events`/`interest_signals` 域内，属主表已覆盖范围） |
| 5 | **`source_health_check` 与 `source_health_api` 的口径差异** | 未逐字段比对 `check_all_health` 与 API 端点返回结构是否等价 | 需读 `backend/api/source_health_api.py` 与 `source_health_service.check_all_health` 做字段级 diff |
| 6 | **`process_events` 表无生产读取方** | 该表由 `backend/observability_records.py:198` 写入（ProcessSupervisor 钩子），由 job 51 TTL 清理；无 API/服务读取路径 | 该写入**不在 job 内**（由 dsh/agent 进程钩子写入），故不在本表 59 job 的「写入表」列内；但它是「无读取方的观测表」候选，建议并入 R-04 一并裁决 |
| 7 | **`secret_access_logs` 表无写入方** | 全仓仅 `backend/repository/secrets_repo.py:298` 的 DELETE（reset 时清空），未找到 INSERT | 疑为历史设计（unlock/reveal 审计）未接线；与 job 无关，但属同类「无消费表」候选 |
| 8 | **`legacy_promote_due` / `legacy_migrate_resume` 的 trigger 语义** | 两者用 APScheduler **字符串 trigger**（`trigger="interval", minutes=60/30`），非 `IntervalTrigger` 对象，与其余 57 个写法不同 | 已确认实际生效（APScheduler 支持字符串别名 `interval`）；但需确认其 `start_date` 缺省行为是否与 `IntervalTrigger` 一致（本次未做运行时验证） |
| 9 | **`.mimosa` 基线快照文件已排除** | 扫描时排除了 `frontend/src/**/.mimosa/hook-state/**`（会话基线快照，含已删除代码的 `.source` 副本） | 若未来有人把基线快照误当源码，会得到虚假的消费方（如 `/api/trends`）；本盘点已排除，但建议 review 时同样注意 |
| 10 | **写入表归并粒度** | 一个 job 常写多表（如 `collect_all` 写 10+ 表；`weekly_maintenance` 按 `retention.json` truncate 20+ 表）。主表列写的是**主要表 + 代表性副表**，非穷举 | 完整写入图需逐 job 展开 `retention.json` 台账与 repo 调用链；本盘点的裁决结论不依赖穷举（只依赖「是否有读取方」） |

---

## 7. 验收对照（PRD §4.7）

| 验收标准 | 结论 | 证据 |
|---|---|---|
| ① 59 行表格齐全 | ✅ **通过** | `count_jobs()` = 59；复刻 AST = 59；主表 §2 共 59 行，编号 1–59 无缺 |
| ② 无 gate 归属的 job 数为 0 | ✅ **通过** | §3.3：50 core + 9 显式扩展 gate = 59，无归属空缺；判定链为 `_is_job_enabled` → `JOB_TO_EXTENSION` → `feature_gates.toml`，未按文件名猜 |
| ③ 「写入表无任何读取方」的 job 单独列出并给出裁决建议 | ✅ **通过** | §4 独立小节；结论：**严格意义上 0 个**（每张表均有 API 或 service 读取路径），但「产出物无读取方」3 个（`weekly_report` / `daily_snapshot` / `stats_daily`）+「只读无产出」3 个（`stats_daily` / `kl_dead_letter_retry` / `source_health_check`），均给出 下线/观察/保留 裁决 |

---

*本盘点为 P0 只读产出，未修改任何业务代码；本文件是本次任务的唯一写入物。实现侧不自称 PASS —— §6 的 10 项不确定项须在 P1 裁决前逐条闭环。*
