"""Knowledge domain models for v1.4 knowledge dashboard.

v1.7 Phase 1: ``compiled`` 字段被 ``lifecycle`` (SAG 生命周期) 替换.
为保持向后兼容 (compiler.py / soul_service.py / 前端仍引用 compiled),
``compiled`` 作为只读 property 保留, 值由 lifecycle 派生:
  lifecycle == 'generate' → compiled=True, 否则 False.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 知识条目生命周期合法状态 (v1.7 SAG + P1-3 KL 统一)
# P1-3 (2026-08-15): 系统存在两套生命周期 — SAG (signal/amplify:*/generate)
# 与 KL 五阶段 (kl:raw/refine/link/structure/publish)。统一以 **KL 五阶段为
# 规范**, legacy SAG 值保留为兼容 (历史数据/外部调用), 新写入一律用 kl:*。
# 映射关系:
#   signal            → kl:raw        (刚被发现)
#   amplify:tagged    → kl:refine     (已打标签)
#   amplify:linked    → kl:link       (已关联概念)
#   amplify:complete  → kl:structure  (已完成结构化)
#   generate          → kl:publish    (已发布知识)
VALID_LIFECYCLE_STATES = {
    # --- KL 五阶段 (唯一规范, P1.5 单轨化; legacy SAG 值已全部迁移) ---
    "kl:raw",         # 原始入库 (从 hotspots / 收藏导入)
    "kl:refine",      # 评分 + tag 完成
    "kl:link",        # 实体关联完成
    "kl:structure",   # 摘要 + 结构化完成
    "kl:publish",     # 已发布
}

# P1-3: legacy SAG → KL 归一映射 (P1.5 单轨化后保留作防御性读取; 不参与写)
LEGACY_TO_KL = {
    "signal": "kl:raw",
    "amplify:tagged": "kl:refine",
    "amplify:linked": "kl:link",
    "amplify:complete": "kl:structure",
    "generate": "kl:publish",
}


def normalize_lifecycle(value: str | None) -> str:
    """P1-3: 把任意 lifecycle 值归一为 KL 五阶段规范值。

    - kl:* 值原样返回
    - legacy SAG 值映射为对应 kl:*
    - 未知值返回 'kl:raw'
    """
    if value is None:
        return "kl:raw"
    if value in LEGACY_TO_KL:
        return LEGACY_TO_KL[value]
    if isinstance(value, str) and value.startswith("kl:"):
        return value
    return "kl:raw"


@dataclass
class KnowledgeItem:
    """Mirrors knowledge/items/{hash}.md frontmatter."""
    id: str
    title: str
    source: str  # cubox | bookmark | secnews | secnews_archive
    source_url: str | None = None
    domain: str | None = None
    topic: str | None = None
    type: str | None = None  # news | analysis | paper | tutorial | tool | opinion
    difficulty: str | None = None  # beginner | intermediate | advanced | expert
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    mastery: int = 0
    # v1.7: lifecycle 替换 compiled; news_type + tech_stack 新增
    # P1-3: 默认值统一为 KL 规范 kl:raw
    lifecycle: str = "kl:raw"
    news_type: str | None = None
    tech_stack: list[str] = field(default_factory=list)
    ingested_at: str = ""
    updated_at: str = ""

    # ---- v1.7 向后兼容: compiled 从 lifecycle 派生 ----
    @property
    def compiled(self) -> bool:
        """lifecycle 为 generate 或 kl:publish 视为已编译 (P1-3 统一后兼容)."""
        return self.lifecycle in ("generate", "kl:publish")

    @compiled.setter
    def compiled(self, value: bool) -> None:
        """允许旧代码 ``item.compiled = True`` 设置 lifecycle."""
        self.lifecycle = "kl:publish" if value else "kl:raw"

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeItem":
        import json
        # v1.7: 优先读 lifecycle, 旧行回退到 compiled (P1-3: 新值用 kl:* 规范;
        # 但读取不归一 legacy 值 — 下游 (compiler 等) 仍按旧值做兼容判断)
        lifecycle = row.get("lifecycle")
        if not lifecycle:
            lifecycle = "kl:publish" if bool(row.get("compiled", 0)) else "kl:raw"
        return cls(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            source_url=row.get("source_url"),
            domain=row.get("domain"),
            topic=row.get("topic"),
            type=row.get("type"),
            difficulty=row.get("difficulty"),
            tags=json.loads(row["tags"]) if row.get("tags") else [],
            concepts=json.loads(row["concepts"]) if row.get("concepts") else [],
            mastery=row.get("mastery", 0),
            lifecycle=lifecycle,
            news_type=row.get("news_type") or None,
            tech_stack=json.loads(row["tech_stack"]) if row.get("tech_stack") else [],
            ingested_at=row["ingested_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "domain": self.domain,
            "topic": self.topic,
            "type": self.type,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "concepts": self.concepts,
            "mastery": self.mastery,
            # v1.7: 同时输出 compiled (兼容) 和 lifecycle (新)
            "compiled": self.compiled,
            "lifecycle": self.lifecycle,
            "news_type": self.news_type,
            "tech_stack": self.tech_stack,
            "ingested_at": self.ingested_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeConcept:
    """Mirrors knowledge/concepts/{slug}.md frontmatter.

    v0.4.0 收尾: 增加 entity_type / external_id / external_ref — security↔
    knowledge 实体统一命名空间的互引字段 (concept 指向 security_entity)。
    """
    slug: str
    title: str
    domain: str | None = None
    source_items: list[str] = field(default_factory=list)
    local_wiki_ref: str | None = None
    updated_at: str = ""
    entity_type: str | None = None
    external_id: str | None = None
    external_ref: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeConcept":
        import json
        return cls(
            slug=row["slug"],
            title=row["title"],
            domain=row.get("domain"),
            source_items=json.loads(row["source_items"]) if row.get("source_items") else [],
            local_wiki_ref=row.get("local_wiki_ref"),
            updated_at=row["updated_at"],
            entity_type=row.get("entity_type"),
            external_id=row.get("external_id"),
            external_ref=row.get("external_ref"),
        )

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "domain": self.domain,
            "source_items": self.source_items,
            "local_wiki_ref": self.local_wiki_ref,
            "updated_at": self.updated_at,
            "entity_type": self.entity_type,
            "external_id": self.external_id,
            "external_ref": self.external_ref,
        }


@dataclass
class KnowledgeTask:
    """Task queue item."""
    id: int
    task_type: str
    status: str = "pending"
    params: dict | None = None
    result_path: str | None = None
    error_message: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "KnowledgeTask":
        import json
        return cls(
            id=row["id"],
            task_type=row["task_type"],
            status=row["status"],
            params=json.loads(row["params"]) if row.get("params") else None,
            result_path=row.get("result_path"),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status,
            "params": self.params,
            "result_path": self.result_path,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
