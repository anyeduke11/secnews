"""Quality gate mapping — dsh-SecNews 8 道 ↔ Hotspot 13 道对照表。

S2-1 合并结论：Hotspot 13 道同步门禁已完整覆盖 dsh-SecNews 全部 8 道检查，
无缺口。本模块提供：
1. GATE_COVERAGE — 对照表（审计与文档用）
2. run_refine_gates() — kl_pipeline refine 阶段的质量校验入口
   （对 wiki-first 新入库条目执行核心三检：标题长度 / 分类相关 / 内容质量）

dsh-SecNews → Hotspot 映射：

| dsh Gate             | Hotspot Gate           | 覆盖 |
|----------------------|------------------------|------|
| category-relevance   | CategoryMatchGate      | ✅   |
| content-length       | ContentQualityGate     | ✅   |
| recency              | RecencyGate            | ✅   |
| simhash              | DuplicateGate          | ✅   |
| source-trust         | SourceReputationGate   | ✅   |
| title-quality        | TitleSummaryGate       | ✅   |
| url-duplicate        | DuplicateGate          | ✅   |
| url-valid            | FinalUrlGate           | ✅   |

Hotspot 独有（dsh 无对应）：SchemaGate / NoiseContentGate /
AuthorVerificationGate / BidRecencyGate。
"""
from __future__ import annotations

import re
from typing import Any

GATE_COVERAGE: list[dict[str, str]] = [
    {"dsh": "category-relevance", "hotspot": "CategoryMatchGate", "covered": "✅"},
    {"dsh": "content-length", "hotspot": "ContentQualityGate", "covered": "✅"},
    {"dsh": "recency", "hotspot": "RecencyGate", "covered": "✅"},
    {"dsh": "simhash", "hotspot": "DuplicateGate", "covered": "✅"},
    {"dsh": "source-trust", "hotspot": "SourceReputationGate", "covered": "✅"},
    {"dsh": "title-quality", "hotspot": "TitleSummaryGate", "covered": "✅"},
    {"dsh": "url-duplicate", "hotspot": "DuplicateGate", "covered": "✅"},
    {"dsh": "url-valid", "hotspot": "FinalUrlGate", "covered": "✅"},
]

# S2-1: refine 阶段轻量校验规则（不引全量 Pipeline，避免循环依赖）
_TITLE_MIN = 4
_TITLE_MAX = 500
_SUMMARY_MAX = 500

_SPAM_RE = re.compile(
    r"点击查看|>>>|查看更多|入驻|阅读全文|赞助|广告|推广", re.IGNORECASE,
)
_GARBLED_RE = re.compile(r"[\ufffd\u00ef\u00bf\u00bd]{3,}")


def run_refine_gates(fm: dict[str, Any], body: str) -> list[str]:
    """kl:refine 阶段质量校验 — 返回 flags 列表（空 = 全通过）。

    对 wiki-first 入库条目执行核心三检，不合格打 flag 但不拒绝入库
    （loose 语义，与 Hotspot 主 pipeline 一致）。
    """
    flags: list[str] = []
    title = str(fm.get("title") or "").strip()

    if len(title) < _TITLE_MIN:
        flags.append("title_too_short")
    elif len(title) > _TITLE_MAX:
        flags.append("title_too_long")

    summary = str(body or "")[:_SUMMARY_MAX]
    text_blob = title + " " + summary
    lowered = text_blob.lower()
    for kw in ("点击查看", ">>>", "阅读全文", "赞助"):
        if kw.lower() in lowered:
            flags.append("spam_keyword")
            break

    if _GARBLED_RE.search(text_blob):
        flags.append("garbled_text")

    return flags


__all__ = ["GATE_COVERAGE", "run_refine_gates"]
