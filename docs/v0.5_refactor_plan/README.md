# Hotspot v0.5 重构方案（README）

> **版本:** 0.5 ｜ **日期:** 2026-08-21 ｜ **状态:** 历史存档
> **取代:** 旧版 `docs/archived/v0.5_refactor_plan_perf_only.md`
> **关联归档:** `docs/archived/v0.5_refactor_plan_wiki_v2.md`
> **前身:** `docs/superpowers/plans/2026-08-20-performance-feature-enhancement.md`
> **依据:** `docs/ARCHITECTURE.md`、`PROGRESS.md`、v0.4.3 分层产物

本文档为 v0.5 重构方案的**入口 README**。完整技术规格见 [SPEC.md](SPEC.md)，执行细节见 [EXEC.md](EXEC.md)。

---

## 0. 为什么改写计划（第一性原理）

旧计划把 v0.5 定义为「性能 + 自研 AiHub + 独立 Workbench 页」。深挖现状后发现四条硬事实，决策随之改变：

1. **已经有「AI 中枢」雏形**：`AIService`(门禁/评分/限频) 与 `LLMService`(回退链) 双出口并存，
   `llm_cache`/`llm_usage_log` 表已存在。v0.5 不是「从零写 AiHub」，而是「把双出口收敛成单契约」。
2. **editorial 新版式是空壳演示**：6 个 view 中 action 待办 / KL 复利是**硬编码假数据**，
   review / alert 是 toast 占位，报告/导入/secrets/sync/图谱等 14 项老功能**完全缺失**。
   「只留一套新样式」的真正障碍不是路由，是功能没接满。
3. **知识底座缺"终态归档"**：v0.4 数据流停在 SQLite，md 作为真源的语义弱；缺 confidence、
   supersession、Ebbinghaus 遗忘衰减、typed relationships。30 天皇冠数据无处沉淀为长期资产。
4. **外部已有成熟 agent harness（DeepSeek Harness）**：dsh 提供 agent-loop、工具注册表、
   LLM 适配、沙箱、会话日志、ACP(JSON-RPC stdio) 后端化接口。「自己手写 LLM 编排层」是重复造轮子。
5. **DB 全量存储是膨胀根因**：quality_check_logs 系 380 万行的本质是
   「每条目 × 每门禁结果都进中央表」。截断式 db_diet 治标不治本——正确做法是把存储主体
   **倒置**为 llm-wiki-2.0：摄入即写 md（gate 决策链随条目落 frontmatter），SQLite 只留
   热窗口索引 + 操作事件。膨胀在源头消失，且知识库天然成为 agent 的直接工作对象。
6. **dsh 可编排外部 agent**：dsh `subagent-acp` 能把一个轮次委派给另一个产品——Claude Code /
   Codex / Gemini CLI 等 ACP 兼容 CLI 均可挂载。hotspot 不绑定单一「大脑」，获得可切换、可降级的多 agent 编排层。

**结论**：v0.5 = 统一前端(editorial 接满 + AI 页) + dsh 认知层(acp 进程，编排 Claude Code /
Codex 等外部 CLI agent) + llm-wiki-2.0 数据底座(md 唯一真源，摄入即写盘，SQLite 退化为
热索引 + 事件桥) + 性能四板斧。不给用户第二套 UI；dsh 只作无头后端进程，通过 FastAPI
单一 HTTP 入口暴露；所有 agent（含外部 CLI）的持久产物强制写回 llm-wiki-2.0。

---

## 1. Goal 任务书（整块粘贴）

```text
# Hotspot v0.5 重构：统一前端 + DeepSeek Harness 认知层 + llm-wiki-2.0 数据底座 + 性能收敛

目标（硬数字）：
- 冷路径 /api/hotspots p95 <150ms（当前走缓存假基线不算数）
- 主列表查询走索引（EXPLAIN QUERY PLAN 出 idx_list_visible）
- 前端主 chunk <300KB（当前 1.14MB）
- hotspot.db <300MB（当前 1.0GB）——**且摄入不再入中央大表，diet 一次后永久封顶**
- 存储倒置：新条目摄入即写 llm-wiki-2.0 md（延迟 <1s），SQLite 只做热索引
- 多 agent 编排：dsh 挂载 Claude Code / Codex 等 ACP CLI，同一会话可切换/降级大脑
- 全仓 LLM 调用单契约（grep 可验，不再并立双出口）
- 统一前端：editorial 版式 6 view 假数据清零 + 新增第 7 view AI（dsh 工作台）
- dsh 认知层：DeepSeek Harness acp 进程后端化，FastAPI 唯一 HTTP 入口
- llm-wiki-2.0 数据底座：md 为真源，SQLite 退化为 search/index 缓存；confidence /
  supersession / Ebbinghaus 衰减 / 6 种 typed relationships
- 终态版本号 0.5.0

规格文件：`docs/v0.5_refactor_plan/README.md` 是唯一真理，任务定义/验收命令/地界全在其中。

M1 性能三任务（承接自旧计划，不改）：
1) hotspot_repo：is_hidden 列+部分索引 idx_list_visible；迁移从 064 起编；
   回填独立脚本 scripts/backfill_ingested_at.py 分批；cursor 改 ISO 比较留旧格式兼容。
2) cache.py：cache_hit 日志每 100 次采样；warmup 改真实查询。
3) vite manualChunks 拆 vendor-react/vendor-echarts；排查非 lazy echarts import。
M1 硬指标：p95<150ms；主 chunk<300KB；缓存每 101 次 get 日志 ≤2 条。

M2 DB 瘦身 + 表生命周期台账 + 契约第一刀：
4) scripts/db_diet.py：quality_check_logs_archive 截 30 天、quality_check_logs 截 30 天、
   crawler_runs 截 90 天、raw_items 截 90 天、hotspots 非收藏 180 天归档 JSONL；
   VACUUM INTO 替换；先在 .bak 副本演练。建表生命周期台账 retention.json，
   每张表登记 retention 并挂 weekly_maintenance job 链。
5) 契约第一刀（见 §6）：SSE 事件补 extract_done/job_done/task_done 三事件；
   CLI 输出统一 {ok,code,duration_ms,data} --json 契约（8 个批处理子命令）。
M2 硬指标：db<300MB；台账每表有清理 job；SSE/CLI 契约测试绿。

**M2-T6 存储倒置（2026-08-22 裁决：wiki-first，替代原「91 表四分温度库」方案）**:

> 裁决理由：T6 四分库仍以 SQLite 为真源，数据继续在库里积累，只是摊到 4 个文件；
> 与「md 为唯一真源、agent 直接读写知识库」的产品终态相悖。膨胀根治靠停写中央大表，
> 不靠分文件。`docs/v0.5_storage_design.md` 中有价值的部分（增量备份/Fernet/CI 校验）
> 收缩保留如下。

21) **摄入路径倒置**：collect → gates → 先写 llm-wiki-2.0（items/{hash}.md 完整 frontmatter +
    sources/{hash}.md 含 gate 决策链，atomic .tmp→rename，延迟 <1s）→ 异步 wiki_indexer
    刷新 SQLite 热窗口索引。quality_check_logs 中央表**停写**（gate 结果随条目 md 分布式
    存储）；raw_items/crawler_runs 转滚动事件表（90 天滑窗）。DB ↔ wiki 通过事件对应
    （wiki_written / index_refreshed SSE 事件 + indexer 幂等重建）双向对账。
22) **agent 知识访问替代 RAG**：MCP 工具面改为直接读写 llm-wiki-2.0——search=FTS5 over
    wiki（indexer 维护）、read=md 直读、write=经 ai_hub 单契约落 md；chunk_service/RAG
    检索路径冻结不再扩展。
23) **存量迁移**：hotspots 存量 + knowledge/(4152 items + 98 concepts) 批量导出为
    llm-wiki-2.0 md（快照校验后切换读取路径，v0.4 双轨零回归）。
24) **db_diet 一次性执行**（已有脚本）：历史中央大表截断 + VACUUM INTO；此后主库只含
    热窗口索引 + 滚动事件，体积自然封顶 <300MB。
25) **备份与完整性（自 T6 收缩保留）**：daily_db_backup_job 增量(WAL 帧)+周日 full、
    sha256 链 + PRAGMA integrity_check、backups/≤1GB；Fernet 加密对象从 COLD db 改为
    llm-wiki-2.0 归档 bundle；scripts/check_backup_chain.py 进 CI。
M2-T6 硬指标：新条目摄入即出 md(<1s)；主库 diet 后 <300MB 且停止增长；
  agent 经 MCP 直接命中 wiki 内容（grep 无 chunk/RAG 新增依赖）；
  backups/≤1GB、integrity_check 全 ok、恢复演练过。

M3 统一前端（编辑风 editorial 接满）：
6) editorial 6 view 接真实 API：todos→/api/todos、review→/api/reviews、alert→/api/alerts/v2、
   KL 复利→知识 API、outbox→后端 outbox、briefing→digest；砍硬编码假数据与 toast 占位。
7) 缺的 14 项老功能按优先级分批接回：报告(日报/周报/月报)、导入(import+knowledge)、
   历史批次、secrets、sync、知识图谱(process/compile/imported)、attention heatmap、
   bid-alert、skills、CodeGarden、soul 画像+stats、趋势完整分析、收藏管理页、质量拒绝明细。
8) /data 老版式进入退役倒计时（M5 才物理删除，期间保持可回跳）。
9) GET /api/workbench/summary（6 块聚合，outcome 用 llm-wiki-2.0 指标：
   crystallized_this_week / superseded_this_week / retention_health / confidence_avg_7d）。
   **只保留 API，不建 Workbench UI**（Today 视图并入 editorial front 顶栏 summary card）。
M3 硬指标：editorial 无硬编码数据、无 toast 占位；每 view 有真实 API 数据；
   summary<150ms、6 块全真。

M3.5 llm-wiki-2.0 数据底座（md 真源化）：
10) llm-wiki-2.0 目录：{items,sources,concepts,digest,schema}/ + retention.json + graph.json；
    SCHEMA.md 定义全部 frontmatter；v0.4 knowledge/_SCHEMA.md 标 deprecated 但兼容；
    Settings 加 HOTSPOT_LLM_WIKI_V2=false 可关（Pydantic+env，非 TOML）。
11) wiki_archiver.py：30 天前非收藏条目 → items/{hash}.md + sources/{hash}.md
    （含抓取元数据 + quality_gate 决策链），atomic 写入(.tmp→rename)，初始 retention 1.0。
12) retention_engine.py：Ebbinghaus 衰减 current *= 0.9^(days/7)；access 时 reset；
    周 job 跑一次；<0.3 标 stale(不删只降权)；scripts/check_retention_decay.py 进 CI。
13) graph.json 升级 6 种边（v0.4 只有 2 种）；t_confidence 写 items frontmatter
    confidence 字段；t_supersede 建立 supersession 链（被新证据覆盖自动置 supersedes）。
14) M5 一次性迁移：实测 4152 items + 98 concepts 从 knowledge/ 迁到 llm-wiki-2.0/。
M3.5 硬指标：归档 100 条→ md 数对得上；retention 7 天 1.0→0.9、30 天≈0.7、
   access 重置 1.0；CI check_retention(>0.7 占比≥80%)；v0.4 数据双轨期间零功能回归。

M4 dsh 认知层（统一前端第 7 view AI）：
15) FastAPI 新增 /api/agent/* 代理路由（token 鉴权，转发 dsh acp stdio JSON-RPC）。
16) acp 子进程管理器：lifespan spawn/保活/崩溃重启/心跳；dsh 离线→AI view 降级显示，
    其余页面照常。降级开关 HOTSPOT_AGENT_BACKEND=off|acp。
17) editorial 新增第 7 view 'AI'：编辑风对话组件，走 /api/agent/session|send|events(SSE)，
    不 iframe dsh web；配置 MCP client 连 hotspot，tool 面见 §6。
18) 记忆单源裁决：dsh 会话仅短期上下文；agent 持久产物（提炼/建议/flag）写回
    llm-wiki-2.0 + SQLite（经 ai_hub 单契约），不滞留 dsh。
M4 硬指标：/ai 完成 意图→工具→结果 闭环；对话能调 hotspot MCP 工具；
   dsh 崩溃不影响非 agent 页面；grep 验证无绕过契约的 LLM 调用。

M5 收尾 + 发版：
19) ai_hub.py 单 PR 合并 llm_service+ai_service（1 步，不搞 strangler）：
    既有 test_llm_service 全绿为准入；mcp_agent_tools 4 个 tool 经 hub 审计入口；
    grep 'from llm_service|from ai_service' = 0；ai_scores 写路径仅 ai_hub 命中。
20) version 0.5.0；CHANGELOG 补条目；generate_meta --check；
    ARCHITECTURE.md 更新至 v0.5 现状；/data 与 dsh web(:3080) 生产入口移除。
M5 硬指标：版本三处一致；meta check 过；LLM 单出口 grep 验证；全站唯一路由入口（editorial）。

全程法（违反即不合格）：
- 测试基线不可退：后端 ≥2547、skipped 不增；前端 tsc+vitest(292)+build 全绿。
- 启动迁移禁大表 UPDATE/全量回填；凭据只走 env 不落表。
- 不引入 Redis/PG/Celery/Docker/K8s。
- 禁 force push / --no-verify；一任务一提交。
```

---

## 2. 目标对比（新旧 v0.5）

| 目标 | 旧 v0.5 | 新 v0.5 |
|---|---|---|
| 性能四板斧 | M1/M2 | 保留（M1/M2，目标收紧） |
| AI 中枢 | 自研 ai_hub.py 单出口 | 单契约收敛 + dsh 认知层（M4/M5） |
| 看板 | 新建 Workbench 页（第三套 UI） | **保留 API + editorial 顶栏 Today card**（M3） |
| Agent | 不引入 | DeepSeek Harness acp 后端进程（M4） |
| 知识底座 | SQLite 为真源，数据停库里 | **llm-wiki-2.0 md 真源 + SQLite 缓存**（M3.5） |
| 能力语义 | 无 confidence/supersession/衰减 | confidence + supersession 链 + Ebbinghaus 衰减 + 6 种边 |
| 前端 | 3 套风险（老/editorial/Workbench） | 1 套（editorial + AI view） |

---

## 12. 决策记录（2026-08-21 与 Duke 拍板的 5 项）

| ID | 决策点 | 拍板 | 影响 |
|---|---|---|---|
| D1 | dsh 部署形态 | **本地已独立装 + 重新部署 deepseek-ai/deepseek-harness 与 hotspot 融合** | M4 不再 defer；需 git submodule 或 vendor 嵌入 dsh 源码到 hotspot 仓库 |
| D2 | 24 collection errors 处理 | **我修（独立 PR）** | 实际根因是 hotspot_repo.py:609 IndentationError（working tree WIP 引入），1 行 try/except 包裹修复 + test_query_next_cursor_format 断言更新 → 2547 baseline 恢复 |
| D3 | hotspot_repo working tree 处理 | **先 commit 现状** | 与 D2 协调：1 行修 + WIP 改造 → 0490470f 一次 commit，2547 全绿 |
| D4 | plan 文档位置 | **更新到 v0.5_refactor_plan.md** | 不新建 docs/v0.5_execution_plan.md，在本 SPEC 追加 §11-§14 |
| D5 | EditorialView 拆分 | **（待 M3 开工时决定）** | 1067 行单文件不可改，必须先拆 6 组件；建议 M3-T6 开工前 0.5d 拆 |

---

## 导航

- **[SPEC.md](SPEC.md)** — 技术规格：约束、基线、架构、契约、里程碑、风险
- **[EXEC.md](EXEC.md)** — 执行细节：文件映射、任务分解、dsh 融合、存储设计、部署步骤
