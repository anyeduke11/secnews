"""公开学术论文多源采集器 (2026-10-13 论文来源扩展)。

在既有 :class:`ArxivPaperCollector` 之外, 新增 5 个公开高质量 AI / 网络
信息安全方向的论文来源, 均为 ``Category.PAPER``:

- ``OpenAlexCollector``           — OpenAlex works API (JSON, CS 领域)
- ``SemanticScholarCollector``    — Semantic Scholar bulk search (JSON)
- ``IACRCollector``               — IACR ePrint (RSS, 密码学专门源)
- ``CrossrefCollector``           — Crossref works API (JSON, 期刊论文)
- ``HFDailyPapersCollector``      — Hugging Face Daily Papers (JSON)

**共享逻辑**: :class:`PaperProviderMixin` 承载四件事, 5 个具体类只声明自身
单源常量 + ``_parse_json``:

1. **源归属隔离** — 基类 ``_load_sources_from_registry`` 按 ``category``
   装载, 会把 category='paper' 的全部行 (含 arXiv 的 14 领域行与其余 5 源)
   一并返回; ``paper`` 分类下存在多个 collector, 故各 collector 必须按自身
   ``sources`` 名称过滤, 否则会互相抓取对方的源。
2. **动态日期窗注入** — OpenAlex / Semantic Scholar / Crossref 需按日期区间
   检索 (避免拉回未来日期或陈年论文); 端点用 ``{from_date}`` / ``{to_date}``
   占位, 抓取前实时注入最近 :data:`_LOOKBACK_DAYS` 天窗口。
3. **标题压平** — 部分 API 标题含换行/多余空白, 统一压平后再交基类。
4. **稳定 item id 钩子** — ``_paper_id_from_url`` 默认空, 供 RSS 类源
   (IACR) 从链接提取可读 ID。

**落点**: ``category=Category.PAPER``, 时效门禁沿用 ``item_builder`` 的
14 天论文窗口 (非资讯周级门禁); 放行基准 = 10 实践域 ∪ 通用 AI/ML
(见 ``keywords._is_paper_title_relevant``)。

**网络**: 5 源均为国际源, 注册行 ``network_zone='international'``;
JSON 路径首跳直连, 失败后 ``_proxy_json_retry`` 按 ``should_use_proxy`` 走
代理兜底。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.collection import SourceResult
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

# 动态日期窗回看天数: 学术源索引滞后 (~4 天) 决定不能只取当日;
# 取 21 天给 API 侧留缓冲, 落库端再由 item_builder 的 14 天论文窗口收口。
_LOOKBACK_DAYS = 21


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_date(value: Any) -> datetime | None:
    """解析 ``YYYY-MM-DD`` / ISO-8601 (含 ``Z``) 为 UTC datetime。

    解析失败返回 None (调用方跳过该条)。
    """
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _crossref_date(item: dict) -> datetime | None:
    """Crossref ``published-online`` → ``published`` 的 date-parts 取日期。

    仅接受年/月/日三段齐全的条目 (Crossref 常见仅年或年月,
    精度不足无法做时效判定 → 跳过)。
    """
    for key in ("published-online", "published"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and len(parts[0]) >= 3:
            try:
                y, m, d = parts[0][:3]
                return datetime(int(y), int(m), int(d), tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


class PaperProviderMixin:
    """论文多源采集器的共享逻辑 (依赖宿主类的
    ``sources`` / ``category`` / ``logger`` / ``timeout``)。"""

    # 动态日期窗回看天数 (供 _date_window 使用)
    _LOOKBACK_DAYS = _LOOKBACK_DAYS

    # ------------------------------------------------------------------
    # 源归属隔离
    # ------------------------------------------------------------------
    def _load_sources_from_registry(
        self, only_source: str | None = None
    ) -> list[dict] | None:
        """仅保留本 collector 自身的源行。

        基类按 ``category`` 装载 (paper 分类下 6 个 collector 共用 19 行),
        不隔离会让每个 collector 抓到全部源。``loaded is None`` (分类未注册)
        时原样返回 None, 交基类回退类常量。
        """
        loaded = super()._load_sources_from_registry(only_source)
        if loaded is None:
            return None
        own = {s.get("name") for s in self.sources}
        return [s for s in loaded if s.get("name") in own]

    # ------------------------------------------------------------------
    # 动态日期窗
    # ------------------------------------------------------------------
    def _date_window(self) -> tuple[str, str]:
        """返回 (起始日, 今日) 的 ``YYYY-MM-DD`` 字符串。"""
        today = _now_utc().date()
        start = today - timedelta(days=self._LOOKBACK_DAYS)
        return start.isoformat(), today.isoformat()

    async def fetch_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], SourceResult]:
        """端点含 ``{from_date}`` / ``{to_date}`` 时注入实时日期窗后再抓取。"""
        api_url = source.get("api_url") or ""
        if "{from_date}" in api_url or "{to_date}" in api_url:
            from_date, to_date = self._date_window()
            source = {
                **source,
                "api_url": api_url.format(from_date=from_date, to_date=to_date),
            }
        return await super().fetch_source(source)

    # ------------------------------------------------------------------
    # item 构建
    # ------------------------------------------------------------------
    def _paper_id_from_url(self, url: str) -> str | None:
        """从论文链接提取稳定 ID; 默认无 (JSON 源已在 _parse_json 设 id)。"""
        return None

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """压平标题空白 + 缺 id 时尝试从 URL 提取稳定 ID。"""
        for raw in raw_items:
            title = (raw.get("title") or "").strip()
            raw["title"] = " ".join(title.split())
            if not raw.get("id"):
                pid = self._paper_id_from_url(raw.get("url", ""))
                if pid:
                    raw["id"] = pid
        return super()._build_items(raw_items, source)


# ----------------------------------------------------------------------
# OpenAlex
# ----------------------------------------------------------------------
# fields/17 = Computer Science (OpenAlex 领域分类); type:article 排除
# paratext/dataset 等非论文类型; 按 publication_date 倒序取最近窗口。
_OPENALEX_API = (
    "https://api.openalex.org/works"
    "?filter=type:article,primary_topic.field.id:fields/17,"
    "from_publication_date:{from_date},to_publication_date:{to_date}"
    "&sort=publication_date:desc&per-page=25"
)
OPENALEX_SOURCES = [
    {
        "name": "OpenAlex",
        "url": "https://openalex.org/",
        "api_url": _OPENALEX_API,
        "score": 75,
        "renderer": "json",
    }
]


class OpenAlexCollector(PaperProviderMixin, BaseCollector):
    """OpenAlex 论文采集器 (JSON)。"""

    category = Category.PAPER
    sources = OPENALEX_SOURCES
    timeout = 30
    max_items = 20
    min_items_threshold = 1

    def _parse_json(self, data: Any, source: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        now = _now_utc()
        for w in (data or {}).get("results", []) or []:
            title = (w.get("display_name") or "").strip()
            if not title:
                continue
            dt = _parse_iso_date(w.get("publication_date"))
            if dt is None or dt > now:
                continue
            loc = w.get("primary_location") or {}
            url = (
                loc.get("landing_page_url")
                or w.get("doi")
                or w.get("id")
                or ""
            ).strip()
            if not url:
                continue
            raw: dict[str, Any] = {
                "title": title,
                "url": url,
                "published_at": dt,
                "summary": "",
            }
            oid = str(w.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
            if oid:
                raw["id"] = f"openalex:{oid}"
            out.append(raw)
        return out


# ----------------------------------------------------------------------
# Semantic Scholar
# ----------------------------------------------------------------------
# bulk search 端点需 search_query; 用宽泛 query=security + fieldsOfStudy
# 限 CS + 日期区间; 条目级再由 keywords 领域门放行。
_S2_API = (
    "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    "?query=security"
    "&fields=title,url,publicationDate,externalIds"
    "&fieldsOfStudy=Computer%20Science"
    "&publicationDateOrYear={from_date}:{to_date}"
    "&sort=publicationDate:desc"
)
S2_SOURCES = [
    {
        "name": "Semantic Scholar",
        "url": "https://www.semanticscholar.org/",
        "api_url": _S2_API,
        "score": 75,
        "renderer": "json",
    }
]


class SemanticScholarCollector(PaperProviderMixin, BaseCollector):
    """Semantic Scholar 论文采集器 (JSON bulk search)。"""

    category = Category.PAPER
    sources = S2_SOURCES
    timeout = 30
    max_items = 20
    min_items_threshold = 1

    def _parse_json(self, data: Any, source: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        now = _now_utc()
        for p in (data or {}).get("data", []) or []:
            title = (p.get("title") or "").strip()
            if not title:
                continue
            dt = _parse_iso_date(p.get("publicationDate"))
            if dt is None or dt > now:
                continue
            pid = str(p.get("paperId") or "").strip()
            url = (p.get("url") or "").strip()
            if not url and pid:
                url = f"https://www.semanticscholar.org/paper/{pid}"
            if not url:
                continue
            raw: dict[str, Any] = {
                "title": title,
                "url": url,
                "published_at": dt,
                "summary": "",
            }
            if pid:
                raw["id"] = f"s2:{pid}"
            out.append(raw)
        return out


# ----------------------------------------------------------------------
# IACR ePrint (RSS)
# ----------------------------------------------------------------------
IACR_SOURCES = [
    {
        "name": "IACR ePrint",
        "url": "https://eprint.iacr.org/",
        "rss_url": "https://eprint.iacr.org/rss/rss.xml",
        "score": 75,
    }
]


class IACRCollector(PaperProviderMixin, BaseCollector):
    """IACR Cryptology ePrint Archive 采集器 (RSS)。

    密码学专门源, 标题多含专有术语 (zero-knowledge / multiparty 等),
    是否放行交由 ``keywords._is_paper_title_relevant`` (领域门) 判定。
    """

    category = Category.PAPER
    sources = IACR_SOURCES
    timeout = 30
    max_items = 20
    min_items_threshold = 1

    def _paper_id_from_url(self, url: str) -> str | None:
        m = re.search(r"eprint\.iacr\.org/(\d{4}/\d+)", url or "")
        return f"iacr:{m.group(1)}" if m else None


# ----------------------------------------------------------------------
# Crossref
# ----------------------------------------------------------------------
_CROSSREF_API = (
    "https://api.crossref.org/works"
    "?filter=from-pub-date:{from_date},until-pub-date:{to_date},"
    "type:journal-article"
    "&query=security&rows=20&sort=published&order=desc"
    "&select=DOI,title,published,published-online,URL,container-title,type"
)
CROSSREF_SOURCES = [
    {
        "name": "Crossref",
        "url": "https://www.crossref.org/",
        "api_url": _CROSSREF_API,
        "score": 75,
        "renderer": "json",
    }
]


class CrossrefCollector(PaperProviderMixin, BaseCollector):
    """Crossref 论文采集器 (JSON, 期刊论文)。"""

    category = Category.PAPER
    sources = CROSSREF_SOURCES
    timeout = 30
    max_items = 20
    min_items_threshold = 1

    def _parse_json(self, data: Any, source: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        now = _now_utc()
        items = ((data or {}).get("message") or {}).get("items", []) or []
        for it in items:
            titles = it.get("title") or []
            title = (titles[0] if titles else "").strip()
            if not title:
                continue
            dt = _crossref_date(it)
            if dt is None or dt > now:
                continue
            doi = str(it.get("DOI") or "").strip()
            url = (
                f"https://doi.org/{doi}" if doi else (it.get("URL") or "").strip()
            )
            if not url:
                continue
            raw: dict[str, Any] = {
                "title": title,
                "url": url,
                "published_at": dt,
                "summary": "",
            }
            if doi:
                raw["id"] = f"crossref:{doi}"
            out.append(raw)
        return out


# ----------------------------------------------------------------------
# Hugging Face Daily Papers
# ----------------------------------------------------------------------
_HF_API = "https://huggingface.co/api/daily_papers"
HF_SOURCES = [
    {
        "name": "Hugging Face Daily Papers",
        "url": "https://huggingface.co/papers",
        "api_url": _HF_API,
        "score": 75,
        "renderer": "json",
    }
]


class HFDailyPapersCollector(PaperProviderMixin, BaseCollector):
    """Hugging Face Daily Papers 采集器 (JSON 数组)。

    端点返回 top-level 数组, 元素含 ``paper`` 子对象 (id/title/summary/
    publishedAt)。仅经代理可达 (直连超时 → 代理兜底)。
    """

    category = Category.PAPER
    sources = HF_SOURCES
    timeout = 30
    max_items = 20
    min_items_threshold = 1

    def _parse_json(self, data: Any, source: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        now = _now_utc()
        entries = data if isinstance(data, list) else []
        for entry in entries:
            paper = entry.get("paper") or entry
            pid = str(paper.get("id") or "").strip()
            title = (paper.get("title") or "").strip()
            if not title or not pid:
                continue
            dt = _parse_iso_date(paper.get("publishedAt"))
            if dt is None or dt > now:
                continue
            out.append(
                {
                    "id": f"hf:{pid}",
                    "title": title,
                    "url": f"https://huggingface.co/papers/{pid}",
                    "published_at": dt,
                    "summary": (paper.get("summary") or "").strip(),
                }
            )
        return out


__all__ = [
    "CrossrefCollector",
    "HFDailyPapersCollector",
    "IACRCollector",
    "OpenAlexCollector",
    "PaperProviderMixin",
    "SemanticScholarCollector",
]