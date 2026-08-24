# PORT_SPEC.md — hotspot Python → dsh-SecNews TypeScript 移植对照表

> **目标读者**: dsh-SecNews 仓库开发者 (Phase 0-6)
> **数据基线**: 2026-08-24 hotspot v0.5.0
> **目的**: 给 dsh 仓库一份**精确到文件 + 行数 + 关键函数**的移植清单, 照单实现

## 1. 总量基线 (2026-08-24 实测)

| 子系统 | 文件数 | 行数 | spec 目标 |
|--------|--------|------|----------|
| `backend/repository/` | 35 | 10,136 | `packages/store/src/*` (P0/P1/P2) |
| `backend/services/` | 85 | 25,854 | `packages/{wiki,cap,review,report,enrichment,mcp}/src/*` (P1/P5) |
| `backend/collectors/` | 14 | 6,548 | `packages/collectors/src/providers/*` (P2) |
| `backend/quality/` | 13 | 3,607 | `packages/quality/src/gates/*` (P3) |
| `backend/repository/migrations/*.sql` | 67 | 2,713 | `packages/store/src/migrations/` (P1) |
| `frontend/src/` | 257 tsx | — | `web/src/` (P6) |
| **总计** | ~481 py + 257 tsx | **~48.9K** | — |

> spec 行 9 写 "~25000 行" 是历史快照, 当前实测量约 2 倍 (因 quality/ + migration + collectors 演进)。

## 2. Phase 1 — 存储层移植 (5-7 天)

### 2.1 `backend/repository/db.py` (327 行) → `store/src/schema.ts` + `store/src/index.ts`

**核心内容**:
- `init_db(path)` — SQLite 连接 + WAL + FTS5 注册
- `apply_migrations(conn)` — 顺序 exec 67 个 migrations/*.sql
- `_BACKEND_DIR` / `_MIGRATIONS_DIR` 路径常量
- `get_connection()` 单例

**dsh 端参考**:
- ✅ schema 终态: `data/schema/ddl.sql` (dump_schema.py Phase 7d 输出)
- ✅ schema 演进: `data/migrations/001_init.sql ... 070_kl_pipeline.sql` (export_migrations_for_dsh.py Phase 7e 输出)
- 验收: `node -e "import('@secnews/store')"` 能 init DB; 67 migrations 顺序执行后 schema 与 dump_schema 一致

### 2.2 `backend/repository/hotspot_repo.py` (808 行) → `store/src/hotspot-repo.ts`

**核心类/函数**:
- `HotspotRepo` 类, 主要方法:
  - `insert(item)` / `upsert(item)` — INSERT OR REPLACE
  - `list(filters)` — 多维筛选 (category/source/date range)
  - `search(query)` — FTS5 全文检索 (hotspots_fts)
  - `get(id)` / `get_by_url(url)`
  - `update_quality(id, score, flags)`
  - `count_by_category()` / `count_by_source()`
- `hotspot_row_to_dict(row)` — 行 → dict 转换器

**dsh 端参考**:
- ✅ 行数基线 808 行, 移植后约 600 行 TS (类型注解 + 注释)
- 关键 SQL: `INSERT INTO hotspots (...) VALUES (...) ON CONFLICT(id) DO UPDATE SET ...`
- 验收: 同输入 → 同输出 (与 Python 版对比 100%)

### 2.3 `backend/repository/wiki_event_repo.py` → `store/src/wiki-event-repo.ts` (~150 行)

**核心内容**:
- `WikiEventRepo` 类, `wiki_events` 表 CRUD
- 事件类型枚举: import / advance / refine / publish / archive
- `event_bus.emit(event)` 触发下游

### 2.4 `backend/services/backup_service.py` → `store/src/backup.ts` (~300 行)

**核心内容**:
- `BackupService` 类: SQLite `.backup()` API
- 增量备份 (WAL frame-by-frame)
- 压缩 (gzip) + 校验 (sha256)

### 2.5 `backend/crypto.py` → `store/src/crypto.ts` (~100 行)

**核心内容**:
- Fernet 对称加密 (Python `cryptography` 库)
- key rotation
- base64 编码

**dsh 端**: 用 `crypto.subtle` (Web Crypto API) 实现 AES-GCM, 与 Fernet 兼容或重新设计

### 2.6 Migrations (67 个 .sql)

✅ 已导出到 `data/migrations/` (Phase 7e)
- 命名风格: `NNN_xxx.sql` (NNN 三位序号保证字典序 = 时间序)
- 关键词分布 (2026-08-24 实测):
  - CREATE INDEX: 168
  - CREATE TABLE: 95
  - ALTER TABLE: 50
  - INSERT INTO: 34 (数据迁移)
  - CREATE TRIGGER: 18
  - DROP TABLE: 16 (038, 051 等)
  - UPDATE: 16 (回滚脚本如 046_down)
  - PRAGMA: 4
  - CREATE VIEW: 2
  - DELETE FROM: 1

**dsh 端消费指引** (见 `data/migrations/README.md`):
1. `cp -r hotspot/data/migrations/* dsh/packages/store/src/migrations/`
2. dsh migration runner 沿用 `NNN_xxx.sql` 命名
3. 验证: `diff /tmp/h_schema/ddl.sql /tmp/d_schema.sql` 应一致

## 3. Phase 2 — 采集系统移植 (7-10 天, 14 collector / 6548 行)

| Python 源 | 行数 | TS 目标 | 复杂度 | 备注 |
|----------|------|---------|--------|------|
| `base.py` | 500 | `collectors/src/base.ts` | 中 | 抽象类, HTTP retry/rate-limit |
| `bid_collector.py` | 867 | `providers/bid.ts` | 高 | 多源招标, 需 session |
| `sogou_search.py` | 627 | `providers/sogou.ts` | 高 | 反爬, JS render |
| `security_collector.py` | 326 | `providers/security.ts` | 中 | 多 RSS 源聚合 |
| `hn_collector.py` | 257 | `providers/hackernews.ts` | 低 | HN Algolia API |
| `finance_collector.py` | 256 | `providers/finance.ts` | 中 | 多 RSS |
| `telegram_collector.py` | 204 | `providers/telegram.ts` | 中 | TG API |
| `item_builder.py` | 214 | `parser/item-builder.ts` | 中 | item 字段归一化 |
| `tech_collector.py` | 141 | `providers/tech.ts` | 低 | RSS |
| `ai_security_collector.py` | 86 | `providers/ai-security.ts` | 低 | RSS |
| `startup_collector.py` | 146 | `providers/startup.ts` | 低 | RSS |
| `session.py` | 154 | `internal/session.ts` | 中 | requests.Session 包装 |
| `bid_status.py` | 138 | `internal/bid-status.ts` | 低 | 标讯状态枚举 |
| `id_factory.py` | 53 | `internal/id-factory.ts` | 低 | ulid 生成 |

**dsh 端验收**: 同输入 → 同输出 (Python vs TS 跑 100 条 sample 对比)

## 4. Phase 3 — 质量门禁移植 (5-7 天, 13 gate / 3607 行)

| 门禁 | Python 源 | 行数 | TS 目标 | 关键算法 |
|------|----------|------|---------|---------|
| URL 去重 | `duplicate_gate.py` | — | `gates/duplicate.ts` | URL exact match |
| URL canonical | `url_canonicalize.py` | 61 | `gates/url-canonicalize.ts` | query param sort |
| URL 验证 | `url_validity_gate.py` | 95 | `gates/url-validity.ts` | HEAD request 200 |
| URL 内容 | `url_content_gate.py` | 144 | `gates/url-content.ts` | GET + content hash |
| 最终 URL | `final_url_gate.py` + `final_url_resolver.py` | — | `gates/final-url.ts` | 跳转跟踪 |
| 内容质量 | `content_quality_gate.py` | — | `gates/content-quality.ts` | 长度 + 词数 |
| 作者质量 | `author_verification_gate.py` | 160 | `gates/author.ts` | 白名单 + LLM |
| 时效性 | `recency_gate.py` | 119 | `gates/recency.ts` | published_at vs now |
| 类目匹配 | `category_match_gate.py` | 56 | `gates/category-match.ts` | LLM classify |
| AI 质量 | `ai_quality_gate.py` | 109 | `gates/ai-quality.ts` | LLM score |
| Schema 校验 | `schema_gate.py` | 49 | `gates/schema.ts` | Pydantic → Zod |
| 源覆盖 | `source_coverage.py` | 323 | `gates/source-coverage.ts` | 30 天 rolling |
| **SimHash** | `simhash.py` | **138** | `gates/simhash.ts` | **算法移植, 见 §4.1** |
| 来源信誉 | `source_reputation_gate.py` | 71 | `gates/source-reputation.ts` | 历史准确率 |
| 标讯时效 | `bid_recency_gate.py` | — | `gates/bid-recency.ts` | 招标截止日期 |
| 噪音过滤 | `noise_content_gate.py` | — | `gates/noise.ts` | 关键词黑名单 |
| 评分 | `scorer.py` | 53 | `scoring.ts` | 加权综合 |
| 流水线 | `pipeline.py` | — | `pipeline.ts` | 13 gate 串行 |

### 4.1 SimHash 算法移植 (P3 关键风险点)

**位置**: `backend/quality/simhash.py` (138 行)

**核心算法**:
```python
def simhash(text: str, n_gram: int = 3) -> int:
    """3-gram 分词 + 64-bit hash 加权投票, 返回 int。"""
    tokens = ngrams(jieba.cut(text), n_gram)
    vector = [0] * 64
    for token, weight in tokens_with_weight(tokens):
        h = mmh3.hash(token)
        for i in range(64):
            vector[i] += weight if (h >> i) & 1 else -weight
    return int("".join("1" if v > 0 else "0" for v in vector), 2)
```

**dsh 端实现要点**:
1. 分词: 用 `nodejieba` (npm) 或自实现 3-gram sliding window
2. 哈希: 用 `farmhash` / `xxhash` / `murmurhash3` (npm), 64-bit
3. 向量加权: `[number, number, ...]` (64 元素)
4. 输出: JS bitint 或 string (避免 32-bit overflow)

**验收**: 同样本 → 相同 simhash (Python vs TS 100% 一致)

## 5. Phase 4 — 调度系统移植 (5-7 天, 45 job)

**位置**: `backend/scheduler/jobs.py` (2260 行, 45 个 `@register_job` 函数)

**job 域分类** (按 spec 第 262 行):
- collect (5): collect_all / collect_per_source / catch_up / source_health / scheduler_tick
- quality (4): quality_pipeline / quality_rescore / quality_logs_cleanup / quality_logs_archive
- knowledge (8): wiki_archiver / retention_decay / concept_linker_run / kl_trigger_t1~t4 / kl_dead_letter_replay
- maintenance (6): weekly_maintenance / monthly_archive / index_rebuild / vacuum / backup / fts_rebuild
- report (4): daily_report / weekly_report / monthly_digest / briefing_generate
- enrichment (3): cve_enrich / attack_enrich / compliance_match
- codegarden (4): cg_service_scan / cg_event_process / cg_drift_assess / cg_resource_gc
- sync (3): sync_fernet_keys / sync_external / sync_history_compact
- compile (4): compile_daily / compile_weekly / compile_kl_summary / compile_archive
- review (4): sm2_daily_review / todo_due_check / annotation_cleanup / review_stats

**dsh 端**: 使用 `croner` (npm) 或 dsh `ctx.schedule`, 每个 job 函数 → 对应 Cordis 服务方法

**验收**: 45 job 全部注册 + cron 触发后日志可见

## 6. Phase 5 — AI/知识层 (5-7 天, 关键算法)

### 6.1 `backend/services/ai_hub.py` (931 行) → `cap/src/model-router.ts`

**核心类**:
- `AIHub` — 多 provider 回退链 (OpenAI / Anthropic / DeepSeek / 自部署)
- `ModelRouter` — 按 token cost + latency 分层 (flash / standard / heavy)
- `TokenLedger` — token 用量台账

**dsh 优势**: 用 `ctx.llm` (Cordis harness) 替代自建多 provider 回退链
- `ctx.credentials` 替代自建凭据管理
- `ctx.session` 替代自建 session 管理

### 6.2 `backend/services/wiki_archiver.py` (254 行) → `wiki/src/archiver.ts`

**核心算法**:
- 30 天前非收藏条目自动归档 md (frontmatter 完整 + atomic write)
- 归档后从 SQLite 移除, 但保留 frontmatter 索引

### 6.3 `backend/services/retention_engine.py` (237 行) → `wiki/src/retention.ts`

**核心算法 (Ebbinghaus 衰减)**:
```python
def decay(initial: float, days_since_access: int) -> float:
    """current = initial * 0.9 ^ (days / 7)"""
    return initial * (0.9 ** (days_since_access / 7))

def is_stale(retention: float, threshold: float = 0.3) -> bool:
    return retention < threshold
```

**dsh 端**: TS 实现, `Math.pow(0.9, days / 7)`, 周 job 扫描

### 6.4 `backend/services/concept_linker.py` (473 行) → `wiki/src/concept-linker.ts`

**核心算法**:
- 条目概念共现累积 → `uses` 边 (weight + source_observation_count)
- 6 条核心边: uses / part-of / related-to / contradicts / extends / instance-of
- runtime 填入 `graph.json`

### 6.5 `backend/enrich_v2.py` (80 行) → `enrichment/src/{cve,attack,compliance}.ts`

**核心函数**:
- `extract_cve(text) -> list[str]` — 正则匹配 CVE-YYYY-NNNN
- `extract_attack(text) -> list[str]` — ATT&CK technique ID
- `extract_compliance(text) -> list[str]` — 法规引用
- `extract_deadline(text) -> list[str]` — 截止日期
- `extract_bid_status(text) -> list[str]` — 招标状态

## 7. Phase 6 — 前端迁移 (7-10 天)

**源**: `frontend/src/` (257 tsx 文件)
**目标**: `web/src/components/workbench/` (5 视图)

| 当前 hotspot 组件 | 目标 workbench 视图 | 备注 |
|------------------|-------------------|------|
| `BriefingMode.tsx` | `BriefingView.tsx` | 今日简报 + 扫读队列 |
| `ScanMode.tsx` / `AlertMode.tsx` | `PipelineView.tsx` | KL 管线漏斗 |
| `KnowledgeActionBar.tsx` / `KnowledgeGraph` | `KnowledgeView.tsx` | wiki + 概念图谱 + 复习 |
| (分散) | `AnalyzeView.tsx` | 深度研判 + URL 导入 |
| `QualitySettings.tsx` | `SettingsView.tsx` | 模型路由 + 采集源 |

**API 适配**:
- `web/src/lib/api.ts` 基址: `http://localhost:3210/api/`
- 路由映射: hotspot `/api/data/...` → dsh `/api/v1/dataapi/...`

**废弃**:
- `/data` 三层路由 (DataLayerPage/JudgeLayerPage/ActionLayerPage)
- `EditorialView.tsx`

## 8. 全局验收命令

```bash
# Phase 1 验收
node -e "import('@secnews/store')"  # 能 init DB
diff /tmp/h_schema/ddl.sql /tmp/d_schema.sql  # schema 一致

# Phase 2 验收
pnpm --filter @secnews/collectors test  # 14 collector 单测

# Phase 3 验收
pnpm --filter @secnews/quality test  # 13 gate 单测
python3 -c "
from backend.quality.simhash import simhash
from backend.quality.pipeline import run
ts_simhash = 0x1234...  # 同一文本 TS 输出
assert simhash(sample) == ts_simhash
"

# Phase 4 验收
pnpm --filter @secnews/scheduler test  # 45 job 触发 + 日志可见

# Phase 5 验收
pnpm --filter @secnews/cap test
pnpm --filter @secnews/wiki test  # KL raw→publish 全链路

# Phase 6 验收
cd web && npx tsc --noEmit && npx vitest run && npx vite build

# Phase 7 验收 (D+0/D+1)
# hotspot 侧 (本仓库)
python3 scripts/snapshot_for_retirement.py --verify  # baseline 对账
# dsh 侧
sqlite3 data/secnews.db "SELECT COUNT(*) FROM hotspots"  # == 3391
```

## 9. hotspot 侧已交付的 dsh 消费资产

| 资产 | 路径 | 行/件 | commit |
|------|------|-------|--------|
| 8 表 → JSON | `data/export/` | 8902 行 + 4149 wiki | `b1cd80de` |
| 行数 baseline | `data/retirement_baseline.json` | 42 行 | `94d02c49` |
| 80 表 DDL (4 文件) | `data/schema/` | 80 表 + 21 FK + 3 FTS5 | `40632c98` |
| 67 migrations | `data/migrations/` | 67 个 .sql + manifest + README | (本 commit) |
| 6 步退役脚本 | `scripts/execute_retirement.sh` | 309 行 | `94d02c49` |
| 整合 spec | `docs/HOTSPOT_RETIREMENT.md` | 257 行 | `8ec7db61` + `68234ae6` |
| **本对照表** | **`docs/PORT_SPEC.md`** | **(本文件)** | **(本 commit)** |

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| SimHash 算法 Python/TS 不一致 | 中 | Phase 3 验收用 100 条 sample 字节级对比 |
| KL 管线状态机遗漏 | 高 | 写 characterization test 锁现有行为 |
| 14 collector 反爬逻辑 | 高 | 优先移植 5 个核心, 其余 Python 子进程过渡 |
| migration 演进顺序错乱 | 高 | dsh 沿用 NNN_xxx.sql 命名, 顺序 exec |
| token/cookie 加密 Fernet vs AES-GCM | 中 | 双向互通测试 + 重新加密迁移窗口 |
