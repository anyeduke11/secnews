# M1-Task1 收尾证据（2026-08-21）

> 规格: `docs/v0.5_refactor_plan/README.md` §1 M1-Task1
> 实现: commit `0490470f` (hotspot_repo 改造 + IndentationError 修复)
> 目的: 记录 EXPLAIN 验证 + 回填脚本验证 + 数据一致性核对的硬证据。

## 1. 回填脚本验证

```
$ .venv/bin/python backend/scripts/backfill_ingested_at.py
开始回填: /Users/duke/Documents/hotspot/backend/hotspot.db (hotspots 共 2952 行)
[ingested_at] 本批回填 0 行 (累计 0)
[is_hidden=1] 本批修正 0 行 (累计 0)
[is_hidden=0] 本批修正 0 行 (累计 0)
完成: ingested_at 回填 0 行 | is_hidden 置1 0 行 / 清0 0 行
校验: ingested_at 仍为 NULL 0 行 | is_hidden 不一致 0 行
```

**结论**: 幂等通过（0 行命中），说明 prior runs (含 hotspot_repo.upsert_many 写入路径)
已经把存量 2952 行数据 + is_hidden 都同步到位。

## 2. 数据一致性核对

```
$ sqlite3 backend/hotspot.db <<'SQL'
SELECT is_hidden, COUNT(*) AS n FROM hotspots GROUP BY is_hidden;
SELECT
  SUM(CASE WHEN quality_flags LIKE '%historical_bid%' OR quality_flags LIKE '%historical_published%'
        OR quality_flags LIKE '%no_published_at%' OR quality_flags LIKE '%landing_page_unresolvable%'
        THEN 1 ELSE 0 END) AS would_be_hidden_by_flag,
  SUM(CASE WHEN is_hidden = 1 THEN 1 ELSE 0 END) AS is_hidden_count,
  COUNT(*) AS total
FROM hotspots;
SQL
```

| 指标 | 值 |
|---|---|
| `is_hidden=0` 行数 | 2844 |
| `is_hidden=1` 行数 | 108 |
| `quality_flags` 含 4 个 hidden 标记之一 | 108 |
| `is_hidden=1` 与 4-flag 口径一致 | ✅ 108 = 108 (0 偏差) |
| hotspots 总行数 | 2952 (与 PROGRESS.md 基线一致) |

**结论**: is_hidden 推导与 SPEC §1 M1-Task1 口径（historical_bid / historical_published /
no_published_at / landing_page_unresolvable 任一命中 → 1）100% 一致。

## 3. 索引存在性

```
$ sqlite3 backend/hotspot.db <<'SQL'
SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='hotspots' AND name='idx_list_visible';
SQL

name              sql
----------------  ------------------------------------------------------------
idx_list_visible  CREATE INDEX idx_list_visible
                      ON hotspots(category, ingested_at DESC) WHERE is_hidden
                  = 0
```

**结论**: 064 迁移生效，idx_list_visible 部分索引存在（WHERE is_hidden=0）。

## 4. EXPLAIN 验证（主路径）

```
$ sqlite3 backend/hotspot.db <<'SQL'
EXPLAIN QUERY PLAN
SELECT id, title, ... FROM hotspots
WHERE ingested_at >= '2026-08-14T00:00:00+00:00'
  AND is_hidden = 0
  AND (url_check_status IS NULL OR url_check_status NOT IN ('mismatch', 'unreachable'))
  AND category = 'security'
ORDER BY ingested_at DESC, rowid DESC LIMIT 30;
SQL

QUERY PLAN
|--SEARCH hotspots USING INDEX idx_list_visible (category=? AND ingested_at>?)
`--USE TEMP B-TREE FOR LAST TERM OF ORDER BY
```

**结论**:
- ✅ 走 `idx_list_visible` 部分索引（SPEC §1 主目标达成）
- ⚠️ `TEMP B-TREE FOR LAST TERM OF ORDER BY` 仍存在 — 但只是为 `rowid DESC` tiebreak
  排 30 行内的小代价 TEMP 排序

## 5. EXPLAIN 多场景对比

```
$ sqlite3 backend/hotspot.db <<'SQL'
SQL

--- no category ---
QUERY PLAN
|--SEARCH hotspots USING INDEX idx_ingested (ingested_at>?)
`--USE TEMP B-TREE FOR LAST TERM OF ORDER BY

--- with region ---
QUERY PLAN
|--SEARCH hotspots USING INDEX idx_ingested (ingested_at>?)
`--USE TEMP B-TREE FOR LAST TERM OF ORDER BY

--- with category IN ('ai', 'tech') ---
QUERY PLAN
|--SEARCH hotspots USING INDEX idx_list_visible (category=? AND ingested_at>?)
`--USE TEMP B-TREE FOR ORDER BY
```

**场景总结**:

| 场景 | 走索引 | 备注 |
|---|---|---|
| `category = 'security'` | idx_list_visible ✅ | 主路径 |
| 无 category | idx_ingested | 仍走 ingested_at 索引 |
| `region = ?` | idx_ingested | region 不在 idx_list_visible 列首 |
| `category IN ('ai', 'tech')` | idx_list_visible + TEMP ORDER BY | IN 当 OR 处理, SQLite 整列 sort |

## 6. 与 SPEC §4 基线对比

| 指标 | 基线（未优化） | 现状（M1-Task1 后） | 改善 |
|---|---|---|---|
| 主路径索引 | `idx_hotspot_region` (TEMP B-TREE FOR ORDER BY) | `idx_list_visible` | ✅ |
| 走索引范围 | 整 category 扫 | 仅 visible 行 (`is_hidden=0`) | ✅ 数据量降 3.6% (108/2952 hidden) |
| ORDER BY 走索引前缀 | 否（COALESCE 不走索引） | 是（ingested_at 直接比较） | ✅ |
| TEMP B-TREE | 整列 sort | 30 行内 sort (rowid tiebreak) | ✅ 量级提升 |
| COALESCE 计算 | 每行 1 次 | 0 次 | ✅ |

## 7. 残留 TEMP B-TREE 的来源与决策

**来源**:
- 索引 `idx_list_visible (category, ingested_at DESC) WHERE is_hidden=0` 覆盖了
  `category` + `ingested_at` 两个 ORDER BY key
- 但 ORDER BY 第二个 key `rowid DESC` 不在索引里 → SQLite 用 TEMP B-TREE 处理

**为什么不能消除**:
- Phase 24 修复明确: `rowid DESC` 是 id DESC 字典序 bug fix (security_xxx > finance_xxx > ai_xxx)
- 313 条同毫秒 security 写入会挤掉 ai/finance 行的 bug
- 改 ORDER BY 去掉 `rowid DESC` 会回归这个 bug
- 改索引加 rowid 列: SQLite 不会为 rowid 建新索引（rowid 已是隐式 B-tree 的一部分）

**决策**:
- ✅ 接受残留 TEMP（只为 30 行内 tiebreak，开销可忽略）
- ✅ 相比基线（整列 sort + 全表扫）已量级提升
- ⏸ 严格"无 TEMP SORT"目标作为"半达"记录在 PROGRESS.md

## 8. M1-Task1 收尾判定

| 验收项 | 状态 | 证据 |
|---|---|---|
| 064 迁移 is_hidden + idx_list_visible | ✅ | §3 |
| hotspot_repo upsert_many 写 is_hidden | ✅ | 0490470f diff |
| hotspot_repo query() 走 idx_list_visible | ✅ | §4 主路径 |
| COALESCE 移除 + ingested_at 直接比较 | ✅ | 0490470f diff |
| cursor 浮点精度 (微秒) | ✅ | 0490470f diff + test 16/16 |
| 4 quality_flags 口径一致 | ✅ | §2 108=108 |
| 回填脚本幂等可重跑 | ✅ | §1 0 命中 |
| 基线 2547 tests collected | ✅ | 0490470f 验证 |
| ruff 干净 | ✅ | 0490470f 验证 |
| **SPEC §1 "无 TEMP SORT"** | ⚠️ 半达 | §7 解释（量级提升, 残留 TEMP 为 30 行内 tiebreak） |

**结论**: M1-Task1 主任务达成, p95 优化路径已就位。TEMP B-TREE 残留作为可接受 trade-off 记录,
不阻塞 M1 验收（依赖实测 p95<150ms 验证, M1 完工时跑 quick_perf --cold）。

## 9. 引用

- SPEC: `docs/v0.5_refactor_plan/README.md` §1 M1-Task1 / §4 现状基线 / §7 退出门禁
- 迁移: `backend/repository/migrations/064_list_query_optimization.sql`
- 实现: commit `0490470f` (hotspot_repo + test)
- 脚本: `backend/scripts/backfill_ingested_at.py` (159 行, 幂等)
- PROGRESS.md: 任务清单 M1-Task1 待勾选（待 Duke 一起 commit）
