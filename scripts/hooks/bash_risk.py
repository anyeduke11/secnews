"""Bash PreToolUse risk warnings for hotspot.

Returns list[str] of advisory notes (additionalContext fragments). Empty list = clean.

Checked patterns (from hotspot MEMORY.md + PROGRESS.md documented failure modes):
  1. `git add -A` / `git add .` / `git add *` — refuse without explicit pathspec
     (memory: 2026-08-30 git add -A 扫入并行会话 3840 文件)
  2. `git commit` on main branch without explicit file path — branch-aware gate
     (memory: 2026-08-31 Batch 2 docs commit 误入 main 教训)
  3. `pkill -f uvicorn` / `kill -9` against uvicorn — wrong backend stop pattern
     (memory: 停后端用 lsof 查 pid 别信 pkill 模式)
  4. `rm` against .env*, *.db, .venv — destructive against hot state
  5. `pip install` / `npm install` — needs explicit confirmation, not silent
  6. `python ` (not `.venv/bin/python`) for pytest — backend must use venv
     (memory: 后端必用 .venv/bin/python)

Per user choice: ALL warnings only — never block. The agent can override by ignoring notes.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+add\s+(-\w*A|\.|\*)"),
        "git add -A / . / * — use explicit pathspec to avoid sweeping in parallel-session "
        "edits (memory: 2026-08-30 3840-file incident)",
    ),
    (
        re.compile(r"\bpkill\s+-f\s+(uvicorn|python)"),
        "pkill -f uvicorn — false-positive-prone; use `lsof -ti:<port>` then `kill <pid>` "
        "(memory L15)",
    ),
    (
        re.compile(r"\brm\s+-[rf]+\s+.*(\.env|\.db|\.venv)"),
        "rm against .env / .db / .venv — these hold secrets / live DB / venv",
    ),
    (
        re.compile(r"\b(pip|npm|pnpm|yarn)\s+install\b"),
        "package install — confirm dependency intent before running",
    ),
]

_COMMIT_PATH_HINT = re.compile(
    r"\bgit\s+commit\b.*\s\S+\.(py|ts|tsx|md|json|toml|yml|yaml)\b"
)


def _current_branch() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.5,
        ).stdout.strip()
    except Exception:
        return ""


def check(payload: dict) -> list[str]:
    """Return advisory notes for a Bash PreToolUse payload. Empty list = clean."""
    cmd = payload.get("tool_input", {}).get("command", "")
    if not cmd:
        return []
    notes: list[str] = []
    for pat, msg in DESTRUCTIVE_PATTERNS:
        if pat.search(cmd):
            notes.append(f"⚠ {msg}")
    # Branch-aware gate: git commit on main without explicit file path
    if re.search(r"\bgit\s+commit\b", cmd):
        br = _current_branch()
        if br == "main" and not _COMMIT_PATH_HINT.search(cmd):
            notes.append(
                "⚠ git commit on main branch without explicit file path — risk of "
                "wrong-branch commit (memory: 2026-08-31 Batch 2 docs commit 误入 main)"
            )
    # venv reminder: only when pytest + bare python is invoked (not already in venv python)
    if re.search(r"\bpytest\b", cmd) and re.search(r"\bpython\b", cmd) and ".venv/bin" not in cmd:
        notes.append(
            "ℹ backend pytest should use `.venv/bin/python -m pytest ...` "
            "(memory L15: 后端必用 .venv/bin/python)"
        )
    return notes