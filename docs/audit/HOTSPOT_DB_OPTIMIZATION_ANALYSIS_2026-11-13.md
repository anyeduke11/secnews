# hotspot.db 优化方案 v2 — 以「零停机 + 可重建」替代「体积压缩」

> **日期**: 2026-11-13（v2 修订）
> **类型**: 架构级优化方案（第一性原理重排）
> **v1**: 同日同文件 `HOTSPOT_DB_OPTIMIZATION_ANALYSIS_2026-11-13.md`（核心论据已被实测推翻，勘误见 §0.2）
> **关联**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`](../v0.8.8/V0.8.8_REFACTOR_PRD.md) §4.17 R-17 / [`docs/audit/DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md`](DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md)
> **目标**: 更健壮、更轻量地将「资讯」转为「知识」，将「知识 wiki」转为「人机可执行的养料」。**文件字节数不是验收对象。**

---

## 0. 修订说明

### 0.1 v2 相对 v1 的根本变化

| 维度 | v1 | v2 |
|---|---|---|
| 最大优化对象 | FTS 索引 34.41 MB（判为分词器固有成本） | **FTS 索引碎片 30.74 MB（删行遗留）** |
| 首推手段 | 去掉 summary 索引（牺牲召回换空间） | **重建 FTS（零能力损失）** |
| 对 `auto_vacuum=0` / `journal_size_limit=-1` | 视为「SQLite 固有约束」 | **识别为两个可修的配置缺陷** |
| 对 `llm_cache` | 「TTL 衰减待核」 | **只删 TTL 过期行**（v2 误判为废弃表，勘误见 §0.3） |
| 对 `fts_rebuild_job` | 未发现 | **发现其每 5 分钟重建的是 0 行死表** |
| 验收指标 | `hotspot.db ≤ 120 MB` | **零停机 / 碎片率 / 过期行 / 可重建率 / 召回不降级** |
| 兜底基线 | 无 | **「只修缺陷不改架构」基线 = −36 MB，且已足够接近目标** |

### 0.2 v1 勘误（保留记录，避免重复踩坑）

| # | v1 论断 | 实测事实 | 证据 |
|---|---|---|---|
| E1 | FTS 34.41 MB 是「分词器固有成本，非数据冗余」 | **89% 是删行碎片**：同库重建 34.64 → **3.90 MB**（同 6,548 行 / 同 81,797 词元） | 副本库 drop+recreate 实测 |
| E2 | 稳态膨胀 14.8x | 稳态 **1.5x** | 3.90 / 2.57 MB 源文本 |
| E3 | 去 summary 可省 32.8 MB | 重建已回收 30.7 MB；去 summary 仅再省 **≤3.4 MB**，且静默降召回 | 同上 |
| E4 | `chunk_service._search_fts` 是 `hotspots_fts` 消费点 | 它查 `knowledge_chunks_fts_cjk`，与 hotspots 无关；且仓库**早有 trigram 中文索引先例** | 源码 L165 |
| E5 | `kl_transition` 账可由 md 重建 | **不可重建**：23,244 行 / 11,964 path = **1.94 行/path** 的多步时序；md 只有最终 lifecycle | 实测分布 |
| E6 | `sink` 账可由 md 重建 | **不可重建**：sink 的 `ts` 是归档时刻，md 记录无此字段 | 实测样例 |
| E7 | `llm_cache` TTL「待核」 | ~~废弃表~~ → **勘误见 §0.3**：活跃缓存表，17,315/18,100 行已过期 | 全仓 grep + `ai_hub/cache.py` |
| E8 | 「P0+P1 → ~90 MB」 | 算术应为 105.3 MB（差 15.3 MB） | 加总核对 |

### 0.3 v2.1 自我勘误（本方案自身的错误，实施时发现）

| # | v2 论断 | 实测事实 | 证据 |
|---|---|---|---|
| **S1** | `llm_cache` 是「废弃表」，全仓零运行时引用，可直接 `DELETE FROM llm_cache` 清空 | **错误**。它是 ai_hub 的**活跃缓存表**：`backend/services/ai_hub/cache.py` 定义读写，`gateway.py` 有 5 处调用（score / classify / ner 等）。此前的 grep 排除了 migrations 但漏了 `ai_hub/` 包内的引用。**正确处置 = 只删 TTL 过期行**（周期兜底清扫冷 key），绝不整表清空/删表 | `ai_hub/cache.py` L1-60 + `gateway.py` 调用点 |
| **S2** | （同上衍生）「清了不损失能力」 | **会损失**：清空即让全部缓存命中归零，AI 打分/分类链在下一次调用前退化为全量上游请求 | 同上 |

**影响**: P0-2 从「清空废弃表（−5.30 MB）」改为「TTL 过期行清扫（实测 −17,315 行）」。体积收益在实施后确认，**不再作为独立收益项**计入；能力侧的「不打断 AI 调用链」优先。

---

## 1. 第一性原理：重新定义「轻量」与「健壮」

### 1.1 「重量」有三个量纲，MB 是最不重要的那个

| 量纲 | 定义 | 当前痛点 |
|---|---|---|
| **维护窗口** | 需停服才能完成的运维动作 | **大**：VACUUM 与 WAL 截断都必须停服 |
| **失败面** | 新增代码路径 / 目录 / 冷热路由数量 | 中 |
| **认知负担** | 「一个事实在哪、丢了怎么恢复」的可答性 | 中 |
| 文件字节 | `hotspot.db` 大小 | 163.6 MB |

**判据**：一个 **163 MB 但零停机、可自愈** 的库，比一个 90 MB 但每次维护要停服、且同一事实分散在四处 md 的库更「轻」。

v1 的方案主体（账下沉 / 原文外移 / 反查改道）**恶化了前两项去换第四项**，与目标相反。

### 1.2 数据库的不可替代职责只有三件

事务原子性、按 key/时间索引查询、并发写安全。据此判定每一块的正确处置：

| 对象 | 需事务 | 需索引 | 需并发写 | 正确处置 |
|---|---|---|---|---|
| `hotspots_fts` | 否 | **是** | 否 | **留 DB**；但必须**可在线重建**（碎片治理） |
| `admission_log` 原文 | 否 | 否 | 否 | 可外移，**但绝不进 `llm-wiki-2.0/`**（wiki 只放知识） |
| `wiki_events` 账 | 是 | 是 | 是 | **先定性「证据 or 索引」，技术方案不能替代定性** |
| `llm_cache` | 否 | 否 | 否 | **纯派生 → 周期性清扫过期行**（活跃表，不可删表） |
| `v1_materials` | 是 | 是 | 是 | **留**，去重收益 3 MB 不值得改写入路径 |

### 1.3 「证据」与「索引」必须先定性

v1 的 B1 方案隐含「账能由对象重建，所以账可删」——这是**循环论证**：若账能由对象重建，账就不是独立证据；既然是证据，删后重建出来的是伪证。

- **定性 A（账是索引）** → md 文件本身即证据，DB 账可删，反查扫 md（45.8 MB grep 约百毫秒，完全可接受；v1「无法直接扫 md」的说法过强）
- **定性 B（账是证据）** → 承担审计义务，**不应为省 10 MB 而删**，体积必须为它让路

**这是 owner 决策，不是技术选择。**

---

## 2. 实测基线（校正后）

### 2.1 体积分布（`dbstat`，2026-11-13）

| 对象 | 体积 | 性质 | 可回收？ |
|---|---|---|---|
| `hotspots_fts_data` | **34.41 MB** | **碎片**（稳态 3.90 MB） | ✅ **−30.74 MB** |
| `admission_log` | 20.71 MB | 元数据 340 B/行 + 原文 762 B/行 | 需裁决 |
| `wiki_events` + 3 索引 | 19.84 MB | 账 + 运行流 | 需定性 |
| `hotspots` | 6.67 MB | 养料（30 天窗） | 否 |
| `v1_materials` | 6.57 MB | 养料引用层 | 否 |
| `v1_signals` | 5.61 MB | 养料 | 否 |
| `llm_usage_log` | 5.62 MB | 日志（30 天已截） | 否 |
| **`llm_cache`** | **5.30 MB** | **活跃缓存（17,315 行已过期）** | ✅ **只删过期行**（实测 −17,315 行） |
| `v1_evidence_receipts` | 4.59 MB | 养料 | 否 |
| `security_edges` + 索引 | 5.81 MB | 工作集 | 否 |
| `job_runs` | 3.27 MB | 日志（20k 环截） | 否 |
| `ai_scores` + 索引 | 4.79 MB | 打分（30 天窗） | 否 |
| 其余 | ~30 MB | 台账 / 审计 / 图谱索引等 | 否 |
| **合计** | **163.6 MB** | — | **可回收 36.04 MB** |

### 2.2 配置现状（两个缺陷）

| PRAGMA | 当前值 | 后果 | 应为 |
|---|---|---|---|
| `auto_vacuum` | **0 (NONE)** | 删行后空间永不回收 → **必须停服 VACUUM**（v1「阻碍 5」的真实根因） | `2 (INCREMENTAL)` + 周期 `incremental_vacuum` |
| `journal_size_limit` | **-1（无限制）** | WAL 可涨到 ≈ 库体积（实测 210 MB） | `33554432`（32 MB） |

### 2.3 死代码现状（两个）

| 对象 | 事实 | 处置 |
|---|---|---|
| `fts_rebuild_job`（`maintenance.py:502`，v1.8 R3 起挂在采集尾部链而非独立定时） | `INSERT INTO unified_fts(unified_fts) VALUES('rebuild')`，而 **`unified_fts` 实测 0 行 / 0.02 MB** | **整函数移除（C2.6-P0d 已实施）**。`wiki_items_fts` 自愈是**另一个独立 job**（`wiki_items_fts_sync_job`），不受影响；碎片治理由 `scripts/rebuild_fts_index.py` 承接 |
| `llm_cache`（migration 052 建表） | **活跃缓存表**：`ai_hub/cache.py` 定义，`gateway.py` 5 处消费；18,100 行中 17,315 行已过期 | 只删 TTL 过期行（周期兜底），**不删表不清空**（勘误 §0.3） |

---

## 3. 方案（按第一性原理重排）

### P0 — 治本、零耦合、零能力损失（预计 −36.04 MB，实测可验证）

#### P0-1 FTS 碎片回收（−30.74 MB）★ 最高优先

**为什么**：`contentless` FTS5 的 `DELETE` 只打墓碑不回收页 → C2.3b 删 37,317 行后索引留 34.64 MB 死页。`content=''` 表**不支持** `INSERT INTO t(t) VALUES('rebuild')`（无 content 表可读），只能 drop + recreate + 显式重灌（`scripts/backfill_hotspots_fts.py` 头部已记录此约束）。

**做法**：
1. 新建 `scripts/rebuild_fts_index.py --defrag`
   - `DROP TABLE hotspots_fts` → 按现 DDL 重建（**保留 `title + summary` 两列，`tokenize='unicode61'`**）→ 从 `hotspots` 按 rowid 全量重灌
   - 默认 `--dry-run`，`--apply` 才执行；输出前后体积与行数核对
2. 触发条件（三条，任一命中）
   - `delete_sunk_hotspots` 单次删除 > 1,000 行后
   - 碎片率 `fts_data 实际 / 重建基线 > 1.5`（健康检查 job 计算）
   - 每周兜底一次
3. 与 `rebuild_hot_index.py --from-cold` 串联：重建热层后必跑一次 defrag

**实测证据**：副本库同一数据 34.64 → 3.90 MB，行数与词元数不变（无召回损失）。

#### P0-2 `llm_cache` TTL 过期行清扫（实测 −17,315 行）

- **不是**「废弃表清空」：`llm_cache` 是 ai_hub 活跃缓存（`gateway.py` 5 处消费），清空会打断 AI 调用链（勘误 §0.3）
- `DELETE FROM llm_cache WHERE datetime(cached_at, '+' || ttl_seconds || ' seconds') < datetime('now')`
- 加入 `cleanup_log_tables.py` 的清理清单（幂等，第二轮删 0 行）
- ⚠️ 判定必须用 `datetime(...)` 同格式文本比较；用 `strftime('%s', ...)` 会因 TEXT/INTEGER 隐式转换把全部行误判过期（实测 18,100 vs 17,315）

**这是补读路径的惰性清理缺口**：`get_llm_cache` 只在缓存被再次读到时删单条过期行，冷 key 永久滞留（实测 95.7% 行已过期）。

#### P0-3 两个配置缺陷修正（健壮性，非体积）

```sql
-- 一次性（需重启生效）
PRAGMA auto_vacuum = 2;        -- INCREMENTAL
VACUUM;                         -- 使设置生效（一次性停服窗口）

-- 常驻连接即生效（在 db.get_connection 的 PRAGMA 段追加）
PRAGMA journal_size_limit = 33554432;   -- WAL 上限 32 MB，checkpoint 后自动截断
```

- 之后回收空间改为在线：`PRAGMA incremental_vacuum(N)`（不重写全库、不长时间独占）
- `cleanup_log_tables.py` 的 `VACUUM` 调用改为 `incremental_vacuum`，**消除停服需求**

**收益**：v1「阻碍 5」的根因（空间回收=停服）被消除；C2.2 已修的「VACUUM 后 WAL 残留 200 MB」从「靠补 checkpoint」变为「靠 32 MB 上限兜底」。

#### P0-4 死代码纠正（无体积收益，但消除误导）

- `maintenance.py:502` 移除对 0 行 `unified_fts` 的 rebuild 语句（该 job 每 5 分钟白跑一次）
- 保留同 job 的 `wiki_items_fts` 失同步自愈逻辑
- 把「FTS 重建」这个语义正确接到 P0-1 的 defrag 上

**P0 合计：163.6 → 约 127.6 MB**，且：
- ✅ summary 检索能力不变
- ✅ 无新增 md 目录 / 冷热路由
- ✅ 维护窗口从「每次回收都要停服」降为 0（仅一次性 auto_vacuum 切换）

> 注：127.6 MB 已接近 v1 的 120 MB 目标，且**不牺牲任何能力**。这构成后续任何复杂方案的必选基线——复杂方案必须证明在 127.6 MB 之上还能额外带来什么，且代价可接受。

### P1 — 需 owner 定性（非技术选择）

#### P1-1 `wiki_events` 定性（影响 19.84 MB 含索引）

| 定性 | 处置 | 前置 |
|---|---|---|
| **A. 账是索引** | 删 sink / kl_transition 账；反查改扫 `feed/` + `items/` md（45.8 MB，百毫秒级）；仅留运行流 | 需实现 md 反查（小脚本，非架构改造） |
| **B. 账是证据** | **不动**；体积目标为它让路，`hotspots.db ≤ 120 MB` 目标正式作废 | 无 |

**必须先定性再动手。** v1 直接给了「下沉方案」但未解决这个定性问题。

#### P1-2 `admission_log`（影响 20.71 MB）

三个可选路径（可叠加）：

| 选项 | 收益 | 代价 |
|---|---|---|
| a. 行数上限 15,000 → 5,000 | 约 **−13.5 MB**（一行常量改动） | 缩短 quarantine 审计窗口（需 owner 认可） |
| b. 原文外移到 `data/quarantine/{yyyy-mm}/{hash}.md`（**不入 wiki**） | 约 **−11 MB** | 读取方需按需读 md |
| c. 保持现状 | 0 | 20.71 MB 常驻 |

**v1 的一个架构错误必须纠正**：把被准入拒绝的原料写进 `llm-wiki-2.0/` 会破坏「wiki = 可信知识库」契约——任何基于 wiki 全量的编译 / 索引 / agent 读取都会把垃圾原料当知识消费。正确位置是与 wiki 物理隔离的 `data/quarantine/`（gitignored）。

### P2 — 建议不做（已评估，收益不成立）

| 方案 | 不做的理由 |
|---|---|
| FTS 去 summary 索引 | 重建后仅再省 ≤3.4 MB，且 `MATCH` 无列过滤（`search_service` / `hotspot_repo` 均为裸 `MATCH`）→ **静默降低召回**，属不可接受的退化 |
| 分词器换 trigram | 重建后 3.9 MB 已足够小，无收益证据。仓库已有 `knowledge_chunks_fts_cjk` trigram 先例，但那是因为 chunk 正文长（需要中文部分匹配），hotspots 摘要场景不适用 |
| `v1_materials` 去重 | −3 MB，需改写入路径与引用语义，耦合高于收益 |
| 备份链恢复 | 违反 R-17 裁决（备份语义 = 可重建） |

---

## 4. 验收指标（替换 MB 代理指标）

MB 是代理指标，会诱导错误优化（v1 即典型案例）。改用五个二值指标：

| # | 指标 | 判据 | 测法 |
|---|---|---|---|
| **M1** | 零停机空间回收 | 回收空间**不需要停服** | 删除 1 万行后跑 `incremental_vacuum`，期间 `/api/health` 持续 200 |
| **M2** | FTS 碎片率 | `fts_data 实际 / 重建基线 ≤ 1.2` | 健康检查 job 计算并落 `job_runs.meta` |
| **M3** | 过期缓存行 | `llm_cache` TTL 过期行数 = 0（表与新鲜行保留） | SQL |
| **M4** | 可重建率 | 每张非养料表都能回答「丢了怎么恢复」 | `retention.json` 增加 `recovery` 字段，逐表填写 |
| **M5** | 召回不降级 | summary 关键词检索回归用例通过 | 新增 `test_hotspots_fts_recall.py`（关键词命中 summary 的样本） |

**体积**降为观测项（记录但不做门禁）：P0 后预期 163.6 → ~127.6 MB。

---

## 5. 裁决请求（收窄为 2 项）

| # | 裁决项 | 选项 | 影响 |
|---|---|---|---|
| **1** | `wiki_events` 是**索引**还是**证据** | A. 索引（可删，反查改扫 md）· B. 证据（保留，体积目标作废） | 决定 19.84 MB 能否动、R-17-A2 目标存废 |
| **2** | `admission_log` 保留策略 | A. 上限降到 5,000 行 · B. 原文外移到 `data/quarantine/` · C. 两者都做 · D. 现状 | 决定 20.71 MB 的处置 |

~~v1 的 3 项裁决~~中的「FTS summary 索引」**已撤销**——P0-1 重建后无必要牺牲召回。

---

## 6. 实施顺序（每阶段独立 commit + 副本库实测 + 生产首跑复核）

| 阶段 | 内容 | 前置 | 门禁 |
|---|---|---|---|
| **C2.6-P0a** | `scripts/rebuild_fts_index.py --defrag` + 碎片率健康检查 | 无 | 副本库实测 34.64 → 3.90 MB；召回用例全绿；`--dry-run` 默认 |
| **C2.6-P0b** | `llm_cache` TTL 过期行清扫 + 纳入 `cleanup_log_tables.py` | 无 | 幂等（第二轮删 0 行）；新鲜行与表保留 |
| **C2.6-P0c** | `auto_vacuum=INCREMENTAL` + `journal_size_limit=32MB` + `cleanup_log_tables.py` 改 `incremental_vacuum` | 无 | M1 零停机验证；WAL 不再超 32 MB |
| **C2.6-P0d** | 移除 `fts_rebuild_job`（连函数体，非仅语句） | 无 | **已实施**：jobs 数不变（56）；`wiki_items_fts_sync_job` 独立存在且自愈仍工作；调度域 44 passed |
| **C2.6-P1** | 按 §5 裁决结果实施 wiki_events / admission_log | **owner 裁决** | 逐项验收 |
| **C2.6-P2** | `retention.json` 增 `recovery` 字段（M4 落地） | P0 完成 | 双向差集 0 |

P0 四项互相独立，可并行开发、串行提交。P0 完成后重测体积与 M1~M5，再决定是否需要 P1。

**执行纪律**（沿用 DEV-0349）：F-1 时间锚定（测试禁用绝对日期）· F-2 生产首跑复核（破坏性阶段必须生产 dry-run + 首跑核验）· F-3 目标预演（体积/性能目标先跑只读预演，不匹配提前修正）。

---

## 附录：实测证据与复现命令

```bash
# 1) FTS 碎片：同库重建前后对比（v1 核心论据被推翻）
cp backend/hotspot.db /tmp/f.db
python - <<'PY'
import sqlite3
c=sqlite3.connect('/tmp/f.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
sz=lambda: (c.execute("SELECT SUM(pgsize) FROM dbstat WHERE name LIKE 'hotspots_fts%'").fetchone()[0])/1048576
print('before', round(sz(),2))
c.execute("DROP TABLE hotspots_fts")
c.execute("CREATE VIRTUAL TABLE hotspots_fts USING fts5(id UNINDEXED,title,summary,content='',tokenize='unicode61')")
c.executemany("INSERT INTO hotspots_fts(rowid,id,title,summary) VALUES (?,?,?,?)",
              c.execute("SELECT rowid,id,title,IFNULL(summary,'') FROM hotspots").fetchall())
c.commit(); print('after', round(sz(),2))
PY

# 2) 配置缺陷
sqlite3 backend/hotspot.db "PRAGMA auto_vacuum; PRAGMA journal_size_limit;"   # 0 / -1 → 0 / 33554432 (P0-3a 已实施)

# 3) 活跃缓存表 (勘误 §0.3: 不是废弃表)
grep -rn "llm_cache" --include=*.py backend/ | grep -v migrations   # >0: ai_hub/cache.py + gateway.py 消费点
sqlite3 backend/hotspot.db \
  "SELECT COUNT(*), SUM(datetime(cached_at,'+'||ttl_seconds||' seconds') < datetime('now')) FROM llm_cache;"  # 18100 / 17315

# 4) 死 job
sqlite3 backend/hotspot.db "SELECT COUNT(*) FROM unified_fts;"      # 0

# 5) 账不可由 md 重建
sqlite3 backend/hotspot.db "SELECT COUNT(*), COUNT(DISTINCT wiki_path) FROM wiki_events WHERE kind='kl_transition';"  # 23244 / 11964

# 6) MATCH 无列过滤（去 summary 会静默降召回）
grep -n "hotspots_fts MATCH" backend/services/search_service.py backend/repository/hotspot_repo.py
```
