"""质量门禁配置中心。

- :class:`QualityMode`  严格 / 宽松 枚举
- :class:`QualityConfig` 配置聚合（含默认）
- :func:`default_category_keywords` 5 个分类的默认关键词
- :func:`get_category_keywords`      从 settings 表读 + 兜底默认
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from backend.domain.enums import Category
from backend.logging_config import logger
from backend.repository.settings_repo import SettingsRepository


class QualityMode(str, Enum):
    """严格 / 宽松 模式。

    - ``LOOSE`` 失败时打 flag + 扣分，但仍入库（默认）
    - ``STRICT`` 失败时打 flag + 扣分；评分 < 阈值时**拒绝入库**
    """

    LOOSE = "loose"
    STRICT = "strict"


# ---------------------------------------------------------------------------
# 默认关键词
# ---------------------------------------------------------------------------
DEFAULT_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    Category.AI.value: [
        "AI", "人工智能", "大模型", "LLM", "GPT", "Claude",
        "OpenAI", "Anthropic", "深度学习", "神经网络", "机器学习",
        # Phase 14 扩充: 覆盖具身智能 / 算力 / 芯片等 2026 热点
        "具身智能", "机器人", "算力", "芯片", "GPU", "Meta",
        "智能体", "agent", "AGI", "生成式", "AIGC", "智算",
    ],
    Category.SECURITY.value: [
        "漏洞", "CVE", "安全", "勒索", "黑客", "attack",
        "exploit", "malware", "phishing", "威胁", "0day",
        # Phase 14 扩充: AI 安全 / 数据安全
        "数据安全", "网安", "信息安全", "攻防", "护网",
        "ransomware", "backdoor", "后门", "APT", "供应链攻击",
    ],
    Category.FINANCE.value: [
        "股票", "基金", "财报", "上市公司", "央行", "汇率",
        "stock", "earnings", "Fed", "利率", "GDP", "CFA",
        # Phase 14 扩充: 覆盖债券 / 大盘 / 板块等更宽泛金融内容
        "债券", "周报", "研究", "操作", "策略", "A股", "港股", "美股",
        "大盘", "板块", "涨幅", "跌幅", "牛市", "熊市", "通胀", "通缩",
        "IPO", "退市", "停牌", "复牌", "分红", "回购", "市值",
    ],
    Category.STARTUP.value: [
        "创业", "融资", "独角兽", "众筹", "种子轮", "A轮",
        "startup", "funding", "YC", "种子", "天使", "孵化",
        # Phase 14 扩充: 覆盖投资界 RSS 实际内容
        "VENTURE", "IPO", "上市", "资本", "事件", "投资", "机构",
        "回报", "国资", "敲锣", "下线", "智能体", "创始人", "CEO",
        "B轮", "C轮", "D轮", "估值", "独角兽", "并购", "M&A",
    ],
    Category.BID.value: [
        "招标", "投标", "中标", "采购", "公告", "政府采购",
        "tender", "bid", "procurement", "工程", "标段", "竞标",
    ],
    Category.GITHUB.value: [
        "github", "trending", "star-history", "repo", "awesome",
        "llm", "cursor", "claude", "openai", "langchain", "rust", "agent",
    ],
    # Phase 25 P1: tech (IT/科技) 分类默认关键词
    # 覆盖 IT之家 / Solidot / 稀土掘金 / 酷安 等 IT 资讯源
    Category.TECH.value: [
        "科技", "互联网", "IT", "数码", "手机", "电脑", "硬件", "软件",
        "系统", "应用", "平台", "发布", "更新", "版本", "芯片", "处理器",
        "5G", "6G", "WiFi", "蓝牙", "USB", "Type-C", "SSD", "内存",
        "Linux", "Windows", "macOS", "iOS", "Android", "鸿蒙",
        "苹果", "Apple", "华为", "小米", "三星", "OPPO", "vivo",
        "发布会", "亮相", "推出", "上线", "开源", "社区",
    ],
}


def default_category_keywords() -> dict[str, list[str]]:
    """返回 7 个分类的默认关键词（深拷贝，避免外部修改污染默认）。"""
    return {k: list(v) for k, v in DEFAULT_CATEGORY_KEYWORDS.items()}


def get_category_keywords(category: Category) -> list[str]:
    """从 ``settings`` 表读 ``quality.category_keywords.<cat>``；缺失走默认。

    读取失败（DB 异常）走默认 + 写一条 WARNING log。
    """
    key = f"quality.category_keywords.{category.value}"
    try:
        repo = SettingsRepository()
        value = repo.get(key, default=None)
        if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
            return value
    except Exception as e:
        logger.warning(
            "get_category_keywords failed, using defaults",
            extra={"trace_id": "", "key": key, "error": str(e)},
        )
    return list(DEFAULT_CATEGORY_KEYWORDS.get(category.value, []))


# ---------------------------------------------------------------------------
# QualityConfig
# ---------------------------------------------------------------------------
class QualityConfig:
    """运行时质量配置聚合。

    实例化时立即从 settings + 环境变量读取；后续可通过
    :meth:`refresh` 重新拉取。
    """

    def __init__(self) -> None:
        self._repo = SettingsRepository()
        self._cache: dict[str, Any] = {}
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """从 settings + config 重新拉取。"""
        from backend.config import config as _app_config

        self._cache = {
            "strict_mode": bool(self._repo.get("quality.strict_mode",
                                               _app_config.quality_strict_mode)),
            "min_score": int(self._repo.get("quality.min_score",
                                            _app_config.quality_min_score)),
            "url_check_sample_rate": float(self._repo.get(
                "quality.url_check_sample_rate",
                _app_config.quality_url_check_sample_rate,
            )),
            "url_check_concurrency": int(self._repo.get(
                "quality.url_check_concurrency", 5
            )),
            "url_check_timeout": int(self._repo.get(
                "quality.url_check_timeout", _app_config.quality_url_check_timeout
            )),
            "url_check_interval_seconds": int(self._repo.get(
                "quality.url_check_interval_seconds", 300
            )),
            "reputation_interval_seconds": int(self._repo.get(
                "quality.reputation_interval_seconds", 21600
            )),
            "category_keywords": self._load_all_keywords(),
        }

    def _load_all_keywords(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for cat in Category:
            out[cat.value] = get_category_keywords(cat)
        return out

    # ------------------------------------------------------------------
    @property
    def mode(self) -> QualityMode:
        return QualityMode.STRICT if self._cache["strict_mode"] else QualityMode.LOOSE

    @property
    def min_score(self) -> int:
        return self._cache["min_score"]

    @property
    def url_check_sample_rate(self) -> float:
        return self._cache["url_check_sample_rate"]

    @property
    def url_check_concurrency(self) -> int:
        return self._cache["url_check_concurrency"]

    @property
    def url_check_timeout(self) -> int:
        return self._cache["url_check_timeout"]

    @property
    def url_check_interval_seconds(self) -> int:
        return self._cache["url_check_interval_seconds"]

    @property
    def reputation_interval_seconds(self) -> int:
        return self._cache["reputation_interval_seconds"]

    @property
    def category_keywords(self) -> dict[str, list[str]]:
        return self._cache["category_keywords"]


__all__ = [
    "QualityMode",
    "QualityConfig",
    "DEFAULT_CATEGORY_KEYWORDS",
    "default_category_keywords",
    "get_category_keywords",
]
