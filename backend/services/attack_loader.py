"""S4-3 ATT&CK data loader + CWE→Technique lookup service.

职责
----
- `load_attack_data()`: 启动时调用一次, 若表空则从 `data/stix/` 灌入
  - `attack_techniques`: Top-200 technique 子集
  - `attack_cwe_map`: CWE → Technique 静态映射 (~150 条)
- `cwe_to_techniques(cwe_ids)`: 给定 CWE 列表, 返回聚合 technique 计数

设计
----
- 幂等: 仅当 COUNT(*) == 0 时 INSERT, 重复调用不报错
- 无网络依赖: 数据静态嵌入 `data/stix/`
- 无外部 cache: 直连 SQLite, 小数据集无需 Redis
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.logging_config import logger
from backend.repository.db import get_connection

# data/stix/ 相对于项目根目录
_STIX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "stix"
_TECHNIQUES_FILE = _STIX_DIR / "attack-techniques.json"
_CWE_MAP_FILE = _STIX_DIR / "cwe-to-technique.json"


def load_attack_data() -> dict:
    """Idempotent loader: 若表空则从 data/stix/ 灌入 attack_techniques + attack_cwe_map。

    Returns:
        {"techniques": int, "cwe_mappings": int}
    """
    conn = get_connection()
    result = {"techniques": 0, "cwe_mappings": 0}

    try:
        # 1. attack_techniques
        count = conn.execute("SELECT COUNT(*) AS n FROM attack_techniques").fetchone()["n"]
        if count == 0 and _TECHNIQUES_FILE.exists():
            techniques = json.loads(_TECHNIQUES_FILE.read_text(encoding="utf-8"))
            rows = [
                (t["id"], t["name"], t["tactic_id"], t.get("description", ""))
                for t in techniques
            ]
            conn.executemany(
                "INSERT INTO attack_techniques (id, name, tactic, description) VALUES (?, ?, ?, ?)",
                rows,
            )
            result["techniques"] = len(rows)
            logger.info("attack_loader: loaded %d techniques", len(rows))

        # 2. attack_cwe_map
        count = conn.execute("SELECT COUNT(*) AS n FROM attack_cwe_map").fetchone()["n"]
        if count == 0 and _CWE_MAP_FILE.exists():
            mappings = json.loads(_CWE_MAP_FILE.read_text(encoding="utf-8"))
            rows = [(m["cwe_id"], m["technique_id"]) for m in mappings]
            conn.executemany(
                "INSERT INTO attack_cwe_map (cwe_id, technique_id) VALUES (?, ?)",
                rows,
            )
            result["cwe_mappings"] = len(rows)
            logger.info("attack_loader: loaded %d cwe mappings", len(rows))
    except Exception as exc:
        logger.error("attack_loader failed: %s", exc)
    finally:
        conn.commit()

    return result


def cwe_to_techniques(cwe_ids: list[str]) -> dict[str, int]:
    """给定 CWE 列表, 返回 technique_id → count 聚合。

    Args:
        cwe_ids: 如 ["CWE-79", "CWE-89"]

    Returns:
        {"T1059": 3, "T1190": 1, ...}
    """
    if not cwe_ids:
        return {}

    conn = get_connection()
    placeholders = ",".join("?" for _ in cwe_ids)
    rows = conn.execute(
        f"""
        SELECT technique_id, COUNT(*) AS cnt
        FROM attack_cwe_map
        WHERE cwe_id IN ({placeholders})
        GROUP BY technique_id
        """,
        list(cwe_ids),
    ).fetchall()

    return {row["technique_id"]: row["cnt"] for row in rows}


__all__ = ["cwe_to_techniques", "load_attack_data"]
