"""C2.4 管道 B 重建验收（T4 门禁的可 CI 版本）。

语义（WHY）: 取消备份链的合法性来自「DB 可从冷层重建」（RA-14）。本测试跑真实
脚本 ``scripts/rebuild_hot_index.py``，验证 **沉降 → 删热层 → 重建 → 行数/FTS 一致**
这条链在隔离环境内端到端成立；任何一环断（写盘丢列、触发器坏、解析漂移）都必须让它失败。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import config
from backend.repository.db import get_connection
from backend.services.wiki_archiver import sink_hotspots_to_feed

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_hot_index.py"


def _seed() -> None:
    conn = get_connection()
    old = (datetime.now(tz=timezone.utc) - timedelta(days=60)).isoformat()
    for i in range(3):
        conn.execute(
            "INSERT INTO hotspots (id, title, summary, source, url, category, published_at, "
            "score, fetched_at, ingested_at, quality_score, tags) "
            "VALUES (?, ?, ?, 'src', ?, 'security', ?, 1, ?, ?, 90, '[\"ai\"]')",
            (f"HSREBUILD{i}", f"T{i}", f"S{i}", f"https://e.com/{i}", old, old, old),
        )
    conn.execute(
        "INSERT INTO favorites (hotspot_id, category, title, source, url, favorited_at) "
        "VALUES ('HSREBUILD2', 'security', 'T2', 'src', 'https://e.com/2', ?)",
        (old,),
    )
    conn.execute(
        "INSERT INTO tags (id, label, type, weight, created_at) VALUES ('TAG1', '标签', 'concept', 1.0, ?)",
        (old,),
    )
    conn.execute(
        "INSERT INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) VALUES ('HSREBUILD0', 'TAG1', 0.9, ?)",
        (old,),
    )
    conn.commit()


def test_rebuild_from_cold_roundtrip(temp_db, tmp_path) -> None:
    wiki = tmp_path / "wiki"
    _seed()

    # 1. 沉降（30 天外 + 未收藏 → 2 条）；RSBUILD2 是收藏 → 永不下沉
    first = sink_hotspots_to_feed(wiki_root=wiki, days=30, limit=100)
    assert first["sunk"] == 2, first
    assert sink_hotspots_to_feed(wiki_root=wiki, days=30, limit=100)["sunk"] == 0  # 幂等
    assert len(list((wiki / "feed").glob("*.md"))) == 1

    # 2. 模拟热层丢失（保留 schema / tags / favorites / wiki_events）
    conn = get_connection()
    conn.execute("DELETE FROM hotspot_tags")
    conn.execute("DELETE FROM hotspots")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0] == 0  # 触发器已清索引

    # 3. 真实脚本重建
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(config.db_path),
         "--wiki-root", str(wiki), "--from-cold", "--json"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    # 4. 行数容差 0 + FTS 一致 + 标签回填
    assert out["cold_records"] == 2 and out["inserted"] == 2
    assert out["hotspots_rows"] == 2 and out["fts_rows"] == 2
    assert out["diff_total"] == 0 and out["missing_count"] == 0
    assert out["skipped_tag_links"] == 0 and out["tag_links"] == 1
    assert out["invalid"] == []
    row = conn.execute(
        "SELECT title, summary, category, quality_score, tags, lifecycle FROM hotspots "
        "WHERE id = 'HSREBUILD0'"
    ).fetchone()
    assert tuple(row) == ("T0", "S0", "security", 90, '["ai"]', "signal")
    assert conn.execute("SELECT COUNT(*) FROM hotspot_tags").fetchone()[0] == 1