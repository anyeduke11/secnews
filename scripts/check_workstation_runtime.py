"""v1.0 C01 — 工作站运行时只读诊断 (lsof/curl/SQLite 只读查询).

不修改任何状态, 不写文件, 不启动 scheduler, 不触发 init_db.
当后端起不来, 这个脚本导出可诊断的脱敏 JSON, 给后续 C02-C04 决策用.

依据 [docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md §3 步骤 1] + [CLOSEOUT_TASKS.md C01].

使用:
  python scripts/check_workstation_runtime.py              # 完整诊断 (返回 JSON)
  python scripts/check_workstation_runtime.py --quiet      # 仅 failed/warn 项
  python scripts/check_workstation_runtime.py --exit-zero  # 不以非零退出 (供 lint 用)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# 脱敏: 任何 keyring/secret 字段不进 JSON
_SENSITIVE_KEYS = re.compile(r"(key|secret|token|password|cred)", re.IGNORECASE)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            key_match = _SENSITIVE_KEYS.search(str(k)) if k is not None else None
            if key_match and isinstance(v, (str, int, float)):
                result[str(k)] = "[REDACTED]"
            else:
                result[str(k)] = _redact(v)
        return result
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _check_ports() -> dict[str, Any]:
    """lsof 8000/8898 (生产) + 8766/8899 (dev)."""
    ports = [8000, 8898, 8766, 8899]
    out: dict[str, Any] = {"checked": ports, "listening": {}}
    for p in ports:
        try:
            r = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{p}", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=2,
            )
            listening = []
            for line in r.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    listening.append({"command": parts[0], "pid": parts[1]})
            out["listening"][p] = listening
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            out["listening"][p] = f"lsof err: {e}"
    return out


def _check_backend_health(port: int = 8000) -> dict[str, Any]:
    """curl /api/health 探活, 5s timeout. 不启动后端, 只测已起的."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as r:
            body = json.loads(r.read().decode("utf-8", errors="replace"))
            return {
                "ok": True,
                "status_code": r.status,
                "status": body.get("status"),
                "db_ok": body.get("components", {}).get("db", {}).get("ok"),
                "scheduler_ok": body.get("components", {}).get("scheduler", {}).get("ok"),
                "hotspots_count": body.get("components", {}).get("db", {}).get("hotspots_count"),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _check_db_files() -> dict[str, Any]:
    """SQLite 只读: schema_version + 关键表行数 + 视图列表 + integrity_check."""
    from backend.config import config
    out: dict[str, Any] = {"hot": {}, "warm": {}, "cold": {}, "wiki_root": str(os.environ.get("HOTSPOT_WIKI_ROOT") or "")}
    targets = [
        ("hot", config.db_path),
        ("warm", getattr(config, "warm_db_path", None)),
        ("cold", getattr(config, "cold_db_path", None)),
    ]
    for kind, path in targets:
        if not path or not Path(path).exists():
            out[kind] = {"exists": False, "path": str(path) if path else None}
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            out[kind] = {"exists": True, "open_error": str(e)[:200]}
            continue
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            try:
                sv = [r[0] for r in conn.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                ).fetchall()]
            except sqlite3.OperationalError:
                sv = []  # warm/cold 不一定有 schema_version (历史分库)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            views = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            ).fetchall()]
            row_counts: dict[str, int] = {}
            for t in ("hotspots", "knowledge_items", "v1_subjects", "v1_materials", "v1_signals", "v1_cases", "v1_knowledge"):
                if t in tables:
                    try:
                        row_counts[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    except sqlite3.Error:
                        pass
            out[kind] = {
                "exists": True,
                "path": str(path),
                "size_mb": round(Path(path).stat().st_size / 1e6, 2),
                "integrity_check": integrity[0] if integrity else "unknown",
                "schema_version_count": len(sv),
                "schema_version_max": max((int(v.split("_")[0]) for v in sv if v.split("_")[0].isdigit()), default=0),
                "tables_count": len(tables),
                "views": views,
                "row_counts": row_counts,
            }
        finally:
            conn.close()
    return out


def _check_wiki_root() -> dict[str, Any]:
    """HOTSPOT_WIKI_ROOT 解析 + items 数 + git 状态."""
    from backend.wiki_fs.root import resolve_wiki_root
    root = resolve_wiki_root()
    out: dict[str, Any] = {"resolved": root, "exists": False}
    p = Path(root)
    if p.exists():
        items_dir = p / "items"
        out["exists"] = True
        out["items_count"] = len(list(items_dir.glob("*.md"))) if items_dir.exists() else 0
        out["concepts_count"] = len(list((p / "concepts").glob("*.md"))) if (p / "concepts").exists() else 0
    # 警告: 旧 knowledge/ 根仍存在 (R10 修复前提)
    legacy = REPO_ROOT / "knowledge"
    if legacy.exists():
        out["legacy_knowledge_root_exists"] = True
        out["legacy_knowledge_items"] = len(list((legacy / "items").glob("*.md"))) if (legacy / "items").exists() else 0
    return out


def _check_environment_id() -> str:
    """读 environment_id 决定 dev/staging/prod; 来自 env 或 settings."""
    return os.environ.get("HOTSPOT_ENVIRONMENT_ID", "default")


def main() -> int:
    ap = argparse.ArgumentParser(description="C01 工作站只读诊断")
    ap.add_argument("--quiet", action="store_true", help="仅显示问题项")
    ap.add_argument("--exit-zero", action="store_true", help="不返回非零退出码")
    ap.add_argument("--backend-port", type=int, default=8000, help="后端 health 探测端口")
    args = ap.parse_args()

    report: dict[str, Any] = {
        "check": "check_workstation_runtime",
        "version": "C01",
        "environment_id": _check_environment_id(),
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
    }
    report["ports"] = _check_ports()
    report["backend_health"] = _check_backend_health(args.backend_port)
    report["db_files"] = _check_db_files()
    report["wiki"] = _check_wiki_root()
    report = _redact(report)

    # 找 failed/warn
    issues: list[str] = []
    if not report["backend_health"].get("ok"):
        issues.append(f"backend {args.backend_port} not healthy: {report['backend_health'].get('error', '?')}")
    for kind, info in report["db_files"].items():
        if isinstance(info, dict) and info.get("integrity_check") and info["integrity_check"] != "ok":
            issues.append(f"{kind} db integrity {info['integrity_check']}")
    if report["wiki"].get("legacy_knowledge_root_exists"):
        issues.append(
            f"legacy knowledge/ root still exists ({report['wiki'].get('legacy_knowledge_items', 0)} items); "
            "R10 fix stops new code writing here, but old items remain — migration plan needed"
        )
    report["issues"] = issues

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.quiet and not issues:
        return 0
    if issues and not args.exit_zero:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
