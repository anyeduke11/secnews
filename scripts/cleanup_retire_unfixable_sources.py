"""cleanup_retire_unfixable_sources — 按诊断结论退役不可修的离线源 (默认 dry-run).

用法::

    # 1) 先备份 (T02 演练脚本, 出 manifest.json + sha256)
    .venv/bin/python scripts/t02_backup_drill.py --execute
    # 2) dry-run: 只打印处置清单 (默认)
    .venv/bin/python scripts/cleanup_retire_unfixable_sources.py
    # 3) apply: 必须给出新鲜备份 manifest (24h 内), 否则拒绝
    .venv/bin/python scripts/cleanup_retire_unfixable_sources.py --apply \
        --require-backup backend/backups/_drill/<ts>/manifest.json
    # 4) 回滚: 用 apply 时落盘的记录恢复 enabled/status
    .venv/bin/python scripts/cleanup_retire_unfixable_sources.py --revert reports/retired_sources_<ts>.json --apply

输入 (两份只读报告, 由同批脚本产出):
    reports/dead_source_triage.json     — audit_dead_source_triage: 独立四层探测 + 死因 + ever_succeeded
    reports/check_source_fetch.json     — check_source_fetch --offline: 生产链实测 alive/ok/zero

处置规则 (与 owner 裁决一致: 先诊断, 能修则修, 修不好激进退役; 曾成功者观察):
    keep    生产链实测 alive/ok (修复后已恢复)
    retire  死因 ∈ {dns_nxdomain, http_gone, tls_unrecoverable, tcp_refused, ssrf_policy, no_url}
            或 tcp_timeout 且从未成功
            或 从未成功 且 生产链仍 0 候选 (需 per-source 破解 WAF/弱 TLS, 不做)
    hold    曾成功但当前 0 候选 → 保留 enabled, 靠 6h cadence 低成本观察

写入语义 (仅 apply): ``enabled=0, status='disabled', last_error='retired ...'``; **不 DELETE**,
清单落 ``reports/retired_sources_<ts>.json`` 含改前状态, ``--revert`` 可原样恢复。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402

HARD_CAUSES = {"dns_nxdomain", "http_gone", "tls_unrecoverable", "tcp_refused", "ssrf_policy", "no_url"}
BACKUP_MAX_AGE_S = 24 * 3600


def decide(check: dict, triage: dict | None) -> tuple[str, str]:
    """返回 (decision, reason). decision ∈ keep | retire | hold."""
    res = check.get("result")
    t = (triage or {}).get("triage", {})
    cause = t.get("cause", "unknown")
    ever = bool(t.get("ever_succeeded", True))
    if res in ("alive", "ok"):
        return "keep", f"recovered ({res}, raw={check.get('raw_count')})"
    if cause in HARD_CAUSES:
        return "retire", f"unreachable: {cause}"
    if cause == "tcp_timeout" and not ever:
        return "retire", "tcp_timeout and never succeeded"
    if not ever:
        return "retire", f"never succeeded and still zero after fixes ({cause})"
    return "hold", f"ever succeeded, still zero ({cause}); keep enabled at low cadence"


def load_reports(report_dir: Path) -> tuple[dict, dict]:
    chk_p = report_dir / "check_source_fetch.json"
    tri_p = report_dir / "dead_source_triage.json"
    if not chk_p.exists() or not tri_p.exists():
        raise SystemExit(f"missing reports: {chk_p} / {tri_p} — 先跑 audit_dead_source_triage.py 与 check_source_fetch.py --offline")
    chk = {r["id"]: r for r in json.loads(chk_p.read_text(encoding="utf-8"))["results"]}
    tri = {r["source"]["id"]: r for r in json.loads(tri_p.read_text(encoding="utf-8"))["results"]}
    return chk, tri


def _open_rw() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _check_backup(manifest: str | None) -> None:
    if not manifest:
        raise SystemExit("--apply 需要 --require-backup <manifest.json> (先跑 t02_backup_drill.py --execute)")
    p = Path(manifest)
    if not p.exists():
        raise SystemExit(f"备份 manifest 不存在: {p}")
    age = time.time() - p.stat().st_mtime
    if age > BACKUP_MAX_AGE_S:
        raise SystemExit(f"备份 manifest 已 {age / 3600:.1f}h, 超过 24h, 请重新备份")
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"备份 manifest 不可解析: {e}") from e
    print(f"[retire] backup manifest ok: {p} (age {age / 60:.0f} min, keys={list(m)[:6]})")


def do_retire(decisions: list[dict], apply: bool, manifest: str | None, out_dir: Path) -> None:
    retire = [d for d in decisions if d["decision"] == "retire"]
    print(f"[retire] retire={len(retire)} keep={sum(d['decision']=='keep' for d in decisions)} hold={sum(d['decision']=='hold' for d in decisions)}")
    for d in sorted(retire, key=lambda x: x["id"]):
        print(f"   RETIRE {d['id']:34s} {d['reason']}")
    if not apply:
        print("[retire] dry-run: 未写入 (加 --apply 执行)")
        return
    _check_backup(manifest)
    conn = _open_rw()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    note_prefix = f"retired {ts[:8]} cadence-batch"
    record = {"applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": []}
    changed = 0
    for d in retire:
        before = conn.execute(
            "SELECT id, enabled, status, last_error FROM crawler_sources WHERE id = ?", (d["id"],)
        ).fetchone()
        if before is None:
            print(f"   skip (not found): {d['id']}")
            continue
        record["rows"].append({k: before[k] for k in before.keys()})
        conn.execute(
            "UPDATE crawler_sources SET enabled = 0, status = 'disabled', last_error = ?, updated_at = datetime('now') WHERE id = ?",  # noqa: E501
            (f"{note_prefix}: {d['reason']}"[:500], d["id"]),
        )
        changed += 1
    conn.commit()
    conn.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_p = out_dir / f"retired_sources_{ts}.json"
    rec_p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[retire] applied: {changed} rows → enabled=0,status=disabled; before-state saved {rec_p}")


def do_revert(record_path: str, apply: bool) -> None:
    rec = json.loads(Path(record_path).read_text(encoding="utf-8"))
    rows = rec.get("rows", [])
    print(f"[revert] {len(rows)} rows from {record_path} (applied_at={rec.get('applied_at')})")
    for r in rows:
        print(f"   REVERT {r['id']:34s} → enabled={r['enabled']} status={r['status']}")
    if not apply:
        print("[revert] dry-run: 未写入 (加 --apply 执行)")
        return
    conn = _open_rw()
    for r in rows:
        conn.execute(
            "UPDATE crawler_sources SET enabled = ?, status = ?, last_error = ?, updated_at = datetime('now') WHERE id = ?",  # noqa: E501
            (int(r["enabled"]), r["status"], r.get("last_error"), r["id"]),
        )
    conn.commit()
    conn.close()
    print(f"[revert] restored {len(rows)} rows")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="真实写入 (默认 dry-run)")
    ap.add_argument("--require-backup", default=None, help="apply 前置: 24h 内的备份 manifest.json")
    ap.add_argument("--reports", default=str(REPO_ROOT / "reports"))
    ap.add_argument("--revert", default=None, help="用 retired_sources_<ts>.json 回滚")
    args = ap.parse_args()

    if args.revert:
        do_revert(args.revert, args.apply)
        return 0

    report_dir = Path(args.reports)
    chk, tri = load_reports(report_dir)
    decisions = []
    for sid, c in chk.items():
        decision, reason = decide(c, tri.get(sid))
        decisions.append({"id": sid, "decision": decision, "reason": reason,
                          "cause": (tri.get(sid) or {}).get("triage", {}).get("cause"),
                          "check": c.get("result"), "raw_count": c.get("raw_count")})
    (report_dir / "retire_decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    do_retire(decisions, args.apply, args.require_backup, report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
