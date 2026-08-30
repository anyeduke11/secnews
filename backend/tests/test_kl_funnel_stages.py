"""funnel_stats 阶段归一口径回归测试.

为什么需要这个文件 (第一性原理: 计量口径必须说真话)
--------------------------------------------------
心跳条"管线漏斗"曾显示 ``kl:raw=175``, 而 warm 库里真实的 ``kl:raw`` 只有 **2** 条。
差额来自 ``funnel.py`` 旧实现的兜底分支: 凡是"不认识的值"一律计入 ``kl:raw``。

而 wiki md frontmatter 里至今留着 pre-v1.7 的 lifecycle 值 —— 迁移
``046_v1.7_lifecycle.sql`` 只 UPDATE 了 DB 表, **从未改写 md 文件**（实测
``generate`` 124 / ``signal`` 48 / ``amplify:tagged`` 3，合计正好 175）。
于是 175 个漂移项被伪装成"待判读积压"，真实含义（它们分属 structure/raw/refine
三个阶段）被彻底抹掉。
"""
from __future__ import annotations

from backend.kl_pipeline.obs.funnel import UNKNOWN_STAGE, funnel_stats


class _FakeWikiFs:
    """最小 wiki_fs 替身: 只提供 list_ids / read_item。"""

    def __init__(self, stages: dict[str, str | None]):
        self._stages = stages

    def list_ids(self):
        return list(self._stages)

    def read_item(self, item_id: str):
        lifecycle = self._stages[item_id]
        if lifecycle is None:
            return None  # 文件读不出
        return {"fm": {"id": item_id, "lifecycle": lifecycle}, "body": ""}


def _as_map(rows: list[dict]) -> dict[str, int]:
    return {r["stage"]: r["count"] for r in rows}


def test_legacy_lifecycle_maps_to_v17_stage():
    """pre-v1.7 值必须按迁移 046 的同一张表归位, 而不是堆进 kl:raw。"""
    fs = _FakeWikiFs({
        "a": "signal",            # → kl:raw
        "b": "amplify:tagged",    # → kl:refine
        "c": "generate",          # → kl:structure
        "d": "kl:publish",
        "e": "kl:link",
    })

    counts = _as_map(funnel_stats(fs))

    assert counts["kl:raw"] == 1, "signal 才是 raw；旧实现会把 3 个 legacy 值全算成 raw"
    assert counts["kl:refine"] == 1
    assert counts["kl:structure"] == 1
    assert counts["kl:publish"] == 1
    assert counts["kl:link"] == 1
    assert counts[UNKNOWN_STAGE] == 0


def test_real_wiki_drift_counts_are_preserved():
    """归一后总数必须与归一前一致 —— 重新分桶不是丢数据。"""
    fs = _FakeWikiFs({f"id{i}": ("generate" if i % 2 else "signal") for i in range(20)})

    counts = _as_map(funnel_stats(fs))

    assert counts["kl:raw"] + counts["kl:structure"] == 20
    assert sum(counts.values()) == 20


def test_unknown_value_goes_to_unknown_not_raw():
    """值域外与读不出的项进 unknown，让漂移可见而不是伪装成积压。"""
    fs = _FakeWikiFs({"weird": "kl:bogus", "broken": None, "ok": "kl:raw"})

    counts = _as_map(funnel_stats(fs))

    assert counts[UNKNOWN_STAGE] == 2
    assert counts["kl:raw"] == 1, "真实 kl:raw 不该被无关项顶高"


def test_none_wiki_fs_returns_zero_grid():
    counts = _as_map(funnel_stats(None))
    assert set(counts) >= {"kl:raw", "kl:publish", UNKNOWN_STAGE}
    assert all(v == 0 for v in counts.values())
