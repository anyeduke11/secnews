"""解析器基类 — 所有站点特定解析器的统一接口。

设计
----
- ``parse(content, url, content_type)`` 是唯一公共方法
- 返回 ``list[RawItem]`` — 已过滤的原始条目
- 子类只需实现 ``_do_parse()``
- 验证（标题长度 ≥8、URL 非空）在基类自动完成
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RawItem:
    """解析器输出的原始条目（尚未经 collector 的 build_items 处理）。"""

    __slots__ = ("published_at", "summary", "title", "url")

    def __init__(
        self,
        title: str,
        url: str,
        summary: str = "",
        published_at: str | None = None,
    ):
        self.title = title
        self.url = url
        self.summary = summary
        self.published_at = published_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published_at": self.published_at,
        }

    def __repr__(self) -> str:
        return f"<RawItem title={self.title!r} url={self.url!r}>"


class BaseSourceParser(ABC):
    """所有站点解析器的基类。

    Attributes:
        source_id: 唯一标识（对应 BaseCollector sources 列表中的 id）
        version: 语义版本号，站点改版时递增
    """

    source_id: str = ""
    version: str = "1.0.0"

    @abstractmethod
    def _do_parse(self, content: str, url: str, content_type: str) -> list[RawItem]:
        """子类实现实际的解析逻辑。"""
        ...

    def parse(self, content: str, url: str, content_type: str = "html") -> list[RawItem]:
        """解析内容并验证条目。

        Args:
            content: 原始内容（HTML/JSON 字符串）
            url: 来源 URL
            content_type: "html" | "json" | "js"

        Returns:
            验证通过的 RawItem 列表
        """
        items = self._do_parse(content, url, content_type)
        return self._validate(items)

    def _validate(self, items: list[RawItem]) -> list[RawItem]:
        """过滤无效条目。"""
        return [it for it in items if len(it.title) >= 8 and it.url]


__all__ = ["BaseSourceParser", "RawItem"]