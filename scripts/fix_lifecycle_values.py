#!/usr/bin/env python3
"""lifecycle 值域收敛 — 旧版 SAG 语义值一律迁为 ``"kl:publish"`` (默认 dry-run)。

背景 (KL 管线治理 T2, 2026-09-26):
  ``llm-wiki-2.0/items/`` 下存量 md 的 frontmatter 残留 pre-v1.7 值
  ``generate`` (带/不带引号) 与 ``signal``。owner 裁决: 两者均为"已发布为知识"
  的旧语义, 一律迁 ``kl:publish`` (与 domain.knowledge_models.LEGACY_TO_KL 的
  generate→kl:publish 同判定), 并统一为主流引号风格 ``"kl:publish"``。

实现约束:
  - **字节级外科式改写**: 只替换 frontmatter 块内 lifecycle 行的值部分,
    其余 frontmatter 与正文字节一律不动 (含 utf-8 解码失败的文件 —
    其 frontmatter 通常完好, 损坏在正文, 字节操作不受影响)。
  - 幂等: ``kl:publish`` 不在旧值集合内, 二次运行零改写。
  - 读路径兜底见 backend/wiki_fs/contract.get_lifecycle (防外部工具再写旧值)。

用法::

    python scripts/fix_lifecycle_values.py                 # 全量 dry-run 报告
    python scripts/fix_lifecycle_values.py --sample 5      # dry-run + 样例 diff
    python scripts/fix_lifecycle_values.py --apply         # 真实迁移 (先备份)
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ROOT = "llm-wiki-2.0/items"

# 迁移目标: 与主流 4179 个文件的带双引号风格一致 (抽样实测 2026-09-26)。
TARGET_VALUE = b'"kl:publish"'

# 旧值集合 (owner 裁决: generate / signal 均为已发布语义 → kl:publish)。
LEGACY_VALUES = ("generate", "signal")

# frontmatter 块边界 (字节域); 正文不参与匹配。
_FM_BLOCK_RE = re.compile(rb"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
# lifecycle 行: 前导空白 + 键 + 值 (可选单/双引号包裹, 大小写不敏感)。
_LIFECYCLE_LINE_RE = re.compile(
    rb"(?m)^([ \t]*)lifecycle:[ \t]*([\"']?)(?P<val>" + b"|".join(
        v.encode() for v in LEGACY_VALUES) + rb")([\"']?)[ \t]*$",
    re.IGNORECASE,
)


def rewrite_frontmatter(data: bytes) -> tuple[bytes, int]:
    """返回 (新字节, 替换行数)。无匹配时原样返回 (0 改写 → 幂等)。"""
    m = _FM_BLOCK_RE.match(data)
    if not m:
        return data, 0
    fm_block = m.group(1)
    new_fm, n = _LIFECYCLE_LINE_RE.subn(
        rb"\1lifecycle: " + TARGET_VALUE, fm_block,
    )
    if n == 0:
        return data, 0
    return data[: m.start(1)] + new_fm + data[m.end(1):], n


def collect(root: Path) -> list[Path]:
    return sorted(root.glob("*.md"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help=f"待扫描目录 (默认 {DEFAULT_ROOT})")
    ap.add_argument("--apply", action="store_true",
                    help="真实写盘 (缺省即 dry-run, 不产生任何副作用)")
    ap.add_argument("--sample", type=int, default=0, metavar="N",
                    help="打印前 N 个文件的 lifecycle 行 diff")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    if not root.is_dir():
        print(f"[error] 目录不存在: {root}", file=sys.stderr)
        return 2

    files = collect(root)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = REPO_ROOT / "backups" / f"fix_lifecycle_values_{stamp}"

    changed: list[tuple[Path, bytes, bytes]] = []
    undecodable = 0
    for f in files:
        data = f.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            undecodable += 1
        new_data, n = rewrite_frontmatter(data)
        if n:
            changed.append((f, data, new_data))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== fix_lifecycle_values [{mode}] ==")
    print(f"扫描 {len(files)} 个 md, 需迁移 {len(changed)} 个 "
          f"(旧值 {', '.join(LEGACY_VALUES)} → {TARGET_VALUE.decode()})")
    if undecodable:
        print(f"  其中 {undecodable} 个文件 utf-8 解码失败 "
              f"(frontmatter 字节级处理, 不受影响; 编码损坏须单独修复)")
    if args.sample:
        for f, before, after in changed[: args.sample]:
            old_line = next(
                ln for ln in before.split(b"\n") if b"lifecycle:" in ln)
            new_line = next(
                ln for ln in after.split(b"\n") if b"lifecycle:" in ln)
            print(f"  {f.relative_to(REPO_ROOT)}: "
                  f"{old_line.decode('utf-8', 'replace')!r} -> "
                  f"{new_line.decode('utf-8', 'replace')!r}")

    if not args.apply:
        print("\n[dry-run] 未写盘。确认后加 --apply 执行 (会先备份到 backups/)。")
        return 0

    if not changed:
        print("无需迁移。")
        return 0

    backup_dir.mkdir(parents=True, exist_ok=False)
    for f, _before, after in changed:
        rel = f.relative_to(REPO_ROOT)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        tmp = f.with_name(f.name + ".fixtmp")
        tmp.write_bytes(after)
        tmp.replace(f)
    print(f"已迁移 {len(changed)} 个文件; 原件备份于 {backup_dir.relative_to(REPO_ROOT)}")
    print("回滚: git checkout -- <路径> (md 均已提交), 或从备份目录拷回。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
