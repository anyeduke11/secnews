"""aiohttp 响应体宽容解码 — 政企/老站编码陷阱兜底.

cadence 修正批 (T2.2) 实测根因: 招标采购导航网 (okcis.cn) HTTP 200 / 472KB /
``Content-Type: text/html; charset=GB2312``, 但正文含 GBK 扩展字 (0xa8 ...),
``await resp.text()`` 严格按声明解码直接抛 ``UnicodeDecodeError``; bid 级联链
``except Exception`` 吞掉后 ``html=None`` → "crawl4ai+direct+proxy all failed",
源被判 dead 数十轮 — 页面其实一直可达。全仓 5 处 ``resp.text()`` 同样暴露。

解码顺序 (全部严格, 首个成功即返回):
    1. 响应头声明 charset (gb2312 / gbk / x-gbk 一律升级为超集 gb18030)
    2. 正文前 4KB 的 ``<meta charset=...>`` / ``http-equiv`` 声明 (同样升级)
    3. utf-8
    4. gb18030
    全败 → utf-8 ``errors="replace"`` (宁可少量乱码, 不可丢整页)。
"""
from __future__ import annotations

import re

_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE)

# gb2312 ⊂ gbk ⊂ gb18030: 声明小集合、内容含大集合字符是政企站通病, 一律用超集解码
_ALIASES = {
    "gb2312": "gb18030",
    "gb_2312-80": "gb18030",
    "gbk": "gb18030",
    "x-gbk": "gb18030",
    "cp936": "gb18030",
    "ms936": "gb18030",
}


def decode_html_bytes(raw: bytes, declared: str | None = None) -> str:
    """把响应字节宽容解码为 str (见模块 docstring 的顺序)."""
    candidates: list[str] = []

    def _add(cs: str | None) -> None:
        if not cs:
            return
        norm = cs.strip().strip("\"'").lower()
        norm = _ALIASES.get(norm, norm)
        if norm and norm not in candidates:
            candidates.append(norm)

    _add(declared)
    m = _META_CHARSET.search(raw[:4096])
    if m:
        _add(m.group(1).decode("ascii", "ignore"))
    _add("utf-8")
    _add("gb18030")
    for cs in candidates:
        try:
            return raw.decode(cs)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


async def read_text_lenient(resp) -> str:
    """``await resp.text()`` 的宽容替代: 读原始字节后走 :func:`decode_html_bytes`.

    ``resp`` 为 ``aiohttp.ClientResponse`` (或鸭子类型: ``read()`` 协程 + ``charset`` 属性)。
    没有 ``read()`` 的对象 (测试桩 / 非 aiohttp 响应) 回落到 ``text()``。
    """
    read = getattr(resp, "read", None)
    if read is None:
        return await resp.text()
    raw = await read()
    if isinstance(raw, str):
        return raw
    declared = getattr(resp, "charset", None)
    return decode_html_bytes(raw, declared if isinstance(declared, str) else None)


__all__ = ["decode_html_bytes", "read_text_lenient"]
