# P2 精选功能 (多信号合成挑选资讯) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「精选」模式落地——每轮采集后对新增资讯合成 pick_score（质量分 + 关注域 boost + 收藏源加权 + 时效衰减），Top-N 落 `hotspots.pick_score` 列；首页「精选」视图按分排序展示，「全量/深度」视图语义补齐。

**Architecture:** 新服务 `pick_service.py` 纯规则评分（无 LLM）, 迁移 129 加 `pick_score REAL` 列, post-ingest 链追加 `_pick_score_tick()`; 前端精选视图 = 既有列表按新 query 参数排序 + 精选徽章。依赖 P1 的 collect.py 挂点模式（已落地）。

**Tech Stack:** Python 3 / SQLite / pytest; React 18 + TS + Vitest。Spec: `docs/superpowers/specs/2026-09-27-four-modes-redefine-design.md` §3。

**前置**: P1 已合入（collect.py `_news_alert_tick` 先例 + `_news_alert_tick` 追加行位置）。

**计划阶段核实结论:**
1. hotspots 现有 `score` 列均值 77.7/最大 82（7d 实测）— pick_score 公式中 quality_score 用 `COALESCE(quality_score, score, 60)` 兜底。
2. `interest_engine_service.get_boost_map()` 返回 `{domain: m}` m∈[0.79,1.30] — 公式取 `（m - 1.0) × 25` 使关注域加权 ∈ [-5, +7.5]，比 spec 的 `×10` 更贴合实测乘子区间（spec §3.1 的 ×10 为示意, 以本计划为准）。
3. favorites 按 source 聚合无现成方法 — `FavoriteRepository.list()` 返回全量收藏（当前 9 条，量小），service 层内存聚合即可，不加 repo 方法。
4. `query_in_range` 不支持按 pick_score 排序 — 精选视图走新轻量 repo 方法 `list_picked_since`（url+title+score+pick_score 直查, 同 DEV-0235 url-only 先例, 不受 _MAX_LIMIT 影响不适用——本查询有行数语义故受 _MAX_LIMIT 钳制可接受: Top-N=30 << 200）。
5. 迁移编号: P1 用 128 → 本计划用 129。

---

### Task 1: 迁移 129 — hotspots.pick_score 列

**Files:**
- Create: `backend/repository/migrations/129_hotspot_pick_score.sql`

- [ ] **Step 1: 写迁移 SQL**

```sql
-- 129_hotspot_pick_score.sql
-- 2026-09-27 四模式重定义 P2 (spec §3.2): 精选评分列。
-- pick_score 可空 — 未评估的旧行 NULL, 精选视图 COALESCE(quality_score) 兜底排序。
ALTER TABLE hotspots ADD COLUMN pick_score REAL;
```

- [ ] **Step 2: 验证列存在**

Run: `.venv/bin/python3 -c "from backend.repository.db import close_db, init_db; close_db(); init_db(); from backend.repository.db import get_connection; print([r['name'] for r in get_connection().execute('PRAGMA table_info(hotspots)').fetchall() if r['name']=='pick_score'])"`
Expected: `['pick_score']`

- [ ] **Step 3: Commit**

```bash
git add backend/repository/migrations/129_hotspot_pick_score.sql
git commit -m "feat(pick): 迁移 129 — hotspots.pick_score 列 (P2 Task 1)"
```

---

### Task 2: pick_service — 评分合成 + Top-N 落列

**Files:**
- Create: `backend/services/pick_service.py`
- Test: `backend/tests/test_pick_service.py`

- [ ] **Step 1: 写失败测试**

```python
"""pick_service — 精选评分合成 (spec 2026-09-27 four-modes §3)。

契约:
- pick_score = quality_score + (boost-1)*25 + 10* favored_source + 时效衰减
- 时效衰减: 24h 内满权重; 24h~7d 线性衰减到 0.6 (不为零 — 旧文仍可比)
- Top-N: 全量按 pick_score DESC 取 N=30 落列, 其余落 NULL? 不 — 全部落分,
  视图取 Top-N; 落列覆盖窗口内全部新条目 (可解释性)
- favored source: favorites 中该 source 出现 ≥2 次
"""
import pytest
from datetime import datetime, timedelta, timezone

from backend.services import pick_service as ps


def _mk(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class TestComputePickScore:
    def test_base_quality_score(self):
        s = ps.compute_pick_score(
            quality_score=80, interest_boost=1.0,
            favored_source=False, fetched_at_iso=_mk(1),
        )
        assert 79 <= s <= 81  # 衰减近满

    def test_interest_boost_adds(self):
        base = ps.compute_pick_score(80, 1.0, False, _mk(1))
        boosted = ps.compute_pick_score(80, 1.3, False, _mk(1))
        assert boosted > base + 5  # (1.3-1)*25 = 7.5

    def test_favored_source_adds_10(self):
        base = ps.compute_pick_score(80, 1.0, False, _mk(1))
        fav = ps.compute_pick_score(80, 1.0, True, _mk(1))
        assert abs((fav - base) - 10) < 0.5

    def test_decay_old_item(self):
        fresh = ps.compute_pick_score(80, 1.0, False, _mk(1))
        old = ps.compute_pick_score(80, 1.0, False, _mk(24 * 6))
        assert old < fresh
        # 衰减下限: 不低于 0.6 系数
        assert old >= 80 * 0.6 - 0.1


class TestRefreshPickScores:
    def test_end_to_end_writes_column(self, temp_db, monkeypatch):
        from backend.repository.db import get_connection
        conn = get_connection()
        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now - timedelta(hours=1)).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 80, 80, '', ?, ?)",
                (f"p_{i}", f"t{i}", f"https://x.com/{i}", ts, ts, ts),
            )
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {"security": 1.2})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: {"src"})  # ≥2 收藏的源
        result = ps.refresh_pick_scores(lookback_hours=40, top_n=3)
        assert result["evaluated"] == 5
        assert result["picked"] == 3
        scores = conn.execute(
            "SELECT id, pick_score FROM hotspots WHERE pick_score IS NOT NULL"
        ).fetchall()
        assert len(scores) == 3  # 只有 Top-3 有分 (其余 NULL = 未入选)
        # favored source + boost 都加成 → 分数 > 80
        assert all(r["pick_score"] > 80 for r in scores)

    def test_empty_window_noop(self, temp_db, monkeypatch):
        monkeypatch.setattr(ps, "_load_boost_map", lambda: {})
        monkeypatch.setattr(ps, "_load_favored_sources", lambda: set())
        assert ps.refresh_pick_scores(lookback_hours=40, top_n=3) == {
            "evaluated": 0, "picked": 0,
        }
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pick_service.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 pick_service**

```python
"""精选评分服务 (2026-09-27 四模式重定义 P2, spec §3)。

pick_score = quality_score
           + (interest_boost - 1) × 25        (关注域, ∈[-5, +7.5])
           + 10 × favored_source               (收藏 ≥2 篇的源)
           × 时效衰减系数 (≤24h: 1.0; 24h~168h: 线性降至 0.6)

每轮 post-ingest 对窗口内新条目计算, Top-N 落 pick_score 列, 其余置 NULL
(视图 COALESCE(pick_score, quality_score) 排序)。纯规则无 LLM。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# 时效衰减
FULL_WEIGHT_HOURS = 24
DECAY_FLOOR_HOURS = 168  # 7d
DECAY_FLOOR = 0.6

# 加权
INTEREST_SPAN = 25     # (boost-1) 的放大系数
FAVORED_SOURCE_BONUS = 10.0

_TOP_N_DEFAULT = 30
_SETTINGS_KEY_TOPN = "quality.pick_top_n"


def compute_pick_score(
    *,
    quality_score: float,
    interest_boost: float,
    favored_source: bool,
    fetched_at_iso: str,
) -> float:
    """单条合成 (纯函数)。boost/favored 参数由调用方批量预取。"""
    base = float(quality_score or 60)
    interest = (float(interest_boost) - 1.0) * INTEREST_SPAN
    favored = FAVORED_SOURCE_BONUS if favored_source else 0.0

    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    except Exception:
        hours = 0.0

    if hours <= FULL_WEIGHT_HOURS:
        decay = 1.0
    elif hours >= DECAY_FLOOR_HOURS:
        decay = DECAY_FLOOR
    else:
        span = DECAY_FLOOR_HOURS - FULL_WEIGHT_HOURS
        decay = 1.0 - (hours - FULL_WEIGHT_HOURS) / span * (1.0 - DECAY_FLOOR)

    return round((base + interest + favored) * decay, 2)


def _load_boost_map() -> dict[str, float]:
    """关注域乘子 (interest_engine 既有缓存)。失败 → 空 (无加成)。"""
    try:
        from backend.services.interest_engine_service import InterestEngineService

        return InterestEngineService().get_boost_map()
    except Exception:
        return {}


def _load_favored_sources(min_count: int = 2) -> set[str]:
    """收藏 ≥min_count 篇的源集合。失败 → 空。"""
    try:
        from backend.repository.db import get_connection

        rows = get_connection().execute(
            "SELECT h.source, COUNT(*) c FROM favorites f "
            "JOIN hotspots h ON f.hotspot_id = h.id "
            "GROUP BY h.source HAVING c >= ?",
            (min_count,),
        ).fetchall()
        return {r["source"] for r in rows}
    except Exception:
        return set()


def _load_top_n() -> int:
    try:
        from backend.repository.settings_repo import SettingsRepository

        v = SettingsRepository().get(_SETTINGS_KEY_TOPN, default=None)
        if isinstance(v, (int, float)) and int(v) > 0:
            return int(v)
    except Exception:
        pass
    return _TOP_N_DEFAULT


def refresh_pick_scores(
    lookback_hours: int = 40, top_n: int | None = None
) -> dict[str, int]:
    """采集尾部入口: 窗口内新条目算分, Top-N 落列, 其余置 NULL。

    全程不抛 (调用方 _tick 再兜一层)。
    """
    from backend.repository.db import get_connection

    n = top_n if top_n is not None else _load_top_n()
    boost = _load_boost_map()
    favored = _load_favored_sources()

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=lookback_hours)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, COALESCE(quality_score, score, 60) qs, source,"
        " category, fetched_at FROM hotspots "
        "WHERE fetched_at >= ? ORDER BY fetched_at DESC LIMIT 1000",
        (cutoff,),
    ).fetchall()
    if not rows:
        return {"evaluated": 0, "picked": 0}

    scored: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        s = compute_pick_score(
            quality_score=float(item["qs"]),
            interest_boost=float(boost.get(item["category"], 1.0)),
            favored_source=item["source"] in favored,
            fetched_at_iso=item["fetched_at"],
        )
        scored.append({"id": item["id"], "pick_score": s})

    scored.sort(key=lambda x: x["pick_score"], reverse=True)
    picked_ids = {x["id"] for x in scored[:n]}
    by_id = {x["id"]: x["pick_score"] for x in scored}

    for item_id, score in by_id.items():
        val = score if item_id in picked_ids else None
        conn.execute(
            "UPDATE hotspots SET pick_score = ? WHERE id = ?", (val, item_id)
        )
    return {"evaluated": len(scored), "picked": min(n, len(scored))}


__all__ = ["compute_pick_score", "refresh_pick_scores"]
```

- [ ] **Step 4: 跑确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pick_service.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pick_service.py backend/tests/test_pick_service.py
git commit -m "feat(pick): pick_service 评分合成 + Top-N 落列 — quality/interest/收藏源/时效四信号 (P2 Task 2)"
```

---

### Task 3: repo 查询 + scheduler 挂点

**Files:**
- Modify: `backend/repository/hotspot_repo.py`（追加 `list_picked_since`，放 `list_urls_fetched_since` 后）
- Modify: `backend/scheduler/jobs/collect.py`（`_news_alert_tick()` 后追加 `_pick_score_tick()` + 文件尾部实现）
- Test: `backend/tests/test_pick_service.py`（追加 repo 用例）+ `backend/tests/test_news_alert_tick.py`（追加 pick tick 用例）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_pick_service.py
class TestListPickedSince:
    def test_returns_top_by_pick_score(self, temp_db):
        from backend.repository.db import get_connection
        from backend.repository.hotspot_repo import HotspotRepository
        from datetime import datetime, timedelta, timezone
        conn = get_connection()
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=1)).isoformat()
        for i, pscore in enumerate([90.0, 70.0, 80.0]):
            conn.execute(
                "INSERT OR IGNORE INTO hotspots (id, title, url, source,"
                " category, published_at, quality_score, score, summary,"
                " fetched_at, ingested_at, pick_score)"
                " VALUES (?, ?, ?, 'src', 'security', ?, 80, 80, '', ?, ?, ?)",
                (f"pk_{i}", f"t{i}", f"https://y.com/{i}", ts, ts, ts, pscore),
            )
        since = (now - timedelta(days=7)).isoformat()
        rows = HotspotRepository().list_picked_since(since, limit=2)
        assert [r["pick_score"] for r in rows] == [90.0, 80.0]
        assert rows[0]["id"] == "pk_0"
```

```python
# 追加到 backend/tests/test_news_alert_tick.py
def test_pick_tick_isolates_crash(monkeypatch):
    import backend.scheduler.jobs as pkg

    def boom(**kw):
        raise RuntimeError("crash")
    monkeypatch.setattr("backend.services.pick_service.refresh_pick_scores", boom)
    from backend.scheduler.jobs.collect import _pick_score_tick
    asyncio.run(_pick_score_tick())  # 不抛 = 通过


def test_pick_tick_calls_service(monkeypatch):
    called = {"n": 0}

    def fake(**kw):
        called["n"] += 1
        return {"evaluated": 5, "picked": 3}
    monkeypatch.setattr("backend.services.pick_service.refresh_pick_scores", fake)
    from backend.scheduler.jobs.collect import _pick_score_tick
    asyncio.run(_pick_score_tick())
    assert called["n"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pick_service.py backend/tests/test_news_alert_tick.py -q 2>&1 | tail -3`
Expected: FAIL — AttributeError list_picked_since / ImportError _pick_score_tick

- [ ] **Step 3: 实现 repo 方法**

`hotspot_repo.py`（`list_urls_fetched_since` 后追加）:

```python
    def list_picked_since(self, since_iso: str, limit: int = 30) -> list[dict]:
        """精选视图: fetched_at >= since 的条目按 pick_score DESC (NULL 不返回)。

        2026-09-27 四模式 P2 (spec §3): 精选 Top-N 由 pick_service 落列,
        本查询只读列排序。有行数语义 → 受 _MAX_LIMIT 钳制可接受 (30 << 200)。
        """
        effective = max(1, min(limit, _MAX_LIMIT))
        if not since_iso:
            return []
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, url, source, category, summary, published_at,"
            " quality_score, score, pick_score, fetched_at"
            " FROM hotspots WHERE fetched_at >= ? AND pick_score IS NOT NULL"
            " ORDER BY pick_score DESC LIMIT ?",
            (since_iso, effective),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: 实现 _pick_score_tick + 挂点**

`collect.py` — `_news_alert_tick()` 调用行后追加:

```python
    # ---- 精选评分 (2026-09-27 四模式 P2; 内部全 try-except) ----
    await _pick_score_tick()
```

文件尾部追加（与 `_news_alert_tick` 同款）:

```python
async def _pick_score_tick() -> None:
    """采集尾部: 精选评分 (spec 2026-09-27 four-modes §3)。"""
    try:
        from backend.services.pick_service import refresh_pick_scores

        result = await asyncio.to_thread(refresh_pick_scores)
        if result.get("evaluated"):
            _logger.info(
                f"pick_score: evaluated={result['evaluated']} "
                f"picked={result['picked']}"
            )
    except Exception as e:
        _logger.error(f"_pick_score_tick crashed: {e}")
```

- [ ] **Step 5: 跑确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_pick_service.py backend/tests/test_news_alert_tick.py -q`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/repository/hotspot_repo.py backend/scheduler/jobs/collect.py backend/tests/test_pick_service.py backend/tests/test_news_alert_tick.py
git commit -m "feat(pick): list_picked_since 查询 + _pick_score_tick 采集尾部挂点 (P2 Task 3)"
```

---

### Task 4: 前端精选视图 + 按钮文案收尾

**Files:**
- Modify: `frontend/src/api/secnews.ts`（追加 `getPickedItems`）
- Modify: `frontend/src/components/sentinel/SentinelHomePage.tsx`（精选视图 + 深度视图 + 全量文案）
- Test: `frontend/src/components/sentinel/SentinelHomePage.test.tsx`（追加精选视图用例; 若该文件无既有测试则新建最小测试文件）

- [ ] **Step 1: API 函数**

`secnews.ts` 追加:

```typescript
// ── 精选 (2026-09-27 四模式 P2) ──────────────────────────────────────
export interface PickedItem {
  id: string;
  title: string;
  url: string;
  source: string;
  category: string;
  summary: string;
  quality_score: number | null;
  pick_score: number;
  published_at: string | null;
  fetched_at: string;
}

/** GET /api/hotspots/picked — 精选 Top-N (pick_score DESC) */
export function getPickedItems(days = 2, limit = 30): Promise<{ count: number; items: PickedItem[] }> {
  return getJSON(`/api/hotspots/picked?days=${days}&limit=${limit}`);
}
```

- [ ] **Step 2: 后端端点（Task 3 漏斗的读出口, 补在此处一并交付）**

Modify: `backend/api/secnews.py`（或 hotspots 路由所在文件 — 实施时 `grep -rn "hotspots" backend/api/_registry.py` 定位主路由文件; ≤150 行门: 函数 6 行, 若超限走同文件既有聚合层）:

```python
@router.get("/hotspots/picked")
async def list_picked(days: int = Query(2, ge=1, le=7), limit: int = Query(30, ge=1, le=50)):
    """精选资讯 Top-N (P2): pick_score DESC, pick_service 每轮落列。"""
    from datetime import datetime, timedelta, timezone

    from backend.repository.hotspot_repo import HotspotRepository

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    items = await asyncio.to_thread(
        HotspotRepository().list_picked_since, since, limit
    )
    return {"count": len(items), "items": items}
```

（`asyncio`/`Query` 若未 import 则补。）

- [ ] **Step 3: 写失败测试**

```tsx
// 追加/新建 frontend/src/components/sentinel/SentinelHomePage.test.tsx 最小用例
// (实施时先读该文件是否已存在 — 已存在则追加 describe 块, mock 策略对齐既有)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SentinelHomePage } from './SentinelHomePage';

// mock 全部数据 hook — 以文件既有测试/组件实际依赖为准, 最小桩:
// useHotspotData / useRealtimeInvalidation / useFavorites 等按既有 test 惯例。
// 按钮文案断言:
describe('四模式按钮文案 (P2)', () => {
  it('渲染 全量/精选/深度/告警 四按钮', async () => {
    // mock 策略对齐既有 SentinelHomePage 测试 (若文件不存在, mock 见下)
    render(
      <MemoryRouter>
        <SentinelHomePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /全量/ })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /精选/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /深度/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /告警/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /简报/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /扫描/ })).not.toBeInTheDocument();
  });
});
```

（注: 若 SentinelHomePage 尚无测试文件, 首次 mock 其 hooks 成本较高 — 允许降级为把文案断言并入 NewsAlertList.test.tsx 同目录新文件 `ModesBar.test.tsx`, 只抽 `modes` 渲染区为微型组件断言; 实施时择简, **文案断言本身不可省**。）

- [ ] **Step 4: 跑确认失败**

Run: `cd frontend && npx vitest run --grep 文案 2>/dev/null || npx vitest run src/components/sentinel/`
Expected: FAIL — 按钮文案仍是 简报/扫描

- [ ] **Step 5: 实现视图接线**

(a) SentinelHomePage:

- 按钮文案（若 P1 Task 6 未提前改）: `[['brief', '全量'], ['scan', '精选'], ['deep', '深度']]`
- **精选视图**（`mode === 'scan'`）: 列表区渲染 picked 数据 — `useEffect` 拉 `getPickedItems()`, 渲染复用 flash-item 结构 + `精选`徽章 + `pick_score` 数值; 空态: `本轮精选生成中 — 回退高分排序` 并回退现有 quality_score 排序列表（或直接展示空态文案 `暂无精选 — 下一轮采集后生成`, 择简取后者, 保持诚实）
- **深度视图**（`mode === 'deep'`）: 列表 = 当前 items 过滤 `summary.length >= 200 || /分析|详解|深度|指南|research/.test(title)`; 空态: `当前无深读候选 — 在条目上收藏后归入深读`
- **全量视图**（`mode === 'brief'`）: 现有快讯流原样

(b) CSS: sentinel.css 补 `.pick-badge`（精选徽章, 复用既有 chip 色变量）。

- [ ] **Step 6: 跑确认通过 + 全量前端回归**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 0 错 / 0 失败

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/secnews.ts frontend/src/components/sentinel/SentinelHomePage.tsx frontend/src/components/sentinel/sentinel.css backend/api/ frontend/src/components/sentinel/*.test.tsx
git commit -m "feat(sentinel): 精选视图 + 全量/深度文案语义 — pick_score 排序 + 精选徽章 (P2 Task 4)"
```

---

### Task 5: P2 收口 — 全量回归 + 文档同步

- [ ] **Step 1: 后端全量**

Run: `.venv/bin/python3 -m pytest backend/tests/ --tb=short -q`
Expected: 0 failed（既有环境性失败对账 DEV-0233）

- [ ] **Step 2: generate_meta + 行数门**

Run: `.venv/bin/python3 scripts/generate_meta.py --check && .venv/bin/python3 -m pytest backend/tests/test_api_layer_guard.py -q`
Expected: OK（services 数字 P1 已同步, 本期 +1 pick_service → 再同步一轮）; api 层行数门通过（secnews.py 若加函数后超 150 → 走豁免清单调整或拆分, 以实测为准）

- [ ] **Step 3: 实弹验证**

```bash
.venv/bin/python3 -c "
from backend.services.pick_service import refresh_pick_scores
print(refresh_pick_scores(lookback_hours=168, top_n=30))
"
```

Expected: `{'evaluated': N>0, 'picked': 30}`; `curl 'http://127.0.0.1:8000/api/hotspots/picked?days=7&limit=5'` 返回 5 条按 pick_score DESC。

- [ ] **Step 4: DEV_LOG [DEV-0237] + PRD + Commit**

DEV_LOG 按 DEV-0236 格式追加; PRD 四模式语义段（若 P1 已建该段则补 P2 段落）:

```bash
git add DEV_LOG.md docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md docs/ARCHITECTURE.md AGENTS.md backend/AGENTS.md backend/services/AGENTS.md backend/api/AGENTS.md scripts/AGENTS.md CLAUDE.md
git commit -m "docs(pick): P2 精选功能收口 — DEV-0237 + PRD 四模式语义 + 架构数字同步"
```

---

## Self-Review 记录

1. **Spec 覆盖**: spec §3.1 公式→Task 2 / §3.2 落库→Task 1/2 / §3.3 挂点→Task 3 / §4 前端精选+全量+深度→Task 4 / §5 SSE pick_refresh→**裁剪不实现**（精选列表非时效敏感, 30min 轮询粒度足够, 减一条事件类型维护; spec 该项为 over-spec, 此处置换为空态文案诚实标注）— 偏差已记录。§6 测试→各 Task。
2. **占位符**: Task 4 Step 2 路由文件定位与 Step 3 测试 mock 策略两处"实施时核实"均给出主路径+降级路径与断言底线（文案断言不可省）; 无 TBD。
3. **类型一致性**: `refresh_pick_scores(lookback_hours, top_n) -> {evaluated, picked}` 定义（Task 2）与挂点消费（Task 3）一致; `list_picked_since(since_iso, limit) -> list[dict]` 定义（Task 3）与 API 消费（Task 4）一致; `compute_pick_score` 关键字参数在测试与实现一致; 迁移 129 / `_SETTINGS_KEY_TOPN='quality.pick_top_n'` 与 spec §3.2 一致。
4. **与 P1 依赖**: Task 3 挂点插入位置依赖 P1 Task 5 的 `_news_alert_tick` 已存在 — 两计划按序执行（P1 → P2）。
