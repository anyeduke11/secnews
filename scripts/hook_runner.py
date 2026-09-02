#!/usr/bin/env python3
"""hotspot ZCode hook dispatcher. Reads stdin JSON, dispatches per subcommand, writes status.

Subcommands:
  pre-bash       — Bash PreToolUse risk warn (git add -A, pkill, .db/.env rm, main-branch commit)
  post-edit      — Edit/Write PostToolUse (docstring/meta/asset lint per file glob)
  user-prompt    — UserPromptSubmit branch context (current branch echo)
  stop           — Stop end-of-task checklist (which suites apply to changed files)

Exit semantics:
  0  = healthy (warnings emitted via additionalContext)
  1  = infra error (stdin invalid) — surfaces to ZCode log; NEVER blocks the agent
  NEVER exits 2 (would deny PreToolUse — by design, hooks are advisory)

Mirror of Mimosa's pattern (.mimosa/hook-status/); status JSONL per session rewritten on each
invocation (no unbounded growth). chmod 0600 on status files.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(os.environ.get("ZCODE_PROJECT_DIR", "."))
STATUS_DIR = ROOT / ".zcode" / "hook-status"
SUB = sys.argv[1] if len(sys.argv) > 1 else ""

# Ensure `hooks/` package is importable when invoked as a script
sys.path.insert(0, str(ROOT / "scripts"))


def _read_stdin() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"hook_runner: invalid stdin JSON: {e}", file=sys.stderr)
        sys.exit(1)


def _write_status(session_id: str, payload: dict) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    p = STATUS_DIR / f"{session_id}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _emit(notes: list[str]) -> None:
    out = {"additionalContext": "\n".join(notes)} if notes else {}
    print(json.dumps(out, ensure_ascii=False))


def _branch_note() -> list[str]:
    try:
        br = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.5,
        ).stdout.strip()
        return [f"[hotspot] current git branch: {br}"] if br else []
    except Exception:
        return []


def _stop_checklist() -> list[str]:
    return [
        "[hotspot] task ending checklist:",
        "- backend code edited? → .venv/bin/python -m pytest backend/tests/ -k <scope>",
        "- frontend code edited? → cd frontend && npx vitest run",
        "- ARCHITECTURE.md numbers suspect? → python scripts/generate_meta.py --check",
        "- new/changed SKILL.md? → python scripts/harness_analyze.py --check",
    ]


_DISPATCH: dict[str, object] = {
    "pre-bash": lambda payload: __import__(
        "hooks.bash_risk", fromlist=["check"]
    ).check(payload),
    "post-edit": lambda payload: __import__(
        "hooks.post_edit_quality", fromlist=["check"]
    ).check(payload),
    "user-prompt": lambda _payload: _branch_note(),
    "stop": lambda _payload: _stop_checklist(),
}


def main() -> int:
    payload = _read_stdin()
    session = payload.get("session_id", "unknown")
    notes: list[str] = []
    started = time.time()
    try:
        handler = _DISPATCH.get(SUB)
        if handler is not None:
            notes = handler(payload)
    except Exception as e:
        print(f"hook_runner[{SUB}]: {type(e).__name__}: {e}", file=sys.stderr)
        _write_status(
            session,
            {
                "schemaVersion": "hotspot-hook-status/v1",
                "event": SUB,
                "outcome": "infra_error",
                "error": str(e),
                "durationMs": int((time.time() - started) * 1000),
                "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "sessionId": session,
            },
        )
        return 1
    _write_status(
        session,
        {
            "schemaVersion": "hotspot-hook-status/v1",
            "event": SUB,
            "outcome": "ok" if not notes else "warn",
            "notes": notes,
            "durationMs": int((time.time() - started) * 1000),
            "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sessionId": session,
        },
    )
    _emit(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())