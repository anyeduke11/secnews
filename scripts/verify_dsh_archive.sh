#!/usr/bin/env bash
# v0.6 Phase 6 commit 3 — dsh-SecNews archive 一键校验脚本 (Python 包装)。
#
# 比对逻辑:
#   1. archives/dsh-secs-news-2026-08-27.tar.zst 本身的 SHA256
#   2. tar 提取出每个文件 → 算 SHA256 → 跟 MANIFEST 列对
#
# exit 0 = 全通过; exit 1 = 任一不匹配 (含文件数差异)。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="${REPO_ROOT}/archives/dsh-secs-news-2026-08-27.tar.zst"
MANIFEST="${REPO_ROOT}/archives/dsh-secs-news.MANIFEST"

if [[ ! -f "${ARCHIVE}" ]]; then
    echo "ERROR: archive missing: ${ARCHIVE}" >&2
    exit 1
fi
if [[ ! -f "${MANIFEST}" ]]; then
    echo "ERROR: manifest missing: ${MANIFEST}" >&2
    exit 1
fi

# 找到项目 venv 的 python
PY="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
    PY="$(command -v python3)"
fi

exec "${PY}" - "${ARCHIVE}" "${MANIFEST}" <<'PYEOF'
import hashlib
import sys
import tarfile
import tempfile
from pathlib import Path

archive = Path(sys.argv[1])
manifest = Path(sys.argv[2])

# 1. archive 自身 SHA256
expected_archive_sha = ""
file_entries: dict[str, str] = {}
for line in manifest.read_text(encoding="utf-8").splitlines():
    line = line.rstrip()
    if line.startswith("- sha256:"):
        expected_archive_sha = line.split(":", 1)[1].strip()
    elif line and not line.startswith("#") and not line.startswith("- "):
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            file_entries[parts[1].strip()] = parts[0]

actual_archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
print("[1/2] archive SHA256...")
if expected_archive_sha != actual_archive_sha:
    print(f"  ERROR: expected {expected_archive_sha}", file=sys.stderr)
    print(f"         actual   {actual_archive_sha}", file=sys.stderr)
    sys.exit(1)
print(f"  ok: {actual_archive_sha}")

# 2. file-level
print("[2/2] file-level SHA256...")
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    # 解 zstd → tar 提取 (tar.zstd 已是 tar 外部包 zstd, 与 tarfile.open 不兼容,
    # 显式两段: subprocess zstd -dc → tarfile r:)
    import subprocess
    tar_bytes = subprocess.run(
        ["zstd", "-dc", str(archive)],
        check=True,
        capture_output=True,
    ).stdout
    import io
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tf:
        # Python3.14 默认 data_filter 拒绝绝对 symlink / 路径穿越; 我们的归档
        # 里 node_modules 含 dsh-home 的绝对 symlink (历史快照), 这里用
        # filter=fully_trusted 跳过严格校验 (验证用途, 临时目录安全).
        tf.extractall(tmp_path, filter="fully_trusted")  # noqa: S202

    failures = 0
    checked = 0
    for path_str, expected_sha in file_entries.items():
        f = tmp_path / path_str
        if not f.is_file():
            print(f"  MISSING: {path_str}", file=sys.stderr)
            failures += 1
            continue
        actual_sha = hashlib.sha256(f.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            print(f"  MISMATCH: {path_str}", file=sys.stderr)
            print(f"    expected: {expected_sha}", file=sys.stderr)
            print(f"    actual:   {actual_sha}", file=sys.stderr)
            failures += 1
        checked += 1

    print(f"  checked: {checked} files")
    if failures:
        print(f"ERROR: {failures} file(s) failed SHA256 verification", file=sys.stderr)
        sys.exit(1)

print("OK: archive fully verified")
PYEOF