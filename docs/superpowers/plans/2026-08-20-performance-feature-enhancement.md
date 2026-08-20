# Hotspot 性能优化与功能完善实施计划（草稿 · 已被取代）

> ⚠️ **本文件为历史草稿，已被正式版 `docs/v0.5_refactor_plan.md` 完全取代。**
> 执行 v0.5 重构只读正式版；本文件仅供追溯方案演进（批判性审查结论已整合进正式版 §2 A11–A15 / §5.3 / §6）。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不引入 Redis/PG/Celery 的「单人本地工作站」约束下，消除已实测的性能瓶颈（993MB 数据库、1.14MB 前端主 chunk、列表查询不可走索引），落地「个人工作看板」聚合视图，并把分散的 AI 能力（质量评分/质量门禁/内容提炼/行动建议）收敛为统一的 LLM 中枢（AiHub，见 Part G）。

**Architecture:** 短期走「查询走索引 + 缓存降噪 + 前端分包 + 数据库瘦身」四板斧；中期沿 crawler-v2 strangler 路线收敛采集管道，同步把 `llm_service`/`ai_service` 双入口合并为单一 AiHub（llm.yaml 为配置真相源 + SQLite 运行时覆写）；新增 `/workbench` 聚合 API + 页面，把任务状态/采集进度/质量指标/学习进度/AI 用量汇聚成单屏看板。

**Tech Stack:** FastAPI · SQLite(WAL) · APScheduler · React 18 + Vite 5 + TypeScript · Tailwind · ECharts

**制定日期:** 2026-08-20（同日整合 LLM 集中管理方案，见 Part G）
**依据文档:** `docs/ARCHITECTURE.md`（v0.4.0 现状）、`docs/v1.7_development_plan.md`、代码实测

---

## Part A · 现状基线诊断（实测证据）

| # | 瓶颈 | 证据（文件/数据） | 影响 |
|---|------|------|------|
| A1 | **主列表查询不走索引** | `backend/repository/hotspot_repo.py` `list_hotspots`：`ORDER BY COALESCE(ingested_at, published_at)` 与 cursor 条件 `CAST(strftime('%s', COALESCE(...)) AS INTEGER)` 均为逐行函数计算；`quality_flags NOT LIKE '%..%'` ×4 逐行字符串扫描。现有 `idx_cat_ingested(category, ingested_at DESC)` 完全用不上 | 每次翻页全表扫描，数据量越大越慢 |
| A2 | **数据库膨胀** | `du -sh backend/hotspot.db` = **993MB**；`ARCHITECTURE.md` 记载 quality_check_logs 曾达 440 万行/1.35GB | 备份慢、查询缓存命中率下降、FTS 重建慢 |
| A3 | **前端主 chunk 过大** | `dist/assets/index-DtAMlHTK.js` = **1.14MB**（ECharts 混入主包），`BarChart-*.js` 376KB；`vite.config.ts` 无 `manualChunks`、无压缩插件 | 首屏 JS 解析/执行慢，冷启动白屏 |
| A4 | **缓存层日志开销** | `backend/cache.py`：每次 hit/miss 都调 `log_event`（第 80/115 行） | 高命中场景下日志 I/O 可能超过被省掉的 DB 查询 |
| A5 | **warmup 是假的** | `cache.py:warmup()` 只写 `{"_warmed": True}` 哨兵，首请求仍 miss | 冷启动第一批请求全部打 DB |
| A6 | **无聚合看板入口** | `frontend/src/routes/index.tsx` 41 条路由中没有 workbench；采集进度/质量/todos/复习散落 `/judge/*`、`/action/*` | 用户对「系统今天干了什么、我还欠什么」无单屏掌控 |
| A7 | **已知功能债** | `ARCHITECTURE.md` 第八章：chunk 生成器未落地（API 为预留）、URL 校验降级为异步抽样、sync 删除通道不全、SyncPage/SecretsPage ~800 行 | 知识库 chunk/FTS 检索是空壳；部分体验不完整 |
| A8 | **AI 能力双入口分裂** | `backend/services/llm_service.py`（读 `config/llm.yaml`，多 provider 降级）与 `backend/services/ai_service.py`（v4.4 重构，硬编码 sensenova/env，门禁与 evaluate 走它）并存；`evaluate_article` 在 llm_service 里却委托 ai_service | 凭据/限频/缓存语义分裂，配置改了不生效 |
| A9 | **llm.yaml 半数是死配置** | `rate_limits.requests_per_minute` 无任何消费方（ai_service 自己另写了一套 6 次/60s 硬编码限频）；`task_overrides` 未被 `_resolve_model` 读取；前端 0 处引用 `/api/llm` | 用户无法配置/观测 AI 行为 |
| A10 | **门禁 AI 半挂空 + 无行动建议能力** | `quality/ai_quality_gate.py` 仅启发式 + 限频 6 次/分钟的 `gate_detect` 抽样；「行动建议」（读完该做什么）完全不存在 | AI 加持的质量闭环不成立 |

**基线测量命令**（每个阶段前后各跑一次，对比验收）：

```bash
# 后端 API 延迟基线（后端需先启动）
python scripts/quick_perf.py                 # 记录 avg/p95/p99/QPS
# 前端构建体积基线
cd frontend && npx vite build --logLevel error && du -sh dist && ls -laS dist/assets | head -8
# 数据库体积基线
du -sh backend/hotspot.db
# 列表查询计划验证（确认走索引）
sqlite3 backend/hotspot.db "EXPLAIN QUERY PLAN SELECT id FROM hotspots WHERE category='ai' AND ingested_at >= '2026-08-13' ORDER BY ingested_at DESC LIMIT 50"
```

---

## Part B · 短期快速见效（第 1–2 周）

### Task 1: 列表查询索引化（消除 COALESCE/LIKE 全表扫描）

**思路：** 两个根因分别根治——
1. `COALESCE(ingested_at, published_at)` → 一次性回填 `ingested_at`，之后所有查询直接用 `ingested_at`，`idx_cat_ingested` 生效。
2. `quality_flags LIKE` ×4 → 物化为布尔列 `is_hidden`（写入路径维护），查询变 `is_hidden = 0`。

**Files:**
- Create: `backend/repository/migrations/060_list_query_optimization.sql`
- Create: `backend/scripts/backfill_ingested_at.py`（一次性脚本）
- Modify: `backend/repository/hotspot_repo.py`（`upsert_many`、`list_hotspots`、flag 更新处）
- Test: `backend/tests/test_hotspot_repo_perf.py`

- [ ] **Step 1: 写失败测试** — `backend/tests/test_hotspot_repo_perf.py`

```python
"""列表查询优化验收: ingested_at 非空 + is_hidden 过滤 + 查询计划走索引."""
import sqlite3

from backend.repository.hotspot_repo import HotspotRepository


def test_list_query_uses_index(temp_db):
    repo = HotspotRepository()
    conn = sqlite3.connect(str(temp_db))
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM hotspots "
        "WHERE category='ai' AND ingested_at >= '2026-08-13' AND is_hidden = 0 "
        "ORDER BY ingested_at DESC LIMIT 50"
    ).fetchall()
    text = " ".join(str(r) for r in plan)
    assert "idx_cat_ingested" in text or "idx_list_visible" in text


def test_hidden_flag_filters_list(temp_db):
    """is_hidden=1 的条目不出现在列表里。"""
    repo = HotspotRepository()
    # 插入 2 条, 其中 1 条带 historical_published flag
    from backend.domain.hotspot import HotspotItem
    visible = HotspotItem(id="ai_ok", title="ok", source="s", url="http://a", category="ai")
    hidden = HotspotItem(
        id="ai_bad", title="bad", source="s", url="http://b", category="ai",
        quality_flags=["historical_published"],
    )
    repo.upsert_many([visible, hidden])
    items, _ = repo.list_hotspots(category=None, time_range=__import__("backend.domain.hotspot", fromlist=["TimeRange"]).TimeRange.DAYS_7)
    ids = {i.id for i in items}
    assert "ai_ok" in ids and "ai_bad" not in ids
```

- [ ] **Step 2: 运行测试确认失败** — `python -m pytest backend/tests/test_hotspot_repo_perf.py -v`（预期 FAIL：`is_hidden` 列不存在）

- [ ] **Step 3: 迁移脚本** — `backend/repository/migrations/060_list_query_optimization.sql`

```sql
-- 列表查询优化: is_hidden 物化列 + ingested_at 回填
ALTER TABLE hotspots ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0;

-- 回填: 把当前 4 类 suppress flag 映射到 is_hidden
UPDATE hotspots SET is_hidden = 1
WHERE quality_flags LIKE '%historical_bid%'
   OR quality_flags LIKE '%historical_published%'
   OR quality_flags LIKE '%no_published_at%'
   OR quality_flags LIKE '%landing_page_unresolvable%';

-- 回填 ingested_at, 让 COALESCE 彻底退役
UPDATE hotspots SET ingested_at = published_at WHERE ingested_at IS NULL;

-- 覆盖列表主查询的复合索引
CREATE INDEX IF NOT EXISTS idx_list_visible
    ON hotspots(category, ingested_at DESC) WHERE is_hidden = 0;
```

- [ ] **Step 4: 改 `hotspot_repo.py`**
  - `upsert_many`：SQL 增加 `is_hidden` 列，值由 flags 推导：
    ```python
    _HIDDEN_FLAGS = ("historical_bid", "historical_published",
                     "no_published_at", "landing_page_unresolvable")

    def _is_hidden(flags: list[str] | None) -> int:
        if not flags:
            return 0
        return 1 if any(f in _HIDDEN_FLAGS for f in flags) else 0
    ```
  - `list_hotspots`：`where_clauses` 中删除 4 行 LIKE 与 `COALESCE`，替换为：
    ```python
    where_clauses = [
        "ingested_at >= ?",
        "is_hidden = 0",
        "(url_check_status IS NULL OR url_check_status NOT IN ('mismatch', 'unreachable'))",
    ]
    # cursor 条件简化为纯字符串比较（ISO-8601 同格式可按字节序比较）
    where_clauses.append("(ingested_at < ? OR (ingested_at = ? AND rowid < ?))")
    # ORDER BY
    "ORDER BY ingested_at DESC, rowid DESC "
    ```
    注：cursor 构造 `_make_cursor` 仍用 unix ts 兼容旧 cursor，`_parse_cursor` 后需把 ts 转回 ISO 字符串比较；或同步把 cursor 改为 `<iso>_<id>` 并对旧格式做一次性兼容分支。
  - 所有更新 `quality_flags` 的写入点（url_check job、quality 重跑）同步维护 `is_hidden`。

- [ ] **Step 5: 运行测试确认通过** — `python -m pytest backend/tests/test_hotspot_repo_perf.py backend/tests/test_hotspot_repo.py -v` 全部 PASS
- [ ] **Step 6: 跑全量回归** — `python -m pytest backend/tests/ --tb=short -q`（cursor 语义变更影响面广，必须全量）
- [ ] **Step 7: 用 Part A 基线命令复测** `quick_perf.py`，记录 p95 下降幅度，Commit。

```bash
git add backend/repository/migrations/060_list_query_optimization.sql backend/repository/hotspot_repo.py backend/tests/test_hotspot_repo_perf.py
git commit -m "perf: list query index-ization (is_hidden + ingested_at backfill)"
```

---

### Task 2: 缓存层降噪 + 真实预热

**Files:**
- Modify: `backend/cache.py`
- Modify: `backend/main.py`（lifespan warmup 调用点）
- Test: `backend/tests/test_cache.py`（已有，追加用例）

- [ ] **Step 1:** `TTLCache.__getitem__` 中把 `cache_hit` 的 `log_event` 改为**每 100 次 hit 采样一次**（`if self.hits % 100 == 0`），`cache_miss` 保留但降级为 DEBUG 级别输出。预期：稳态命中率 >80% 时日志量降 ~99%。
- [ ] **Step 2:** 把 `warmup()` 从「写哨兵」改为「真实预热」：在 `backend/main.py` lifespan 的 scheduler 启动后，用 `asyncio.to_thread` 真实执行一次 `HotspotService().list_hotspots(category="all", time_range="7d", limit=50)` 与 `trend` 查询，结果走正常路径写入 `list_cache`。哨兵逻辑保留作为 fallback。
- [ ] **Step 3:** 追加测试：连续 get 101 次只产生 ≤2 条 hit 日志（monkeypatch `log_event` 计数）。
- [ ] **Step 4:** `python -m pytest backend/tests/test_cache.py -v` PASS 后 commit：`perf: cache log sampling + real warmup`

---

### Task 3: 前端 bundle 拆分（ECharts 逐出主包）

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: 引用 ECharts 的组件（确认全部经 `React.lazy` 页面间接引入；排查 `frontend/src` 中顶层 import echarts 的位置）

- [ ] **Step 1: 定位主 chunk 内容** — `cd frontend && npm i -D rollup-plugin-visualizer && npx vite build`，打开 `stats.html` 确认 1.14MB 主 chunk 里是 echarts 还是其他依赖。
- [ ] **Step 2: 配置 manualChunks** — `frontend/vite.config.ts`：

```typescript
build: {
  target: 'es2020',
  rollupOptions: {
    output: {
      manualChunks: {
        'vendor-react': ['react', 'react-dom', 'react-router-dom'],
        'vendor-echarts': ['echarts', 'echarts-for-react'],
      },
    },
  },
  chunkSizeWarningLimit: 600,
},
```

- [ ] **Step 3: 排查非懒加载 import** — `grep -rn "from 'echarts'" frontend/src --include='*.tsx' --include='*.ts'`；任何被非 lazy 页面直接引用的图表组件改为 `React.lazy` 或动态 `import()`。
- [ ] **Step 4: 验收** — 重新 build，主 chunk 应 <300KB；`npx tsc --noEmit && npx vitest run && npx vite build --logLevel error` 全绿。Commit：`perf(frontend): split vendor chunks, evict echarts from main bundle`

> 注意（项目已有经验）：Vite dev server 不热重载 `vite.config.ts` / `tailwind.config.js`，改后必须重启 dev server 验证。

---

### Task 4: 数据库瘦身（993MB → 目标 <300MB）

**Files:**
- Create: `backend/scripts/db_diet.py`
- Modify: `backend/scheduler/scheduler.py`（挂月度 job）

- [ ] **Step 1: 诊断** — `sqlite3 backend/hotspot.db "SELECT name, SUM(pgsize) AS sz FROM dbstat GROUP BY name ORDER BY sz DESC LIMIT 15"` 找出最大表与索引。
- [ ] **Step 2:** 写 `db_diet.py`：
  - 归档：`hotspots` 中 `ingested_at` 早于 180 天且非收藏的条目导出 JSONL 到 `backend/data/archive/hotspots-YYYYMM.jsonl` 后删除（收藏关联表同步清理检查）。
  - 截断：`quality_check_logs` 保留 30 天（现有 job 只 DELETE 不回收空间，见 scheduler.py 第 236 行注释）。
  - 回收：`VACUUM INTO 'backend/hotspot.db.slim'` 后原子替换（服务需短暂停写；或放进周日 `weekly_maintenance` 链）。
- [ ] **Step 3:** 先对 `hotspot.db.bak-*` 副本演练，确认归档可回导后再对真库执行。
- [ ] **Step 4:** 挂到调度器：月度第 1 个周日 03:30 执行归档 + VACUUM。
- [ ] **Step 5:** 验收：`du -sh backend/hotspot.db` <300MB；`quick_perf.py` 无回归；全量测试 PASS。Commit：`ops: db diet - archive 180d cold data + vacuum`

---

## Part C · 长期架构优化路线图（第 3–12 周）

| 阶段 | 周次 | 事项 | 说明 |
|------|------|------|------|
| C1 | 3–4 | **crawler-v2 strangler 收敛** | `ARCHITECTURE.md` 债务 #1：`crawler_sources`/`raw_items`/`source_scheduler` 旁路表已建（迁移 055–057）。按源逐个把 8 个 collector 的调度权交给源级状态机，每切一个源跑 7 天对比采集量/失败率后再切下一个 |
| C2 | 4–6 | **URL 校验恢复实时性** | 债务 #5：异步 job 抽样实时性弱。方案：入库时只做 DNS/HEAD 轻量检查（<200ms 超时，并发 20），完整 GET 校验仍走异步队列；把结果回写 `url_check_status` 并联动 `is_hidden` |
| C3 | 5–7 | **读路径去计算化** | 把 `count_by_category`、trends 等聚合改为 post-ingest 链中预计算落表（`category_counts` / `trend_snapshots` 已有雏形），API 直读快照，TTL 缓存仅作兜底 |
| C4 | 7–9 | **FTS5 检索体验化** | 搜索接口从 `LIKE` 迁到 `hotspots_fts`（若尚无则建外部内容表 + 触发器），支持 bm25 排序与高亮 |
| C5 | 9–12 | **可观测性轻量闭环** | 不加 Prometheus。把 `observability.log_event` 的结构化事件落 `events.db` 侧表，`/api/health` 扩展出 24h 分位延迟、job 成功率、缓存命中率三块；Workbench 直接消费（见 Part D） |
| C6 | 4–8 | **AiHub LLM 中枢整合** | 与 C2 并行：合并双入口、激活死配置、新增行动建议能力，详见 Part G |

**明确不做**（守住 ARCHITECTURE.md 附录原则）：不引入 Redis/PG/Celery/Docker；不做多 worker（SQLite WAL 单写者）；不为不确定的多用户场景预留抽象。

---

## Part D · 个人工作看板（Workbench）

**理念：** 单人工作站的核心体验是「掌控感」——一屏回答三个问题：
1. **系统替我干了什么？**（采集进度、质量门禁战果、任务队列）
2. **我还欠什么？**（到期复习、待办、编译队列积压、失败任务）
3. **我的注意力花在哪了？**（阅读/收藏/标注趋势，对应 attention_events 5 维评分）

### D1 · 数据来源映射（全部复用现有表，零新采集）

| 看板卡片 | 数据来源 | 现有 API |
|----------|----------|----------|
| 今日采集 | `collection_runs` / `crawler_runs`（SUCCESS/PARTIAL/FAILED 计数 + 新增条数） | `sources.py`、`health.py` |
| 质量门禁 | `quality_check_logs` 24h 通过率 + 拒绝原因 TOP3 | `/api/quality/*` |
| 待办 | `todos` 表（pending/今日完成） | `/api/todos` |
| 复习到期 | `sm2_reviews` due 计数 | `/api/reviews` |
| 知识编译 | `knowledge_tasks` pending/processing/failed + compile 队列净流出 | `/api/knowledge/*` |
| 系统健康 | 缓存命中率（`cache.hit_rate()`）、DB 体积、下轮 job 时间 | `/api/health`、`/api/cache` |
| 注意力周报 | `attention_events` 7 天 view/dwell/favorite 聚合 | `/api/attention-events` |
| 实时性 | SSE `collect_done` 事件触发卡片刷新 | `/api/events`（`useSSE` hook） |

### D2 · 新增聚合 API（避免前端发 8 个请求）

**Files:**
- Create: `backend/api/workbench.py`（新 router，注册进 `backend/core/routers.py` 白名单）
- Create: `backend/services/workbench_service.py`
- Test: `backend/tests/test_workbench_api.py`

```python
# backend/api/workbench.py 核心形态
@router.get("/api/workbench/summary")
async def workbench_summary():
    """单请求聚合 6 块数据, 各块独立 try/except — 单块失败返回 null 不影响整页."""
    return await asyncio.to_thread(WorkbenchService().build_summary)
```

`build_summary()` 内部每块用 `try/except` 隔离（优雅退化原则），返回：

```json
{
  "collect": {"runs_today": 28, "last_status": "SUCCESS", "items_added_24h": 142, "failed_sources": []},
  "quality": {"pass_rate_24h": 0.87, "rejected_top": [{"gate": "RecencyGate", "n": 34}]},
  "tasks": {"todos_pending": 5, "todos_done_today": 3, "knowledge_queue": {"pending": 2, "failed": 0}},
  "learning": {"reviews_due": 12, "compile_backlog": 8},
  "system": {"cache_hit_rate": {"list": 0.91}, "db_size_mb": 287, "next_jobs": [{"id": "collect_all", "at": "..."}]},
  "attention": {"read_7d": [12, 8, 15, 9, 20, 4, 6], "favorites_7d": 9}
}
```

### D3 · 前端页面

**Files:**
- Create: `frontend/src/pages/WorkbenchPage.tsx`（lazy 注册进 `routes/lazy-imports.ts`）
- Create: `frontend/src/hooks/useWorkbench.ts`
- Modify: `frontend/src/routes/index.tsx`（加 `path="/workbench"` 并设为首页默认路由 `/` 的候选——保留 `/editorial` 现状，导航加入口，不抢首页）

设计要点（遵循报纸编辑风设计语言：Newsreader 标题 / Inter 正文 / 墨色纸色令牌）：
- 顶部一行「今日脉搏」数字带（新增条目 / 通过率 / 待办 / 到期复习），衬线大数字。
- 中部三栏：系统产出（采集+质量）｜我的债务（待办+复习+失败任务，每项带跳转深链）｜注意力曲线（7 天 sparkline，用已分包的 ECharts）。
- 卡片失败态显示「—」不显示错误堆栈（优雅退化）。
- `useSSE` 监听 `collect_done` → 只刷新采集卡片，不全页 reload。
- 轮询兜底：60s `useRefreshInterval`（复用现有 hook）。

### D4 · 验收

- [ ] `GET /api/workbench/summary` 单请求 <150ms（内部全为轻量 COUNT/聚合，且各块可并行 `asyncio.gather`）
- [ ] 任一数据源表损坏（如 drop `sm2_reviews`）时 API 仍返回其余块
- [ ] 前端 vitest：卡片渲染 + SSE 刷新用例；`npx tsc --noEmit` 无错误

---

## Part E · 功能完善清单（优先级排序）

| 优先级 | 功能点 | 现状问题 | 改进建议 | 预估工作量 |
|--------|--------|----------|----------|-----------|
| **P0** | 知识 chunk 生成器 | `ARCHITECTURE.md` 明示未落地，`knowledge_chunks_api` 是空壳 API | 落地段落切分器（按 markdown heading/段落，写 `knowledge_chunks` + FTS5 触发器已在），接入 knowledge_sync 管道；让 chunk 级检索真正可用 | 3–5 天 |
| **P0** | Workbench 看板 | 无聚合入口（Part D） | 按 Part D 实施 | 3 天 |
| **P0** | DB 瘦身 | 993MB | Task 4 | 1–2 天 |
| **P0** | AiHub 双入口合并 | A8/A9：llm_service 与 ai_service 凭据/限频/缓存语义分裂，llm.yaml 半数死配置 | Part G strangler 五步 | 4–6 天 |
| **P1** | 行动建议能力（t_advice） | A10：完全不存在 | Part G G2，读完/提炼后生成 1–3 条可执行建议 | 2 天 |
| **P1** | AI 集中配置页 | 前端 0 处引用 `/api/llm`，用户无法配置/观测 AI 行为 | Part G G4-Step4，任务级开关/采样率/模型覆写 UI | 2 天 |
| **P1** | sync 删除通道补全 | 债务 #2：仅部分表支持 absence-as-deletion | 对 settings/黑名单补显式删除记录（`deleted_keys` manifest），避免语义特殊表永远无法同步删除 | 2–3 天 |
| **P1** | 标讯告警规则引擎 | `bid_alert.py` 138 行，规则能力弱 | 关键词 + 地区 + 金额阈值组合规则，命中经 SSE 推送 Workbench | 2 天 |
| **P1** | SyncPage/SecretsPage 拆分 | 债务 #4：~800 行单文件 | 按 section 拆 3–4 个子组件，纯 UI 重构不改行为 | 1–2 天 |
| **P2** | FTS5 热点检索 | 搜索走 LIKE（C4） | 见 Part C C4 | 3 天 |
| **P2** | RUF001–003 精细化 | 债务 #3：全仓忽略中文误报 | 按目录换行级启用（backend/tests 先试点） | 0.5 天 |
| **P2** | MCP 工具扩展 | 现 9–13 个工具 | 暴露 workbench summary / 采集手动触发给外部 Agent | 1 天 |

**排序逻辑：** P0 = 已实证的瓶颈或空壳功能；P1 = 架构文档已登记的债务；P2 = 体验增强。P0 内部顺序 = Task 1→2→3→4（性能）→ Workbench（体验）→ AiHub 合并（AI 地基）→ chunk 生成器（功能，chunk 摘要可接 AiHub），因为性能基线先固化，后续功能验收才有参照。

---

## Part G · LLM 集中管理（AiHub）

**理念：** 质量评分、质量门禁、核心内容提炼、行动建议四类 AI 能力，共享同一条管线（凭据→限频→成本控制→缓存→降级链→用量审计），因此必须是**一个服务、一张任务表、一个配置页**，而不是每个能力各自接 LLM。

### G1 · 现状结论（实测）

| 问题 | 证据 |
|------|------|
| 双入口分裂 | `llm_service.py`（读 `config/llm.yaml`，多 provider 降级）与 `ai_service.py`（v4.4 重构，硬编码 sensenova/env）并存；`evaluate_article` 在 llm_service 里却委托 ai_service（`llm_service.py` 末尾） |
| 死配置 | `llm.yaml` 的 `rate_limits.requests_per_minute` 无消费方（ai_service 另写了 6 次/60s 硬编码限频）；`task_overrides` 未被 `_resolve_model` 读取 |
| 门禁 AI 半挂空 | `ai_quality_gate.py` 主靠启发式，LLM 仅抽样且限频极保守 |
| 前端零暴露 | `frontend/src` 无任何 `/api/llm` 引用，用户无法配置/观测 |
| 能力缺失 | 「行动建议」完全不存在 |

### G2 · 目标架构：单一 AiHub + 任务注册表

```
              config/llm.yaml                SQLite: llm_task_settings
          (静态真相源: provider/           (运行时覆写: 每任务开关/
           模型/降级链/限频/成本)            采样率/阈值/模型覆写, UI 可改)
                    \                        /
                     \                      /
                ┌──────┴────────────────┴─────┐
                │  backend/services/ai_hub.py     │
                │  单一管线: 限频→成本闸→缓存→   │
                │  provider 降级链→用量审计       │
                └──────┬────────────────────┘
         ┌──────────┼──────────┬───────────┐
    t1_score   gate_ai_detect  t_extract    t_advice
    质量评分     门禁AI增强     核心提炼      行动建议
    (ai_scores)  (quality/)    (深读/知识)   (新增)
```

**任务注册表**（新表 `llm_task_settings`，迁移脚本创建）：

| task_id | 能力 | 消费方 | 可配项 | 降级行为（总开关 off / 全部 provider 失败） |
|---------|------|--------|--------|------------------------------|
| `t1_score` | 质量评分 0–10 | T1/T3 触发器读 `ai_scores` | provider/model/开关 | 回退 DEFAULT_SCORE=5.0（现状兼容） |
| `gate_ai_detect` | 门禁 AI 生成/软文检测 | `ai_quality_gate.py` | 开关/采样率（默认 10%）/置信阈值 | 仅启发式判定 |
| `t_extract` | 核心内容提炼（key_points + summary） | 深读页、知识编译、`/evaluate` | provider/model/max_tokens | 截断前 200 字 |
| `t_advice` | 行动建议（1–3 条可执行建议） | 深读页、提炼结果附带 | 开关/provider | 不生成（字段缺省） |
| `t_tag` / `t_ner` / `t_summary` | 既有能力 | 现有消费方不动 | provider/model | 空结果 |

**关键设计决策：**
- `llm.yaml` = 静态真相源（改文件重启生效，管 provider/降级/限频/成本上限）；`llm_task_settings` = 运行时覆写（UI 即时生效，只管任务级开关/采样/模型覆写）。两层职责不重叠。
- 凭据继续走 env（`SENSENOVA_API_KEY`/`OPENAI_API_KEY` 等）与 `backend/secrets` 体系，**不落 settings 表明文**（延续 v4.4 决策）。
- 成本控制复用已有 `cost_monitor.py`，但真正接入管线：超限时按 `on_exceeded` 语义执行（warn/block/fallback_local），当前它只告警不拦截。
- `gate_ai_detect` 的采样写入管道而非硬编码：每轮采集按采样率抽条目送检，限频从 llm.yaml `rate_limits` 读取（激活死配置）。

### G3 · API 设计（扩展 `backend/api/llm_status.py` → 重命名 `llm.py`）

| 端点 | 方法 | 职责 |
|------|------|------|
| `/api/llm/status` | GET | 已有；扩展返回 24h 用量/成本/缓存命中率（聚合 `llm_usage_log`） |
| `/api/llm/tasks` | GET | 任务注册表全量：每任务配置 + 生效中的 provider/model + 降级态 |
| `/api/llm/tasks/{task_id}` | PUT | 写 `llm_task_settings`（开关/采样率/阈值/模型覆写），写完即时生效 |
| `/api/llm/playground` | POST | 合并现有 `/evaluate`：指定 task + 输入文本试跑，返回结果与耗时/成本（调试专用） |
| `/api/llm/usage` | GET | `llm_usage_log` 按天/任务/provider 聚合，供配置页成本曲线 |

### G4 · strangler 迁移五步（每步可独立验收、可回退）

- [ ] **Step 1：建 `ai_hub.py`，双入口变 facade。** 把 ai_service 的凭据解析/限频与 llm_service 的多 provider 降级/缓存/用量合并进 `AiHub`；`llm_service`/`ai_service` 保留类与方法签名，内部全部委托 hub。验收：`test_llm_service.py` + `test_llm_evaluate.py` + `test_ai_quality_gate` 相关用例全绿，调用方零改动。
- [ ] **Step 2：迁移建 `llm_task_settings` 表 + `_resolve` 逻辑。** 每次调用先查表内覆写，再回退 llm.yaml `task_overrides`，最后默认模型；激活 `rate_limits`（进程级令牌桶，替代 ai_service 硬编码 deque）。验收：新增单测验证「表覆写 > yaml override > 默认」三级优先级与限频生效。
- [ ] **Step 3：门禁接入采样化 AI。** `ai_quality_gate` 从 hub 读 `gate_ai_detect` 配置（开关/采样率/阈值）；采样决策上提到 `QualityGatesMixin`（每轮采集固定配额而非每条判断），避免热路径逐条抖动。验收：采样率设 0 时 LLM 调用次数为 0；设 100% 时不超限频。
- [ ] **Step 4：新能力 t_extract/t_advice + 配置页。** `t_extract` 接管 `/evaluate` 与深读页提炼；`t_advice` 新增（输入 title+summary+key_points，输出结构化建议 JSON，落 `hotspots.ai_advice` 新列或复用 `ai_scores.metadata`）；前端新增 `/settings/ai` 页（或 SettingsPage 分区）：总开关、每任务开关/采样滑块、provider 健康灯、playground 试跑、7 天成本曲线。验收：UI 改采样率后下一轮采集行为变化；无 API key 时页面显示降级态而非报错。
- [ ] **Step 5：删除双入口。** 确认全仓无 `from backend.services.llm_service import` / `ai_service import` 直接调用（除 hub 自身）后，删两文件只留 `ai_hub.py`；同步 `docs/llm_config.md`。验收：全量后端测试 + `ruff` 无死代码告警。

### G5 · 与其他 Part 的联动

- **Workbench（Part D）**：`system` 块新增 `ai` 子卡（今日调用数/估算成本/门禁采样状态/降级态），数据来自 `/api/llm/status`。
- **chunk 生成器（Part E P0）**：chunk_summary 任务走 AiHub，本地 ollama 优先零成本。
- **降级总原则**：`llm.yaml` `enabled: false` 或文件缺失 → 所有任务走降级列行为，系统其余功能不受影响（延续 Phase 16 兼容模式语义）。

### G6 · 验收指标

- [ ] 全仓 LLM 调用只剩 `ai_hub.py` 一个出口（grep 验证）
- [ ] `llm.yaml` 的 `rate_limits`/`cost_alert`/`task_overrides` 三项均有生效测试
- [ ] 四类能力（评分/门禁/提炼/建议）在前端配置页均可独立开关，关闭后对应功能优雅退化不报错
- [ ] `/api/llm/playground` 对每类任务试跑通过；无凭据时返回明确降级信息

---

## Part H · 执行顺序与验收总表

| 里程碑 | 内容 | 验收指标 |
|--------|------|----------|
| M1（第 1 周末） | Task 1 + 2 + 3 | `quick_perf.py` p95 下降 ≥50%；主 chunk <300KB；缓存日志量降 ≥95% |
| M2（第 2 周末） | Task 4 + Workbench API | DB <300MB；`/api/workbench/summary` <150ms |
| M3（第 3–4 周） | Workbench 页面 + AiHub Step1–2 | 看板页 Playwright 冒烟通过；双入口已 facade 化，任务覆写三级优先级测试绿 |
| M4（第 5–8 周） | AiHub Step3–5 + t_advice + AI 配置页 + P0 chunk 生成器 | G6 全部验收项通过；chunk 摘要走 AiHub 本地模型 |
| M5（第 9–12 周） | Part C 其余路线（crawler-v2/URL 校验/FTS/可观测）+ Part E P1 | 按每源切换的 7 天观察期推进 |

**全程约束：**
- 每个 Task 结束跑全量回归：`python -m pytest backend/tests/ --tb=short -q` + `cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error`
- 迁移脚本必须幂等（`IF NOT EXISTS` / duplicate column 容错，见 `db.py:apply_migrations`）
- 改注册代码后同步架构数字：`python scripts/generate_meta.py`
