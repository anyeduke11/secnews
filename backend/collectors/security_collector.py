"""网络安全热点数据采集器（Phase 3 重构）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.SECURITY``
- ``sources``   : 4 个权威安全资讯站（THN / 安全客 / FreeBuf / 嘶吼）
- ``timeout``   : 25s
- ``max_items`` : 60

外网抓取走 ``BaseCollector.fetch_source`` 默认实现。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。
"""
from __future__ import annotations

import re
from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

# 临时黑名单（2026-07-06 用户反馈）
# - krebsonsecurity.com: 抓到的资讯标题噪声太多（评论数 / 导航被误当标题）,
#   短期内不值得继续投入解析成本
# - infosec.exchange: 用户列入黑名单（即使未来重新加入 SECURITY_SOURCES
#   也会被过滤掉,防止误回填）
# - easyaq.com (E安全): Phase 24 用户反馈内容偏离网络安全主题,移除抓取
# - 启明星辰 (gm7.org): Phase 34 (2026-07-08) 用户反馈,内容质量差
#   (UI 显示大量噪声/短讯),停止抓取。域名 → 启明星辰 的映射仍保留在
#   PUBLISHER_REGISTRY 中,用于历史条目 author 解析
SOURCE_BLACKLIST: set[str] = {
    "KrebsOnSecurity",  # url=https://krebsonsecurity.com/
    "infosec.exchange",  # mastodon 实例
    "E安全",  # url=https://www.easyaq.com/
    "启明星辰",  # url=https://www.gm7.org/
}


def _filter_blacklist(sources: list[dict]) -> list[dict]:
    """按 ``name`` 字段过滤临时黑名单。

    不改原 list,返回新 list — 便于测试和热重载。
    """
    return [s for s in sources if s.get("name") not in SOURCE_BLACKLIST]


# ---------------------------------------------------------------------------
# Phase 33 (2026-07-08): 安全客 (anquanke.com) 标题黑名单
# ---------------------------------------------------------------------------
# 适用场景: 安全客首页 JSON 块中除了 ``list`` (真实文章) 还混入 4 类非资讯条目
#   1) 岗位招聘 (title=职位名, url=/job/<id>)       → 已被 URL 路径黑名单拦
#   2) 公司介绍 (title=公司名, url=/company/<id>)   → 已被 URL 路径黑名单拦
#   3) 专题聚合 (url=/subject/id/<id>)             → 已被 URL 路径黑名单拦
#   4) 周报页   (title="360网络安全周报", url=/week-list) → 标题+URL 双重拦
# 边缘情况: 偶有企业发布的"加入我们"/"公司介绍"软文走 ``/post/id/<n>`` 路径
# (URL 合法, 但标题纯粹是公司名/岗位名),此处通过标题正则兜底拦截。
# 仅对 url 含 ``anquanke.com`` 的源生效,不影响其他安全源。
# ---------------------------------------------------------------------------
_ANQUANKE_COMPANY_NAME_RE = re.compile(
    r"^[\u4e00-\u9fa5A-Za-z0-9·\-\s]+"  # 开头: 中文/英文/数字/·/连字符/空格
    r"(有限公司|股份有限公司|服务中心|分公司|子公司|办事处|事务所|研究院|实验室)$"
)
_ANQUANKE_JOB_TITLE_RE = re.compile(
    r"^[\u4e00-\u9fa5A-Za-z0-9·\-\s]+"  # 开头: 中文/英文/数字/·/连字符/空格
    r"(工程师|分析师|专家|顾问|架构师|研究员|总监|主管|经理|总裁|实习生|实习)$"
)


SECURITY_SOURCES: list[dict] = [
    # ===== 原有 5 源 (Phase 9/14) =====
    {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/", "score": 85},  # 黑名单
    {"name": "TheHackerNews", "url": "https://thehackernews.com/", "rss_url": "https://thehackernews.com/feeds/posts/default", "score": 82},
    {"name": "安全客", "url": "https://www.anquanke.com/", "rss_url": "https://api.anquanke.com/data/v1/rss", "score": 75},
    # Phase 22: 走 RSS 抓取,避免首页误抓 beian.miit.gov.cn 等页脚链接
    {
        "name": "FreeBuf",
        "url": "https://www.freebuf.com/",
        "rss_url": "https://www.freebuf.com/feed",
        "score": 75,
    },
    {"name": "嘶吼", "url": "https://www.4hou.com/", "rss_url": "https://www.4hou.com/feed", "score": 70},
    # ===== Phase 22 新增 — secnews §三 RSS 5 源 补齐 =====
    # V1.9: url 改为 index.php (与用户指定的首页路径一致), RSS 保持不变
    {
        "name": "SecWiki",
        "url": "https://www.sec-wiki.com/index.php",
        "rss_url": "https://www.sec-wiki.com/news/rss",
        "score": 70,
    },
    # ===== Phase 17 新增 — 监管机构 (信源总览 §二, 5 源) =====
    {
        "name": "国家金融监督管理总局",  # 监管处罚/行业动态 — 2026-08-02: JS SPA 空壳(215 bytes), 不可抓取
        "url": "https://www.nfra.gov.cn/",
        "score": 90,
        "max_items": 15,
        "renderer": "disabled",
    },
    # NOTE: 中国证监会于 Phase 48 移到 finance_collector.py (实际内容是金融监管公告/行政处罚/警示函, 不是 security)
    # V1.9: 中国人民银行 (pbc.gov.cn) 已移除 — 用户反馈内容非安全资讯
    # ===== Phase 17 新增 — 标准/漏洞库 (信源总览 §四, 3 源) =====
    {
        "name": "等级保护网",  # 等保标准 — 2026-08-02: 无文章内容(2.4KB, 0 links), 不可抓取
        "url": "https://www.djbh.net/",
        "score": 82,
        "renderer": "disabled",
    },
    {
        "name": "TC260 信安标委",  # 信息安全国标 — 2026-08-02: 无解析内容(30KB, 5 导航 links), 不可抓取
        "url": "https://www.tc260.org.cn/",
        "score": 82,
        "renderer": "disabled",
    },
    {
        "name": "CNNVD 国家漏洞库",  # 漏洞信息 — 2026-08-02: JS SPA 空壳(903 bytes), 不可抓取
        "url": "https://www.cnnvd.org.cn/",
        "score": 80,
        "renderer": "disabled",
    },
    # ===== Phase 17 新增 — 安全媒体 (信源总览 §三 §八 RSS, 4 源) =====
    {
        "name": "安全内参",  # secrss.com 6 类全覆盖
        "url": "https://www.secrss.com/",
        "api_url": "https://www.secrss.com/api/articles",
        "score": 80,
        "renderer": "json",  # V1.9: 走 JSON API 获取 published_at
    },
    # Phase 24: E安全 (easyaq.com) 已移除 — 用户反馈内容偏离网络安全主题
    # 旧条目保留在 quality_flags / publisher_registry 但 SECURITY_SOURCES 不再抓取
    {
        "name": "HackRead",  # 国际安全媒体 — 直连 CF 封禁但代理可用(74 links)
        "url": "https://www.hackread.com/",
        "score": 72,
    },
    {
        "name": "Schneier on Security",  # 密码学专家; 直连 CF 封禁但代理可用(135 links)
        "url": "https://www.schneier.com/",
        "score": 78,
    },
    # ===== Phase 17 新增 — 安全厂商 (信源总览 §八 选 5) =====
    # 2026-08-02 实测: 以下厂商站点均为 JS SPA 企业站/空壳，无可解析文章内容
    # 奇安信威胁情报(1.3KB), 深信服(520KB 全导航), 绿盟科技(466B), 知道创宇(2.3KB)
    {
        "name": "奇安信威胁情报",
        "url": "https://ti.qianxin.com/",
        "score": 85,
        "renderer": "disabled",
    },
    {
        "name": "深信服科技",
        "url": "https://www.sangfor.com.cn/",
        "score": 78,
        "renderer": "disabled",
    },
    {
        "name": "绿盟科技",
        "url": "https://www.nsfocus.com/",
        "score": 78,
        "renderer": "disabled",
    },
    {
        # Phase 23: venustech.com.cn 报 403, 改用 secnews §三同款 RSS (gm7.org/feed)
        "name": "启明星辰",  # 信息安全知识库 (gm7.org = 启明星辰安全简讯)
        "url": "https://www.gm7.org/",
        "rss_url": "https://www.gm7.org/feed",
        "score": 76,
    },
    {
        "name": "知道创宇",
        "url": "https://www.knownsec.com/",
        "score": 76,
        "renderer": "disabled",
    },
    # ===== 安全公众号 (2026-08-02 新增, 走 sogou weixin 搜索) =====
    {
        "name": "微步在线",
        "account_name": "微步在线",
        "score": 85,
        "renderer": "wechat",
    },
    {
        "name": "360威胁情报中心",
        "account_name": "360威胁情报中心",
        "score": 84,
        "renderer": "wechat",
    },
    {
        "name": "安全内参",
        "account_name": "安全内参",
        "score": 83,
        "renderer": "wechat",
    },
    {
        "name": "奇安信集团",
        "account_name": "奇安信集团",
        "score": 82,
        "renderer": "wechat",
    },
    {
        "name": "看雪学院",
        "account_name": "看雪学院",
        "score": 80,
        "renderer": "wechat",
    },
    {
        "name": "腾讯安全",
        "account_name": "腾讯安全",
        "score": 80,
        "renderer": "wechat",
    },
    {
        "name": "火绒安全",
        "account_name": "火绒安全",
        "score": 78,
        "renderer": "wechat",
    },
    {
        "name": "长亭科技",
        "account_name": "长亭科技",
        "score": 76,
        "renderer": "wechat",
    },
    {
        "name": "青藤云安全",
        "account_name": "青藤云安全",
        "score": 76,
        "renderer": "wechat",
    },
    {
        "name": "阿里云安全",
        "account_name": "阿里云安全",
        "score": 75,
        "renderer": "wechat",
    },
    {
        "name": "中国信息安全",
        "account_name": "中国信息安全",
        "score": 75,
        "renderer": "wechat",
    },
# ===== 旧 sogou 搜索源已被 renderer="wechat" 替代 (2026-08-02) =====
]


class SecurityCollector(BaseCollector):
    """采集网络安全领域热点数据。"""

    category = Category.SECURITY
    # 应用临时黑名单 — 重新加回只需在 SOURCE_BLACKLIST 移除对应 name
    sources: list[dict] = _filter_blacklist(SECURITY_SOURCES)
    timeout = 25
    # Phase 24: max_items 提到 400。19 源实测可达 12 源 (嘶吼 40+安全客 37+Schneier 52+
    # HackRead 38+安全内参 30+深信服 25+FreeBuf 20+启明星辰 20+证监会 15+央行 15
    # +TC260 11+SecWiki 10 = 313) + per-source cap 留余量;E安全已移除
    # V1.9: +7 搜狗微信公众号源 → 上调到 500 容纳新增量
    # 旧值 200 仍会导致末位 RSS 源(启明星辰)被截断不入库
    max_items = 500

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [],UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。

    def _title_relevant(
        self, title: str, url: str, source: dict
    ) -> bool:
        """Phase 33 (2026-07-08) override: 安全客标题黑名单。

        在 BaseCollector 默认实现基础上,叠加安全客特定的标题正则:
        - 公司名结尾 (有限公司 / 服务中心 / 研究院 等)
        - 岗位名结尾 (工程师 / 分析师 / 实习生 等)
        仅对源 url 含 ``anquanke.com`` 的条目生效,其他源走默认实现。
        """
        from backend.collectors.keywords import _is_title_relevant_to_category

        if not _is_title_relevant_to_category(title, self.category.value):
            return False
        src_url = source.get("url", "") if isinstance(source, dict) else ""
        if "anquanke.com" in src_url:
            t = (title or "").strip()
            if _ANQUANKE_COMPANY_NAME_RE.match(t) or _ANQUANKE_JOB_TITLE_RE.match(t):
                return False
        return True

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """安全内参 JSON API 解析 (V1.9)。

        响应格式:
          {"code": 10000, "msg": "操作成功", "data": [
              {"id": 92698, "title": "...", "summary": "...",
               "published_at": "2026-07-31 18:32:00", ...}
          ]}
        published_at 为 Shanghai 时区 naive datetime 字符串。
        """
        from datetime import datetime, timezone

        records = ((data or {}).get("data") or [])
        out: list[dict[str, Any]] = []
        for entry in records:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            article_id = entry.get("id")
            if not title or not article_id:
                continue
            url = f"https://www.secrss.com/articles/{article_id}"
            # 解析 published_at: "2026-07-31 18:32:00" (Shanghai, naive)
            published_at: datetime | None = None
            pub_str = entry.get("published_at")
            if pub_str:
                try:
                    naive = datetime.strptime(str(pub_str)[:19], "%Y-%m-%d %H:%M:%S")
                    published_at = naive.replace(tzinfo=timezone.utc) - __import__("datetime").timedelta(hours=8)
                except (ValueError, TypeError):
                    published_at = None
            out.append(
                {
                    "title": title,
                    "url": url,
                    "summary": (entry.get("summary") or "").strip(),
                    "published_at": published_at,
                }
            )
        return out


__all__ = ["SECURITY_SOURCES", "SecurityCollector"]
