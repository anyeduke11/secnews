"""S4-3 CVE 分析 API — 热力图 + ATT&CK 映射 + 最近 CVE 清单。

路由:
- GET /api/cve/heatmap?weeks=12
- GET /api/cve/attack-mapping?cve_ids=CVE-1,CVE-2
- GET /api/cve/recent?limit=50   (v0.6.3 P1-3: ATT&CK 前端数据源, 此前
  SecNewsAnalytics 硬编码 cveIds=[] 恒空)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.repository.db import get_connection
from backend.services.attack_loader import load_attack_data
from backend.services.cve_attack_service import cves_to_attack_techniques
from backend.services.cve_heatmap_service import weekly_heatmap

router = APIRouter()


@router.get("/cve/heatmap")
async def get_cve_heatmap(weeks: int = Query(12, ge=1, le=52)) -> dict[str, Any]:
    """CVE 时序热力图 (按周 + 严重程度 5 级)。"""
    return weekly_heatmap(weeks=weeks)


@router.get("/cve/recent")
def get_recent_cves(
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """最近入库的 CVE 实体 id 清单 (security_entities, entity_type='cve')。

    id 形态原样返回 (CVE-xxx 与 cve:CVE-xxx 并存) — /cve/attack-mapping
    按 id 精确 IN 匹配, 前端直接透传即可。
    """
    rows = get_connection().execute(
        """
        SELECT id, name, created_at
        FROM security_entities
        WHERE entity_type = 'cve'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    items = [{"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/cve/attack-mapping")
async def get_attack_mapping(
    cve_ids: str = Query("", description="逗号分隔的 CVE 编号列表"),
) -> dict[str, Any]:
    """CVE → ATT&CK technique 映射。"""
    ids = [c.strip() for c in cve_ids.split(",") if c.strip()]
    return cves_to_attack_techniques(ids)


@router.post("/cve/attack-data/load")
async def load_attack_data_endpoint() -> dict[str, Any]:
    """手动触发 ATT&CK 数据灌入 (幂等, 仅当表空时写入)。"""
    return load_attack_data()


__all__ = ["router"]
