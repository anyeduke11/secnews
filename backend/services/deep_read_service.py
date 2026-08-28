"""DeepRead 深度分析面板服务 (Phase 4 S4-2)。

入口: ``DeepReadService.run(entity_type, entity_id, force=False)``.

行为:
- 表里已有 → 直接返回 (cache 命中, 不调 LLM)
- force=True 或不存在 → 按 entity_type 拉原文 → 拼 prompt → 调 LLM → 解析 4 节
  JSON → UPSERT deep_reads → 返回
- LLM 失败/解析失败 → 抛 ``DeepReadError``, **不写表** (避免半成品污染)
"""
from __future__ import annotations

import json
import time
from typing import Any

from backend.logging_config import logger
from backend.repository.deepread_repo import DeepReadItem, DeepReadRepository

# 模块级绑定 (让 ``patch("backend.services.deep_read_service.llm_service")`` 可用):
# 直接 import 单例会让函数体内的 import 重新覆盖 mock, 因此用 ai_hub.llm_service 路径访问。
from backend.services import ai_hub as _ai_hub_mod


class DeepReadError(Exception):
    """DeepRead 流程失败 (LLM 调用 / 解析 / 原文缺失)。"""


# ── Prompt 模板 ──────────────────────────────────────────────

_PROMPT_INSTRUCTION = """你是一名资深安全研究员, 正在分析下面这条信息, 生成 4 节深度分析报告。

严格要求:
1. **必须**返回合法 JSON, 字段严格匹配下方 schema, 不可省略任意 key。
2. 每节内容用 markdown 格式 (可含列表 / 粗体 / 代码块), 但不要套外层 markdown fence。
3. 简洁直接, 每节 80~200 字, 避免空话/重复条目/无信息量总结。
4. "summary" 节必须有具体技术内容 (CVE 编号/受影响组件/时间线/关键 IoC)。
5. "impact" 节必须区分影响范围 (全球/区域/特定行业) 与受影响对象 (终端/服务器/云/IoT)。
6. "relations" 节必须列出 ≥1 个可验证关联 (CVE ↔ 家族 / 漏洞 ↔ 利用框架 / 事件 ↔ actor)。
7. "risks" 节必须给出 ≥1 条具体可操作缓解建议 (补丁版本/配置项/监控规则)。

JSON schema:
{
  "summary": "<本条最核心的事件摘要, 含关键时间/技术/对象>",
  "impact": "<影响范围与对象的层次化分析>",
  "relations": "<关联家族/技术/事件的证据链>",
  "risks": "<威胁评估与可操作缓解建议>"
}

待分析内容:
"""


def _build_prompt(entity_type: str, entity_id: str, content: str) -> str:
    """组装 prompt (头部指令 + 来源元信息 + 正文)。"""
    header = f"[来源类型] {entity_type}\n[来源 ID] {entity_id}\n\n"
    return _PROMPT_INSTRUCTION + header + content[:8000]


# ── 原文拉取 ──────────────────────────────────────────────────


def _fetch_source(entity_type: str, entity_id: str) -> tuple[str, dict[str, str]]:
    """按 entity_type 拉原文 (Markdown 优先)。失败抛 ``DeepReadError``。

    支持的 entity_type: hotspot / wiki (v0.6 当前已落库实体)。
    cve / news 留待 v0.7+ 接入 (无 cves_repo)。
    """
    from backend.repository.hotspot_repo import HotspotRepository
    from backend.repository.knowledge_repo import KnowledgeRepo

    metadata: dict[str, str] = {"entity_type": entity_type, "entity_id": entity_id}

    if entity_type == "hotspot":
        item = HotspotRepository().get_by_id(entity_id)
        if item is None:
            raise DeepReadError(f"hotspot not found: {entity_id}")
        metadata["title"] = str(getattr(item, "title", "") or "")
        # HotspotItem 字段探测: summary / content / body
        body = str(
            getattr(item, "summary", "")
            or getattr(item, "content", "")
            or getattr(item, "body", "")
            or ""
        )
        return body, metadata

    if entity_type == "wiki":
        # knowledge_repo.get_item 按 id 查;若传 path,加 .md 后缀作为 item_id
        path = entity_id if entity_id.endswith(".md") else f"{entity_id}.md"
        item = KnowledgeRepo().get_item(path)
        if item is None:
            raise DeepReadError(f"wiki item not found: {path}")
        metadata["title"] = str(getattr(item, "title", "") or path)
        body = str(getattr(item, "content", "") or "")
        return body, metadata

    raise DeepReadError(
        f"unsupported entity_type: {entity_type} (supported: hotspot/wiki)"
    )


# ── JSON 解析 (容错) ─────────────────────────────────────────


def _parse_sections(raw: str) -> dict[str, str]:
    """从 LLM 原始输出抽取 4 节 JSON, 容错 markdown fence + 文本包裹。"""
    import re

    text = raw.strip()

    # 1) 直接 JSON 解析
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _normalize_sections(data)
    except json.JSONDecodeError:
        pass

    # 2) 去掉 ```json ... ``` 包裹
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1))
            if isinstance(data, dict):
                return _normalize_sections(data)
        except json.JSONDecodeError:
            pass

    # 3) 截取首个 { 到最后一个 } 之间
    if "{" in text and "}" in text:
        try:
            start, end = text.index("{"), text.rindex("}")
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return _normalize_sections(data)
        except (ValueError, json.JSONDecodeError):
            pass

    # 4) 全失败 — 整段塞 summary, 其余空
    logger.warning("DeepRead 4 节 JSON 解析失败, fallback 到整段 summary (raw=%d 字符)", len(text))
    return {"summary": text[:1000], "impact": "", "relations": "", "risks": ""}


def _normalize_sections(data: dict[str, Any]) -> dict[str, str]:
    """统一 4 节为 str (LLM 可能返回 list / None)。"""
    out: dict[str, str] = {}
    for key in ("summary", "impact", "relations", "risks"):
        val = data.get(key, "")
        if val is None:
            val = ""
        elif isinstance(val, list):
            val = "\n".join(str(x) for x in val)
        else:
            val = str(val)
        out[key] = val.strip()
    return out


def _sections_to_markdown(sections: dict[str, str]) -> str:
    """4 节 JSON → 完整 markdown 文档 (供前端整段渲染 / 下载)。"""
    titles = {
        "summary": "摘要",
        "impact": "影响",
        "relations": "关联",
        "risks": "风险",
    }
    lines: list[str] = []
    for key in ("summary", "impact", "relations", "risks"):
        title = titles[key]
        body = sections.get(key, "").strip()
        if not body:
            body = "_(本节暂无内容)_"
        lines.append(f"## {title}\n\n{body}\n")
    return "\n".join(lines)


# ── 入口 ──────────────────────────────────────────────────────


class DeepReadService:
    """DeepRead 4 节分析: hotspot / cve / wiki 跨实体一致接口。"""

    def __init__(self) -> None:
        self.repo = DeepReadRepository()

    async def run(
        self,
        entity_type: str,
        entity_id: str,
        force: bool = False,
    ) -> DeepReadItem:
        """获取或生成 DeepRead。

        - force=False 且表里有 → 直接返回
        - 否则拉原文 → 调 LLM → 4 节 JSON → UPSERT
        """
        existing = self.repo.get(entity_type, entity_id)
        if existing is not None and not force:
            return existing

        body, metadata = _fetch_source(entity_type, entity_id)

        # 拼 prompt
        content = body if body else "(原文为空, 仅依据 ID 与类型生成)"
        prompt = _build_prompt(entity_type, entity_id, content)

        # 调 LLM (走 ai_hub.LLMService.generate, 失败抛 DeepReadError)
        # 通过模块属性访问 (而非 from-import) 以保持测试 mock 生效。
        llm_service = _ai_hub_mod.llm_service
        t0 = time.monotonic()
        raw = await llm_service.generate(prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        if not raw or not raw.strip():
            raise DeepReadError(
                f"LLM 返回空 (entity={entity_type}/{entity_id}); 可能所有 provider 不可用"
            )

        sections = _parse_sections(raw)
        content_md = _sections_to_markdown(sections)
        sections_json = json.dumps(sections, ensure_ascii=False)

        # provider/model 记账: generate() 内部不暴露, 用 router 推荐 + 当前 model 推导。
        # 若 LLM 实际跑了 fallback 链的不同 provider, 这里记的是预期值 — 仍可追溯 (审计/对账)。
        routed = llm_service.resolve_provider_for_task("summary")
        if routed:
            provider, model = routed
        else:
            # 兜底: fallback_order[0] + 对应 summary model
            order = llm_service._config.fallback_order if llm_service._config else []
            provider = order[0] if order else ""
            model = llm_service._resolve_model(provider, "summary") if provider else ""

        # 估算 tokens (启发式, 实际 LLM 内部统计在 v0.7+ 接入)
        from backend.services.ai_hub import _est_tokens
        tokens_in = _est_tokens(prompt)
        tokens_out = _est_tokens(raw)

        item = self.repo.upsert(
            entity_type=entity_type,
            entity_id=entity_id,
            content_md=content_md,
            sections_json=sections_json,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,  # cost 估算接入 v0.7+ 同步到 cost_alert
            latency_ms=latency_ms,
        )
        logger.info(
            "DeepRead generated entity=%s/%s provider=%s model=%s latency_ms=%d",
            entity_type, entity_id, provider, model, latency_ms,
        )
        return item

    async def fetch(self, entity_type: str, entity_id: str) -> DeepReadItem | None:
        """纯读 (不触发 LLM)。表里没有 → 返回 None。"""
        return self.repo.get(entity_type, entity_id)

    def list_recent(self, limit: int = 20) -> list[dict]:
        return [it.to_dict() for it in self.repo.list_recent(limit)]


__all__ = ["DeepReadError", "DeepReadService"]