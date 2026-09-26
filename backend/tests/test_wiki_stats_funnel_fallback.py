"""funnel_from_db → md 真源回退的回归测试 (2026-09-18)。

为什么需要这个文件 (第一性原理: 漏斗必须说真话)
------------------------------------------------
warm.db (923MB, knowledge_items 投影表所在地) 于 2026-09-12/13 之间遗失,
仓库备份只剩 .sha256 校验文件。此后 ``/api/secnews/pipeline`` 的漏斗每 30s
打一条 "no such table: knowledge_items" warning 并**静默返回全 0** ——
UI 呈现的 "管线为空" 是假象, md 真源里明明有 ~4200 条带 lifecycle 的条目。

契约 (2026-09-18 修复): 投影缺失时回退 md 归档口径让漏斗保持可读 —
注意 md 数字与 DB 管线实时口径本就不同 (T1-T5 触发器读写的是 DB),
此为降级展示而非口径替换; 但 "投影没了" 绝不能被报成 "业务为空"。
回退尊重 wiki_fs 注入语义: 显式传 None (SecNewsDashboard 降级注入)
→ 禁用回退保持归零契约; 未传 → 抓 production 单例回退。
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.kl_pipeline.obs.funnel import UNKNOWN_STAGE
from backend.services import wiki_stats_service
from backend.services.wiki_stats_service import (
    funnel_from_db,
    funnel_from_md_cached,
    knowledge_stats_from_db,
    stage_distribution_from_db,
)


class _FakeWikiFs:
    """最小 wiki_fs 替身: 只提供 list_ids / read_item (同 test_kl_funnel_stages)。"""

    def __init__(self, stages: dict[str, str | None]):
        self._stages = stages
        self.scans = 0

    def list_ids(self):
        self.scans += 1
        return list(self._stages)

    def read_item(self, item_id: str):
        lifecycle = self._stages[item_id]
        if lifecycle is None:
            return None
        return {"fm": {"id": item_id, "lifecycle": lifecycle}, "body": ""}


@pytest.fixture
def fake_fs(monkeypatch):
    """注入假 wiki_fs 生产单例 + 清空模块级缓存 (防跨测试污染)。"""
    wiki_stats_service._md_funnel_cache.clear()
    fs = _FakeWikiFs({
        "a": "signal",            # → kl:publish (T2 值域收敛读路径兜底)
        "b": "generate",          # → kl:publish (T2 值域收敛读路径兜底)
        "c": "kl:publish",
        "d": "kl:deduped",        # 终态单列, 不许混进 unknown
        "e": "kl:bogus",          # 值域外
        "f": None,                # 读不出
    })
    monkeypatch.setattr(
        "backend.kl_pipeline.runtime.get_production_wiki_fs", lambda: fs
    )
    yield fs
    wiki_stats_service._md_funnel_cache.clear()


def _conn_without_knowledge_items(tmp_path) -> sqlite3.Connection:
    """无 knowledge_items 表的连接 — 模拟 warm.db 遗失后的投影缺失。"""
    conn = sqlite3.connect(str(tmp_path / "no_projection.db"), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE marker (x INTEGER)")
    return conn


def _as_map(rows: list[dict]) -> dict[str, int]:
    return {r["stage"]: r["count"] for r in rows}


def test_db_projection_missing_falls_back_to_md(fake_fs, tmp_path):
    """投影表不存在时必须回退 md 真源, 而不是静默返回全 0。"""
    funnel = funnel_from_db(_conn_without_knowledge_items(tmp_path))
    counts = _as_map(funnel)

    assert counts["kl:raw"] == 0
    assert counts["kl:structure"] == 0
    assert counts["kl:publish"] == 3, "signal/generate 经 T2 兜底也读作 kl:publish"
    assert sum(counts.values()) == 6, "重新分桶不丢数据"


def test_md_fallback_keeps_deduped_out_of_unknown(fake_fs):
    """kl:deduped 必须单列 — 混进 unknown 会把 '已判重' 显示成 '状态未知'。"""
    counts = _as_map(funnel_from_md_cached(fake_fs))

    assert counts["kl:deduped"] == 1
    assert counts[UNKNOWN_STAGE] == 2, "bogus + 读不出各 1"


def test_stage_distribution_fallback_same_source(fake_fs, tmp_path):
    """stage_distribution (知识库 tab) 与漏斗同源同回退。"""
    dist = stage_distribution_from_db(_conn_without_knowledge_items(tmp_path))

    assert dist["kl:publish"] == 3, "signal/generate 经 T2 兜底也读作 kl:publish"
    assert dist["kl:deduped"] == 1


def test_db_projection_present_still_wins(fake_fs, tmp_path):
    """投影表可用时不许走 md — DB 才是管线实时口径 (T1-T5 读写的就是它)。"""
    conn = sqlite3.connect(str(tmp_path / "with_projection.db"), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE knowledge_items (lifecycle TEXT)")
    conn.executemany(
        "INSERT INTO knowledge_items VALUES (?)",
        [("kl:raw",), ("kl:raw",), ("kl:publish",)],
    )

    counts = _as_map(funnel_from_db(conn))

    assert counts["kl:raw"] == 2
    assert counts["kl:publish"] == 1
    assert fake_fs.scans == 0, "投影可用时不应触碰 md"


def test_knowledge_stats_items_fallback_concepts_survive(fake_fs, tmp_path):
    """items 投影缺失回退 md 总数; main.knowledge_concepts 健在时不被连坐归零
    (2026-09-18 实测: warm 遗失后 concepts 98 条被同一 try 连坐成 0)。"""
    conn = sqlite3.connect(str(tmp_path / "ks.db"), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE knowledge_concepts (id TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO knowledge_concepts VALUES (?)", [("c1",), ("c2",)]
    )

    ks = knowledge_stats_from_db(conn)

    assert ks["items"] == 6, "md 回退条目总数 (fake_fs 共 6 条)"
    assert ks["concepts"] == 2, "concepts 查询独立容错, 不随 items 缺失归零"
    assert ks["stage_distribution"]["kl:publish"] == 3


def test_explicit_none_wiki_fs_disables_fallback(tmp_path):
    """SecNewsDashboard(wiki_fs=None) 注入契约: 显式声明无 md 源 → 禁用回退,
    保持归零; 期间绝不允许抓 production 单例 (否则会扫真实 4200 文件)。"""
    conn = _conn_without_knowledge_items(tmp_path)

    counts = _as_map(funnel_from_db(conn, wiki_fs=None))
    assert all(c == 0 for c in counts.values()), "显式 None 必须保持归零契约"

    dist = stage_distribution_from_db(conn, wiki_fs=None)
    assert dist == {}, "显式 None 保持原 {} 归零契约 (dashboard 测试依赖)"


def test_ttl_cache_avoids_rescan(fake_fs):
    """30s 轮询 × 4200 文件全扫 = 卡顿根治成果倒退; TTL 内必须共享一次扫描。"""
    funnel_from_md_cached(fake_fs)
    funnel_from_md_cached(fake_fs)

    assert fake_fs.scans == 1


def test_invalidate_stats_cache_clears_funnel(fake_fs):
    funnel_from_md_cached(fake_fs)
    wiki_stats_service.invalidate_stats_cache()
    funnel_from_md_cached(fake_fs)

    assert fake_fs.scans == 2, "失效后下一请求必须重扫"
