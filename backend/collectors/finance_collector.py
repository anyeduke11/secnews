"""金融 / 投资热点数据采集器（Phase 3 重构, Phase 25 P1 扩容）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.FINANCE``
- ``sources``   : 新浪财经 / 东方财富 / 华尔街见闻 / 雪球 / 财新网
                  + Phase 25 P1: 财联社 / 金十数据
- ``timeout``   : 20s
- ``max_items`` : 60 (扩容接住 P1 新源)

外网抓取走 ``BaseCollector.fetch_source`` 默认实现。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。

Phase 25 P1:
- 财联社 (cls.cn/telegraph): 实时电报页, 标准 HTML 解析
- 金十数据 (jin10.com/flash_newest.js): 特殊 JSON-via-JS API,
  响应是 ``var newest = [...]``, 需要剥离 var 声明再 JSON.parse。
  走 ``renderer="html"`` + 重写 ``_parse_html`` 处理。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

# 财联社实时电报: 时间戳在文本开头 (例 "14:03:21财联社7月7日电，...").
# 注意: 文本里的"14:03:21"是北京时间,我们用今天的日期 + 该时分秒构造 UTC。
_TELEGRAPH_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})")


def _parse_cls_telegraph_time(hh: str, mm: str, ss: str) -> str:
    """财联社电报时间 → ISO 8601 (UTC)。"""
    now_utc = datetime.now(timezone.utc)
    # 北京时间 = UTC+8, 北京的 hh:mm:ss 当天 → UTC = 当天 - 8h
    beijing = now_utc.replace(
        hour=int(hh), minute=int(mm), second=int(ss), microsecond=0
    )
    # 转换为 UTC: beijing - 8h
    utc_dt = beijing.astimezone(timezone.utc)
    # 简单处理: 用 beijing 的日期/时间视为 UTC+8, 转 UTC
    from datetime import timedelta

    utc_dt = beijing - timedelta(hours=8)
    return utc_dt.isoformat()


# 金十 flash JSON 解析: 响应是 ``var newest = [...]`` JS 片段
_JIN10_PREFIX_RE = re.compile(r"^\s*var\s+newest\s*=\s*")
_JIN10_SUFFIX_RE = re.compile(r"[;\s]+$")


def _parse_jin10_js(raw: str) -> list[dict[str, Any]] | None:
    """剥离 JS 包裹, 返回 list[dict] 或 None (解析失败)。"""
    s = _JIN10_PREFIX_RE.sub("", raw.strip())
    s = _JIN10_SUFFIX_RE.sub("", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return data


def _parse_jin10_time(time_str: str) -> str | None:
    """金十 data.time → ISO 8601 UTC."""
    # 金十格式: "2026-07-07 14:03:21" (北京时间)
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))  # 北京时间
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


from datetime import timedelta  # noqa: E402  # 延后导入避免循环

FINANCE_SOURCES: list[dict] = [
    # Phase 48: 中国证监会 - 实际内容是金融监管公告/行政处罚/警示函/约谈
    # 之前误放在 security_collector.py, 导致 93/94 条被标 category_mismatch
    {
        "name": "中国证监会",  # 处罚信息/监管公告
        "url": "https://www.csrc.gov.cn/",
        "score": 88,
        "max_items": 15,
    },
    {"name": "新浪财经", "url": "https://finance.sina.com.cn/", "score": 80, "renderer": "crawl4ai"},  # Phase 14: 反爬 + JS 渲染
    {"name": "东方财富", "url": "https://www.eastmoney.com/", "score": 80, "renderer": "crawl4ai"},
    {"name": "华尔街见闻", "url": "https://wallstreetcn.com/", "score": 78},
    {"name": "雪球", "url": "https://xueqiu.com/", "score": 75, "renderer": "crawl4ai"},  # Phase 14: 反爬
    {"name": "财新网", "url": "https://www.caixin.com/", "score": 80},
    # Phase 25 P1: 财联社实时电报
    # 已知限制: telegraph 页是 Next.js SPA,数据通过签名 API 异步加载
    # (cls.cn/v3/depth/home/assembled/1000 需要签名),即使 crawl4ai 渲染
    # 也拿不到 subject-content DOM (initial state 仅有 chooseNav)。
    # 解决方案待 P2: 反向 API 签名算法 + 自实现 fetcher。
    # 当前先 disable, 避免无效请求拖累其他源。
    {
        "name": "财联社",
        "url": "https://www.cls.cn/telegraph",
        "score": 82,
        "renderer": "disabled",  # P1 暂未接入, 见上方注释
    },
    # Phase 25 P1: 金十数据 7×24 快讯 (JSON-via-JS API)
    {
        "name": "金十数据",
        "url": "https://www.jin10.com/flash_newest.js",
        "score": 80,
        "renderer": "html",  # 自己处理 JS 响应
    },
]


class FinanceCollector(BaseCollector):
    """采集金融 / 投资领域热点数据。"""

    category = Category.FINANCE
    sources = FINANCE_SOURCES
    timeout = 20
    max_items = 60  # Phase 25 P1: 40 → 60 接住 2 个新源

    def _parse_html(
        self, html: str, source: dict
    ) -> list[dict[str, Any]]:
        """财联社 + 金十 专用 HTML/JS 解析。

        财联社 telegraph 列表:
          <div class="subject-content">14:03:21财联社7月7日电，...</div>
          <a href="https://www.cls.cn/detail/2419001">... </a>

        金十 flash_newest.js:
          var newest = [{ "id": "...", "time": "2026-07-07 14:03:21",
                          "data": {"title": "...", "content": "..."}, ...}]
        """
        name = source.get("name", "")
        if name == "金十数据":
            return self._parse_jin10(html)
        if name == "财联社":
            return self._parse_cls(html)
        return super()._parse_html(html, source)

    @staticmethod
    def _parse_jin10(raw: str) -> list[dict[str, Any]]:
        """金十 flash_newest.js → [{title, url, published_at}, ...]"""
        data = _parse_jin10_js(raw)
        if not data:
            return []
        items: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            # channel=5 是 VIP/付费内容, 跳过
            if 5 in (entry.get("channel") or []):
                continue
            d = entry.get("data") or {}
            # 优先 title, 其次 content
            text = d.get("title") or d.get("content") or ""
            text = re.sub(r"</?b>", "", text).strip()
            if not text:
                continue
            # 拆【title】desc 格式
            m = re.match(r"^【([^】]*)】(.*)$", text)
            if m:
                title = (m.group(1) or text).strip()
            else:
                title = text
            if not title or len(title) < 8:
                continue
            url = f"https://flash.jin10.com/detail/{entry.get('id')}"
            published_at = _parse_jin10_time(entry.get("time") or "")
            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                }
            )
        return items

    @staticmethod
    def _parse_cls(html: str) -> list[dict[str, Any]]:
        """财联社 telegraph → [{title, url, published_at}, ...]"""
        # 简单正则: 匹配 <a class="subject-content" href="...">TEXT</a>
        # 实际 DOM: <a class="subject-content" href="/detail/2419001">14:03:21财联社7月7日电，...</a>
        link_re = re.compile(
            r'<a[^>]+class=["\']subject-content["\']'
            r'[^>]+href=["\']([^"\']+)["\']'
            r'[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        items: list[dict[str, Any]] = []
        for m in link_re.finditer(html):
            url, body = m.group(1), m.group(2)
            # 清理 HTML
            text = re.sub(r"<[^>]+>", "", body).strip()
            if not text or len(text) < 8:
                continue
            # 提取电报前缀时间 "HH:MM:SS"
            t = _TELEGRAPH_TIME_RE.match(text)
            published_at = None
            if t:
                published_at = _parse_cls_telegraph_time(
                    t.group(1), t.group(2), t.group(3)
                )
            # 拼接完整 URL
            if url.startswith("/"):
                url = "https://www.cls.cn" + url
            items.append(
                {
                    "title": text,
                    "url": url,
                    "published_at": published_at,
                }
            )
        return items

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [],UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。


__all__ = ["FinanceCollector", "FINANCE_SOURCES"]
