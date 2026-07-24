"""v1.7 Phase 5 — extract_tags skill.

从内容中提取标签 (关键词匹配, 不调用 LLM).
可被外部 Agent 替换为更复杂实现 (LLM 提取 / NER).
"""
from __future__ import annotations

import re
from typing import Optional

from agent.client import HotspotClient
from agent.executor import register_skill


# 简单关键词字典 (可由 Agent 通过 /api/tags/rules 远程更新)
DEFAULT_KEYWORDS = {
    "fastapi": ["fastapi", "FastAPI"],
    "python": ["python", "Python", "py3"],
    "llm": ["llm", "大模型", "大语言模型", "语言模型"],
    "rag": ["rag", "RAG", "检索增强"],
    "vulnerability": ["vulnerability", "vuln", "cve", "CVE", "漏洞"],
    "ransomware": ["ransomware", "勒索软件"],
    "ai-security": ["prompt injection", "提示注入", "jailbreak", "越狱"],
    "github": ["github", "GitHub", "gh-"],
}


@register_skill("extract_tags")
def extract_tags_skill(task: dict, client: HotspotClient) -> dict:
    """从内容中提取标签 (纯规则, 无 LLM 调用).

    实际使用建议: 外部 Agent 替换为基于 LLM 的实现.
    本 skill 作为 fallback, 保证在无 LLM 环境下也能工作.
    """
    text = task.get("params", {}).get("text", "")
    if not text:
        return {"tags": [], "note": "no text provided"}
    text_lower = text.lower()
    matched = []
    for tag_id, keywords in DEFAULT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(tag_id)
                break
    return {"tags": matched, "count": len(matched)}
