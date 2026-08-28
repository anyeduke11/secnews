"""ai_hub/tasks.py — AI 任务门面：AIService + evaluate_article + 知识写回。

职责
----
- ``AIService``: evaluate / gate_detect（集中式凭据 / 缓存 / 限频 / 调用）
- ``evaluate_article``: 统一评价入口（委托 AIService.evaluate）
- ``write_score``: ai_scores 写路径唯一入口
- ``write_item`` / ``update_frontmatter``: 知识写回唯一门面
- Prompt / 解析辅助: _DETECT_SYSTEM / _eval_prompt / _parse_eval_json / _parse_score01
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from backend.logging_config import logger as _logger
from backend.repository.db import get_connection

from .cache import get_ai_cache, set_ai_cache
from .gateway import llm_service

log = logging.getLogger("hotspot.ai_hub")

# 默认评分兜底 (score 0-10 / confidence 用 0.5 见 write_item 侧)
DEFAULT_SCORE = 5.0


# ═══════════════════════════════════════════════════════════════
# AIService — 集中式 AI 管理 (凭据 / 缓存 / 限频 / 调用)
# ═══════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(prefix: str, content: str) -> str:
    return f"{prefix}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


class AIService:
    """集中式 AI 服务：凭据 / 缓存 / 限频 / 调用统一管理。

    v0.6 P0-⑥ 双引擎收敛：provider 定义（base_url / 模型 / api_key_env）
    与 LLMService 共用 ``config/llm.yaml`` 单一来源（经 ``llm_service.config``）。
    ``FALLBACK_*`` 常量仅在配置缺失/未声明该 provider 时兜底，取值与
    收敛前的硬编码一致，保证无配置环境行为不变。
    """

    # 采集热路径限频：默认 60s 内最多 6 次（商汤免费 rpm 有限）。
    GATE_RATE_WINDOW_S = 60
    GATE_RATE_MAX = 6

    # 无 llm.yaml 或 provider 未声明时的历史兜底值
    FALLBACK_BASE_URLS: ClassVar[dict[str, str]] = {
        "sensenova": "https://token.sensenova.cn/v1",
        "ollama": "http://127.0.0.1:11434",
    }
    FALLBACK_EVAL_MODELS: ClassVar[dict[str, str]] = {
        "sensenova": "sensenova-6.8-flash-lite",
        "ollama": "qwen2.5:7b",
    }

    def __init__(self) -> None:
        self._gate_calls: deque[float] = deque(maxlen=128)

    # ------------------------------------------------------------------
    # provider / 凭据（llm.yaml 单一来源 + env 覆盖）
    # ------------------------------------------------------------------
    @staticmethod
    def _provider_cfg(name: str):
        """取共享 LLMConfig 中 provider 定义；无配置或未声明时返回 None。"""
        cfg = llm_service.config
        if cfg is None:
            return None
        return cfg.providers.get(name)

    @classmethod
    def _base_url(cls, provider: str) -> str:
        """chat 端点 base（不含路径后缀；openai 系拼 /chat/completions）。"""
        pcfg = cls._provider_cfg(provider)
        if pcfg is not None and pcfg.base_url:
            return pcfg.base_url.rstrip("/")
        return cls.FALLBACK_BASE_URLS.get(
            provider, cls.FALLBACK_BASE_URLS["sensenova"])

    @classmethod
    def _eval_model(cls, provider: str) -> str:
        """evaluate / gate_detect 所用模型。"""
        pcfg = cls._provider_cfg(provider)
        if pcfg is not None:
            return pcfg.models.score
        return cls.FALLBACK_EVAL_MODELS.get(
            provider, cls.FALLBACK_EVAL_MODELS["sensenova"])

    @staticmethod
    def _resolve_provider() -> str:
        """S4-1 决议: 三级优先级 — AI_PROVIDER env > router 推荐 > default_provider。

        兼容旧行为: cfg.default_provider 为空 / 未配置时仍兜底到 sensenova。
        router 推荐失败 (LLM 未启用 / import 异常) 时也直接回退到 default_provider。
        """
        import os
        env = os.environ.get("AI_PROVIDER")
        if env:
            return env
        try:
            from backend.services.llm.model_router import route_model
            # AIService 的 evaluate/gate_detect 是标准分析档; router 推荐最稳的 provider
            routed = route_model("evaluate", config=llm_service.config)
            if routed and routed[0]:
                return routed[0]
        except Exception as e:
            log.debug(f"AIService._resolve_provider router fallback: {e}")
        cfg = llm_service.config
        return cfg.default_provider if cfg is not None else "sensenova"

    @staticmethod
    def _resolve_api_key() -> str:
        """按当前 provider 的 api_key_env 读密钥（不持久化到 settings）。"""
        import os
        p = AIService._resolve_provider()
        pcfg = AIService._provider_cfg(p)
        env_name = (pcfg.api_key_env if pcfg is not None else None) \
            or "SENSENOVA_API_KEY"
        return os.environ.get(env_name, "") or ""

    @staticmethod
    def _ollama_up(timeout: float = 1.0) -> bool:
        import urllib.request
        base = AIService._base_url("ollama")
        try:
            with urllib.request.urlopen(
                f"{base}/api/tags", timeout=timeout
            ):
                return True
        except Exception:
            return False

    def available(self, provider: str | None = None) -> bool:
        """provider 是否就绪。"""
        p = provider or self._resolve_provider()
        if p == "ollama":
            return self._ollama_up()
        return bool(self._resolve_api_key())

    # ------------------------------------------------------------------
    # 限频（供采集热路径门禁用）
    # ------------------------------------------------------------------
    def gate_rate_allowed(self) -> bool:
        now = time.monotonic()
        while self._gate_calls and \
                now - self._gate_calls[0] > self.GATE_RATE_WINDOW_S:
            self._gate_calls.popleft()
        return len(self._gate_calls) < self.GATE_RATE_MAX

    def gate_rate_mark(self) -> None:
        self._gate_calls.append(time.monotonic())

    # ------------------------------------------------------------------
    # 能力：提炼关键内容 + 质量评分（用户保留的唯一 LLM 功能）
    # ------------------------------------------------------------------
    def evaluate(
        self,
        content: str,
        *,
        title: str = "",
        provider: str | None = None,
        api_key: str | None = None,
        timeout: float = 20.0,
    ) -> dict:
        """用大模型评价文章质量并提炼关键内容。

        返回 { ok, provider, quality_score(0-10), verdict, key_points, summary }。
        失败时 ok=False + error（不静默降级，便于人工复核/测试）。
        """
        p = provider or self._resolve_provider()
        key = api_key if api_key is not None else self._resolve_api_key()

        # 缓存
        cache_key = _cache_key("eval", f"{title}|{content}")
        if self._cache_get(cache_key) is not None:
            return self._cache_get(cache_key)

        try:
            if p == "ollama":
                result = self._call_ollama_eval(title, content, timeout)
            else:
                result = self._call_sensenova_eval(
                    title, content, key, timeout
                )
        except Exception as e:
            self._usage(p, self._eval_model(p), "evaluate", 0, 0.0)
            _logger.warning("ai evaluate failed (%s): %s", p, e)
            return {"ok": False, "provider": p, "error": f"{type(e).__name__}: {str(e)[:300]}"}

        result["ok"] = True
        result["provider"] = result.get("provider", p)
        self._cache_set(cache_key, result)
        self._usage(p, self._eval_model(p), "evaluate", _est_tokens(f"{title}{content}"), 0.0)
        return result

    def gate_detect(
        self, title: str, summary: str,
        provider: str | None = None, api_key: str | None = None,
        timeout: float = 8.0,
    ) -> float | None:
        """门禁专用 AI 概率（0..1），带限频；超限/失败返回 None（fail-open）。"""
        p = provider or self._resolve_provider()
        if not self.available(p):
            return None
        # 商汤付费：限频；ollama 本地免费不限。
        if p != "ollama" and not self.gate_rate_allowed():
            return None
        key = api_key if api_key is not None else self._resolve_api_key()
        try:
            if p == "ollama":
                self.gate_rate_mark()
                return self._call_ollama_detect(title, summary, timeout)
            self.gate_rate_mark()
            return self._call_sensenova_detect(title, summary, key, timeout)
        except Exception as e:
            _logger.warning("ai gate-detect failed (%s): %s", p, e)
            return None

    # ------------------------------------------------------------------
    # 商汤日日新 / ollama 调用
    # ------------------------------------------------------------------
    def _call_sensenova_eval(self, title: str, content: str, key: str, timeout: float) -> dict:
        prompt = _eval_prompt(title, content)
        url = self._base_url("sensenova") + "/chat/completions"
        payload = {
            "model": self._eval_model("sensenova"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "temperature": 0.2, "max_tokens": 600,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _parse_eval_json(raw, provider="sensenova")

    def _call_ollama_eval(self, title: str, content: str, timeout: float) -> dict:
        prompt = _eval_prompt(title, content)
        url = self._base_url("ollama") + "/api/chat"
        payload = {
            "model": self._eval_model("ollama"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "temperature": 0.2, "options": {"num_predict": 600},
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("message") or {}).get("content", "") or ""
        return _parse_eval_json(raw, provider="ollama")

    def _call_sensenova_detect(self, title: str, summary: str, key: str, timeout: float) -> float:
        text = f"标题：{title}\n摘要：{summary}"
        url = self._base_url("sensenova") + "/chat/completions"
        payload = {
            "model": self._eval_model("sensenova"),
            "messages": [
                {"role": "system", "content": _DETECT_SYSTEM},
                {"role": "user", "content": text},
            ],
            "stream": False, "temperature": 0.0, "max_tokens": 8,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _parse_score01(raw)

    def _call_ollama_detect(self, title: str, summary: str, timeout: float) -> float:
        text = f"标题：{title}\n摘要：{summary}"
        url = self._base_url("ollama") + "/api/chat"
        payload = {
            "model": self._eval_model("ollama"),
            "messages": [
                {"role": "system", "content": _DETECT_SYSTEM},
                {"role": "user", "content": text},
            ],
            "stream": False, "temperature": 0.0, "options": {"num_predict": 8},
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("message") or {}).get("content", "") or ""
        return _parse_score01(raw)

    # ------------------------------------------------------------------
    # 向后兼容：旧版 _cache_get/_cache_set/_usage 方法签名
    # (测试 monkeypatch 仍通过 ai_service 实例调用)
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> dict | None:
        return get_ai_cache(key)

    def _cache_set(self, key: str, value: dict) -> None:
        set_ai_cache(key, value)

    def _usage(self, task: str, provider: str, tokens: int, cost: float) -> None:
        from .usage import log_ai_usage
        log_ai_usage(provider, self._eval_model(provider), task, tokens, cost)


# 全局单例
ai_service = AIService()


# ═══════════════════════════════════════════════════════════════
# Prompt / 解析 (AI 能力辅助)
# ═══════════════════════════════════════════════════════════════

_DETECT_SYSTEM = (
    "你是一名内容质量审查员。判断下面的资讯是否为AI批量生成的低信息密度内容"
    "或营销软文。只输出一个0到1的数字（1=极可能AI生成/软文，0=真实高信息密度），"
    "不要输出任何其他文字。"
)


def _eval_prompt(title: str, content: str) -> str:
    title_line = f"标题：{title}\n" if title else ""
    return (
        "你是一名资深内容质量评审。请对下面的文章做两件事，并严格以 JSON 输出"
        "（不要任何其他文字）：\n"
        "1. 评价文章质量，fields: {\"score\": 0到10的浮点数，"
        "\"verdict\": 一句话总体评价}\n"
        "2. 提取文章关键内容，fields: {\"summary\": 2-3句摘要, "
        "\"key_points\": [3-6个要点字符串]}\n"
        f"输出格式：{{\"score\": <0-10>,\"verdict\":\"...\","
        f"\"summary\":\"...\",\"key_points\":[\"...\",\"...\"]}}\n\n"
        f"{title_line}文章内容：\n{content[:4000]}"
    )


def _parse_eval_json(raw: str, *, provider: str) -> dict:
    import re
    try:
        start, end = raw.index("{"), raw.rindex("}")
        data = json.loads(raw[start:end + 1])
        if isinstance(data, dict):
            return {
                "provider": provider,
                "quality_score": float(data.get("score", DEFAULT_SCORE)),
                "verdict": str(data.get("verdict", "")),
                "summary": str(data.get("summary", "")),
                "key_points": [str(k) for k in data.get("key_points", [])],
            }
    except (ValueError, json.JSONDecodeError):
        pass
    m = re.search(r"\"score\"\s*:\s*(\d+(?:\.\d+)?)", raw)
    score = float(m.group(1)) if m else DEFAULT_SCORE
    return {
        "provider": provider,
        "quality_score": score,
        "verdict": raw[:200],
        "summary": "",
        "key_points": [],
    }


def _parse_score01(raw: str) -> float:
    import re
    m = re.search(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", (raw or "").strip())
    if not m:
        return 0.0
    return max(0.0, min(1.0, float(m.group(0))))


def _est_tokens(text: str) -> int:
    return len(text) // 4


# ═══════════════════════════════════════════════════════════════
# evaluate_article — 文章评价统一入口 (M5 合并后单契约)
# ═══════════════════════════════════════════════════════════════
async def evaluate_article(
    content: str,
    *,
    title: str = "",
    provider: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict:
    """用大模型评价文章质量并提炼关键内容（统一委托 AIService）。

    凭据 / 缓存 / 用量 / 限频统一由 ``ai_service`` 管理（env 优先，
    不再读 settings 表）。返回结构化结果：

        { ok, provider, quality_score(0-10), verdict,
          key_points: [str], summary, error? }

    失败时 ok=False + error（不静默降级，便于测试定位）。
    """
    import asyncio

    def _call():
        return ai_service.evaluate(
            content, title=title, provider=provider,
            api_key=api_key, timeout=timeout,
        )

    # evaluate 为同步阻塞的 httpx 调用，放入线程池避免阻塞事件循环
    return await asyncio.to_thread(_call)


# ═══════════════════════════════════════════════════════════════
# ai_scores 写路径唯一入口 (SPEC §1 Task19)
# ═══════════════════════════════════════════════════════════════
def write_score(
    hotspot_id: str,
    score: float,
    *,
    reason: str = "ai_hub",
    scorer: str | None = None,
) -> int | None:
    """写入 ``ai_scores`` 表 — 生产代码唯一 INSERT 入口。

    SPEC §1 Task19: ``ai_scores`` 写路径仅本函数命中; mcp_agent_tools 的
    ``score_item`` 与 T1 的 LLM 评分审计都必须经此调用。

    Args:
        hotspot_id: 关联 hotspot / knowledge item id
        score: 0-10 评分
        reason: 评分理由/来源 (如 llm_service / agent:claude-desktop)
        scorer: 评分者标识 (MCP agent 工具用), 默认 None

    Returns:
        lastrowid; 失败返回 None (评分是审计增强, 静默降级不阻塞业务)。
    """
    try:
        cur = get_connection().execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scorer, scored_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (hotspot_id, float(score), reason, scorer, _now_iso()),
        )
        return cur.lastrowid
    except Exception as e:
        log.warning(f"write_score failed for {hotspot_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 知识写回唯一门面 (v0.5 §18.2 强约束 1)
# ═══════════════════════════════════════════════════════════════
def write_item(
    item: dict,
    content: str | None = None,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> None:
    """写回 ``knowledge/items/{id}.md`` 并在 wiki_events 留痕。

    md 写失败向上抛错 (真相源必须成功); 遥测失败静默降级 (不阻塞写路径)。

    Args:
        item: knowledge_items dict (须含 id)
        content: Markdown 正文 (None=保留文件已有正文, ''=清空)
        kind: wiki_events 事件类型, 默认 agent_write
        agent: 产生者标识, 如 api:patch_item / mcp:wiki_write
    """
    from backend.services import knowledge_sync

    knowledge_sync.write_item_to_md(item, content=content)
    item_id = str(item.get("id", ""))
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind=kind,
            wiki_path=f"items/{item_id}.md",
            db_table="knowledge_items",
            db_row_id=item_id,
            agent=agent,
        )
    except Exception as e:
        log.debug(f"wiki_events log skipped for items/{item_id}.md: {e}")


def update_frontmatter(
    rel_path: str,
    key: str,
    value: str,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> bool:
    """就地更新 md frontmatter 单字段并留痕。

    Args:
        rel_path: 相对 knowledge/ 的路径, 如 ``concepts/zero-trust.md``
        key/value: 要写入的 frontmatter 字段
        kind/agent: wiki_events 事件类型与产生者

    Returns True on success (同 knowledge_sync.update_md_frontmatter_field)。
    """
    from backend.services.knowledge_sync import KNOWLEDGE_DIR, update_md_frontmatter_field

    ok = update_md_frontmatter_field(KNOWLEDGE_DIR / rel_path, key, value)
    if ok:
        try:
            from backend.repository.wiki_event_repo import wiki_event_repo

            wiki_event_repo.log(kind=kind, wiki_path=rel_path, agent=agent)
        except Exception as e:
            log.debug(f"wiki_events log skipped for {rel_path}: {e}")
    return ok
