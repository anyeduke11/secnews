# 数据架构热冷分层设计（v0.8.8 R-17）

> **文档类型**: 设计规格（**本轮不改运行代码**，仅设计 + PRD 落账）
> **版本**: v0.8.8-design.1
> **日期**: 2026-11-11
> **依据**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`](../v0.8.8/V0.8.8_REFACTOR_PRD.md)（唯一权威 spec）§4 新增 R-17 / §6.3 数据兼容性 / §8.1 阶段划分
> **owner 裁决（本轮 AskUserQuestion）**:
> 1. 备份语义 = 「**可重建**」而非「可拷贝」→ 取消 DB 二进制备份链，冷数据落 `llm-wiki-2.0/`
> 2. 排期 = **先出设计文档，P2 消融跑完再动代码**（避免污染消融观测）
> 3. 「热」的口径 = **纯时间窗：热点留 30 天**
> 4. 落地层级 = **先写设计 + PRD，改造实施下一轮**

---

## 0. 一句话结论

把当前「一个 355 MB 大库 + 449 MB 备份 + 一套从未落地的四层台账」收敛为
**「一个 ≤120 MB 热库（30 天窗口）+ 一个 wiki 冷层（`llm-wiki-2.0/`，真源）+ 零备份作业」**，
数据流动靠**单向热→冷沉降 + 单向冷→热重建**两条管道，中间用 `wiki_events` + `retention.json` 做可核验的账。

---

## 1. 现状事实基线（实测，非估算）

### 1.1 体积分布（`backend/hotspot.db`，361,697,280 B ≈ 345 MB；WAL 96 MB）

| 排名 | 表 / 索引 | 体积 | 行数 | 性质判定 |
|---|---|---|---|---|
| 1 | `admission_log` | **91.2 MB** | 68,646 | 追加日志（`raw_material_json` avg 776 B） |
| 2 | `hotspots` | 39.4 MB | 43,307 | 业务实体（**真源在 DB**，md 无对应物） |
| 3 | `job_runs` | 34.8 MB | 192,801 | 追加日志（执行流水） |
| 4 | `hotspots_fts_data` | 24.6 MB | 43,288 | FTS5 投影（随 `hotspots` 等量） |
| 5 | `idx_job_runs_job_type_at` | 12.2 MB | — | 索引 |
| 6 | `llm_usage_log` | 9.6 MB | 48,808 | 追加日志 |
| 7 | `idx_job_runs_status_at` | 9.3 MB | — | 索引 |
| 8 | `idx_job_runs_trace` | 8.6 MB | — | 索引 |
| 9 | `v1_materials` | 6.4 MB | 7,323 | 证据链（行动页直读） |
| 10 | `v1_signals` | 5.5 MB | 7,322 | 证据链（资讯页 SignalPanel 直读） |
| 11 | `v1_evidence_receipts` | 5.2 MB | 14,824 | 幂等回执（无前端读路径） |
| 12 | `llm_cache` | 5.1 MB | 16,748 | 可重建缓存 |
| 13 | `idx_admission_log_created` | 4.8 MB | — | 索引 |
| 14 | `wiki_events` | 4.5 MB | 29,787 | md↔DB 桥接日志 |
| 15 | `ai_scores` | 4.1 MB | 35,045 | 派生投影 |

**派生结论**：
- `job_runs` 表体 34.8 MB + 其 3 个索引 **30.1 MB** = 64.9 MB，索引占表体 87% —— 纯为 `/api/ops/runs` 三个查询建的索引撑起近 30 MB。
- `admission_log` 单表 + 索引 = **96 MB**，占全库 **27%**。
- `job_runs` + `admission_log` + `llm_usage_log` + `wiki_events` + `ai_scores` = **144 MB**，全部是「只写不改、只按时间查」的流水/投影，**零业务真源价值**。
- `PRAGMA auto_vacuum = 0`（关闭）→ 删除后空间不回收，必须 `VACUUM` 或改 `auto_vacuum=INCREMENTAL`。
- `PRAGMA freelist_count` 在写入期非零 → 已有碎片。

### 1.2 时间分布（决定时间窗效果的硬数字）

| 表 | 总行数 | 30 天内 | 90 天内 | 判定 |
|---|---|---|---|---|
| `hotspots` | 43,307 | **6,644（15%）** | 42,729（99%） | 30 天窗可砍 85% ✅ |
| `admission_log` | 68,646 | 51,550（**75%**） | 68,646（100%） | 30 天窗只砍 25% ❌ |
| `job_runs` | 192,801 | 192,777（**99.8%**） | 192,801（100%） | 30 天窗**几乎无效** ❌ |
| `wiki_events` | 29,787 | 6,107（20%） | 29,787（100%） | 30 天窗可砍 80% ✅ |
| `ai_scores` | 35,045 | 25,929（74%） | 35,045（100%） | 30 天窗只砍 26% ❌ |

> **⚠️ 关键约束（设计中必须正面处理，不能用「30 天窗」一句话糊过去）**：
> `job_runs` 与 `admission_log` 是**高频追加**表，30 天内的量就接近全量。
> 对这两张表，**时间窗压不下体积**，必须走**行数上限 / 环形截断（ring buffer）**，而非时间窗。
> owner 裁决的「纯时间窗：热点留 30 天」严格适用于 `hotspots`（真源类实体）；日志类必须另设机制。
> 本设计据此把「热窗口」拆为**两种口径**（见 §3），并在 §5 给出日志类的独立机制。

### 1.3 既有设计资产（可复用，不必重造）

| 资产 | 位置 | 现状 | 复用判断 |
|---|---|---|---|
| `retention.json` 台账 | `scripts/retention.json` | 声明 104 表 × HOT/WARM/COLD/FROZEN 四层 + 各自 backup 策略 | **纸面设计**：warm/cold 库文件不存在；70 活表不在台账；35 台账表在 main 不存在 → **重写为两层** |
| `wiki_archiver` | `backend/services/wiki_archiver.py` | 30 天 + 非收藏 → 写 md；**但不删 DB 行**（`:12-14` 明示） | **核心骨架复用**，补「删行 + 事务 + 校验」三段 |
| `knowledge_watcher` | `backend/services/knowledge_watcher.py` | md → DB 增量同步（1 s 防抖）+ 每日全量投影重建 | **冷→热重建管道复用** |
| `wiki_events` | `backend/repository/migrations/065_wiki_events.sql` | 29,787 行，md↔DB 桥接留痕 | **保留并扩语义**为沉降/重建账 |
| `retention.json` (wiki 侧) | `llm-wiki-2.0/retention.json` | 4,149 条 Ebbinghaus 衰减条目 | **保留**（这是记忆衰减模型，不是分层台账，两者同名不同义，**命名必须解耦**） |
| `graph.json` | `llm-wiki-2.0/graph.json` | nodes/edges 概念图 | 不动 |
| `llm-wiki-2.0/` | 磁盘 | 5.6 MB 真实字节（items 4776 md / concepts 165 / learning 2199 / content 286） | 冷层落点 |

### 1.4 备份链现状（待删除对象清单）

| 对象 | 位置 | 说明 |
|---|---|---|
| `backup_service.py` | `backend/services/backup_service.py`（1,048 行） | `backup_database` 全量快照 / `backup_incremental` 自研 WAL 帧差分 / `compact_backup_chain` roll-forward / `restore_from_*` |
| `backup_verify_service.py` | `backend/services/backup_verify_service.py` | 完整性校验 + 行数单调性 |
| `daily_db_backup_job` | `backend/scheduler/scheduler.py:602-608`（04:30 每日） | → `backup_incremental()` |
| `weekly_maintenance_job` 链尾 | `backend/scheduler/jobs/maintenance.py:411` `_force_full_backup_rotate` | 周日 04:00 强制全量 |
| `backup_verify_job` | `backend/scheduler/scheduler.py:611-618`（周一 02:00） | 校验最新备份 |
| 3 个 API 端点 | `backend/api/maintenance_retention_api.py:15/58/68` | `/backup-verify` `/backups` `/backups/compact` |
| 产物 | `backend/backups/` = **449 MB** | 8 档 WAL 增量 + 全量快照 + 14 份 manifest |
| 远端推送 | `backup_service.py:113` `_maybe_remote_push` | WebDAV，默认关 |
| 脚本 | `scripts/check_backup_chain.py` / `scripts/t02_backup_drill.py` | 备份链巡检 + 演练 |
| 测试 | `backend/tests/test_backup_service.py` / `test_backup_verify.py` / `test_backup_compact.py` / `test_c01_wal_backup_and_wikifs_isolation.py` | 4 个测试文件 |

**空间收益**：删除 449 MB 备份产物 + 停止 3 个 job + 删 1,048 + 8 KB 服务代码 + 4 个测试文件。

---

## 2. 硬冲突与裁决记录

### 冲突 A：取消备份 = 冷数据单点

`llm-wiki-2.0/` 被 `.gitignore:69` 排除，且 2026-08-30 已用 `filter-repo` 从 git 历史移除（决策记录见 `.gitignore:64-66`：含明文 API key）。因此若直接「取消全部备份」，冷数据将只剩本地单副本。

**owner 裁决**：「备份改为『可重建』而非『可拷贝』」。

**本设计的落地方式**（把风险从「不可恢复」转为「可重建」）：

| 保障手段 | 内容 | 成本 |
|---|---|---|
| **真源前置** | `hotspots`（真源在 DB）必须先有 md 落盘通道，DB 才允许删行 → DB 丢失后可从 md 全量重建热索引 | 见 §4 管道 A |
| **重建脚本** | `scripts/rebuild_hot_index.py`：从 `llm-wiki-2.0/` 扫 md → 重建 `hotspots` 表 + FTS + `hotspot_tags` | 新增 1 脚本 |
| **重建验收门** | T4 架构门新增一项：删库 → 重建 → `hotspots` 行数与 md 数一致（容差 0） | CI 加 1 step |
| **单副本的剩余风险** | 磁盘硬件故障仍不可恢复 | **显式接受**：owner 已裁决；缓解手段是 §8 的「待定项 D1」建议用户自行做 Time Machine / 异盘同步（**不在本项目代码内**） |

> **本设计明确不解决**：磁盘硬件故障导致 `llm-wiki-2.0/` 全失。
> 该风险已被 owner 裁决接受，本文档负责让该风险**可见、可核验**，而非隐藏。

### 冲突 B：P2 消融占用工作树

P2 消融（20 对象 × 约 23 min）正在当前工作树运行，改 `db.py` / `services/` / `scheduler` 会污染全部后续观测。

**owner 裁决**：本轮只出设计与 PRD，**不动任何运行代码**；P2 跑完后再实施。

**本轮实际改动清单**（全部为文档，零代码）：
- 新增 `docs/audit/DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md`（本文）
- `docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`：新增 §4.17 R-17 + §3.1 S-12 + §6.3 补 §6.3.1 + §8.1 P2.5 行 + 附录 A.5
- `DEV_LOG.md`：追加 `[DEV-0337]` 条目

---

## 3. 目标分层模型

### 3.1 两层 + 一个账（不是四层）

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOT  —  backend/hotspot.db（SQLite，单文件，目标 ≤120 MB）        │
│  职责：热查询 / 索引投影 / 幂等去重键 / 短周期计数                  │
│  ──────────────────────────────────────────────────────────────── │
│  · hotspots            30 天窗（owner 裁决：纯时间窗）              │
│  · hotspot_tags        随 hotspots 同窗                            │
│  · hotspots_fts        随 hotspots 同窗（contentless FTS5）        │
│  · v1_signals/cases/…  永久留（行动页直读 = 热）                    │
│  · job_runs/admission_log/llm_usage_log   环形截断（见 §5）        │
└─────────────────────────────────────────────────────────────────────┘
              ▲ 管道 A：沉降（hot → cold，写 md 后删行）
              │ 管道 B：重建（cold → hot，扫 md 回填索引）
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  COLD —  llm-wiki-2.0/（md 真源，5.6 MB → 目标 60-80 MB）         │
│  items/{id}.md      知识条目（已存在，4776）                        │
│  feed/{yyyy-mm}.md  ★ 新增：资讯归档（hotspots 冷数据）            │
│  concepts/ graph.json retention.json                               │
└─────────────────────────────────────────────────────────────────────┘
              ▲
┌─────────────────────────────────────────────────────────────────────┐
│  LEDGER（账）— wiki_events + scripts/retention.json（两层台账）    │
│  记录「哪一行何时沉降到哪个 md、哪一行被重建回来」                  │
└─────────────────────────────────────────────────────────────────────┘
```

**与既有四层台账的关系**：`scripts/retention.json` 声明的 HOT/WARM/COLD/FROZEN 四层 → 收敛为 **HOT(DB) / COLD(wiki) 两层**，删掉 WARM（warm.db 从未存在）与 FROZEN（与 COLD 语义重复）。台账从 104 表裁到**实际存在的活表**。

### 3.2 「热」的两口径（因 §1.2 实测数据而分）

| 类别 | 表 | 口径 | 理由 |
|---|---|---|---|
| **真源实体** | `hotspots` / `hotspot_tags` / `hotspots_fts` | **时间窗 30 天**（owner 裁决） | 30 天覆盖 6,644 行（15%），砍 85% 体积；且 md 侧保留全量历史，查询历史走冷层 |
| **热必留** | `v1_signals` / `v1_cases` / `v1_materials` / `v1_judgments` / `v1_actions` / `v1_proposals` / `v1_outbox` / `favorites` / `settings` / `tags` | **永久留 DB** | 行动页/资讯页**直读**；`favorites` 9 行含 `hotspot_id` 逻辑外键（无 CASCADE，刻意保留历史） |
| **日志 / 投影** | `job_runs` / `admission_log` / `llm_usage_log` / `wiki_events` / `ai_scores` / `llm_cache` / `api_events` / `process_events` / `audit_log` | **环形截断 + TTL**（见 §5） | 零业务真源价值；30 天窗对 `job_runs` 无效（99.8% 在窗内） |
| **wiki 投影** | `knowledge_items` / `knowledge_chunks` / `wiki_items_fts` | **随 md 投影重建** | `main.knowledge_items` 实测 **0 行**；真源早已是 md，DB 侧只是投影（`wiki_archiver.py:12-14`） |

---

## 4. 数据流动机制（核心设计）

### 4.1 管道 A：沉降（hot → cold）

**触发**：每日 job `hot_to_cold_sink_job`（复用现有 `wiki_archiver_job` 的调度位 `scheduler.py:369-377`，避免新增 job 计数）

**流程**（每批 ≤500 条，与 `wiki_archiver.py:241` 的 limit 一致）：

> **实施状态（p2.5.1）**：**只写阶段（C2.3a）已落地**——步骤 1/2/3/5 已实现于 `services/wiki_archiver.py::sink_hotspots_to_feed()`（`_atomic_write_text` 原子写 + 读回校验 + `kind='sink'` 记账），**步骤 4（删行）未开启**，待 C2.4 重建管道通过 T4 后以 C2.3b 开启（RA-14）。选批口径与下方 SQL 的差异：实现用 `COALESCE(ingested_at, fetched_at)` 兜空值，并加 `NOT EXISTS(wiki_events kind='sink')` 排除已记账行（保证重跑幂等、已沉批次不再选）。

**冷层记录契约（`feed/{yyyy-mm}.md`，实现即此格式）**：

```
---
doc: feed
schema: 1
month: 2026-08
records: 1234
updated_at: 2026-11-11T...
---

<!--hsc:{"v":1,"id":"...","title":"...","summary":"...","source":"...","url":"...",...,"tags":[...],"tag_links":[{"tag_id":"...","label":"...","confidence":0.9}]}-->
<!--hsc:{...}-->
```

- 每行一条记录，`<!--hsc:{json}-->` 包裹 JSON（sort_keys + ensure_ascii=False），JSON 内**逐列保真**携带 `hotspots` 20 列 + `tags` + `tag_links`；坏行解析时跳过并计入 errors。
- 按月聚合，追加写（先读现有记录 → 按 id 去重 → 原子重写整文件）。

```
1. 选批    SELECT * FROM hotspots
           WHERE COALESCE(ingested_at, fetched_at) < now-30d
             AND id NOT IN (SELECT hotspot_id FROM favorites)   ← 收藏永不下沉
             AND NOT EXISTS (wiki_events kind='sink' ...)       ← 已沉批次不再选
           ORDER BY ... LIMIT 500
2. 写 md   原子写 llm-wiki-2.0/feed/{yyyy-mm}.md（append 段，非覆盖）
           前置校验：目标 md 已含该 id → 跳过（幂等）
3. 校验    重新读回 md，确认 id 存在（失败 → 计入 errors，本批中止，fail-loud）
4. 删行    DELETE FROM hotspots WHERE id = ?      ← C2.3b，T4 通过后才开启
           ↓ 同时处理 FK 级联与 FTS
5. 记账    wiki_events(kind='sink', wiki_path='feed/xxx.md', db_table='hotspots', db_row_id=id)
```

**关键实现约束（来自实测，不是假设）**：

| 约束 | 依据 | 处理 |
|---|---|---|
| `hotspots_fts` 是 **contentless FTS5**（`content=''`） | `migrations/003_github_category.sql:53-59` | DELETE/UPDATE 被禁 → **必须走触发器**。`hotspots_ad` 已由 `migrations/078_fix_hotspots_fts_delete_triggers.sql:14-17` 修好为**带旧值**删除（`VALUES('delete', old.rowid, old.title, IFNULL(old.summary,''))`），故**普通 `DELETE FROM hotspots` 即自动同步 FTS**，不需手写 FTS 语句。⚠️ 但 078 的注释明确记录：**只给 rowid 不给旧值会「不报错但词条静默残留」→ 搜索假阳性** → 实施时**严禁手写不带旧值的 FTS delete**，也严禁改这两个触发器 |
| `hotspots_fts` 的 `summary` 存的是 `IFNULL(summary,'')` | 同上 | 触发器在 NULL 时存空串；重建索引时必须用**同样的 `IFNULL` 语义**，否则 FTS 内容与源表不一致（重建验收须比对 FTS 命中数） |
| `hotspots_trigram_fts` 惰性触发器 | `secnews_dashboard.py:121` `_FEED_TRIGRAM_TRIGGER_SQL`（运行时 DDL） | 随 `hotspots` 删除自动走触发器；但触发器在 5 万行阈值后才建 → 需显式核对（V1） |
| `hotspot_tags` 级联删 | `migrations/024.sql:16` `ON DELETE CASCADE` | 随 `hotspots` 自动删，**但需确认**：无 tag 的热点会连带丢失分类标签，而 `ai_scores` 的 `hotspot_id` **FK 已被剥离**（`migrations/132_ai_scores_drop_fk.sql:1-11`）→ 删热点后 `ai_scores` 变悬空引用，**必须同步删 `ai_scores` 行**（否则 `ai_scores` 同样成为死存储） |
| `favorites` 无 CASCADE | `migrations/006.sql:13-14` 注释（刻意保留历史） | 收藏永不沉降；`favorites.hotspot_id` 指向的热点**必须保留在 DB**，否则收藏变孤儿 |
| `v1_materials` / `v1_signals` 无 CASCADE | `migrations/096.sql:65-66` | `v1_signals` 永久留；`v1_materials` 若无引用可沉降至 `feed/`，但**需先确认无 signal 引用** |
| `hotspots` 正文列 | `summary` / `quality_flags` | md 落盘需完整携带（否则冷层不可重建热索引） |

### 4.2 管道 B：重建（cold → hot）

**触发**：两种场景
- **恢复场景**：DB 丢失/损坏后，人工执行 `python scripts/rebuild_hot_index.py --from-cold`
- **常态场景**：新增 `rebuild_hot_index.py --sync` 增量模式（与既有 `wiki_projection_rebuild_job` 同调度位，30 min 一次）

**流程**：
```
1. 扫冷层  hotspots 只从 feed/*.md 重建（逐行 <!--hsc:{json}--> 记录）
           items/*.md 仅用于重建 knowledge_items（不可用于 hotspots，见下）
2. 回填    UPSERT hotspots / hotspot_tags（`knowledge_items` 不在本脚本范围，由既有 wiki 链路负责）
3. 索引    hotspots_fts 由 migration 078 触发器随行 DML 自动同步（**不手写 FTS DML、不 REINDEX**）
4. 对账    md 条数 vs DB 行数 → 差异入 wiki_events(kind='rebuild_diff')
```

**依赖前提**：`feed/{yyyy-mm}.md` 必须携带足够信息重建 `hotspots` 行（`title` / `url` / `summary` / `category` / `published_at` / `ingested_at` / `score` / `quality_score` / `tags`）。**这是 §4.1 管道 A 的 schema 约束，必须在实现时严格遵守**。

> **实测补充（p2.5.1）**：`llm-wiki-2.0/items/*.md` 的 frontmatter **缺 `category` / `published_at`**，且 `hotspot_repo.upsert_many` 仅覆盖 16 列（未含 `tags` / `last_read_at` / `lifecycle` / `pick_score` / `quality_*`）→ **items 无法独立重建 `hotspots`**。故 `hotspots` 的唯一冷层来源是 `feed/*.md` 的 `<!--hsc:{json}-->` 全列记录（这是把 C2.3a 提到 C2.4 之前的原因）。

**实施状态（p2.5.2，已交付）**：

| 项 | 落地事实 |
|---|---|
| 脚本 | `scripts/rebuild_hot_index.py`；CLI = `--from-cold`（默认，覆盖同 id 行）/ `--sync`（`INSERT OR IGNORE`，仅补缺）/ `--db` / `--wiki-root` / `--dry-run` / `--allow-partial` / `--json` |
| 写入面 | 自持 **20 列** UPSERT（不复用 `hotspot_repo.upsert_many` 的 16 列，避免丢 `tags` / `last_read_at` / `lifecycle` / `pick_score` / `quality_*`） |
| FTS | **不手写 FTS DML、不 REINDEX** —— 由 migration 078 的 `hotspots_ai/au/ad` 触发器随普通 `INSERT/UPDATE/DELETE FROM hotspots` 自动同步；T4 中「删热层后 `hotspots_fts` 归零」即触发器健康证明 |
| tag 边界 | `hotspot_tags` 仅回填 `tags` 表中**已存在**的 `tag_id`（冷层未持久化 `tags.type`，凭空建 `tags` 行会伪造概念图）；缺失计入 `skipped_tag_links` 并影响退出码 |
| 对账 | 冷层记录数 vs `hotspots` 行数 vs `hotspots_fts` 行数；差异写 `wiki_events(kind='rebuild_diff')`，`diff_total > 0` 时 exit 1（`--allow-partial` 可放行） |
| T4 实测 | 生产库副本（未触碰生产）：`hotspots` 43,442 → 沉降 36,855（4 个月文件，dup 0）→ 删热层（`hotspots=0` / `fts=0`）→ 重建 36,855 = 冷层 36,855（**容差 0**）；FTS 36,855 一致、`MATCH 'security'` 253 命中、`hotspot_tags` 回填 34,423、`rebuild_diff` 事件 0、脚本 exit 0 |
| CI 门禁 | `backend/tests/test_rebuild_hot_index.py`（隔离库内 sink → 删 → 子进程跑真实脚本 → 行/FTS/tag/对账四路断言） |

### 4.3 两管道的可核验性

| 方向 | 核验手段 | 失败处理 |
|---|---|---|
| hot → cold | `wiki_events(kind='sink')` 计数 vs 实际删除行数 | 计数不等 → 报警，不继续 |
| cold → hot | `rebuild_diff` 事件 + md/DB 条数对账 | 差异 → 报警 |
| 端到端 | T4 门禁：删库 → 重建 → 行数一致 | CI 阻断 |

### 4.4 读路径的冷热路由（前端无感）

前端**不感知**冷热分层，路由在 service 层：

| 查询 | 路由 | 现状是否已满足 |
|---|---|---|
| `/api/hotspots`（feed 首页） | 热层（30 天内足够） | ✅ 已满足（`_MAX_LIMIT=200`，`ORDER BY ingested_at DESC`） |
| `/api/hotspots` 翻页到 30 天前 | **需冷层兜底** | ❌ 需新增：`hotspot_service` 查热层不足时 → 读 `feed/*.md` |
| `/api/favorites` | 热层（收藏永不下沉） | ✅ 已满足 |
| `/api/v1/signals` | 热层（永久留） | ✅ 已满足 |
| `/api/knowledge/items` | 投影（`main.knowledge_items` 已 0 行 → 实际走 warm 投影） | ⚠️ 需确认 `knowledge_items_table()` 在 warm.db 不存在时的回落路径 |
| `/api/knowledge/search` | 冷层 grep（`federation_service.py:318` 遍历 items/*.md） | ✅ 已是冷层路由 |

> **风险点标注**：`hotspots` 沉降至 md 后，`/api/hotspots` 的历史翻页会少数据。
> `hotspot_repo.py` 的 `_MAX_LIMIT=200` 钳制意味着单页最多 200 条，前端默认按 `ingested_at DESC` 拉取。
> **30 天窗下 feed 首页 6,644 条 ÷ 每页 100 = 66 页**，日常使用**不会触及** 30 天边界。
> 故翻页越界是低频场景 → 冷层兜底可作为 P2.5 之后的增量项，首版可不实现（但必须在 PRD 标注为已知限制）。

---

## 5. 日志类表的环形截断（补 §1.2 的洞）

`job_runs`（192,801 行 / 64.9 MB 含索引）30 天窗无效。改用**双阈值环形截断**：

| 表 | 阈值 | 截断动作 | 预期收益 |
|---|---|---|---|
| `job_runs` | 行数 > **20,000** 或 存续 > 14 天 | 删最旧行 + **同时删 3 个索引对应行** | 64.9 MB → **约 8 MB**（表体 3.6 + 索引 3.4） |
| `admission_log` | 行数 > **15,000** | 删最旧行 + `idx_admission_log_created` | 96 MB → **约 22 MB** |
| `llm_usage_log` | 存续 > 30 天 | 删最旧行 | 9.6 MB → 约 6 MB |
| `wiki_events` | 行数 > **8,000** | 删最旧行（**保留全部 `sink`/`rebuild` 类事件**） | 4.5 MB → 约 1.5 MB |
| `ai_scores` | 随 `hotspots` 同窗 | 删对应行（FK 已剥离，须显式删） | 4.1 MB → 约 1.2 MB |
| `llm_cache` | TTL 已有 | 不动 | 5.1 MB |

**`job_runs` 索引瘦身**：3 个索引占 30.1 MB。环截后行数降至 20k，索引体积按比例降至约 3.1 MB。
**进一步可做**（P2.5 可选）：`idx_job_runs_trace`（8.6 MB）服务的 `trace` 查询若无前端入口可考虑移除 —— 需先核验消费点。

**`job_runs` 截断的语义风险**：`/api/ops/runs`（设置页 OpsRunsPanel）是其唯一前端消费点。环截后历史执行记录消失 —— 这是**明确的功能取舍**，属「日志类数据不承诺长期留存」的口径，需在 PRD 写明。

---

## 6. 备份链退役清单（R-17 的一部分）

### 6.1 删除（物理移除）

| 类 | 对象 | 校验方式 |
|---|---|---|
| 服务 | `backend/services/backup_service.py`（1,048 行） | 文件消失 + `grep backup_service` 0 命中 |
| 服务 | `backend/services/backup_verify_service.py` | 同上 |
| job | `daily_db_backup_job`（`scheduler.py:602-608`） | `scheduler.py` 无该 id |
| job | `backup_verify_job`（`scheduler.py:611-618`） | 同上 |
| job 链尾 | `_force_full_backup_rotate`（`jobs/maintenance.py:411`） | 文件内无该函数 |
| API | `/backup-verify` `/backups` `/backups/compact`（`maintenance_retention_api.py:15/58/68`） | 端点 404 |
| 脚本 | `scripts/check_backup_chain.py` / `scripts/t02_backup_drill.py` | 文件消失 |
| 测试 | `test_backup_service.py` / `test_backup_verify.py` / `test_backup_compact.py` / `test_c01_wal_backup_and_wikifs_isolation.py` | 文件消失 |
| 产物 | `backend/backups/`（**449 MB**） | 目录消失 |
| 远端 | `_maybe_remote_push`（`backup_service.py:113`） | 文件随服务删除 |

### 6.2 改造（不是删除）

| 对象 | 动作 |
|---|---|
| `weekly_maintenance_job`（周日 04:00） | 保留 job 本身（内有 `db_diet` dry-run 等），**仅摘掉链尾 `_force_full_backup_rotate`** |
| `scripts/db_diet.py` | 保留（承担 VACUUM / orphan / duplicate 清理），**删 `make_backup_snapshot`**（`db_diet.py:82`），保留 `vacuum_into`（`:102`） |
| `backend/api/maintenance.py` docstring | 同步删备份链端点描述 |
| `backend/config/` 备份相关配置 | `BACKUP_RETENTION` / `SIDE_DB_RETENTION` / `MANIFEST_KEEP` / `INCREMENTAL_KEEP` / `KNOWLEDGE_INC_KEEP` / `MAX_INCREMENTAL_PAGES` / `HOTSPOT_REMOTE_BACKUP` 一并清理 |

### 6.3 替代物（保证「可重建」）

| 新增 | 位置 | 作用 |
|---|---|---|
| `rebuild_hot_index.py` | `scripts/` | 从 `llm-wiki-2.0/` 重建 `hotspots` + FTS + `hotspot_tags`（§4.2） |
| 冷层 schema 契约 | `llm-wiki-2.0/schema/SCHEMA.md` 追加 `feed/` 段 | 约束 `feed/{yyyy-mm}.md` frontmatter 必含字段（§4.1 管道 A 的 schema 约束） |
| T4 门禁增量 | `.github/workflows/ci.yml` | 「删库 → 重建 → 行数一致」1 step |

---

## 7. 空间账（目标值）

| 项 | 现状 | 目标 | 手段 |
|---|---|---|---|
| `hotspot.db` | 345 MB（+WAL 96 MB） | **≤120 MB** | 热点 30 天窗（−34 MB）+ 日志环截（−130 MB）+ `ai_scores` 随删（−3 MB） |
| `backend/backups/` | 449 MB | **0** | 备份链退役 |
| `llm-wiki-2.0/` | 5.6 MB | **60–80 MB** | 接收 36,663 条热点冷数据（按 avg 1.2 KB/条估算） |
| `hotspot-warm.db` / `hotspot-cold.db` | 不存在 | **保持不存在** | 台账两层化后不再声明 |
| **DB + 备份合计** | **794 MB** | **≤120 MB（−85%）** | — |
| **含冷层总占用** | 799.6 MB | **180–200 MB（−75%）** | — |

**WAL 96 MB 问题**：`db.py:212` `wal_autocheckpoint=1000`（约 4 MB 阈值）本应自动回收，实测 WAL 96 MB → 说明存在长事务或 checkpoint 被阻塞。
**排查方向**（P2.5 实施时定位）：`backend/core/events.py` 的 SSE 长连接 + `knowledge_watcher` 的持续写入可能持有读事务。
**建议**：P2.5 顺带加 `PRAGMA wal_checkpoint(TRUNCATE)` 到每日维护 job，并确认无长期读事务。

---

## 8. 待定项（需 owner 二次确认，本轮不阻塞）

| 编号 | 待定 | 选项 | 影响 |
|---|---|---|---|
| D1 | 磁盘故障的单副本风险 | 接受 / 建议用户自建 Time Machine | 接受则本设计完整闭环 |
| D2 | `hotspots` 冷数据 md 粒度 | ① 一条一 md（4,766 → 40,000+ 文件，目录膨胀）② **按月聚合 md（推荐，本设计采用）** ③ JSONL | 决定 `feed/` 目录结构 |
| D3 | 收藏的热点是否允许下沉 | 本设计：**永不下沉**（保 `favorites.hotspot_id` 有效） | 若允许，需引入 md 侧收藏索引 |
| D4 | `job_runs` 环截阈值 | 本设计：20,000 行 / 14 天 | 直接决定设置页 OpsRunsPanel 的历史可见范围 |
| D5 | `/api/hotspots` 历史翻页越界 | 首版不实现冷层兜底（标注限制）/ P2.5 后补 | 影响 feed 深度浏览体验 |

---

## 9. 实施顺序（p2.5.1 二次裁决后，按序执行）

| 阶段 | 内容 | 前置门 |
|---|---|---|
| **P2.5-3a** | 冷层 `feed/` 目录 + 管道 A **只写阶段**（不删行） | T2 全绿 ✅ → 已交付（`sink_hotspots_to_feed` + 6 测试） |
| **P2.5-4** | 管道 B 重建脚本（§4.2）+ T4 门禁增量（§6.3） | ✅ **已交付**：`scripts/rebuild_hot_index.py` + `test_rebuild_hot_index.py`；T4 实测 36,855 冷层记录 → 重建 36,855 行（容差 0）、FTS 一致、对账差异 0 |
| **P2.5-1** | 备份链退役（§6.1 + §6.2） | P2.5-4 通过（重建能力已就位，RA-14） + `grep backup` 0 残留 |
| **P2.5-2** | 日志环截（§5） | T2 全绿 + 体积实测下降 |
| **P2.5-3b** | 管道 A **删行阶段**开启 | P2.5-4 的 T4 全绿 + 备份链已退役 |
| **P2.5-5** | `retention.json` 台账两层化重写 | `generate_meta --check` 通过 + 台账与实际表一致 |

> **顺序修订说明**：原稿把 P2.5-4 排在 P2.5-1 之前（RA-14），但 P2.5-4 的输入 `feed/*.md` 由 P2.5-3 产出 → 「删库 → 重建 → 行数一致」在 3 落地前无真实数据可验。故 3 拆为 **3a 只写 / 3b 删行**，3a 提到最前；「重建先于备份退役」（4 先于 1）与「删行最后」（3b 最后）两条约束同时满足。

**每阶段必须**：单独 commit + T2/T3/T4 全绿 + `DEV_LOG` 记录 + PRD §8.1 P2.5 行更新。

---

## 10. 验收标准（可二值判定）

| 编号 | 标准 | 判定方式 |
|---|---|---|
| R-17-A1 | 备份链彻底退役 | `grep -rn "backup_service\|backup_verify\|daily_db_backup_job" backend/ scripts/` = 0 命中；`backend/backups/` 不存在 |
| R-17-A2 | 磁盘占用达标 | `backend/hotspot.db` ≤ 120 MB；`backend/backups/` = 0 |
| R-17-A3 | 冷层承载完整 | `llm-wiki-2.0/feed/` 中的热点 md 条数 = 已下沉热点总数（`wiki_events kind='sink'` 计数一致） |
| R-17-A4 | 可重建 | 执行 `rebuild_hot_index.py --from-cold` 后，`hotspots` 行数 = 冷层 md 条数（容差 0） |
| R-17-A5 | 收藏不失效 | `favorites` 9 行的 `hotspot_id` 在 `hotspots` 中 100% 存在 |
| R-17-A6 | 热必留未受影响 | `v1_signals` / `v1_cases` / `v1_materials` 行数与实施前一致 |
| R-17-A7 | 行动页不受影响 | `/api/v1/signals` `/api/v1/cases` 200 且返回行数不变 |
| R-17-A8 | 日志类达标 | `job_runs` ≤ 20,000 行；`admission_log` ≤ 15,000 行 |
| R-17-A9 | 台账一致 | `scripts/retention.json` 中每个声明的表在 main 库实际存在，且每个活表在台账内（差集 = 0） |
| R-17-A10 | 架构门绿 | `generate_meta.py --check` + `harness_analyze.py --check` exit 0 |

---

## 附录 A：实测命令与环境

```bash
# 体积与行数（只读）
.venv/bin/python3 -c "
import sqlite3
con=sqlite3.connect('file:backend/hotspot.db?mode=ro',uri=True)
for n,p in con.execute('SELECT name,SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC LIMIT 16'):
    print(n, round(p/1048576,1),'MB')
"
# 时间分布
.venv/bin/python3 -c "
import sqlite3,datetime
con=sqlite3.connect('file:backend/hotspot.db?mode=ro',uri=True)
cut=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat()
print(con.execute('SELECT COUNT(*) FROM hotspots').fetchone())
print(con.execute('SELECT COUNT(*) FROM hotspots WHERE ingested_at>=?',(cut,)).fetchone())
"
```

| 项 | 值 |
|---|---|
| 采集时间 | 2026-11-11 11:40 |
| 采集对象 | `/Users/duke/Documents/hotspot/backend/hotspot.db`（361,697,280 B） |
| 采集方式 | `mode=ro` 只读连接 + `dbstat` 虚表 + `PRAGMA` |
| 采集树状态 | **含未提交改动**（P0/R-13/R-15 工作树）—— 与 P0 基线树不同，**本文件的体积数字是「当前工作树」口径**，实施后须重采 |
| 干扰 | P2 消融在同树运行（pytest 写 `hotspot-test-iso-*` 临时根，不污染主库） |

## 附录 B：待核对项（实施前必须逐条验证，不得凭本文档假设）

| 编号 | 待核对 | 原因 |
|---|---|---|
| V1 | `hotspots_trigram_fts` 删除触发器在 30 天窗下的实际行为 | 触发器为运行时 DDL（`secnews_dashboard.py:121`），5 万行阈值后才建 |
| V2 | `ai_scores` 删除时机与悬空引用处理 | FK 已剥离（migration 132），需确认删除顺序不影响 `ai_scores` 写入路径 |
| V3 | `knowledge_items_table()` 在 warm.db 不存在时的回落 | `db.py:260` + `db.py:626` 自愈逻辑，实测 `main.knowledge_items` = 0 行 |
| V4 | `idx_job_runs_trace` 是否有前端消费点 | 若无，8.6 MB 可直接删 |
| V5 | `federation_service.py:318` md grep 在 feed 数据量下的耗时 | 冷层增至 40k+ md 后搜索延迟 |
| V6 | `db.py` WAL 96 MB 的长事务来源 | 决定 §7 的 WAL 治理方案 |
