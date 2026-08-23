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
- [ ] M3.5-Task10 llm-wiki-2.0 目录 + SCHEMA + HOTSPOT_LLM_WIKI_V2 开关
- [ ] M3.5-Task11 wiki_archiver.py（30 天归档 md + sources + atomic）
- [ ] M3.5-Task12 retention_engine.py（Ebbinghaus 衰减 + 周 job + CI check）
- [ ] M3.5-Task13 graph.json 6 种边 + t_confidence + t_supersede
- [ ] **M3.5 里程碑验收**（归档 100 条对得上 / 衰减曲线 / 双轨零回归）
- [ ] M4-Task15 /api/agent/* 代理路由（token 鉴权 → dsh acp）
- [ ] M4-Task16 acp 子进程管理器（spawn/保活/重启/降级 HOTSPOT_AGENT_BACKEND）
- [ ] M4-Task17 editorial 第 7 view 'AI'（编辑风对话 + SSE，不 iframe）
- [ ] M4-Task18 记忆单源裁决（agent 产物写回 llm-wiki-2.0 + SQLite）
- [ ] **M4 里程碑验收**（意图→工具→结果 / 崩溃降级不 500 / grep 单契约）
- [ ] M5-Task19 ai_hub.py 单 PR 合并双出口（test_llm_service 全绿准入）
- [ ] M5-Task20 版本 0.5.0 + CHANGELOG + generate_meta + ARCHITECTURE + 移除旧入口
- [ ] **M5 里程碑验收**（LLM 单出口 grep / 版本一致 / meta check / 唯一路由入口）
- [ ] 全局结束门禁 + 最终 code review

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

### M4 路线决策（2026-08-23，用户裁决）

> 发现平行工程 `~/Documents/dsh-SecNews/SECNEWS-二次开发方案.md`（dsh 宿主 :3210 反代
> hotspot 骨干、AI 能力按钮、P2 已完成），与 SPEC §13-17 的 hotspot 宿主 + editorial 第7
> view 自由对话方向相反。用户拍板：

- **M4 以 dsh-SecNews 方案为准**：hotspot 不做 acp 子进程宿主，T16/T17 的
  「FastAPI spawn dsh」「editorial AI 对话 view」不再按原样执行；
  hotspot 侧保留并已提前落地的部分：agent_runner_schema + agents.yaml（T15b，
  runner 元数据事实源）、ai_hub 写回门面、MCP 14 工具面（dsh mcp-client 已验证可连）。
- **T18 记忆单源**改为：dsh agent 产物经 ai_hub 写回（llm-wiki-2.0 就绪前暂写 knowledge/）。
- **SPEC 待改**：docs/v0.5_refactor_plan.md §13-§17 需按 dsh-SecNews 方案重写
  （hotspot=确定性骨干被反代；dsh=认知宿主）；执行 M4 前先改 SPEC。
- **M3.5 与 M4 整合推进**（用户裁决）：llm-wiki-2.0 底座与 dsh 集成一体完成。
