"""Crawler v2 Phase 0 seed — 从现有 collector 提取源配置到 crawler_sources。

用法:
    python -c "from backend.services.crawler_seed import seed_sources; seed_sources()"

并行运行期: 新表只写不读，不影响现有功能。
"""
from __future__ import annotations

# AI
from backend.collectors.ai_collector import AI_SOURCES

# AI 安全
from backend.collectors.ai_security_collector import AI_SECURITY_SOURCES

# 标讯
from backend.collectors.bid_collector import BID_SOURCES

# 金融
from backend.collectors.finance_collector import FINANCE_SOURCES

# GDELT
from backend.collectors.gdelt_collector import GDELT_SOURCES

# GitHub
from backend.collectors.github_collector import GITHUB_SOURCES

# HN
from backend.collectors.hn_collector import HN_SOURCES

# OpenBB
from backend.collectors.openbb_collector import OPENBB_SOURCES

# OSS Insight
from backend.collectors.ossinsight_collector import OSSINSIGHT_SOURCES

# Reddit
from backend.collectors.reddit_collector import REDDIT_SOURCES

# ---------------------------------------------------------------------------
# 从现有 collector 提取源配置
# 每个 collector 导出 SOURCES 常量，格式为 list[dict]。
# 这里直接 import，不实例化 collector。
# ---------------------------------------------------------------------------
# 安全资讯
from backend.collectors.security_collector import SECURITY_SOURCES

# 创业
from backend.collectors.startup_collector import STARTUP_SOURCES

# 科技
from backend.collectors.tech_collector import TECH_SOURCES

# Telegram
from backend.collectors.telegram_collector import TELEGRAM_SOURCES
from backend.logging_config import logger
from backend.repository.db import get_connection

# category -> sources 映射
_SOURCE_GROUPS: list[tuple[str, str, list[dict]]] = [
    ("security", "security", SECURITY_SOURCES),
    ("ai_security", "ai_security", AI_SECURITY_SOURCES),
    ("ai", "ai", AI_SOURCES),
    ("finance", "finance", FINANCE_SOURCES),
    ("startup", "startup", STARTUP_SOURCES),
    ("bid", "bid", BID_SOURCES),
    ("github", "github", GITHUB_SOURCES),
    ("tech", "tech", TECH_SOURCES),
    ("tech", "hn", HN_SOURCES),
    ("tech", "reddit", REDDIT_SOURCES),
    ("finance", "openbb", OPENBB_SOURCES),
    ("security", "gdelt", GDELT_SOURCES),
    ("tech", "ossinsight", OSSINSIGHT_SOURCES),
    ("tech", "telegram", TELEGRAM_SOURCES),
]


def _make_source_id(category: str, name: str) -> str:
    """生成全局稳定源 ID: ``{category}:{name_slug}``"""
    slug = name.lower().strip()
    # 取中文/英文/数字，去特殊字符
    import re
    slug = re.sub(r'[^\w\u4e00-\u9fff]+', '_', slug).strip('_')[:60]
    return f"{category}:{slug}"


def _detect_kind(src: dict) -> str:
    """从源配置推断 kind: rss / json / html / browser"""
    if src.get("renderer") == "json":
        return "json"
    if src.get("rss_url"):
        return "rss"
    if src.get("renderer") == "browser" or src.get("use_crawl4ai"):
        return "browser"
    return "html"


def _get_url(src: dict) -> str:
    """取主 URL"""
    return src.get("rss_url") or src.get("api_url") or src.get("url", "")


def _get_feed_url(src: dict) -> str:
    """取 RSS URL"""
    return src.get("rss_url", "")


def _detect_parser_id(name: str, kind: str) -> str:
    """从源名称和 kind 推断 parser_id。

    Phase 1.1: P0 标讯源映射到独立 parser。
    """
    if kind == "rss":
        return "rss_generic"
    if kind == "json":
        return "json_generic"

    # P0 标讯源映射
    _P0_PARSER_MAP: dict[str, str] = {
        "中国政府采购网": "bid_ccgp",
        "招标投标公共服务平台": "bid_cebpub",
        "全国公共资源交易平台": "bid_ggzy",
        "中央政府采购网": "bid_zycg",
        "中国采购与招标网": "bid_chinabidding",
    }
    for key, parser_id in _P0_PARSER_MAP.items():
        if key in name:
            return parser_id

    return "html_generic"


def seed_sources() -> int:
    """从现有 collector 提取源配置并写入 crawler_sources。

    Returns:
        INSERT 的行数。
    """
    conn = get_connection()
    count = 0

    for category, _subcategory, sources in _SOURCE_GROUPS:
        for src in sources:
            name = src.get("name", "")
            url = _get_url(src)
            if not name or not url:
                continue

            source_id = _make_source_id(category, name)
            kind = _detect_kind(src)
            feed_url = _get_feed_url(src)
            max_items = src.get("max_items", 50)

            # Phase 1.1: 从 score 字段映射优先级
            score = src.get("score", 50)
            if score >= 80:
                priority = 90   # P0 — 国家级官方平台
            elif score >= 75:
                priority = 70   # P1 — 行业级平台
            elif score >= 70:
                priority = 60   # P2 — 商业聚合
            else:
                priority = 40   # P3 — 辅助渠道

            parser_id = _detect_parser_id(name, kind)

            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO crawler_sources
                        (id, category, name, kind, parser_id, url, feed_url,
                         max_items, priority, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (source_id, category, name, kind, parser_id, url, feed_url,
                     max_items, priority),
                )
                if conn.total_changes > 0:
                    count += 1
            except Exception as e:
                logger.warning(
                    "seed source failed",
                    extra={"source": name, "error": str(e)},
                )

    logger.info(
        "crawler_sources seeded",
        extra={"inserted": count, "total_groups": len(_SOURCE_GROUPS)},
    )
    return count


if __name__ == "__main__":
    n = seed_sources()
    print(f"Seeded {n} sources into crawler_sources")