"""retention_engine — Ebbinghaus 衰减追踪 (v0.5 M3.5 §18)。

职责 (SPEC §18.2 强约束 2 + llm-wiki-2.0/retention.json):
- 公式: ``current_score = initial_score * 0.9 ^ (days_since_access / 7)``
- access (read / search / citation) 时 reset: current_score = initial_score,
  last_accessed = now, decay_events 追加 ``{"kind": "access", "ts": ...}``
- 周 job 扫一遍 retention.json entries, 更新 current_score
- current_score < 0.3 标 stale (不删, 只降权)
- 配套 ``scripts/check_retention_decay.py`` (M3.5 c 子任务补) CI 验证 >0.7 占比 ≥ 80%

设计边界:
- 纯函数 (record_access / run_decay / decay_score) 易测, 无 DB 依赖
- 关闭 llm-wiki-v2 时上层 job 直接跳过本模块
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("hotspot.retention_engine")

# 衰减窗口 (天) — 公式分母 = 7 表示每 7 天乘 0.9
DECAY_WINDOW_DAYS = 7
DECAY_FACTOR_PER_WINDOW = 0.9
# stale 阈值 — < 0.3 视为陈旧 (不删, 只在 UI 排序里降权)
STALE_THRESHOLD = 0.3
# CI 健康阈值 — current_score > 0.7 的条目占比 ≥ 80% (wiki v2 §11 / SPEC M3.5)
RETENTION_HEALTHY_THRESHOLD = 0.7
RETENTION_HEALTHY_MIN_RATIO = 0.8


# ---------------------------------------------------------------------------
# 纯函数 (无 IO, 单元测试用)
# ---------------------------------------------------------------------------

def decay_score(initial: float, days_since_access: float) -> float:
    """Ebbinghaus 衰减公式: ``initial * 0.9 ^ (days / 7)``。

    Args:
        initial: 初始分数 (默认 1.0)
        days_since_access: 自上次访问天数 (可为 0/负/小数)

    Returns:
        current_score, 截断到 [0, initial] 区间, 精度 4 位小数
    """
    if days_since_access < 0:
        days_since_access = 0.0
    raw = initial * (DECAY_FACTOR_PER_WINDOW ** (days_since_access / DECAY_WINDOW_DAYS))
    # 截断: 不超过 initial, 不低于 0
    bounded = max(0.0, min(initial, raw))
    return round(bounded, 4)


def parse_iso(ts: str) -> float:
    """ISO8601 时间字符串 → 自 epoch 的天数 (浮点)。

    解析失败返回 0.0 (视为已充分衰减, 不抛错)。
    """
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(tz=timezone.utc) - dt
    return max(0.0, delta.total_seconds() / 86400.0)


# ---------------------------------------------------------------------------
# retention.json 读改写 (atomic, 与 wiki_archiver 同一模式)
# ---------------------------------------------------------------------------

def _atomic_write_text(target: Path, content: str) -> None:
    import os

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _load_retention(retention_path: Path) -> dict:
    if not retention_path.exists():
        return {"$schema_version": "0.5.0", "entries": []}
    try:
        return json.loads(retention_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"retention.json unreadable, returning empty: {e}")
        return {"$schema_version": "0.5.0", "entries": []}


def _save_retention(retention_path: Path, obj: dict) -> None:
    _atomic_write_text(
        retention_path,
        json.dumps(obj, indent=2, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------

def run_decay(retention_path: Path) -> dict[str, int]:
    """扫一遍 retention.json, 更新所有 entry 的 current_score。

    Args:
        retention_path: ``llm-wiki-2.0/retention.json`` 路径

    Returns:
        统计 dict: {updated, stale_after, unchanged, errors}
    """
    obj = _load_retention(retention_path)
    stats = {"updated": 0, "stale_after": 0, "unchanged": 0, "errors": 0}

    for entry in obj.get("entries", []):
        try:
            initial = float(entry.get("initial_score", 1.0))
            last_accessed = entry.get("last_accessed", "")
            days = parse_iso(last_accessed)
            new_score = decay_score(initial, days)
            old_score = entry.get("current_score", 1.0)
            if abs(new_score - old_score) > 0.0001:
                entry["current_score"] = new_score
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
            if new_score < STALE_THRESHOLD:
                stats["stale_after"] += 1
        except Exception as e:
            log.warning(f"decay entry error ({entry.get('id', '?')}): {e}")
            stats["errors"] += 1

    _save_retention(retention_path, obj)
    return stats


def record_access(
    retention_path: Path,
    item_id: str,
    *,
    now: str | None = None,
) -> bool:
    """记录对 item_id 的访问, reset current_score = initial_score。

    Args:
        retention_path: retention.json 路径
        item_id: 被访问条目 id
        now: ISO8601 时间字符串 (默认 now UTC); 测试可注入

    Returns:
        True = entry 已存在并被 reset; False = entry 不存在 (新建会一并完成,
        故 True 始终成立; 保留 bool 返回以表达意图)
    """
    obj = _load_retention(retention_path)
    now_iso = now or datetime.now(tz=timezone.utc).isoformat()
    found = False
    for entry in obj.get("entries", []):
        if entry.get("id") == item_id:
            entry["current_score"] = entry.get("initial_score", 1.0)
            entry["last_accessed"] = now_iso
            events = entry.setdefault("decay_events", [])
            events.append({"kind": "access", "ts": now_iso})
            # events 限长 (LIFO, 保留最近 50 条)
            if len(events) > 50:
                entry["decay_events"] = events[-50:]
            found = True
            break
    if not found:
        # entry 不存在 → 视为新建 (initial=1.0, current=1.0, last=now)
        obj.setdefault("entries", []).append({
            "id": item_id,
            "initial_score": 1.0,
            "current_score": 1.0,
            "last_accessed": now_iso,
            "decay_events": [{"kind": "access", "ts": now_iso}],
        })
    _save_retention(retention_path, obj)
    return True


def load_entry(retention_path: Path, item_id: str) -> dict[str, Any] | None:
    """读取单条目 retention entry (供 UI / API 调用方查 current_score)。"""
    obj = _load_retention(retention_path)
    for entry in obj.get("entries", []):
        if entry.get("id") == item_id:
            return entry
    return None


def check_retention_health(retention_path: Path) -> dict[str, Any]:
    """CI 健康检查: ``current_score > 0.7`` 的条目占比 ≥ 80%。

    Args:
        retention_path: ``llm-wiki-2.0/retention.json`` 路径

    Returns:
        ``{"total", "healthy", "ratio", "ok"}``; 无条目时 ratio=1.0, ok=True
        (空知识库不算失败)。
    """
    obj = _load_retention(retention_path)
    entries = obj.get("entries", [])
    total = len(entries)
    if total == 0:
        return {"total": 0, "healthy": 0, "ratio": 1.0, "ok": True}
    healthy = 0
    for entry in entries:
        try:
            if float(entry.get("current_score", 1.0)) > RETENTION_HEALTHY_THRESHOLD:
                healthy += 1
        except (TypeError, ValueError):
            continue
    ratio = healthy / total
    return {
        "total": total,
        "healthy": healthy,
        "ratio": round(ratio, 4),
        "ok": ratio >= RETENTION_HEALTHY_MIN_RATIO,
    }


__all__ = [
    "DECAY_FACTOR_PER_WINDOW",
    "DECAY_WINDOW_DAYS",
    "RETENTION_HEALTHY_MIN_RATIO",
    "RETENTION_HEALTHY_THRESHOLD",
    "STALE_THRESHOLD",
    "check_retention_health",
    "decay_score",
    "load_entry",
    "parse_iso",
    "record_access",
    "run_decay",
]