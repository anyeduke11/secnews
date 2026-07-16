"""Phase 1j Task 10.5: 18 个空模板概念补定义."""

from __future__ import annotations

from pathlib import Path

CONCEPTS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "concepts"

# 每个概念的定义 + 关键要点
DEFINITIONS = {
    "industry-news": {
        "title": "行业资讯",
        "definition": "跟踪报道特定行业动态、市场趋势、政策变化和企业新闻的资讯内容。在知识管理中作为 L1 资料层，为后续深度分析和学习计划提供原始素材。",
        "points": [
            "按 domain 分类聚合，便于按领域检索历史动态",
            "需配合 RecencyGate 门禁，区分本周资讯与历史归档",
            "是知识金字塔 L1 层的主要来源之一（Cubox/SecNews/书签）",
        ],
    },
    "knowledge-management": {
        "title": "知识管理",
        "definition": "系统化地收集、组织、存储、检索和分享知识的方法论与实践。本项目采用 LLM-Wiki 架构，以 Markdown 为真相源，SQLite 为镜像，实现人机双向可读。",
        "points": [
            "L1-L4 金字塔模型：items → concepts → learning → content",
            "Markdown 为真相源，SQLite 为查询镜像，watchdog 双向同步",
            "联邦架构支持跨 wiki 引用（hotspot ↔ local）",
        ],
    },
    "learning-methods": {
        "title": "学习方法",
        "definition": "提高知识吸收效率的策略与技巧，包括间隔重复、主动回忆、费曼技巧等。在知识管理系统中用于制定学习计划、追踪掌握进度、评估学习效果。",
        "points": [
            "知识掌握度 0-100 量化，配合 half-open-book 测试评估",
            "学习计划按周组织，支持 goals + tasks 清单结构",
            "雷达图可视化多维度能力分布",
        ],
    },
    "investment": {
        "title": "投资",
        "definition": "将资金投入资产以期获得回报的经济活动。涵盖私募、证券、基金等多种形式，需关注市场动态、政策变化和风险管理。",
        "points": [
            "私募自购是机构对自身投研能力的信心信号",
            "投资决策需结合宏观经济周期与行业基本面",
            "风险管理：分散投资 + 止损纪律 + 仓位控制",
        ],
    },
    "financial-regulation": {
        "title": "金融监管",
        "definition": "政府及监管机构对金融市场、金融机构和金融行为实施的监督与管理。在中国包括央行、银保监会、证监会的多层次监管体系。",
        "points": [
            "银行 App 合规通报是常见监管手段",
            "金融科技监管沙盒为创新提供试错空间",
            "反洗钱、投资者适当性是核心监管要求",
        ],
    },
    "banking": {
        "title": "银行业务",
        "definition": "银行机构提供的存贷款、支付结算、财富管理等金融服务。数字化转型推动银行积极采用 AI、大模型技术提升服务效率和风控能力。",
        "points": [
            "大模型应用：客服、风控、合规、运营四大场景",
            "Token 消耗量是衡量 AI 应用深度的关键指标",
            "App 安全合规是监管重点关注领域",
        ],
    },
    "national-standards": {
        "title": "国家标准",
        "definition": "由国家标准化管理委员会发布的强制性或推荐性技术标准。在信息安全领域包括 GB/T 系列标准，是合规建设的基础依据。",
        "points": [
            "GB/T 22239（等保2.0）是安全建设核心标准",
            "标准更新需持续跟踪并及时调整合规策略",
            "实践指南（TC260）提供具体落地指引",
        ],
    },
    "work-report": {
        "title": "工作汇报",
        "definition": "定期向上级或团队展示工作进展、成果和问题的正式文档。好的工作汇报需结构清晰、数据支撑、重点突出。",
        "points": [
            "结构：目标 → 进展 → 问题 → 下一步计划",
            "量化成果（KPI/OKR）优于定性描述",
            "周报/月报/季报的颗粒度递进",
        ],
    },
    "securities": {
        "title": "证券",
        "definition": "代表财产权利的金融工具，包括股票、债券、基金等。证券市场是直接融资的重要渠道，受证监会严格监管。",
        "points": [
            "信息披露是证券市场公平交易的基础",
            "投资者适当性管理保护普通投资者",
            "注册制改革重塑 A 股上市生态",
        ],
    },
    "standards": {
        "title": "标准",
        "definition": "为在一定范围内获得最佳秩序，经协商一致制定并经公认机构批准的规范性文件。技术标准促进行业互操作性和质量提升。",
        "points": [
            "国际标准（ISO/IEC）→ 国家标准（GB）→ 行业标准的层级",
            "开源标准推动生态发展（如 OAuth、OpenID）",
            "安全标准是等保、密评的依据",
        ],
    },
    "openai": {
        "title": "OpenAI",
        "definition": "美国 AI 研究公司，开发了 GPT 系列大语言模型、DALL-E 图像生成模型和 ChatGPT 产品。是生成式 AI 领域的领军企业。",
        "points": [
            "GPT 系列模型推动 LLM 规模化应用",
            "API 经济的先行者，催生大量 AI 应用",
            "商业化路径：订阅 + API + 企业版",
        ],
    },
    "technical-principles": {
        "title": "技术原理",
        "definition": "技术方案背后的科学基础和工程逻辑。理解技术原理有助于评估方案可行性、排查问题和做技术选型。",
        "points": [
            "Transformer 架构是现代 LLM 的基础",
            "RAG vs Fine-tuning 的适用场景不同",
            "向量检索 + 重排序提升 RAG 准确率",
        ],
    },
    "ciso": {
        "title": "首席信息安全官 (CISO)",
        "definition": "企业中负责信息安全和数据保护的最高管理者。向 CIO 或 CEO 汇报，统筹安全战略、合规建设、 incident response 和安全团队管理。",
        "points": [
            "平衡安全投入与业务发展的资源分配",
            "安全治理：制度 + 流程 + 技术 + 人员",
            "需向董事会定期汇报安全态势",
        ],
    },
    "deepseek": {
        "title": "DeepSeek",
        "definition": "中国 AI 公司深度求索，以开源大模型著称。DeepSeek-V3/R1 系列在推理能力上表现突出，且训练成本远低于同级别模型。",
        "points": [
            "MoE 架构实现高效推理",
            "R1 推理模型对标 OpenAI o1",
            "开源策略推动国产 LLM 生态发展",
        ],
    },
    "claude": {
        "title": "Claude",
        "definition": "Anthropic 公司开发的大语言模型系列，以长上下文、工具调用和安全性著称。Claude Code 是其命令行编程助手产品。",
        "points": [
            "200K+ 上下文窗口支持长文档处理",
            "Constitutional AI 提升安全对齐",
            "Claude Code 推动 AI 编程工作流革新",
        ],
    },
    "ai-design": {
        "title": "AI 设计",
        "definition": "将 AI 能力融入产品设计和用户体验的方法论。包括 AI 原生界面设计、人机协作交互模式、AI 透明度与可控性设计等。",
        "points": [
            "AI 原生 UI：从 GUI 到 CUI（对话界面）的演进",
            "人机协作：AI 建议 + 人类决策的混合模式",
            "可解释性是 AI 设计的信任基础",
        ],
    },
    "tutorials": {
        "title": "教程",
        "definition": "系统性教授某项技能或知识的教育内容。好的教程需循序渐进、配套实践、覆盖常见问题和最佳实践。",
        "points": [
            "结构：概念 → 示例 → 练习 → 拓展",
            "实战项目驱动比纯理论更有效",
            "更新频率需匹配技术演进速度",
        ],
    },
    "fintech": {
        "title": "金融科技 (FinTech)",
        "definition": "用技术手段创新金融服务的领域，包括支付、借贷、保险科技、监管科技等。AI 和区块链是当前核心驱动力。",
        "points": [
            "AI 驱动智能风控和个性化服务",
            "监管科技（RegTech）用技术解决合规问题",
            "开放银行推动 API 经济在金融落地",
        ],
    },
}


def update_concept_md(slug: str, data: dict) -> bool:
    """Update concept .md body with definition and key points."""
    path = CONCEPTS_DIR / f"{slug}.md"
    if not path.exists():
        print(f"  WARN: {slug}.md not found")
        return False

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False

    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    frontmatter = parts[1]
    # Keep frontmatter, replace body
    points_md = "\n".join(f"{i+1}. {p}" for i, p in enumerate(data["points"]))
    new_body = f"""

# {data['title']}

## 定义

{data['definition']}

## 关键要点

{points_md}

## 参考条目

（待补充）
"""

    path.write_text(f"---{frontmatter}---{new_body}", encoding="utf-8")
    print(f"  ✓ {slug}: {data['title']}")
    return True


def main() -> None:
    print("=" * 60)
    print("Phase 1j Task 10.5: 18 个空模板概念补定义")
    print("=" * 60)

    count = 0
    for slug, data in DEFINITIONS.items():
        if update_concept_md(slug, data):
            count += 1

    print(f"\nUpdated: {count} concepts")

    # Verify: no more "待补充——自动创建"
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", "待补充——自动创建", str(CONCEPTS_DIR)],
        capture_output=True, text=True,
    )
    remaining = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    print(f"Remaining empty templates: {remaining}")

    # Sync to SQLite
    from backend.services.knowledge_sync import full_sync_concepts_to_db
    synced = full_sync_concepts_to_db()
    print(f"Synced {synced} concepts to SQLite")

    print(f"\n{'=' * 60}")
    print(f"Task 10.5 complete: {count} concepts filled")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
