"""M3.5 wiki_archiver + retention_engine 单元测试 (无 DB)。

覆盖 SPEC §18 验收:
- retention: 7 天 1.0→0.9, 30 天≈0.7, access 重置
- wiki_archiver: 原子写 + 幂等 + retention entry 自动建
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ── retention_engine ───────────────────────────────────────────
class TestDecayScore:
    """§18 Ebbinghaus 公式: initial * 0.9 ^ (days / 7)。"""

    def test_decay_zero_days_returns_initial(self):
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, 0) == 1.0

    def test_decay_seven_days_is_0_9(self):
        """7 天衰减后 = 1.0 * 0.9 = 0.9 (SPEC: 7 天 1.0→0.9)。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, 7) == pytest.approx(0.9, abs=0.001)

    def test_decay_thirty_days_is_about_0_64(self):
        """30 天衰减: 1.0 * 0.9 ^ (30/7) ≈ 0.637。

        注: SPEC §18 文字「30 天≈0.7」是用户口径的「约 70%」近似,
        实际公式结果 (0.9 ^ 4.286) ≈ 0.64 — 这就是真实衰减曲线。
        测试以公式结果为准 (0.64±0.01), 与 SPEC 文字不符处算 SPEC 留口。
        """
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, 30) == pytest.approx(0.637, abs=0.01)

    def test_decay_negative_days_clamped_to_zero(self):
        """未来时间 (negative days_since_access) 不应衰减, 钳到 0。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, -5) == 1.0

    def test_decay_respects_initial_lower_than_one(self):
        """initial=0.5 的条目衰减起点是 0.5, 不是 1.0。"""
        from backend.services.retention_engine import decay_score

        # 7 天后 0.5 * 0.9 = 0.45
        assert decay_score(0.5, 7) == pytest.approx(0.45, abs=0.001)

    def test_decay_bounded_by_initial(self):
        """current_score 永远不超过 initial (异常情况防越界)。"""
        from backend.services.retention_engine import decay_score

        # 即使 days=0, 也不会超过 initial
        assert decay_score(0.5, 0) <= 0.5


class TestRetentionRunAndAccess:
    """retention.json 读改写 + access reset。"""

    def test_run_decay_empty_file(self, tmp_path: Path):
        """空 retention.json 跑 run_decay 不报错, 返回全 0。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        stats = run_decay(rp)
        assert stats == {"updated": 0, "stale_after": 0, "unchanged": 0, "errors": 0}

    def test_run_decay_updates_score(self, tmp_path: Path):
        """构造 7 天前访问的 entry, run_decay 后 current_score 应≈0.9。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        now = datetime.now(tz=timezone.utc)
        seven_days_ago = (now - timedelta(days=7)).isoformat()
        rp.write_text(json.dumps({
            "entries": [{
                "id": "abc123",
                "initial_score": 1.0,
                "current_score": 1.0,
                "last_accessed": seven_days_ago,
                "decay_events": [],
            }],
        }))

        stats = run_decay(rp)
        assert stats["updated"] == 1
        obj = json.loads(rp.read_text())
        assert obj["entries"][0]["current_score"] == pytest.approx(0.9, abs=0.001)

    def test_record_access_resets_to_initial(self, tmp_path: Path):
        """record_access 把 current_score 重置为 initial_score, last_accessed 刷新。"""
        from backend.services.retention_engine import record_access, run_decay

        rp = tmp_path / "retention.json"
        now = datetime.now(tz=timezone.utc)
        # 先建一个已衰减的 entry (30 天前)
        rp.write_text(json.dumps({
            "entries": [{
                "id": "abc123",
                "initial_score": 1.0,
                "current_score": 0.7,
                "last_accessed": (now - timedelta(days=30)).isoformat(),
                "decay_events": [],
            }],
        }))

        record_access(rp, "abc123")

        obj = json.loads(rp.read_text())
        entry = obj["entries"][0]
        assert entry["current_score"] == 1.0  # 重置到 initial
        assert entry["decay_events"][-1]["kind"] == "access"

    def test_record_access_creates_new_entry(self, tmp_path: Path):
        """access 一个不存在的 item_id → 自动建 entry (initial=1.0)。"""
        from backend.services.retention_engine import load_entry, record_access

        rp = tmp_path / "retention.json"
        record_access(rp, "new_id")

        e = load_entry(rp, "new_id")
        assert e is not None
        assert e["initial_score"] == 1.0
        assert e["current_score"] == 1.0


# ── wiki_archiver ───────────────────────────────────────────────
class TestArchiveItem:
    """archive_item 原子写 + 幂等 + retention entry 自动建。"""

    def test_archive_item_writes_md(self, tmp_path: Path):
        from backend.services.wiki_archiver import archive_item

        item = {
            "id": "abc123",
            "title": "Test Article",
            "source": "secnews",
            "ingested_at": "2026-07-01T00:00:00Z",
            "tags": ["ai-security", "red-team"],
            "mastery": 50,
        }
        path = archive_item(item, wiki_root=tmp_path, body="body content")

        assert path.exists()
        text = path.read_text()
        assert "id: abc123" in text
        assert "title: Test Article" in text
        assert "  - ai-security" in text
        assert "body content" in text

        # retention entry 自动建
        retention = json.loads((tmp_path / "retention.json").read_text())
        assert any(e["id"] == "abc123" for e in retention["entries"])

    def test_archive_item_is_idempotent(self, tmp_path: Path):
        """重复调用, 已存在则 skip (不覆盖, 不重写)。"""
        from backend.services.wiki_archiver import archive_item

        item = {"id": "dup", "title": "v1", "ingested_at": "2026-07-01T00:00:00Z"}
        p1 = archive_item(item, wiki_root=tmp_path, body="first")

        # 改 title 试图再次写入
        item2 = {**item, "title": "v2"}
        p2 = archive_item(item2, wiki_root=tmp_path, body="second")

        assert p1 == p2
        # 仍是 v1, 不是 v2 (幂等)
        assert "v1" in p2.read_text()
        assert "v2" not in p2.read_text()

    def test_archive_item_raises_on_missing_id(self, tmp_path: Path):
        from backend.services.wiki_archiver import archive_item

        with pytest.raises(ValueError, match=r"item\['id'\] is required"):
            archive_item({"title": "no id"}, wiki_root=tmp_path)

    def test_archive_item_writes_source_meta(self, tmp_path: Path):
        """source_meta 非空时, 同时写 sources/{id}.md。"""
        from backend.services.wiki_archiver import archive_item

        item = {"id": "src1", "title": "With Source", "ingested_at": "2026-07-01T00:00:00Z"}
        source_meta = {
            "url": "https://example.com/a",
            "parser": "aihot_parser",
            "quality_gates": ["recency", "source_reputation", "url_validity"],
            "fetched_at": "2026-07-01T00:00:00Z",
        }
        archive_item(item, wiki_root=tmp_path, source_meta=source_meta)

        src_path = tmp_path / "sources" / "src1.md"
        assert src_path.exists()
        text = src_path.read_text()
        assert "parser: aihot_parser" in text
        assert "  - recency" in text
        assert "  - source_reputation" in text


class TestAtomicWrite:
    """原子写不应留 .tmp 残留。"""

    def test_atomic_write_no_tmp_leftover(self, tmp_path: Path):
        from backend.services.wiki_archiver import _atomic_write_text

        target = tmp_path / "a.md"
        _atomic_write_text(target, "content")

        assert target.exists()
        assert not (tmp_path / "a.md.tmp").exists()

    def test_atomic_write_overwrites(self, tmp_path: Path):
        from backend.services.wiki_archiver import _atomic_write_text

        target = tmp_path / "b.md"
        _atomic_write_text(target, "v1")
        _atomic_write_text(target, "v2")

        assert target.read_text() == "v2"


# ── e2e 链路: archive → decay → access → 再次 decay ────────────────────
class TestEndToEndArchiveDecayAccess:
    """SPEC §18 验收: 归档后 retention entry 写入 → 7 天后 decay 至 0.9 →
    access 后 reset → 再次 decay。

    验证整条链路 (替代手工 e2e 脚本)。
    """

    def test_archive_then_decay_then_access_then_decay(self, tmp_path: Path):
        from datetime import datetime, timedelta, timezone

        from backend.services.retention_engine import (
            decay_score,
            record_access,
            run_decay,
        )
        from backend.services.wiki_archiver import archive_item

        # 1. archive 创建一个 item (自动建 retention entry, last_accessed=now)
        item = {
            "id": "e2e1",
            "title": "E2E Article",
            "source": "secnews",
            "ingested_at": "2026-07-15T00:00:00Z",
        }
        archive_item(item, wiki_root=tmp_path)

        retention_path = tmp_path / "retention.json"
        assert retention_path.exists()

        # 2. 模拟「7 天后」: 把 entry 的 last_accessed 倒推 7 天
        seven_days_ago = (
            datetime.now(tz=timezone.utc) - timedelta(days=7)
        ).isoformat()
        obj = json.loads(retention_path.read_text())
        for e in obj["entries"]:
            if e["id"] == "e2e1":
                e["last_accessed"] = seven_days_ago
                e["current_score"] = 1.0  # 重置起点
        retention_path.write_text(json.dumps(obj))

        # 3. run_decay → current_score 应≈0.9
        stats = run_decay(retention_path)
        assert stats["updated"] == 1
        obj = json.loads(retention_path.read_text())
        e = next(x for x in obj["entries"] if x["id"] == "e2e1")
        assert e["current_score"] == pytest.approx(0.9, abs=0.001)

        # 4. 用户访问 → record_access → current_score 重置为 1.0
        record_access(retention_path, "e2e1")
        obj = json.loads(retention_path.read_text())
        e = next(x for x in obj["entries"] if x["id"] == "e2e1")
        assert e["current_score"] == 1.0
        # decay_events 末条 = access
        assert e["decay_events"][-1]["kind"] == "access"

        # 5. 再次 run_decay (没有时间流逝, score 不变)
        stats = run_decay(retention_path)
        # last_accessed 是刚才 record_access 写入的 now, days=0 → 不衰减
        obj = json.loads(retention_path.read_text())
        e = next(x for x in obj["entries"] if x["id"] == "e2e1")
        assert e["current_score"] == 1.0

    def test_decay_score_pure_function_matches_formula(self):
        """公式直接验证 (与 run_decay 路径无关): 14 天 = 0.81, 21 天 = 0.729。"""
        from backend.services.retention_engine import decay_score

        # 14 天 = 2 个 7 天窗口 → 0.9^2 = 0.81
        assert decay_score(1.0, 14) == pytest.approx(0.81, abs=0.001)
        # 21 天 = 3 个 7 天窗口 → 0.9^3 = 0.729
        assert decay_score(1.0, 21) == pytest.approx(0.729, abs=0.001)