"""Phase 47: collector 时效门禁集成测试 — 模拟嘶吼 (4hou.com) 源典型场景。

覆盖场景
--------
- 嘶吼 HTML 抓取混合 batch: 当周 / 缺失 / 历史 published_at
- 缺失 published_at → 拒收 (避免 fallback 到 now 污染首页)
- 历史 published_at → 拒收
- 当周 published_at → 通过
- _build_items 错误处理不抛异常
- HTML 解析器对 4hou.com 风格的链接 / 标题兼容
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category
from backend.utils.business_days import current_week_start


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class _TestSecCollector(BaseCollector):
    """安全分类 collector, 用于模拟嘶吼."""

    category = Category.SECURITY
    _skip_quality = True
    max_items = 50
    name = "test_sihou"


def _sihou_source():
    return {"name": "嘶吼", "url": "https://www.4hou.com/", "score": 70}


# ---------------------------------------------------------------------------
# 嘶吼典型场景
# ---------------------------------------------------------------------------
class TestSihouScenario:
    """模拟嘶吼首页抓到的混合 batch."""

    def test_current_week_articles_pass(self):
        """嘶吼抓到的 5 条当周新资讯 (页面级 published_at = 抓取前几小时) → 通过."""
        c = _TestSecCollector()
        now_utc = datetime.now(timezone.utc)
        raw = [
            {
                "title": f"嘶吼安全资讯第 {i} 期: 某 APT 组织最新活动分析",
                "url": f"https://www.4hou.com/post/{i}",
                "published_at": now_utc - timedelta(hours=i),
            }
            for i in range(5)
        ]
        items = c._build_items(raw, _sihou_source())
        assert len(items) == 5
        for it in items:
            assert it.source == "嘶吼"
            assert it.category == Category.SECURITY

    def test_missing_published_at_rejected(self):
        """嘶吼抓到的 20 条, HTML 没提取到发布时间 → 全部拒收.

        旧行为: ``published_at = raw.get("published_at") or now`` → 当 fetch time 入库
                 → 历史资讯被当「当周新资讯」混入首页
        新行为 (Phase 47): ``published_at is None`` → 拒收 (宁缺毋滥)
        """
        c = _TestSecCollector()
        raw = [
            {
                "title": f"嘶吼历史资讯第 {i} 期: 某 RDP 漏洞",
                "url": f"https://www.4hou.com/post/old{i}",
                # no published_at
            }
            for i in range(20)
        ]
        items = c._build_items(raw, _sihou_source())
        assert len(items) == 0

    def test_historical_published_at_rejected(self):
        """嘶吼抓到的 5 条历史资讯 (URL slug 是 2025 年) → 全部拒收."""
        c = _TestSecCollector()
        week_start = current_week_start()
        # 3 个月前 / 6 个月前 / 1 年前
        old_dates = [
            week_start - timedelta(days=90),
            week_start - timedelta(days=180),
            week_start - timedelta(days=365),
        ]
        raw = [
            {
                "title": f"嘶吼历史资讯: 某安全事件 (发布于 {d.date()})",
                "url": f"https://www.4hou.com/post/h{i}",
                "published_at": d,
            }
            for i, d in enumerate(old_dates)
        ]
        items = c._build_items(raw, _sihou_source())
        assert len(items) == 0

    def test_mixed_batch_only_current_week_passes(self):
        """混合 batch: 5 条当周 + 10 条缺失 + 5 条历史 → 只 5 条当周通过."""
        c = _TestSecCollector()
        now_utc = datetime.now(timezone.utc)
        week_start = current_week_start()

        raw = []

        # 5 条当周资讯
        for i in range(5):
            raw.append({
                "title": f"嘶吼当周新资讯第 {i} 期: 某 CVE 漏洞",
                "url": f"https://www.4hou.com/post/new{i}",
                "published_at": now_utc - timedelta(hours=i),
            })

        # 10 条缺失 published_at (HTML 抓不到时间)
        for i in range(10):
            raw.append({
                "title": f"嘶吼提取不到时间的资讯第 {i} 期",
                "url": f"https://www.4hou.com/post/miss{i}",
            })

        # 5 条历史资讯
        for i in range(5):
            raw.append({
                "title": f"嘶吼历史资讯第 {i} 期: 旧事件",
                "url": f"https://www.4hou.com/post/old{i}",
                "published_at": week_start - timedelta(days=30 + i),
            })

        items = c._build_items(raw, _sihou_source())
        assert len(items) == 5
        for it in items:
            # 只保留当周资讯
            assert "当周新资讯" in it.title
            assert str(it.url) in {
                f"https://www.4hou.com/post/new{i}" for i in range(5)
            }


# ---------------------------------------------------------------------------
# 容错: published_at 异常不抛
# ---------------------------------------------------------------------------
class TestErrorTolerance:
    def test_garbage_published_at_skipped(self):
        """published_at 字段是 string 而不是 datetime → 跳过 (不 crash)."""
        c = _TestSecCollector()
        now_utc = datetime.now(timezone.utc)
        raw = [
            {
                "title": "嘶吼资讯正常这条标题够长",
                "url": "https://www.4hou.com/post/ok",
                "published_at": now_utc,
            },
            {
                "title": "嘶吼资讯异常时间字段这条也够长",
                "url": "https://www.4hou.com/post/bad",
                "published_at": "2026-07-10",  # str (实际不会发生, 防御性)
            },
        ]
        # string 不会进入 _build_items 的 datetime 处理逻辑
        # 实际上 _build_items 直接用 raw["published_at"] 不做类型校验
        # 这条会进 model 构造时炸 → _build_items 内部 try/except
  # 第一条正常, 第二条异常被吞
        items = c._build_items(raw, _sihou_source())
        assert len(items) == 1
        assert str(items[0].url) == "https://www.4hou.com/post/ok"


# ---------------------------------------------------------------------------
# max_items 截断
# ---------------------------------------------------------------------------
class TestMaxItems:
    def test_max_items_still_applies(self):
        """即使所有 100 条都当周, max_items 仍截断."""
        c = _TestSecCollector()
        now_utc = datetime.now(timezone.utc)
        raw = [
            {
                "title": f"嘶吼资讯第 {i:03d} 期: 当周新事件",
                "url": f"https://www.4hou.com/post/m{i}",
                "published_at": now_utc - timedelta(seconds=i),
            }
            for i in range(100)
        ]
        items = c._build_items(raw, _sihou_source())
        # max_items=50
        assert len(items) == 50
