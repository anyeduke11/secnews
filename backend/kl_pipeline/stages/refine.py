"""kl:refine stage — light AI refinement.

Reads a raw wiki item, calls LLM to generate a structured summary,
extracts tags, and writes the refined frontmatter back.
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger


def run_refine(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Refine a raw item: generate summary + tags via LLM."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    body = doc.get("body", "")

    # Skip if already refined.
    if fm.get("kl_stage") not in (None, "kl:raw"):
        logger.info(f"refine: skipping {item_id} (stage={fm.get('kl_stage')})")
        return

    # If no LLM client, do a lightweight local refine (title-only).
    if llm_client is None:
        fm["kl_stage"] = "kl:refine"
        if not fm.get("summary"):
            # Fallback: first 200 chars of body as summary.
            fm["summary"] = (body[:200] + "...") if len(body) > 200 else body
        wiki_fs.write_item(item_id, {"fm": fm, "body": body})
        return

    # LLM-based refinement.
    prompt = (
        "Analyze the following security article and produce a JSON object with:\n"
        '1. "summary": a 2-3 sentence executive summary\n'
        '2. "tags": a list of 3-7 topical tags (e.g., "ransomware", "CVE-2026-1234")\n'
        '3. "severity": one of "critical", "high", "medium", "low", "info"\n\n'
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
    except Exception as exc:
        logger.warning(f"refine LLM failed for {item_id}: {exc}, using fallback")
        if not fm.get("summary"):
            fm["summary"] = (body[:200] + "...") if len(body) > 200 else body

    fm["kl_stage"] = "kl:refine"
    wiki_fs.write_item(item_id, {"fm": fm, "body": body})
