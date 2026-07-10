"""招标资讯热点数据采集器（Phase 3 + Phase 9 + Bug 1 修复）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.BID``
- ``sources``   : 30+ 国家级 / 行业级 / 商业级招标平台（覆盖 skillhub 网安标讯助手推荐渠道）
- ``timeout``   : 25s
- ``max_items`` : 40

Phase 9 改造：
1. 渠道扩充：8 → 30+ 源（金融/能源/电信/医疗/交通/商业聚合全覆盖）
2. 关键词过滤：四线 AND/OR 体系（安全服务线 / 安全产品线 / 运维平台线 / 行业搜索线），
   只保留网络安全/AI安全相关的招标，避免大量无关采购信息
3. 抓取过滤：在 ``_parse_html`` 中应用关键词过滤

Phase 13 硬约束: 撤销 Phase 12 的 Google 搜索 fallback 方案。用户明确反
对"把搜索工作推给用户"。源全部失败时直接返回空列表,UI 显示
"该分类暂无可用资讯"。详细约束见 SPEC §3。

参考 skillhub 网安标讯助手：
    https://skillhub.cn/skills/bid-news-collection-light
"""
from __future__ import annotations

import re

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

# ---------------------------------------------------------------------------
# 30+ 招标渠道（覆盖 skillhub 推荐 50+ 渠道的关键子集）
# ---------------------------------------------------------------------------
# P0 国家级官方平台
# P1 金融行业
# P1 能源电力
# P1 电信运营商
# P1 政府机构
# P2 医疗教育
# P2 交通制造
# P2 商业聚合
# P3 辅助渠道
BID_SOURCES: list[dict] = [
    # ===== P0 国家级官方平台（5） =====
    {
        "name": "中国政府采购网",
        "url": "https://www.ccgp.gov.cn/cggg/zygg/",
        "score": 80,
        "keywords": ["bid", "government"],
    },
    {
        "name": "招标投标公共服务平台",
        "url": "https://www.cebpubservice.com/ggxx/",
        "score": 80,
        "keywords": ["bid", "public"],
    },
    {
        "name": "全国公共资源交易平台",
        "url": "https://www.ggzy.gov.cn/info/zbgg",
        "score": 80,
        "keywords": ["bid", "public"],
    },
    {
        "name": "中央政府采购网",
        "url": "https://www.zycg.gov.cn/freecms/site/zycg/ggxx/info/",
        "score": 78,
        "keywords": ["bid", "government"],
    },
    {
        "name": "中国采购与招标网",
        "url": "https://www.chinabidding.com.cn/zbgg/",
        "score": 75,
        "keywords": ["bid", "platform"],
    },
    # ===== P1 金融行业（6+6=12 源 — Phase 16 补全表格 P1 缺口） =====
    {
        "name": "深交所采购信息",
        "url": "https://www.szse.cn/disclosure/notice/general/",
        "score": 80,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "上交所采购信息",
        "url": "https://www.sse.com.cn/services/trading/business/",
        "score": 80,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "中金所采购公告",
        "url": "https://www.cffex.com.cn/",
        "score": 78,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "国家开发银行采购",
        "url": "https://www.cdb.cn/",
        "score": 78,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "成方金融采购网",
        "url": "https://www.cfid.org.cn/",
        "score": 76,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "金融采购网",
        "url": "https://www.cfcpn.com/",
        "score": 75,
        "keywords": ["bid", "finance"],
    },
    # Phase 16 新增 — 覆盖表格 P1 金融缺口
    {
        "name": "中国人民银行集中采购中心",  # 表格 "央行(jzcg)"
        "url": "https://jzcg.pbc.gov.cn/",
        "score": 80,
        "keywords": ["bid", "finance", "central_bank"],
    },
    {
        "name": "中国采购与招标网-金融频道",  # 表格 "标探云脑" 无公开入口,改用 chinabidding 第三方聚合
        "url": "https://www.chinabidding.com.cn/bidList-0-0-1-0-0-1.html",  # 金融分类
        "score": 76,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "采招网-金融频道",  # 表格 "银保信" / "中国银联" / "证保信" 垂直机构无公开列表,用 bidcenter 第三方聚合替代
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-1-1-0.htm",  # 金融分类
        "score": 75,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "晨歌招标网",  # Phase 16 探针: 365bid 跳 lander 失败,改用 chengezhao.com
        "url": "https://www.chengezhao.com/",
        "score": 72,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "招标网-金融频道",  # 第三方聚合
        "url": "https://www.zhaobiao.cn/bidding/list?catId=2",  # 金融分类
        "score": 72,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "采联网-金融频道",  # 第三方聚合
        "url": "https://www.zgzbw.com/list-1.html",  # 金融分类
        "score": 70,
        "keywords": ["bid", "finance", "aggregator"],
    },
    # ===== P1 能源电力（6） =====
    {
        "name": "国家电网电子商务平台",
        "url": "https://ecp.sgcc.com.cn/html/project/index_1.shtml",
        "score": 80,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "南方电网采购",
        "url": "https://www.bidding.csg.cn/",
        "score": 80,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "国家能源采购",
        "url": "https://www.chnenergybidding.com.cn/",
        "score": 78,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "中石化采购",
        "url": "https://www.sinopec-ec.com/",
        "score": 76,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "电力招标网",
        "url": "https://www.dlzb.com/",
        "score": 72,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "电力能源招标网",
        "url": "https://www.dlnyzb.com/",
        "score": 70,
        "keywords": ["bid", "energy"],
    },
    # ===== P1 电信运营商（4） =====
    {
        "name": "中国移动 B2B 采购",
        "url": "https://b2b.10086.cn/",
        "score": 80,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国电信采购",
        "url": "https://caigou.chinatelecom.com.cn/",
        "score": 78,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国联通采购",
        "url": "https://www.chinaunicombidding.com/",
        "score": 76,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国广电采购",
        "url": "https://www.zgdsy.com.cn/",
        "score": 70,
        "keywords": ["bid", "telecom"],
    },
    # ===== P2 医疗教育（2+2=4 源 — Phase 16 补全表格 P2 缺口） =====
    {
        "name": "卫健委采购平台",
        "url": "https://www.nhc.gov.cn/",
        "score": 72,
        "keywords": ["bid", "medical"],
    },
    {
        "name": "教育部政府采购",
        "url": "https://www.moe.gov.cn/",
        "score": 70,
        "keywords": ["bid", "education"],
    },
    # Phase 16 新增 — 表格 "医学院校采购网" / "公立医院采购平台"
    # 两者都没有独立公开列表页,用第三方聚合站的医疗分类替代
    {
        "name": "采招网-医疗频道",  # 表格 "公立医院采购平台"
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-3-1-0.htm",  # 医疗分类
        "score": 72,
        "keywords": ["bid", "medical", "aggregator"],
    },
    {
        "name": "采招网-教育频道",  # 表格 "医学院校采购网"
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-4-1-0.htm",  # 教育分类
        "score": 70,
        "keywords": ["bid", "education", "aggregator"],
    },
    # ===== P2 交通制造（4） =====
    {
        "name": "交通运输部采购",
        "url": "https://www.mot.gov.cn/",
        "score": 72,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "国铁集团采购平台",
        "url": "https://www.crgc.cc/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "中车集团采购",
        "url": "https://www.crsc.com.cn/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "中船集团采购",
        "url": "https://www.cssc.com.cn/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    # ===== P2 商业聚合（6+6=12 源 — Phase 16 补全表格 P2 缺口） =====
    {
        "name": "采招网",
        "url": "https://www.bidcenter.com.cn/",
        "score": 70,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "千里马招标网",
        "url": "https://www.qianlima.com/",
        "score": 68,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "乙方宝",
        "url": "https://www.yifangbao.com/",
        "score": 66,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "政采云",
        "url": "https://www.zcygov.cn/",
        "score": 72,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "军队采购网",
        "url": "https://www.plap.cn/",
        "score": 74,
        "keywords": ["bid", "military"],
    },
    {
        "name": "中招联合招标采购",
        "url": "https://www.zbj.com/",
        "score": 65,
        "keywords": ["bid", "aggregator"],
    },
    # Phase 16 新增 — 补全表格 P2 商业聚合
    {
        "name": "招标网",  # zhaobiao.cn 综合商业聚合
        "url": "https://www.zhaobiao.cn/",
        "score": 68,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "比比招标",  # Phase 16 探针发现 365bid 跳 lander 落地页,改用 chengezhao.com
        "url": "https://www.chengezhao.com/zfcg/",  # 政府采购分类
        "score": 67,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "采联网",  # zgzbw.com
        "url": "https://www.zgzbw.com/",
        "score": 67,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "招标信息港",  # bidnews.cn
        "url": "https://www.bidnews.cn/",
        "score": 66,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "易招标",  # ebnew.com
        "url": "https://www.ebnew.com/",
        "score": 65,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "深圳公共资源交易",  # szexgrp.com (与 P3 重叠,放这里方便统一)
        "url": "https://www.szexgrp.com/",
        "score": 70,
        "keywords": ["bid", "public", "aggregator"],
    },
    # ===== P3 辅助渠道（2 — 深圳公共资源交易已上移到 P2 商业聚合） =====
    {
        "name": "蚂蚁投标",
        "url": "https://www.mayitb.com/",
        "score": 60,
        "keywords": ["bid", "aggregator"],
    },
    # ===== Phase 19: v1.6.3 补全 16 源（renderer=search 走搜索引擎绕反爬）=====
    # 标讯信源普遍有 anti-bot / WAF / 强制 JS 渲染,直抓成功率近 0。
    # v1.6.3 思路：用搜索引擎 (DDG HTML) 抓 site:<domain> 关键词,
    #   **提取真实源 URL** 而非搜索引擎跳转 URL,这样:
    #   - url_validity 跑 HEAD 通过(测的是源站 URL,不是 DDG URL)
    #   - 不命中 FORBIDDEN_URL_PATTERNS (无 google.com/search 等)
    #   - author_verification 走新注册表(见 publisher_registry.py)
    #   - 整链路不违反质量门禁
    # ----- P1 金融缺口 -----
    {
        "name": "中国农业发展银行集中采购",
        "url": "https://pms.adbc.com.cn/",
        "score": 78,
        "keywords": ["bid", "finance", "policy_bank"],
        "renderer": "search",
    },
    {
        "name": "银保信",
        "url": "https://www.cfxcredit.com/",
        "score": 76,
        "keywords": ["bid", "finance", "banking_assoc"],
        "renderer": "search",
    },
    {
        "name": "中国银联采购",
        "url": "https://www.chinaunionpay.com/",
        "score": 76,
        "keywords": ["bid", "finance", "unionpay"],
        "renderer": "search",
    },
    {
        "name": "知了标讯",
        "url": "https://www.zhiliaobiaoxun.com/",
        "score": 70,
        "keywords": ["bid", "finance", "aggregator"],
        "renderer": "search",
    },
    {
        "name": "证保信",
        # v1.6.3 提到但未给 URL;这里用 search 模式只需 site: 域名
        # 实际我们用 site:zgzx-pa.com.cn (深圳证券结算公司) 作为代理
        "url": "https://zgzx-pa.com.cn/",
        "score": 70,
        "keywords": ["bid", "finance", "cert_registry"],
        "renderer": "search",
    },
    # ----- P1 能源电力缺口 -----
    {
        "name": "华能电子商务平台",
        "url": "https://ec.chng.com.cn/",
        "score": 78,
        "keywords": ["bid", "energy", "huaneng"],
        "renderer": "search",
    },
    {
        "name": "大唐电子商务平台",
        "url": "https://www.cdt-ec.com/",
        "score": 78,
        "keywords": ["bid", "energy", "datang"],
        "renderer": "search",
    },
    {
        "name": "华电电子商务平台",
        "url": "https://www.chdtp.com/",
        "score": 78,
        "keywords": ["bid", "energy", "huadian"],
        "renderer": "search",
    },
    {
        "name": "中化商务电子招投标",
        "url": "https://ebid.sinochemitc.com/",
        "score": 74,
        "keywords": ["bid", "energy", "sinochem"],
        "renderer": "search",
    },
    {
        "name": "深圳阳光采购平台",
        "url": "https://ygcg.szexgrp.com/",
        "score": 72,
        "keywords": ["bid", "public", "shenzhen"],
        "renderer": "search",
    },
    # ----- P2 商业聚合缺口 -----
    {
        "name": "招标采购导航网",
        "url": "https://www.okcis.cn/",
        "score": 68,
        "keywords": ["bid", "aggregator", "okcis"],
        "renderer": "search",
    },
    {
        "name": "比地招标网",
        "url": "https://www.bidizhaobiao.com/",
        "score": 66,
        "keywords": ["bid", "aggregator", "bidizhaobiao"],
        "renderer": "search",
    },
    {
        "name": "元博招标网",
        "url": "https://www.bidchance.com/",
        "score": 66,
        "keywords": ["bid", "aggregator", "bidchance"],
        "renderer": "search",
    },
    {
        "name": "中国国际招标网",
        "url": "https://chinabidding.mofcom.gov.cn/",
        "score": 72,
        "keywords": ["bid", "aggregator", "mofcom"],
        "renderer": "search",
    },
    {
        "name": "中国政府采购招标网",
        "url": "https://www.chinabidding.org.cn/",
        "score": 66,
        "keywords": ["bid", "aggregator", "chinabidding_org"],
        "renderer": "search",
    },
    # ----- P3 辅助缺口 -----
    {
        "name": "中国外汇交易中心",
        "url": "https://www.chinamoney.com.cn/",
        "score": 68,
        "keywords": ["bid", "finance", "forex"],
        "renderer": "search",
    },
]

# Phase 14/19: 标讯类源默认走 crawl4ai (政府站点普遍有 WAF / JS 渲染)
#   - setdefault 不会覆盖已显式设 renderer="search" 的源 (Phase 19 新增 16 源)
#   - "search" 路径走 DDG HTML 搜索,提取真实源 URL (v1.6.3 思路)
for _src in BID_SOURCES:
    _src.setdefault("renderer", "crawl4ai")


# ---------------------------------------------------------------------------
# 四线 AND/OR 关键词体系（参考 skillhub 网安标讯助手）
# ---------------------------------------------------------------------------
# 四条业务线，每条线内的核心关键词（OR），加上采购语境词（AND）：
#   任意一条业务线的核心关键词命中（OR）即视为网络安全/AI安全相关。
SECURITY_KEYWORDS: dict[str, list[str]] = {
    # ===== 安全服务线（22 + 8 补充 = 30 词） =====
    # Phase 16 补充: 表格"覆盖范围"列出的合规测评/攻防实战/检测审计,
    # 网安领域常用的应急响应/安全咨询/安全体系规划/数据安全咨询。
    "安全服务线": [
        # Phase 9 原有
        "等保", "等级保护", "密评", "密码评估", "密码改造", "密码应用",
        "渗透测试", "攻防演练", "重保", "护网",
        "安全评估", "安全检测", "安全审计", "风险评估",
        "安全咨询", "安全服务", "安全测评", "安全认证",
        "网络安全", "信息安全", "网信安全", "安全防护",
        # Phase 16 补充 — 表格"覆盖范围" + 完整网安术语
        "合规测评",      # 表格"覆盖范围"
        "攻防实战",      # 表格"覆盖范围"
        "检测审计",      # 表格"覆盖范围"
        "应急响应",      # 网安常用: 勒索病毒/数据泄露响应
        "安全规划",      # 安全体系咨询
        "安全体系",      # 体系化建设
        "安全培训",      # 意识培训/CTF 培训
        "安全运维",      # 也常作为服务线,这里和运维线互补
    ],
    # ===== 安全产品线（30 + 12 补充 = 42 词） =====
    # Phase 16 补充: 表格"覆盖范围"的网安设备,
    # 网安领域新型产品 API 安全/UEBA/NDR/SOAR/CASB/NTA。
    "安全产品线": [
        # Phase 9/14 原有
        "防火墙", "IPS", "IPS 设备", "IDS", "IDS 设备", "WAF", "WAF 设备", "漏洞扫描",
        "态势感知", "堡垒机", "数据库审计", "邮件安全",
        "DLP", "DLP 系统", "零信任", "EDR", "EDR 系统", "XDR", "XDR 平台",
        "数据安全", "数据防泄漏", "防泄漏", "数据脱敏",
        "防病毒", "终端安全", "主机安全", "上网行为",
        "VPN", "网闸", "蜜罐", "沙箱", "网络隔离",
        "抗DDoS", "抗DDOS", "抗拒绝服务",
        "网安设备",      # 表格"覆盖范围"
        # Phase 16 补充 — 完整网安术语
        "API安全",       # API 防护
        "API 安全",      # 带空格变体
        "API网关",       # API 网关产品
        "API 网关",      # 带空格变体
        "UEBA",          # 用户行为分析
        "UEBA 用户行为",  # 带空格变体
        "NDR",           # 网络检测响应
        "NTA",           # 网络流量分析
        "SOAR",          # 安全编排自动化响应
        "CASB",          # 云访问安全代理
        "SD-WAN",        # 安全广域网络
        "主机防护",      # 主机安全(产品形态)
        "运维审计",      # 运维堡垒机/4A
        "应用安全",      # AppSec/WAF 体系
    ],
    # ===== 运维/平台线（11 + 8 补充 = 19 词） =====
    # Phase 16 补充: 表格"覆盖范围"的维保/运营中心/驻场运维/整改,
    # 网安新型运营形态 MSSP/安全托管/安全编排。
    "运维/平台线": [
        # Phase 9/14 原有
        "安全运营", "安全运维", "安全驻场", "安全运维服务",
        "SOC", "SOC 平台",       # 带空格变体
        "安全管理平台", "SIEM", "SIEM 平台",
        "安全加固", "安全合规", "安全整改", "安全维保",
        "安全监控", "日志审计平台", "安全日志审计",
        # Phase 16 补充 — 表格"覆盖范围" + 完整网安术语
        "维保",          # 表格"覆盖范围"
        "运营中心",      # 表格"覆盖范围"
        "驻场运维",      # 表格"覆盖范围"
        "整改",          # 表格"覆盖范围"
        "MSSP",          # 托管安全服务
        "安全托管",      # MSSP 中文
        "托管检测",      # MDR
        "MDR",           # 托管检测响应
        "MDR 服务",      # 带空格变体
    ],
    # ===== 行业搜索线（17 + 5 补充 = 22 词） =====
    # Phase 16 补充: 车联网/无人机/卫星/量子/生成式 AI。
    "行业搜索线": [
        # Phase 9/14 原有
        "工控安全", "电力监控安全", "物联网安全", "云安全",
        "数据分类分级", "主机安全", "终端安全",
        "医疗数据安全", "教育行业安全", "交通物流安全",
        "AI安全", "大模型安全", "算法安全", "AI风控",
        "数据安全治理", "隐私计算", "联邦学习",
        # Phase 16 补充 — 新型行业网安
        "车联网安全",   # V2X/智能网联汽车
        "卫星互联网安全",  # 卫星通信安全
        "量子安全",     # 抗量子密码
        "生成式AI安全", # AIGC/ChatGPT 安全
        "智能网联汽车",  # 智能汽车
    ],
    # ===== 跨线通用（新增分类 — 网安/密码/数据合规顶层词） =====
    # Phase 16 补充: 关基保护/个保/商用密码/信创 等顶层法规类术语。
    "通用合规线": [
        "网络与信息安全",  # 表格标题
        "关基保护",         # 关键信息基础设施保护
        "关键信息基础设施",  # 同上长尾
        "个人信息保护",     # PIPL
        "个保",             # PIPL 缩写
        "数据出境",         # 数据安全法
        "商用密码",         # 国密
        "国密",             # 同上
        "信创",             # 国产化
        "数据安全法",       # 法规
        "网络安全法",       # 法规
    ],
}

# 采购语境词（AND）— 不强制要求，但用于加分
# Phase 16 补充: 合同/续约/框架协议/年度 等新合同语境。
PROCUREMENT_KEYWORDS: list[str] = [
    # Phase 9 原有
    "采购", "招标", "中标", "征集", "比选", "磋商", "竞价",
    "询价", "项目", "服务", "设备", "平台", "系统",
    # Phase 16 补充 — 合同/续约/框架
    "合同", "续约", "框架", "框架协议", "年度", "运维", "驻场", "整改",
]

# 行业语境词 — Phase 16 表格提到的"金融/政府/医疗/教育/能源/电信/交通"
# 用于 AND 配合核心关键词。当标题不含"采购"但含"医疗"+"等保"也算网安标讯。
INDUSTRY_KEYWORDS: list[str] = [
    "金融", "银行", "证券", "保险", "政府", "机关", "事业单位",
    "医疗", "医院", "卫生", "教育", "高校", "学校", "院校",
    "能源", "电力", "电网", "石化", "电信", "运营商", "通信",
    "交通", "物流", "轨交", "铁路",
]

# 非网安标讯黑名单词 — Phase 18 截图中误录的非网安标讯
# 任何标题/正文包含这些词都视为非网安,直接 Reject。
# 设计动机: 标讯四线关键词中"维保"+"运营"+"系统"太宽,容易让
#   消防/空调/饮水/办公/车辆/印刷 等无关维保项目混入。
NON_SECURITY_BLACKLIST: list[str] = [
    # ===== 消防/安全 (非网络安全) =====
    # 注意: 不要用"防火" / "防火墙" 这种易误伤的子串
    "消防", "灭火", "火灾", "消防车", "消防维保", "消防救援",
    "消防设施", "消防设备", "消防工程", "消防器材", "消防检测",
    "阻燃", "烟感", "喷淋", "应急照明",
    # ===== 后勤/办公 =====
    # 注意: 不要用"电脑" / "主机" / "笔记本" 等子串,会误伤"网络安全"主题
    "饮水机", "饮用水", "开水器", "净化水",
    "空调", "中央空调", "多联机", "VRV", "冷暖", "暖通", "冷源",
    "电梯", "扶梯", "升降梯",
    "印刷", "硒鼓", "墨盒", "复印纸", "复印机",
    "办公家具", "办公用品", "办公耗材", "办公设备", "文具",
    # ===== 车辆/通勤 =====
    "车辆维保", "汽车维保", "车队", "公务用车", "班车", "通勤",
    "租车", "租赁车", "救援车", "救护车", "工程车", "扫地车",
    "车辆保养", "保养服务", "检测线", "验车",
    # ===== 餐饮/物业 =====
    "食堂", "餐饮", "厨具", "灶具", "餐具", "食材", "配送餐",
    "物业", "保洁", "保安", "绿化", "园林", "花卉", "绿植",
    "保洁服务", "物业管理", "物业服务",
    # ===== 通用后勤 =====
    "工作服", "制服", "服装", "劳保用品",
    "基建工程", "土建", "装修", "装饰", "改造工程", "建筑",
    "售后", "售后服务", "客服", "呼叫中心", "话务",
    # ===== 业务类非网安 =====
    "制卡机", "即时制卡", "POS机", "刷卡机",
    "电视机", "显示屏采购", "广告机", "会议系统", "音响",
    "医疗设备", "医疗器械", "检验设备",
    "教学设备", "实验室", "实训",
]


def _build_keyword_set() -> set[str]:
    """汇总所有四线关键词到 1 个 set，供 O(1) 查找。"""
    out: set[str] = set()
    for words in SECURITY_KEYWORDS.values():
        out.update(words)
    return out


# 全量关键词（用于 _parse_html 过滤）
SECURITY_KEYWORD_SET: set[str] = _build_keyword_set()

# 编译正则（中文无空格分词，每条关键词直接 substring 匹配）
_SECURITY_RE = re.compile(
    "|".join(re.escape(kw) for kw in SECURITY_KEYWORD_SET)
)

# 采购语境词 — 用于 AND 配合核心关键词
_PROCUREMENT_RE_LIST: list[str] = list(PROCUREMENT_KEYWORDS)

# 行业关键词 — Phase 16 表格里的"金融/政府/医疗/教育/能源/电信/交通"
# 当标题没有"采购"字样但有"医疗"/"金融"等行业词时也算合法
_INDUSTRY_RE_LIST: list[str] = list(INDUSTRY_KEYWORDS)


def is_security_bid(text: str) -> bool:
    """判断文本是否包含网络安全/AI安全相关关键词。

    规则 (Phase 16 表格四线 AND/OR 体系 + Phase 18 黑名单 Reject):
    - **黑名单前置** (Phase 18): 标题/正文含任何 NON_SECURITY_BLACKLIST
      词 → 直接 False。避免消防/空调/饮水/办公/车辆/印刷 等非网安标讯
      因为"维保"+"系统" 等宽泛词被误判。
    - **宽松层** (向后兼容): 核心关键词命中 → 保留
      - 避免 "SOC 安全运营中心" 这种专业网安术语短句被漏
    - **严格层** (Phase 16): 核心 + 采购/行业语境命中 → 保留
      - 避免 "采购 WAF 系统" 这种通用 IT 采购被误判为网安标讯

    实际判定: 黑名单全否决,否则核心命中即 True。
    """
    if not text:
        return False
    # Phase 18: 黑名单前置 Reject
    if any(kw in text for kw in NON_SECURITY_BLACKLIST):
        return False
    # 宽松层: 核心关键词命中
    if _SECURITY_RE.search(text):
        return True
    return False


class BidCollector(BaseCollector):
    """采集招标资讯热点数据。Phase 9 改造：聚焦网络安全/AI安全。

    Phase 19 改造: 集成 v1.6.3 搜索引擎思路。
    - renderer="search" 的源走 DDG HTML 搜索（绕开 anti-bot）
    - 提取的 URL 是真实源 URL,不是 DDG 跳转 URL
    - 走完正常 is_security_bid 过滤 + 质量门禁
    """

    category = Category.BID
    sources = BID_SOURCES
    timeout = 25
    max_items = 40
    min_items_threshold = 5

    def _is_relevant(self, title: str, summary: str = "") -> bool:
        """判断一条标讯是否网络安全/AI安全相关。

        规则：
        - title 或 summary 任一命中四线关键词集合 → 保留
        - 否则过滤掉（避免大量无关采购信息）
        """
        return is_security_bid(title) or is_security_bid(summary)

    async def _fetch_search_source(
        self, source: dict
    ) -> tuple[list[HotspotItem], Any]:
        """renderer="search" 源路径: 走 DDG HTML 搜索 (Phase 19)。

        Returns: ``(items, SourceResult)`` 形态同 :meth:`fetch_source`。
        失败返回 ``([], SourceResult(error))``,不向上抛异常。
        """
        from datetime import datetime, timezone as _tz
        from backend.domain.collection import SourceResult
        from backend.collectors.bid_search import search_one_source

        start = datetime.now(_tz.utc)
        source_name = source.get("name", "unknown")
        try:
            raw_items = await search_one_source(source, max_results=self.max_items)
        except Exception as e:
            duration = int(
                (datetime.now(_tz.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"search_source {source_name!r} failed: "
                f"{type(e).__name__}: {str(e)[:80]}"
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source["url"],
                item_count=0,
                error_msg=f"search_error: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        # 复用基类 _build_items
        items = self._build_items(raw_items, source)
        duration = int(
            (datetime.now(_tz.utc) - start).total_seconds() * 1000
        )
        return items, SourceResult(
            source_name=source_name,
            source_url=source["url"],
            item_count=len(items),
            duration_ms=duration,
        )

    def _parse_html(self, html: str, source: dict) -> list[dict]:
        """解析招标页面 HTML，过滤无关采购信息。

        Phase 9 增强：
        1. 优先从招标页面常见结构中提取 title + url
        2. 关键词过滤：只保留网络安全/AI安全相关条目
        """
        # 调父类解析（默认 <a href> 锚点提取）
        raw_items = super()._parse_html(html, source)
        # 关键词过滤
        out: list[dict] = []
        seen: set[str] = set()
        for it in raw_items:
            title = it.get("title", "") or ""
            summary = it.get("summary", "") or ""
            if not self._is_relevant(title, summary):
                continue
            url = it.get("url", "") or ""
            if url in seen:
                continue
            seen.add(url)
            out.append(it)
            if len(out) >= self.max_items:
                break
        return out

    async def fetch_source(self, source: dict):
        """Phase 19: 按 ``renderer`` 字段路由。

        - ``renderer="search"`` → :meth:`_fetch_search_source` 走 DDG HTML 搜索
        - 其他 → 走父类 ``BaseCollector.fetch_source`` 走 crawl4ai / aiohttp
        """
        if source.get("renderer") == "search":
            return await self._fetch_search_source(source)
        return await super().fetch_source(source)


__all__ = [
    "BidCollector",
    "BID_SOURCES",
    "SECURITY_KEYWORDS",
    "SECURITY_KEYWORD_SET",
    "PROCUREMENT_KEYWORDS",
    "is_security_bid",
]
