"""v0.7 Batch ⑤ — DSH Session 桥接 (hotspot ↔ dsh session 日志).

职责:
  将 hotspot 反馈事件写入 dsh session JSONL 格式, 复用 dsh 内置
  message-feedback 语义模型, 而非自建协议。

设计:
  - 不直接连接 dsh HTTP (DSHClient 仍是 stub), 而是写本地 JSONL 文件,
    dsh 侧可配置读取同一目录。
  - JSONL 格式遵循 dsh SessionEvent schema (最小可行子集):
    {"type":"feedback","entity_type":"hotspot","entity_id":"h-123",
     "action":"like","signal":0.4,"created_at":"..."}
  - 写入失败不阻塞反馈主路径 (catch + log)。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import config

logger = logging.getLogger(__name__)

# dsh session 日志目录 (配置驱动, 默认 data/dsh/sessions)
_SESSION_DIR = Path(getattr(config, "dsh_session_dir", "data/dsh/sessions"))
_SESSION_DIR.mkdir(parents=True, exist_ok=True)


class DSHSessionBridge:
    """hotspot 与 dsh session 日志的双向桥接 (MVP: 单向写入)。"""

    def __init__(self, session_dir: Path | None = None) -> None:
        self._session_dir = session_dir or _SESSION_DIR

    def write_feedback_event(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        signal: float,
        *,
        category: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        title: str | None = None,
        created_at: str | None = None,
    ) -> None:
        """将反馈事件追加到 dsh session JSONL。

        Parameters
        ----------
        entity_type:
            ``"hotspot"`` 或 ``"knowledge"``。
        entity_id:
            实体 ID。
        action:
            ``"like"`` 或 ``"dislike"``。
        signal:
            信号强度 (0.4 / -0.3)。
        category/source/tags/title:
            冗余元数据, 便于 dsh 侧分析。
        created_at:
            ISO-8601 UTC 时间戳, 默认 now。
        """
        event: dict[str, Any] = {
            "type": "feedback",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "signal": signal,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        }
        if category:
            event["category"] = category
        if source:
            event["source"] = source
        if tags:
            event["tags"] = tags
        if title:
            event["title"] = title

        try:
            self._append_event(event)
        except Exception as e:
            logger.warning("dsh session_bridge write failed: %s", e)

    def read_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """读取 dsh session JSONL 中最近的 feedback 事件。

        Returns
        -------
        list[dict]
            按 created_at 升序排列的事件列表。
        """
        events: list[dict[str, Any]] = []
        try:
            for f in sorted(self._session_dir.glob("*.jsonl"), reverse=True):
                if not f.is_file():
                    continue
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                            if event.get("type") == "feedback":
                                events.append(event)
                        except json.JSONDecodeError:
                            continue
                if len(events) >= limit:
                    break
        except Exception as e:
            logger.warning("dsh session_bridge read failed: %s", e)

        events.sort(key=lambda e: e.get("created_at", ""))
        return events[-limit:]

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------
    def _append_event(self, event: dict[str, Any]) -> None:
        """追加单条事件到当日 session JSONL。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_file = self._session_dir / f"session-{today}.jsonl"
        line = json.dumps(event, ensure_ascii=False)
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# 模块级单例
dsh_session_bridge = DSHSessionBridge()

__all__ = ["DSHSessionBridge", "dsh_session_bridge"]
