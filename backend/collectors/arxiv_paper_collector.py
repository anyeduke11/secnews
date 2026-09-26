"""arXiv 学术论文采集器 (2026-09-26 论文抓取能力 Batch A Task 1)。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.PAPER``
- ``sources``   : 14 领域 arXiv API 检索模板 (export.arxiv.org, Atom)
- ``timeout``   : 30s
- ``max_items`` : 30 (单轮 3 领域 × max_results=20, 截断到 30)

**轮转采样**: arXiv 单领域一次可返回 20 条, 14 领域全抓会单源刷屏。
每次 ``collect()`` 只取游标窗口内的 3 个领域 (cursor, cursor+1, cursor+2
mod 14), 随后 cursor += 3。collector 是长生命周期实例
(collection_service 持有), 实例属性 ``_domain_cursor`` 即可跨轮推进。

**tags 落点说明**: HotspotItem 无 tags 字段 (hotspots.tags 列不在采集
链路写入), 三要素映射到现有通道——

- ``arxiv:<id>``  → ``HotspotItem.id`` (可读 ID 先例 ``hn:item:{id}``;
  同论文跨轮恒同 ID, upsert latest-wins 幂等, 见 ``_paper_tags``)
- ``领域:<key>``  → ``HotspotItem.source`` (source[\"name\"] = 领域键,
  前端来源可点击筛选)
- ``论文``        → ``category=PAPER`` 本身

**网络**: export.arxiv.org 为国际源, 走代理配置 (crawler_sources 注册行
network_zone='international', 与 YouTube 源同语义); 代理未配置则该源
抓取失败 → 健康机按既有语义处理 (连续失败判 dead), 不做特殊豁免。
"""
from __future__ import annotations

import asyncio
import time
import weakref
from typing import Any, ClassVar
from urllib.parse import quote

from backend.collectors.base import BaseCollector
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

# arXiv API 检索词 (设计稿 §2 领域→arXiv cat 映射, 2026-09-26):
# 多 cat 用 OR, 收敛区分度用 AND + 短语。短语内空格经 quote 编码为 %20。
_ARXIV_EXPRS: dict[str, str] = {
    "AI": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
    "AI安全": 'cat:cs.CR AND (all:adversarial OR all:"LLM security")',
    "网络安全": "cat:cs.CR OR cat:cs.NI",
    "数据安全": 'cat:cs.CR AND (all:"data privacy" OR all:"data security")',
    "安全运营": 'cat:cs.CR AND (all:"security operations" OR all:SOC)',
    "态势感知": (
        'cat:cs.CR AND (all:"situational awareness" '
        'OR all:"threat landscape")'
    ),
    "攻击面管理": 'cat:cs.CR AND all:"attack surface"',
    "应用安全": (
        'cat:cs.CR AND (all:"web security" OR all:"application security")'
    ),
    "漏洞治理": "cat:cs.CR AND all:vulnerability",
    "资产治理": (
        'cat:cs.CR AND (all:"asset management" OR all:"asset discovery")'
    ),
    "信息安全": "cat:cs.CR OR (cat:cs.MM AND all:security)",
    "安全架构": 'cat:cs.CR AND all:"security architecture"',
    "应急响应": 'cat:cs.CR AND all:"incident response"',
    "威胁情报": 'cat:cs.CR AND all:"threat intelligence"',
}

# sortBy 合法值: relevance / lastUpdatedDate / submittedDate (2026-09-26
# 真实拉取验证: 误写 `submitted` 时 arXiv 不报错, 而是返回仅含 1 条 Error
# entry 的 Atom feed — 3 领域轮转恰凑满 min_items_threshold, 垃圾条目会
# 静默入 feed。提交时间排序正确参数为 submittedDate)。
_ARXIV_API = (
    "http://export.arxiv.org/api/query"
    "?search_query={expr}&sortBy=submittedDate&sortOrder=descending"
    "&max_results=20"
)

# 领域键 → arXiv API URL (Atom)。注册行 (crawler_sources.feed_url/api_url)
# 与 sources 的 name 均以此键对齐 — base.py 切流机制按 name 匹配。
PAPER_DOMAIN_QUERIES: dict[str, str] = {
    domain: _ARXIV_API.format(expr=quote(expr, safe=":"))
    for domain, expr in _ARXIV_EXPRS.items()
}

# 单领域 arXiv abs 主页 (SourceResult 展示用; 实际抓取走 feed_url)
_ARXIV_HOME = "https://arxiv.org/"

PAPER_SOURCES: list[dict] = [
    {
        "name": domain,
        "url": _ARXIV_HOME,
        "rss_url": query,
        "api_url": query,
        "score": 75,
    }
    for domain, query in PAPER_DOMAIN_QUERIES.items()
]


def _arxiv_id_from_url(url: str) -> str:
    """从 arXiv abs 链接提取论文 ID: ``.../abs/2107.06384v1`` → ``2107.06384v1``。

    提取失败 (链接非 arxiv.org/abs/ 形态) 返回空串, 调用方回退 URL 指纹 ID。
    """
    marker = "/abs/"
    idx = url.find(marker)
    if idx < 0:
        return ""
    return url[idx + len(marker):].strip().rstrip("/")


class ArxivPaperCollector(BaseCollector):
    """arXiv 论文采集器 — 14 领域检索模板 + 每轮 3 领域轮转采样。

    解析复用 :meth:`BaseCollector._fetch_rss` (feedparser, Atom 兼容);
    title 的 arXiv 换行缩进在 ``_build_items`` 前统一清理。
    """

    category = Category.PAPER
    sources = PAPER_SOURCES
    timeout = 30
    max_items = 30
    min_items_threshold = 3

    # 每轮采样的领域数 (设计稿 §2: 每轮取 2-3 个领域, 取 3)
    _DOMAINS_PER_ROUND = 3

    # ------------------------------------------------------------------
    # arXiv 礼貌节拍 (2026-09-26 真实拉取验证发现)
    # ------------------------------------------------------------------
    # base.collect() 对本轮源 asyncio.gather 并发; 但 arXiv API 官方要求
    # 请求间隔 ≥3s, 并发 3 域实测必触发限流 (HTTP 406, 且对无代理直连
    # 同样生效)。按事件循环惰性建锁 (asyncio.Lock 绑定首次 acquire 的
    # loop — 模块导入期创建的类级锁在跨 asyncio.run/多 loop 场景会抛
    # "bound to a different event loop"), 串行化本 collector 的出网请求;
    # 其他 collector 不经过此处, 共享 fetchers 基建零改动。
    _PACE_LOCKS: ClassVar[weakref.WeakKeyDictionary] = weakref.WeakKeyDictionary()
    _LAST_REQUEST_AT: ClassVar[float] = 0.0
    _PACE_INTERVAL = 3.0

    async def fetch_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], SourceResult]:
        """限速串行地抓单个 arXiv 领域源 (节拍见 _PACE_LOCKS 注释)。"""
        lock = self._PACE_LOCKS.setdefault(
            asyncio.get_running_loop(), asyncio.Lock()
        )
        async with lock:
            wait = self._PACE_INTERVAL - (
                time.monotonic() - ArxivPaperCollector._LAST_REQUEST_AT
            )
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await super().fetch_source(source)
            finally:
                ArxivPaperCollector._LAST_REQUEST_AT = time.monotonic()

    def __init__(self) -> None:
        super().__init__()
        # 轮转游标: collector 由 collection_service 长期持有, 实例属性
        # 跨 collect() 推进 (类属性仅作子类默认值语义, 不用它累计)。
        self._domain_cursor = 0

    # ------------------------------------------------------------------
    # 轮转采样
    # ------------------------------------------------------------------
    def _next_round_domains(self) -> list[str]:
        """取本轮 3 个领域键 (cursor 起 mod 14), 并推进游标 +3。"""
        domains = list(PAPER_DOMAIN_QUERIES)
        n = len(domains)
        picked = [
            domains[(self._domain_cursor + i) % n]
            for i in range(min(self._DOMAINS_PER_ROUND, n))
        ]
        self._domain_cursor = (self._domain_cursor + len(picked)) % n
        return picked

    def _load_sources_from_registry(
        self, only_source: str | None = None
    ) -> list[dict] | None:
        """在基类切流装载后应用轮转窗口: 无论 registry 还是常量路径,
        本轮只保留游标窗口内的 3 个领域源。

        - registry 命中 (crawler_sources 已注册 paper 行) → 过滤装载结果
        - registry 未接管 (返回 None) → 过滤类常量池并以 list 返回,
          基类据此切换 self.sources (避免原地收缩常量池导致下轮空集)
        - ``only_source`` 强刷语义 (健康机单源调度) 不轮转, 原样透传
        """
        loaded = super()._load_sources_from_registry(only_source)
        if only_source is not None:
            return loaded
        window = set(self._next_round_domains())
        if loaded is None:
            return [s for s in PAPER_SOURCES if s.get("name") in window]
        return [s for s in loaded if s.get("name") in window]

    # ------------------------------------------------------------------
    # tags 映射 + 标题清理
    # ------------------------------------------------------------------
    @staticmethod
    def _paper_tags(arxiv_id: str, domain_key: str) -> list[str]:
        """单条论文的语义 tags (设计稿 §3.2)。落点见模块 docstring:
        tags[0] → item.id, tags[1] 的领域键 → item.source, "论文" → category。
        """
        return [f"arxiv:{arxiv_id}", f"领域:{domain_key}", "论文"]

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """arXiv 适配: 清理标题换行缩进 + 以 ``arxiv:<id>`` 作稳定 item id。

        - arXiv Atom 标题内嵌 ``\\n  `` 缩进, _fetch_rss 只 strip 首尾,
          这里先压平空白再交基类构建
        - raw["id"] 命中时基类直接采用 (base.py `_build_items` 约定),
          提取失败回退基类 URL 指纹 ID
        """
        domain = source.get("name", "")
        for raw in raw_items:
            title = (raw.get("title") or "").strip()
            raw["title"] = " ".join(title.split())
            arxiv_id = _arxiv_id_from_url(raw.get("url", ""))
            if arxiv_id:
                raw["id"] = self._paper_tags(arxiv_id, domain)[0]
        return super()._build_items(raw_items, source)


__all__ = [
    "PAPER_DOMAIN_QUERIES",
    "PAPER_SOURCES",
    "ArxivPaperCollector",
]
