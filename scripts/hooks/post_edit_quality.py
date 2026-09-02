"""Post-edit quality-gate dispatcher for hotspot.

Mirrors CI blocking steps (per .github/workflows/ci.yml backend job):
  - check_docstrings.py            → backend/services|api|repository edits (ci.yml step 11)
  - harness_analyze.py --check     → .agents/skills/<name>/SKILL.md edits (ci.yml step 10)
  - generate_meta.py --check       → register-point edits (ci.yml step 9)

For Tailwind config edits (frontend/tailwind.config.*): remind to restart `npm run dev`
(per frontend/src/AGENTS.md "Tailwind 配置需重启 dev server").

All sub-checks are run as subprocesses with explicit timeout. Failures turn into advisory
notes (additionalContext); we never block — per user choice.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]

DOCSTRING_GLOB = re.compile(r"^backend/(services|api|repository)/.*\.py$")
ASSETS_GLOB = re.compile(r"^\.agents/skills/[^/]+/SKILL\.md$")
META_GLOB = re.compile(
    r"^backend/(scheduler/jobs\.py|api/__init__\.py|collectors/.*\.py|services/.*\.py)$"
)
TAILWIND_GLOB = re.compile(r"^frontend/(tailwind|postcss)\.config\.[jt]sx?$")


def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT)
        )
        return r.returncode, (r.stdout + r.stderr).strip()[:600]
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def check(payload: dict) -> list[str]:
    """Return advisory notes for an Edit/Write PostToolUse payload. Empty = clean."""
    tool_input = payload.get("tool_input", {})
    p = tool_input.get("file_path", "") or tool_input.get("path", "")
    try:
        rel = str(pathlib.Path(p).resolve().relative_to(ROOT))
    except (ValueError, OSError):
        rel = p
    if not rel:
        return []
    notes: list[str] = []
    py = str(ROOT / ".venv" / "bin" / "python")

    if DOCSTRING_GLOB.match(rel):
        rc, out = _run([py, "scripts/check_docstrings.py"], 4.0)
        if rc != 0:
            notes.append(
                f"ℹ docstring check failed (CI gate):\n{out}\n"
                f"→ run: {py} scripts/check_docstrings.py"
            )

    if ASSETS_GLOB.match(rel):
        rc, out = _run([py, "scripts/harness_analyze.py", "--check"], 4.0)
        if rc != 0:
            notes.append(
                f"ℹ harness_analyze.py --check failed (CI gate; new long skill missing "
                f"references/):\n{out}\n→ run: {py} scripts/harness_analyze.py"
            )

    if META_GLOB.match(rel):
        rc, out = _run([py, "scripts/generate_meta.py", "--check"], 5.0)
        if rc != 0:
            notes.append(
                f"ℹ docs/ARCHITECTURE.md numbers out of sync (CI gate):\n{out}\n"
                f"→ run: {py} scripts/generate_meta.py && "
                f"{py} scripts/generate_meta.py --check"
            )

    if TAILWIND_GLOB.match(rel):
        notes.append(
            "ℹ tailwind config changed — `npm run dev` does NOT hot-reload "
            "tailwind.config.*; restart dev server (frontend/src/AGENTS.md)"
        )

    return notes