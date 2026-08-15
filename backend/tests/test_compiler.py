"""Compiler service tests — 背压创建 + P0 消费策略 (自动消费者 + 存量归档).

覆盖:
- detect_stale_items: v1.7 后 compiled 语义 (kl:structure/kl:publish 视为已编译)
  + 每日配额 (最旧优先)
- create_compile_task: 批量拆任务 + pending 队列去重
- consume_compile_tasks: 自动消费者 (规则式编译) — 配额 / 分类写回 md+DB /
  lifecycle 流转 / 概念关联 / done 文件落盘
- archive_stale_compile_tasks: 存量积压归档 — 状态流转 + 文件移动 + 幂等
- consume_compile_tasks_job: scheduler job 装配冒烟

所有测试用 tmp_path 隔离 DB 与 knowledge/ 目录, 不触碰真实
backend/hotspot.db 与 knowledge/items/。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository import db
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def compile_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """隔离 DB (tmp_path/test.db) + 把 compiler/knowledge_sync 的目录常量
    全部重定向到 tmp_path。

    同时把 map_updater.MAP_PATH 指向 tmp 文件, 让消费后的 _MAP 更新落盘
    到隔离位置而不是真实 knowledge/_MAP.md。不依赖 conftest 的共享
    temp_db fixture (该 fixture 把 db_path 设为 str, 与 get_connection
    的 Path 用法不兼容 — 各 DB 测试文件均自行定义本地 temp_db)。
    """
    from backend.config import config

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)  # 必须是 Path
    db.close_db()
    db.init_db()

    import backend.services.compiler as compiler
    from backend.services import map_updater

    pending = tmp_path / "tasks" / "pending"
    done = tmp_path / "tasks" / "done"
    failed = tmp_path / "tasks" / "failed"
    items = tmp_path / "items"
    for d in (pending, done, failed, items):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(compiler, "PENDING_DIR", pending)
    monkeypatch.setattr(compiler, "DONE_DIR", done)
    monkeypatch.setattr(compiler, "FAILED_DIR", failed)
    monkeypatch.setattr(knowledge_sync, "ITEMS_DIR", items)
    monkeypatch.setattr(map_updater, "MAP_PATH", tmp_path / "MAP.md")

    yield {
        "compiler": compiler,
        "pending": pending,
        "done": done,
        "failed": failed,
        "items": items,
        "map_path": tmp_path / "MAP.md",
    }
    db.close_db()


def _make_item(
    item_id: str,
    title: str,
    tags: list[str] | None = None,
    lifecycle: str = "kl:link",
    source_url: str = "https://example.com",
    updated_at: str | None = None,
) -> KnowledgeItem:
    """写入一个 knowledge item (DB + md 文件)。"""
    item = KnowledgeItem(
        id=item_id,
        title=title,
        source="test",
        source_url=source_url,
        tags=tags or [],
        lifecycle=lifecycle,
        ingested_at=now_iso(),
        updated_at=updated_at or now_iso(),
    )
    knowledge_repo.upsert_item(item)
    knowledge_sync.write_item_to_md(item.to_dict())
    return item


def _make_task(env, item_ids: list[str], age_days: int = 0, task_type: str = "compile"):
    """创建任务 (DB + pending 文件), 可选回拨 created_at 模拟积压。

    Returns: KnowledgeTask
    """
    task = knowledge_repo.create_task(task_type, {"item_ids": item_ids})
    (env["pending"] / f"task-{task.id}.md").write_text(
        f"""---
task_type: "{task_type}"
status: "pending"
created_at: "{task.created_at}"
params:
  item_ids: {item_ids}
---

# 编译任务
""",
        encoding="utf-8",
    )
    if age_days:
        old = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        conn = db.get_connection()
        conn.execute(
            "UPDATE knowledge_tasks SET created_at = ? WHERE id = ?",
            (old, task.id),
        )
        task.created_at = old
    return task


# ---------------------------------------------------------------------------
# detect_stale_items — compiled 语义 + 配额
# ---------------------------------------------------------------------------

class TestDetectStaleItems:
    def test_kl_structure_publish_are_compiled(self, compile_env):
        """v1.7 后: kl:structure / kl:publish / generate 不再视为 stale。"""
        _make_item("s1", "已结构化", lifecycle="kl:structure")
        _make_item("p1", "已发布", lifecycle="kl:publish")
        _make_item("g1", "已编译(legacy)", lifecycle="generate")

        result = compile_env["compiler"].detect_stale_items(limit=100)
        assert "s1" not in result["stale_items"]
        assert "p1" not in result["stale_items"]
        assert "g1" not in result["stale_items"]

    def test_kl_link_and_legacy_signal_are_stale(self, compile_env):
        _make_item("l1", "待编译", lifecycle="kl:link")
        _make_item("sig1", "legacy 信号", lifecycle="signal")
        _make_item("raw1", "原始", lifecycle="kl:raw")

        result = compile_env["compiler"].detect_stale_items(limit=100)
        stale = set(result["stale_items"])
        assert {"l1", "sig1", "raw1"} <= stale
        assert result["reasons"]["l1"] == "compiled=false"

    def test_quota_oldest_first(self, compile_env):
        """配额只返回最旧 limit 条 (按 updated_at 最旧优先)。"""
        for i in range(5):
            _make_item(
                f"q{i}", f"stale item {i}", lifecycle="kl:link",
                updated_at=f"2026-07-0{i + 1}T00:00:00+00:00",
            )
        result = compile_env["compiler"].detect_stale_items(limit=2)
        assert len(result["stale_items"]) == 2
        assert result["stale_items"] == ["q0", "q1"]  # 最旧两条

    def test_limit_zero_returns_all(self, compile_env):
        for i in range(3):
            _make_item(f"z{i}", f"item {i}", lifecycle="kl:link")
        result = compile_env["compiler"].detect_stale_items(limit=0)
        assert len(result["stale_items"]) == 3


# ---------------------------------------------------------------------------
# create_compile_task — 批量拆任务 + 去重
# ---------------------------------------------------------------------------

class TestCreateCompileTask:
    def test_batch_split_into_multiple_tasks(self, compile_env):
        ids = [f"i{i}" for i in range(12)]  # 12 > COMPILE_BATCH_SIZE=10
        result = compile_env["compiler"].create_compile_task(ids)
        assert result["total_tasks"] == 2
        assert result["items_to_compile"] == 12
        assert len(list(compile_env["pending"].glob("task-*.md"))) == 2

    def test_dedup_skips_already_pending(self, compile_env):
        ids = ["a1", "a2"]
        first = compile_env["compiler"].create_compile_task(ids)
        assert first["status"] == "pending"
        second = compile_env["compiler"].create_compile_task(ids)
        assert second["status"] == "no_items"
        assert second["skipped_duplicates"] == 2

    def test_empty_returns_no_items(self, compile_env):
        result = compile_env["compiler"].create_compile_task([])
        assert result["status"] == "no_items"


# ---------------------------------------------------------------------------
# consume_compile_tasks — 自动消费者
# ---------------------------------------------------------------------------

class TestConsumeCompileTasks:
    def test_quota_leaves_remaining_pending(self, compile_env):
        """配额 2: 只消费 2 个任务, 第 3 个保持 pending。"""
        _make_item("a1", "AI Agent 入门", tags=["Agent"])
        _make_item("a2", "渗透测试实战", tags=["安全技术"])
        _make_item("a3", "金融科技观察", tags=["金融科技"])
        _make_task(compile_env, ["a1"], age_days=3)
        _make_task(compile_env, ["a2"], age_days=2)
        _make_task(compile_env, ["a3"], age_days=1)

        result = compile_env["compiler"].consume_compile_tasks(limit_items=2)
        assert result["processed_tasks"] == 2
        assert result["items_consumed"] == 2

        done_tasks = knowledge_repo.list_tasks(status="done")
        pending = knowledge_repo.list_tasks(status="pending")
        assert len(done_tasks) == 2
        assert len(pending) == 1
        assert pending[0].params["item_ids"] == ["a3"]  # 最旧的先消费, 留下最新

        # 再次消费: 剩余任务被处理, 队列清空
        result2 = compile_env["compiler"].consume_compile_tasks(limit_items=10)
        assert result2["processed_tasks"] == 1
        assert len(knowledge_repo.list_tasks(status="pending")) == 0

    def test_classifies_and_advances_lifecycle(self, compile_env):
        """分类写回 md + DB; kl:link → kl:structure; 概念关联。"""
        _make_item("b1", "AI Agent 入门教程", tags=["Agent", "教程实操"])
        _make_task(compile_env, ["b1"])
        result = compile_env["compiler"].consume_compile_tasks(limit_items=10)
        assert result["processed_tasks"] == 1
        detail = result["details"][0]
        assert detail["classified"] == 1
        assert detail["lifecycle_advanced"] == 1

        # md (真相源) 已更新
        fm = knowledge_sync.parse_frontmatter(compile_env["items"] / "b1.md")
        assert fm["domain"] == "ai"
        assert fm["type"] == "tutorial"
        assert fm["difficulty"] == "beginner"
        assert fm["lifecycle"] == "kl:structure"

        # DB 已同步
        item = knowledge_repo.get_item("b1")
        assert item.domain == "ai"
        assert item.lifecycle == "kl:structure"
        assert "ai-agent" in item.concepts  # concept_linker 映射

        # done 文件落盘, pending 文件移除, _MAP 已重建
        done_files = list(compile_env["done"].glob("task-*.md"))
        assert len(done_files) == 1
        done_text = done_files[0].read_text(encoding="utf-8")
        assert 'status: "done"' in done_text
        assert "executor: auto-consumer" in done_text
        assert not list(compile_env["pending"].glob("task-*.md"))
        assert compile_env["map_path"].exists()

    def test_unclassifiable_item_still_completes(self, compile_env):
        """无规则命中的条目也推进 lifecycle 并完成 (避免无限重新入队)。"""
        _make_item("c1", "https://example.com/no-keywords", tags=["未知标签"])
        _make_task(compile_env, ["c1"])
        result = compile_env["compiler"].consume_compile_tasks(limit_items=10)
        assert result["processed_tasks"] == 1
        assert result["details"][0]["classified"] == 0
        assert result["details"][0]["lifecycle_advanced"] == 1

        item = knowledge_repo.get_item("c1")
        assert item.domain is None
        assert item.lifecycle == "kl:structure"  # 推进, 不再被 detect 重新入队

        # 稳定性: 再跑一次 detect + consume, 队列不复活
        stale = compile_env["compiler"].detect_stale_items(limit=100)
        assert "c1" not in stale["stale_items"]

    def test_legacy_signal_advances_to_structure(self, compile_env):
        """P1-3: legacy signal 条目推进到 kl:structure (原 generate/compiled)。"""
        _make_item("d1", "安全漏洞分析", tags=["漏洞管理"], lifecycle="signal")
        _make_task(compile_env, ["d1"])
        compile_env["compiler"].consume_compile_tasks(limit_items=10)
        item = knowledge_repo.get_item("d1")
        assert item.lifecycle == "kl:structure"
        assert item.compiled is False  # structure 未发布, compiled 语义保留在 publish

    def test_missing_item_does_not_crash(self, compile_env):
        """任务引用的条目已不存在: 任务仍标记 done, missing 计数。"""
        _make_task(compile_env, ["ghost-id"])
        result = compile_env["compiler"].consume_compile_tasks(limit_items=10)
        assert result["processed_tasks"] == 1
        assert result["details"][0]["missing"] == 1
        assert knowledge_repo.get_task(result["details"][0]["task_id"])["status"] == "done"

    def test_kl_raw_not_advanced(self, compile_env):
        """kl:raw / kl:refine 只分类, 不越级推进 lifecycle (留给 KL 状态机)。"""
        _make_item("r1", "大模型综述", tags=["大模型进展"], lifecycle="kl:raw")
        _make_task(compile_env, ["r1"])
        compile_env["compiler"].consume_compile_tasks(limit_items=10)
        item = knowledge_repo.get_item("r1")
        assert item.domain == "ai"  # 分类完成
        assert item.lifecycle == "kl:raw"  # 状态不变


# ---------------------------------------------------------------------------
# archive_stale_compile_tasks — 存量积压归档
# ---------------------------------------------------------------------------

class TestArchiveStaleCompileTasks:
    def test_archives_old_backlog_keeps_fresh(self, compile_env):
        """30 天前的积压任务 → failed + 文件移入 failed/; 新任务保留。"""
        _make_item("e1", "条目1", tags=["Agent"])
        _make_item("e2", "条目2", tags=["安全技术"])
        _make_item("e3", "条目3", tags=["金融科技"])
        old1 = _make_task(compile_env, ["e1"], age_days=30)
        old2 = _make_task(compile_env, ["e2"], age_days=20)
        fresh = _make_task(compile_env, ["e3"], age_days=1)

        result = compile_env["compiler"].archive_stale_compile_tasks(max_age_days=7)
        assert result["archived"] == 2
        assert result["kept"] == 1
        assert result["total"] == 3
        assert "superseded" in result["reason"]

        # DB 状态流转
        assert knowledge_repo.get_task(old1.id)["status"] == "failed"
        assert knowledge_repo.get_task(old2.id)["status"] == "failed"
        assert knowledge_repo.get_task(fresh.id)["status"] == "pending"
        assert "superseded" in knowledge_repo.get_task(old1.id)["error_message"]

        # 文件移动 + failed 前标记
        assert (compile_env["failed"] / f"task-{old1.id}.md").exists()
        assert not (compile_env["pending"] / f"task-{old1.id}.md").exists()
        failed_text = (compile_env["failed"] / f"task-{old1.id}.md").read_text(encoding="utf-8")
        assert 'status: "failed"' in failed_text
        assert "reason:" in failed_text and "failed_at:" in failed_text
        assert (compile_env["pending"] / f"task-{fresh.id}.md").exists()

    def test_idempotent(self, compile_env):
        """已归档任务不再匹配, 重复执行无副作用。"""
        _make_item("f1", "条目", tags=["Agent"])
        old = _make_task(compile_env, ["f1"], age_days=30)
        compile_env["compiler"].archive_stale_compile_tasks(max_age_days=7)
        result = compile_env["compiler"].archive_stale_compile_tasks(max_age_days=7)
        assert result["archived"] == 0
        assert result["kept"] == 0  # 已无 pending compile 任务
        assert knowledge_repo.get_task(old.id)["status"] == "failed"

    def test_keep_recent_protects_newest(self, compile_env):
        """keep_recent=N: 最新 N 条无论如何保留 (即使已超龄)。"""
        _make_item("g1", "条目1", tags=["Agent"])
        _make_item("g2", "条目2", tags=["安全技术"])
        _make_task(compile_env, ["g1"], age_days=30)
        _make_task(compile_env, ["g2"], age_days=25)

        result = compile_env["compiler"].archive_stale_compile_tasks(
            max_age_days=None, keep_recent=1
        )
        assert result["archived"] == 1
        assert result["kept"] == 1
        # 保留的是最新的 task (g2)
        pending = knowledge_repo.list_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0].params["item_ids"] == ["g2"]

    def test_only_compile_tasks_archived(self, compile_env):
        """非 compile 任务不受影响。"""
        _make_task(compile_env, ["h1"], age_days=30, task_type="generate_soul")
        result = compile_env["compiler"].archive_stale_compile_tasks(max_age_days=7)
        assert result["archived"] == 0
        assert result["kept"] == 0  # compile 任务为空
        assert knowledge_repo.list_tasks(status="pending")[0].task_type == "generate_soul"


# ---------------------------------------------------------------------------
# consume_compile_tasks_job — scheduler 装配冒烟
# ---------------------------------------------------------------------------

class TestConsumeCompileTasksJob:
    def test_job_consumes_within_quota(self, compile_env):
        """job 装配: 配额内任务全部被消费 (含积压任务 — 先消费后归档),
        归档步骤对剩余积压兜底, 全程不抛异常。"""
        from backend.scheduler.jobs import consume_compile_tasks_job

        _make_item("j1", "AI Agent", tags=["Agent"])
        _make_item("j2", "渗透测试", tags=["安全技术"])
        _make_task(compile_env, ["j1"])  # 新任务
        _make_task(compile_env, ["j2"], age_days=30)  # 积压任务 (配额内被消费)

        asyncio.run(consume_compile_tasks_job())

        done = knowledge_repo.list_tasks(status="done")
        failed = knowledge_repo.list_tasks(status="failed")
        # 两个任务都在 100-item 配额内 → 全部被规则式消费, 无归档
        assert len(done) == 2
        assert len(failed) == 0
        assert {d.params["item_ids"][0] for d in done} == {"j1", "j2"}
