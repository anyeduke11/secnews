"""公众号 wechat renderer 时效 + 跨次去重 + 离题黑名单 单元测试 (2026-08-04)。

覆盖 ``backend/collectors/sogou_search.py`` 的 ``parse_wechat_articles_html``:

1. ``test_7d_default_rejects_10d_old``            — 7 天默认窗口拒收 10 天前
2. ``test_7d_default_keeps_3d_old``               — 7 天默认窗口放行 3 天前
3. ``test_14d_hard_cap_rejects_30d_old``          — 14 天硬上限拒收 30 天前
4. ``test_max_age_days_capped_at_14``             — 传 99 天被 cap 到 14
5. ``test_no_published_at_rejected``              — 缺失 published_at 一律拒
6. ``test_topic_blocklist_filters_entertainment`` — "明星八卦" 拒收
7. ``test_topic_blocklist_filters_travel``        — "旅游攻略" 拒收
8. ``test_topic_blocklist_keeps_security``        — "APT 活动分析" 通过
9. ``test_seen_urls_external_dedup``              — DB 已存在 URL 跳过
10. ``test_seen_urls_external_dedup_distinct``    — DB 不含的 URL 保留
11. ``test_topic_keywords_positive_filter``       — 标题未命中白名单拒
12. ``test_topic_keywords_positive_filter_match`` — 命中白名单通过

纯函数测试, 不依赖 DB, 跑得最快。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from backend.collectors.sogou_search import (
    WECHAT_MAX_AGE_DAYS_DEFAULT,
    WECHAT_MAX_AGE_DAYS_HARD_CAP,
    parse_wechat_articles_html,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ts(dt: datetime) -> int:
    """datetime → Unix 秒 (sogou timeConvert 风格)。"""
    return int(dt.timestamp())


def _make_html_block(title: str, ts: int, account: str = "测试公众号") -> str:
    """构造一条 weixin.sogou.com 标准 result 块 HTML."""
    # 注意: 标题要 > 4 字符才能过 _clean_html_text 的长度过滤
    safe_title = title if len(title) >= 5 else title + "_补齐"
    # 2026-08-04: parser 正则 (_WEIXIN_BLOCK_RE / <a> href) 强制双引号,
    # 必须与 sogou 实际页面结构一致, 不能用单引号。
    # 但 timeConvert(...) 内部是单引号 (sogou 实际页面也是单引号)
    return (
        f'<h3><a href="/link?url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%2Ftest_{ts}">'
        f"{safe_title}</a></h3>"
        f'<p class="txt-info">摘要占位</p>'
        f'<div class="s-p">'
        f'<span class="all-time-y2">{account}</span>'
        f"<span class=\"s2\"><script>timeConvert('{ts}')</script></span>"
        f"</div>"
    )


def _wrap(blocks_html: str) -> str:
    return f"<html><body><ul class=\"news-list\">{blocks_html}</ul></body></html>"


# ---------------------------------------------------------------------------
# 1-2. 默认 7 天窗口
# ---------------------------------------------------------------------------
def test_7d_default_rejects_10d_old():
    """10 天前发布的文章, 默认 7 天窗口应拒收."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=10)
    html = _wrap(_make_html_block("某 APT 组织最新活动分析报告", _ts(old)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert items == [], f"10 天前应被拒收, 实际通过 {len(items)} 条"


def test_7d_default_keeps_3d_old():
    """3 天前发布的文章, 7 天窗口内应放行."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=3)
    html = _wrap(_make_html_block("某 APT 组织最新活动分析报告", _ts(recent)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert len(items) == 1, f"3 天前应通过, 实际 {len(items)} 条"
    assert "APT" in items[0]["title"]


# ---------------------------------------------------------------------------
# 3-4. 14 天硬上限
# ---------------------------------------------------------------------------
def test_14d_hard_cap_rejects_30d_old():
    """30 天前发布的文章, 14 天硬上限应拒收."""
    now = datetime.now(timezone.utc)
    very_old = now - timedelta(days=30)
    html = _wrap(_make_html_block("某历史漏洞复盘分析报告", _ts(very_old)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert items == [], f"30 天前应被 14 天硬上限拒收, 实际通过 {len(items)} 条"


def test_max_age_days_capped_at_14():
    """source dict 传 99 也会被 cap 到 14, 15 天前的文章被拒."""
    now = datetime.now(timezone.utc)
    borderline = now - timedelta(days=15)
    html = _wrap(_make_html_block("某 CISA 漏洞预警分析报告", _ts(borderline)))

    items = parse_wechat_articles_html(html, max_age_days=99, max_items=10)

    assert items == [], (
        f"99 应被 cap 到 {WECHAT_MAX_AGE_DAYS_HARD_CAP}, "
        f"15 天前应被拒, 实际通过 {len(items)} 条"
    )


# ---------------------------------------------------------------------------
# 5. 缺失 published_at
# ---------------------------------------------------------------------------
def test_no_published_at_rejected():
    """缺失 Unix timestamp 的 article 应被拒收 (无法验证时效)."""
    # 不含 timeConvert 的 s-p 块
    html = _wrap(
        f'<h3><a href="/link?url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%2Fno_ts">'
        f"某活动报道但无时间戳</a></h3>"
        f'<p class="txt-info">无摘要</p>'
        f'<div class="s-p">'
        f'<span class="all-time-y2">测试公众号</span>'
        f"</div>"
    )

    items = parse_wechat_articles_html(html, max_items=10)

    assert items == [], f"缺失 published_at 应被拒, 实际通过 {len(items)} 条"


# ---------------------------------------------------------------------------
# 6-8. 离题黑名单
# ---------------------------------------------------------------------------
def test_topic_blocklist_filters_entertainment():
    """"明星八卦" 命中 _NON_RELEVANT_TOPIC_RE, 应被拒收."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("某明星八卦爆料汇总", _ts(recent)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert items == [], f"明星八卦应被离题黑名单拒, 实际通过 {len(items)} 条"


def test_topic_blocklist_filters_travel():
    """"旅游攻略" 命中 _NON_RELEVANT_TOPIC_RE, 应被拒收."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("5 月旅游攻略: 国内 10 大景点", _ts(recent)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert items == [], f"旅游攻略应被离题黑名单拒, 实际通过 {len(items)} 条"


def test_topic_blocklist_keeps_security():
    """"APT 活动分析" 不在离题黑名单, 也不在 _TITLE_BLOCKLIST_RE, 应通过."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("某 APT 组织最新活动分析报告", _ts(recent)))

    items = parse_wechat_articles_html(html, max_items=10)

    assert len(items) == 1, f"安全资讯应通过黑名单, 实际 {len(items)} 条"
    assert "APT" in items[0]["title"]


# ---------------------------------------------------------------------------
# 9-10. 跨次去重 (DB 预查询)
# ---------------------------------------------------------------------------
def test_seen_urls_external_dedup():
    """若 URL 已在 seen_urls_external 集合, 应在 parse 层跳过."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    ts = _ts(recent)
    full_url = f"https://weixin.sogou.com/link?url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%2Ftest_{ts}"
    html = _wrap(_make_html_block("某已知重复文章标题", ts))

    items = parse_wechat_articles_html(
        html, max_items=10, seen_urls_external={full_url},
    )

    assert items == [], f"已在 DB 中的 URL 应被跳过, 实际通过 {len(items)} 条"


def test_seen_urls_external_dedup_distinct():
    """seen_urls_external 中不含的 URL 应正常通过."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    ts = _ts(recent)
    html = _wrap(_make_html_block("某新发布的漏洞分析", ts))

    items = parse_wechat_articles_html(
        html, max_items=10, seen_urls_external=set(),
    )

    assert len(items) == 1, f"DB 不含的 URL 应通过, 实际 {len(items)} 条"


# ---------------------------------------------------------------------------
# 11-12. 可选正面白名单 topic_keywords
# ---------------------------------------------------------------------------
def test_topic_keywords_positive_filter():
    """source 指定了 topic_keywords 后, 标题未命中关键词应被拒."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("某娱乐八卦娱乐报道", _ts(recent)))

    items = parse_wechat_articles_html(
        html, max_items=10, topic_keywords=["GPT", "AI", "大模型"],
    )

    assert items == [], f"未命中正面白名单应被拒, 实际通过 {len(items)} 条"


def test_topic_keywords_positive_filter_match():
    """source 指定了 topic_keywords 后, 标题命中关键词应通过."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("GPT-5 正式发布与多模态能力升级", _ts(recent)))

    items = parse_wechat_articles_html(
        html, max_items=10, topic_keywords=["GPT", "AI", "大模型"],
    )

    assert len(items) == 1, f"命中正面白名单应通过, 实际 {len(items)} 条"
    assert "GPT" in items[0]["title"]


# ---------------------------------------------------------------------------
# 边界 / 一致性
# ---------------------------------------------------------------------------
def test_default_max_age_is_7():
    """模块级常量与设计一致 — 默认 7 天, 硬上限 14 天."""
    assert WECHAT_MAX_AGE_DAYS_DEFAULT == 7
    assert WECHAT_MAX_AGE_DAYS_HARD_CAP == 14


def test_account_name_filter_still_works():
    """account_name 过滤未被破坏 (向后兼容)."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    html = _wrap(_make_html_block("某安全分析文章", _ts(recent), account="其他公众号"))

    items = parse_wechat_articles_html(
        html, account_name="目标公众号", max_items=10,
    )

    assert items == [], f"account_name 不匹配应被过滤, 实际通过 {len(items)} 条"
