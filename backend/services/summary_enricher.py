"""v1.9 — 文章摘要富化服务。

从 RSS 摘要中读取实际文章内容，生成有意义的纯文本摘要。
核心逻辑：
1. 检测 RSS 摘要是否为 HTML 元数据（如 Hacker News 的"Article URL: ..."）
2. 若是，抓取实际文章 URL，提取正文文本
3. 取首段有意义文本作为摘要

设计原则：
- 仅富化"质量差"的摘要（含 HTML 标签 / 纯元数据 / 缺失）
- 并发抓取（asyncio.gather），单文章超时 5s
- 幂等：已富化的摘要不再重复处理
- 尽力而为：抓取失败保留原始摘要，不阻塞主流程
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import aiohttp
from lxml import html as lxml_html

logger = logging.getLogger("hotspot.summary_enricher")

# 单篇文章抓取超时（秒）
FETCH_TIMEOUT = 5
# 摘要最大长度（字符）
SUMMARY_MAX_LEN = 400
# 摘要最小长度（字符）— 低于此值认为需要富化
SUMMARY_MIN_LEN = 30

# 纯元数据模式：Hacker News 等源的 RSS 摘要只有 URL/Points/Comments
_META_ONLY_RE = re.compile(
    r"^(<p>)?(Article URL|Comments URL|Points|HN\s|"
    r"<a href=|https?://)",
    re.IGNORECASE,
)


def _needs_enrich(summary: Optional[str]) -> bool:
    """判断摘要是否需要富化。

    条件（满足任一即需富化）：
    - 缺失
    - 过短
    - 包含 HTML 标签
    - 匹配纯元数据模式
    """
    if not summary:
        return True
    if len(summary) < SUMMARY_MIN_LEN:
        return True
    # 含 HTML 标签
    if "<" in summary and ">" in summary:
        if _META_ONLY_RE.search(summary):
            return True
        # 粗略检测：摘要包含 HTML 标签
        if re.search(r"<[a-z]+[^>]*>", summary, re.IGNORECASE):
            return True
    # 纯元数据（无 HTML 标签但也只有 URL）
    if _META_ONLY_RE.match(summary):
        return True
    return False


def _strip_html(text: str) -> str:
    """用 lxml 剥离 HTML 标签，返回纯文本。"""
    try:
        root = lxml_html.fromstring(text)
        return root.text_content().strip()
    except Exception:
        # fallback: 简单正则剥离
        clean = re.sub(r"<[^>]+>", "", text)
        return clean.strip()


def _extract_first_text(html_text: str) -> Optional[str]:
    """从文章 HTML 中提取首段有意义文本。

    策略：
    1. 用 lxml 解析，提取 ``<p>`` / ``<article>`` / ``<div class="content">``
       等容器内的文本
    2. 跳过导航 / 版权 / 元数据等噪声
    3. 取第一个有意义段落（至少 20 字符）
    """
    try:
        root = lxml_html.fromstring(html_text)
    except Exception:
        return None

    # 尝试优先取 <article> 或 <main>
    for tag in ("article", "main", '[role="main"]'):
        container = root.cssselect(tag)
        if container:
            root = container[0]
            break

    # 遍历所有 <p> 标签，取第一个有意义的
    for p in root.iter("p"):
        text = p.text_content().strip()
        # 跳过噪声
        if not text or len(text) < 20:
            continue
        if re.match(r"^(copyright|©|all rights reserved|分享到|关注我们|"
                    r"免责声明|转载请注明|阅读原文|扫描二维码)", text, re.IGNORECASE):
            continue
        return text[:SUMMARY_MAX_LEN].strip()

    # fallback: 取 body 文本的第一个有意义块
    body = root.find("body")
    if body is None:
        body = root
    text = body.text_content().strip()
    # 按段落分割
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) >= 20:
            return para[:SUMMARY_MAX_LEN].strip()

    return None


async def _fetch_article(url: str) -> Optional[str]:
    """抓取文章 URL 并返回 HTML 文本。

    通过 aiohttp 抓取，超时 FETCH_TIMEOUT 秒。
    失败或超时返回 None（不阻塞主流程）。
    """
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
        async with connector:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    },
                    timeout=timeout,
                ) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "article fetch HTTP %d for %s", resp.status, url
                        )
                        return None
                    # 只读取前 64KB 足够提取摘要
                    raw = await resp.content.read(65536)
                    # 尝试解码
                    content_type = resp.headers.get("Content-Type", "")
                    encoding = "utf-8"
                    if "charset=" in content_type:
                        encoding = content_type.split("charset=")[-1].split(";")[0]
                    try:
                        return raw.decode(encoding, errors="replace")
                    except (LookupError, ValueError):
                        return raw.decode("utf-8", errors="replace")
    except (asyncio.TimeoutError, aiohttp.ClientError, OSError) as e:
        logger.debug("article fetch failed for %s: %s", url, type(e).__name__)
        return None


async def enrich_summary(url: str, original_summary: Optional[str]) -> Optional[str]:
    """对单条资讯进行摘要富化。

    流程：
    1. 判断是否需要富化（_needs_enrich）
    2. 若需要，抓取文章 URL
    3. 从 HTML 提取首段文本
    4. 若提取成功，返回富化摘要；否则返回原始摘要（清空 HTML 标签）

    Args:
        url: 文章 URL
        original_summary: RSS 原始摘要（可能含 HTML 标签）

    Returns:
        富化后的纯文本摘要，或 None（无摘要）
    """
    if not _needs_enrich(original_summary):
        return original_summary

    # 先尝试剥离 HTML，看看是否还有内容
    if original_summary:
        clean = _strip_html(original_summary)
        if len(clean) >= SUMMARY_MIN_LEN and not _META_ONLY_RE.match(clean):
            return clean[:SUMMARY_MAX_LEN].strip()

    # 抓取文章
    html_text = await _fetch_article(url)
    if html_text is None:
        # 抓取失败，返回剥离 HTML 后的原始摘要（或 None）
        if original_summary:
            clean = _strip_html(original_summary)
            return clean[:SUMMARY_MAX_LEN].strip() if clean else None
        return None

    # 从文章 HTML 提取文本
    enriched = _extract_first_text(html_text)
    if enriched:
        return enriched

    # 文章提取失败，返回剥离 HTML 后的原始摘要
    if original_summary:
        clean = _strip_html(original_summary)
        return clean[:SUMMARY_MAX_LEN].strip() if clean else None
    return None


async def batch_enrich(
    items: list,
    max_concurrent: int = 5,
) -> list:
    """批量富化摘要。

    对 items 列表中的每个 item，检查并富化其 summary 字段。
    修改是就地进行的（mutate），同时返回 items 列表。
    并发控制：最多同时抓取 max_concurrent 篇文章。

    Args:
        items: HotspotItem 列表（需有 .summary 和 .url 属性）
        max_concurrent: 最大并发抓取数

    Returns:
        同 items 列表（已就地修改）
    """
    # 收集需要富化的 item
    to_enrich = []
    for item in items:
        if _needs_enrich(item.summary):
            to_enrich.append(item)

    if not to_enrich:
        logger.debug("batch_enrich: no items need enrichment")
        return items

    logger.info(
        "batch_enrich: enriching %d/%d items",
        len(to_enrich), len(items),
    )

    # 并发抓取
    sem = asyncio.Semaphore(max_concurrent)

    async def _enrich_one(item):
        async with sem:
            try:
                new_summary = await enrich_summary(str(item.url), item.summary)
                if new_summary is not None and new_summary != item.summary:
                    item.summary = new_summary
                    logger.debug(
                        "enriched summary for %s: %s…",
                        item.id, new_summary[:60],
                    )
            except Exception as e:
                logger.warning(
                    "enrich failed for %s: %s", item.id, e,
                )

    await asyncio.gather(*[_enrich_one(item) for item in to_enrich])

    enriched_count = sum(
        1 for item in to_enrich
        if item.summary is not None and len(item.summary) >= SUMMARY_MIN_LEN
        and not _META_ONLY_RE.match(item.summary)
    )
    logger.info(
        "batch_enrich: done, %d/%d enriched",
        enriched_count, len(to_enrich),
    )
    return items


__all__ = ["enrich_summary", "batch_enrich", "_needs_enrich", "_strip_html"]