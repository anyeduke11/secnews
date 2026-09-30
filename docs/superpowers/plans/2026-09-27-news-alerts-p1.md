# P1 资讯告警落地 (需执行动作的资讯) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 首页「告警」模式从纯前端假告警升级为真告警——4 规则词表筛 + pi LLM 复核判定"需要用户执行动作"的资讯, 落 `alert_events`, 首页展示真告警列表（4 分类 tab + 未读徽标 + 已读/解决）。

**Architecture:** 新服务 `news_alert_service.py` 承载资讯域判定编排（词表筛→去重→单次 pi 复核→落库）, 挂 `collect_all_job` post-ingest 链尾部（与 `_auto_intake_tick` 同款异常隔离模式）; 复用既有 `alert_events` 表（零 DDL, 仅 `alert_rule_definitions` 插 4 行）与 `/api/alerts/v2` 端点（`list_alerts` 加 rule_type 参数一行改动）; 前端 `SentinelHomePage` 告警视图替换假告警区块。fail-open: LLM 失败时词表 ≥2 强信号条目直接放行。

**Tech Stack:** Python 3 / FastAPI / SQLite / pytest; React 18 + TS + Vitest。Spec: `docs/superpowers/specs/2026-09-27-four-modes-redefine-design.md` §2。

**计划阶段核实结论（覆盖 spec 待核实项）:**
1. `_trigger_alert` 签名已核实: `(rule_type, title, description, severity, source=None, source_url=None, item_id=None, project_id=None) -> int`（0=去重跳过）, 自带同 source+rule_type 24h 去重 — CVE 级去重直接复用。
2. `alert_rule_definitions` 无 repo 封装 — 规则行 INSERT 直接走迁移 SQL（alert_engine 也是裸 SQL 查同表）。
3. `list_alerts`/`unread_alert_count` 在 `backend/services/alert_service.py:277/298` — rule_type 过滤加在此层 + `alert_api.py` 透传。
4. hotspots 表 NOT NULL 无默认列: title/source/url/category/published_at/fetched_at — 测试插桩需带全。
5. 迁移编号: 现最大 127 → 本计划用 128。
6. SSE: `publish_event(event_type, data)` async, `publish_collect_done` 同款 try-except + `_spawn` 模式。

---

### Task 1: 迁移 128 — 4 条规则定义 + news_alerts 评估游标 settings

**Files:**
- Create: `backend/repository/migrations/128_news_alert_rules.sql`

- [ ] **Step 1: 写迁移 SQL**

```sql
-- 128_news_alert_rules.sql
-- 2026-09-27 四模式重定义 P1 (spec §2): 资讯告警 4 规则定义。
-- alert_events 零 DDL (13 列够用); 本迁移只插规则定义行, 幂等 (NOT EXISTS)。
INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '需打补丁/排查的漏洞', 'critical_vuln', 1,
       '{"max_per_run": 5, "keywords": ["在野利用", "exploited in the wild", "0day", "零日", "PoC", "概念验证", "紧急补丁", "out-of-band"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'critical_vuln');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '需资产排查/响应的安全事件', 'major_security_event', 1,
       '{"max_per_run": 5, "keywords": ["遭攻击", "hacked", "breach", "数据泄露", "勒索攻击", "供应链攻击", "关基", "critical infrastructure", "APT", "失陷"], "min_signals_alone": 2, "quality_score_gate": 75}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'major_security_event');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT 'AI 资产需行动的事件', 'major_ai_security_event', 1,
       '{"max_per_run": 5, "keywords": ["AI黑客", "AI 黑客", "deepfake", "深度伪造", "提示注入", "prompt injection", "模型投毒", "AI 漏洞", "LLM 漏洞", "MCP 漏洞"], "ai_context_words": ["AI", "LLM", "大模型", "GPT", "Claude", "agent", "智能体"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'major_ai_security_event');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '监管/政策限时执行', 'must_know_regulatory', 1,
       '{"max_per_run": 5, "keywords": ["紧急通报", "公安部", "报送", "等保", "CISA", "advisory"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'must_know_regulatory');
```

- [ ] **Step 2: 验证迁移幂等执行**

Run: `.venv/bin/python3 -c "from backend.repository.db import init_db, close_db; close_db(); init_db(); import sqlite3; from backend.repository.db import get_connection; rows = get_connection().execute('SELECT rule_type, enabled FROM alert_rule_definitions WHERE rule_type LIKE \"%vuln\" OR rule_type LIKE \"%event\" OR rule_type LIKE \"%regulatory\"').fetchall(); print([dict(r) for r in rows])"`
Expected: 4 行, enabled=1

- [ ] **Step 3: Commit**

```bash
git add backend/repository/migrations/128_news_alert_rules.sql
git commit -m "feat(alerts): 迁移 128 — 资讯告警 4 规则定义 (P1 Task 1)"
```

---

### Task 2: 词表筛模块 — `match_rules` 纯函数

**Files:**
- Create: `backend/services/news_alert_service.py`（本 Task 只建词表筛部分）
- Test: `backend/tests/test_news_alert_service.py`

- [ ] **Step 1: 写失败测试**

```python
"""news_alert_service — 资讯告警判定 (spec 2026-09-27 four-modes §2)。

契约:
- match_rules 纯函数: (title, summary, quality_score) → 命中规则 dict 列表
- R3 AI 语境限定: 安全词命中但无 AI 语境词 → 不进 major_ai_security_event
- R2 双信号门槛: 单信号 + quality_score < 75 → 不命中
- config 从 alert_rule_definitions.config JSON 读, 词表可调
"""
import pytest

from backend.services.news_alert_service import match_rules


CFG = {
    "critical_vuln": {"max_per_run": 5, "keywords": ["在野利用", "0day", "PoC", "紧急补丁"]},
    "major_security_event": {
        "max_per_run": 5,
        "keywords": ["数据泄露", "勒索攻击", "供应链攻击", "APT"],
        "min_signals_alone": 2,
        "quality_score_gate": 75,
    },
    "major_ai_security_event": {
        "max_per_run": 5,
        "keywords": ["提示注入", "模型投毒", "MCP 漏洞"],
        "ai_context_words": ["AI", "LLM", "大模型"],
    },
    "must_know_regulatory": {"max_per_run": 5, "keywords": ["紧急通报", "等保", "报送"]},
}


def _hit(rule):
    return rule["rule"]


class TestMatchRules:
    def test_critical_vuln_single_signal_hits(self):
        hits = match_rules("Chrome 0day 在野利用公开", "详情见原文", 80, CFG)
        assert _hit(hits[0]) == "critical_vuln"

    def test_major_event_two_signals_hits(self):
        hits = match_rules("某厂商遭 APT 数据泄露", "大规模供应链攻击背景", 60, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_low_score_misses(self):
        """R2 门槛: 单信号 + score<75 → 不命中 (降噪声)。"""
        hits = match_rules("某小站数据泄露", "无更多背景", 60, CFG)
        assert not any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_high_score_hits(self):
        hits = match_rules("某厂商数据泄露", "背景", 80, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_ai_event_requires_ai_context(self):
        """R3 限定: 安全词命中但无 AI 语境词 → 不命中。"""
        hits = match_rules("新型提示注入攻击手法", "针对传统 Web 框架", 80, CFG)
        assert not any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_ai_event_with_context_hits(self):
        hits = match_rules("针对 LLM 的新型提示注入攻击", "大模型应用受影响", 80, CFG)
        assert any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_regulatory_hits(self):
        hits = match_rules("网信办发布紧急通报", "等保报送时限调整", 70, CFG)
        assert any(_hit(h) == "must_know_regulatory" for h in hits)

    def test_no_match_returns_empty(self):
        assert match_rules("普通 AI 新闻: 新模型发布", "性能提升", 80, CFG) == []

    def test_hit_carries_matched_signals(self):
        hits = match_rules("Chrome 0day 在野利用公开", "", 80, CFG)
        assert set(hits[0]["signals"]) == {"0day", "在野利用"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.news_alert_service'`

- [ ] **Step 3: 实现 match_rules**

```python
"""资讯告警判定服务 (2026-09-27 四模式重定义 P1, spec §2)。

判定漏斗: 词表筛 (本模块 match_rules) → 去重闸 → pi LLM 复核
(review_candidates) → alert_events 落库 (run_news_alert_review)。
词表/阈值从 alert_rule_definitions.config JSON 读, 可经 settings API 调。
"""
from __future__ import annotations

from typing import Any

RuleConfig = dict[str, Any]


def match_rules(
    title: str,
    summary: str,
    quality_score: float,
    config: dict[str, RuleConfig],
) -> list[dict[str, Any]]:
    """对单条资讯跑 4 规则词表筛, 返回命中规则列表。

    每个命中项: {"rule": rule_type, "signals": [命中词], "strength": 命中数}
    - R1/R4: 任一强信号命中即候选
    - R2: ≥min_signals_alone(默认2) 个信号, 或 1 信号 + quality_score ≥ quality_score_gate
    - R3: 安全词命中 **且** title+summary 含 AI 语境词 (双通道限定)
    """
    text = f"{title} {summary}"
    hits: list[dict[str, Any]] = []

    for rule_type, cfg in config.items():
        keywords = cfg.get("keywords", [])
        signals = [kw for kw in keywords if kw in text]
        if not signals:
            continue

        if rule_type == "major_security_event":
            min_alone = int(cfg.get("min_signals_alone", 2))
            gate = float(cfg.get("quality_score_gate", 75))
            if len(signals) < min_alone and quality_score < gate:
                continue
        elif rule_type == "major_ai_security_event":
            context_words = cfg.get("ai_context_words", [])
            if not any(w in text for w in context_words):
                continue

        hits.append(
            {"rule": rule_type, "signals": signals, "strength": len(signals)}
        )
    return hits


__all__ = ["match_rules"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/news_alert_service.py backend/tests/test_news_alert_service.py
git commit -m "feat(alerts): 词表筛 match_rules 纯函数 — 4 规则 + AI 语境限定 + 双信号门槛 (P1 Task 2)"
```

---

### Task 3: pi 复核 — `review_candidates` + fail-open

**Files:**
- Modify: `backend/services/ai_hub/prompts.py`（追加 `_NEWS_ALERT_REVIEW_PROMPT`）
- Modify: `backend/services/news_alert_service.py`（追加 `review_candidates`）
- Test: `backend/tests/test_news_alert_service.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_news_alert_service.py
from backend.services.news_alert_service import review_candidates

CANDS = [
    {"id": "h1", "rule": "critical_vuln", "signals": ["0day", "在野利用"], "title": "Chrome 0day", "summary": "s"},
    {"id": "h2", "rule": "major_security_event", "signals": ["数据泄露"], "title": "某厂商泄露", "summary": "s"},
]


def _mock_llm(monkeypatch, payload=None, fail=False):
    import asyncio
    from backend.services.ai_hub.gateway import llm_service

    async def _gen(prompt, *, task="summary", **kw):
        assert task == "news_alert_review"
        if fail:
            raise RuntimeError("pi down")
        return payload
    monkeypatch.setattr(llm_service, "generate", _gen)


class TestReviewCandidates:
    def test_llm_confirms(self, monkeypatch):
        _mock_llm(monkeypatch, '[{"id": "h1", "execute": true, "reason": "在野利用需排查"}, {"id": "h2", "execute": false}]')
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]
        assert out[0]["reason"] == "在野利用需排查"

    def test_llm_fail_open_strong_signals_pass(self, monkeypatch):
        """fail-open: LLM 挂 → strength ≥2 的候选直接放行, 单信号丢弃。"""
        _mock_llm(monkeypatch, fail=True)
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]  # h1 strength=2, h2 strength=1

    def test_llm_garbage_fail_open(self, monkeypatch):
        _mock_llm(monkeypatch, "不是 JSON 的输出")
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]

    def test_empty_candidates_skips_llm(self, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        assert review_candidates([]) == []
        assert called["n"] == 0
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -k review -v`
Expected: FAIL — ImportError review_candidates

- [ ] **Step 3: prompt 模板**

`backend/services/ai_hub/prompts.py` 模块级追加（风格对齐 `_SEMANTIC_VERDICT_PROMPT`）:

```python
# ── 资讯告警复核 (2026-09-27 四模式 P1, gate 无关 — 常开) ──────────
_NEWS_ALERT_REVIEW_PROMPT = """你是安全资讯告警复核员。以下候选资讯已通过关键词初筛,
请逐条判断:读者(安全从业者/AI 从业者)是否需要**执行某个动作**(打补丁/排查资产/
修改配置/关注后续/参加响应), 而非纯知情。

候选列表 (JSON):
{candidates}

判定标准:
- execute=true: 有明确动作需求 — 如在野利用漏洞需排查版本、供应链投毒需查依赖、
  监管通报有报送时限
- execute=false: 纯知情/观点/行业动态, 无读者动作

只输出 JSON 数组, 不要输出其他文字:
[{{"id": "候选id", "execute": true 或 false, "reason": "一句话理由"}}]"""


def build_news_alert_review_prompt(candidates: list[dict]) -> str:
    import json as _json
    slim = [
        {"id": c["id"], "rule": c["rule"], "title": c["title"][:100],
         "summary": (c.get("summary") or "")[:200]}
        for c in candidates
    ]
    return _NEWS_ALERT_REVIEW_PROMPT.format(candidates=_json.dumps(slim, ensure_ascii=False))
```

`__all__` 追加 `"build_news_alert_review_prompt"`。

- [ ] **Step 4: 实现 review_candidates**

`news_alert_service.py` 追加:

```python
def _parse_review_json(raw: str) -> list[dict] | None:
    """容错解析复核 JSON 数组; 失败返回 None (调用方 fail-open)。"""
    import json as _json
    import re as _re
    try:
        m = _re.search(r"\[.*\]", raw or "", _re.DOTALL)
        if not m:
            return None
        data = _json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except Exception:
        return None


def review_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """pi 复核候选 (spec §2.3): 合并单次调用, execute=true 才告警。

    fail-open: LLM 失败/解析失败 → strength ≥2 (≥2 个词表信号) 的候选
    直接放行, 单信号丢弃 — 宁多报不漏报。
    返回: 确认告警列表 [{id, rule, signals, reason}]。
    """
    if not candidates:
        return []
    import asyncio

    from backend.ai_hub_compat import ai_generate  # 占位 — 实现见 Step 4b
    raw = asyncio.run(ai_generate(candidates))
    confirmed: list[dict[str, Any]] = []
    parsed = _parse_review_json(raw)
    if parsed is None:
        # fail-open
        for c in candidates:
            if c["strength"] >= 2:
                confirmed.append({
                    "id": c["id"], "rule": c["rule"],
                    "signals": c["signals"],
                    "reason": f"llm_fail_open: {len(c['signals'])} 强信号",
                })
        return confirmed
    by_id = {str(v.get("id")): v for v in parsed if isinstance(v, dict)}
    for c in candidates:
        v = by_id.get(str(c["id"]))
        if v and v.get("execute"):
            confirmed.append({
                "id": c["id"], "rule": c["rule"], "signals": c["signals"],
                "reason": str(v.get("reason", ""))[:200],
            })
    return confirmed
```

**Step 4b（上面对象的真实 LLM 调用, 替换占位）**: `_ai_generate` 辅助直接内联到 `review_candidates`（不建 compat 模块）:

```python
# review_candidates 内 `raw = ...` 一行的真实实现:
    def _call_llm() -> str:
        from backend.services.ai_hub.gateway import llm_service
        from backend.services.ai_hub.prompts import (
            build_news_alert_review_prompt,
        )

        return asyncio.run(llm_service.generate(
            build_news_alert_review_prompt(candidates),
            task="news_alert_review",
        ))

    raw = _call_llm()
```

（即: `review_candidates` 顶部 `def _call_llm(): ...` 局部函数, `raw = _call_llm()`; 删除占位 import 行。测试的 monkeypatch 目标是 `backend.services.ai_hub.gateway.llm_service.generate`, 与该调用路径一致。）

- [ ] **Step 5: 跑确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -v`
Expected: 全 PASS（含 Task 2 既有用例）

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai_hub/prompts.py backend/services/news_alert_service.py backend/tests/test_news_alert_service.py
git commit -m "feat(alerts): pi 复核 review_candidates — 合并单次调用 + fail-open (P1 Task 3)"
```

---

### Task 4: 落库编排 — `run_news_alert_review` + 去重冷却

**Files:**
- Modify: `backend/services/news_alert_service.py`（追加 `run_news_alert_review`）
- Test: `backend/tests/test_news_alert_service.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 backend/tests/test_news_alert_service.py
from backend.services.news_alert_service import run_news_alert_review


def _insert_hotspot(item_id, title, summary="", score=80.0, hours_ago=1):
    from backend.repository.db import get_connection
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    get_connection().execute(
        "INSERT OR IGNORE INTO hotspots (id, title, url, source, category,"
        " published_at, quality_score, score, summary, fetched_at, ingested_at)"
        " VALUES (?, ?, ?, '测试源', 'security', ?, ?, ?, ?, ?, ?)",
        (item_id, title, f"https://t.com/{item_id}", ts, score, score,
         summary, ts, ts),
    )


@pytest.fixture
def review_env(temp_db):
    """temp_db + 4 规则行 + mock LLM 全确认。"""
    from backend.repository.db import init_db, close_db
    close_db(); init_db()
    from backend.repository.db import get_connection
    get_connection().executescript(open(
        "backend/repository/migrations/128_news_alert_rules.sql", encoding="utf-8"
    ).read())
    yield
    close_db(); init_db()


class TestRunNewsAlertReview:
    def test_end_to_end_inserts_alert_events(self, review_env, monkeypatch):
        _insert_hotspot("h_a1", "Chrome 0day 在野利用", "需紧急排查", 85)
        _mock_llm(monkeypatch, '[{"id": "h_a1", "execute": true, "reason": "需排查"}]')
        result = run_news_alert_review(lookback_hours=40)
        assert result["alerted"] == 1
        from backend.repository.db import get_connection
        row = get_connection().execute(
            "SELECT * FROM alert_events WHERE item_id = 'h_a1'"
        ).fetchone()
        assert row is not None
        assert row["rule_type"] == "critical_vuln"
        assert row["severity"] == "critical"
        assert "需排查" in row["description"]

    def test_same_hotspot_not_realerted(self, review_env, monkeypatch):
        _insert_hotspot("h_b1", "Chrome 0day 在野利用", "s", 85)
        _mock_llm(monkeypatch, '[{"id": "h_b1", "execute": true, "reason": "r"}]')
        run_news_alert_review(lookback_hours=40)
        result2 = run_news_alert_review(lookback_hours=40)  # 同条目还在窗口内
        assert result2["alerted"] == 0  # 去重闸

    def test_max_per_run_cap(self, review_env, monkeypatch):
        for i in range(7):
            _insert_hotspot(f"h_c{i}", f"漏洞{i} 0day 在野利用", "s", 85)
        _mock_llm(monkeypatch, '[' + ",".join(
            f'{{"id": "h_c{i}", "execute": true, "reason": "r"}}' for i in range(7)
        ) + ']')
        result = run_news_alert_review(lookback_hours=40)
        assert result["alerted"] == 5  # max_per_run

    def test_no_candidates_zero_llm_calls(self, review_env, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        result = run_news_alert_review(lookback_hours=40)
        assert result == {"candidates": 0, "alerted": 0}
        assert called["n"] == 0

    def test_window_excludes_old_items(self, review_env, monkeypatch):
        _insert_hotspot("h_d1", "Chrome 0day 在野利用", "s", 85, hours_ago=72)
        _mock_llm(monkeypatch, "[]")
        result = run_news_alert_review(lookback_hours=40)
        assert result["candidates"] == 0  # 72h 前的条目不在窗口
```

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -k run_news -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 实现 run_news_alert_review**

`news_alert_service.py` 追加:

```python
def _load_rule_config() -> dict[str, RuleConfig]:
    """从 alert_rule_definitions 读 4 规则 config JSON (enabled=1)。"""
    import json as _json

    from backend.repository.db import get_connection

    rows = get_connection().execute(
        "SELECT rule_type, config FROM alert_rule_definitions "
        "WHERE enabled = 1 AND rule_type IN "
        "('critical_vuln','major_security_event',"
        "'major_ai_security_event','must_know_regulatory')"
    ).fetchall()
    out: dict[str, RuleConfig] = {}
    for r in rows:
        try:
            cfg = _json.loads(r["config"]) if r["config"] else {}
        except Exception:
            cfg = {}
        out[r["rule_type"]] = cfg
    return out


def run_news_alert_review(lookback_hours: int = 40) -> dict[str, int]:
    """采集尾部入口 (spec §2.1 漏斗编排)。全程不抛 — 调用方 (_tick) 再兜一层。

    Returns: {"candidates": 词表筛候选数, "alerted": 实际落 alert_events 数}
    """
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=lookback_hours)).isoformat()
    rows = get_connection().execute(
        "SELECT id, title, COALESCE(summary,'') summary, quality_score, source,"
        " url FROM hotspots "
        "WHERE fetched_at >= ? AND category IN ('security','ai_security','ai') "
        "ORDER BY fetched_at DESC LIMIT 500",
        (cutoff,),
    ).fetchall()

    config = _load_rule_config()
    if not config:
        return {"candidates": 0, "alerted": 0}

    # 词表筛
    candidates: list[dict[str, Any]] = []
    seen_hotspots: set[str] = set()
    for r in rows:
        item = dict(r)
        if item["id"] in seen_hotspots:
            continue
        # 去重闸: 该 hotspot 已告警过 → 跳过
        dup = get_connection().execute(
            "SELECT 1 FROM alert_events WHERE item_id = ? LIMIT 1",
            (item["id"],),
        ).fetchone()
        if dup:
            continue
        hits = match_rules(
            item["title"], item["summary"],
            float(item["quality_score"] or 0), config,
        )
        for h in hits:
            candidates.append({
                "id": item["id"], "rule": h["rule"], "signals": h["signals"],
                "strength": h["strength"], "title": item["title"],
                "summary": item["summary"], "source": item["source"],
                "url": item["url"], "quality_score": item["quality_score"],
            })
    seen_hotspots = {c["id"] for c in candidates}

    confirmed = review_candidates(candidates)
    alerted = 0
    per_rule: dict[str, int] = {}
    for c in confirmed:
        cap = int(config.get(c["rule"], {}).get("max_per_run", 5))
        if per_rule.get(c["rule"], 0) >= cap:
            continue
        per_rule[c["rule"]] = per_rule.get(c["rule"], 0) + 1

        from backend.services.alert_engine import AlertEngine

        engine = AlertEngine()
        sev = "critical" if c["rule"] == "critical_vuln" else (
            "medium" if c["rule"] == "must_know_regulatory" else "high"
        )
        item_row = next(x for x in candidates if x["id"] == c["id"])
        new_id = engine._trigger_alert(
            rule_type=c["rule"],
            title=item_row["title"][:200],
            description=(
                f"{c['reason']} | {item_row['summary'][:200]}"
            ),
            severity=sev,
            source=item_row["source"],
            source_url=item_row["url"],
            item_id=c["id"],
        )
        if new_id:
            alerted += 1

    if alerted:
        _publish_news_alert_sse(alerted)
    return {"candidates": len(candidates), "alerted": alerted}


def _publish_news_alert_sse(alerted: int) -> None:
    """SSE news_alert 事件 (outbox 由 publish_event 调用方决定, 此处直推)。"""
    try:
        import asyncio

        from backend.core.events import publish_event
        asyncio.get_event_loop().run_until_complete(
            publish_event("news_alert", {"count": alerted})
        ) if False else None
        # 与 publish_collect_done 同款: spawn 协程而非阻塞
        import backend.services.collection_pipeline as _cp

        _cp._spawn(asyncio.ensure_future(
            publish_event("news_alert", {"count": alerted})
        ))
    except Exception:
        pass  # SSE 失败不影响告警落库
```

（注: `_publish_news_alert_sse` 中首个 run_until_complete 行是废稿 — 最终实现只保留 `_spawn` 分支, 写代码时删掉该行与 `if False else None`。）

- [ ] **Step 4: 跑确认通过**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_service.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/news_alert_service.py backend/tests/test_news_alert_service.py
git commit -m "feat(alerts): run_news_alert_review 编排 — 窗口拉取/去重闸/max_per_run/落库/SSE (P1 Task 4)"
```

---

### Task 5: scheduler 挂点 + API rule_type 过滤

**Files:**
- Modify: `backend/scheduler/jobs/collect.py:45`（`_auto_intake_tick()` 后追加 `_news_alert_tick()`）+ 文件尾部追加 `_news_alert_tick`
- Modify: `backend/services/alert_service.py:277-303`（`list_alert_events`/`unread_alert_count` 加 rule_type 过滤）
- Modify: `backend/api/alert_api.py:31-46`（两端点透传 rule_type）
- Test: `backend/tests/test_news_alert_tick.py`（新）

- [ ] **Step 1: 写失败测试**

```python
"""_news_alert_tick — 采集尾部挂点 (异常隔离契约)。

契约: news_alert_service 崩溃时 _tick 不抛 (不阻塞 post-ingest 链);
成功时 log 计数。
"""
import asyncio


def test_tick_isolates_crash(monkeypatch):
    import backend.scheduler.jobs as pkg

    def boom(**kw):
        raise RuntimeError("service crashed")
    monkeypatch.setattr(
        "backend.services.news_alert_service.run_news_alert_review", boom
    )
    # _tick 内部 to_thread(run_news_alert_review) — monkeypatch 模块函数即可
    from backend.scheduler.jobs.collect import _news_alert_tick
    asyncio.run(_news_alert_tick())  # 不抛 = 通过


def test_tick_calls_service(monkeypatch):
    import backend.scheduler.jobs as pkg
    called = {"n": 0}

    def fake(**kw):
        called["n"] += 1
        return {"candidates": 1, "alerted": 1}
    monkeypatch.setattr(
        "backend.services.news_alert_service.run_news_alert_review", fake
    )
    from backend.scheduler.jobs.collect import _news_alert_tick
    asyncio.run(_news_alert_tick())
    assert called["n"] == 1
```

（注: `_news_alert_tick` 实现里 `from ... import run_news_alert_review` 放函数体内 lazy import — 与 `_auto_intake_tick` 同款, monkeypatch 才能命中。）

- [ ] **Step 2: 跑确认失败**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_tick.py -v`
Expected: FAIL — ImportError `_news_alert_tick`

- [ ] **Step 3: 实现 tick + 挂点**

`collect.py` L45 `_auto_intake_tick()` 之后追加一行 `await _news_alert_tick()`（注释: `# ---- 资讯告警评估 (2026-09-27 四模式 P1; 内部全 try-except) ----`）; 文件尾部追加:

```python
async def _news_alert_tick() -> None:
    """采集尾部: 资讯告警评估 (spec 2026-09-27 four-modes §2.1)。

    词表筛+pi 复核"需执行动作"资讯 → alert_events。run_news_alert_review
    全程不抛; 此处再兜一层异常隔离, 与 post-ingest 链各 job 模式一致。
    """
    try:
        from backend.services.news_alert_service import run_news_alert_review

        result = await asyncio.to_thread(run_news_alert_review)
        if result.get("alerted"):
            _logger.info(
                f"news_alert: candidates={result['candidates']} "
                f"alerted={result['alerted']}"
            )
    except Exception as e:
        _logger.error(f"_news_alert_tick crashed: {e}")
```

- [ ] **Step 4: alert_service + api 加 rule_type**

`backend/services/alert_service.py` — `list_alert_events` 签名加 `rule_type: str | None = None`, 函数体 severity 块后加:

```python
    if rule_type:
        sql += " AND rule_type = ?"
        params.append(rule_type)
```

`unread_alert_count` 改为可带规则域过滤:

```python
NEWS_ALERT_RULE_TYPES = (
    "critical_vuln", "major_security_event",
    "major_ai_security_event", "must_know_regulatory",
)


def unread_alert_count(rule_types: tuple[str, ...] | None = None) -> int:
    """未读告警数. rule_types 给定时仅统计这些规则 (资讯告警与项目告警分离)."""
    if rule_types:
        marks = ",".join("?" for _ in rule_types)
        row = get_connection().execute(
            f"SELECT COUNT(*) AS c FROM alert_events "
            f"WHERE status = 'unread' AND rule_type IN ({marks})",
            rule_types,
        ).fetchone()
    else:
        row = get_connection().execute(
            "SELECT COUNT(*) AS c FROM alert_events WHERE status = 'unread'"
        ).fetchone()
    return int(row["c"])
```

`backend/api/alert_api.py` — `list_alerts` 签名加 `rule_type: str | None = Query(None)` 并透传; `unread_count` 加 `scope: str = Query("all")`（`scope == "news"` 时传 `NEWS_ALERT_RULE_TYPES`）:

```python
@router.get("/unread-count")
def unread_count(scope: str = Query("all")):
    """未读告警数. scope=news → 仅资讯告警 4 规则 (首页徽标用)."""
    from backend.services.alert_service import NEWS_ALERT_RULE_TYPES

    if scope == "news":
        return {"count": unread_alert_count(rule_types=NEWS_ALERT_RULE_TYPES)}
    return {"count": unread_alert_count()}
```

（`Query` 已在该文件 import 区。）

- [ ] **Step 5: 跑确认通过 + 域回归**

Run: `.venv/bin/python3 -m pytest backend/tests/test_news_alert_tick.py backend/tests/test_news_alert_service.py backend/tests/ -k "alert" -q`
Expected: 全 PASS（既有 alert 用例 rule_type 默认 None 不受影响）

- [ ] **Step 6: Commit**

```bash
git add backend/scheduler/jobs/collect.py backend/services/alert_service.py backend/api/alert_api.py backend/tests/test_news_alert_tick.py
git commit -m "feat(alerts): 采集尾部 _news_alert_tick 挂点 + API rule_type/scope 过滤 (P1 Task 5)"
```

---

### Task 6: 前端告警视图替换假告警

**Files:**
- Modify: `frontend/src/api/secnews.ts`（追加 `getNewsAlerts` / `getNewsAlertUnread` / `markAlertRead` / `markAllAlertsRead` / `resolveAlert`）
- Modify: `frontend/src/components/sentinel/SentinelHomePage.tsx`（按钮文案 + 告警视图 + 撤假告警）
- Create: `frontend/src/components/sentinel/NewsAlertList.tsx`（告警列表组件）
- Test: `frontend/src/components/sentinel/NewsAlertList.test.tsx`

- [ ] **Step 1: API 函数（secnews.ts 追加）**

```typescript
// ── 资讯告警 (2026-09-27 四模式 P1, /api/alerts/v2) ──────────────────
export interface NewsAlertEvent {
  id: number;
  rule_type: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium';
  source: string | null;
  source_url: string | null;
  item_id: string | null;
  status: string;
  created_at: string;
}

export const ALERT_RULE_LABELS: Record<string, string> = {
  critical_vuln: '漏洞',
  major_security_event: '安全事件',
  major_ai_security_event: 'AI 安全事件',
  must_know_regulatory: '合规时限',
};

export function getNewsAlerts(ruleType?: string): Promise<{ count: number; items: NewsAlertEvent[] }> {
  const qs = ruleType ? `?rule_type=${encodeURIComponent(ruleType)}&limit=100` : '?limit=100';
  return getJSON(`/api/alerts/v2${qs}`);
}

export function getNewsAlertUnread(): Promise<{ count: number }> {
  return getJSON('/api/alerts/v2/unread-count?scope=news');
}

export function markAlertRead(id: number): Promise<unknown> {
  return putJSON(`/api/alerts/v2/${id}/read`);
}

export function markAllAlertsRead(): Promise<unknown> {
  return putJSON('/api/alerts/v2/read-all');
}

export function resolveAlert(id: number): Promise<unknown> {
  return putJSON(`/api/alerts/v2/${id}/resolve`);
}
```

（`getJSON` 已在该文件 import; `putJSON` 若无则从 `../../lib/api` 补 import — 实施时核实该文件既有 import 区, 若 lib/api 无 putJSON 则用 `fetch(..., {method:'PUT'})` 封装, 与文件内既有写 mutations 的方式保持一致。）

- [ ] **Step 2: NewsAlertList 组件失败测试**

```tsx
/**
 * NewsAlertList — 资讯告警列表 (2026-09-27 四模式 P1)
 * 意图: 4 分类 tab + severity 色条 + reason 展示 + 已读/解决; 空态诚实。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NewsAlertList } from './NewsAlertList';

const ALERTS = {
  count: 2,
  items: [
    { id: 1, rule_type: 'critical_vuln', title: 'Chrome 0day 在野利用',
      description: '需排查 | 详见原文', severity: 'critical', source: 'FreeBuf',
      source_url: 'https://f.com/1', item_id: 'h1', status: 'unread',
      created_at: '2026-09-27T10:00:00' },
    { id: 2, rule_type: 'must_know_regulatory', title: '等保报送时限',
      description: '限时报送', severity: 'medium', source: '监管',
      source_url: null, item_id: null, status: 'unread',
      created_at: '2026-09-27T09:00:00' },
  ],
};

function makeFetch() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/alerts/v2/unread-count')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 2 }) } as Response);
    }
    if (url.startsWith('/api/alerts/v2')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(ALERTS) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('NewsAlertList — 资讯告警列表', () => {
  beforeEach(() => { vi.stubGlobal('fetch', makeFetch()); });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('渲染告警条目与 severity 标识', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/Chrome 0day/)).toBeInTheDocument());
    expect(screen.getByText(/等保报送/)).toBeInTheDocument();
    expect(screen.getByText('漏洞')).toBeInTheDocument();      // rule_type 标签
    expect(screen.getByText('合规时限')).toBeInTheDocument();
  });

  it('分类 tab 过滤: 点「漏洞」只看 critical_vuln', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => screen.getByText(/Chrome 0day/));
    fireEvent.click(screen.getByRole('tab', { name: /漏洞/ }));
    await waitFor(() => {
      const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .filter((c: unknown[]) => String(c[0]).includes('rule_type=critical_vuln'));
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('全部已读按钮触发 PUT', async () => {
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => screen.getByText(/Chrome 0day/));
    fireEvent.click(screen.getByRole('button', { name: /全部已读/ }));
    await waitFor(() => {
      const puts = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .filter((c: unknown[]) => String(c[1]?.method ?? '').toUpperCase() === 'PUT'
          && String(c[0]).includes('read-all'));
      expect(puts.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('空态诚实: 无告警时提示自动扫描', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/alerts/v2/unread-count')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 0 }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ count: 0, items: [] }) } as Response);
    }));
    render(<MemoryRouter><NewsAlertList /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/当前无可执行告警/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: 跑确认失败**

Run: `cd frontend && npx vitest run src/components/sentinel/NewsAlertList.test.tsx`
Expected: FAIL — 模块不存在

- [ ] **Step 4: 实现 NewsAlertList**

```tsx
/**
 * NewsAlertList — 资讯告警列表 (2026-09-27 四模式 P1, spec §4)
 *
 * 数据: GET /api/alerts/v2?rule_type= (4 规则域, 不含 CodeGarden 项目告警)。
 * 操作: tab 过滤 / 单条已读 / 全部已读 / 解决。severity 色条 + rule_type 标签
 * + description 首段 (LLM reason | 摘要)。
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getNewsAlerts, markAlertRead, markAllAlertsRead, resolveAlert,
  ALERT_RULE_LABELS,
  type NewsAlertEvent,
} from '../../api/secnews';

const TABS: Array<{ key: string; label: string }> = [
  { key: '', label: '全部' },
  { key: 'critical_vuln', label: '漏洞' },
  { key: 'major_security_event', label: '安全事件' },
  { key: 'major_ai_security_event', label: 'AI 安全事件' },
  { key: 'must_know_regulatory', label: '合规时限' },
];

const SEV_CLASS: Record<string, string> = {
  critical: 'sev-critical', high: 'sev-high', medium: 'sev-medium',
};

export function NewsAlertList() {
  const [items, setItems] = useState<NewsAlertEvent[] | null>(null);
  const [tab, setTab] = useState('');
  const nav = useNavigate();

  const reload = useCallback(async (ruleType: string) => {
    try {
      const d = await getNewsAlerts(ruleType || undefined);
      setItems(d.items ?? []);
    } catch { setItems([]); }
  }, []);

  useEffect(() => { void reload(tab); }, [tab, reload]);

  const openHref = (a: NewsAlertEvent) =>
    a.source_url && /^https?:\/\//.test(a.source_url) ? a.source_url : null;

  if (items === null) {
    return <div className="news-alert-list"><p className="na-empty">载入中…</p></div>;
  }
  return (
    <div className="news-alert-list">
      <div className="na-head">
        <div className="na-tabs" role="tablist">
          {TABS.map(t => (
            <button key={t.key} role="tab" aria-selected={tab === t.key}
              className={`na-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => setTab(t.key)}>{t.label}</button>
          ))}
        </div>
        <div className="na-ops">
          <button className="abtn" onClick={() => { void markAllAlertsRead().then(() => reload(tab)); }}>全部已读</button>
        </div>
      </div>
      {items.length === 0 ? (
        <p className="na-empty">当前无可执行告警 — 系统每轮采集后自动扫描</p>
      ) : (
        <ul className="na-items">
          {items.map(a => (
            <li key={a.id} className={`na-item ${SEV_CLASS[a.severity] ?? ''}${a.status === 'unread' ? ' unread' : ''}`}>
              <div className="na-bar">
                <span className="na-sev">{a.severity}</span>
                <span className="na-rule">{ALERT_RULE_LABELS[a.rule_type] ?? a.rule_type}</span>
                <span className="na-time">{a.created_at.slice(5, 16).replace('T', ' ')}</span>
              </div>
              <div className="na-title">{a.title}</div>
              <div className="na-desc">{a.description}</div>
              <div className="na-src">{a.source ?? ''}</div>
              <div className="na-actions">
                {a.item_id && (
                  <button className="abtn" onClick={() => nav(`/deep/hotspot/${a.item_id}`)}>进入深读</button>
                )}
                {openHref(a) && (
                  <button className="abtn" onClick={() => window.open(openHref(a)!, '_blank', 'noopener')}>查看原文</button>
                )}
                {a.status === 'unread' && (
                  <button className="abtn" onClick={() => { void markAlertRead(a.id).then(() => reload(tab)); }}>已读</button>
                )}
                <button className="abtn" onClick={() => { void resolveAlert(a.id).then(() => reload(tab)); }}>解决</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

CSS: `sentinel.css` 追加 `.na-*` / `.sev-critical|high|medium` 色条类（critical=`--alert-red` / high=橙 / medium=黄, 用既有 CSS 变量; 具体变量名实施时从 sentinel.css 既有 alert-badge 色值对齐）。

- [ ] **Step 5: 跑确认通过**

Run: `cd frontend && npx vitest run src/components/sentinel/NewsAlertList.test.tsx`
Expected: 4 PASS

- [ ] **Step 6: SentinelHomePage 装配**

(a) 按钮文案: L352 modes 数组 `[['brief', '简报'], ['scan', '扫描'], ['deep', '深度']]` → `[['brief', '全量'], ['scan', '精选'], ['deep', '深度']]`（P1 只改文案, 视图行为 P2 接; 「告警」按钮 L354 不动）。

(b) 告警视图: 快讯流 `<ul className="flash-list">` 区块改为 `mode === 'alert' ? <NewsAlertList /> : (原快讯流 JSX)`; 删除 `alertItem` useMemo（L323-328）与"高危告警 (可展开)"整块 JSX（L539-580 区, 含 alert-detail）及相关 CSS 类引用。头部副标题 `SentinelShell mode` prop 不动（壳层心跳条与 mode 无关）。

(c) 未读徽标: 「告警」按钮内追加:

```tsx
{newsUnread > 0 && <span className="alert-unread-badge" aria-label={`${newsUnread} 条未读告警`}>{newsUnread}</span>}
```

`newsUnread` 状态: `useEffect` 拉 `getNewsAlertUnread()` + `useRealtimeInvalidation` 监听 `news_alert` 事件类型刷新（`SSE_EVENTS` 若无该常量则直接用字符串 `'news_alert'` 并在同批把类型常量补进 `SSE_EVENTS`）。

- [ ] **Step 7: 全量前端回归**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 0 错 / 0 失败（nav4_shell 等守卫不受影响 — 无路由变更）

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/secnews.ts frontend/src/components/sentinel/NewsAlertList.tsx frontend/src/components/sentinel/NewsAlertList.test.tsx frontend/src/components/sentinel/SentinelHomePage.tsx frontend/src/components/sentinel/sentinel.css
git commit -m "feat(sentinel): 告警模式接真告警列表 — 4 tab/未读徽标/已读解决, 撤假告警 (P1 Task 6)"
```

---

### Task 7: P1 收口 — 全量回归 + DEV_LOG

- [ ] **Step 1: 后端全量**

Run: `.venv/bin/python3 -m pytest backend/tests/ --tb=short -q`
Expected: 0 failed（唯一允许: test_check_temp_db_sizes 既有环境性失败, 如出现须与 DEV-0233 记录对账）

- [ ] **Step 2: generate_meta**

Run: `.venv/bin/python3 scripts/generate_meta.py --check`
Expected: services 数字 +1（news_alert_service）→ 若 MISMATCH 跑 `generate_meta.py` 同步 ARCHITECTURE.md + 4 个 AGENTS.md + CLAUDE.md 后复检 OK

- [ ] **Step 3: 实弹验证**

后端起服（owner 环境已在跑则跳过）→ `POST /api/alerts/v2/evaluate` 不适用（那是旧引擎）; 直调:

```bash
.venv/bin/python3 -c "
from backend.services.news_alert_service import run_news_alert_review
print(run_news_alert_review(lookback_hours=168))  # 首轮 7d 回看
"
```

Expected: `{'candidates': N>0, 'alerted': M>=0}`; `GET /api/alerts/v2/unread-count?scope=news` 返回 M; 校对室不受影响。

- [ ] **Step 4: DEV_LOG [DEV-0236] + Commit**

按 DEV-0235 格式追加（关联 spec §2 + 本计划 + 改动文件清单 + 实弹证据）:

```bash
git add DEV_LOG.md docs/ARCHITECTURE.md AGENTS.md backend/AGENTS.md backend/services/AGENTS.md backend/api/AGENTS.md CLAUDE.md
git commit -m "docs(alerts): P1 资讯告警落地收口 — DEV-0236 + 架构数字同步"
```

---

## Self-Review 记录

1. **Spec 覆盖**: spec §2.1 漏斗→Task 4/5 / §2.2 词表→Task 1(配置)+Task 2(逻辑) / §2.3 复核协议→Task 3 / §2.4 去重冷却→Task 4（hotspot 去重闸 + `_trigger_alert` 自带 24h source 去重 + max_per_run）/ §2.5 数据契约→Task 1 / §2.6 API→Task 5 / §4 前端告警部分→Task 6（按钮文案全量/精选部分属 P2, Task 6 Step 6a 只改文案先行）/ §5 SSE→Task 4 `_publish_news_alert_sse` + Task 6 徽标监听 / §6 测试→各 Task。spec §3 精选 / §4 精选与深度视图 → **不在本计划**（P2 另立）。
2. **占位符**: Task 3 Step 4 的 `ai_generate` 占位已在 Step 4b 显式给出替换实现并标注"写代码时删除占位行"; Task 6 putJSON 与 CSS 变量两处"实施时核实"均给出核对方法与备选路径; Task 4 `_publish_news_alert_sse` 废稿行已标注删除。
3. **类型一致性**: `match_rules(title, summary, quality_score, config)` 在 Task 2 定义与 Task 4 消费一致; `review_candidates(candidates) -> [{id, rule, signals, reason}]` 定义/消费一致; `strength` 字段 Task 2 产出 → Task 3 fail-open 消费一致; `NEWS_ALERT_RULE_TYPES` Task 5 定义 → Task 6 徽标 scope=news 一致; 4 个 rule_type 字符串在迁移/服务/API/前端五处拼写一致。
