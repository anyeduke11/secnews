"""v0.7 Batch ⑤ — 反馈 AI 分析器.

职责:
  1. 从 feedback_events 读取近期反馈批次
  2. 构造分析 prompt 调用 LLM (via ai_hub.llm_service.generate)
  3. 解析 LLM 返回的结构化 JSON
  4. 写入 user_memory_service 形成用户记忆

调度: 由 feedback_service.submit_feedback 异步触发 (asyncio.create_task),
      也可独立调用 analyze_batch()。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.repository.feedback_repo import FeedbackRepository
from backend.services.user_memory_service import user_memory_service

logger = logging.getLogger(__name__)

# 触发 AI 分析的最小反馈数 (避免空转)
_BATCH_SIZE = 20

# 分析 prompt 模板
_ANALYSIS_PROMPT = """\
基于用户最近的点赞/点踩行为，分析其阅读偏好与兴趣画像。

最近 {count} 条反馈：
{events}

请输出严格 JSON，结构如下：
{{
  "interests": ["感兴趣的标签/分类", ...],
  "dislikes": ["排斥的标签/分类", ...],
  "preferred_sources": ["偏好的数据源", ...],
  "reading_style": "deep|skim|mixed",
  "confidence": 0.0-1.0,
  "summary": "一句话用户画像"
}}

要求：
- interests/dislikes 各最多 8 项，按置信度降序
- reading_style 只取 deep/skim/mixed
- confidence 根据反馈数量和质量综合判断
- summary 不超过 50 字"""


class FeedbackAnalyzer:
    """反馈批次分析器."""

    def __init__(self) -> None:
        self._repo = FeedbackRepository()

    def analyze_batch(self, batch_size: int = _BATCH_SIZE) -> dict[str, Any]:
        """分析一批反馈事件并写入 user_memory。

        Parameters
        ----------
        batch_size:
            最多分析的反馈条数。

        Returns
        -------
        dict
            ``{"ok", "analyzed", "memory_keys", "error"?}``
        """
        events = self._repo.recent(limit=batch_size)
        if not events:
            return {"ok": True, "analyzed": 0, "memory_keys": []}

        prompt = _ANALYSIS_PROMPT.format(
            count=len(events),
            events=self._format_events(events),
        )

        try:
            raw = self._call_llm(prompt)
            result = self._parse_result(raw)
            memory_keys = self._apply_analysis(result)
            return {"ok": True, "analyzed": len(events), "memory_keys": memory_keys}
        except Exception as exc:
            logger.error("feedback analyze failed: %s", exc)
            return {"ok": False, "analyzed": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------
    def _format_events(self, events: list[dict]) -> str:
        lines: list[str] = []
        for i, e in enumerate(events, 1):
            tags = ""
            raw_tags = e.get("tags")
            if raw_tags:
                try:
                    tags = json.loads(raw_tags)
                    if isinstance(tags, list):
                        tags = ", ".join(tags)
                    else:
                        tags = str(tags)
                except Exception:
                    tags = str(raw_tags)
            lines.append(
                f"{i}. [{e.get('created_at','')}] {e.get('action')} "
                f"on {e.get('entity_type')}:{e.get('entity_id')} "
                f"(category={e.get('category')}, source={e.get('source')}, tags={tags})"
            )
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 生成分析结果."""
        try:
            from backend.services.ai_hub.gateway import llm_service
            if not llm_service.enabled:
                return ""
            # 在线程池中运行异步 generate
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    llm_service.generate(prompt, task="analyze_feedback")
                )
            finally:
                loop.close()
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return ""

    def _parse_result(self, raw: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON."""
        if not raw:
            return {}
        # 尝试提取 JSON (LLM 可能返回 markdown 代码块)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = "\n".join(text.splitlines()[:-1])
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 兜底: 尝试找第一个 { 到最后一个 }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    pass
            return {}

    def _apply_analysis(self, result: dict[str, Any]) -> list[str]:
        """将分析结果写入 user_memory."""
        memory_keys: list[str] = []

        for interest in result.get("interests", []) or []:
            key = f"interest:{interest}"
            user_memory_service.record_memory(
                memory_type="interest", key=key,
                value=json.dumps({"source": "feedback_analyzer", "interest": interest}, ensure_ascii=False),
            )
            memory_keys.append(key)

        for dislike in result.get("dislikes", []) or []:
            key = f"dislike:{dislike}"
            user_memory_service.record_memory(
                memory_type="dislike", key=key,
                value=json.dumps({"source": "feedback_analyzer", "dislike": dislike}, ensure_ascii=False),
            )
            memory_keys.append(key)

        for source in result.get("preferred_sources", []) or []:
            key = f"source_pref:{source}"
            user_memory_service.record_memory(
                memory_type="source_pref", key=key,
                value=json.dumps({"source": "feedback_analyzer", "preferred_source": source}, ensure_ascii=False),
            )
            memory_keys.append(key)

        reading_style = result.get("reading_style")
        if reading_style:
            user_memory_service.record_memory(
                memory_type="reading_style", key="current",
                value=json.dumps({"source": "feedback_analyzer", "style": reading_style}, ensure_ascii=False),
            )
            memory_keys.append("reading_style:current")

        return memory_keys


__all__ = ["FeedbackAnalyzer"]
