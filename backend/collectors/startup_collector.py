"""独立开发 / 创业热点数据采集器（Phase 3 重构）。

继承 :class:`BaseCollector`:

- ``category``  : ``Category.STARTUP``
- ``sources``   : 36氪 / 虎嗅 / 投资界 / IT 桔子
- ``timeout``   : 20s
- ``max_items`` : 40

外网抓取走 ``BaseCollector.fetch_source`` 默认实现。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。

Phase 34 (2026-07-08) 新增: 投资界 (pedaily.cn) 非资讯标题黑名单。
背景: 投资界首页/频道页混入 "投资人排行榜" 系列条目 (e.g. 2026「投资界
TOP100」投资人、2025「投资界S50女性投资人」等),URL 路径已被全局
``URL_PATH_BLOCKLIST`` 拦截 (pedaily.cn/{YYYY}investor 等),但偶尔有
URL 走 ``/2026investor/index.shtml`` 之类边角路径漏网;此处用标题正则
兜底拦截"投资人排行榜"系列,仅对源 url 含 ``pedaily.cn`` 的条目生效。
"""
from __future__ import annotations

import re
from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

STARTUP_SOURCES: list[dict] = [
    {"name": "36氪", "url": "https://36kr.com/", "rss_url": "https://36kr.com/feed", "score": 78},
    # 2026-08-02 实测: 虎嗅(2 bytes, 反爬拦截), IT桔子(HTTP 412), 均不可抓取
    {"name": "虎嗅", "url": "https://www.huxiu.com/", "score": 76, "renderer": "disabled"},
    {"name": "投资界", "url": "https://www.pedaily.cn/", "score": 75},  # 有 64 links, 需 site-specific parser
    {"name": "IT桔子", "url": "https://www.itjuzi.com/", "score": 72, "renderer": "disabled"},
    # ===== 创业公众号 (2026-08-02 新增, 走 sogou weixin 搜索) =====
    {"name": "创业邦", "account_name": "创业邦", "score": 74, "renderer": "wechat"},
    {"name": "亿欧网", "account_name": "亿欧网", "score": 72, "renderer": "wechat"},
    {"name": "铅笔道", "account_name": "铅笔道", "score": 70, "renderer": "wechat"},
]


# ---------------------------------------------------------------------------
# Phase 34 (2026-07-08): 投资界 (pedaily.cn) 非资讯 标题 黑名单
# ---------------------------------------------------------------------------
# URL 路径已在全局 URL_PATH_BLOCKLIST 拦截 (pedaily.cn/{YYYY}{investor|S50|F40} 等),
# 此处仅兜底拦截标题中"投资人排行榜"系列。
# 仅对源 url 含 ``pedaily.cn`` 的条目生效。
# ---------------------------------------------------------------------------
_PEDAILY_RANKING_TITLE_RE = re.compile(
    r"投资界(TOP100|S50|F40|独角兽)"  # 投资界XXX 排名
    r"|F40中国青年投资人"  # 标题前缀
    r"|独角兽榜单"  # 独角兽榜单
)


class StartupCollector(BaseCollector):
    """采集独立开发 / 创业领域热点数据。"""

    category = Category.STARTUP
    sources = STARTUP_SOURCES
    timeout = 20
    max_items = 40

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [],UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。

    def _parse_html(
        self, html: str, source: dict
    ) -> list[dict[str, Any]]:
        """投资界专有 HTML 解析; 其他源走默认实现。

        投资界 (pedaily.cn) 首页结构:
          <div class="box">
            <a href="https://news.pedaily.cn/202608/567173.shtml">
              <span>机构资本事件汇总</span>
            </a>
          </div>
        默认 CSS selectors (h2/h3) 不匹配, 需要自定义解析。
        """
        name = source.get("name", "")
        if name == "投资界":
            return self._parse_pedaily(html)
        return super()._parse_html(html, source)

    @staticmethod
    def _parse_pedaily(html: str) -> list[dict[str, Any]]:
        """投资界首页 → [{title, url, published_at}, ...]

        提取 news.pedaily.cn 下文章链接, 过滤导航/分类链接。
        注意: 不使用 _is_noise_url 因为其跨域过滤会误杀 news.pedaily.cn
        (子域名 ≠ www.pedaily.cn), 改用 URL_PATH_BLOCKLIST 正则。
        """
        import html as _html
        import re

        from backend.collectors.parsing import _is_noise_title

        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 投资界噪声路径: video/, media/, /events/, /company/, /stock/
        _PEDAILY_NOISE_PATH = re.compile(
            r"/(video/|media/|events/|company/|stock/|99discoveries/)",
            re.IGNORECASE,
        )

        # 匹配 <a href="https://news.pedaily.cn/...">...</a>
        pat = re.compile(
            r'<a[^>]*href="(https://news\.pedaily\.cn/[^"]+)"[^>]*>([^<]{8,120})</a>',
            re.IGNORECASE,
        )
        for m in pat.finditer(html):
            url, title = m.group(1), m.group(2)
            title = _html.unescape(title.strip())
            if not title or len(title) < 8:
                continue
            # 过滤噪声路径
            if _PEDAILY_NOISE_PATH.search(url):
                continue
            if _is_noise_title(title):
                continue
            key = title[:30]
            if key in seen:
                continue
            seen.add(key)
            items.append({"title": title, "url": url, "published_at": None})
        return items

    def _title_relevant(
        self, title: str, url: str, source: dict
    ) -> bool:
        """Phase 34 (2026-07-08) override: 投资界标题兜底黑名单。

        在 BaseCollector 默认实现基础上,叠加投资界特定的:
        - 标题正则 (投资界TOP100 / S50 / F40 / 独角兽)
        仅对源 url 含 ``pedaily.cn`` 的条目生效,其他源走默认实现。
        """
        from backend.collectors.keywords import _is_title_relevant_to_category

        if not _is_title_relevant_to_category(title, self.category.value):
            return False
        src_url = source.get("url", "") if isinstance(source, dict) else ""
        return not ("pedaily.cn" in src_url and _PEDAILY_RANKING_TITLE_RE.search(title or ""))


__all__ = ["STARTUP_SOURCES", "StartupCollector"]
