"""Phase 14 CVE 双向同步服务 — Knowledge item_entities → Security 同步.

职责
----
- sync_cve_to_security(): 从 knowledge_items 的 item_entities 中提取
  entity_type='cve' 的记录, 同步到 security_entities 表
- 双向去重: 同 CVE 编号在 security_entities 中只保留一条记录
- 同步失败时只记录日志, 不阻塞后续同步

设计
----
- 新 CVE: INSERT INTO security_entities (id, entity_type, name, metadata)
  - id: 使用 CVE 编号 (如 'CVE-2024-12345')
  - metadata: {"knowledge_refs": ["item_id_1", "item_id_2"]}
- 已存在 CVE: 检查 metadata 是否包含当前 item_id, 不包含则追加
- 失败记录: 只 log.error, 不抛异常
"""
from __future__ import annotations

import json

from backend.logging_config import logger
from backend.repository.db import get_connection


def sync_cve_to_security(limit: int = 500) -> dict:
    """执行 CVE 同步: item_entities(entity_type='cve') → security_entities.

    Args:
        limit: 最大处理记录数

    Returns:
        {
            "synced": N,        # 新插入的 CVE 数
            "already_exists": N, # 已存在且无需更新的 CVE 数
            "updated": N,        # 已存在但 metadata 已更新的 CVE 数
            "failed": N,         # 处理失败的记录数
            "total_processed": N  # 总处理记录数
        }
    """
    conn = get_connection()
    synced = 0
    already_exists = 0
    updated = 0
    failed = 0

    # 1. 查询所有 entity_type='cve' 的 item_entities 记录
    rows = conn.execute(
        """
        SELECT ie.item_id, ie.entity_name
        FROM item_entities ie
        WHERE ie.entity_type = 'cve'
        ORDER BY ie.entity_name
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    total_processed = len(rows)

    # 2. 按 entity_name (CVE 编号) 分组
    cve_groups: dict[str, list[str]] = {}
    for r in rows:
        name = str(r["entity_name"])
        item_id = str(r["item_id"])
        if name not in cve_groups:
            cve_groups[name] = []
        cve_groups[name].append(item_id)

    for cve_id, item_ids in cve_groups.items():
        try:
            # a. 检查 security_entities 是否已存在
            existing = conn.execute(
                "SELECT id, metadata FROM security_entities WHERE entity_type = 'cve' AND name = ?",
                (cve_id,),
            ).fetchone()

            if existing is None:
                # b. 不存在 → 插入新记录
                metadata = {"knowledge_refs": item_ids}
                conn.execute(
                    """
                    INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at)
                    VALUES (?, 'cve', ?, ?, datetime('now'), datetime('now'))
                    """,
                    (cve_id, cve_id, json.dumps(metadata, ensure_ascii=False)),
                )
                synced += 1
            else:
                # c. 已存在 → 检查 metadata 是否需要更新
                existing_metadata = existing["metadata"]
                existing_refs: list[str] = []
                if existing_metadata:
                    try:
                        parsed = json.loads(existing_metadata) if isinstance(existing_metadata, str) else existing_metadata
                        existing_refs = parsed.get("knowledge_refs", [])
                    except (json.JSONDecodeError, TypeError):
                        existing_refs = []

                # 找出需要追加的 item_ids
                new_refs = [iid for iid in item_ids if iid not in existing_refs]
                if new_refs:
                    all_refs = list(dict.fromkeys(existing_refs + new_refs))  # 去重保序
                    updated_metadata = {"knowledge_refs": all_refs}
                    conn.execute(
                        """
                        UPDATE security_entities
                        SET metadata = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (json.dumps(updated_metadata, ensure_ascii=False), existing["id"]),
                    )
                    updated += 1
                else:
                    already_exists += 1
        except Exception as e:
            logger.error(f"CVE sync failed for {cve_id}: {e}")
            failed += 1
            continue

    report = {
        "synced": synced,
        "already_exists": already_exists,
        "updated": updated,
        "failed": failed,
        "total_processed": total_processed,
    }

    logger.info(
        f"CVE sync: synced={synced} already_exists={already_exists} "
        f"updated={updated} failed={failed} total={total_processed}"
    )
    return report


__all__ = ["sync_cve_to_security"]