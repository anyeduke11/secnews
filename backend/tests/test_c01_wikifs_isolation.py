"""v1.0 C01 反例测试 — WikiFs 根隔离 (R10)。

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §2 C01] + [REVIEW_2026-09-07.md R10]

原文件 ``test_c01_wal_backup_and_wikifs_isolation.py`` 含两组反例:
R12 (WAL 备份) 与 R10 (WikiFs 根隔离)。v0.8.8 P2.5 C2.1 退役备份链后,
R12 组失去被测对象 (backup_service / t02_backup_drill 已删除), 仅保留
R10 组 —— 它守卫 wiki-first 存储哲学 (PRD C-4 硬约束: md 为唯一真相源,
不得写入仓库根旧 knowledge/)。
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# R10: WikiFs cwd 隔离 — 字面 "knowledge" 写入仓库根污染
# ---------------------------------------------------------------------------
def test_wikifs_cwd_isolation_writes_to_resolve_wiki_root(monkeypatch, tmp_path: Path) -> None:
    """R10 修复断言: WikiFs(resolve_wiki_root()) 写到 env 指定的隔离根.

    仓库根的 knowledge/ 是 .gitignore 内的历史根, 不应被新代码写入.
    反例: 在隔离 wiki 根下写知识项, 应进 env 根, 不进仓库根 knowledge/.
    """
    # 1) 隔离: 设置 HOTSPOT_WIKI_ROOT 指向 tmp_path
    iso_wiki = tmp_path / "iso-wiki-c01"
    iso_wiki.mkdir()
    monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(iso_wiki))

    # 2) 走"新实现"路径
    from backend.wiki_fs.root import resolve_wiki_root
    from backend.wiki_fs.store import WikiFs
    fs = WikiFs(resolve_wiki_root())
    assert fs.root == str(iso_wiki), (
        f"R10 根错: WikiFs({resolve_wiki_root()}).root 应为 {iso_wiki}, 实际 {fs.root}"
    )
    fs._ensure_dirs()
    fs.write_item("ki_isolation_test", {"title": "iso", "body": "body"})

    # 3) 断言: 隔离根有内容
    assert (iso_wiki / "items" / "ki_isolation_test.md").exists(), (
        f"隔离根应收到写入, 实际 {list(iso_wiki.rglob('*'))[:10]}"
    )

    # 4) 断言: 仓库根 knowledge/ 不应被新增 (与原 178 items 数对账, 任何增加 = 污染)
    repo_root = Path.cwd()
    repo_knowledge_items = repo_root / "knowledge" / "items"
    if repo_knowledge_items.exists():
        # 取新增数 (按 mtime 过滤) — 隔离测试期间不应有任何新增
        import time as _t
        cutoff = _t.time() - 30  # 30s 内
        new_files = [
            f for f in repo_knowledge_items.iterdir()
            if f.is_file() and f.stat().st_mtime > cutoff
        ]
        assert not new_files, (
            f"R10 污染: 仓库根 knowledge/items/ 30s 内新增 {new_files}"
        )


def test_wikifs_knowledge_service_uses_resolve_wiki_root(monkeypatch, tmp_path: Path) -> None:
    """R10 修复断言: knowledge_service.publish 调 WikiFs 时用 resolve_wiki_root, 不写字面 'knowledge'.

    旧实现 knowledge_service:480 写 WikiFs("knowledge") 是相对 cwd 污染源.
    修复后: WikiFs(resolve_wiki_root()), 由 env HOTSPOT_WIKI_ROOT 决定根.
    """
    iso_wiki = tmp_path / "iso-wiki-2"
    iso_wiki.mkdir()
    monkeypatch.setenv("HOTSPOT_WIKI_ROOT", str(iso_wiki))

    # 静态检查: knowledge_service.publish 路径的 WikiFs 调用
    import inspect

    from backend.services import knowledge_service
    src = inspect.getsource(knowledge_service)
    # 不应出现 WikiFs("knowledge") 字面 (是 R10 旧实现)
    assert 'WikiFs("knowledge")' not in src, (
        f"R10 未修: knowledge_service.py 仍用 WikiFs('knowledge') 字面字符串\n{src[:2000]}"
    )
    # 应出现 WikiFs(resolve_wiki_root()) 或类似 env-based 形式
    assert "resolve_wiki_root" in src or "HOTSPOT_WIKI_ROOT" in src, (
        "R10 未走 env 根: knowledge_service.py 不引用 resolve_wiki_root/HOTSPOT_WIKI_ROOT"
    )


def test_wikifs_judgment_service_uses_resolve_wiki_root(monkeypatch, tmp_path: Path) -> None:
    """R10 修复断言: judgment_service.publish 同样修."""
    import inspect

    from backend.services import judgment_service
    src = inspect.getsource(judgment_service)
    assert 'WikiFs("knowledge")' not in src, (
        "R10 未修: judgment_service.py 仍用 WikiFs('knowledge') 字面字符串"
    )
    assert "resolve_wiki_root" in src or "HOTSPOT_WIKI_ROOT" in src, (
        "R10 未走 env 根: judgment_service.py 不引用 resolve_wiki_root/HOTSPOT_WIKI_ROOT"
    )
