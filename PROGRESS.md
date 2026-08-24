# v0.5 重构执行进度（PROGRESS.md）

> 规格文件：`docs/v0.5_refactor_plan.md`（唯一真理）。接手会话先读本文件，不重做已完成任务。
> 止损：基线不符→BLOCKED.md；连败 3 次→停；劣于基线→回滚如实报告。
>
> **2026-08-21 SPEC 更替**：正式 SPEC 已改写为「统一前端 + DeepSeek Harness 认知层 + llm-wiki-2.0」方案
> （取代旧的性能+Workbench+自研 AiHub 版，旧版归档于 `docs/archived/v0.5_refactor_plan_perf_only.md`）。
> M1 性能三任务 / M2 DB 瘦身承接不变；M3 改为 editorial 对齐填空；M3.5 为 llm-wiki-2.0 数据底座；
> M4 改为 dsh 认知层。T0 已完成项保留。
>
> ## 5 文件用法（接手必读）
> | 文件 | 角色 | 用法 |
> |---|---|---|
> | `docs/v0.5_refactor_plan.md` | **正式 SPEC（唯一真理）** | 执行时只读它。M1→M5 定义/硬指标/验收全在 §1。 |
> | `docs/archived/v0.5_refactor_plan_perf_only.md` | 旧计划归档 (性能+Workbench+AiHub v1) | 查 v1 细节/后悔回退时参考。 |
> | `docs/archived/v0.5_refactor_plan_wiki_v2.md` | 并行 v2 归档 (llm-wiki-2.0) | 执行 M3.5 的参考底稿：细节 Task 4-17 在此。 |
> | `PROGRESS.md`（本文件） | 执行进度台账 | 每次动手前后必读写；接手会话第一件事读它。 |
> | `docs/FRONTEND_BACKEND_ALIGNMENT_AUDIT.md` | 前后端能力对齐审计 | 执行 M3（editorial 接满）时的功能清单源头（54 router × 207 tsx 映射）。 |
> 协作流：读本文件 → 翻 SPEC §1 该做什么 → 打开审计清单定位功能 → 做任务 → 回来勾选并记录。

## 基线档案（2026-08-20/21 实测）

| 指标 | 基线值 | 目标 | 测量命令 |
|------|--------|------|----------|
| 后端测试收集数 | **2573**（0 error，含 M2-T4 db_diet 9 + M2-T5 cli_contract 7 + sse_events 8 + M2-T6 修复的 cwd/env） | ≥2573，skipped 不增 | `.venv/bin/python -m pytest backend/tests/ --collect-only -q \| tail -1` |
| 冷路径 p95 | **待服务启动后测**（后端当前未运行） | <150ms | `.venv/bin/python scripts/quick_perf.py --cold` |
| 查询计划 | `idx_hotspot_region` + **TEMP B-TREE FOR ORDER BY** | 出 `idx_list_visible` 无 TEMP SORT | §12 EXPLAIN 命令 |
| 主 chunk | **1,144,684 B (1.14MB)** `index-DugkVWQY.js` | <300KB | `ls -laS frontend/dist/assets/*.js` |
| DB 体积 | **1.0GB**（vacuum_into 后 0.997GB；质量审计日志占 73% 体积） | <300MB → M2-T6 终态 HOT<80MB | `du -sh backend/hotspot.db` |
| backups/ 体积 | **1.0GB** 单 full | ≤1GB 单盘 + ≤300MB 增量（7 份） | `du -sh backend/backups/` |
| hotspots 行数 | 2952（ingested_at NULL 仅 1 行） | — | sqlite3 COUNT |
| LLM 出口 | 双入口（llm_service + ai_service） | 单出口 ai_hub.py | §12 grep 命令 |

### 基线勘误（与方案原记载的差异，已同步修订方案文档）
1. 迁移编号 061 已被占用（`061_v0.4_chunk_fts_cjk.sql`），新迁移从 **064** 起编。
2. DB 膨胀源是 `quality_check_logs_archive`(265 万行) / `quality_check_logs`(115 万行) /
   `crawler_runs`(16 万) / `raw_items`(13.8 万)，不是 hotspots（仅 2952 行）。
   Task 4 瘦身重心已按此调整。
3. 现状查询已用 `idx_hotspot_region` 但排序走 TEMP B-TREE；测试基线 2547 取代方案的 2288。

### 存量缺陷修复（T0，不属于任何 Task）
- `backend/tests/test_llm_evaluate.py` 收集错误（ImportError: `_parse_eval_json`）：
  该函数 v4.4 后位于 ai_service，测试仍从 llm_service 导入且 mock 错层（AsyncClient vs 同步 Client）。
  已按实际契约重写，测试意图不变，7 用例全过。

## 任务清单

- [x] T0 基线测量 + PROGRESS.md + quick_perf --cold 模式 + 测试基线修复
- [x] M1-Task1 列表查询索引化（迁移 064 + 回填脚本 + hotspot_repo 改造 + EXPLAIN 验证 + 回填幂等）
- [x] M1-Task2 缓存日志采样（每 100 次）+ 真实 warmup 预热 list_cache 主路径
- [x] M1-Task3 Vite manualChunks 拆包（vendor-react + vendor-echarts）+ 5 个非 lazy echarts import 已在 lazy chunk 内
- [ ] **M1 里程碑验收**（p95<150ms / chunk<300KB / 缓存采样）
- [x] M2-Task4 db_diet.py + 表生命周期台账（retention.json + weekly_maintenance 链）
- [x] M2-Task5 契约第一刀：SSE 补 3 事件 + 8 子命令 --json 契约
- [ ] **M2 里程碑验收**（db<300MB / 台账全 job / 契约测试绿 / HOT<80MB / COLD 加密 / 增量链 checksum）
- [ ] M3-Task6 editorial 6 view 接真实 API（todos/review/alert/KL/outbox/briefing）
- [ ] M3-Task7 14 项缺失老功能分批接回（报告/导入/secrets/sync/图谱/heatmap/bid-alert/skills/codegarden 等）
- [ ] M3-Task8 /data 老版式退役倒计时（M5 才物理删除）
- [ ] M3-Task9 /api/workbench/summary API（6 块 + llm-wiki-2.0 outcome 指标；无 UI）
- [ ] **M3 里程碑验收**（无假数据/无占位/每 view 真 API/summary<150ms）
- [x] M3.5-Task10 llm-wiki-2.0 目录 + SCHEMA + HOTSPOT_LLM_WIKI_V2 开关（**2026-08-23 完成，72a8264a**）
- [x] M3.5-Task11 wiki_archiver.py（30 天归档 md + sources + atomic）(**2026-08-23 完成，d5576036**)
- [x] M3.5-Task12 retention_engine.py（Ebbinghaus 衰减 + 周 job）(**2026-08-23 完成，d5576036**)
- [x] M3.5-Task13 graph.json 6 边运行时填入（concept_linker 改造 + CI check）
- [ ] **M3.5 里程碑验收**（归档 100 条对得上 / 衰减曲线 / 双轨零回归）
- [ ] **M4 路线变更**（2026-08-23 用户拍板）：T15-18 废止，改 dsh-SecNews 方案承接。hotspot 侧仅 T18（ai_hub 写回）保留。详见 SPEC §13 头部决议块。
- [x] M5-Task19 ai_hub.py 单 PR 合并双出口（test_llm_service 全绿准入）
- [x] M5-Task20 版本 0.5.0 + CHANGELOG + generate_meta + ARCHITECTURE + 移除旧入口
- [ ] **M5 里程碑验收**（LLM 单出口 grep / 版本一致 / meta check / 唯一路由入口）
- [ ] 全局结束门禁 + 最终 code review

## 2026-08-23 M3.5 落地记录（c3a + c3b）

- **commit 72a8264a**（c3a）：llm-wiki-2.0 5 子目录 + SCHEMA.md + retention.json +
  graph.json（6 边 schema）+ Settings 加 llm_wiki_v2 开关（默认 True, env
  HOTSPOT_LLM_WIKI_V2=false 可关闭）
- **commit d5576036**（c3b）：wiki_archiver.py + retention_engine.py 纯函数
  实现 + knowledge_repo.list_archived_candidates() (LEFT JOIN favorites 排除
  收藏) + 2 个 scheduler job (wiki_archiver 每日 03:50 Shanghai / retention_decay
  Sun 05:30 Shanghai) + 16 单元测试覆盖核心 + 链路
- **架构数**：jobs 43→45, services 86→88（ARCHITECTURE.md 同步）
- **测试基线**：pytest --collect-only = 2639 ≥ 2573 (R9 通过)
- **关键路径**：归档→7天 decay 0.9→access 重置 1.0→再次 decay 整链路 e2e 测试通过
- **SPEC 文字出入**：30 天衰减实际值 0.637 (公式 0.9^(30/7))，SPEC §18 文字
  「30 天≈0.7」是用户口径的「约 70%」近似；测试以公式为准

### M3.5 剩余（M5 之前必做）
- ✅ Task13: graph.json 6 边运行时填入（concept_linker 改造，CI check_retention_decay.py
  + check_graph_schema.py）— **2026-08-23 完成**
- ✅ Task14: 一次性迁移 4152 items + 98 concepts 从 knowledge/ 到 llm-wiki-2.0/
  （M5 验收前做）— **2026-08-23 完成**

## 2026-08-23 M3.5 Task13/14 + M5 落地记录（c4）

### Task13 — graph.json 6 边运行时填入
- `backend/services/concept_linker.py`：新增 `update_graph_from_item/batch`（uses 边
  共现累积, weight + source_observation_count, 幂等, 保留人工/LLM 标注的其余 5 种边）
  + `validate_graph_schema`（6 边类型/weight/节点引用/重复边校验）; `batch_link_items`
  处理完自动累积 graph
- `backend/services/retention_engine.py`：新增 `check_retention_health`（>0.7 占比 ≥80%）
- 新增 `scripts/check_graph_schema.py` + `scripts/check_retention_decay.py`（CI 接入 ci.yml）
- 测试: `backend/tests/test_graph_runtime.py` 18 用例全绿

### Task14 — 一次性迁移 knowledge/ → llm-wiki-2.0/
- 新增 `scripts/migrate_v04_to_llm_wiki.py`（--dry-run 先统计; 幂等覆盖）
- **实际磁盘数: 4149 items + 96 concepts**（spec 预估 4152/98 — 有漂移, 以磁盘为准）
- 关键修复: 存量 items 91.5% 用 `---#` 结尾 (关闭 --- 无换行直接跟 H1), 宽容正则覆盖;
  id 用原始字符串提取 (纯数字/科学计数法 id 被数值化撞车 → 9 条 inf 冲突)
- 迁移后: llm-wiki-2.0/items 4149 + concepts 96 + retention.json 4149 条目 +
  graph.json 96 nodes / 136 edges（check_graph_schema + check_retention_decay 双绿）
- 存量修复: `backend/api/knowledge.py` 移除 `mastered→mastery` 死代码转换
  （原会把 mastery 清零 — to_dict 已返回 mastery）

### M5 Task19 — ai_hub 单出口合并
- `backend/services/ai_hub.py` 合并 llm_service(LLMService 回退链+缓存+用量) +
  ai_service(AIService 凭据/限频/评价/门禁) + evaluate_article + write_score +
  既有 write_item/update_frontmatter; `ai_scores` 写路径唯一入口 `ai_hub.write_score()`
- 调用方改 ai_hub: t1/t3 triggers、llm_status、ai_quality_gate、mcp_agent_tools(score_item
  经 write_score); 测试同步改 (test_llm_service/evaluate/ai_quality_gate/hybrid_ai/
  t1_trigger; t3_trigger 因 mock 共享单例对象无需改)
- **删除旧双入口** `backend/services/llm_service.py` + `ai_service.py`;
  `grep 'from llm_service|from ai_service'` = 0
- docs/llm_config.md 补单出口说明; test_ai_hub.py 新增 TestWriteScore 3 用例

### M5 Task20 — 版本 + 文档
- backend/version.py + frontend/package.json → 0.5.0
- docs/CHANGELOG.md 补 v0.5.0 条目
- docs/ARCHITECTURE.md 更新至 v0.5（services 88→86, 知识库 §四 补 llm-wiki-2.0,
  ai_hub 单出口）; `generate_meta --check` 过 (jobs 45/collectors 14/routers 52/services 86)
- **移除旧入口**: 已删 llm_service.py + ai_service.py（"/data 老版式物理删除" 待 M3
  editorial 接满后按 M5 门禁处理, 未动 — M3 Task6-9 未完成, 删 /data 会丢功能）

### 测试基线
- 全量 collect 2662 ≥ 2573（新增 graph_runtime 18 + ai_hub write_score 3）; ruff 全仓干净

## 2026-08-24 整合 dsh-SecNews 方案定稿

> **方案文档**：`docs/HOTSPOT_SECNEWS_INTEGRATION.md`（完整整合方案）
> **执行任务**：`docs/SECNEWS_INTEGRATION_TASKS.md`（Phase 0-6 可落地任务清单）

### 整合总览
| Phase | 名称 | 人天 | 状态 |
|-------|------|------|------|
| 0 | 基础层：KL 引擎 + wiki FS + 看板壳 | 8 | ✅ 完成 (2592a640) |
| 1 | 管线引擎 + 书签导入 + Pipeline 观测 | 10 | 待开始 |
| 2 | 质量门禁合并 + CVE/ATT&CK + sweep | 5 | 待开始 |
| 3 | 安全看板完整 UI + 三层路由整合 | 8 | 待开始 |
| 4 | AI 研判 + DeepRead + 模型路由 | 6 | 待开始 |
| 5 | 复习集成 + 复利打通 | 4 | 待开始 |
| 6 | 存量迁移 + 清理 | 3 | 待开始 |
| 合计 | | 44 | — |

### Phase 0 任务分解（✅ 2026-08-24 完成，commit 2592a640 + 981eaae6 路由数落账）

> **2026-08-24 验收复核**（本会话实测）：S0-1..S0-11 已全部实现并提交。
> 实测证据：`from backend.kl_pipeline import KLPipeline` / `from backend.wiki_fs import WikiFs` OK；
> kl_pipeline 全部文件 <200 行；`pytest test_kl_pipeline.py test_secnews_dashboard.py` = 32 passed；
> hotspot.db 含 kl_queue / token_ledger / wiki_items_fts 三表（schema 与任务定义一致）；
> 测试基线 collect = 2732 ≥ 2662；前端 /secnews 路由组 + LayerNav 安全看板按钮 +
> DataLayerPage 快捷入口均在位。

- [x] S0-1: 新建 `backend/kl_pipeline/` 包结构（engine.py / queue.py / stages/ / obs/）
- [x] S0-2: 新建 `backend/wiki_fs/` 包结构（contract.py / store.py / migrate.py / linker.py）
- [x] S0-3: 增强 `backend/enrich_v2.py`（CVE/ATT&CK/合规正则 + 到期时间）
- [x] S0-4: 新建 `backend/secnews_dashboard.py`（feed/pipeline/knowledge/stats 聚合）
- [x] S0-5: 新建 `backend/api/kl_pipeline_api.py`（import/url, import/bookmarks, inbox/scan, stats, drain, advance, retry）
- [x] S0-6: 新建 `backend/api/secnews_dashboard_api.py`（feed, pipeline, knowledge, stats）
- [x] S0-7: 前端新建 `frontend/src/components/secnews/` 组件目录
- [x] S0-8: 前端新增 `/secnews` 路由（feed, pipeline, knowledge）
- [x] S0-9: 数据库迁移（kl_queue + token_ledger + wiki_items_fts）
- [x] S0-10: LayerNav 新增「安全看板」入口按钮
- [x] S0-11: DataLayerPage 新增「安全看板」快捷入口卡片

### Phase 1 任务分解
- [x] S1-1: KL 引擎五阶段状态机跑通（raw → refine → link → structure → publish）
  （全链路测试通过 + heartbeat job 每 60s 自动消费 kl_queue, 见 2026-08-24 心跳节）
- [x] S1-2: wiki_fs store.py 读写契约 + 块序列解析
- [ ] S1-3: 书签 HTML 导入（Netscape 解析 + 存活三态检测）
  （HTML 导入已可用; 存活三态检测未做）
- [ ] S1-4: Pipeline 观测台 UI（漏斗 + 队列卡片 + 死信表 + token 台账）
- [ ] S1-5: inbox 扫描入口 + quarantine 隔离区
- [x] S1-6: refine 轻 AI 接入（flash 档，topic/type/tags）
  （AIHubLLMClient 桥接 ai_hub; 无 provider 时 generate 返回 "" 自动降级摘要）

### Phase 2 任务分解
- [ ] S2-1: 质量门禁 13+ 道 Gate 合并（Hotspot 13 + dsh 8）
- [x] S2-2: CVE/ATT&CK/合规正则抽取（T\d{4} + CVE-YYYY-NNNN + 等保/关基）
- [x] S2-3: 每日 sweep 兜底运行（滞留条目自动入队）
  （实现为 heartbeat 每 10 拍 = 10 分钟 sweep, 强于每日兜底）
- [ ] S2-4: concept-linker Python 移植（FTS 共现 → 权重边）

### Phase 3 任务分解
- [ ] S3-1: 报纸风 Feed 完整 UI（头版头条 + 分类标签 + 网格卡片）
- [ ] S3-2: Pipeline 观测台完整 UI（五阶段漏斗 + 队列 + 死信 + token 台账）
- [ ] S3-3: wiki 知识浏览 UI（items + concepts + inbox 扫描）
- [ ] S3-4: 安全看板设置页（采集源 + 模型档位 + 管线参数）
- [ ] S3-5: LayerNav 完整四入口（资料层 / 判断层 / 行动层 / 安全看板）

### Phase 4 任务分解
- [ ] S4-1: 模型分层路由（flash/big/embed 三档配置）
- [ ] S4-2: DeepRead 深度分析面板（四节报告）
- [ ] S4-3: CVE 热力图 + ATT&CK 技术映射可视化
- [ ] S4-4: 合规矩阵面板

### Phase 5 任务分解
- [ ] S5-1: SM-2 复习与 wiki pipeline 打通
- [ ] S5-2: 复习结果单向投影回 wiki frontmatter
- [ ] S5-3: 08:00 日报自动生成
- [ ] S5-4: 到期复习卡自动出现

### Phase 6 任务分解
- [ ] S6-1: 存量 4149 items + 96 concepts 迁移脚本
- [ ] S6-2: graph.json 合并去重
- [ ] S6-3: 迁移验证 + FTS5 可检索确认
- [ ] S6-4: dsh-SecNews 仓库归档（不删除，保留备份）

## 2026-08-24 产品三层架构裁决 + wiki 单根落地

> **用户裁决原文**：「我的目标是将DeepSeek Harness作为大脑，pi作为执行agent，
> hotspot作为平台看板，开发一个安全从业者的生产级别的安全从业者AI助手」
> 「补齐llm-wiki-2.0作为知识库关键存档的部分，数据库作为事件管理」

### 裁决一：产品三层架构（hotspot 保持活跃）

| 层 | 角色 | 落点 |
|----|------|------|
| DeepSeek Harness | 大脑（认知层） | HTTP bridge localhost:3210, fallback 直连 LLM（v0.6 方案 §3） |
| pi | 执行 agent | `backend/config/agent_runner_schema.py` runner 注册表（agents.yaml 待建） |
| hotspot | 平台看板 | 本仓库, SECNEWS_INTEGRATION_TASKS Phase 0-6 继续推进 |

**连锁裁决**：Phase 7 退役的破坏性步骤（D+2 停 :8000 / D+3 git mv 归档）**冻结不执行**；
`export_for_dsh.py` 等工具保留为参考资产。AGENTS.md 顶部「已退役预告」banner 失效，
以本节为准。

### 裁决二：llm-wiki-2.0 = 知识唯一存档根（wiki-first）

- `llm-wiki-2.0/*.md` = 知识真源；SQLite = 运营层 + 事件管理
  （`wiki_events` 表为两世界唯一桥梁, v0.5 §18 存储哲学反转的最终收口）
- 新增单一根解析器 `backend/wiki_fs/root.py::resolve_wiki_root()`
  （env `HOTSPOT_WIKI_ROOT` 可覆盖）; kl_pipeline API / secnews dashboard API 全部切换,
  旧 `knowledge/` 根不再被读写
- 字段对齐：代码侧 `kl_stage` → SCHEMA.md 契约字段 `lifecycle`（17 处写入/读取点;
  `contract.get_lifecycle()` 兼容读历史 kl_stage）
- 事件留痕：engine.drain_due 成功转换 → kind=`kl_transition`, 阶段失败 → kind=`kl_error`,
  导入入口 → kind=`ingest_url` / `ingest_bookmarks`（agent=kl_pipeline / api:kl_import）；
  留痕失败只 warning 不阻塞管线
- 附带修复：SecNewsDashboard 此前构造时未注入 wiki_fs 导致知识统计恒空, 已接单根 WikiFs

### 验证证据（本会话实测）

- `pytest test_kl_pipeline.py test_secnews_dashboard.py test_wiki_tools.py` = **54 passed**
  （含新增 6 测: 根解析×2 / lifecycle 契约×1 / 全链路 raw→publish / 事件留痕×2）
- 全量回归 `pytest backend/tests/` = **2760 passed, 4 skipped**（基线 2732 之上零失败）;
  touched 文件 ruff 干净（linker/store 各余 1 处 HEAD 历史遗留, 非本次引入）;
  `generate_meta.py --check` OK (jobs 45 / routers 54 / services 86)
- 未竟事项（后续任务）：调度器 heartbeat job 驱动 drain_due/sweep 自动消费；
  S1-6 refine 接 ai_hub LLM（当前 llm_client=None 走降级摘要）

## 2026-08-24 心跳闭环 + S1-6 LLM 接入 + pi runner 注册

> 承接上节两项未竟事项 + 三层架构 pi 执行层落位（一任务一提交拆 3 个 commit）。

### kl_queue 心跳消费 (S1-1/S2-3 收口)

- 新增 `kl_pipeline_heartbeat_job`（60s）：`drain_due(limit=50)` 常规消化；
  每 10 拍（10 分钟）附带 `sweep()` 兜底滞留条目 —— 强于原计划的每日 sweep
- 注册于 `scheduler.py` `_JOB_EXT_MAP` → `secnews` 扩展域（feature gate 可关）;
  drain/sweep 为同步 DB+FS 操作, `asyncio.to_thread` 包装; 失败仅 log.error
- 注意：与 v1.8 Phase 10 的 `kl_trigger_t1..t4_job`（services/triggers/*,
  旧 knowledge_items 状态机）是两套系统, 本 job 驱动 backend/kl_pipeline 的 kl_queue
- 附带修复：jobs.py 预存 F821 —— wiki_archiver_job / retention_decay_job 使用
  未导入的 `timezone`（ruff 检出）, 一旦运行即 NameError; 补 `from datetime import timezone`

### S1-6: refine 接 ai_hub LLM

- 新增 `backend/kl_pipeline/llm_adapter.py::AIHubLLMClient`：
  stage 期望同步 `chat()` ↔ ai_hub `llm_service.generate()`（async）桥接;
  工作线程无循环时 `asyncio.run` 直跑, API 循环内用独立单线程池避免嵌套
- refine prompt 扩展 topic/type 两字段（severity/tags/summary 沿用）;
  无 provider / 全失败时 generate 返回 "" → JSON 解析失败 → 自动降级正文截断摘要
- 新增 `backend/kl_pipeline/runtime.py` 生产装配单一出口（依赖方向:
  scheduler/jobs → kl_pipeline.runtime → wiki_fs+ai_hub, 调度器不 import backend.api）;
  API 层 `_get_wiki_fs/_get_pipeline/_get_dashboard` 全部切换至 runtime 单例

### pi 执行 agent 注册 (三层架构执行层)

- 仓库根 `config/agents.yaml` 新增 `pi:` 条目（command=["pi"], protocol=acp,
  task_types=[execute], timeout=600）; CLI 未装时 §19.4 回退 default_agent
- `route("execute") == "pi"` 路由断言入 test_agent_runner_schema.py

### 验证证据（本会话实测）

- 定向套件: test_secnews_p1_runtime(新,10) + test_agent_runner_schema +
  test_kl_pipeline = **43 passed**; gates/scheduler×2/dashboard = **92 passed**;
  test_wiki_tools = **15 passed**
- 全量回归 `pytest backend/tests/` = **2822 passed, 4 skipped** 零失败;
  touched 文件 ruff 干净（jobs.py 余 3 处 HEAD 历史遗留: RUF006/ASYNC221/RUF022）
- `generate_meta.py --check` OK (**jobs 46** ← 心跳 job 入账 / routers 54 / services 86)


## 2026-08-23 M4 路线决策（已被 2026-08-23 产品身份裁决取代）

> ⚠️ 本节已被下方「产品身份裁决」取代。原文保留作为决策链审计。
> 原决策：以 dsh-SecNews 方案为准，hotspot 不做 acp 子进程宿主，后续 M4 在外部仓库推进。
> 新裁决：hotspot 就是产品主体，dsh-SecNews PRD 设计回灌 hotspot。

## 2026-08-23 产品身份裁决（取代 M4 路线决策）

> **用户拍板**：hotspot 的产品身份 = 「集成 DeepSeek Harness 的安全从业者 AI 工作台」。

### 三条第一性原理
1. **工作台 ≠ 聚合器**：用户来工作台是「做事」，不是「看新闻」。采集是管道，不是产品。
2. **安全从业者 = 判断密集型**：核心价值是帮用户从碎片信息中形成判断，不是推送更多资讯。
3. **集成 dsh ≠ 依赖 dsh**：hotspot 独立可运行，dsh 增强推理能力。dsh 挂了 hotspot LLM 直连兜底。

### 四项结构裁决
| # | 裁决 | 含义 |
|---|------|------|
| R1 | dsh-SecNews PRD 回灌 hotspot | SECNEWS-v5-PRD 的 M1-M7 映射到 hotspot 代码结构；dsh-SecNews 仓库保留为设计参考 |
| R2 | dsh 进程间通信 | hotspot 与 deepseek-harness 通过 HTTP/WebSocket 通信，松耦合；不用 ACP 子进程 |
| R3 | ai_hub 拆三层 | llm/(gateway+scoring+model_router) + knowledge/(wiki_io+wiki_query) + dsh/(bridge+task_router+session) |
| R4 | editorial → 工作台 UI | 5 视图：Briefing/Pipeline/Knowledge/Analyze/Settings（取代 editorial 6 view + /data 三层） |

### 对已完成工作的影响
- **M1/M2/M3.5/M5 已完成工作全部保留**：性能优化、DB 瘦身、llm-wiki-2.0 底座、ai_hub 单出口——这些都是工作台的基础设施，方向不变。
- **M3 editorial 接满废止**：不再按「editorial 6 view 接老功能」执行；改为按工作台 5 视图重新设计。
- **M4 路线反转**：不再在外部仓库推进；dsh 集成回到 hotspot 代码库。
- **dsh-SecNews/secnews/ 代码不搬迁**：作为设计参考，不合并到 hotspot。

### 新重构方案骨架（已细化为 `docs/v0.6_workstation_plan.md`）

| Phase | 内容 | 对应旧版 |
|-------|------|----------|
| Phase 1 | 清场：死代码/F821/jobs拆分/M1M2验收 | 新增 |
| Phase 2 | ai_hub 解耦 + dsh 桥接层 | 取代 M4 |
| Phase 3 | KL 管线落地 (wiki-first + 模型分层) | 取代 M3+M3.5 剩余 |
| Phase 4 | 工作台 UI 重建 (5 视图) | 取代 M3 editorial |
| Phase 5 | 执行层 (SM-2/简报/MCP/CLI) | 新增 |

## 开发计划（2026-08-21 制定，依 SPEC §1 细化）

执行顺序与依赖：M1 → M2 → M3 → M3.5 → M4 → M5。
M1 是前置门槛（性能基线）；M2 契约第一刀是 M4 的基础；M3.editorial 接满是"唯一前端"前提；
M3.5 数据底座与 M4 dsh 认知层分域，M3.5 可先行（不影响 dsh 接入）。

### M1 性能三任务（P0，前置）
- **Task1（✅ 2026-08-21 收尾）**：
  - [x] `064_list_query_optimization.sql`（is_hidden 列 + idx_list_visible 部分索引）
  - [x] `backend/scripts/backfill_ingested_at.py`（回填 + is_hidden 推导，分批幂等；重跑=0 命中）
  - [x] `hotspot_repo.py.query()`：全面改为 `ingested_at` 直接比较 + `is_hidden = 0`，
    消除 COALESCE/LIKE/TEMP B-TREE（实测 EXPLAIN 命中 `idx_list_visible`，老式 query 走 SCAN + TEMP B-TREE）。
  - [x] 验收：EXPLAIN 通过；is_hidden=2844 / hidden=108（合计 2952 行）；回填幂等 0 命中。
- **Task2（✅ 2026-08-21 收尾）**：
  - [x] `cache.py` 加 `cache_hit` 每 100 次采样日志（`__getitem__` 命中计数 % 100 == 0），
    实测 102 次连续命中只产出 ≤1 条 cache_hit 日志。
  - [x] `warmup()` 改真实查询：调 `HotspotRepository.query()` 跑 list_cache 主路径
    (all/ai/security 7d)，实测 `{"warmed": 9, "real_warmed": 3}`。
  - [x] 验收：27 个 cache 测试全绿；warmup 后 list:all:7d 命中返回 50 items。
- **Task3（✅ 2026-08-21 收尾）**：
  - [x] `frontend/vite.config.ts` manualChunks 已配 `vendor-react` + `vendor-echarts`。
  - [x] 实测：主 chunk `index-BrhdIP6a.js` = **25,947 B (25.9 KB)** << 300KB 目标。
  - [x] `vendor-echarts-DFlXbToH.js` = 1.14 MB（按需懒加载）。
  - [x] 5 处非 lazy `from 'echarts-for-react'` (MasteryGauge/KnowledgeGraph/TrendChart/
    JudgeTrendsPage/KnowledgeCompoundingDashboard) 全部位于 React.lazy chunk 内，
    DataLayerPage/JudgeLayerPage/EditorialView 都是 lazy 入口，echarts 不进主 chunk。

### M2 DB 瘦身 + 契约第一刀（P0）
- **Task4（✅ 2026-08-21 收尾）**：
  - [x] `scripts/retention.json`：6 张表 (quality_check_logs / crawler_runs /
    raw_items / hotspots / sync_history / quality_check_logs_archive)
    每张声明 retention_days + action + scheduled_in。
  - [x] `scripts/db_diet.py`：实现 truncate / archive_db_table / archive_jsonl
    三种 action，复用 maintenance_service.archive_quality_logs（DRY）；
    支持 `--backup` 演练 + `--vacuum-into` 收尾；统一 CLI 契约 `--json`。
  - [x] `backend/scheduler/jobs.py`：weekly_maintenance_job 末尾追加
    `db_diet_job` 子进程调用；新加 `@instrument_job` 装饰器 + `job_done_event()`
    fire-and-forget helper (供 M2-Task5 job_done SSE 复用)。
  - [x] `backend/tests/test_db_diet.py`：9 用例覆盖 retention.json 结构、
    CLI envelope、dry_run 不动库、execute 三种 action、--table 过滤、
    --backup 副本机制；全部 9/9 通过。
- **Task5（✅ 2026-08-21 收尾）**：
  - [x] SSE 补 3 事件：extract_done（api/extract.py）、job_done
    （scheduler/jobs.py instrument_job 装饰器）、task_done
    （compiler.py _execute_compile_task 末尾）。payload 形状对齐 SPEC §6.2。
  - [x] `scripts/cli_contract.py`：统一 CLI 契约包装 {ok, code, duration_ms, data}；
    8 个子命令注册表（db_diet + manual_collect 已实现，6 个 v0.4 由
    jobs/HTTP 触发 → `not_yet_implemented` 状态 ok=true 不破契约）。
  - [x] `scripts/manual_collect.py`：加 `--json` 走 SPEC §6.1 契约。
  - [x] `backend/tests/test_cli_contract.py`：7 用例全过（注册表完整性、
    envelope 形状、子进程 emit_envelope 闭环）。
  - [x] `backend/tests/test_sse_events_v05.py`：8 用例全过（extract_done /
    job_done / task_done payload 形状、queue 隔离、instrument_job 装饰器存在）。
- **Task6 - M2-T6 全站存储设计（✅ 2026-08-22 全部完成，含 T6.1-T6.10 实施）**：
  - [x] **清理 backups**：老 1GB×5 备份残留已删，`backend/backups/` 只剩 1 份当前 full + 1 knowledge.zip
  - [x] **改增量备份**：`backend/services/backup_service.py` 加 `backup_incremental()`
    （WAL 帧解析: magic + page_size + checkpoint_seq → `incremental/wal-{ts}-{seq}.bin`）；
    `BACKUP_RETENTION=1`、`MAX_INCREMENTAL_PAGES=8192`、`restore_from_incremental_chain()`
    `daily_db_backup_job` 04:30 调增量；`weekly_maintenance_job` 周日调 full 轮转；
    @instrument_job 触发 SSE `job_done` 事件。
  - [x] **修 backup_database 关键 bug**：
    1) Python sqlite3 默认 deferred 必须 `dst_conn.commit()` 关闭前落盘, 否则 rollback
    2) 保留策略按 mtime 排序 (不是字典序) → 避免 diet-vacuum 残留覆盖新 backup
    3) 排除 `hotspot-diet-*` 前缀, 不让 db_diet 临时文件污染 retention glob
    4) 配对删 .db + .knowledge.zip
  - [x] **老数据 db 清理落地**：`db_diet --execute --backup /tmp/x.bak --vacuum-into`
    实测: 6/6 表 succeeded, rows_deleted=0 (实测当前 DB 数据全部在过去 30 天内, retention 窗口未到),
    但 VACUUM INTO 把主库 1.07GB → 0.997GB (回收 28MB 碎片), 部分缓解膨胀。
  - [x] **数据库设计方案 + 后端功能映射文档**：`docs/v0.5_storage_design.md` (678 行)
    - §1 数据温度模型 (HOT/WARM/COLD/FROZEN)
    - §2 全 91 张表台账 + 物理分离方案
    - §3 增量备份 (已实现 + 落地)
    - §4 老数据清理 (现状 + 目标)
    - §5 分类存储迁移路径 (migrate_temp_layers.py 设计)
    - §6 后端功能 ↔ 表 ↔ 物理层 ↔ 备份 完整映射 (16 routers + 22 services + 13 scheduler jobs + 4 collector 类别)
    - §7 安全稳定性 (Fernet 加密 / PRAGMA integrity / RTO/RPO / CI 校验)
    - §8 性能容量对比
    - §9 M2-T6 实施 Task 列表 (T6.1-T6.10, ~22.5h)
    - §10-12 验收命令 + 反向验证 + 与 v0.5 主 SPEC 关系
  - [x] **v0.5 主 SPEC 追加 §10.5**：M2-T6 任务条目 (T6.1 - T6.10)、与 T4/5 关系、表-温度层速查、增量备份现状、加密方案、验收命令
  - [x] **§1 Goal / §7 里程碑 / §9 文件变更映射 / §4 现状基线** 同步更新 (M2-T6 退出门禁 + 文件清单)
  - [x] **T6.1**: `scripts/retention.json` 扩到 91 张表 (HOT/WARM/COLD/FROZEN 全覆盖)
  - [x] **T6.2**: `db_diet --execute --vacuum-into` 跑全表
  - [x] **T6.3**: `backend/repository/db.py` get_connection 自动 ATTACH warm/cold (+cold Fernet 透明解密)
  - [x] **T6.4**: `scripts/migrate_temp_layers.py` 跨库迁移 — 实测 HOT 63 表 / WARM 40 表 / 0 重叠;
        WARM 承接 crawler_runs 162K / quality_check_logs 1.21M / raw_items 138K 等 ~157 万行;
        迁移前 safety 备份, 迁移后主库 1GB→~700MB
  - [x] **T6.5**: 全 repo 生产代码 42 处 `INSERT INTO x` → `INSERT INTO warm.x` (27 文件,
        services/api/collectors/repository; tests 与 migrations 不动);
        maintenance_service 加 `_alias_for()` warm/main fallback
  - [x] **T6.6**: COLD db Fernet 加密 `scripts/cold_db_crypto.py`
        (PBKDF2 600k + salt 前置 envelope); db.py 检测 `.enc` + cold_db_key 自动解密 tempfile ATTACH
  - [x] **T6.7**: `scripts/check_backup_chain.py` CI 校验 (full quick_check / 增量链数 /
        sha256 校验 / knowledge.zip; FTS vtable 容错) — 7/7 checks passed
  - [x] **T6.8**: WAL 增量帧 sha256 sidecar (.sha256 文件旁车)
  - [x] **T6.9**: remote backup hook (`HOTSPOT_REMOTE_BACKUP=webdav`, env 默认关)
  - [x] **T6.10**: 更新 `docs/ARCHITECTURE.md` §六点五 全站数据视图 (物理分离表格 +
        写入路径约定 + 备份链结构 + COLD 加密 + 体积预估)
  - [x] **测试修复收尾** (test_db_diet.py 9/9 绿):
        1) `_alias_for()` 改用 `PRAGMA warm.table_info()` 行数判断 (原 `PRAGMA table_info("warm.x")`
           语法无效永远返回空 → qcl 归档误判 no such table)
        2) db_diet 主连接每表一 commit (qcl archive_db_table 内部开第二连接,
           未提交事务导致 database is locked)
        3) retention.json hotspots 恢复 archive_jsonl/180d (被误重置为 keep/null);
           quality_check_logs_archive 改按 archived_at 计 90 天 (原按 checked_at 会立刻删掉刚归档的老行)
        4) test_retention_json_referenced_tables_exist 扫描 main+warm+cold 三 schema
        5) db_diet safety backup 写源库同目录 (mini_db 测试不再污染共享 backups/)
        6) 重建备份链: 删除损坏的旧 full backup, force_full 重建后 check_backup_chain 7/7 过
- **全量测试收尾 (✅ 2026-08-22, 209 失败 → 0)**:
  - [x] **方案 A 回滚 T6.5 前缀写**: 42 处 `INSERT INTO warm.x` 恢复裸表名
        (SQLite 未限定名称按 main→ATTACH 顺序解析, 写入自动落 warm 库;
        测试/迁移不再因前缀与解析顺序错位而 404)
  - [x] **conftest `_isolate_temp_dbs`**: warm/cold/cold_db_key 重定向 tmp_path
        (测试不再 ATTACH 生产 warm.db)
  - [x] **mastered → mastery 重命名**: 6 个测试文件同步
  - [x] **v4.4 AI 集中层**: test_ai_quality_gate 改 mock AIService.gate_detect;
        test_observability 缓存命中按 100:1 采样节奏重写
  - [x] **cursor 微秒精度 bug** (`backend/services/hotspot_service.py` `_to_repo_cursor`):
        `int(timestamp())` 截断微秒 → 同秒多条记录翻页丢行; 改 `f"{ts:.6f}_id"`
        与 HotspotRepository._make_cursor 同格式 (repo._parse_cursor 兼容两种)
  - [x] **crawl4ai load_dotenv 测试污染** (test_config::test_default_values
        单跑过/全量挂): `crawl4ai/config.py` 模块顶层 `load_dotenv()` 在
        import 时把项目根 .env 的 HOTSPOT_HOST=0.0.0.0 写入 os.environ 永不还原;
        test_catchup_api 真实 lifespan 触发 collector 链 import crawl4ai 后
        污染同进程后续测试。修复: conftest 新增 autouse `_protect_hotspot_env`
        (HOTSPOT_ 前缀变量快照/还原)。关键: 快照必须放 conftest **模块级**
        而非 fixture 内 — 测试模块 collection 阶段的顶层 import
        (test_crawl4ai_client → crawl4ai) 就已触发 load_dotenv,
        fixture 运行时快照已被毒化

### M3 统一前端 editorial 接满（P0）

### 2026-08-22 存储哲学反转 + dsh 多智能体编排（§18/§19 增补）

- **M3.5 §18.4 第一批落地（✅ 2026-08-22）**:
  - [x] `065_wiki_events.sql`: wiki ↔ DB 事件对应表（kind/wiki_path/db_table/db_row_id/agent/payload + 3 索引）
  - [x] `backend/repository/wiki_event_repo.py`: log / trace_by_wiki_path / trace_by_db_ref / stats
  - [x] `backend/api/wiki_tools.py` `/api/wiki/*`: search(FTS5 trigram CJK + LIKE 回退) /
        read(P4-9 同款路径穿越防护) / graph(concepts/graph.json BFS k=1..n) /
        trace(wiki_events 反查)；注册进 api/__init__.py
  - [x] MCP 注册: mcp_config 4 个 operation_id + mcp_types 4 个 InputModel（category=read）
        → 工具总数 9→13 (9 读 + 4 写)
  - [x] `backend/tests/test_wiki_tools.py` 11 用例全绿；test_mcp_server/sse/phase7_e2e
        计数断言同步 13
- **warm 库 FTS5 虚表修复（✅ 2026-08-22, T6.4 盲区暴露）**:
  - 症状: `test_retention_json_referenced_tables_exist` 失败 — retention.json 引用的
    `knowledge_chunks_fts` 在生产 warm 库不存在
  - 根因: T6.4 migrate_temp_layers.py 只搬普通表，**FTS5 虚表定义无法被复制**，
    迁移后 warm 库只剩 8 张孤儿影子表 (_data/_idx/_docsize/_config × 2)，虚表 + 6 触发器全丢；
    后果是 wiki_search/knowledge_chunks_api FTS 静默降级、chunk 写入不同步索引
  - 修复: DROP 孤儿影子表 → 按 054/061 原始 DDL CREATE VIRTUAL TABLE ×2 +
    触发器 ×6 → 官方 `rebuild` 命令回灌索引
  - 验证: chunks=fts=cjk=507 行对齐；trigram 表 MATCH '"业务系统"' 命中、unicode61 MATCH 'security' 命中；
    test_db_diet 9/9 绿
  - 教训: **后续跨库迁移必须枚举 sqlite_master type='table' 之外还要处理 vtab**
    （虚表需原库 DDL + 新库 rebuild），migrate_temp_layers.py 待补此能力
- **臃肿根因实测**: 业务数据 <20MB（hotspots 仅 4891 行），1GB+ 全是遥测
  （qcl_archive 265 万行等）+ 1.27GB 旧备份残留 → M2-T6 只解决"放哪"没解决"留多少"
- **立即瘦身**（已执行）: 删 bak-dedup-20260820 残留(-1.27GB)；
  qcl_archive/crawler_runs/raw_items >7d 清理 + VACUUM(删 83 万+25 万行)
  → 主库 1.04GB→330MB、warm 320MB→241MB
- **v0.5 SPEC §18 存储哲学反转**（SAG 模式，RAG→llm-wiki-2.0）:
  - llm-wiki-2.0 = 知识真源；SQLite 降级为运营层（遥测滚动删除/只读索引）
  - 新增 wiki_events 事件对应表 = 两世界唯一桥梁
  - 三强约束: 知识写入唯一路径 ai_hub / retention.json 补 source 字段 /
    DB 体积红线 <500MB 进 CI
  - 新增 wiki_* MCP 工具族 (search/read/graph/write/db_trace)
- **v0.5 SPEC §19 dsh 多智能体编排**: dsh 作为 agent 网关统一调度
  claude code / codex CLI；T15 拆 T15a(dsh 主进程)+T15b(CLI runner 注册)；
  路由策略表 + 沙箱边界(codegarden/<project>/ 内) + 降级回退 builtin
- **待办固化**: 7 天遥测窗口改 scheduler job；retention.json 加 source 字段
- **Task6**：6 view 接真 API——todos→`/api/todos`、review→`/api/reviews`、
  alert→`/api/alerts/v2`、KL 复利→知识 API、outbox→后端 outbox、briefing→digest API。
  砍 EditorialView 内硬编码 state（todos/KL 假数据）与 toast 占位（review/alert）。
- **Task7**：14 项缺失功能按 4 批接回（参考 `docs/FRONTEND_BACKEND_ALIGNMENT_AUDIT.md`）：
  批1 报告/导入/history; 批2 secrets/sync; 批3 图谱/compile/imported/heatmap; 批4 bid-alert/skills/codegarden/rejection。
  每批独立验收（页面有真数据）。
- **Task8**：`/data` 老版式退役倒计时：路由保留、入口加"即将移除"提示（M5 物理删除）。
- **Task9**：`backend/api/workbench.py` + `workbench_service.py`：
  `GET /api/workbench/summary`（6 块聚合，每块 try/except 隔离返 null；outcome 用
  crystallized_this_week/superseded_this_week/retention_health/confidence_avg_7d）。**无 UI**。
  - 验收：summary<150ms；6 块全真；Today card 并入 editorial front（后续 M4 前可白板）。

### M3.5 llm-wiki-2.0 数据底座（P1，可与 M3 并行）
- **Task10**：`llm-wiki-2.0/{items,sources,concepts,digest,schema}/` + `retention.json` + `graph.json`；
  SCHEMA.md 定义全部 frontmatter；v0.4 `knowledge/_SCHEMA.md` 标 deprecated；
  Settings 加 `HOTSPOT_LLM_WIKI_V2=false`（Pydantic+env）。
- **Task11**：`wiki_archiver.py`：30 天前非收藏 → items/{hash}.md（完整 frontmatter）+
  sources/{hash}.md（抓取元数据+quality_gate 决策链）；atomic 写；初始 retention 1.0。
- **Task12**：`retention_engine.py`：Ebbinghaus `current *= 0.9^(days/7)`；access reset；
  周 job（weekly_maintenance 链）扫全部；<0.3 标 stale（不删）；`scripts/check_retention_decay.py` 进 CI。
- **Task13**：graph.json 6 种边；t_confidence 写 confidence（默认 0.5）；t_supersede 建 supersession 链。
- **Task14**：M5 一次性迁移：4152 items + 98 concepts `knowledge/`→`llm-wiki-2.0/`（先快照校验）。
  - 验收：归档 100 条→md 数对；retention 7 天 1.0→0.9、30 天≈0.7；v0.4 双轨零回归。

### M4 dsh 认知层（P1）
- **Task15**：`backend/api/agent_api.py`：`/api/agent/session|send|events` 三端点（token 鉴权）。
- **Task16**：`backend/services/agent_bridge.py`：acp 子进程 spawn/保活/重启/心跳；
  `HOTSPOT_AGENT_BACKEND=off|acp`；dsh 离线→AI view 降级、其余不动。
- **Task17**：editorial 第 7 view `AI`：编辑风对话组件 + `/api/agent/*` SSE 流。
- **Task18**：记忆单源裁决：agent 产物（提炼/建议/flag）经 ai_hub 写回 llm-wiki-2.0+SQLite。
  - 验收：意图→工具→结果闭环；对话调 hotspot MCP 工具；dsh 崩溃不 500；grep 单契约。

### M5 ai_hub 合并 + 发版（P1）
- **Task19**：`backend/services/ai_hub.py` 单 PR 合并 llm_service+ai_service（不搞 strangler）；
  mcp_agent_tools 4 tool 经 hub 审计入口；grep 双出口 = 0；ai_scores 写路径仅 hub。
- **Task20**：version 0.5.0（后端/frontend/README/CHANGELOG）；generate_meta --check；
  ARCHITECTURE.md 更新；移除 `/data` 与 dsh web(:3080) 生产入口。

### 全程门禁（每里程碑执行）
- 测试基线 ≥2547 / skipped 不增 / 前端 tsc+vitest(292)+build 全绿 / ruff 干净 / 一任务一提交。

## 里程碑验收记录

（每里程碑结束在此追加：命令 + 输出摘要）

### T0 提交记录
- `fix(test): repair llm_evaluate baseline imports/mock layer`（基线修复）
- `feat(perf): quick_perf --cold 双轨冷路径模式 + PROGRESS.md 基线档案`

### 2026-08-23 未提交工作分类落账（6 commit 拆分）

> 背景：M1/M2 各任务实际已完成但长期未提交，工作树累积 ~133 文件。按「一任务一提交」
> 原则拆为 6 个逻辑提交；提交前跑新增测试 74 用例全绿 + py_compile 关键模块通过。

- `chore(v05-m1)` e9d053a3: conftest env 防污染 / vite manualChunks / 观测采样测试 / .gitignore 运行时产物
- `feat(v05-m2-t5)` af464a32: SSE 三事件 + instrument_job + CLI 契约 8 子命令
- `feat(v05-m2-t6)` 63bd90d4: HOT/WARM/COLD/FROZEN 分层存储 + WAL 增量备份链 + COLD Fernet 加密
- `feat(v05-m2)` 04a69367: wiki_events(065) + wiki_tools API + MCP 工具面扩展
- `feat(v05-§18.2)` a4283c36: ai_hub 写回唯一门面 + agent_runner_schema(T15b 前置) + agents.yaml
- `docs/chore` (本条): PROGRESS 落账 + ARCHITECTURE meta 同步 + knowledge 快照

### M4 路线决策（2026-08-23，已被产品身份裁决取代）

> 原文保留作为决策链审计。详见上方「产品身份裁决」一节。
> - 原决策：M4 以 dsh-SecNews 方案为准，后续在外部仓库推进。
> - 新裁决：hotspot 就是产品主体，dsh-SecNews PRD 回灌 hotspot，dsh 进程间通信。

## 2026-08-24 Phase 7 数据迁移 + 旧系统退役 (c5)

> **背景**：hotspot v0.5.0 + dsh-SecNews 方案定稿后，进入 Phase 7 数据迁移 + 旧系统退役阶段。
> workspace 约束下, hotspot 端能推进的是 (a) Python 旁路导出器 + (b) 退役文档;
> dsh 端的 `migrate-from-hotspot.ts` (344 行, 已在 dsh-SecNews 仓库内) 由 dsh 侧开发。

### Phase 7a — hotspot.db → JSON 旁路导出器

- **commit b1cd80de**: `feat(scripts): export_for_dsh.py + test (Phase 7 数据迁移旁路)`
- **scripts/export_for_dsh.py** (375 行):
  - 8 张核心表: hotspots/favorites/todos/sm2_reviews/annotations/hotspot_tags/knowledge_concepts/knowledge_graph
  - 输出契约: manifest.json (schema_version + counts + contract) + per-table *.json (CREATE TABLE DDL + columns + rows)
  - 字段归一化: datetime → ISO8601; BLOB → {__b64__: base64}; JSON-encoded 字符串 → 原生 list/object; None → null
  - wiki_files/: cp -r knowledge/{items,concepts,inbox,quarantine}/
  - 37 张 SKIP_TABLES 含 rationale (schema_version / encryption_keys / cg_* / llm_* / FTS5 虚表等)
  - 支持 --tables / --no-wiki / --dry-run / --out / --db / --wiki-src 五个 flag
- **backend/tests/test_export_for_dsh.py** (135 行, 8 cases 全绿):
  - manifest schema_version=1 + counts + contract
  - 每张表 schema/columns/rows 形状
  - JSON-encoded 字段解析
  - row_count == SELECT COUNT(*)
  - skip_tables_rationale ≥ 10 项
- **实测**: 8 表 8902 行 + 4245 wiki 文件 (4149 items + 96 concepts)
- **.gitignore**: 新增 `data/export/` (运行时产物不入版本库)

### Phase 7b — 退役清单文档 (当前)

- **新增 docs/HOTSPOT_RETIREMENT.md** (202 行):
  - 退役时间线 (D+0 至 D+4)
  - hotspot 端验收命令 (行数对账 / wiki 文件数对账)
  - hotspot 端退役步骤 (6 步: 停 :8000 / 跑 export / git mv / 标 AGENTS / git tag)
  - 代码迁移清单 (run.py / check_render.py / backend/main.py 等)
  - 应急回滚 (30 天观察期)
  - 不迁移表 + 文档同步清单 + 验收 checklist
- **AGENTS.md 同步**:
  - 顶部加 RETIRED banner (Phase 7 进行中)
  - Development Commands 加退役警告
  - 指向 HOTSPOT_RETIREMENT.md

### Phase 7 后续 (待 dsh 端推进)

- dsh 端 secnews.db 行数对账 == hotspot.db 8 表 8902 行
- dsh 端 wiki 文件数对账 == 4245
- dsh 端 React SPA `web/` 全功能冒烟
- hotspot 端 :8000 进程停止 / git mv backend → hotspot-archived / git tag v0.5.0-retired

### Phase 7c — 一键退役脚本 + baseline 快照 (当前)

> 7b 文档就绪后, 补充两个**可控触发**的工具, 让 hotspot 端在 dsh 验收通过后,
> 一条命令完成所有破坏性动作, 保留 dry-run 默认 + safety checks + 30 天回滚指引。

- **scripts/snapshot_for_retirement.py** (NEW, 305 行):
  - 8 张核心表 + 4 个 wiki 子目录行数锁定 → `data/retirement_baseline.json` (gitignored)
  - 含 `schema_version=1` + `dsh_verify_hint` (node:sqlite 对账命令模板)
  - 三个 mode: 默认写盘 / `--dry-run` / `--verify` (与 baseline 比对)
  - 退出码: 0 一致, 1 漂移, 2 baseline 缺失
- **backend/tests/test_snapshot_for_retirement.py** (NEW, 13 cases 全绿):
  - schema_version=1 + 8 张表 + 4 个 wiki 子目录覆盖
  - 总数与 DB/rglob 双源校验
  - 锁定 2026-08-24 baseline 数字 (反向验证, 漂移会失败)
  - `--verify` 子命令两个退出码分支
- **scripts/execute_retirement.sh** (NEW, 309 行, 可执行):
  - 6 步流水线: kill :8000 → export → baseline → git mv backend → git mv frontend → git tag v0.5.0-retired
  - 默认 dry-run (打印所有命令, 不执行)
  - `--apply` 真执行
  - `--step N` 单步重跑 (排错用)
  - `--skip-kill / --skip-export / --skip-baseline` 灵活跳过
  - preflight 检查: git tree clean / hotspot.db 存在 / python + git 命令
  - 失败时打印 30 天应急回滚命令
- **docs/HOTSPOT_RETIREMENT.md** 增量:
  - 行数对账用 `snapshot_for_retirement.py` 取代手写 python -c
  - 新增 "步骤 2.5: 锁 baseline 快照"
  - 新增 "一键退役脚本" 章节 (含 dry-run / --apply / --step 示例)
  - 验收 checklist 加 3 项 (baseline 锁定 / --verify / --help 可执行)
  - 相关文档加 4 个新工具交叉链接
- **实测**: `bash scripts/execute_retirement.sh` 打印 6 步 [dry-run] 计划 + 30 天回滚指引
- **测试**: 21 cases 全绿 (8 export + 13 snapshot)

### Phase 7d — Schema dump (dsh `schema.ts` 参考) (当前)

> spec 第 207 行关键决策: 「迁移策略: 从 hotspot 导出当前 schema → 生成
> TypeScript DDL → 逐步迁移」。本阶段提供 hotspot 端的 schema 转储工具, 让
> dsh `packages/store/src/schema.ts` 不需要反代 hotspot 也能拿到完整 DDL。

- **scripts/dump_schema.py** (NEW, 425 行):
  - 输出 4 文件到 `data/schema/` (gitignored):
    - `ddl.sql` (36K): 全部 CREATE TABLE / VIRTUAL TABLE / INDEX / VIEW / TRIGGER
      (跳过 FTS5 shadow 与 sqlite_* 内部表, 可被 node:sqlite 直接 exec)
    - `tables.json` (126K): 62 业务表每张的 columns / pk / indexes / fks
    - `fks.json` (4.6K): 21 外键扁平图 (from_table, from, to_table, to)
    - `fts_groups.json` (1.2K): 3 个 FTS5 虚表组 (hotspots_fts + 4 shadow,
      unified_fts + 5 shadow, wiki_items_fts + 5 shadow)
  - 总数 (锁定 2026-08-24):
    - 190 sqlite_master 对象: 80 表 (62 业务 + 14 FTS5 shadow + 3 internal + 1 placeholder)
      + 106 索引 + 1 view + 3 trigger
    - 3 FTS5 虚表组 (热点 / 统一 / wiki)
    - 21 外键约束
  - 命令行:
    - `python3 scripts/dump_schema.py` 写全部 4 文件
    - `--sql-only` 仅写 ddl.sql
    - `--dry-run` 仅打印统计
    - `--out DIR` 自定义输出目录
  - 关键修复:
    - FTS5 shadow 按**后缀**严格匹配 (config/data/docsize/idx/content), 不能用 prefix
      匹配, 否则会把 hotspots_ad/ai/au trigger 误算
    - render_ddl 跳过 FTS5 shadow + sqlite_* 内部表 (sqlite_sequence 不可手动 CREATE)
- **backend/tests/test_dump_schema.py** (NEW, 14 cases 全绿):
  - schema_version=1 + 80 表覆盖 + 3 FTS5 组
  - FTS5 shadow 严格后缀匹配 (反向验证, trigger 不泄漏)
  - totals.business_tables >= 60 (锁定 2026-08-24: 62)
  - ddl.sql 经 sqlite3.executescript 重建 62 业务表全部成功
  - CLI 子命令: --sql-only 仅 ddl.sql; 默认 4 文件
- **docs/HOTSPOT_RETIREMENT.md** 增量: 相关文档加 dump_schema.py + test + dsh schema.ts 链接
- **测试总计**: 35 cases 全绿 (8 export + 13 snapshot + 14 schema dump)

### Phase 7e — Migrations 演进日志导出 (当前)

> spec 第 198 行要求「65 个 migrations/*.sql → store/src/migrations/ 直接复制+改写」。
> 本阶段提供 hotspot 端 67 个 .sql 的字节级导出 + manifest + README, 让 dsh 端
> `packages/store/src/migrations/` 可 `cp -r` 直接用。

- **scripts/export_migrations_for_dsh.py** (NEW, 337 行):
  - 扫描 `backend/repository/migrations/*.sql` (2026-08-24 实测: 67 文件)
  - 输出 3 类文件到 `data/migrations/` (gitignored):
    - 67 个 `.sql` 字节级复制 (sha256 一致)
    - `manifest.json`: schema_version=1 + 每文件 sha256/size/line_count/keywords
    - `README.md`: 关键词分布表 + 文件清单 + dsh 端消费指引
  - 关键词分布 (2026-08-24 实测):
    CREATE INDEX 168 / CREATE TABLE 95 / ALTER TABLE 50 / INSERT INTO 34 /
    CREATE TRIGGER 18 / DROP TABLE 16 / UPDATE 16 / PRAGMA 4 / CREATE VIEW 2 / DELETE FROM 1
  - 命令行:
    - `python3 scripts/export_migrations_for_dsh.py` 写全部
    - `--sql-only` 仅复制 .sql
    - `--dry-run` 仅打印统计
    - `--out DIR` 自定义输出目录
  - 关键修复: macOS `/private/var/folders/...` tmp_path 路径兼容
    (`_rel_or_abs()` 辅助函数, try relative_to 失败回退绝对路径)
- **backend/tests/test_export_migrations_for_dsh.py** (NEW, 196 行, 11 cases 全绿):
  - entries count == 67 (锁定 2026-08-24)
  - 排序 (001_init.sql → 070_kl_pipeline.sql)
  - 必需 keys (filename/size_bytes/line_count/sha256/keywords)
  - sha256 字节级校验 (manifest vs 磁盘)
  - 关键词分布 (CREATE TABLE ≥ 50 / CREATE INDEX ≥ 50)
  - manifest shape (schema_version=1 + totals + files)
  - README 内容 (dsh 消费指引 + 关键词表 + 文件清单)
  - CLI 三模式: --dry-run / 完整 / --sql-only
  - 字节级一致复制 (sha256 源 == 目标)
- **测试总计**: 46 cases 全绿 (8 export + 13 snapshot + 14 schema dump + 11 migrations)

### Phase 7f — Python → TS 移植对照表 (当前)

> 给 dsh-SecNews 仓库开发者一份**精确到文件 + 行数 + 关键函数**的移植清单,
> 照单实现 Phase 0-6 全部工作。

- **docs/PORT_SPEC.md** (NEW, 312 行, 10 节):
  - §1 总量基线: 481 py + 257 tsx / ~48.9K 行 (spec 行 9 的 "~25000 行" 是历史快照, 实测 2 倍)
  - §2 Phase 1 存储层 (6 文件映射): db.py→schema.ts / hotspot_repo.py→hotspot-repo.ts /
    migrations/*.sql / wiki_event_repo.py→wiki-event-repo.ts / backup_service.py→backup.ts / crypto.py→crypto.ts
  - §3 Phase 2 采集系统 (14 collector 行数表): base 500 / bid 867 / sogou 627 / security 326 /
    hn 257 / finance 256 / telegram 204 / item_builder 214 / tech 141 / ai_security 86 /
    startup 146 / session 154 / bid_status 138 / id_factory 53
  - §4 Phase 3 质量门禁 (13 gate + SimHash 算法 §4.1): 含 `simhash()` 核心算法 pseudocode
    (3-gram + mmh3 + jieba + 64-bit 加权投票)
  - §5 Phase 4 调度系统 (45 job 10 域分类): collect(5) / quality(4) / knowledge(8) /
    maintenance(6) / report(4) / enrichment(3) / codegarden(4) / sync(3) / compile(4) / review(4)
  - §6 Phase 5 AI/知识层 (5 关键算法): ai_hub 931 行 / concept_linker 473 行 /
    wiki_archiver 254 行 / retention_engine Ebbinghaus 公式 / enrich_v2 80 行
  - §7 Phase 6 前端迁移 (5 workbench 视图映射)
  - §8 全局验收命令 (6 phase 的 test/build/diff)
  - §9 hotspot 已交付的 dsh 消费资产 (7 行表格)
  - §10 风险与缓解 (5 个移植风险点: SimHash / KL 状态机 / collector 反爬 / migration 顺序 / Fernet 加密)
- **docs/HOTSPOT_RETIREMENT.md**: Phase 7 交付状态表加 7e/7f 两行
- **docs/CHANGELOG.md**: 加 §Phase 7e + §Phase 7f 条目

## 2026-08-24 P0 代码治理审计 (新增)

> **目标**: 给后续 P1+ 治理建立**基线 + 判据**, 非一次性大改实现。
> **原则**: 不改实现语义, 只清死代码 + 锁算法行为。

### P0-1 死代码清理

- `ruff check backend/ --select F401,F811 --fix --exclude tests` → **All checks passed!**
- F401 (unused import) 自动修复 ~32 处; F811 (redefinition) ~3 处
- F841 (unused local var) 保留 **59 个**不动, 风险三档归档至 `docs/P0_AUDIT.md §2.2`
- 含 ruff 自动修的 `backend/services/backup_service.py` (删 `import time`)

### P0-2 API 路由对账

- 后端真路由 (`app.openapi()`) **213 个** vs 前端 API 调用 (`frontend/src/`) **119 个**
- 后端独有 **94 个** → 分类到 7 个独立 frontend (kl/ai_hub/secnews/security_cockpit/knowledge-master/codegarden/main hotspot)
- 前端独有 **7 个 mismatch** → P1-1 task 修复

### P0-3 Characterization Test

- **新文件**: `backend/tests/test_characterization_golden.py` (**51 个测试, 全绿**)
- 覆盖: simhash (8+2+4+5+3=22) / retention (5+3+4=12) / concept_linker (6+9=15)
- 锁定 SHA-256 simhash fingerprint / retention Ebbinghaus 衰减 / 6-edge graph schema
- 设计原则: golden 数值透明 / frozen 时间 / tmp_path 隔离 / 不引入新依赖

### P0-4 交付物

- `docs/P0_AUDIT.md` (NEW, 188 行, 7 节)
- `backend/tests/test_characterization_golden.py` (NEW, 592 行, 51 tests)
- `backend/services/backup_service.py` (M, -1 line: `import time` 删除)

### P1+ 建议（按价值排序）

1. **P1-1**: 修复 7 个 frontend-only 路由 mismatch (用户可见 bug)
2. **P1-2**: F841 批 1 (~30 个低风险直删, 1 commit)
3. **P1-3**: 跨 7 个 frontend 建路由注册表 → 0 孤儿路由
4. **P1-4**: 后端模块入口加 `__all__`, 让 ruff / IDE 锁定对外 API
5. **P1-5**: mutation test, 验证 golden 真能 catch bug

> **数据时间**: 2026-08-24 23:15 (系统时间)
> **状态**: P0 全项交付, 待 P1 任务接续
