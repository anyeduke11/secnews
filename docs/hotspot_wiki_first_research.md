# Hotspot Wiki-First 改造 — 调研与方案 (P1.1, 下次 batch)

> **状态(2026-09-03)**: 调研完成, 设计落地, 实施**留待下次 batch** (本批 P1 仅做信源管道 8 项)。
> **决策**: 路径 A — Wiki 主写 + DB 派生。
> **参考**: [Zleap-AI/SAG](https://github.com/Zleap-AI/SAG) (single-write-authority + immutable originals + derived indexes)

---

## 1. 现状与冲突

### 1.1 AGENTS.md 声明 (目标态)

> "wiki-first 存储哲学" — .md 文件是真相源, DB 是导出副本。

### 1.2 实际实现 (实态)

| 域 | 主写 | 派生 |
|---|---|---|
| Knowledge items (4194 .md) | **wiki (`.md`)** | DB / FTS / wiki_stats |
| **Hotspots (collection_service)** | **DB (SQLite)** | wiki (零 .md) |

冲突: hotspot 域完全 DB-of-record; 收藏 / 相关推荐 / AI agent 想读 .md 只能从 DB 实时渲染, 拿不到"真相源"。

### 1.3 后果 (任一处可观测)

- DB 写入成功 + wiki 同步失败 → 数据分裂, 需 reconcile
- 收藏 / 标签按 id 关联, 但 wiki 与 DB 可能错位
- FTS 索引 / `wiki_stats` / `related_items` 下游消费者永远在猜"哪个真"
- 其他 AI agent (cursor / 协作 agent) 读 wiki → 拿不到 hotspot 数据

---

## 2. SAG 模式参考

[SAG (Single-writer Authority Graph)](https://github.com/Zleap-AI/SAG) 三原则:

1. **Single-writer authority**: 每个实体只有一个权威写者 (例如 `.md` 文件)
2. **Immutable originals**: 原始文件只追加, 不就地修改
3. **Derived indexes**: DB / FTS / 向量索引都是派生, 可重建

类比现实: 便签纸 (.md) 主写, 电子表格 (DB) 手抄副本。便签纸丢了, 副本就是错的; 但副本丢了, 便签纸还是对的。

---

## 3. 路径 A 设计 (选定)

### 3.1 架构

```
ingest (collection_service)
  │
  ├─[1]──> wiki_fs.write_hotspot()  ──> llm-wiki-2.0/hotspots/{id}.md
  │         (主写, 同步阻塞, retry 3 次)
  │
  ├─[2]──> hotspot_repo.upsert()    ──> SQLite hotspots 表
  │         (派生, 异步, 失败可重试)
  │
  └─[3]──> fts_index.sync()         ──> FTS5 虚拟表
            (派生, 同 [2])

query path (read)
  │
  ├─[A]──> hotspot_repo.fetch()     ──> SQLite (现 90% 入口)
  │         (派生, 低延迟)
  │
  └─[B]──> wiki_fs.read_hotspot()   ──> .md
            (权威, AI agent / 人类读)
```

### 3.2 数据流

| 阶段 | 路径 | 失败语义 |
|---|---|---|
| 主写 | wiki (`.md`) | 失败 → 阻塞主流程 + retry 3 次 (1s/5s/25s 退避) |
| 派生 | DB / FTS | 失败 → 写入 `wiki_sync_backfill` + 告警 |
| Backfill worker | 每 60s 轮询 `wiki_sync_backfill` | 重试失败项 |
| 监控 | `wiki_sync_lag` (md mtime vs DB last sync) | >60s 告警 |

### 3.3 一致性边界

- **最终一致**: 派生层允许短暂落后 (<60s)
- **强一致**: 主写必须成功才返回 success 给上游
- **审计**: 每次主写 / 派生失败 → `audit_log` (现有 schema 即可, 无新表)

### 3.4 新增 / 改动文件

| 路径 | 改动 | 工作量 |
|---|---|---|
| `backend/wiki_fs/paths.py` | 新增 `hotspots_dir` 路径常量 | 0.5d |
| `backend/wiki_fs/write_item.py` | 复用现 `write_item_to_md`, 加 `subtype='hotspot'` 分支 | 0.5d |
| `backend/services/wiki_to_db_sync.py` | 新 worker, 30s 轮询 `wiki_sync_backfill` | 1d |
| `backend/services/db_to_wiki_reconcile.py` | 一次性 backfill 4194 md + 启动 reconcile | 0.5d |
| `backend/services/collection_service.py` | 改 `_run_once_locked`: 主写 wiki, 派生 DB | 1d |
| `backend/repository/hotspot_repo.py` | upsert 加 idempotent 校验 | 0.5d |
| `backend/services/recency.py` (新) | 把 `_build_items` 的 recency 校验迁过来, 派生层读 wiki fm | 0.5d |
| 迁移 087 | `wiki_sync_backfill` 表 | 0.5d |
| Scheduler job 18 `wiki_to_db_sync` | 每 30s | 0.5d |
| Scheduler job 19 `sync_backfill_process` | 每 60s | 0.5d |
| 监控指标 `wiki_sync_lag` | observability/batch-2 扩展 | 0.5d |
| **测试** | 12+ 文件, ~80 cases | 1d |
| **文档** | AGENTS.md 修 + runbook | 0.5d |
| **总计** | | **~7d (1.5 周)** |

### 3.5 4194 md backfill 策略

1. 启动前 `dry-run`: 跑 reconcile, 报告 md 数 vs DB 数差异, 不写
2. 启动后第一周: 静默 mode, 双写但派生失败只告警, 不阻断主流程
3. 第二周起: 主写严格, 派生失败告警
4. 一个月后: 退役旧 DB 写入路径, 只允许 wiki 写入

### 3.6 风险

| 风险 | 缓解 |
|---|---|
| 4194 md backfill 慢 / 出错 | dry-run + 增量 + idempotent + 进度可视化 |
| ingest 双写延迟 → DB 查询空 | `wiki_sync_lag` 监控 + 告警阈值 60s |
| watcher 与现有 hot ingest 锁竞争 | watcher 用只读 connection + 独立连接池 |
| 历史 DB 数据不一致 | reconcile 比对 md 与 DB, 差异入 `reconcile_diff` 表供人工 review |
| scheduler job 18/19 增 event loop 负担 | 两个 job 都用 `asyncio.to_thread` 包装 sqlite |
| wiki_fs 路径热切换 (HOTSPOT_WIKI_ROOT) 失效 | 路径单一源 + 启动时校验 md 根存在 |

---

## 4. 路径 B / C 简评 (不选, 留档)

### B: DB 主写 + Wiki 同步

- 优点: 改动小, 现有 read path 零变化
- 缺点: 与 AGENTS.md 哲学违背; 人类 / AI agent 读 wiki 永远滞后; 4194 md 永远死代码
- 适合: 短期过渡, 不适合作为最终态

### C: 双写统一 write_path() helper

- 优点: 一处 helper, 统一语义
- 缺点: 高风险 (无单一权威写者, 违反 SAG); 失败回滚复杂; 测试矩阵 4 维 (md×db × 成功×失败)
- 适合: 都不适合

---

## 5. 决策记录 (P1.1 batch 内不再动)

- ✅ **路径 A 选定** (用户 2026-09-03 裁决, 理由: "人工读 wiki + 其他 AI agent 运用 wiki")
- ✅ **AGENTS.md "wiki-first" 哲学保持, 不删不改**
- ⏸ **实施**: 留待 P1.1-batch (估 1.5 周)
- ⏸ **背压 / 中间态**: 本批 P1.2-9 不动 wiki 哲学, 仅做信源管道 8 项根治

---

## 6. 与本批 P1.2-9 的关系

| 关系 | 说明 |
|---|---|
| **正交** | P1.2-9 是数据流上的"质量"问题; P1.1 是"存储架构"问题 |
| **不冲突** | P1.2-9 完成后, P1.1 实施的写入路径就是"清洗后的 hot item" |
| **依赖反转** | P1.1 实施时, 现有 P1.5 (id_factory) / P1.3 (recency) / P1.4 (quality) / P1.6 (tz_assumed) 都已落, 可作为 wiki fm 字段 |
| **可叠加** | P1.1 完成后, P1.6 `published_at_tz_assumed` 等审计字段直接写进 wiki fm, 不再需要 DB 列 |

---

## 7. 验证清单 (实施时)

- [ ] dry-run reconcile: md 数 vs DB 数差异 (0 = 历史完美, >0 = 待 backfill)
- [ ] backfill 4194 md, idempotent (重跑 0 副作用)
- [ ] 启动期: 主写 + 派生双轨 1 周, 监控 lag <60s
- [ ] 第二周: 切严格模式, 派生失败告警
- [ ] 一个月后: 退役 DB 写入路径
- [ ] 其他 AI agent (cursor / 协作 agent) 读 wiki → 拿到的数据 == DB 查询结果 (consistency check)

---

## 8. 文档变更 (实施时同步)

- [ ] AGENTS.md: 加 "Hotspot 域 wiki-first 落地" 一节, 列 `llm-wiki-2.0/hotspots/` 路径
- [ ] ARCHITECTURE.md: 加 sync flow ASCII 图
- [ ] PROGRESS.md: 记 P1.1 batch 起止 / 关键 commit
- [ ] runbook: `wiki_sync_lag` 告警处置 / `wiki_sync_backfill` 手动触发

---

**结论**: 路径 A 设计完整, 实施就绪, 留待下次 batch 启动。本批 P1.2-9 完成后, 信源管道干净, P1.1 实施时直接接入"质量 + 审计字段已就绪"的数据流。
