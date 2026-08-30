"""KL 管线自愈出口回归测试 (队列重试 + graph 形状).

为什么需要这个文件 (第一性原理: 任何终态都必须有出口)
----------------------------------------------------
实测 ``kl_queue`` 全表仅 2 行, 均为 ``status='error'``:

    6467 a379a6f6eeaf kl:structure error attempts=1/5 next_run_at=2026-08-27
    7816 k-gen-1      kl:structure error attempts=1/5 next_run_at=2026-08-28

``due()`` 只取 ``status='pending'``, 而 ``mark_error`` 既不写退避也不比较
``max_attempts`` → 出错即永久搁死 (已卡 2-3 天, attempts 永远 1)。
``enqueue_unique`` 撞 UNIQUE 后的 UPDATE 又带 ``AND status='pending'``, 连
``engine.sweep()`` 兜底重排都是 no-op, 自愈回路形同虚设。

另一半: 生产 ``graph.json`` 的 ``edges`` 是 **list** (实测 96 nodes / 136 edges),
而 structure stage 按 dict 下标写入 → ``list indices must be integers or
slices, not str``, 正是上面那两条 error 的直接来源。

覆盖:
  Q1 未达 max_attempts 的失败 → 回 pending + 退避推迟 next_run_at
  Q2 达到 max_attempts 的失败 → error 终态 (由调用方落死信)
  Q3 退避到期的 pending 行能被 due() 重新取到 (闭环)
  Q4 enqueue_unique 能重新武装 error 行 (sweep 才可能真正自愈)
  Q5 enqueue_unique 不动 running 行 (不抢占执行中的任务)
  G1 list 形状 edges 不再崩溃, 追加带 type 的边且不重复
  G2 dict 形状 edges 保留原语义 (兼容历史图文件)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.kl_pipeline.queue import KLQueue, RETRY_BACKOFF_BASE_S
from backend.kl_pipeline.stages.structure import _upsert_edge


@pytest.fixture
def queue_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE kl_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 5,
            next_run_at TEXT NOT NULL,
            last_error TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, stage)
        )
        """
    )
    conn.commit()
    yield KLQueue(db=conn)
    conn.close()


def _row(q: KLQueue, qid: int) -> sqlite3.Row:
    return q.db.execute("SELECT * FROM kl_queue WHERE id = ?", (qid,)).fetchone()


# ---------------------------------------------------------------------------
# Q1 / Q2 — 失败必须有出口
# ---------------------------------------------------------------------------
def test_mark_error_retries_with_backoff_below_max(queue_db):
    now = datetime.now(timezone.utc)
    queue_db.enqueue_unique("item-a", "kl:structure", now)
    qid = queue_db.due(20)[0]["id"]
    queue_db.mark_run(qid)                      # attempts → 1 (< max 5)

    outcome = queue_db.mark_error(qid, "boom")

    assert outcome == "retry"
    row = _row(queue_db, qid)
    assert row["status"] == "pending", "失败后停在 error 就再也不会被 due() 取到"
    assert datetime.fromisoformat(row["next_run_at"]) > now, "必须退避, 不能热循环重试"
    assert row["last_error"] == "boom"


def test_mark_error_terminal_at_max_attempts(queue_db):
    now = datetime.now(timezone.utc)
    queue_db.enqueue_unique("item-b", "kl:structure", now)
    qid = queue_db.due(20)[0]["id"]
    queue_db.db.execute(
        "UPDATE kl_queue SET attempts = max_attempts, status='running' WHERE id = ?",
        (qid,),
    )

    outcome = queue_db.mark_error(qid, "still broken")

    assert outcome == "terminal", "耗尽重试后必须给出终态信号以便落死信"
    assert _row(queue_db, qid)["status"] == "error"


def test_backoff_row_becomes_due_again(queue_db):
    """闭环: 退避到期的行必须重新进入 due()。"""
    now = datetime.now(timezone.utc)
    queue_db.enqueue_unique("item-c", "kl:link", now)
    qid = queue_db.due(20)[0]["id"]
    queue_db.mark_run(qid)
    queue_db.mark_error(qid, "transient")

    assert queue_db.due(20) == [], "退避期内不该被取走"
    queue_db.db.execute(
        "UPDATE kl_queue SET next_run_at = ? WHERE id = ?",
        ((now - timedelta(seconds=1)).isoformat(), qid),
    )
    assert [r["id"] for r in queue_db.due(20)] == [qid], "退避结束后必须可重试"
    assert RETRY_BACKOFF_BASE_S > 0


# ---------------------------------------------------------------------------
# Q4 / Q5 — 重新入队能否救回搁死行
# ---------------------------------------------------------------------------
def test_enqueue_unique_rearms_error_row(queue_db):
    now = datetime.now(timezone.utc)
    queue_db.enqueue_unique("item-d", "kl:structure", now)
    qid = queue_db.due(20)[0]["id"]
    queue_db.mark_run(qid)
    queue_db.mark_error(qid, "stuck")
    queue_db.db.execute("UPDATE kl_queue SET status='error' WHERE id = ?", (qid,))

    requeued = queue_db.enqueue_unique("item-d", "kl:structure", now)

    assert requeued is True, (
        "旧实现恒返回 False 且 UPDATE 带 AND status='pending' → sweep 对 error 行"
        "是 no-op, 自愈回路形同虚设"
    )
    row = _row(queue_db, qid)
    assert row["status"] == "pending"
    assert row["last_error"] is None


def test_enqueue_unique_leaves_running_row(queue_db):
    now = datetime.now(timezone.utc)
    queue_db.enqueue_unique("item-e", "kl:link", now)
    qid = queue_db.due(20)[0]["id"]
    queue_db.mark_run(qid)                       # status = running

    assert queue_db.enqueue_unique("item-e", "kl:link", now) is False
    assert _row(queue_db, qid)["status"] == "running", "不得抢占正在执行的任务"


# ---------------------------------------------------------------------------
# G1 / G2 — graph.json 两种形状
# ---------------------------------------------------------------------------
def test_upsert_edge_on_list_shaped_graph():
    """生产形状: edges 是 list[dict]。旧实现按 dict 下标写 → TypeError。"""
    graph = {
        "nodes": [{"id": "a"}],
        "edges": [{"source": "x", "target": "y", "weight": 3, "type": "uses"}],
    }

    _upsert_edge(graph, "a", "b")

    assert len(graph["edges"]) == 2
    added = graph["edges"][-1]
    assert added == {"source": "a", "target": "b", "weight": 1.0, "type": "related"}

    _upsert_edge(graph, "a", "b")                # 重复边不得再追加
    assert len(graph["edges"]) == 2


def test_upsert_edge_on_dict_shaped_legacy_graph():
    graph = {"nodes": {}, "edges": {"x->y": {"source": "x", "target": "y", "weight": 2}}}

    _upsert_edge(graph, "x", "y")
    assert len(graph["edges"]) == 1

    _upsert_edge(graph, "a", "b")
    assert graph["edges"]["a->b"]["weight"] == 1.0


def test_upsert_edge_creates_missing_container():
    graph: dict = {}
    _upsert_edge(graph, "a", "b")
    assert isinstance(graph["edges"], list) and len(graph["edges"]) == 1
