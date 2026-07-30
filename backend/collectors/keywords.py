"""Module-level category keywords extracted from base.py.

- ``_CAT_KEYWORDS`` — per-category keyword whitelists for relevance filtering
- ``_is_title_relevant_to_category(title, category_value)`` — relevance check

Phase 25+: 防止综合媒体把无关内容误归类到某个分类。
没列在关键词白名单的 category (security / bid / github) 默认放行。
"""
from __future__ import annotations

# Phase 25: 分类相关度关键词白名单 (module-level 常量)
# 防止综合媒体 (投资界/新浪/36kr) 把无关内容 (旅行社/演唱会/餐饮) 误归类
# 没命中关键词的标题直接 drop, 避免噪声入库
#
# 没列的 category (security / bid / github) 默认放行——它们用领域专用
# 关键词过滤 (security_collector / bid_collector 内部已处理),
# 不需要通用白名单。
_CAT_KEYWORDS: dict[str, list[str]] = {
    "ai": [
        # AI / 大模型
        "AI", "GPT", "LLM", "大模型", "人工智能", "机器学习", "深度学习",
        "神经网络", "AGI", "AIGC", "扩散模型", "推理", "智能体", "Agent",
        "机器人", "具身", "世界模型", "WAIC", "Transformer", "LLama",
        "Claude", "Gemini", "Qwen", "DeepSeek", "豆包", "文心", "通义",
        "Sora", "HBM", "多模态", "RAG", "MoE", "训练",
    ],
    "finance": [
        # 金融 / 投资
        "经济", "股市", "A股", "港股", "美股", "上证", "深证", "创业板",
        "纳斯达克", "标普", "道指", "期货", "外汇", "汇率", "美元", "人民币",
        "黄金", "原油", "大宗", "央行", "美联储", "加息", "降息", "利率",
        "通胀", "GDP", "PMI", "非农", "财报", "营收", "利润", "市值",
        "上市公司", "IPO", "并购", "重组", "证券", "基金", "ETF",
        "宁德", "比亚迪", "苹果", "微软", "英伟达", "台积电", "三星",
        "LG", "SK", "现代", "丰田", "大众", "Meta", "Google",
        "阿里", "腾讯", "字节", "百度", "拼多多", "美团", "京东",
        "高盛", "摩根", "巴菲特", "木头姐", "ARK", "对冲基金",
    ],
    "startup": [
        # 创业 / 融资 / 公司动态
        "融资", "天使轮", "种子轮", "Pre-A", "A轮", "B轮", "C轮", "D轮",
        "Pre-IPO", "估值", "领投", "跟投", "投资人", "创投", "VC",
        "PE", "FA", "路演", "创投号", "新青年", "融资轮", "数千万",
        "数亿", "亿元", "万元", "美元", "完成", "获投", "完成融资",
        "创业", "创始人", "CEO", "90后", "00后", "85后", "95后",
        "独角兽", "上市公司", "并购", "战略投资", "红杉", "IDG",
        "经纬", "源码", "真格", "启明", "DCM", "GGV", "五源",
        "高瓴", "弘毅", "鼎晖", "复星", "软银", "愿景", "老虎",
        "创业公司", "初创", "联合创始人", "孵化", "加速器",
        "YC", "Y Combinator",
    ],
    "tech": [
        # IT / 科技 / 数码
        "科技", "数码", "手机", "iPhone", "Android", "iOS", "HarmonyOS",
        "鸿蒙", "小米", "华为", "OPPO", "vivo", "荣耀", "三星", "苹果",
        "Mac", "MacBook", "iPad", "iMac", "AirPods", "Apple Watch",
        "Windows", "Linux", "Ubuntu", "Chromebook", "Surface",
        "Intel", "AMD", "高通", "联发科", "骁龙", "天玑", "麒麟",
        "显卡", "GPU", "RTX", "处理器", "芯片", "主板", "内存",
        "SSD", "硬盘", "显示器", "笔记本", "台式机", "服务器",
        "Docker", "Kubernetes", "K8s", "开源", "GitHub", "代码",
        "程序员", "开发者", "开发", "前端", "后端", "全栈", "DevOps",
        "数据库", "SQL", "NoSQL", "Redis", "MongoDB", "PostgreSQL",
        "Python", "Java", "Go", "Rust", "C++", "TypeScript", "JavaScript",
        "Solidot", "IT之家", "ithome", "稀土", "掘金", "酷安",
        "发布会", "系统更新", "版本", "升级", "推送",
        "上架", "下架", "App Store", "Play Store", "应用商店",
        "5G", "6G", "Wi-Fi", "蓝牙", "NFC", "USB-C", "Type-C",
        "折叠屏", "全面屏", "曲面屏", "OLED", "LCD", "Mini LED",
        "相机", "摄像", "像素", "光圈", "长焦", "广角", "夜景",
        "AI", "大模型", "LLM", "GPT", "Claude", "Gemini", "DeepSeek",
        "机器人", "无人机", "智能", "自动化", "算法",
    ],
    "ai_security": [
        # AI 安全 / 大模型安全 / 对抗 ML
        "AI安全", "人工智能安全", "大模型安全", "LLM安全",
        "prompt injection", "jailbreak", "AI safety",
        "adversarial", "model poisoning", "AI red team",
        "AI incident", "OWASP LLM", "AI alignment",
        "AI regulation", "AI governance", "AI threat",
        "AI malware", "AI worm", "恶意AI",
        "对抗攻击", "对抗样本", "模型投毒",
        "数据投毒", "逃逸攻击", "AI 漏洞",
        "LLM vulnerability", "AI attack", "AI defense",
        "robustness", "AI 监管", "AI 治理",
        "AI 风险", "AI 安全", "AI security",
    ],
}


def _is_title_relevant_to_category(title: str, category_value: str) -> bool:
    """Phase 25: 分类相关度过滤 (module-level helper)。

    检查 ``title`` 是否命中 ``category_value`` 对应的关键词白名单。
    没在白名单的 category (security/bid/github/ai_security) 一律放行。
    """
    keywords = _CAT_KEYWORDS.get(category_value)
    if not keywords:
        return True
    return any(kw in title for kw in keywords)


__all__ = ["_CAT_KEYWORDS", "_is_title_relevant_to_category"]