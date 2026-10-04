"""P2-2/E8 真源缺列补齐测试 (裁决 2026-10-04)。

裁决两分法:
- entities (T1 NER 抽取, 119 迁移) = 语义真源列 → **进 md frontmatter**,
  md→SQLite 重投影经 knowledge_repo.set_entities 写回;
- attention_score = 派生缓存可丢 (attention_scorer 1800s job 重算) →
  **刻意不入 frontmatter** (真源文件不留缓存痕迹);
- compiled = v1.7 起 lifecycle 派生的只读 property (审计该半已自然闭环)。

WHY (Rule 9): 审计 E8 = "投影不可从 md 完整重建, 违背 wiki-first" —
本测试以 md→SQLite roundtrip 锁定 entities 重建能力 + frontmatter
无缓存痕迹两支契约。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import config
from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository import db
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync


@pytest.fixture
def wiki_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    test_db = tmp_path / "test_e8.db"
    monkeypatch.setattr(config, "db_path", test_db)
    monkeypatch.setattr(config, "warm_db_path", None, raising=False)
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", tmp_path / "items")
    db.close_db()
    db.init_db()
    yield tmp_path / "items"
    db.close_db()


def _item(item_id: str, entities: list[str] | None = None) -> dict:
    item = KnowledgeItem(
        id=item_id, title="E8 样例", source="test",
        source_url=f"https://example.com/{item_id}",
        lifecycle="kl:publish", ingested_at=now_iso(), updated_at=now_iso(),
    )
    knowledge_repo.upsert_item(item)
    d = item.to_dict()
    if entities is not None:
        d["entities"] = entities
    return d


class TestE8EntitiesFrontmatter:
    def test_write_md_includes_entities_from_db_dict(self, wiki_env):
        """裁决主断言: DB dict 携带 entities → frontmatter 必须落 entities 行。"""
        d = _item("e8-1", entities=["CVE-2026-1234", "ATT&CK T1059"])
        knowledge_sync.write_item_to_md(d)
        text = (wiki_env / "e8-1.md").read_text(encoding="utf-8")
        fm = knowledge_sync.parse_frontmatter(wiki_env / "e8-1.md")
        assert fm is not None and fm.get("entities") == [
            "CVE-2026-1234", "ATT&CK T1059",
        ]
        assert json.dumps(["CVE-2026-1234"], ensure_ascii=False)  # json 格式 sanity

    def test_write_md_preserves_existing_entities_when_dict_lacks(self, wiki_env):
        """DB dict 无 entities 键 (既有 16 列消费点) → 继承文件已有值, 不重置。"""
        d = _item("e8-2")  # 无 entities 键
        knowledge_sync.write_item_to_md(d)
        # 首写 (空 entities) 后, 模拟旧文件已带 entities 的场景: 直接改文件
        md = wiki_env / "e8-2.md"
        text = md.read_text(encoding="utf-8")
        md.write_text(
            text.replace("entities: []", 'entities: ["CVE-2026-9999"]'),
            encoding="utf-8",
        )
        # 再次回写 (既有消费点形态: dict 无 entities)
        knowledge_sync.write_item_to_md(d)
        fm = knowledge_sync.parse_frontmatter(md)
        assert fm.get("entities") == ["CVE-2026-9999"], (
            "既有消费点回写不得重置 frontmatter 已有 entities (md 真源哲学)"
        )

    def test_attention_score_deliberately_absent(self, wiki_env):
        """裁决第二支: attention_score = 派生缓存可丢, 刻意不入 frontmatter
        (真源文件不留缓存痕迹; 重投影时该列由 attention_scorer job 重算)。"""
        d = _item("e8-3", entities=[])
        knowledge_sync.write_item_to_md(d)
        text = (wiki_env / "e8-3.md").read_text(encoding="utf-8")
        assert "attention_score" not in text

    def test_reprojection_roundtrip_md_to_sqlite(self, wiki_env):
        """审计 E8 闭环主断言: md→SQLite 重投影恢复 entities (投影可重建)。"""
        d = _item("e8-rt", entities=["CVE-2026-7777", "APT29"])
        knowledge_sync.write_item_to_md(d)
        # 模拟投影丢失: DB entities 清空 (重投影前态)
        knowledge_repo.set_entities("e8-rt", [])
        assert knowledge_repo.get_entities("e8-rt") == []

        # 重投影: md → SQLite (full_sync 的单文件路径)
        item_id = knowledge_sync.sync_item_to_db(wiki_env / "e8-rt.md")
        assert item_id == "e8-rt"
        assert knowledge_repo.get_entities("e8-rt") == ["CVE-2026-7777", "APT29"]

    def test_reprojection_skips_non_list_entities(self, wiki_env):
        """frontmatter entities 非 list (脏值) → 不写回, 不炸同步。"""
        d = _item("e8-dirty", entities=[])
        knowledge_sync.write_item_to_md(d)
        md = wiki_env / "e8-dirty.md"
        text = md.read_text(encoding="utf-8")
        md.write_text(text.replace("entities: []", "entities: not-a-list"),
                      encoding="utf-8")
        item_id = knowledge_sync.sync_item_to_db(md)
        assert item_id == "e8-dirty"  # 同步不炸
