"""S4-3 CVE → ATT&CK technique 映射服务。

职责
----
- `cves_to_attack_techniques(cve_ids)` → 给定 CVE 编号列表, 返回 technique 计数
- 链路: CVE metadata.cwe_ids → attack_cwe_map → attack_techniques → 聚合计数

依赖
----
- `attack_loader.load_attack_data()` 启动时已灌入 (幂等)
- `security_entities.metadata` 需含 `cwe_ids` 列表 (由 cve_knowledge_sync 写入)
"""
from __future__ import annotations

import json
from typing import Any

from backend.repository.db import get_connection
from backend.services.attack_loader import cwe_to_techniques


def cves_to_attack_techniques(cve_ids: list[str]) -> dict[str, Any]:
    """给定 CVE 列表, 返回 ATT&CK technique 聚合结果。

    Args:
        cve_ids: 如 ["CVE-2024-12345", "CVE-2024-67890"]

    Returns:
        {
            "techniques": [
                {"technique_id": "T1059", "name": "...", "tactic": "...", "count": 3},
                ...
            ],
            "total_cves": 2,
            "matched_cves": 1
        }
    """
    if not cve_ids:
        return {"techniques": [], "total_cves": 0, "matched_cves": 0}

    conn = get_connection()
    placeholders = ",".join("?" for _ in cve_ids)

    rows = conn.execute(
        f"""
        SELECT id, metadata
        FROM security_entities
        WHERE entity_type = 'cve'
          AND id IN ({placeholders})
        """,
        list(cve_ids),
    ).fetchall()

    # 收集所有 CWE IDs
    all_cwe_ids: list[str] = []
    matched_cves = 0
    for row in rows:
        metadata_raw = row["metadata"]
        if not metadata_raw:
            continue
        try:
            meta = (
                json.loads(metadata_raw)
                if isinstance(metadata_raw, str)
                else metadata_raw
            )
            cwes = meta.get("cwe_ids", [])
            if cwes:
                matched_cves += 1
            all_cwe_ids.extend(cwes)
        except (TypeError, ValueError):
            continue

    if not all_cwe_ids:
        return {"techniques": [], "total_cves": len(cve_ids), "matched_cves": 0}

    # CWE → technique 聚合
    technique_counts = cwe_to_techniques(all_cwe_ids)

    # 补 technique 名称/tactic
    technique_rows = conn.execute(
        """
        SELECT id, name, tactic
        FROM attack_techniques
        WHERE id IN ({placeholders})
        """.format(placeholders=",".join("?" for _ in technique_counts)),
        list(technique_counts.keys()),
    ).fetchall()

    technique_info = {row["id"]: row for row in technique_rows}

    techniques = []
    for tid, count in sorted(technique_counts.items(), key=lambda x: x[1], reverse=True):
        info = technique_info.get(tid, {})
        techniques.append({
            "technique_id": tid,
            "name": info["name"] if "name" in info else tid,
            "tactic": info["tactic"] if "tactic" in info else "",
            "count": count,
        })

    return {
        "techniques": techniques,
        "total_cves": len(cve_ids),
        "matched_cves": matched_cves,
    }


__all__ = ["cves_to_attack_techniques"]
