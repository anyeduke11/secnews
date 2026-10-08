"""DeepRead 深度分析面板服务 (Phase 4 S4-2)。

入口: ``DeepReadService.run(entity_type, entity_id, force=False)``.

行为:
- 表里已有 → 直接返回 (cache 命中, 不调 LLM)
- force=True 或不存在 → 按 entity_type 拉原文 → 按文章 category 选视角 →
  拼 prompt → 调 LLM → 解析动态分节 JSON → UPSERT deep_reads → 返回
- LLM 失败/解析失败 → 抛 ``DeepReadError``, **不写表** (避免半成品污染)

分节集合由 ``ai_hub.prompts.DEEP_READ_PROFILES`` 按 category 决定, 不再固定 4 节。
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
from backend.services.ai_hub.prompts import (
    DEEP_READ_PROFILE_VERSION,
    _build_deep_read_prompt,
    deep_read_sections,
)

# 走 model_router 的 HEAVY 档 (→ t3_summary → 有凭据的 provider)。
# 历史上本服务不传 task, 被 generate() 内部写死成 "summary" → FLASH 档 →
# 未运行的 ollama, 导致 deep_reads 表长期 0 行。
DEEP_READ_TASK = "deep_read"
# 输出上限: sensenova 实测约 80ms/token (推理已关) × provider 超时 90s 反推。
# v3 字数语义化 (要点速读 100~250 字) 后上调, 再高会在到达前被截断。
DEEP_READ_MAX_TOKENS = 1800
DEEP_READ_TEMPERATURE = 0.3


class DeepReadError(Exception):
    """DeepRead 流程失败 (LLM 调用 / 解析 / 原文缺失)。"""


# ── 分节解析 (按分类的动态节集合) ─────────────────────────


def _parse_raw_dict(raw: str) -> dict[str, Any] | None:
    """从 LLM 原始输出抽取 JSON dict (framework/headline/节键同居一层), 容错 fence。"""
    import re

    text = raw.strip()

    def _try(candidate: str) -> dict[str, Any] | None:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    parsed = _try(text)
    if parsed is not None:
        return parsed
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        parsed = _try(fence_match.group(1))
        if parsed is not None:
            return parsed
    if "{" in text and "}" in text:
        return _try(text[text.index("{"): text.rindex("}") + 1])
    return None


def _parse_sections_v3(
    raw: str, category: str | None
) -> tuple[dict[str, str], str, str]:
    """v3 解析: raw → (sections, framework, headline)。

    - framework 键合法 → 用 ``deep_read_sections(category, framework)`` 取节定义;
      非法/缺失 → 回落 profile 默认框架 (v2 行为), headline 空串。
    - 全部 JSON 解析失败 → 整段塞首节 (v2 fallback 语义保留)。
    """
    data = _parse_raw_dict(raw)
    framework = ""
    headline = ""
    if data is not None:
        fw_val = data.get("framework")
        if isinstance(fw_val, str) and fw_val.strip():
            framework = fw_val.strip()
        hl_val = data.get("headline")
        if isinstance(hl_val, str):
            headline = hl_val.strip()[:80]

    # framework 合法性由 deep_read_sections 内部回落保证 (非法值 → 默认框架)
    section_defs = deep_read_sections(category, framework or None)
    keys = [s["key"] for s in section_defs]

    if data is not None:
        return _normalize_sections(data, keys), framework, headline

    logger.warning(
        "DeepRead JSON 解析失败, fallback 到整段首节 (raw=%d 字符, 期望 %d 节)",
        len(raw), len(keys),
    )
    fallback = dict.fromkeys(keys, "")
    if keys:
        fallback[keys[0]] = raw[:1000]
    return fallback, framework, headline


def _normalize_sections(data: dict[str, Any], keys: list[str]) -> dict[str, str]:
    """统一各节为 str (LLM 可能返回 list / None / 多余键)。"""
    out: dict[str, str] = {}
    for key in keys:
        val = data.get(key, "")
        if val is None:
            val = ""
        elif isinstance(val, list):
            val = "\n".join(str(x) for x in val)
        else:
            val = str(val)
        out[key] = val.strip()
    return out


def _build_payload(
    category: str | None,
    sections: dict[str, str],
    framework: str = "",
    headline: str = "",
) -> tuple[str, str]:
    """分节 → (sections_json, content_md)。

    ``sections_json`` 自描述 (schema / category / profile_version / framework /
    headline / 有序 sections), 因此新增或调整分节**不需要数据库迁移** —— 迁移 075
    当初选 JSON 串就是为了这个。
    """
    defs = deep_read_sections(category, framework or None)
    ordered = [{**d, "body": sections.get(d["key"], "")} for d in defs]
    sections_json = json.dumps(
        {
            "schema": 1,
            "category": category or "general",
            "profile_version": DEEP_READ_PROFILE_VERSION,
            "framework": framework,
            "headline": headline,
            "sections": ordered,
        },
        ensure_ascii=False,
    )
    head = f"# {headline}\n\n" if headline else ""
    lines = [
        f"## {d['title']}\n\n{sections.get(d['key'], '').strip() or '_(本节暂无内容)_'}\n"
        for d in defs
    ]
    return sections_json, head + "\n".join(lines)


# ── DB 行 → 响应渲染 (治理 T3 review fix: 自 api 层下沉的纯逻辑) ──


# 旧行 (v1 envelope 之前的扁平 4 键) 的标题兜底, 保证历史缓存仍渲染出小标题
_LEGACY_SECTION_TITLES: dict[str, str] = {
    "summary": "摘要",
    "impact": "影响",
    "relations": "关联",
    "risks": "风险",
}


def build_sections(item_dict: dict[str, Any]) -> list[dict[str, str]]:
    """分节渲染源: 优先 v1 有序定义, 旧行回落扁平键 + 中文标题表。

    返回纯 dict 列表 (key/title/tone/body); pydantic response model 映射
    留在 api 层 — service 严禁反向 import backend.api。
    """
    defs = item_dict.get("section_defs") or []
    if isinstance(defs, list) and defs:
        out = []
        for d in defs:
            if not isinstance(d, dict) or not d.get("key"):
                continue
            out.append({
                "key": str(d["key"]),
                "title": str(d.get("title") or d["key"]),
                "tone": str(d.get("tone") or "mint"),
                "body": str(d.get("body") or ""),
            })
        if out:
            return out

    sections_raw = item_dict.get("sections") or {}
    if not isinstance(sections_raw, dict):
        return []
    return [
        {
            "key": str(k),
            "title": _LEGACY_SECTION_TITLES.get(str(k), str(k)),
            "body": str(v or ""),
        }
        for k, v in sections_raw.items()
    ]


def extract_envelope_meta(item_dict: dict[str, Any]) -> tuple[str, str]:
    """从 sections_json 提取 v3 envelope 元 (headline/framework); 旧报告返空串。"""
    try:
        data = json.loads(item_dict.get("sections_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return (
        str(data.get("headline") or "")[:80],
        str(data.get("framework") or ""),
    )


# ── 原文拉取 ──────────────────────────────────────────────────


def _fetch_source(entity_type: str, entity_id: str) -> tuple[str, dict[str, str]]:
    """按 entity_type 拉原文 (Markdown 优先)。失败抛 ``DeepReadError``。

    支持的 entity_type: hotspot / wiki / knowledge (DEV-0298)。
    - ``wiki``: entity_id 是 wiki 文件 path (v0.6 语义, 自动补 .md)
    - ``knowledge``: entity_id 是 knowledge_items.id (P4-1 统一检索锚点;
      同一行在 wiki 面叫 path, 在检索面叫 id — 本分支桥接两套语义)
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
        metadata["source"] = str(getattr(item, "source", "") or "")
        # category 决定视角 profile (persona / 专属节 / 原文预算)。
        # 兼容枚举与裸字符串两种落值形态。
        raw_cat = getattr(item, "category", None)
        metadata["category"] = str(getattr(raw_cat, "value", raw_cat) or "")
        # HotspotItem 字段探测: summary / content / body
        body = str(
            getattr(item, "summary", "")
            or getattr(item, "content", "")
            or getattr(item, "body", "")
            or ""
        )
        return body, metadata

    if entity_type == "knowledge":
        # P4-1 锚点: knowledge_items.id 直查 (get_item 按主键, 不做 .md 补全)
        item = KnowledgeRepo().get_item(entity_id)
        if item is None:
            raise DeepReadError(f"knowledge item not found: {entity_id}")
        topic = str(getattr(item, "topic", "") or "")
        metadata["title"] = str(getattr(item, "title", "") or entity_id)
        # DEV-0300: CVE 空壳条目 (topic 只有编号) → NVD 回源拼结构化简报,
        # category=cve 走漏洞通告 profile; 回源失败诚实拒绝 (不喂空壳幻觉)。
        from backend.services.cve_enrich_service import (
            compose_cve_brief,
            extract_cve_id,
            fetch_cve_facts,
            is_cve_shell,
        )

        if is_cve_shell(topic):
            cve_id = extract_cve_id(topic)
            facts = fetch_cve_facts(cve_id) if cve_id else None
            if not facts:
                raise DeepReadError(
                    f"CVE 空壳条目且 NVD 回源失败 ({cve_id}): 本地无事实, "
                    "拒绝以空原文生成深读 (防幻觉浪费算力)"
                )
            metadata["category"] = "cve"
            metadata["cve_id"] = cve_id or ""
            metadata["title"] = f"{cve_id} 漏洞情报 (NVD 回源)"
            return compose_cve_brief(facts), metadata
        metadata["category"] = str(getattr(item, "domain", "") or "")
        return topic, metadata

    if entity_type == "wiki":
        # DEV-0299: 原文真源 = llm-wiki-2.0/items/{id}.md 正文 (wiki-first 哲学;
        # knowledge_items 表无 content 列, 旧实现 getattr(item,'content') 恒空串
        # → wiki 深读一直拿空原文调 LLM)。entity_id 是 knowledge_items.id =
        # wiki 文件 stem (两侧 1:1 对账), 经 WikiFs 读 md 真身 + frontmatter。
        from backend.wiki_fs.root import resolve_wiki_root
        from backend.wiki_fs.store import WikiFs

        doc = WikiFs(resolve_wiki_root()).read_item(entity_id)
        if doc is None:
            raise DeepReadError(f"wiki item not found: {entity_id}")
        fm = doc.get("fm") or {}
        metadata["title"] = str(fm.get("title") or entity_id)
        metadata["category"] = str(fm.get("domain") or fm.get("category") or "")
        body = str(doc.get("body") or "")
        if not body.strip():
            raise DeepReadError(f"wiki item has empty body: {entity_id}")
        return body, metadata

    raise DeepReadError(
        f"unsupported entity_type: {entity_type} (supported: hotspot/wiki/knowledge)"
    )


# ── 入口 ──────────────────────────────────────────────────────


class DeepReadService:
    """DeepRead 分类型深度解读: hotspot / wiki 跨实体一致接口。

    分节集合由文章 category 决定 (见 ``ai_hub.prompts.DEEP_READ_PROFILES``)。
    """

    def __init__(self) -> None:
        self.repo = DeepReadRepository()

    async def run(
        self,
        entity_type: str,
        entity_id: str,
        force: bool = False,
        framework: str | None = None,
    ) -> DeepReadItem:
        """获取或生成 DeepRead。

        - force=False 且表里有 → 直接返回
        - 否则拉原文 → 按 category 选视角 → 调 LLM → 动态分节 → UPSERT
        - framework 非空且合法 (v3) → prompt 菜单收敛到该框架, LLM 按指定框架生成;
          空/None → 菜单全开, LLM 按内容自选
        """
        existing = self.repo.get(entity_type, entity_id)
        if existing is not None and not force:
            return existing

        body, metadata = _fetch_source(entity_type, entity_id)

        # 视角由文章分类决定; 取不到分类回落通用视角而不是失败。
        category = metadata.get("category") or None
        content = body if body else "(原文为空, 仅依据 ID 与类型生成)"
        prompt = _build_deep_read_prompt(category, metadata, content, framework=framework)

        # 调 LLM (走 ai_hub.LLMService.generate, 失败抛 DeepReadError)
        # 通过模块属性访问 (而非 from-import) 以保持测试 mock 生效。
        #
        # task 必须显式传 "deep_read": 历史上 generate() 内部写死 "summary",
        # 会被 model_router 分到 FLASH 档 → t3_chunk_summary → 未运行的 ollama,
        # 于是深度阅读从未成功过 (deep_reads 表 0 行)。
        # max_tokens / temperature 同样只能由调用方给 —— TaskOverride 里这两个值
        # 今天不下发到请求体。上限按 sensenova 实测吞吐 (~80ms/token, 推理已关)
        # 与 90s provider 超时反推, 再高会被截断。
        llm_service = _ai_hub_mod.llm_service
        t0 = time.monotonic()
        raw = await llm_service.generate(
            prompt,
            task=DEEP_READ_TASK,
            max_tokens=DEEP_READ_MAX_TOKENS,
            temperature=DEEP_READ_TEMPERATURE,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        if not raw or not raw.strip():
            raise DeepReadError(
                f"LLM 返回空 (entity={entity_type}/{entity_id}); 可能所有 provider 不可用"
            )

        sections, framework, headline = _parse_sections_v3(raw, category)
        sections_json, content_md = _build_payload(category, sections, framework, headline)

        # provider/model 记账: generate() 内部不暴露, 用 router 推荐 + 当前 model 推导。
        # 必须用**同一个** DEEP_READ_TASK 查询, 否则记下来的 provider/model 与实际
        # 跑的那条链不是一条 (历史上这里写死 "summary", 记的是 FLASH 档)。
        routed = llm_service.resolve_provider_for_task(DEEP_READ_TASK)
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


__all__ = ["DeepReadError", "DeepReadService", "build_sections", "extract_envelope_meta"]