"""kl:refine stage — light AI refinement + quality gates (S2-1).

Reads a raw wiki item, calls LLM to generate a structured summary,
extracts tags, runs quality gate checks, and writes the refined
frontmatter back.
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.wiki_fs.contract import get_lifecycle


def run_refine(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Refine a raw item: quality gates + summary + tags via LLM."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    body = doc.get("body", "")

    # Skip if already refined.
    if get_lifecycle(fm) != "kl:raw":
        logger.info(f"refine: skipping {item_id} (stage={get_lifecycle(fm)})")
        return

    # S2-1: quality gates — loose 语义, 不合格打 flag 但不拒绝入库。
    try:
        from backend.services.quality_gate_map import run_refine_gates
        q_flags = run_refine_gates(fm, body)
        if q_flags:
            existing = fm.get("quality_flags", [])
            fm["quality_flags"] = list(set(existing + q_flags))
            logger.info(f"refine: {item_id} quality flags={q_flags}")
    except Exception as exc:
        logger.warning(f"refine: quality gates failed for {item_id}: {exc}")

    # If no LLM client, do a lightweight local refine (title-only).
    if llm_client is None:
        fm["lifecycle"] = "kl:refine"
        if not fm.get("summary"):
            # Fallback: first 200 chars of body as summary.
            fm["summary"] = (body[:200] + "...") if len(body) > 200 else body
        wiki_fs.write_item(item_id, {"fm": fm, "body": body})
        return

    # LLM-based refinement (S1-6: flash 档轻 AI — summary/tags/severity/topic/type).
    prompt = (
        "Analyze the following security article and produce a JSON object with:\n"
        '1. "summary": a 2-3 sentence executive summary\n'
        '2. "tags": a list of 3-7 topical tags (e.g., "ransomware", "CVE-2026-1234")\n'
        '3. "severity": one of "critical", "high", "medium", "low", "info"\n'
        '4. "topic": the primary security topic in 1-2 words '
        '(e.g., "云安全", "漏洞管理", "威胁情报")\n'
        '5. "type": one of "vuln", "incident", "tool", "standard", '
        '"opinion", "news"\n\n'
        f"Title: {fm.get('title', '')}\n"
        f"Content:\n{body[:3000]}"
    )

    try:
        result = llm_client.chat(prompt, response_format="json")
        import json
        parsed = json.loads(result)
        fm["summary"] = parsed.get("summary", "")
        fm["tags"] = parsed.get("tags", fm.get("tags", []))
        fm["severity"] = parsed.get("severity", "info")
        if parsed.get("topic"):
            fm["topic"] = str(parsed["topic"])[:50]
        if parsed.get("type"):
            fm["type"] = str(parsed["type"])
    except Exception as exc:
        logger.warning(f"refine LLM failed for {item_id}: {exc}, using fallback")
        if not fm.get("summary"):
            fm["summary"] = (body[:200] + "...") if len(body) > 200 else body

    fm["lifecycle"] = "kl:refine"
    wiki_fs.write_item(item_id, {"fm": fm, "body": body})
