"""Phase 1j Task 10.7: 清理 knowledge/learning/tasks/pending/ 队列。

策略 (spec 10.7.3 + 10.7.4):
- 124 条 compile 任务 → 按 created_at DESC 保留最新 10 个，其余 114 条移到 failed/
- 2 条 generate_learning_plan + 1 条 generate_soul → 保留（非 compile 类型，数量合理）
- 所有任务 created_at 均在 2 天内，无 > 7 天过期任务
- 移到 failed/ 的任务在 frontmatter 追加 reason 字段

成功标准: pending/ 总数 < 20 (预计 13)
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

PENDING_DIR = Path("/Users/duke/Documents/hotspot/knowledge/learning/tasks/pending")
FAILED_DIR = Path("/Users/duke/Documents/hotspot/knowledge/learning/tasks/failed")
KEEP_LATEST_COMPILE = 10


def parse_task(path: Path) -> dict:
    """Parse task .md frontmatter + return dict with task_type, created_at, path."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"task_type": "unknown", "created_at": "", "path": path}
    parts = text.split("---", 2)
    frontmatter = parts[1] if len(parts) >= 3 else ""
    task_type_match = re.search(r'task_type:\s*"?([^"\n]+)"?', frontmatter)
    created_match = re.search(r'created_at:\s*"?([^"\n]+)"?', frontmatter)
    return {
        "task_type": (task_type_match.group(1).strip() if task_type_match else "unknown"),
        "created_at": (created_match.group(1).strip() if created_match else ""),
        "path": path,
        "text": text,
    }


def main() -> None:
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    for md in PENDING_DIR.glob("task-*.md"):
        tasks.append(parse_task(md))

    compile_tasks = [t for t in tasks if t["task_type"] == "compile"]
    other_tasks = [t for t in tasks if t["task_type"] != "compile"]
    print(f"[scan] total={len(tasks)} compile={len(compile_tasks)} other={len(other_tasks)}")

    # Sort compile by created_at DESC; keep newest 10
    compile_tasks.sort(key=lambda t: t["created_at"], reverse=True)
    keep_compile = compile_tasks[:KEEP_LATEST_COMPILE]
    drop_compile = compile_tasks[KEEP_LATEST_COMPILE:]
    print(f"[plan] keep compile={len(keep_compile)} drop compile={len(drop_compile)}")

    # Move drop_compile to failed/ with reason appended
    now_iso = datetime.now(timezone.utc).isoformat()
    moved = 0
    for t in drop_compile:
        src: Path = t["path"]
        dst = FAILED_DIR / src.name
        # Append reason to frontmatter
        text = t["text"]
        if text.startswith("---"):
            parts = text.split("---", 2)
            frontmatter = parts[1] if len(parts) >= 3 else ""
            # Append reason fields before closing ---
            extra = (
                f"\nreason: \"superseded:Phase 1j batch compile complete; queue cleanup\"\n"
                f"failed_at: \"{now_iso}\"\n"
            )
            new_frontmatter = frontmatter.rstrip("\n") + extra
            new_text = f"---{new_frontmatter}\n---" + (parts[2] if len(parts) >= 3 else "")
            dst.write_text(new_text, encoding="utf-8")
            src.unlink()
        else:
            shutil.move(str(src), str(dst))
        moved += 1

    remaining = list(PENDING_DIR.glob("task-*.md"))
    print(f"[done] moved {moved} compile tasks to failed/")
    print(f"[verify] pending/ remaining = {len(remaining)} (target < 20)")

    # Breakdown of remaining
    remaining_types = {}
    for md in remaining:
        info = parse_task(md)
        remaining_types[info["task_type"]] = remaining_types.get(info["task_type"], 0) + 1
    print(f"[verify] remaining breakdown: {remaining_types}")

    if len(remaining) >= 20:
        raise SystemExit(f"FAIL: pending/ still has {len(remaining)} tasks (>= 20)")
    print("[ok] pending/ < 20")


if __name__ == "__main__":
    main()
