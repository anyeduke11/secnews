"""S4-4 合规矩阵服务 — 事件 ↔ 合规条款双向交叉表。

数据源
------
- `data/compliance/frameworks.json` — 3 框架控制项静态嵌入
- `data/compliance/event-mapping.json` — 事件类型 → 控制项静态映射

返回格式
--------
matrix(event_types) -> {
    "rows": [
        {
            "event_type": "data_breach",
            "controls": [
                {"framework": "gdpr", "control_id": "Art.33", "name": "..."},
                ...
            ]
        },
        ...
    ],
    "columns": [
        {"framework": "gdpr", "control_id": "Art.33", "name": "..."},
        ...
    ]
}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Static data loaders (called once at startup / first request)
# ---------------------------------------------------------------------------
_FRAMEWORKS_PATH = Path(__file__).resolve().parent.parent.parent / "data/compliance/frameworks.json"
_EVENT_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "data/compliance/event-mapping.json"

_frameworks_cache: dict[str, dict[str, Any]] | None = None
_event_mapping_cache: dict[str, list[dict[str, str]]] | None = None


def _load_frameworks() -> dict[str, dict[str, Any]]:
    global _frameworks_cache
    if _frameworks_cache is None:
        raw = json.loads(_FRAMEWORKS_PATH.read_text(encoding="utf-8"))
        _frameworks_cache = {fw["id"]: fw for fw in raw}
    return _frameworks_cache


def _load_event_mapping() -> dict[str, list[dict[str, str]]]:
    global _event_mapping_cache
    if _event_mapping_cache is None:
        _event_mapping_cache = json.loads(_EVENT_MAPPING_PATH.read_text(encoding="utf-8"))
    return _event_mapping_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_frameworks() -> list[dict[str, Any]]:
    """返回 3 框架元数据列表 (不含 controls 详情)。"""
    fws = _load_frameworks()
    return [
        {
            "id": fw_id,
            "name": fw["name"],
            "description": fw["description"],
            "control_count": len(fw.get("controls", [])),
        }
        for fw_id, fw in fws.items()
    ]


def controls_for_event(event_type: str) -> list[dict[str, str]]:
    """返回某事件类型对应的控制项列表。"""
    mapping = _load_event_mapping()
    controls_raw = mapping.get(event_type, [])
    fws = _load_frameworks()
    result = []
    for item in controls_raw:
        fw = fws.get(item["framework"], {})
        for ctrl in fw.get("controls", []):
            if ctrl["id"] == item["control_id"]:
                result.append({
                    "framework": item["framework"],
                    "control_id": ctrl["id"],
                    "name": ctrl["name"],
                    "description": ctrl.get("description", ""),
                })
                break
    return result


def matrix(
    event_types: list[str],
    frameworks: list[str] | None = None,
) -> dict[str, Any]:
    """返回合规矩阵数据 (rows × columns)。

    Args:
        event_types: 行维度事件类型列表。
        frameworks: 可选框架过滤 (如 ["gdpr", "dengbao"])，空列表 = 全部。

    Returns:
        {
            "rows": [{"event_type": "...", "controls": [...]}],
            "columns": [{"framework": "...", "control_id": "...", "name": "..."}]
        }
    """
    fws = _load_frameworks()
    mapping = _load_event_mapping()

    # Build column set
    column_map: dict[tuple[str, str], dict[str, str]] = {}
    for event_type in event_types:
        for item in mapping.get(event_type, []):
            fw_id = item["framework"]
            if frameworks and fw_id not in frameworks:
                continue
            fw = fws.get(fw_id, {})
            for ctrl in fw.get("controls", []):
                if ctrl["id"] == item["control_id"]:
                    key = (fw_id, ctrl["id"])
                    if key not in column_map:
                        column_map[key] = {
                            "framework": fw_id,
                            "control_id": ctrl["id"],
                            "name": ctrl["name"],
                        }
                    break

    columns = [column_map[k] for k in sorted(column_map.keys())]

    # Build rows
    rows = []
    for event_type in event_types:
        controls_raw = mapping.get(event_type, [])
        row_controls = []
        for item in controls_raw:
            fw_id = item["framework"]
            if frameworks and fw_id not in frameworks:
                continue
            fw = fws.get(fw_id, {})
            for ctrl in fw.get("controls", []):
                if ctrl["id"] == item["control_id"]:
                    row_controls.append({
                        "framework": fw_id,
                        "control_id": ctrl["id"],
                        "name": ctrl["name"],
                    })
                    break
        rows.append({"event_type": event_type, "controls": row_controls})

    return {"rows": rows, "columns": columns}


__all__ = ["controls_for_event", "list_frameworks", "matrix"]
