#!/usr/bin/env python3
"""修复 wiki frontmatter 的两类历史损坏 (默认 --dry-run, 不写盘)。

损坏成因 (两处独立缺陷叠加):
  A. json.dumps 默认 ensure_ascii=True → 中文标签被写成字面 ``\\uXXXX`` 存进
     DB 与 md; ``_unquote`` 当年不解码, 于是每轮 md→DB→md 都把转义文本
     再转义一次。
  B. ``_quote`` 加双引号时不转义内层 ``"`` 与 ``\\`` → 含 JSON 的值
     (如 ``retention``) 写成非法 YAML: ``retention: "{"initial": 1.0}"``。

本脚本只做**逐行外科式重写**: 仅改写真正损坏的行, 不重新序列化整个
frontmatter — 避免把键序/引号风格的全量归一化混进数据修复 diff。
解码与转义复用 backend.wiki_fs.contract (单一真相源), 不在这里重实现。

用法::

    python scripts/fix_wiki_frontmatter_escape.py                 # 全量 dry-run 报告
    python scripts/fix_wiki_frontmatter_escape.py --sample 3      # dry-run + 打印样例 diff
    python scripts/fix_wiki_frontmatter_escape.py --apply         # 真实修复 (先备份到 backups/)
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.wiki_fs.contract import (  # noqa: E402  (需先插 sys.path)
    _quote,
    _decode_escapes,
    _unescape_dq,
)

DEFAULT_ROOTS = (
    "llm-wiki-2.0/items",
    "llm-wiki-2.0/concepts",
    "knowledge/items",
    "knowledge/concepts",
)

_FM_BLOCK_RE = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---)", re.DOTALL)
# 一行拆成: 前导 (缩进 + 可选 "- ") / 可选 "key: " / 值
_LINE_RE = re.compile(r"\A(?P<head>[ \t]*(?:-[ \t]+)?(?:[A-Za-z0-9_]+:[ \t]+)?)(?P<val>.*)\Z")
_ESCAPED_CJK_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _fix_value(val: str) -> tuple[str, str | None]:
    """返回 (新值, 修复类别 | None)。类别: escape / illegal_quote。"""
    if not val:
        return val, None

    # YAML flow 序列 (tags/concepts/sources/related_items/tech_stack): 只解码转义,
    # 保持数组形态。解码结果含 [ ] " 会被 _needs_quote 判成需要加引号, 一旦包上引号
    # 列表就退化成字符串, 而 knowledge_sync.py:171 对非 list 的 tags 静默置 []。
    if val.startswith("[") and val.endswith("]"):
        fixed = _decode_escapes(val)
        return (fixed, "escape") if fixed != val else (val, None)

    # 双引号标量: 先按 YAML 语义解出真实字符串, 再用契约的 _quote 重新落地。
    # 这一步同时修掉 B 类 (内层未转义引号) 与 A 类 (引号内的 \uXXXX)。
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        inner = val[1:-1]
        decoded = _unescape_dq(inner)
        escaped_again = '"' in decoded or "\\" in decoded
        if escaped_again or _ESCAPED_CJK_RE.search(inner):
            category = "illegal_quote" if escaped_again else "escape"
            return _quote(decoded), category
        return val, None

    if len(val) >= 2 and val[0] == "'" and val[-1] == "'":
        return val, None  # 单引号内反斜杠本就字面, 不属本次损坏形态

    if _ESCAPED_CJK_RE.search(val):
        return _quote(_decode_escapes(val)) if _needs_quote(val) else _decode_escapes(val), "escape"

    return val, None


def _needs_quote(original_val: str) -> bool:
    """解码后是否必须加引号 (裸值里出现了 YAML 结构字符)。"""
    decoded = _decode_escapes(original_val)
    return decoded != decoded.strip() or any(c in decoded for c in ':{}[]&*?|>!%@`"\'\\,')


def repair_text(text: str) -> tuple[str, dict[str, int]]:
    """只重写 frontmatter 块内的受损行; 正文一字不动。"""
    m = _FM_BLOCK_RE.match(text)
    if not m:
        return text, {}

    head, fm_block, tail = m.group(1), m.group(2), m.group(3)
    stats: dict[str, int] = {}
    out_lines = []
    for line in fm_block.split("\n"):
        lm = _LINE_RE.match(line)
        if not lm:
            out_lines.append(line)
            continue
        new_val, category = _fix_value(lm.group("val"))
        if category is None or new_val == lm.group("val"):
            # 值未真正改变 (已修好的行会被重新判定) — 不计入, 避免无意义重写
            out_lines.append(line)
            continue
        stats[category] = stats.get(category, 0) + 1
        out_lines.append(lm.group("head") + new_val)

    if not stats:
        return text, {}
    return head + "\n".join(out_lines) + tail + text[m.end():], stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", dest="roots",
                    help=f"待扫描目录 (可重复; 默认 {', '.join(DEFAULT_ROOTS)})")
    ap.add_argument("--apply", action="store_true",
                    help="真实写盘 (缺省即 --dry-run, 不产生任何副作用)")
    ap.add_argument("--sample", type=int, default=0, metavar="N", help="dry-run 时打印前 N 个样例 diff")
    ap.add_argument("--limit", type=int, default=0, metavar="N", help="只处理前 N 个文件 (冒烟用)")
    args = ap.parse_args(argv)

    roots = [Path(r) for r in (args.roots or DEFAULT_ROOTS)]
    files: list[Path] = []
    for r in roots:
        base = REPO_ROOT / r
        if not base.is_dir():
            print(f"[warn] 目录不存在, 跳过: {r}", file=sys.stderr)
            continue
        files.extend(sorted(base.glob("*.md")))
    if args.limit:
        files = files[: args.limit]

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = REPO_ROOT / "backups" / f"fix_wiki_frontmatter_escape_{stamp}"

    totals: dict[str, int] = {}
    changed: list[tuple[Path, str, str]] = []
    anomalies: list[str] = []

    for f in files:
        try:
            before = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            anomalies.append(f"{f}: 读取失败 {exc}")
            continue
        after, stats = repair_text(before)
        if not stats:
            continue
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v
        changed.append((f, before, after))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== fix_wiki_frontmatter_escape [{mode}] ==")
    print(f"扫描 {len(files)} 个 md, 需修复 {len(changed)} 个")
    for k in sorted(totals):
        print(f"  {k:14s} {totals[k]:6d} 行")

    if args.sample:
        for f, before, after in changed[: args.sample]:
            print(f"\n--- {f.relative_to(REPO_ROOT)}")
            for line in list(difflib.unified_diff(
                    before.splitlines(), after.splitlines(), lineterm="", n=0))[2:]:
                print(f"  {line}")

    if not args.apply:
        print("\n[dry-run] 未写盘。确认无误后加 --apply 执行 (会先备份到 backups/)。")
        return 0

    if not changed:
        print("无需修复。")
        return 0

    backup_dir.mkdir(parents=True, exist_ok=False)
    for f, _before, after in changed:
        rel = f.relative_to(REPO_ROOT)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        tmp = f.with_name(f.name + ".fixtmp")
        tmp.write_text(after, encoding="utf-8")
        tmp.replace(f)
    print(f"已修复 {len(changed)} 个文件; 原件备份于 {backup_dir.relative_to(REPO_ROOT)}")
    print("回滚: rm -rf 目标目录后从备份拷回, 或 git checkout -- <路径> (这些 md 均已提交)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
