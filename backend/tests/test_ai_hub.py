"""ai_hub — 知识写回唯一门面 (v0.5 §18.2 强约束 1)。

覆盖:
- write_item: md 落盘 + wiki_events 留痕 (kind=agent_write)
- write_item: 遥测失败不阻塞写路径 (md 成功即成功)
- update_frontmatter: concepts 回填 + 留痕; md 失败返回 False 且不留痕
- knowledge_sync 增量同步留痕 (sync_item), full_sync 批量静默 (无噪音)

业务意图: db_trace 反查链路依赖 wiki_events 完整性 — 每次知识写回
必须可追溯产生者 (agent 标识); 全量索引重建不是知识事件, 不该污染遥测。
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.domain.knowledge_models import now_iso
from backend.repository import db
from backend.services import ai_hub, knowledge_sync


@pytest.fixture
def temp_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """独立 DB + 重定向 items/concepts 目录到 tmp_path。"""
    test_db = tmp_path / "test_aihub.db"
    monkeypatch.setattr(config, "db_path", test_db)
    items_dir = tmp_path / "items"
    concepts_dir = tmp_path / "concepts"
    items_dir.mkdir()
    concepts_dir.mkdir()
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", items_dir)
    monkeypatch.setattr(knowledge_sync, "CONCEPTS_DIR", concepts_dir)
    # ai_hub.update_frontmatter 用 KNOWLEDGE_DIR 拼路径 — 一并重定向
    monkeypatch.setattr(knowledge_sync, "KNOWLEDGE_DIR", tmp_path)
    db.close_db()
    db.init_db()
    yield {"root": tmp_path, "items": items_dir, "concepts": concepts_dir}
    db.close_db()


def _events(conn, wiki_path: str | None = None) -> list:
    sql = "SELECT kind, wiki_path, db_table, db_row_id, agent FROM wiki_events"
    if wiki_path:
        sql += f" WHERE wiki_path = '{wiki_path}'"
    return [dict(r) for r in conn.execute(sql + " ORDER BY id").fetchall()]


class TestWriteItem:
    def test_writes_md_and_logs_event(self, temp_env):
        """write_item 落盘 items/{id}.md 并在 wiki_events 留 agent_write 痕。"""
        ai_hub.write_item(
            {"id": "a1", "title": "T", "source": "test",
             "ingested_at": now_iso(), "updated_at": now_iso()},
            agent="api:patch_item",
        )
        md = temp_env["items"] / "a1.md"
        assert md.exists() and 'id: "a1"' in md.read_text(encoding="utf-8")

        from backend.repository.db import get_connection
        rows = _events(get_connection(), "items/a1.md")
        assert len(rows) == 1
        assert rows[0]["kind"] == "agent_write"
        assert rows[0]["db_table"] == "knowledge_items"
        assert rows[0]["db_row_id"] == "a1"
        assert rows[0]["agent"] == "api:patch_item"

    def test_telemetry_failure_does_not_block_write(self, temp_env, monkeypatch):
        """wiki_events 写失败只降级 — md 必须落盘 (真相源优先)。"""
        from backend.repository import wiki_event_repo

        def _boom(*a, **kw):
            raise RuntimeError("db locked")

        monkeypatch.setattr(wiki_event_repo.WikiEventRepo, "log", _boom)
        ai_hub.write_item(
            {"id": "a2", "title": "T", "source": "test",
             "ingested_at": now_iso(), "updated_at": now_iso()},
        )
        assert (temp_env["items"] / "a2.md").exists()


class TestUpdateFrontmatter:
    def test_updates_and_logs(self, temp_env):
        """update_frontmatter 就地改字段并留痕 (federation 回填场景)。"""
        p = temp_env["concepts"] / "c1.md"
        p.write_text("---\nslug: \"c1\"\ntitle: \"C\"\n---\n\nbody\n",
                     encoding="utf-8")
        ok = ai_hub.update_frontmatter(
            "concepts/c1.md", "local_wiki_ref", "wiki:local:concepts/c1",
            agent="svc:federation_backfill",
        )
        assert ok
        assert 'local_wiki_ref: "wiki:local:concepts/c1"' in p.read_text(encoding="utf-8")

        from backend.repository.db import get_connection
        rows = _events(get_connection(), "concepts/c1.md")
        assert len(rows) == 1 and rows[0]["agent"] == "svc:federation_backfill"

    def test_md_failure_returns_false_no_event(self, temp_env):
        """md 更新失败返回 False 且不留痕 (事件与事实一致)。"""
        ok = ai_hub.update_frontmatter("concepts/ghost.md", "k", "v")
        assert ok is False

        from backend.repository.db import get_connection
        assert _events(get_connection()) == []


class TestSyncEvents:
    def test_incremental_sync_logs_bulk_silent(self, temp_env, monkeypatch):
        """watcher 单文件同步留 sync_item 痕; full_sync 批量重建不留痕。"""
        # 准备一个 item md → 单文件增量同步应留痕
        (temp_env["items"] / "s1.md").write_text(
            "---\nid: \"s1\"\ntitle: \"S\"\nsource: \"test\"\n---\n\nbody\n",
            encoding="utf-8",
        )
        knowledge_sync.sync_item_to_db(temp_env["items"] / "s1.md")

        from backend.repository.db import get_connection
        rows = [r for r in _events(get_connection())
                if r["kind"] == "sync_item"]
        assert len(rows) == 1 and rows[0]["agent"] == "watcher"

        # full_sync 全量重建 → 静默 (不追加新事件)
        before = len(_events(get_connection()))
        count = knowledge_sync.full_sync_items_to_db()
        assert count >= 1
        after = len(_events(get_connection()))
        assert after == before, "full_sync must not pollute wiki_events"
