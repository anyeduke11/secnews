#!/usr/bin/env python3
"""export_migrations_for_dsh — 把 hotspot 的 67 个 migrations/*.sql 导出给 dsh-SecNews。

背景
----
Spec 第 198 行明确要求: ``backend/repository/migrations/*.sql`` (65个) →
``store/src/migrations/`` (直接复制+改写)。

hotspot 的 migrations 是 schema 演进日志, 不是初始 schema dump。
区别于 dump_schema.py (给 dsh 终态 schema 参考), 本脚本给 dsh 提供:

1. **演进路径参考** — dsh 端 `packages/store/src/migrations/` 需要
   对应的 TS migration 文件, 命名风格可对齐 hotspot 编号
2. **可重建性验证** — 67 个文件按顺序 exec 应该能完整重建 hotspot.db
   (除数据行), dsh 端可对照 schema_dump 验证
3. **审计追踪** — 每个文件的 sha256 + 行数 + 关键词索引, 方便 dsh
   仓库开发者 cross-check

输出 (2 目录 + 1 manifest)::

    data/migrations/
    ├── 001_init.sql ... 070_kl_pipeline.sql  (67 个 .sql 原文复制)
    ├── manifest.json   (schema_version + per-file sha256/size/keywords)
    └── README.md       (dsh 端消费指南)

不做的事
--------
- 不解析 SQL AST (用 grep 抽关键词)
- 不翻译成 TypeScript (那是 dsh 仓库开发者的工作)
- 不执行 SQL (验证另起脚本, 见 test_export_migrations_for_dsh.py)

用法
----
::

    # 完整导出 (默认到 data/migrations/)
    python3 scripts/export_migrations_for_dsh.py

    # 输出到自定义目录
    python3 scripts/export_migrations_for_dsh.py --out /tmp/migrations

    # 干跑 (仅打印统计, 不写盘)
    python3 scripts/export_migrations_for_dsh.py --dry-run

    # 只导出 .sql 不写 manifest/README
    python3 scripts/export_migrations_for_dsh.py --sql-only

兼容性
----
- hotspot v0.5.x: 67 个 migrations/*.sql (001_init → 070_kl_pipeline)
- dsh 端: 67 个文件直接 cp 到 ``packages/store/src/migrations/`` 后改写
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# repo root = scripts/../..
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO_ROOT / "backend" / "repository" / "migrations"
DEFAULT_OUT = REPO_ROOT / "data" / "migrations"

# 关键词分类 (基于实际读 001_init.sql/046_down.sql 等样本抽出的常见 operation)
KEYWORDS = (
    "CREATE TABLE",
    "CREATE INDEX",
    "CREATE VIEW",
    "CREATE TRIGGER",
    "ALTER TABLE",
    "DROP TABLE",
    "DROP INDEX",
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
    "PRAGMA ",
    "ATTACH ",
    "DETACH ",
)


def _rel_or_abs(p: Path) -> str:
    """输出尽量用相对 REPO_ROOT 的路径, 失败时回退到绝对路径。"""
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        # macOS /private/var/folders/... 或其他不在 REPO_ROOT 下的临时目录
        return str(p)


def _read_version() -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from backend.version import APP_VERSION  # type: ignore

        return APP_VERSION
    except Exception:
        return "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _scan_keywords(text: str) -> dict[str, int]:
    """统计每个关键词在 SQL 中出现次数 (case-insensitive, 已 upper 输入)。"""
    upper = text.upper()
    return {kw: len(re.findall(re.escape(kw), upper)) for kw in KEYWORDS}


def collect(src_dir: Path) -> list[dict]:
    """扫描 migrations 目录, 返回每个 .sql 的元信息 dict。

    排序规则: 按文件名升序 (001_init.sql < 002_quality.sql < ...),
    保证 dsh 端按写入顺序 exec 就是版本号顺序。
    """
    if not src_dir.is_dir():
        raise FileNotFoundError(f"migrations dir not found: {src_dir}")

    files = sorted(p for p in src_dir.iterdir() if p.suffix == ".sql")
    if not files:
        raise RuntimeError(f"no .sql files found in {src_dir}")

    entries = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        entries.append(
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "line_count": text.count("\n") + (0 if text.endswith("\n") else 1),
                "sha256": _sha256(p),
                "keywords": _scan_keywords(text),
            }
        )
    return entries


def render_manifest(
    entries: list[dict], src_dir: Path, hotspot_version: str
) -> dict:
    """生成 manifest.json (供 dsh 端 cross-check)。"""
    total_kw: dict[str, int] = {}
    for e in entries:
        for kw, cnt in e["keywords"].items():
            total_kw[kw] = total_kw.get(kw, 0) + cnt

    return {
        "schema_version": 1,
        "dumped_at": datetime.now(timezone.utc).isoformat(),
        "hotspot_version": hotspot_version,
        "src_dir": str(src_dir.relative_to(REPO_ROOT)),
        "totals": {
            "files": len(entries),
            "total_bytes": sum(e["size_bytes"] for e in entries),
            "total_lines": sum(e["line_count"] for e in entries),
            "keywords": total_kw,
        },
        "files": entries,
    }


def render_readme(manifest: dict) -> str:
    """生成 README.md 给 dsh 仓库开发者。"""
    t = manifest["totals"]
    lines = [
        "# hotspot migrations → dsh-SecNews",
        "",
        f"> Schema 版本: v{manifest['schema_version']}  ",
        f"> dumped_at: {manifest['dumped_at']}  ",
        f"> hotspot 版本: {manifest['hotspot_version']}",
        "",
        f"## 总量 ({t['files']} 个 .sql 文件)",
        "",
        f"- 文件数: **{t['files']}**",
        f"- 字节: **{t['total_bytes']:,}**",
        f"- 行数: **{t['total_lines']:,}**",
        "",
        "## 关键词分布",
        "",
        "| 关键词 | 出现次数 |",
        "|--------|---------|",
    ]
    for kw, cnt in sorted(t["keywords"].items(), key=lambda x: -x[1]):
        if cnt > 0:
            lines.append(f"| `{kw.strip()}` | {cnt} |")
    lines.extend(
        [
            "",
            "## 文件清单 (按文件名升序)",
            "",
            "| 文件 | 行数 | 字节 | sha256 (前 16) |",
            "|------|------|------|---------------|",
        ]
    )
    for f in manifest["files"]:
        lines.append(
            f"| `{f['filename']}` | {f['line_count']} | {f['size_bytes']} | `{f['sha256'][:16]}` |"
        )
    lines.extend(
        [
            "",
            "## dsh 端消费指引",
            "",
            "### 1. 直接复制",
            "",
            "```bash",
            "cp -r hotspot/data/migrations/* dsh/packages/store/src/migrations/",
            "```",
            "",
            "### 2. 改写为 TypeScript migration runner",
            "",
            "dsh 端建议用 `node:sqlite` 的 `exec()` 顺序执行, 与 hotspot 端",
            "`apply_migrations()` 行为对齐。命名风格沿用 `NNN_xxx.sql` 以保留",
            "hotspot 演进路径可追溯性。",
            "",
            "### 3. 验证 schema 一致",
            "",
            "跑 `hotspot/scripts/dump_schema.py` 得到 80 表 DDL, 与 dsh 端",
            "执行全部 migrations 后的 schema 对比:",
            "",
            "```bash",
            "# hotspot 侧",
            "python3 scripts/dump_schema.py --sql-only --out /tmp/h_schema",
            "",
            "# dsh 侧",
            "sqlite3 dsh/data/secnews.db '.schema' > /tmp/d_schema.sql",
            "",
            "# 对比",
            "diff /tmp/h_schema/ddl.sql /tmp/d_schema.sql",
            "```",
            "",
            "### 4. 注意事项",
            "",
            "- 部分 migration 含 `INSERT INTO` (数据迁移, 非纯 schema)",
            "  或 `UPDATE` (回滚脚本, 如 `046_v1.7_lifecycle_down.sql`)",
            "- `DROP TABLE` 类 migration (038, 051) 在 dsh 端建议保留为 no-op",
            "  以保留演进历史, 但不真执行",
            "- migration 文件头注释保留 hotspot Python enum 引用 (Category,",
            "  CollectorStatus 等), dsh 端可参考 backend/domain/enums.py",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导出 hotspot 67 个 migrations/*.sql 给 dsh-SecNews"
    )
    parser.add_argument(
        "--src", type=Path, default=DEFAULT_SRC, help=f"源目录 (default: {DEFAULT_SRC})"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"输出目录 (default: {DEFAULT_OUT})"
    )
    parser.add_argument("--dry-run", action="store_true", help="不写盘, 仅打印统计")
    parser.add_argument("--sql-only", action="store_true", help="仅复制 .sql, 不写 manifest/README")
    args = parser.parse_args()

    if not args.src.is_dir():
        print(f"ERROR: migrations dir not found at {args.src}", file=sys.stderr)
        return 2

    entries = collect(args.src)
    hotspot_version = _read_version()
    manifest = render_manifest(entries, args.src, hotspot_version)

    totals = manifest["totals"]
    print(f"[*] SRC:           {_rel_or_abs(args.src)}")
    print(f"[*] hotspot ver:   {hotspot_version}")
    print(f"[*] dumped at:     {manifest['dumped_at']}")
    print()
    print("[*] Totals:")
    print(f"    files         {totals['files']}")
    print(f"    total_bytes   {totals['total_bytes']:,}")
    print(f"    total_lines   {totals['total_lines']:,}")
    print()
    print("[*] Keywords (top 10):")
    for kw, cnt in sorted(totals["keywords"].items(), key=lambda x: -x[1])[:10]:
        if cnt > 0:
            print(f"    {kw.strip():<16} {cnt}")
    print()
    print(f"[*] First 5 files:")
    for f in entries[:5]:
        print(f"    {f['filename']:<40} {f['line_count']:>4} lines  {f['size_bytes']:>6}B")
    if len(entries) > 5:
        print(f"    ... +{len(entries) - 5} more")

    if args.dry_run:
        print()
        print("[i] DRY_RUN: not writing to disk")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)

    # 1. 复制 .sql 原文
    for f in entries:
        dst = args.out / f["filename"]
        shutil.copy2(args.src / f["filename"], dst)
    print()
    print(f"[✓] Copied {len(entries)} .sql files to {_rel_or_abs(args.out)}/")

    if args.sql_only:
        return 0

    # 2. manifest.json
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[✓] Wrote {_rel_or_abs(manifest_path)}")

    # 3. README.md
    readme_path = args.out / "README.md"
    readme_path.write_text(render_readme(manifest), encoding="utf-8")
    print(f"[✓] Wrote {_rel_or_abs(readme_path)}")

    print()
    print("[i] dsh 端消费提示:")
    print("    # 1. 复制")
    print("    cp -r hotspot/data/migrations/* dsh/packages/store/src/migrations/")
    print(f"    # 2. 验证 schema 一致 (需先跑 hotspot/scripts/dump_schema.py)")
    print("    diff /tmp/h_schema/ddl.sql /tmp/d_schema.sql")
    return 0


if __name__ == "__main__":
    sys.exit(main())
