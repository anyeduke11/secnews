"""v0.7 Batch ⑤ — 用户显式反馈服务 (点赞/点踩).

编排层职责:
  1. 查实体元数据 (category/source/tags/title)
  2. 调用 profile_service.record_feedback 更新即时权重
  3. 写入 feedback_events 持久化
  4. 桥接 dsh session JSONL (复用 dsh 内置 message-feedback 语义)
  5. (M5) 异步触发 AI 分析

设计原则: 不重造 dsh 内置 feedback 协议, 仅做 hotspot 业务侧桥接。
"""
from __future__ import annotations

from typing import Any

from backend.repository.db import get_connection
from backend.repository.feedback_repo import FeedbackRepository
from backend.services import profile_service

# v0.7 Batch ⑤: dsh session 桥接 (可选, 不阻塞主路径)
try:
    from backend.services.dsh.session_bridge import dsh_session_bridge
except Exception:  # pragma: no cover — 配置缺失时降级
    dsh_session_bridge = None  # type: ignore[assignment]


class FeedbackService:
    """用户反馈编排服务."""

    def __init__(self) -> None:
        self._repo = FeedbackRepository()

    def submit_feedback(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
    ) -> dict[str, Any]:
        """提交点赞/点踩。

        Parameters
        ----------
        entity_type:
            ``"hotspot"`` 或 ``"knowledge"``。
        entity_id:
            实体 ID。
        action:
            ``"like"`` 或 ``"dislike"``。

        Returns
        -------
        dict
            ``{"ok", "action", "signal", "weights", "event_id"}``
        """
        if action not in ("like", "dislike"):
            raise ValueError(f"invalid action: {action!r}; expected 'like' or 'dislike'")

        metadata = self._get_entity_metadata(entity_type, entity_id)
        signal = profile_service.SIGNAL_LIKE if action == "like" else profile_service.SIGNAL_DISLIKE

        # 1. 更新 profile_service 即时权重
        weights: dict[str, float] = {}
        if metadata:
            weights = profile_service.record_feedback(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                metadata=metadata,
            )

        # 2. 持久化到 feedback_events
        event = self._repo.record(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            signal=signal,
            category=metadata.get("category") if metadata else None,
            source=metadata.get("source") if metadata else None,
            tags=metadata.get("tags", []) if metadata else [],
            title=metadata.get("title") if metadata else None,
        )

        # 3. 桥接 dsh session JSONL (不阻塞主路径)
        if dsh_session_bridge is not None:
            try:
                dsh_session_bridge.write_feedback_event(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    signal=signal,
                    category=metadata.get("category") if metadata else None,
                    source=metadata.get("source") if metadata else None,
                    tags=metadata.get("tags", []) if metadata else [],
                    title=metadata.get("title") if metadata else None,
                    created_at=event.get("created_at"),
                )
            except Exception:
                # 桥接失败不影响主路径
                pass

        return {
            "ok": True,
            "action": action,
            "signal": signal,
            "weights": weights,
            "event_id": event.get("id"),
        }

    def get_entity_feedback(
        self, entity_type: str, entity_id: str
    ) -> list[dict[str, Any]]:
        """查询某实体的反馈历史。"""
        return self._repo.get_by_entity(entity_type, entity_id)

    def get_feedback_profile(self, limit: int = 20) -> dict[str, Any]:
        """获取用户反馈画像摘要。

        Returns
        -------
        dict
            ``{"total_likes", "total_dislikes", "recent": [...]}``
        """
        total_likes = self._repo.count_by_action("like")
        total_dislikes = self._repo.count_by_action("dislike")
        recent = self._repo.recent(limit=limit)
        return {
            "total_likes": total_likes,
            "total_dislikes": total_dislikes,
            "recent": recent,
        }

    def get_feedback_history(self, limit: int = 100) -> dict[str, Any]:
        """获取全部反馈记录（用于设置页历史列表）。

        Returns
        -------
        dict
            ``{"items": [...]}``
        """
        items = self._repo.recent(limit=limit)
        return {"items": items}

    def get_role_summary(self) -> dict[str, Any]:
        """生成/获取角色倾向总结。

        优先从 user_memory 读取 AI 已分析结果；若不存在则返回基础统计。
        """
        try:
            from backend.services.user_memory_service import user_memory_service
            ctx = user_memory_service.get_user_context()
            interests = [m.get("key", "").split(":", 1)[-1] for m in ctx.get("interests", [])]
            dislikes = [m.get("key", "").split(":", 1)[-1] for m in ctx.get("dislikes", [])]
            sources = [m.get("key", "").split(":", 1)[-1] for m in ctx.get("source_prefs", [])]
            style = ""
            for m in ctx.get("reading_style", []):
                val = m.get("value", "")
                try:
                    import json
                    style = json.loads(val).get("style", "")
                except Exception:
                    pass
            total_likes = self._repo.count_by_action("like")
            total_dislikes = self._repo.count_by_action("dislike")
            total = total_likes + total_dislikes
            confidence = min(1.0, total / 20.0) if total > 0 else 0.0
            summary = self._build_summary_text(total_likes, total_dislikes, interests, dislikes, style)
            return {
                "summary": summary,
                "interests": interests[:8],
                "dislikes": dislikes[:8],
                "preferred_sources": sources[:8],
                "reading_style": style or "mixed",
                "confidence": round(confidence, 2),
                "total_feedback": total,
            }
        except Exception as exc:
            logger.warning("get_role_summary failed: %s", exc)
            return {
                "summary": "暂无足够反馈数据，继续点赞/点踩后将自动生成画像。",
                "interests": [],
                "dislikes": [],
                "preferred_sources": [],
                "reading_style": "mixed",
                "confidence": 0.0,
                "total_feedback": 0,
            }

    @staticmethod
    def _build_summary_text(likes: int, dislikes: int, interests: list[str], dislikes_list: list[str], style: str) -> str:
        parts = [f"累计反馈 {likes + dislikes} 次（👍{likes} / 👎{dislikes}）"]
        if interests:
            parts.append(f"兴趣集中在 {', '.join(interests[:5])}")
        if dislikes_list:
            parts.append(f"排斥 {', '.join(dislikes_list[:5])}")
        style_map = {"deep": "深度阅读型", "skim": "快速浏览型", "mixed": "混合阅读型"}
        parts.append(f"阅读风格：{style_map.get(style, '混合阅读型')}")
        return "；".join(parts) + "。"

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------
    def _get_entity_metadata(self, entity_type: str, entity_id: str) -> dict | None:
        """从 DB 读取实体元数据 (category/source/tags/title)。"""
        if entity_type == "hotspot":
            return self._get_hotspot_metadata(entity_id)
        if entity_type == "knowledge":
            return self._get_knowledge_metadata(entity_id)
        return None

    def _get_hotspot_metadata(self, hotspot_id: str) -> dict | None:
        row = (
            get_connection()
            .execute(
                "SELECT id, title, source, category, summary "
                "FROM hotspots WHERE id = ?",
                (hotspot_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        tags = self._get_hotspot_tags(hotspot_id)
        return {
            "title": row["title"],
            "source": row["source"],
            "category": row["category"],
            "tags": tags,
        }

    def _get_hotspot_tags(self, hotspot_id: str) -> list[str]:
        rows = (
            get_connection()
            .execute(
                "SELECT ht.tag_id "
                "FROM hotspot_tags ht "
                "WHERE ht.hotspot_id = ?",
                (hotspot_id,),
            )
            .fetchall()
        )
        return [r["tag_id"] for r in rows]

    def _get_knowledge_metadata(self, item_id: str) -> dict | None:
        row = (
            get_connection()
            .execute(
                "SELECT id, title, source, category, tags "
                "FROM knowledge_items WHERE id = ?",
                (item_id,),
            )
            .fetchone()
        )
        if row is None:
            return None
        import json
        tags = []
        raw_tags = row["tags"]
        if raw_tags:
            try:
                tags = json.loads(raw_tags)
                if not isinstance(tags, list):
                    tags = []
            except Exception:
                tags = []
        return {
            "title": row["title"],
            "source": row["source"],
            "category": row["category"],
            "tags": tags,
        }


__all__ = ["FeedbackService"]
