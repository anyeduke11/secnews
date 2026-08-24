#!/usr/bin/env python3
"""export_for_dsh — 把 hotspot.db 导出为 dsh-SecNews migrate-from-hotspot.ts 可消费的 JSON。

背景
----
Phase 7 数据迁移 + 旧系统退役。ts 侧 dsh-SecNews packages/store/src/
migrate-from-hotspot.ts (344 行, 已在 dsh-SecNews 仓库内) 通过 node:sqlite
直读 hotspot.db。但 Python sqlite3 与 node:sqlite 之间存在 4 类不兼容:

1. **WAL 模式**: hotspot.db 默认开 WAL; node:sqlite 需要显式 PRAGMA journal_mode=wal
2. **BLOB 字段**: hotspot 表含 BLOB (encryption_keys 等), node:sqlite Buffer 序列化差异
3. **datetime 精度**: Python 输出 ISO8601 + tz, node:sqlite 字符串比较需标准化
4. **FTS5 虚表**: hotspots_fts_docsize 等虚表不可直接复制, 仅 schema + content 可迁移

为此本脚本作为**旁路导出器**, 把 hotspot 数据降级为纯 JSON, 让 TS 端
不依赖 Python sqlite3 行为, 也不依赖 wal/shm 文件传输。

输出
----
data/export/ (gitignored, 运行时生成)
├── manifest.json     # 导出元数据 (version / exported_at / counts / schema)
├── hotspots.json     # 3391 行热点
├── favorites.json    # 4 行收藏
├── todos.json        # 6 行待办
├── sm2_reviews.json  # 3 行 SM-2 复习状态
├── annotations.json  # 2 行标注
├── hotspot_tags.json # 5356 行 hotspot→tag 关联
├── knowledge_concepts.json  # 98 行概念卡
├── knowledge_graph.json     # 42 行图谱快照
└── wiki_files/      # cp -r knowledge/items/ knowledge/concepts/ 的镜像

每张表的 JSON 形状::

    {
      "table": "<name>",
      "row_count": 1234,
      "schema": "CREATE TABLE ...",          # 给 ts 端直接拼 ddl 用
      "columns": ["id", "title", ...],
      "rows": [ {col: val, ...}, ... ]       # 每行 JSON dict
    }

JSON 字段约定
-------------
- **datetime**: 统一 ISO8601 字符串 (含 tz), Python datetime.isoformat() 输出
- **bytes/BLOB**: {"__b64__": "<base64>"} 包装, TS 端 Buffer.from(s, 'base64')
- **None**: JSON null
- **JSON 字符串 (quality_flags 等)**: 解析为 object/array 后再序列化 (避免双层编码)

用法
----
::

    # 完整导出 (默认)
    python scripts/export_for_dsh.py

    # 仅导热点 + 收藏 (用于 dsh 看板冷启动)
    python scripts/export_for_dsh.py --tables hotspots favorites

    # 干跑 (不打文件, 仅打印会写什么)
    python scripts/export_for_dsh.py --dry-run

    # 自定义输出目录
    python scripts/export_for_dsh.py --out /tmp/dump

验证
----
- 行数 = DB 内行数 (manifest.counts == SELECT COUNT(*))
- 文本字段 round-trip 一致 (UTF-8)
- Wiki 文件数 = knowledge/items/ 下 *.md 数

兼容性
----
- hotspot v0.5.x (本文档写作时): 3391 hotspots / 98 concepts / 4149 wiki items
- hotspot v0.4.x: 同结构, hotspot_tags 行为差异 (见 hotspot_repo.py 注释)
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# repo root = scripts/../..
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"
DEFAULT_OUT = REPO_ROOT / "data" / "export"
DEFAULT_WIKI = REPO_ROOT / "knowledge"

# 优先迁移的核心表 (其余表 dsh 端按需单独处理, 或不迁移)
DEFAULT_TABLES = [
    "hotspots",
    "favorites",
    "todos",
    "sm2_reviews",
    "annotations",
    "hotspot_tags",
    "knowledge_concepts",
    "knowledge_graph",
]

# 不迁移的表 (原因附注, 方便 dsh 端开发对账)
SKIP_TABLES = {
    "schema_version": "dsh 端自有 schema, 不迁移",
    "ai_scores": "v0.5 引入但仍 0 行, 不迁移",
    "alert_events": "实时事件流, dsh 重放或重生成",
    "alert_rules": "与 dsh 端策略不同, 留 hotspot 退役后废弃",
    "alert_rule_definitions": "同上",
    "alerts": "运行时, 不迁移",
    "attention_events": "v0.5 新, 0 行",
    "cg_*": "CodeGarden 扩展, dsh 端独立 schema",
    "crawler_sources": "采集源配置, dsh 端独立管理",
    "encryption_keys": "敏感字段, 不导出 (DSH 端 PBKDF2 重新派生)",
    "favorites_snapshot": "派生表, dsh 端可重算",
    "favorites_stats": "派生表",
    "hotspots_fts*": "FTS5 虚表, dsh 端自行 rebuild",
    "kl_dead_letters": "运行时死信, 不迁移",
    "kl_queue": "Phase 0 新表, dsh 端 schema 不同",
    "llm_*": "LLM 凭据 / 缓存 / 用量, 全部本地化",
    "mcp_tool_registry": "dsh 端 mcp 自管",
    "personal_profile": "v0.5 新, 0 行",
    "proxy_health_log": "运行时健康日志",
    "quality_check_logs_archive": "1.8M 行, 不导入; dsh 端按需从原始 quality_check_logs 重算",
    "reading_states": "v0.5 新, 0 行",
    "secret_access_logs": "审计日志, 不导出",
    "security_*": "v0.6 扩展域, dsh 端独立",
    "settings": "dsh 端独立管理, 仅迁移 quality_rules 子集",
    "skills": "MCP 工具配置, dsh 端独立",
    "source_alerts": "运行时告警",
    "source_reputation": "运行时统计",
    "source_stats": "派生表",
    "sync_configs": "dsh 端独立",
    "sync_states": "派生表",
    "tags": "tag 主表小, 但 hotspot_tags 关联表是核心",
    "tech_stack": "v0.5 新, 0 行",
    "token_ledger": "Phase 0 新表, dsh 端独立",
    "unified_fts*": "FTS5 虚表",
    "wiki_events": "事件流, 留 audit 不迁移",
    "wiki_items_fts*": "FTS5 虚表",
    "_migration_*": "占位符, 不导出",
}


def _is_json_encoded(value: Any) -> bool:
    """检测字符串字段是否实际是 JSON 编码 (如 quality_flags/tags)。"""
    if not isinstance(value, str) or len(value) < 2:
        return False
    if value[0] not in '{"[' or value[-1] not in '"}]':
        return False
    try:
        json.loads(value)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """行级归一化: datetime → ISO 字符串, BLOB → base64, JSON-encoded → 解析后。

    SQLite 返回的列类型:
    - str: 字符串 (含 datetime ISO, 含 JSON-encoded 字段)
    - int/float: 数值
    - None: NULL
    - bytes: BLOB (e.g. encryption_keys)
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, bytes):
            out[k] = {"__b64__": base64.b64encode(v).decode("ascii")}
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            if _is_json_encoded(v):
                try:
                    out[k] = json.loads(v)
                except json.JSONDecodeError:
                    out[k] = v
            else:
                out[k] = v
        else:
            # 罕见: datetime 等已在 connection row_factory=sqlite3.Row 中转为 str
            out[k] = str(v)
    return out


def _table_schema(conn: sqlite3.Connection, table: str) -> tuple[str, list[str]]:
    """返回 (CREATE TABLE ddl, column names)。"""
    cols = [
        r[1]
        for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    ddl = row[0] if row and row[0] else ""
    return ddl, cols


def _export_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """导出单张表为标准化 JSON 形状。"""
    ddl, cols = _table_schema(conn, table)
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    payload = {
        "table": table,
        "row_count": len(rows),
        "schema": ddl,
        "columns": cols,
        "rows": [_normalize_row(dict(zip(cols, r))) for r in rows],
    }
    return payload


def _copy_wiki(src: Path, dst: Path) -> dict[str, Any]:
    """cp -r knowledge/{items,concepts,inbox,quarantine} → data/export/wiki_files/。

    镜像而非 export 是因为 wiki FS 的真相源是 .md 文件, 不在 SQLite 里。
    dsh 端 migrate-from-hotspot.ts 直接读 llm-wiki-2.0/, 这里作为备份旁路。
    """
    if not src.exists():
        return {"copied": 0, "skipped": True, "reason": f"{src} not found"}
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    by_subdir: dict[str, int] = {}
    for subdir in ["items", "concepts", "inbox", "quarantine"]:
        sub = src / subdir
        if not sub.exists():
            by_subdir[subdir] = 0
            continue
        target = dst / subdir
        shutil.copytree(sub, target)
        n = sum(1 for _ in target.rglob("*.md"))
        by_subdir[subdir] = n
        copied += n
    return {"copied": copied, "by_subdir": by_subdir}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导出 hotspot.db 为 dsh-SecNews migrate-from-hotspot.ts 可消费 JSON",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"hotspot.db 路径 (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"导出目录 (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--wiki-src",
        type=Path,
        default=DEFAULT_WIKI,
        help=f"wiki 真相源目录 (default: {DEFAULT_WIKI})",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help=f"指定导出表 (default: {len(DEFAULT_TABLES)} 张核心表)",
    )
    parser.add_argument(
        "--no-wiki",
        action="store_true",
        help="跳过 wiki 文件复制",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不写盘, 仅打印计划",
    )
    args = parser.parse_args()

    tables = args.tables or DEFAULT_TABLES

    if not args.db.exists():
        print(f"ERROR: hotspot.db not found at {args.db}", file=sys.stderr)
        return 2

    print(f"[*] DB:    {args.db}")
    print(f"[*] OUT:   {args.out}")
    print(f"[*] WIKI:  {args.wiki_src}")
    print(f"[*] TABLES ({len(tables)}): {', '.join(tables)}")
    print(f"[*] DRY_RUN: {args.dry_run}")
    print()

    if not args.dry_run:
        args.out.mkdir(parents=True, exist_ok=True)

    # 1. 导出表
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for t in tables:
        try:
            payload = _export_table(conn, t)
        except Exception as exc:
            print(f"  ✗ {t}: {exc}", file=sys.stderr)
            continue
        counts[t] = payload["row_count"]
        payloads[t] = payload
        if not args.dry_run:
            out_path = args.out / f"{t}.json"
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(f"  ✓ {t:<22} {counts[t]:>6} rows")

    # 2. Wiki 文件复制
    wiki_stats: dict[str, Any] = {}
    if not args.no_wiki:
        wiki_dst = args.out / "wiki_files"
        if args.dry_run:
            if args.wiki_src.exists():
                md = sum(1 for _ in (args.wiki_src / "items").rglob("*.md"))
                wiki_stats = {"would_copy": md}
        else:
            wiki_stats = _copy_wiki(args.wiki_src, wiki_dst)
        print(f"  ✓ wiki_files            {wiki_stats}")

    # 3. Manifest
    manifest = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "hotspot_version": _read_version(),
        "counts": counts,
        "total_rows": sum(counts.values()),
        "tables": tables,
        "wiki": wiki_stats,
        "skip_tables_rationale": SKIP_TABLES,
        "contract": {
            "datetime": "ISO8601 string with timezone",
            "blob": {"__b64__": "base64 encoded"},
            "null": "JSON null",
            "json_encoded_string": "parsed into object/array before serialization",
        },
    }
    if not args.dry_run:
        (args.out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print()
    print(f"[✓] Wrote {len(payloads)} table dumps + manifest to {args.out}")
    print(f"[i] Total rows: {sum(counts.values())}")
    return 0


def _read_version() -> str:
    """从 backend/version.py 读 APP_VERSION, 不强依赖 import。"""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from backend.version import APP_VERSION  # type: ignore

        return APP_VERSION
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
