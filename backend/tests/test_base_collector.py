"""BaseCollector 基类测试 (Phase 13 更新, Phase 25 部门信源过滤)

覆盖:
  - 必要方法强制实现 (subclass 必须定义 category / sources)
  - name 自动从类名派生
  - category 默认值是 AI (subclass 必须显式覆盖)
  - 全 source 失败 / item 数 < 阈值时 collect() 直接返回 [],**不**调 _fallback
  - _fallback 默认返回空列表 (Phase 13 硬约束)
  - _mark_fallback 在 fallback 数据上正确打 is_fallback + quality_flags
    (虽然 Phase 13 撤销了 fallback,函数本身仍存在,作为可重用的工具)
  - Phase 25 部门信源过滤: ai/finance/startup 关键词白名单 + 通用 NAV/CTA 黑名单
    防止"查看更多 >" / "演唱会" / "旅行社" / "餐饮" 等无关内容入库
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.collectors.base import (
    BaseCollector,
    _is_title_relevant_to_category,
)
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_item(
    id_: str,
    *,
    category: Category = Category.AI,
    title: str = "title",
) -> HotspotItem:
    """构造一个 tz-aware 时间戳的 HotspotItem。"""
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        source="src",
        url=f"https://real-source.com/{id_}",  # Phase 13: 真实 URL
        category=category,
        published_at=now,
        fetched_at=now,
    )


# ---------------------------------------------------------------------------
# 1. Phase 13: _fallback 不再 abstract,默认返回 []
# ---------------------------------------------------------------------------
def test_default_fallback_returns_empty_list():
    """Phase 13: BaseCollector._fallback() 默认返回 []。

    不再 abstract,subclass 不实现 _fallback 也能实例化。
    """
    class NoFallback(BaseCollector):
        category = Category.AI
        # 注意:没有 _fallback,但仍能实例化

    c = NoFallback()
    items = c._fallback()
    assert items == []


# ---------------------------------------------------------------------------
# 2. name 自动从类名派生（AICollector → 'ai'）
# ---------------------------------------------------------------------------
def test_name_auto_derived_from_class_name():
    """默认 name 应从类名派生（去后缀 'Collector' 并小写）。"""

    class AICollector(BaseCollector):
        category = Category.AI

    c = AICollector()
    assert c.name == "ai"


def test_name_override_takes_precedence():
    """显式设置 name 时应优先于自动派生。"""

    class MyCol(BaseCollector):
        name = "custom_name"
        category = Category.AI

    c = MyCol()
    assert c.name == "custom_name"


# ---------------------------------------------------------------------------
# 3. category 默认是 AI;subclass 必须显式覆盖
# ---------------------------------------------------------------------------
def test_category_default_is_ai():
    """未显式覆盖 category 的 subclass 默认就是 AI。"""

    class DefaultCat(BaseCollector):
        pass

    c = DefaultCat()
    assert c.category is Category.AI


def test_category_required_subclass_must_override():
    """subclass 必须显式覆盖 category 才能绑定到正确的业务类。"""

    class SecurityTestCol(BaseCollector):
        category = Category.SECURITY

    c = SecurityTestCol()
    assert c.category is Category.SECURITY


# ---------------------------------------------------------------------------
# 4. Phase 13 硬约束: 全 source 失败 / item < 阈值时,collect() 直接返回 []
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_sources_failed_returns_empty():
    """所有 source 都失败时 collect() 应返回 [],不调 _fallback (Phase 13)。"""

    class TestCol(BaseCollector):
        category = Category.AI
        sources = [
            {"name": "src1", "url": "https://a.example.com", "score": 70},
            {"name": "src2", "url": "https://b.example.com", "score": 70},
        ]
        min_items_threshold = 3

    c = TestCol()
    # mock fetch_source:所有 source 都返回空(模拟全失败)
    c.fetch_source = AsyncMock(
        return_value=(
            [],
            SourceResult(
                source_name="x",
                source_url="https://x",
                item_count=0,
                error_msg="simulated failure",
                duration_ms=10,
            ),
        )
    )

    items = await c.collect()
    # Phase 13: 全失败时返回 [],不调 _fallback (即使子类实现了 _fallback)
    assert items == []


@pytest.mark.asyncio
async def test_insufficient_items_returns_empty():
    """item 数 < min_items_threshold 时 collect() 应返回 [],不调 _fallback (Phase 13)。"""

    class TestCol(BaseCollector):
        category = Category.AI
        sources = [
            {"name": "src1", "url": "https://a.example.com", "score": 70},
        ]
        min_items_threshold = 10

    c = TestCol()
    # mock fetch_source:返回 2 条(低于阈值 10)
    c.fetch_source = AsyncMock(
        return_value=(
            [_make_item(f"item_{i}") for i in range(2)],
            SourceResult(
                source_name="x",
                source_url="https://x",
                item_count=2,
                duration_ms=10,
            ),
        )
    )

    items = await c.collect()
    # Phase 13: items < 阈值时返回 []
    assert items == []


@pytest.mark.asyncio
async def test_collect_with_no_sources_returns_empty():
    """sources=[] 时 collect() 直接返回 [],不调 _fallback (Phase 13)。"""

    class TestCol(BaseCollector):
        category = Category.AI
        sources = []

    c = TestCol()
    items = await c.collect()
    assert items == []


# ---------------------------------------------------------------------------
# 5. _mark_fallback 工具函数 (Phase 13 仍保留,但不再自动调用)
# ---------------------------------------------------------------------------
def test_mark_fallback_sets_flag_and_quality():
    """_mark_fallback 应正确设置 is_fallback=True + quality_flags 含 'fallback'。

    Phase 13: 虽然 _fallback 撤销了,这个工具函数仍保留 (e.g. 子类用
    来给某些特殊数据打 fallback 标记,虽然 SPEC §3 不推荐)。
    """
    now = datetime.now(timezone.utc)
    raw = [
        HotspotItem(
            id=f"x_{i}",
            title=f"x {i}",
            source="s",
            url=f"https://real.com/{i}",
            category=Category.AI,
            published_at=now,
            fetched_at=now,
        )
        for i in range(3)
    ]

    class TestCol(BaseCollector):
        category = Category.AI

    c = TestCol()
    # raw 默认 is_fallback=False, quality_flags=[]
    assert all(not it.is_fallback for it in raw)
    assert all(it.quality_flags == [] for it in raw)

    marked = c._mark_fallback(raw)
    assert all(it.is_fallback for it in marked)
    assert all("fallback" in it.quality_flags for it in marked)
    # 原始对象不应被修改(使用 model_copy 复制)
    assert all(not it.is_fallback for it in raw)


def test_mark_fallback_preserves_existing_flags():
    """_mark_fallback 应在原有 quality_flags 上追加 'fallback',不覆盖。"""
    now = datetime.now(timezone.utc)
    raw = [
        HotspotItem(
            id="x",
            title="x",
            source="s",
            url="https://real.com",
            category=Category.AI,
            published_at=now,
            fetched_at=now,
            quality_flags=["dup", "low_quality"],
        )
    ]

    class TestCol(BaseCollector):
        category = Category.AI

    c = TestCol()
    marked = c._mark_fallback(raw)
    flags = marked[0].quality_flags
    assert "fallback" in flags
    # 原有的两个 flag 仍在
    assert "dup" in flags
    assert "low_quality" in flags


# ---------------------------------------------------------------------------
# 6. Phase 25 部门信源过滤: 关键词白名单 (helper 函数级)
# ---------------------------------------------------------------------------
class TestTitleRelevantToCategory:
    """``_is_title_relevant_to_category`` 行为契约。"""

    def test_ai_keyword_hit_passes(self):
        """AI 分类: 命中 'GPT' / '大模型' 等关键词放行。"""
        assert _is_title_relevant_to_category("OpenAI 发布新 GPT 模型", "ai")
        assert _is_title_relevant_to_category("深度学习训练框架升级", "ai")
        assert _is_title_relevant_to_category("豆包大模型开放API", "ai")

    def test_ai_no_keyword_rejected(self):
        """AI 分类: 不命中任何关键词拒绝 (与 AI 完全无关的标题)。"""
        assert not _is_title_relevant_to_category("今年暑期旅行社推荐", "ai")
        assert not _is_title_relevant_to_category("餐饮爆店攻略", "ai")
        assert not _is_title_relevant_to_category("演唱会门票开售", "ai")

    def test_finance_keyword_hit_passes(self):
        """Finance 分类: 命中 'A股' / '美联储' 等关键词放行。"""
        assert _is_title_relevant_to_category("A股三大指数集体上涨", "finance")
        assert _is_title_relevant_to_category("美联储宣布加息25基点", "finance")
        assert _is_title_relevant_to_category("英伟达Q2财报超预期", "finance")

    def test_finance_no_keyword_rejected(self):
        """Finance 分类: 命中'投资建议'但无领域关键词 — 拒绝。"""
        assert not _is_title_relevant_to_category("操作上就如何亏小赚大", "finance")
        assert not _is_title_relevant_to_category("投资建议: 普通人如何理财", "finance")
        assert not _is_title_relevant_to_category("暑期旅游攻略TOP10", "finance")

    def test_startup_keyword_hit_passes(self):
        """Startup 分类: 命中'融资' / 'A轮' 等关键词放行。"""
        assert _is_title_relevant_to_category(
            "某 AI 创业公司完成 B 轮融资 3 亿元", "startup"
        )
        assert _is_title_relevant_to_category("红杉领投独角兽Pre-IPO轮", "startup")
        assert _is_title_relevant_to_category("95后创始人获投数千万", "startup")

    def test_startup_no_keyword_rejected(self):
        """Startup 分类: 抓到'旅行社/演唱会/餐饮'类侧栏 reject。"""
        assert not _is_title_relevant_to_category(
            "今年暑期旅行社报价汇总", "startup"
        )
        assert not _is_title_relevant_to_category("演唱会门票开售提醒", "startup")
        assert not _is_title_relevant_to_category("餐饮爆店清单", "startup")
        assert not _is_title_relevant_to_category(
            "查看更多 >", "startup"
        )

    def test_unwhitelisted_category_always_passes(self):
        """没在 _CAT_KEYWORDS 的 category (security/bid/github) 永远放行。

        这些分类走领域专用过滤 (security_collector / bid_collector 内部)。
        """
        # 任何标题都放行,因为这些分类不用通用白名单
        assert _is_title_relevant_to_category(
            "某 RDP 漏洞利用代码公开", "security"
        )
        assert _is_title_relevant_to_category("音响系统采购项目", "bid")
        assert _is_title_relevant_to_category(
            "awesome-python 仓库 Star 破万", "github"
        )
        # 空字符串也放行 (上层有长度检查)
        assert _is_title_relevant_to_category("", "security")


# ---------------------------------------------------------------------------
# 7. Phase 25 部门信源过滤: _title_relevant() 实例方法
# ---------------------------------------------------------------------------
def test_title_relevant_default_uses_category_keywords():
    """BaseCollector._title_relevant() 默认实现走 _CAT_KEYWORDS。"""

    class AiCol(BaseCollector):
        category = Category.AI

    class FinCol(BaseCollector):
        category = Category.FINANCE

    class StCol(BaseCollector):
        category = Category.STARTUP

    class SecCol(BaseCollector):
        category = Category.SECURITY

    ai = AiCol()
    fin = FinCol()
    st = StCol()
    sec = SecCol()

    # AI 命中放行, 不命中拒绝
    assert ai._title_relevant("OpenAI 推出新模型", "", {}) is True
    assert ai._title_relevant("今年暑期旅行社", "", {}) is False

    # Finance 命中放行, 不命中拒绝
    assert fin._title_relevant("A股三大指数", "", {}) is True
    assert fin._title_relevant("操作上就如何亏小赚大", "", {}) is False

    # Startup 命中放行, 不命中拒绝
    assert st._title_relevant("B 轮融资 3 亿元", "", {}) is True
    assert st._title_relevant("演唱会门票", "", {}) is False

    # Security 默认放行 (用领域过滤)
    assert sec._title_relevant("某漏洞利用代码公开", "", {}) is True


def test_subclass_can_override_title_relevant():
    """子类可重写 _title_relevant() 注入自定义逻辑。"""

    class StrictCol(BaseCollector):
        category = Category.AI

        def _title_relevant(self, title, url, source):  # type: ignore[override]
            # 自定义:必须含 "AI" 才放行
            return "AI" in title

    c = StrictCol()
    # 命中 AI
    assert c._title_relevant("AI 新进展", "", {}) is True
    # 命中 GPT (默认 _CAT_KEYWORDS 会放行,但子类更严格)
    assert c._title_relevant("OpenAI GPT-5 发布", "", {}) is True
    # 不命中 AI → 重写后拒绝
    assert c._title_relevant("深度学习训练框架", "", {}) is False


# ---------------------------------------------------------------------------
# 8. Phase 25 _build_items 端到端: NAV/CTA + 关键词 + 长度 综合过滤
# ---------------------------------------------------------------------------
def test_build_items_filters_nav_cta_and_irrelevant_titles():
    """_build_items 端到端: NAV/CTA + 关键词 + 长度 + Phase 47 时效门禁。

    模拟: 一个 finance collector 抓到混合 batch:
    - 1 条 finance 相关 + 当周 published_at (应保留)
    - 1 条 '查看更多 >' (NAV 应被过滤)
    - 1 条 '旅行社' (无关键词 应被过滤)
    - 1 条超短标题 (应被过滤)
    - 1 条 finance 相关但 published_at 为 None (Phase 47 拒收)
    - 1 条 finance 相关但 published_at 是上个月 (Phase 47 拒收)
    """
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)

    class FinCol(BaseCollector):
        category = Category.FINANCE
        _skip_quality = True  # 跳过 quality gate 避免依赖 DB
        max_items = 10

    c = FinCol()
    raw = [
        {"title": "A股三大指数集体上涨", "url": "https://x.com/1",
         "published_at": now_utc},  # 保留
        {"title": "查看更多 >", "url": "https://x.com/2"},  # NAV 过滤
        {"title": "今年暑期旅行社推荐", "url": "https://x.com/3"},  # 关键词拒绝
        {"title": "首页", "url": "https://x.com/4"},  # NAV 过滤
        {"title": "美联储宣布加息25基点", "url": "https://x.com/5",
         "published_at": now_utc},  # 保留
        {"title": "hi", "url": "https://x.com/6"},  # 长度过滤
        # Phase 47: 缺失 published_at → 拒收
        {"title": "纳指创新高", "url": "https://x.com/7"},
        # Phase 47: 早于本周一 → 拒收 (历史资讯)
        {"title": "黄金价格突破", "url": "https://x.com/8",
         "published_at": now_utc - timedelta(days=60)},
    ]
    items = c._build_items(raw, {"name": "投资界", "url": "https://test.com", "score": 70})
    assert len(items) == 2
    assert {it.title for it in items} == {
        "A股三大指数集体上涨",
        "美联储宣布加息25基点",
    }


def test_build_items_security_passes_irrelevant_titles():
    """Security 分类: _CAT_KEYWORDS 不含, 默认放行 (走 collector 内部过滤)。

    Phase 47: published_at 必填 (当周时间)。
    """
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)

    class SecCol(BaseCollector):
        category = Category.SECURITY
        _skip_quality = True
        max_items = 10

    c = SecCol()
    raw = [
        {"title": "某 RDP 漏洞利用代码公开", "url": "https://x.com/1",
         "published_at": now_utc},
        {"title": "CVE-2026-12345 补丁发布", "url": "https://x.com/2",
         "published_at": now_utc},
    ]
    items = c._build_items(raw, {"name": "FreeBuf", "url": "https://test.com", "score": 70})
    # Security 默认放行 — collector 内部 + quality gate 再过滤
    assert len(items) == 2

