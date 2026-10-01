# 拒收日志人话化 + 迁设置运维区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校对室拒收日志的 reason 列从裸 flag 列表转为用户可读解释（词典兜底 + pi 批量人话），日志整体迁至 设置→运维 区，/quality 页收缩为纯校对总览。

**Architecture:** 双层解释——前端词典常量（10 flag 全映射，零成本恒可用）+ 后端 post-ingest 第 3 个 tick（`_rejection_explain_tick`，与 `_news_alert_tick`/`_pick_score_tick` 同款异常隔离模式）每轮合并单次 pi 调用为 `explain IS NULL` 的拒收行批量生成中文解释回填新列。迁移 130 加 `explain TEXT` 列；API 零改动（`SELECT *` 自动带新列）。

**Tech Stack:** Python 3 / SQLite / pytest; React 18 + TS + Vitest。Spec: `docs/superpowers/specs/2026-10-01-rejection-explain-design.md`。

**计划阶段核实结论（覆盖 spec 待核实项）:**
1. `query_rejection_log` 列选择 = `SELECT *` → 迁移后 explain 列自动透出，service 层零改动（spec §5 待核实项关闭）。
2. `QualityRejectionPage.tsx` 263 行，无独立测试文件（测试在 `QualityDashboardPage.test.tsx` 内, 仅测 redirect 组件不测页面本体）→ 删除时断言迁移面小。
3. `LayerTable` 位于 `frontend/src/components/layout/LayerTable.tsx`，RejectionLogCard 复用其 import 路径 `../layout/LayerTable`（从 settings/ 目录出发）。
4. 迁移编号 130（当前最大 129）。
5. `quality_rejection_log` 表列: id, source_id, item_title, item_url, rejected_by, reason, raw_data, created_at (+explain)。
6. `/quality/rejection` redirect 现走 `QueryMergeRedirect`；改为 `Navigate` 直跳 `/settings?cat=ops`。
7. api 层禁 import repository（hotspots.py 先例）——本计划 API 零新增零改动，不受影响。

---

### Task 1: 迁移 130 — explain 列

**Files:**
- Create: `backend/repository/migrations/130_rejection_explain.sql`

- [ ] **Step 1: 写迁移 SQL**

```sql
-- 130_rejection_explain.sql
-- 2026-10-01 拒收日志人话化 (spec 2026-10-01-rejection-explain §5):
-- LLM 批量解释回填列。可空 — NULL = 待生成/生成失败(下轮重试), 前端词典兜底。
ALTER TABLE quality_rejection_log ADD COLUMN explain TEXT;
```

- [ ] **Step 2: 验证列存在**

Run: `.venv/bin/python3 -c "
from backend.repository.db import close_db, init_db
close_db(); init_db()
from backend.repository.db import get_connection
cols = [r['name'] for r in get_connection().execute('PRAGMA table_info(quality_rejection_log)').fetchall()]
assert 'explain' in cols, cols
print('OK:', cols)
"`
Expected: `OK: [... 'explain']`

- [ ] **Step 3: Commit**

```bash
git add backend/repository/migrations/130_rejection_explain.sql
git commit -m "feat(rejection): 迁移 130 — quality_rejection_log.explain 列 (人话解释回填)"
```

---

### Task 2: 词典映射模块（前端常量）

**Files:**
- Create: `frontend/src/lib/rejectionReasons.ts`
- Test: `frontend/src/lib/rejectionReasons.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
/**
 * rejectionReasons — 拒收 flag 词典 + reason 解析 (spec §3)。
 * 意图: 词典兜底层恒可用 — LLM explain 未生成时每条记录仍可读。
 */
import { describe, it, expect } from 'vitest';
import {
  REJECTION_FLAG_LABELS,
  parseRejectionFlags,
  flagLabel,
} from './rejectionReasons';

describe('rejectionReasons — 拒收词典', () => {
  it('10 个生产 flag 全部有映射', () => {
    const REQUIRED = [
      'content_hash_duplicate', 'url_duplicate', 'similar_title_duplicate',
      'category_mismatch', 'title_summary_inconsistent', 'empty_summary',
      'empty_title', 'author_unknown', 'title_spam_words', 'noise_title',
    ];
    for (const f of REQUIRED) {
      expect(REJECTION_FLAG_LABELS[f], `missing: ${f}`).toBeTruthy();
    }
  });

  it('parseRejectionFlags: 裸数组形态', () => {
    expect(
      parseRejectionFlags("['category_mismatch', 'content_hash_duplicate']"),
    ).toEqual(['category_mismatch', 'content_hash_duplicate']);
  });

  it('parseRejectionFlags: flags= 形态 (strict_mode 写入)', () => {
    expect(parseRejectionFlags("flags=['content_hash_duplicate']"))
      .toEqual(['content_hash_duplicate']);
  });

  it('parseRejectionFlags: 空与垃圾输入 → 空数组', () => {
    expect(parseRejectionFlags('')).toEqual([]);
    expect(parseRejectionFlags('noise_title')).toEqual(['noise_title']);
  });

  it('flagLabel: 已知 flag → 中文; 未知 flag 原样', () => {
    expect(flagLabel('content_hash_duplicate')).toBe('与已收录内容重复');
    expect(flagLabel('some_new_flag')).toBe('some_new_flag');
  });
});
```

- [ ] **Step 2: 跑确认失败**

Run: `cd frontend && npx vitest run src/lib/rejectionReasons.test.ts`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现**

```ts
/**
 * rejectionReasons — 拒收 flag 词典 + reason 解析 (2026-10-01 spec §3)。
 *
 * 词典是兜底层: LLM explain (quality_rejection_log.explain 列) 未生成/
 * 失败时, 前端仍可展示每条拒因的可读解释。多 flag 组合全列出,
 * 首项 (主拒因) 由展示层加粗。
 */
export const REJECTION_FLAG_LABELS: Record<string, string> = {
  content_hash_duplicate: '与已收录内容重复',
  url_duplicate: '链接已收录过',
  similar_title_duplicate: '标题与已有条目高度相似',
  category_mismatch: '内容与分类关键词不匹配',
  title_summary_inconsistent: '标题与摘要对不上',
  empty_summary: '摘要为空',
  empty_title: '标题为空',
  author_unknown: '作者无法验证',
  title_spam_words: '标题含营销/低质词',
  noise_title: '标题属噪音内容(备案/版权/招聘等)',
};

/** reason 字符串 → flag 数组。兼容两种生产形态:
 *  "['a', 'b']" (strict_mode/score_below_min) 与 "flags=['a']" (duplicate)。
 *  非 flag 词 (flags/=) 不在词典且不匹配 snake_case 白名单式提取规则时丢弃。 */
export function parseRejectionFlags(reason: string): string[] {
  if (!reason) return [];
  const known = new Set(Object.keys(REJECTION_FLAG_LABELS));
  const tokens = reason.match(/[a-z][a-z_]+/g) ?? [];
  // 只保留: 词典已知 flag 或形如 gate flag 的 snake_case 词 (未知新 flag 原样展示的前提)
  return tokens.filter(t => t !== 'flags' && (known.has(t) || t.includes('_')));
}

/** flag → 中文标签; 未知 flag 原样返回。 */
export function flagLabel(flag: string): string {
  return REJECTION_FLAG_LABELS[flag] ?? flag;
}
```

- [ ] **Step 4: 跑确认通过**

Run: `cd frontend && npx vitest run src/lib/rejectionReasons.test.ts`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/rejectionReasons.ts frontend/src/lib/rejectionReasons.test.ts
git commit -m "feat(rejection): 拒收 flag 词典映射 + reason 解析 (兜底层)"
```

---

### Task 3: LLM 批量解释服务

**Files:**
- Modify: `backend/services/ai_hub/prompts.py`（追加 `build_rejection_explain_prompt`）
- Create: `backend/services/rejection_explain_service.py`
- Test: `backend/tests/test_rejection_explain_service.py`

- [ ] **Step 1: 写失败测试**

```python
"""rejection_explain_service — 拒收日志 LLM 批量解释 (spec §4)。

契约:
- explain IS NULL 的行批量取 (LIMIT), 合并单次 pi 调用, 逐行回填
- 空积压 → 零 LLM 调用
- LLM 挂/解析失败 → explain 保持 NULL (下轮重试), 返回 {"explained": 0}
- 只更新解析结果中 id 匹配且 explain 非空的行 (防毒化)
"""
import pytest

from backend.services import rejection_explain_service as res


def _mock_llm(monkeypatch, payload=None, fail=False):
    import asyncio
    from backend.services.ai_hub.gateway import llm_service

    async def _gen(prompt, *, task="summary", **kw):
        assert task == "rejection_explain"
        if fail:
            raise RuntimeError("pi down")
        return payload
    monkeypatch.setattr(llm_service, "generate", _gen)


def _insert_rejection(item_id_title: str, reason: str, explain: str | None = None) -> int:
    from backend.repository.db import get_connection

    cur = get_connection().execute(
        "INSERT INTO quality_rejection_log"
        " (source_id, item_title, item_url, rejected_by, reason, raw_data,"
        "  created_at, explain) VALUES ('s', ?, 'u', 'strict_mode', ?, '',"
        " datetime('now'), ?)",
        (item_id_title, reason, explain),
    )
    return cur.lastrowid


class TestRunRejectionExplain:
    def test_empty_backlog_zero_llm_calls(self, temp_db, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        assert res.run_rejection_explain() == {"explained": 0}
        assert called["n"] == 0

    def test_batch_generates_and_backfills(self, temp_db, monkeypatch):
        id1 = _insert_rejection("Chrome 0day 爆出", "['category_mismatch']")
        id2 = _insert_rejection("某厂商泄露", "['empty_summary', 'author_unknown']")
        _mock_llm(monkeypatch, (
            f'[{{"id": {id1}, "explain": "内容与安全分类不相关"}},'
            f' {{"id": {id2}, "explain": "摘要为空且作者未知, 疑似低质"}}]'
        ))
        result = res.run_rejection_explain()
        assert result == {"explained": 2}
        from backend.repository.db import get_connection
        rows = get_connection().execute(
            "SELECT id, explain FROM quality_rejection_log ORDER BY id"
        ).fetchall()
        assert rows[0]["explain"] == "内容与安全分类不相关"
        assert rows[1]["explain"] == "摘要为空且作者未知, 疑似低质"

    def test_llm_failure_keeps_null_for_retry(self, temp_db, monkeypatch):
        _insert_rejection("t", "['noise_title']")
        _mock_llm(monkeypatch, fail=True)
        assert res.run_rejection_explain() == {"explained": 0}
        from backend.repository.db import get_connection
        row = get_connection().execute(
            "SELECT explain FROM quality_rejection_log LIMIT 1"
        ).fetchone()
        assert row["explain"] is None  # 保持 NULL 待下轮

    def test_garbage_output_keeps_null(self, temp_db, monkeypatch):
        _insert_rejection("t", "['noise_title']")
        _mock_llm(monkeypatch, "完全不是 JSON")
        assert res.run_rejection_explain() == {"explained": 0}

    def test_already_explained_rows_skipped(self, temp_db, monkeypatch):
        _insert_rejection("old", "['noise_title']", explain="已有解释")
        _mock_llm(monkeypatch, "[]")
        assert res.run_rejection_explain() == {"explained": 0}
        # explain 已存在的行不被触碰 (IS NULL 过滤)

    def test_batch_limit_respected(self, temp_db, monkeypatch):
        for i in range(5):
            _insert_rejection(f"t{i}", "['noise_title']")
        _mock_llm(monkeypatch, "[]")
        res.run_rejection_explain(batch_limit=3)  # 不抛; LIMIT 生效由 SQL 保证

    def test_prompt_contains_title_and_flags(self, temp_db, monkeypatch):
        from backend.services.ai_hub.prompts import build_rejection_explain_prompt
        _insert_rejection("Chrome 0day 爆出", "['category_mismatch']")
        prompt = build_rejection_explain_prompt([
            {"id": 1, "title": "Chrome 0day 爆出", "reason": "['category_mismatch']"},
        ])
        assert "Chrome 0day 爆出" in prompt
        assert "category_mismatch" in prompt
        assert "60" in prompt  # 字数上限要求
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_rejection_explain_service.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: prompt 模板**

`backend/services/ai_hub/prompts.py` 模块级追加（风格对齐既有 `build_news_alert_review_prompt`）:

```python
# ── 拒收日志解释 (2026-10-01 rejection-explain, 常开无 gate) ─────────
_REJECTION_EXPLAIN_PROMPT = """你是资讯质量门禁的解释员。以下条目被采集质量门禁拒收,
请根据标题与拒收 flag, 为每条生成一句面向普通用户的中文解释 (≤60字),
说清它为什么被拒 — 语气客观, 不评判读者, 不堆术语。

拒收条目 (JSON):
{items}

flag 参考含义: content_hash_duplicate=内容重复 / category_mismatch=分类不匹配 /
title_summary_inconsistent=标题摘要不一致 / empty_summary=摘要为空 /
author_unknown=作者无法验证 / title_spam_words=标题营销词 / noise_title=噪音标题

只输出 JSON 数组, 不要输出其他文字:
[{{"id": 条目id, "explain": "一句中文解释"}}]"""


def build_rejection_explain_prompt(items: list[dict]) -> str:
    import json as _json

    slim = [
        {"id": it["id"], "title": (it.get("title") or "")[:100],
         "flags": (it.get("reason") or "")[:120]}
        for it in items
    ]
    return _REJECTION_EXPLAIN_PROMPT.format(
        items=_json.dumps(slim, ensure_ascii=False)
    )
```

`__all__` 追加 `"build_rejection_explain_prompt"`。

- [ ] **Step 4: 实现服务**

```python
"""拒收日志 LLM 批量解释服务 (2026-10-01 spec §4)。

post-ingest 尾部 _rejection_explain_tick 调用: 为 explain IS NULL 的
quality_rejection_log 行合并单次 pi 调用生成中文解释。词典兜底在前端
(rejectionReasons.ts), 本服务失败不写坏数据 — explain 保持 NULL 下轮重试。
"""
from __future__ import annotations

from typing import Any


def run_rejection_explain(batch_limit: int = 200) -> dict[str, int]:
    """批量解释入口。全程不抛; 返回 {"explained": N}。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, item_title, reason FROM quality_rejection_log "
        "WHERE explain IS NULL ORDER BY id DESC LIMIT ?",
        (batch_limit,),
    ).fetchall()
    if not rows:
        return {"explained": 0}

    items = [
        {"id": r["id"], "title": r["item_title"], "reason": r["reason"]}
        for r in rows
    ]
    parsed = _call_and_parse(items)
    if not parsed:
        return {"explained": 0}

    explained = 0
    for v in parsed:
        if not isinstance(v, dict):
            continue
        rid, text = v.get("id"), v.get("explain")
        if rid is None or not text or not str(text).strip():
            continue
        conn.execute(
            "UPDATE quality_rejection_log SET explain = ? WHERE id = ? "
            "AND explain IS NULL",
            (str(text).strip()[:200], rid),
        )
        explained += 1
    return {"explained": explained}


def _call_and_parse(items: list[dict[str, Any]]) -> list[Any] | None:
    """单次 LLM 调用 + 容错解析; 任何失败返回 None (调用方按 0 处理)。"""
    import asyncio
    import json as _json
    import re as _re

    try:
        from backend.services.ai_hub.gateway import llm_service
        from backend.services.ai_hub.prompts import (
            build_rejection_explain_prompt,
        )

        raw = asyncio.run(llm_service.generate(
            build_rejection_explain_prompt(items),
            task="rejection_explain",
        ))
        m = _re.search(r"\[.*\]", raw or "", _re.DOTALL)
        if not m:
            return None
        data = _json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except Exception:
        return None


__all__ = ["run_rejection_explain"]
```

- [ ] **Step 5: 跑确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_rejection_explain_service.py -v`
Expected: 7 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai_hub/prompts.py backend/services/rejection_explain_service.py backend/tests/test_rejection_explain_service.py
git commit -m "feat(rejection): LLM 批量解释服务 — 单次调用回填 explain, 失败保持 NULL 重试"
```

---

### Task 4: 采集尾部挂点

**Files:**
- Modify: `backend/scheduler/jobs/collect.py`（`_pick_score_tick()` 调用行后追加 + 文件尾部实现）
- Test: `backend/tests/test_rejection_explain_service.py`（追加 tick 用例）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_rejection_explain_service.py
class TestExplainTick:
    def test_tick_isolates_crash(self, monkeypatch):
        import asyncio

        def boom(**kw):
            raise RuntimeError("service crashed")
        monkeypatch.setattr(
            "backend.services.rejection_explain_service.run_rejection_explain",
            boom,
        )
        from backend.scheduler.jobs.collect import _rejection_explain_tick
        asyncio.run(_rejection_explain_tick())  # 不抛 = 通过

    def test_tick_calls_service(self, monkeypatch):
        import asyncio

        called = {"n": 0}

        def fake(**kw):
            called["n"] += 1
            return {"explained": 3}
        monkeypatch.setattr(
            "backend.services.rejection_explain_service.run_rejection_explain",
            fake,
        )
        from backend.scheduler.jobs.collect import _rejection_explain_tick
        asyncio.run(_rejection_explain_tick())
        assert called["n"] == 1
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_rejection_explain_service.py -k tick -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 实现挂点**

`collect.py` — `await _pick_score_tick()` 行后追加:

```python
    # ---- 拒收日志解释 (2026-10-01 rejection-explain; 内部全 try-except) ----
    await _rejection_explain_tick()
```

文件尾部追加（与 `_pick_score_tick` 同款）:

```python
async def _rejection_explain_tick() -> None:
    """采集尾部: 拒收日志 LLM 解释回填 (spec 2026-10-01-rejection-explain §4.1)。"""
    try:
        from backend.services.rejection_explain_service import (
            run_rejection_explain,
        )

        result = await asyncio.to_thread(run_rejection_explain)
        if result.get("explained"):
            _logger.info(f"rejection_explain: explained={result['explained']}")
    except Exception as e:
        _logger.error(f"_rejection_explain_tick crashed: {e}")
```

- [ ] **Step 4: 跑确认通过 + 域回归**

Run: `.venv/bin/python3 -m pytest backend/tests/test_rejection_explain_service.py backend/tests/test_news_alert_tick.py backend/tests/test_pick_service.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scheduler/jobs/collect.py backend/tests/test_rejection_explain_service.py
git commit -m "feat(rejection): 采集尾部 _rejection_explain_tick 挂点 (第 3 个同款 tick)"
```

---

### Task 5: 设置页 RejectionLogCard + /quality 收缩 + redirect

**Files:**
- Create: `frontend/src/components/settings/RejectionLogCard.tsx`
- Test: `frontend/src/components/settings/RejectionLogCard.test.tsx`
- Modify: `frontend/src/components/settings/SettingsPage.tsx`（ops 区装配）
- Modify: `frontend/src/components/quality/QualityDashboardPage.tsx`（删 rejection tab）
- Modify: `frontend/src/components/quality/QualityDashboardPage.test.tsx`（redirect 断言更新）
- Modify: `frontend/src/routes/index.tsx`（/quality/rejection redirect 改向）
- Delete: `frontend/src/components/QualityRejectionPage.tsx`
- Modify: `frontend/src/routes/ROUTE_REGISTRY.md`（同步行）

- [ ] **Step 1: 写失败测试（RejectionLogCard）**

```tsx
/**
 * RejectionLogCard — 拒收日志卡 (设置→运维, spec §6)。
 * 意图: reason 列双层解释 — explain (LLM 人话) 有则显 + 词典 flag 标签恒显。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RejectionLogCard } from './RejectionLogCard';

const LOG = {
  total: 2,
  page: 1,
  page_size: 50,
  items: [
    { id: 1, source_id: 'FreeBuf', item_title: 'Chrome 0day 在野利用',
      item_url: 'https://f.com/1', rejected_by: 'duplicate',
      reason: "flags=['content_hash_duplicate']", raw_data: '',
      created_at: '2026-10-01 10:00:00', explain: '与已收录的内容重复, 无需再次入库' },
    { id: 2, source_id: '安全客', item_title: '每周资讯播报',
      item_url: 'https://a.com/2', rejected_by: 'strict_mode',
      reason: "['empty_summary', 'category_mismatch']", raw_data: '',
      created_at: '2026-10-01 09:00:00', explain: null },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    if (String(input).startsWith('/api/quality/rejection-log')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(LOG) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('RejectionLogCard — 拒收日志卡', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染标题与副标题 (自动生成解释说明)', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('拒收日志')).toBeInTheDocument());
    expect(screen.getByText(/每轮采集后自动生成解释/)).toBeInTheDocument();
  });

  it('explain 非空行显示 LLM 人话; 空行只有词典兜底', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/与已收录的内容重复/)).toBeInTheDocument());
    // 第二行 explain=null → 不显示人话, 但词典标签存在
    expect(screen.getByText('摘要为空')).toBeInTheDocument();
    expect(screen.getByText('内容与分类关键词不匹配')).toBeInTheDocument();
  });

  it('主拒因 (首 flag) 加粗', async () => {
    render(<MemoryRouter><RejectionLogCard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('摘要为空')).toBeInTheDocument());
    const el = screen.getByText('摘要为空');
    expect(el.closest('b, strong, [data-main-flag]')).not.toBeNull();
  });
});
```

- [ ] **Step 2: 跑确认失败**

Run: `cd frontend && npx vitest run src/components/settings/RejectionLogCard.test.tsx`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 RejectionLogCard**

```tsx
/**
 * RejectionLogCard — 拒收日志卡 (2026-10-01 spec §6, 设置→运维第 4 卡)。
 *
 * 数据: GET /api/quality/rejection-log (分页 + 源/日期筛选, 复用原
 * QualityRejectionPage 的查询形态)。reason 列双层解释:
 * explain (LLM 人话) 有则首行显示; 词典 flag 标签 (rejectionReasons) 恒显小字。
 */
import { useCallback, useEffect, useState } from 'react';
import { LayerTable, type LayerTableColumn } from '../layout/LayerTable';
import { getJSON } from '../../lib/api';
import { parseRejectionFlags, flagLabel } from '../../lib/rejectionReasons';

interface RejectionLogItem {
  id: number;
  source_id: string;
  item_title: string;
  item_url: string;
  rejected_by: string;
  reason: string;
  explain: string | null;
  created_at: string;
}

const PAGE_SIZE = 20;

export function RejectionLogCard() {
  const [items, setItems] = useState<RejectionLogItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const reload = useCallback(async (p: number) => {
    try {
      const d = await getJSON<{ total: number; items: RejectionLogItem[] }>(
        `/api/quality/rejection-log?page=${p}&page_size=${PAGE_SIZE}`,
      );
      setItems(d.items ?? []);
      setTotal(d.total ?? 0);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => { void reload(page); }, [page, reload]);

  const columns: LayerTableColumn<RejectionLogItem>[] = [
    { key: 'created_at', label: '时间', render: row => (
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {row.created_at?.slice(5, 16)}
      </span>
    ) },
    { key: 'source_id', label: '来源', render: row => (
      <span className="max-w-[120px] truncate inline-block" title={row.source_id}>
        {row.source_id}
      </span>
    ) },
    { key: 'item_title', label: '标题', render: row => (
      <a href={row.item_url} target="_blank" rel="noopener noreferrer"
         className="max-w-[240px] truncate inline-block hover:underline">
        {row.item_title}
      </a>
    ) },
    { key: 'reason', label: '拒收原因', render: row => (
      <div className="max-w-[280px]">
        {row.explain && (
          <div className="text-xs" style={{ color: 'var(--text-primary)' }}>
            {row.explain}
          </div>
        )}
        <div className="flex flex-wrap gap-1 text-[10px]"
             style={{ color: 'var(--text-muted)' }}>
          {parseRejectionFlags(row.reason).map((f, i) => (
            <span key={f} data-main-flag={i === 0 || undefined}
                  style={{ fontWeight: i === 0 ? 600 : 400 }}>
              {flagLabel(f)}
            </span>
          ))}
        </div>
      </div>
    ) },
  ];

  return (
    <div className="st-card">
      <h3>拒收日志</h3>
      <p className="st-section-desc">
        采集质量门禁的拒收审计 · 每轮采集后自动生成解释
      </p>
      {items === null ? (
        <p className="st-cellnote">载入中…</p>
      ) : items.length === 0 ? (
        <p className="st-cellnote">暂无拒收记录。</p>
      ) : (
        <LayerTable
          columns={columns}
          rows={items}
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}
```

（注: `LayerTable` 的 props 以 `frontend/src/components/layout/LayerTable.tsx` 实际签名为准 — 实施时先读该文件, 若 props 名不同 (如 `onPage`) 以实际为准调整, **双层解释的渲染结构不变**。）

- [ ] **Step 4: 跑确认通过**

Run: `cd frontend && npx vitest run src/components/settings/RejectionLogCard.test.tsx`
Expected: 3 PASS

- [ ] **Step 5: SettingsPage 装配**

`SettingsPage.tsx` `case 'ops'` 块内 `DshControlCard` 后追加:

```tsx
            <RejectionLogCard />
```

import 区追加 `import { RejectionLogCard } from './RejectionLogCard';`。

- [ ] **Step 6: /quality 收缩 + redirect + 删除**

(a) `QualityDashboardPage.tsx`:
- `TABS` 删 `{ key: 'rejection', label: '拒绝样本' }` → 只剩 `[{ key: 'overview', label: '校对总览' }]`
- `TabKey` 改 `'overview'`; `tab` 推导行简化为 `'overview'`; `setSearchParams` 的 rejection 分支删除
- 删 `import QualityRejectionPage from '../QualityRejectionPage';` 与 `tab === 'rejection'` 渲染分支
- 头注释 L8-9 的「拒绝样本子标签」描述更新为「拒绝样本已迁 设置→运维 (2026-10-01)」

(b) `routes/index.tsx`: `/quality/rejection` 行改:

```tsx
        <Route path="/quality/rejection" element={<Navigate to="/settings?cat=ops" replace />} />
```

（`Navigate` 已 import; `QueryMergeRedirect` 若因此处无人使用仍被其他路由引用则保留, 仅改本行。）

(c) `QualityDashboardPage.test.tsx`: A5 describe 块（`/quality/rejection → /quality?tab=rejection` 断言）改为断言新 redirect 目标 `/settings?cat=ops`（渲染 `<Navigate to="/settings?cat=ops" replace />` 于同结构 MemoryRouter, 断言 location.pathname === '/settings' && search 含 cat=ops）, describe 标题注明「2026-10-01 迁设置运维区」。

(d) Delete `frontend/src/components/QualityRejectionPage.tsx`（用 DeleteFile）。

(e) `ROUTE_REGISTRY.md`: `/quality/rejection` 行的 redirect 目标同步为 `/settings?cat=ops`。

- [ ] **Step 7: 全量前端回归**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 0 错 / 0 失败（nav4_shell 守卫全绿 — 无路由删除仅 redirect 变更）

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/settings/RejectionLogCard.tsx frontend/src/components/settings/RejectionLogCard.test.tsx frontend/src/components/settings/SettingsPage.tsx frontend/src/components/quality/QualityDashboardPage.tsx frontend/src/components/quality/QualityDashboardPage.test.tsx frontend/src/routes/index.tsx frontend/src/routes/ROUTE_REGISTRY.md
git rm frontend/src/components/QualityRejectionPage.tsx
git commit -m "feat(rejection): 拒收日志迁设置运维区 — 双层解释渲染 + /quality 收缩 + redirect"
```

---

### Task 6: 收口 — 全量回归 + 实弹 + 文档同步

- [ ] **Step 1: 后端全量**

Run: `.venv/bin/python3 -m pytest backend/tests/ --tb=short -q`
Expected: 0 failed（唯一允许: test_check_temp_db_sizes 既有环境性失败）

- [ ] **Step 2: generate_meta 数字同步**

Run: `.venv/bin/python3 scripts/generate_meta.py --check`
Expected: services 152→153 MISMATCH → 跑 `generate_meta.py` + 手改五处文档（ARCHITECTURE.md 三处 / AGENTS.md / CLAUDE.md 两处 / backend/services/AGENTS.md / scripts/AGENTS.md 的 `152 services` → `153 services`）→ 复检 OK

- [ ] **Step 3: 实弹验证**

```bash
.venv/bin/python3 -c "
from backend.services.rejection_explain_service import run_rejection_explain
print(run_rejection_explain(batch_limit=50))
"
```

Expected: `{'explained': N>0}`（生产库积压首批 50 行）; 二次调用返回递减（IS NULL 过滤幂等）。抽查 DB `SELECT item_title, explain FROM quality_rejection_log WHERE explain IS NOT NULL LIMIT 3` 人话质量。

- [ ] **Step 4: DEV_LOG [DEV-0238] + PRD + Commit**

DEV_LOG 按 DEV-0237 格式（关联 spec + 本计划 + 改动清单 + 实弹证据）; PRD §2.4 追加一句（拒收日志迁设置 + 人话解释双层）:

```bash
git add DEV_LOG.md docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md docs/ARCHITECTURE.md AGENTS.md CLAUDE.md backend/services/AGENTS.md scripts/AGENTS.md
git commit -m "docs(rejection): 拒收日志人话化收口 — DEV-0238 + 架构数字同步 153 services"
```

---

## Self-Review 记录

1. **Spec 覆盖**: §3 词典→Task 2 / §4.1 挂点→Task 4 / §4.2 编排→Task 3 / §4.3 护栏→Task 3 (LIMIT/NULL 保持/幂等用例) / §5 迁移→Task 1 + SELECT * 零改动核实结论(头部) / §6 日志卡→Task 5 / §7 收缩+redirect→Task 5 Step 6 / §8 测试→各 Task / §10 文档→Task 6。spec §9 非目标无对应任务（正确）。
2. **占位符**: Task 5 Step 3 的 LayerTable props 留"以实际签名为准"并给出核对文件与不变式（双层解释结构）; Task 5 Step 6(b) QueryMergeRedirect 保留与否给出判定条件。无 TBD。
3. **类型一致性**: `run_rejection_explain(batch_limit=200) -> {"explained": N}` 定义（Task 3）与挂点消费（Task 4）一致; `parseRejectionFlags`/`flagLabel` 定义（Task 2）与 RejectionLogCard 消费（Task 5）一致; `build_rejection_explain_prompt` 定义（Task 3 Step 3）与测试/服务消费一致; 迁移列名 `explain` 在 SQL/服务/前端接口五处一致; `data-main-flag` 属性与测试断言一致。
