# Changelog

## v0.5.1 (2026-08-25) — v0.6 P0 清场第一批 (⑥③⑤)

> 方案: [`docs/v0.6_ai_workstation_plan.md`](v0.6_ai_workstation_plan.md) §P0 清场与统一。
> 本批次为用户裁决顺序: 先 ⑥ ai_hub 双引擎收敛 → ③ jobs.py 拆分 → ⑤ 凭据单一来源。

### ⑥ ai_hub 双引擎收敛 (`6556cd83`; 归因说明见下)

- `AIService` sensenova 硬编码 (URL/模型名/api_key) 并入 `config/llm.yaml` 单一来源:
  新增 `sensenova` provider 块 (`type: openai_compatible`, base_url
  `https://token.sensenova.cn/v1`); `default_provider: openai → sensenova`
- `AIService` 改为经 `_provider_cfg/_base_url/_eval_model` 从 `llm_service.config`
  解析, env 覆盖 (`AI_PROVIDER`) 保留; ClassVar 兜底表防配置缺失
- **公共契约零漂移**: `_call_sensenova_detect/_resolve_api_key/_resolve_provider/
  _ollama_up/_cache_set` 名称签名不变, URL 前缀与模型串断言全过; 定向 63 测 +
  全量 2879 passed / 0 failed
- `fallback_order` 刻意不含 sensenova — LLMService 评分链保持休眠 (真实计费翻转
  留 P1), 避免 T1 场景意外产生调用成本

> **归因说明**: ⑥ 的主体 diff (ai_hub.py +87 / llm.yaml +21) 因并行会话共享暂存区
> 被卷入其提交 `e94e90f1` (linker wiki_fs 修复) 入库; `6556cd83` 为补交的收尾部分。
> 内容归属以本条目为准。

### ③ scheduler/jobs.py 按域拆分 (`8f4ae80a` + `f554c46c`)

- 单文件 (2331 行) → `backend/scheduler/jobs/` 包: `_runtime`(注入+SSE 插桩) /
  `collect` / `kl` / `codegarden` / `security` / `knowledge` / `digest` /
  `maintenance` 八模块, 段落 AST 逐字节搬运
- **空壳门面** (方案 §9): `__init__.py` 全量 re-export + PEP562 `__getattr__`
  活委托 `_service`; `from ...jobs import X` / `jobs.X` / `patch("...jobs.X")`
  三种契约行为与拆分前一致; 跨域 job 经 `_jobs_pkg.<fn>` 动态解析防快照绑定
- generate_meta `count_jobs` 计数拆分不变 (47, 数的是 scheduler.py 的 add_job);
  定向 54+11 测 + 全量两轮绿; 旧文件删除单独成 commit 防 pathspec 漏删

### ⑤ 凭据单一来源 (`5ab5d996` + 数据面收敛)

- **核验坐实审计**: settings 表残留明文 `quality.llm_api_key` (37 字符 sk- 串);
  llm_secrets 表存在但 0 行; 后端对该 settings 键零读取方 (GateContext.llm_api_key
  字段无赋值点, 纯死字段)
- **llm.yaml provider 链对齐**: 已随 ⑥ 完成 (sensenova 块 + default_provider)
- **明文收敛**: settings 值置空 (保留行作溯源), 原值备份至仓库外
  `~/.hotspot/legacy-quality-llm-api-key-20260825.txt` (0600)
- ⚠️ **加密通道接管受阻**: llm_secrets 主密钥已丢失 (keyring 条目对 encryption_keys
  id=2 verify 失败被 service 清除, settings 回退亦空), 且产品决策 Q1 禁止重置、
  sync_configs.webdav_password_encrypted 存量密文依赖现 key — 加密迁移需用户侧
  裁决 (重建主密钥须按 Q1 走 DB 重置, 或通道继续休眠)。详见 PROGRESS 同日条目
- `api/llm_status.py` EvaluateRequest docstring 对齐 ai_hub 实际解析链
  (env AI_PROVIDER → llm.yaml default_provider, 不再指向已废弃 settings 路径)

### meta 同步 (`d473070e`)

- ARCHITECTURE.md services 88→89 (并行会话 mastery_projection.py 注册补账);
  `generate_meta --check` 绿 (jobs 47 / collectors 14 / routers 57 / services 89)

## v0.6.0-dev (2026-08-25) — CRM 业绩座舱 (security-cockpit 方案 C)

> **决策**: 用户拍板 [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md) 方案 C (完整移植), PRD 先行 ([`COCKPIT_PRD.md`](COCKPIT_PRD.md))。CRM-like 业务 (客户/商机/业绩) 与 hotspot 资讯聚合正交, 以 `crm` feature gate 扩展域接入。

### T1-T5 一任务一提交

- **T1 PRD** (`b2131446`): 四问默认假设 + US-1 录入客户 / US-2 商机推进 / US-3 座舱复盘 + 六态状态机 (需求沟通→方案提交→商务谈判→合同签订→赢单/输单, 终态冻结) + KPI 口径表
- **T2 数据层** (`4b8b4c66`): migration `071_crm_cockpit.sql` 三表 + `crm_customer_repo` / `crm_opportunity_repo` (状态机唯一裁决) + 单测 10 用例
- **T3 API 层** (`920587c8`): `/api/crm/customers` CRUD、`/api/crm/opportunities` (+`/transition` 唯一阶段入口)、`/api/crm/stats|meta`; `X-CRM-Token` 常量时间鉴权 (未设 env = 本地模式); extensions 注册 crm 扩展域 + `feature_gates.toml` `crm = true`; 测试矩阵补 crm; ARCHITECTURE 数字同步 (routers 57 / services 87)
- **T4 前端** (`405d98ca`): `/crm` 页面 — CockpitDashboard (8 KPI 卡 + 月度营收/区域分布/漏斗手写 SVG)、CustomerManager、OpportunityManager; `useFeatureFlags.crm` 全链路; ROUTE_REGISTRY §2.7 登记; Header「更多」入口
- **T5 E2E+文档** (本 commit): `backend/tests/test_crm_e2e.py` 全栈闭环 (US-1→US-2→US-3 经 register_routers); PROGRESS / CHANGELOG / P2_6_COCKPIT_EVAL §决议记录 同步; Playwright 浏览器级 E2E 列为后续增强

## v0.5.0-retired (2026-08-24, Phase 7b 待 dsh 端验收后正式生效)

> **状态 (2026-08-25)**: ⏸️ **冻结** — Phase 7 破坏性步骤 (D+2 停 :8000 / D+3 git mv 归档) 按用户裁决 (见 `PROGRESS.md` §2026-08-24 产品三层架构裁决 §连锁裁决) **冻结不执行**; hotspot 仍活跃开发 (`docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6)。7a-7d 工具保留为参考资产。
> **退役文档**: [`HOTSPOT_RETIREMENT.md`](HOTSPOT_RETIREMENT.md) (含冻结横幅)
> **整合 spec**: [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) + [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md)

### Phase 7a — hotspot.db → JSON 旁路导出器 (commit b1cd80de)

- `scripts/export_for_dsh.py` (375 行): 8 张核心表 (hotspots 3391 / favorites 4 /
  todos 6 / sm2_reviews 3 / annotations 2 / hotspot_tags 5356 / knowledge_concepts 98 /
  knowledge_graph 42 = 8902 行) + 4149 wiki items + 96 concepts = 4245 wiki 文件
  旁路导出为 JSON, 供 dsh-SecNews `packages/store/src/migrate-from-hotspot.ts` 消费
- 输出契约: `manifest.json` (schema_version + counts + contract) + 每张表 `*.json`
  (CREATE TABLE DDL + columns + rows)
- 字段归一化: datetime → ISO8601 / BLOB → `{__b64__: base64}` /
  JSON-encoded 字符串 → 原生 list/object / None → null
- 37 张 SKIP_TABLES 含 rationale (schema_version / encryption_keys / cg_* /
  llm_* / FTS5 虚表等)
- `backend/tests/test_export_for_dsh.py`: 8 用例全绿 (manifest / table shape /
  json-encoded / row count / skip rationale)

### Phase 7b — 退役清单文档 (commit 8ec7db61)

- `docs/HOTSPOT_RETIREMENT.md` (202 行): 退役时间线 (D+0 至 D+4) + 行数对账命令 +
  6 步退役步骤 + 代码迁移清单 + 30 天应急回滚 SLA + 9 项验收 checklist
- `AGENTS.md` 顶部加 RETIRED banner, 锁定 2026-08-24 行数基线, Development Commands
  加退役警告
- `PROGRESS.md` 新增 §2026-08-24 Phase 7 数据迁移 + 旧系统退役 (c5)
- `.gitignore`: 新增 `data/export/` (运行时产物不入版本库)

### 待执行 (D+2/D+3, gated on dsh 端 secnews.db 行数对账)

- hotspot 端 :8000 进程停止 (`kill -TERM $(lsof -ti:8000)`)
- `git mv backend hotspot-archived` (保留 history)
- `git mv frontend hotspot-archived/frontend`
- `git tag -a v0.5.0-retired -m "Python 后端退役标记, 数据已迁入 dsh-SecNews"`

### Phase 7c — 行数 baseline + 一键退役流水线 (commit 94d02c49)

- `scripts/snapshot_for_retirement.py` (305 行): 锁定 2026-08-24 行数基线,
  供 dsh 端 secnews.db 迁移完成后对账; `snapshot()` 写 `data/retirement_baseline.json`,
  `verify()` 反向校验; 退出码 0/1/2 (一致/漂移/baseline 缺失)
- `scripts/execute_retirement.sh` (309 行, 可执行): 6 步退役流水线 (Preflight →
  停 :8000 → export → baseline → git mv backend → git mv frontend → git tag),
  默认 dry-run, `--apply` 真执行, `--step N` 单步重跑, `--skip-kill/export/baseline`
  三个开关
- `data/retirement_baseline.json` (42 行): 锁定 8 表 8902 行 + 4 wiki 子目录
  4245 文件 (4149 items + 96 concepts), 2026-08-24 baseline
- `backend/tests/test_snapshot_for_retirement.py` (204 行, 13 用例全绿):
  importlib 加载 scripts/ 脚本, 反向锁定 baseline 数字, 验证 --verify 两个退出码分支
- `docs/HOTSPOT_RETIREMENT.md` 加 §一键退役脚本 + §步骤 2.5 锁 baseline 章节

### Phase 7d — schema 导出给 dsh (commit 40632c98)

- `scripts/dump_schema.py` (443 行): 响应 spec 第 207 行「迁移策略: 从 hotspot
  导出当前 schema → 生成 TypeScript DDL → 逐步迁移」, 输出 4 文件供 dsh
  `packages/store/src/schema.ts` 直接消费, dsh 不需反代 hotspot
  - `data/schema/ddl.sql`: 全部 CREATE TABLE/INDEX/VIEW/TRIGGER 按依赖顺序
    (跳过 FTS5 shadow + sqlite_* 内部表), 可被 node:sqlite `exec()` 重建
  - `data/schema/tables.json`: 每张业务表 dict (columns/pk/indexes/fks)
  - `data/schema/fks.json`: 全表外键扁平图 (from_table/from/to_table/to)
  - `data/schema/fts_groups.json`: FTS5 虚表组 (hotspots_fts/unified_fts/wiki_items_fts)
- 关键 bug 修复 (写在脚本 docstring):
  - FTS5 shadow 必须按**后缀**匹配 (_config/_data/_docsize/_idx/_content),
    prefix 匹配会把 hotspots_ad/ai/au trigger 误算入
  - `render_ddl` 必须跳过 FTS5 shadow (VIRTUAL TABLE 隐式创建) + sqlite_* 内部表
    (sqlite_sequence 不可手动 CREATE)
- `backend/tests/test_dump_schema.py` (234 行, 14 用例全绿):
  schema_version=1 + totals + FTS5 后缀严格匹配 + 双源校验 + sqlite3.executescript
  重建 62 业务表 + CLI 子命令 (--sql-only / 完整模式)
- `docs/HOTSPOT_RETIREMENT.md` 加 §Phase 7d 链接

### Phase 7e — migrations 演进日志导出 (commit pending)

- `scripts/export_migrations_for_dsh.py` (337 行): 响应 spec 第 198 行
  「65 个 migrations/*.sql → store/src/migrations/ 直接复制+改写」,
  把 hotspot 67 个 .sql 文件**字节级**导出供 dsh `packages/store/src/migrations/`
  直接 commit, 保留演进路径可追溯
  - `data/migrations/*.sql`: 67 个文件 (001_init → 070_kl_pipeline) 按字典序复制
  - `data/migrations/manifest.json`: 每文件 sha256/size/line_count + 关键词分布
  - `data/migrations/README.md`: dsh 端消费指引 (cp -r + diff ddl.sql)
- 关键词统计 (2026-08-24 实测): CREATE INDEX 168 + CREATE TABLE 95 + ALTER TABLE 50 +
  INSERT INTO 34 + CREATE TRIGGER 18 + DROP TABLE 16 + UPDATE 16 + PRAGMA 4 + VIEW 2 + DELETE 1
- `backend/tests/test_export_migrations_for_dsh.py` (196 行, 11 用例全绿):
  entries 数量/排序/keys/sha256 校验 + keywords 分布 + manifest shape + README 含
  dsh 端消费指引 + CLI 子命令 (--dry-run/--sql-only) + 字节级一致复制验证

### Phase 7f — Python→TS 移植对照表 (commit pending)

- `docs/PORT_SPEC.md` (312 行): 给 dsh 仓库开发者一份**精确到文件 + 行数 +
  关键函数**的移植清单, 10 节覆盖:
  - §1 总量基线: 481 py + 257 tsx / ~48.9K 行
  - §2 Phase 1 存储层 (6 个文件映射)
  - §3 Phase 2 采集系统 (14 collector + 行数表)
  - §4 Phase 3 质量门禁 (13 gate + SimHash 算法移植 §4.1)
  - §5 Phase 4 调度系统 (45 job 域分类)
  - §6 Phase 5 AI/知识层 (5 关键算法: ai_hub/wiki_archiver/retention/concept_linker/enrich_v2)
  - §7 Phase 6 前端迁移 (5 workbench 视图)
  - §8 全局验收命令 (6 个 phase 的 test/build/diff)
  - §9 hotspot 已交付的 dsh 消费资产 (6 行表格)
  - §10 风险与缓解 (5 个移植风险点)
- SimHash 算法移植是 P3 关键风险点, 文档给出 Python 源码 + TS 移植要点 (分词/哈希/向量)
- Ebbinghaus 衰减公式 `current = initial * 0.9 ^ (days / 7)` 完整列出, dsh 端可直接翻译

### 工具交叉引用

| 工具 | 行数 | 用途 | commit |
|------|------|------|--------|
| `scripts/export_for_dsh.py` | 375 | 8 表 → JSON 旁路 | b1cd80de |
| `scripts/snapshot_for_retirement.py` | 305 | 行数基线 + verify | 94d02c49 |
| `scripts/dump_schema.py` | 443 | 80 表 DDL → 4 文件 | 40632c98 |
| `scripts/execute_retirement.sh` | 309 | 6 步退役 dry-run/apply | 94d02c49 |
| `data/retirement_baseline.json` | 42 | 2026-08-24 baseline | 94d02c49 |
| `data/schema/` (4 文件) | - | dsh schema.ts 消费 | 40632c98 |

### P0 代码治理审计 (2026-08-24, P0 commit 待 push)

- **`docs/P0_AUDIT.md`** (NEW, 188 行, 7 节): 死代码 + 路由对账 + characterization test 三件套
- **`backend/tests/test_characterization_golden.py`** (NEW, 592 行, 51 tests):
  - SimHash: 8 段真实文本的 64-bit SHA-256 fingerprint 锁定 + hamming 距离 golden
  - Retention: run_decay / record_access / check_retention_health 在 frozen 时间下的行为锁
  - Concept linker: link_tags_to_concepts / validate_graph_schema 对 6-edge graph schema 的判据
- **死代码清理** (`ruff check --select F401,F811 --fix`): 自动修 ~32 unused imports + 3 redefs
- **路由对账**: 后端 213 / 前端 119 / 后端独有 94 (分类到 7 个独立 frontend) / 前端独有 7 mismatch
- P1+ 待办: F841 批 1 (~30 个低风险) / 7 mismatch 修复 / 跨 frontend 路由注册表

### P1 治理落地 (2026-08-24, 4 commits: 6f235816 + 7ca15779 + a7965dc8 + de4decf4)

- **P1-1 frontend 路由 mismatch 修复** (commit `6f235816`, 3 files, +6/-6):
  - `KnowledgeActionBar.tsx + test`: `/api/llm/digest` → `/api/digests/generate`
  - `JudgeLayerPage.tsx`: `/api/soul` → `/api/knowledge/soul`
  - 留档: 3 个 mcp 路由 (feature gate 设计) + 2 个 test mock URL
- **P1-2 F841 批 1 删除低风险 dead vars** (commit `7ca15779`, 8 files, +9/-34):
  - 11 个 production dead vars: soul_service (4) + collection_service (1) +
    catchup_checkpoint_repo (1+整块清理) + todo_repo (1) + backup_service (1) +
    codegarden_scanner (1) + maintenance_service (1) + triggers/t3 (1)
  - ruff F841: **55 → 44** (-11)
  - catchup_checkpoint_repo.py 整块删 sql/finished_clause/params/if-finished_clause 12 行
- **P1-3 跨子模块路由注册表** (commit `a7965dc8`, 2 files, +171):
  - `frontend/src/routes/ROUTE_REGISTRY.md` (NEW, 166 行, 6 节):
    - §一 7 子模块边界 (main hotspot 44% / knowledge-master 27% / codegarden 13% /
      kl+ai_hub 10% / security_cockpit 4% / secnews 1%)
    - §二 前端 49 路由按子模块分组 (含 feature flag 标注)
    - §三 P1-1 修复的 7 mismatch 留档
    - §四 新增路由 CI 规则 (5 条)
    - §五 orphan 检测脚本 (manual)
    - §六 未决事项
  - `routes/index.tsx` 顶部加注释指向注册表
- **P1-4 mutation test 验证 golden catch bug** (commit `de4decf4`, scripts/, +255):
  - `scripts/p1_4_mutation_test.py` (NEW, 11 类变异, .bak 精确 revert)
  - **Mutation Score: 10/11 = 90.9% (PASS ≥ 80%)**
  - 1 个真实盲点: decay_score 去掉 round (golden 未测 days 小数精度漂移)
- **PROGRESS.md** 加 P1 治理落地条目 (4 commits 总览 + 状态)
- **P0_AUDIT.md §七** 5 项未做事项标完成 (P1-1/2/3 已闭环), §八加 P1 落地摘要

### P2 治理落地 (2026-08-25, 7 commits: 5fe965a7 + eae608e1 + cf0a0a14 + dbbb3d3c + 4d76b2c2 + d2200a5c)

> 闭环 P0 audit §六 P1+ 剩余 + P1 落地的 48 F841 / 1 mutation 盲点 / 后端 `__all__` 全量补齐 /
> security cockpit SPA 评估。原则: 锁行为不锁实现, 留档可追溯, 区分 mock patch 设计意图 vs 真 dead variable。
> 完整报告: [`docs/P2_5_ALL_AUDIT.md`](P2_5_ALL_AUDIT.md) + [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md)

- **P2-1 F841 批 2 production rename** (commit `5fe965a7`, 12 files, +50/-23):
  - 删除 17 个中等风险 production dead vars (P0 audit §2.2 标 "改 `_` 前缀 + del")
    涉及: soul_service (4+3) + collection_service (2) + digests_archive (1) +
    digest_repo (1) + hook_logger (1) + kl_import (1) + backup_database (1) +
    favorites_service (1) + gap_detector (1) + quality_logger (1)
  - 改名模式: `var = expr()` → `_var = expr(); del _var; # noqa: F841` 留调用痕迹
  - ruff F841 production: **44 → 27** (-17)
- **P2-2 pk_map dead variable PR 评审留档** (commit `eae608e1`, 1 doc, NEW):
  - [`docs/P2_DEAD_VARS_PR_REVIEW.md`](P2_DEAD_VARS_PR_REVIEW.md) (NEW, 6.3KB)
  - 1 个 high-risk dead var: `backend/services/codegarden_scanner.py` pk_map
    (8 个 hot-path 调用方, 删前需 PR 评审确认切接口)
  - 决议: 留档不删, 等下一次 PR 评审由 reviewer 拍板
- **P2-3 mutation 盲点补 test** (commit `cf0a0a14`, 2 files, +96/-10):
  - 新增 `TestDecayScorePrecisionFrozen` (6 tests) 在 `test_characterization_golden.py`
    (golden 总数 51 → 57)
  - 关键 golden: `decay_score(1.0, 1.5) == 0.9777` (raw=0.9776757055472389, 去 round 则失败)
  - 修 `scripts/p1_4_mutation_test.py`: TEST_SELECTOR 加新 class + 修 output regex
    (旧 regex 误取中间行, 新逻辑只取 summary 行)
  - mutation score: 10/11 → **11/11 (100%)**
- **P2-4 F841 tests/ 30 cleanup** (commit `dbbb3d3c`, 20 files, +21/-41):
  - **区分 mock patch 设计意图**: 25 真 dead 直接删 + 2 mock patch 改 `_mock_log`
    (ruff 视为 used, 保留 mock 引用) + 1 未消费 mock_exec drop `as` 子句
  - 涉及关键文件: `test_catchup_phase9.py` (mock_log L163/274/411, L284 events 真消费保留) +
    `test_catchup_service.py` L463 (drop `as mock_exec`)
  - 修 2 个 typo (`__mock_log` 双下划线) + 2 个漏改 (L304 report, L305 latest)
  - 验证: 237 tests passed, ruff tests/ F841 → 0
- **P2-5 后端模块入口 `__all__` 全量 audit** (commit `4d76b2c2`, 23 files, +113/-20):
  - [`docs/P2_5_ALL_AUDIT.md`](P2_5_ALL_AUDIT.md) (NEW, 71 行, audit 表 23 init.py)
  - 10 个补齐 `__all__: list[str] = []` 零契约 (parsers/bid/core/tools/services/
    repository/repository/migrations/security/domain/scheduler/tests)
  - 10 个已有 re-export + 3 个本就有空契约
  - 三档语义: 显式 re-export / 零契约 / 缺失 (缺失即模糊地带)
  - 顺手 ruff `--fix F401` 自动清 19 个测试 unused imports
    (test_cli_contract/collect_validator/dump_schema/knowledge_oneway/
     migrate_temp_layers/quality_hook_filter/quality_logs_archive/
     scheduler_concurrency/snapshot_for_retirement/sync_config_service/
     sync_service_split/wiki_archiver_retention)
- **P2-6 security cockpit SPA 完整评估** (commit `d2200a5c`, 1 file, +211):
  - [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md) (NEW, 211 行, 6 节)
  - 现状: `security-cockpit/` 3 静态 HTML + 1 CSS = **2363 行**
    (cockpit 683 + customer-form 928 + opportunity-form 663)
  - **业务正交**: CRM-like (客户/业绩/商机) vs hotspot 资讯聚合, 零集成点
  - 三档方案: **A 冻结留档 (0h, 推荐) / B MVP 简版 (12h) / C 完整移植 (90h)**
  - 决策权归用户/产品方
- **PROGRESS.md** 加 `## 2026-08-25 P2 治理落地` 章节 (每 P2 子任务独立小节)
- **P0_AUDIT.md** 加 §九 P2 落地摘要 (7 子任务 commits + 累计收益表)

### P2 累计收益

| 指标 | P0 audit §六基线 | P1 落地后 | **P2 落地后** |
|------|------------------|-----------|---------------|
| ruff F841 production | 15 (medium-risk) | 11 (剩 P2-2 high-risk) | **0** (P2-2 留档评审) |
| ruff F841 tests | 33 | 33 | **0** (P2-4 cleanup) |
| ruff F401 backend | ~32 | ~32 | **0** (P2-5 顺手) |
| mutation coverage | 0% | 10/11 (90.9%) | **11/11 (100%)** (P2-3) |
| `__all__` 契约 | 13 已有 + 10 缺失 | 同左 | **23/23 三档语义清晰** (P2-5) |
| security-cockpit 决策 | 未评估 | 未评估 | **A 冻结留档待用户拍板** (P2-6) |

## v0.5.0 (2026-08-23)

### 数据底座 — llm-wiki-2.0 (M3.5)

- `llm-wiki-2.0/` 5 子目录 + `retention.json` + `graph.json`：md 为知识真源，
  SQLite 退化为运营层/索引缓存（SPEC §18 存储哲学反转）
- `wiki_archiver.py`：30 天前非收藏条目自动归档 md（frontmatter 完整 + atomic 写）
- `retention_engine.py`：Ebbinghaus 衰减 `current = initial * 0.9^(days/7)`，
  access 重置、<0.3 标 stale、周 job 扫描
- **Task13 graph.json 6 边运行时填入**：concept_linker 按条目概念共现累积
  `uses` 边（weight + source_observation_count），保留人工/LLM 标注的
  depends/contradicts/caused/fixed/supersedes 边；`scripts/check_graph_schema.py`
  与 `scripts/check_retention_decay.py` 进 CI
- **Task14 一次性迁移**：`scripts/migrate_v04_to_llm_wiki.py` 迁移 4149 items +
  96 concepts（实际磁盘数，spec 预估 4152/98），补 `confidence: 0.5` +
  `retention` frontmatter，种子 retention.json + graph.json；v0.4 `knowledge/`
  双轨保留

### LLM 单出口 — ai_hub (M5)

- **Task19 合并双出口**：`llm_service.py` + `ai_service.py` 单 PR 合并为
  `backend/services/ai_hub.py`（LLMService 回退链 + AIService 凭据/限频/缓存/
  评价 + `evaluate_article` + `write_score` + 知识写回门面）；旧两文件删除，
  `grep 'from llm_service|from ai_service'` = 0
- `ai_scores` 写路径唯一入口 `ai_hub.write_score()`（T1 审计 + MCP score_item
  全部经此）；`docs/llm_config.md` 更新单出口说明
- 存量修复：`knowledge.py` 移除 `mastered→mastery` 死代码转换（原会把 mastery 清零）

### 工程

- 版本 0.5.0：`backend/version.py` + `frontend/package.json` 同步
- CI 新增 graph schema / retention 健康两项检查
- 测试基线：后端 2662 collected（≥2573，skipped 不增）

## v0.4.3 (2026-08-18)

### 重构 — Core/Extension 软分层

- 新增 `backend/config/feature_gates.toml`: 扩展层单一开关源 (codegarden/mcp/sync/tech_stack/security_graph)
- 新增 `backend/core/routers.py`: 43 个 core router 白名单, 永远注册, 防漂移断言 (与扩展域无重叠)
- 新增 `backend/extensions/__init__.py`: 扩展注册表 + 门控读取 (env `HOTSPOT_FEATURE_GATES` 可覆盖, 读取失败保守回退全开)
- `backend/api/__init__.py`: 扩展 router 按 flag 注册, codegarden/mcp 关闭时 `/api/codegarden` `/api/mcp` → 404
- `backend/scheduler/scheduler.py`: `_is_job_enabled()` 门控, 7 个 job 按扩展归属过滤 (sync/cg_*/mitre/cve)
- 前端: `useFeatureFlags` + `extensions.ts`, App.tsx 路由按 flag 条件渲染, 导航/设置卡片同步隐藏
- 新增 `GET /api/settings/features` 端点 (前端 flag 数据源)

### 新增 4 个复利驱动器

- 即时分类: `collect_all_job` 尾部 `_classify_new_items()` — 采集完 5 分钟窗口内新 items 立即分类 (md 真相源先回写)
- SM-2 每日推送: 08:00 cron `sm2_daily_push_job` → SSE `review_due` 事件, 前端 Header 徽标
- 地图每日重建: 02:00 cron `map_rebuild_daily_job` → 全量重建 `_MAP.md` + graph.json
- 注意力→复习自动转化: dwell>30s 的深度阅读事件自动创建 SM-2 条目 (create_review 幂等)

### 工程质量

- 版本统一: backend/frontend/README 三处 0.4.3 (基线 tag v0.4.3-base)
- 新增 `scripts/generate_meta.py`: AST 反推架构数字 (43 jobs/14 collectors/51 routers/81 services), `--check` 纳入 CI
- 新增 `backend/tests/test_feature_gates.py`: 60 用例组合矩阵 (core-only/all-on/mixed)
- 新增 `backend/tests/test_compound_drivers.py`: 7 用例覆盖 4 个复利驱动器 + 异常隔离
- 修复: `_classify_new_items` 改用 `upsert_item` 模式 (原 `update_item` 不存在, 分类静默失败)
- CI 新增 `backend-core-only` job (env 全关启动 + gate 测试)
- CI 修复 (v0.4.3 发布前置, 历史 CI 长期为红): requirements.lock mcp 2.0→1.28.1 (fastapi-mcp 0.4.0 兼容), fastapi-mcp pin <0.5, frontend @types/node 显式声明 + npm install, 4 处测试消除对本地 .env/真实 hotspot.db/上级 node_modules 的隐式依赖; 2026-08-19 三个 job 首次全绿
- 测试环境默认全开 feature gates (conftest autouse), 3 处 migration 标注扩展表归属

## v0.3.0 (2026-08-01)

### 新增功能 (Phase 8-14)

#### Phase 8: 复利基础设施
- 数据模型: 4 张新表 (content_fingerprints, ai_scores, item_entities, knowledge_links)
- 资讯收藏聚合视图: 5 数据源合并+去重+分页
- AI 评分 MCP tool: score_item

#### Phase 10: T1/T2 触发器
- 5 阶段 KL 状态机引擎 (raw→refine→link→structure→publish)
- T1 触发器: raw→refine (60s)
- T2 触发器: refine→link (120s)
- 死信队列 + 重试策略

#### Phase 11: 抓取层现代化
- BackendSession 统一代理注入
- 6 新 collector: HN, Reddit, OpenBB, Telegram, GDELT, OSS Insight
- 可读 ID 格式 {source}:{subtype}:{native_id}

#### Phase 12: T3/T4/T5 触发器 + 告警系统
- T3 触发器: link→structure (600s)
- T4 触发器: structure→publish (1800s)
- T5 回滚: publish→refine
- 3 类告警规则: tech_stack 影响, 关键 CVE (CVSS≥9.0), 标讯命中

#### Phase 13: 复利可视化 + 4 模式 + 规划引导
- KnowledgeCompoundingDashboard 仪表盘
- 4 认知模式 UI: 简报/扫描/深度/告警
- KnowledgePlanningPanel 规划引导

#### Phase 14: 子系统联动
- Tech Stack Drift 评估
- CVE 双向同步 (Knowledge ↔ Security)
- 跨域 entity 命名空间统一

#### Phase 15: AI 混合推理
- LLMService 统一接口 (OpenAI/Anthropic/本地)
- Crawl4AI 解析器集成
- Hybrid AI 降级策略 (AI → 规则 → 空)

#### Phase 16: Hybrid AI 完整
- T1 评分延迟降低 ≥60% (AI 缓存命中率 ≥30%)
- T3 摘要生成延迟降低 ≥40%
- 代理健康检查 + 自动切换

#### Phase 17: Chunks + Attention
- knowledge_chunks 表 (paragraph 级) + FTS5 全文搜索
- 5 维度注意力评分 (view/dwell/scroll/favorite/annotation)
- 30×24 注意力热力图
- 6 认知模式完整 (简报/扫描/深度/告警/整理/复习)

### 破坏性变更
- kv_cache 表删除 → digest 已读状态迁移到 digests.last_read_at
- MCP 工具从 13 减少到 9 (移除 4 个低频工具)
- 底层 REST API 端点保留不变

### 详细变更

各 Phase 详细变更日志见对应 spec 目录:
- Phase 7 (MCP): `.trae/specs/phase7-mcp-server/`
- Phase 8 (复利基础设施): `.trae/specs/phase8-compounding/`
- Phase 9 (抓取标准化): `.trae/specs/phase9-crawl-standardize/`
- Phase 10 (T1/T2 触发器): `.trae/specs/phase10-t1t2-triggers/`
- Phase 11-17 (v1.7): `.trae/specs/phase17-chunks-attention/` 及对应 spec 目录
## v0.4.0 (2026-08-16) — 审计重构 Phase 0-6 全部落地

> 依据 docs/audit_first_principles_plan.md 的第一性原理审计与批判性审计,
> 修复全部发现的断裂/死代码/安全缺口, 版本 0.3.0 → 0.4.0。

### 知识闭环数据流 (P1)
- KL 状态落真相源: md 写入 lifecycle, full_sync 不再抹除 kl:* 状态; 回填 4,117 个既有 md
- T4 触发器修复 content 列崩溃 + 评分 fallback → kl:publish 死锁解除
- 生命周期统一为 KL 五阶段 (sag/extract/compiler 改写 kl:* 值)
- knowledge_watcher 改单文件增量同步 (不再全目录重扫)
- 新增 knowledge_classify_job (每 30min 500 条规则分类)

### 采集管道 (P2)
- run_one_source 真单源化 (collect 支持 only_source 过滤)
- run_one/run_one_source 与 run_once 统一并发锁
- 去重窗口改滚动 7 天; 指纹入库后补写 (FK 失效修复)
- catchup since 窗口透传生效; unreachable 加入复检候选
- 门禁语义对齐 (hard 仅 strict 拒绝; 崩溃 fail-closed)
- 接线 6 个未注册 collector (HN/Reddit/Telegram/OSSInsight/GDELT/OpenBB)
- 稳定 ID (可读前缀+URL 哈希); upsert 不再刷新 ingested_at; 富化摘要复检

### 内化/输出闭环 (P3)
- 注意力事件自动创建 SM-2 复习记录; DeepReadMode 埋点 view/dwell/scroll
- ItemDetailDialog 标注 UI; 内容草稿生成 job (kl:publish/高注意力 → drafts)
- 复利仪表盘改读真实数据 + 挂载到 /knowledge/compound

### 同步与安全 (P4)
- bundle 构建失败即中止 (表缺失=空, 真失败=raise 防误删)
- secrets merge 排除密文字段; 冲突裁决生效; sm2 due_at 晚者胜
- rotate_master_key 主密钥轮换; Playbook 危险命令黑名单
- 备份纳入 knowledge/ 源文件 + restore 流程; MCP 路径穿越校验

### 导航与操作流 (P5)
- 死组件清理 (Sidebar/TopBar); Header "更多"菜单 (知识/Skill/密钥/同步)
- ErrorBoundary 挂载; 主题状态统一; 收藏→知识库单步导入
- 数据源健康汇总; ReviewMode 空态引导

### 兼容性
- 后端 2288+ → 2,400+ 测试全绿; 前端 292 测试全绿
- 数据库迁移无需新增 (全部修复为代码层)

### v0.4.0 收尾 (2026-08-16 补)

#### Chunk + FTS5 全文检索落地 (此前 0 行)
- `chunk_service` 段落切分生成器 (char_start/end 原文定位, 超长段落句切)
- `knowledge_chunk_generation_job` 每 30min 处理 200 条
- 迁移 061: FTS5 trigram 表 → 中文子串检索 (unicode61 不切 CJK)
- 搜索端点路由: CJK≥3字→trigram / ASCII→unicode61 / 短查询→LIKE
- 存量回填: 258 个有正文条目全部生成 chunks

#### Security ↔ Knowledge 实体统一命名空间 (PRD A.3.2)
- `security_enrichment_job` 重构为持续回填 (去掉 24h 限制 + 空结果打标)
- 富化实体写入 `item_entities` 桥接表 (此前 0 行, 全库无写入方)
- `security_entity_concept_sync_job`: item 实体→security_entities + 高频
  实体→knowledge concept 互引 (external_id/external_ref)
- 实测: 34 桥接关联 / 28 CVE 入 security 库 / 2 高频概念互引
