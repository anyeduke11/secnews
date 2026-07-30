"""Compliance ontology seed data for security knowledge graph.

Design
------
- Builtin compliance items are loaded into security_entities + security_terms
  at startup or on demand.
- Users can extend via API/admin later.
"""
from __future__ import annotations

from typing import Any

COMPLIANCE_BUILTIN: list[dict[str, Any]] = [
    {
        "id": "等保2.0-一级",
        "name": "网络安全等级保护2.0 第一级",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "网络安全等级保护2.0 第一级要求，适用于小型非关键信息系统。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "等保2.0-二级",
        "name": "网络安全等级保护2.0 第二级",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "网络安全等级保护2.0 第二级要求，适用于一般系统。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "等保2.0-三级",
        "name": "网络安全等级保护2.0 第三级",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "网络安全等级保护2.0 第三级要求，适用于重要系统/关键信息基础设施。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "等保2.0-四级",
        "name": "网络安全等级保护2.0 第四级",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "网络安全等级保护2.0 第四级要求，适用于最高级别关键系统。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "关基条例",
        "name": "关键信息基础设施安全保护条例",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "中华人民共和国关键信息基础设施安全保护条例。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "数安法",
        "name": "中华人民共和国数据安全法",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "中华人民共和国数据安全法，保障数据安全，促进数据开发利用。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "网安法",
        "name": "中华人民共和国网络安全法",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "security",
        "definition": "中华人民共和国网络安全法，维护网络安全和国家安全。",
        "external_ref": "https://www.mos.gov.cn/",
    },
    {
        "id": "个人信息保护法",
        "name": "中华人民共和国个人信息保护法",
        "entity_type": "compliance",
        "term_type": "compliance",
        "category": "privacy",
        "definition": "中华人民共和国个人信息保护法，保护个人信息权益。",
        "external_ref": "https://www.mos.gov.cn/",
    },
]


def iter_builtin() -> list[dict[str, Any]]:
    return list(COMPLIANCE_BUILTIN)


__all__ = ["COMPLIANCE_BUILTIN", "iter_builtin"]
