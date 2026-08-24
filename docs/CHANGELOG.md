# Changelog

## v0.5.0-retired (2026-08-24, Phase 7b 待 dsh 端验收后正式生效)

> **状态**: ⏳ 文档已就绪, 等 dsh 端 secnews.db 行数对账完成后正式生效
> **退役文档**: [`HOTSPOT_RETIREMENT.md`](HOTSPOT_RETIREMENT.md)
> **整合 spec**: `SecNews_dsh_全栈整合_task-d12.md` Phase 7

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

### 工具交叉引用

| 工具 | 行数 | 用途 | commit |
|------|------|------|--------|
| `scripts/export_for_dsh.py` | 375 | 8 表 → JSON 旁路 | b1cd80de |
| `scripts/snapshot_for_retirement.py` | 305 | 行数基线 + verify | 94d02c49 |
| `scripts/dump_schema.py` | 443 | 80 表 DDL → 4 文件 | 40632c98 |
| `scripts/execute_retirement.sh` | 309 | 6 步退役 dry-run/apply | 94d02c49 |
| `data/retirement_baseline.json` | 42 | 2026-08-24 baseline | 94d02c49 |
| `data/schema/` (4 文件) | - | dsh schema.ts 消费 | 40632c98 |

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
