"""hotspot ZCode hooks package.

Submodules:
  bash_risk          — Bash PreToolUse risk warnings (read-only consumer of MEMORY.md patterns)
  post_edit_quality  — Edit/Write PostToolUse quality-gate dispatcher

All checks are advisory: emit notes via additionalContext, never block (exit 0 / 1 only).
"""