# Phase 8 — 追抓资讯（News Catchup Pipeline）

> **版本**: v1.8
> **日期**: 2026-07-25
> **spec 路径**: `.trae/specs/phase8-catchup/`
> **PRD 章节**: 暂无（hotspot_v1.7_PRD.md 不含，本 spec 为新需求）
> **前置**: Phase 7 MCP Server 完成 (commit e7ba701)

## 1. 背景与目标

### 1.1 事故复盘（2026-07-24 → 2026-07-25 22h 零采集）

`collection_service.py:78-79` 的 `asyncio.Lock` 不跨进程。后端某次重启后，旧的 `run_once` 任务被孤儿化、新 worker 拿不到旧锁的释放信号。`collect_all_job` 在 2026-07-24 13:57 UTC 启动后从未 `finished_at` 落库，导致：

- 22 小时内 0 条新热点入库
- `trend_snapshots` 表 24h × 7 类全 0，趋势图平线
- `D7` 窗口（Shanghai 本周一 00:00 起）看似空，但实际是「没抓到」而非「真没新闻」

加上 2026-07-25 重新冷启动后 5 分钟内入 109 条，证明 22h 期间完全有可抓的新闻。

### 1.2 目标

1. **止血**：让流水线出现「started 但 N 分钟内未 finished」时自动恢复，**不再有 22h 假死**
2. **补救**：用户可主动发起**按时间窗 / 分类的回补**，把 22h 漏抓的 100+ 条一次性追回
3. **观测**：把"采集跑没跑、跑了多久、卡在哪"做进 `GET /api/health` 和首页 banner，**一眼看出**
4. **节流**：避免「追抓 + 实时 collect_all」双重打击源站导致反爬升级

### 1.3 不在范围内

- ❌ 修复 `collection_service.py` 的 asyncio.Lock 本身（**已知根因**，但属于更深层重构，独立 PR）
- ❌ 自动恢复 **所有 22h** 历史（默认深度 7d，避免源站被冲垮）
- ❌ 替代 `/api/collect/run`（如果存在）；追抓是**额外**能力
- ❌ 改动 Proxy 配置体系（沿用现有 `proxy_config.py`）

## 2. 范围

### 2.1 必做

**Watchdog（被动保护）**
- 新增调度 job `catchup_watchdog`：60s 一次，扫 `collection_runs` 表
- 检测 `started_at < now - 600s AND finished_at IS NULL` 的孤儿行
- 动作：标记 `status='failed', error_msg='watchdog: timeout after 600s'`，并 enqueue 一次自动 catchup
- 前端 `/api/health` 暴露 `last_orphan_recovery_at` 时间戳

**主动追抓（API + UI）**
- `POST /api/catchup/run`：参数 `{since, until?, categories?, max_per_source?, mode: 'auto'|'manual'}`
  - `mode='auto'`：watchdog 触发，无 UI 反馈
  - `mode='manual'`：用户主动发起，前端 SSE 推送进度
- `GET /api/catchup/status`：最近 7 轮 + 当前 in-flight
- `POST /api/catchup/abort`：取消 in-flight（仅 manual 模式有效）

**数据模型**
- 新建 `catchup_runs` 表（独立于 `collection_runs`，职责清晰）
- 字段：`id, mode, since_window, until_window, categories, max_per_source, started_at, finished_at, status, items_ingested, items_skipped, sources_attempted, sources_succeeded, error_msg, duration_ms`

**调度 + 集成**
- 追抓与 collect_all **并行**，用独立 `asyncio.Lock` 隔离（catchup_lock），互不阻塞
- 追抓完成时自动触发 `trend_rebuild` job（force_rebuild=True）
- 追抓跳过 known-dead 源（`source_stats.status='dead'` 持续 ≥ 24h 的源）
- 新增 `source_revival_check_job`：每天 03:00 跑一次，对 dead ≥ 7d 的源做单点试探

**前端**
- 首页"本周资讯"区块顶部加 `追抓资讯` 按钮（仅当 `last_ingested > 30min` 时高亮）
- 弹窗：时间范围（默认 now-24h）/ 分类多选 / 每源上限（默认 20）
- 进度条 + 实时日志（通过现有 `/api/events/stream` SSE）
- 追抓完成后 toast 提示「追抓 N 条 / 覆盖 M 分类 / 耗时 Xs」

**测试 + 文档**
- 4 个后端测试文件：`test_catchup_watchdog.py` / `test_catchup_service.py` / `test_catchup_api.py` / `test_catchup_e2e.py`
- 1 个前端组件测试 `CatchupButton.test.tsx`
- 1 份 `docs/phase8_changelog.md`

### 2.2 明确不做

- ❌ 修 `collection_service.py` 的 asyncio.Lock（独立 PR）
- ❌ 改 Proxy 配置体系
- ❌ 给 Phase 7 的 MCP 暴露追抓 tool（用户可手动调 /api/catchup/*；MCP 集成推迟到 Phase 9）
- ❌ 自动恢复 22h 全部历史（默认深度 7d，避免源站被冲）
- ❌ 替换现有 collect_all（追抓是**额外**能力，不破坏现有实时循环）

## 3. 数据模型

### 3.1 新增表（1 张）

**Migration 040: `040_v1.8_catchup_runs.sql`**

```sql
CREATE TABLE IF NOT EXISTS catchup_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mode                TEXT    NOT NULL CHECK (mode IN ('auto', 'manual')),
    since_window        TEXT    NOT NULL,    -- ISO 8601 UTC
    until_window        TEXT,                -- ISO 8601 UTC, nullable (= now)
    categories          TEXT    NOT NULL,    -- JSON array, e.g. '["ai","security"]'
    max_per_source      INTEGER NOT NULL DEFAULT 20,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT,
    status              TEXT    NOT NULL CHECK (status IN ('running','success','partial','failed','aborted')),
    items_ingested      INTEGER NOT NULL DEFAULT 0,
    items_skipped       INTEGER NOT NULL DEFAULT 0,
    sources_attempted   INTEGER NOT NULL DEFAULT 0,
    sources_succeeded   INTEGER NOT NULL DEFAULT 0,
    error_msg           TEXT,
    duration_ms         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_catchup_status   ON catchup_runs(status, started_at DESC);
CREATE INDEX idx_catchup_started  ON catchup_runs(started_at DESC);
```

### 3.2 不动

- `collection_runs` 表（追抓是 read-only consumer）
- `hotspots` 表（追抓走现有 upsert 路径，自动去重）
- `source_stats` 表（追抓会触发现有 liveness 检查）

## 4. 关键设计决策（10 条）

> 来自用户 review；以下均采用**推荐值**。

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Watchdog 检测到卡死后行为 | **自动追抓 + 告警** | 22h 假死的根因是无人看；必须自动 |
| 2 | 主动追抓的运行模式 | **后台 + SSE 推送** | 同步阻塞会 5min+ HTTP 超时 |
| 3 | 追抓历史表 | **新建 catchup_runs** | 避免污染实时 collection_runs schema |
| 4 | 追抓时是否跳过 dead 源 | **跳过 + 标 tried_again** | 节省时间，避免反复失败 |
| 5 | 追抓深度上限 | **用户指定 + 默认 7d** | 默认安全，用户可加到 14d |
| 6 | 追抓完成时是否触发 trend 重建 | **自动 force_rebuild** | 用户看到立即可用的趋势图 |
| 7 | 追抓与 collect_all 是否并行 | **并行（独立 catchup_lock）** | 实时循环不停 |
| 8 | 死源复活探测 | **独立 source_revival_check_job（每日 03:00）** | 不污染追抓 |
| 9 | 追抓 UI 入口位置 | **首页"本周资讯"顶部按钮** | 22h 假死受害者第一眼看到 |
| 10 | 追抓默认参数 | **since=now-24h, categories=all, max_per_source=20** | 与 collect_all 单轮产量匹配 |

## 5. API 端点

### 5.1 `POST /api/catchup/run`

**Request body**:
```json
{
  "since": "2026-07-24T13:57:00Z",
  "until": "2026-07-25T09:25:00Z",   // optional, default=now
  "categories": ["ai", "security", "github"],   // optional, default=all
  "max_per_source": 30               // optional, default=20
}
```

**Response 202** (accepted, async):
```json
{
  "status": "accepted",
  "run_id": 42,
  "since": "2026-07-24T13:57:00Z",
  "until": "2026-07-25T09:25:00Z",
  "categories": ["ai", "security", "github"],
  "estimated_duration_s": 240
}
```

**Response 409** (already running):
```json
{
  "detail": {
    "message": "A manual catchup is already running (run_id=41)",
    "active_run_id": 41
  }
}
```

### 5.2 `GET /api/catchup/status`

**Response 200**:
```json
{
  "version": "1.8.0",
  "current_run": {
    "run_id": 42,
    "mode": "manual",
    "since": "2026-07-24T13:57:00Z",
    "until": "2026-07-25T09:25:00Z",
    "categories": ["ai", "security", "github"],
    "started_at": "2026-07-25T09:30:00Z",
    "elapsed_s": 142,
    "sources_attempted": 8,
    "sources_succeeded": 5,
    "items_ingested": 47
  },
  "recent_runs": [
    {"run_id": 41, "mode": "auto", "status": "success", "items_ingested": 28, "duration_ms": 142000, "finished_at": "..."}
  ]
}
```

### 5.3 `POST /api/catchup/abort`

**Response 200**:
```json
{"status": "aborted", "run_id": 42, "items_ingested_before_abort": 47}
```

## 6. Watchdog 逻辑

```python
# backend/scheduler/jobs.py 新增
def catchup_watchdog_job():
    """每 60s 检查 collection_runs 是否有孤儿 started_at > 10min 未 finished"""
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
    stuck = conn.execute("""
        SELECT id, started_at FROM collection_runs
        WHERE finished_at IS NULL AND started_at < ?
        ORDER BY started_at ASC
    """, (cutoff,)).fetchall()

    if not stuck:
        return

    for row in stuck:
        conn.execute("""
            UPDATE collection_runs
            SET finished_at = ?, status = 'failed', error_msg = 'watchdog: timeout after 600s'
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), row['id']))

    # 自动 enqueue 一次 catchup, 范围 = 最早 stuck 时刻 → now
    earliest = min(r['started_at'] for r in stuck)
    enqueue_catchup(
        mode='auto',
        since=earliest,
        until=datetime.utcnow().isoformat(),
        categories=None,  # all
        max_per_source=30,
    )
```

## 7. 追抓 Service 核心逻辑

```python
# backend/services/catchup_service.py
class CatchupService:
    def __init__(self):
        self._lock = asyncio.Lock()  # 独立于 collect_all 的 lock
        self._current_run: Optional[int] = None

    async def run(self, *, mode, since, until, categories, max_per_source) -> int:
        if self._lock.locked() and mode == 'manual':
            raise HTTPException(409, "A manual catchup is already running")

        async with self._lock:
            run_id = self._create_run_row(mode, since, until, categories, max_per_source)
            self._current_run = run_id
            try:
                # 1. 选源: 跳过 source_stats.status='dead' 持续 >= 24h
                sources = self._select_sources(categories)
                # 2. 分类并行抓 (复用 collection_service 的并发模型)
                results = await self._crawl_all(sources, since, until, max_per_source)
                # 3. 写库 (走 hotspots.upsert, 自动去重)
                ingested = self._upsert_batch(results)
                # 4. 触发 trend_rebuild
                scheduler.add_job(trend_rebuild_job, 'date', run_date=now+1s)
                # 5. 标 success
                self._finish_run(run_id, 'success', ingested)
                return run_id
            except Exception as e:
                self._finish_run(run_id, 'failed', error=str(e))
                raise
            finally:
                self._current_run = None
```

## 8. 调度器集成

新增 2 个 job：

| ID | 名称 | 频率 | 用途 |
|---|---|---|---|
| 28 | `catchup_watchdog` | 60s | 检测孤儿 run + 自动追抓 |
| 29 | `source_revival_check` | 每日 03:00 | 对 dead ≥ 7d 源做单点试探 |

## 9. 前端组件

### 9.1 `<CatchupButton />`（首页 "本周资讯" 区块顶部）

```tsx
<CatchupButton
  lastIngestedAt={last_ingested_at}  // 来自 /api/health
  onRun={(params) => api.post('/api/catchup/run', params)}
  onProgress={(sse_event) => updateProgress(sse_event)}
/>
```

Props-driven：仅在 `now - last_ingested_at > 30min` 时高亮红色，正常状态灰色。

### 9.2 状态机

| 状态 | 视觉 | 行为 |
|---|---|---|
| idle | 灰色按钮 | 可点击 → 弹窗 |
| stale (>30min) | 红色按钮 + 角标 "已 N 分钟未更新" | 可点击 → 弹窗 |
| running | 进度条 + 实时数字 | 不可点击，右上角 "中止" |
| success | 绿色 toast 3s | 自动消失 |
| failed | 红色 toast 5s | 可重试 |

## 10. 测试覆盖

### 10.1 后端（4 文件，约 35 用例）

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_catchup_watchdog.py` | 8 | 孤儿检测、边界（恰好 600s）、并发、auto 触发 |
| `test_catchup_service.py` | 12 | 锁隔离、跳过 dead 源、深度限制、aborted 路径 |
| `test_catchup_api.py` | 10 | POST/GET/Abort 三端点、409 冲突、参数校验 |
| `test_catchup_e2e.py` | 5 | 完整 7d 回补、trend 重建、in-flight 检测 |

### 10.2 前端（1 文件，约 8 用例）

`CatchupButton.test.tsx`：
- stale 状态高亮
- 弹窗 → 提交 → 进度条
- SSE 断线重连
- abort 按钮

## 11. 验收门禁

- [ ] `pytest backend/tests/test_catchup_*.py -v` 全 PASS
- [ ] `npx vitest run src/components/CatchupButton.test.tsx` PASS
- [ ] `npx tsc --noEmit` 0 error
- [ ] 端到端演练：人为制造孤儿（kill -STOP uvicorn 5min → SIGCONT）→ watchdog 10min 内恢复
- [ ] 端到端演练：UI 触发 24h 回补，5min 内 100+ 条入库
- [ ] 文档：docs/phase8_changelog.md + spec.md 链接挂在 README

## 12. 影响范围

| 维度 | 影响 |
|---|---|
| 数据库 | 新增 1 张表（catchup_runs），1 个 migration 文件 |
| 调度器 | 新增 2 个 job（catchup_watchdog, source_revival_check） |
| API | 新增 3 个端点（POST/GET/Abort） |
| 前端 | 新增 1 个组件（<CatchupButton />），无破坏性 |
| 性能 | 追抓期间 + 1 个并发抓取任务（与 collect_all 隔离），CPU 峰值 +10% |
| 风险 | 源站被追抓冲垮（通过 max_per_source + 跳过 dead 源控制） |
| 回滚 | 删除 catchup_runs 表 + 3 个端点 + 1 个组件，不影响 collect_all |

## 13. 时间估算

- 实施：1.5 工作日（数据模型 0.5d + watchdog 0.5d + API/前端 0.5d）
- 测试 + 文档：0.5 工作日
- 验收：0.5 工作日（端到端演练 2 次）
- **合计：2.5 工作日**

## 14. 开放问题（用户可改）

1. **追抓默认深度**：当前默认 7d，PRD 没说，是否改 14d？
2. **手动追抓是否要 rate limit**（同一用户 5min 内只能触发 1 次）？当前无限制
3. **追抓期间是否暂停 dashboard 的 `/api/hotspots` 缓存 invalidate**？当前会随 DB 写入自动失效
4. **追抓成功 / 失败是否要发邮件 / 微信通知**？当前仅 toast

## 15. 附录

- 事故根因：`backend/services/collection_service.py:78-79` asyncio.Lock 跨进程失效
- 22h 漏抓估算：~500-800 条（按 collect_all 5min/次 × 260 次 × 平均 3 条 = 780）
- 恢复证明：2026-07-25 09:25-09:30 冷启动后 5min 入 109 条（与历史 5min/次产量一致）
