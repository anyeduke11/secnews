#!/usr/bin/env python3
"""一次性迁移: knowledge/ → llm-wiki-2.0 (v0.5 M3.5 Task14)。

SPEC §1 / wiki v2 §9 Task 20: 实测 4152 items + 98 concepts (当前磁盘实际
4149 + 96) 从 knowledge/ 迁到 llm-wiki-2.0/。md 是真相源, 迁移 = 复制 +
frontmatter 增强 (幂等覆盖, 可重跑):

- items → llm-wiki-2.0/items/{id}.md:
    + confidence: 0.5 (LLM 失败默认, SPEC §13 Task13 t_confidence)
    + retention: {"initial": 1.0, "current_score": 1.0, "last_accessed": now}
- concepts → llm-wiki-2.0/concepts/{slug}.md (原样复制, 缺 updated_at 补 now)
- 种子 llm-wiki-2.0/retention.json: 全部迁移条目 (initial 1.0)
- 种子 llm-wiki-2.0/graph.json: 概念节点 + item 概念共现 uses 边

v0.4 knowledge/ 双轨保留 (不删除), M5 后手动可删 (SPEC §4 v0.4 兼容性)。

用法::

    python scripts/migrate_v04_to_llm_wiki.py --dry-run   # 只统计不写
    python scripts/migrate_v04_to_llm_wiki.py             # 真迁移 (幂等覆盖)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_ITEMS = ROOT / "knowledge" / "items"
SRC_CONCEPTS = ROOT / "knowledge" / "concepts"
DST_ITEMS = ROOT / "llm-wiki-2.0" / "items"
DST_CONCEPTS = ROOT / "llm-wiki-2.0" / "concepts"
RETENTION_PATH = ROOT / "llm-wiki-2.0" / "retention.json"
GRAPH_PATH = ROOT / "llm-wiki-2.0" / "graph.json"

sys.path.insert(0, str(ROOT))
from backend.services.concept_linker import GRAPH_PATH as _CL_GRAPH

# 复用 knowledge_sync 的 frontmatter 正则 (标准 ---\n 结尾)。
# 注意: 存量 items 多数为 "---#" 结尾 (关闭 --- 后直接跟 H1 标题, 无换行),
# knowledge_sync.parse_frontmatter 解析不了它们 (存量静默不同步的根因之一)。
# 迁移脚本用更宽容的正则覆盖两种结尾 (---\n / ---# / ---EOF)。
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---(?=[\s#]|\n|$)", re.DOTALL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(value) -> str:
    """把 frontmatter 值序列化为 YAML 子集 (对齐 knowledge_sync 解析器)。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _coerce_scalar(value: str):
    """把纯数字标量转 int/float (对齐 knowledge_sync._coerce_scalar)。"""
    if not value:
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_fm_text(text: str) -> dict | None:
    """宽容解析 frontmatter 块 (处理 ---\n 与 ---# 两种结尾)。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm: dict = {}
    current_key: str | None = None
    current_list: list = []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("- "):
            if current_key is not None and current_list:
                fm[current_key] = current_list
                current_list = []
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value == "null":
                value = None
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            elif value.startswith("[") and value.endswith("]"):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = _coerce_scalar(value)
            else:
                value = _coerce_scalar(value)
            current_key = key
            if value != "":
                fm[key] = value
                current_key = None
            else:
                current_list = []
        elif stripped.startswith("- ") and current_key is not None:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
    if current_key is not None and current_list:
        fm[current_key] = current_list
    return fm


def _split_fm(text: str) -> tuple[str | None, str]:
    """返回 (frontmatter 块, 正文)。无 frontmatter 时返回 (None, text)。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def _extract_id(fm_block: str, fallback: str) -> str:
    """从 frontmatter 块原始提取 id 字符串。

    不能用 _parse_fm_text 的通用解析: 纯数字/科学计数法 id (如 "006170206605"、
    "065483e77836") 会被 _coerce_scalar 转成 int/float (后者溢出成 inf → 9 条撞车)。
    id 永远是字符串 (12-hex 短哈希), 不参与数值化。
    """
    m = re.search(r"^id:\s*[\"']?([^\"'\n]+)[\"']?", fm_block, re.M)
    if m:
        return m.group(1).strip()
    return fallback


def _migrate_item(src: Path, dry_run: bool) -> dict:
    """迁移单条 item → llm-wiki-2.0/items/{id}.md, 返回统计。"""
    try:
        text = src.read_text(encoding="utf-8")
    except Exception as e:
        return {"status": "error", "id": src.stem, "msg": str(e)}
    fm_block, body = _split_fm(text)
    fm = _parse_fm_text(text)
    if fm_block is None or fm is None:
        return {"status": "skip_no_fm", "id": src.stem, "msg": "no frontmatter"}

    # id 用原始字符串 (防纯数字/科学计数法 id 被数值化撞车)
    item_id = _extract_id(fm_block, src.stem)
    new_lines = []
    if "confidence" not in fm:
        new_lines.append(f"confidence: {_serialize(0.5)}")
    if "retention" not in fm:
        new_lines.append(
            "retention: " + _serialize({
                "initial": 1.0,
                "current_score": 1.0,
                "last_accessed": _now_iso(),
            })
        )
    new_fm_block = fm_block.rstrip() + "\n" + "\n".join(new_lines).rstrip() + "\n"
    new_text = f"---\n{new_fm_block}---\n" + body

    if not dry_run:
        dst = DST_ITEMS / f"{item_id}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(dst)
    return {"status": "ok", "id": item_id, "src": str(src)}


def _migrate_concept(src: Path, dry_run: bool) -> dict:
    """迁移单条 concept → llm-wiki-2.0/concepts/{slug}.md。"""
    try:
        text = src.read_text(encoding="utf-8")
    except Exception as e:
        return {"status": "error", "id": src.stem, "msg": str(e)}
    fm_block, body = _split_fm(text)
    fm = _parse_fm_text(text)
    if fm_block is None or fm is None:
        return {"status": "skip_no_fm", "id": src.stem, "msg": "no frontmatter"}

    slug = fm.get("slug") or src.stem
    new_fm_block = fm_block.rstrip() + "\n"
    if "updated_at" not in fm:
        new_fm_block += f"updated_at: {_serialize(_now_iso())}\n"
    new_text = f"---\n{new_fm_block}---\n" + body

    if not dry_run:
        dst = DST_CONCEPTS / f"{slug}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(dst)
    return {"status": "ok", "id": slug}


def _seed_retention(item_ids: list[str], dry_run: bool) -> dict:
    """把迁移条目写进 retention.json (initial 1.0), 幂等合并。"""
    obj = {"$schema_version": "0.5.0", "entries": []}
    if RETENTION_PATH.exists():
        try:
            obj = json.loads(RETENTION_PATH.read_text(encoding="utf-8"))
        except Exception:
            obj = {"$schema_version": "0.5.0", "entries": []}
    entries = {e.get("id"): e for e in obj.get("entries", [])}
    added = 0
    now = _now_iso()
    for item_id in item_ids:
        if item_id not in entries:
            entries[item_id] = {
                "id": item_id,
                "initial_score": 1.0,
                "current_score": 1.0,
                "last_accessed": now,
                "decay_events": [],
            }
            added += 1
    obj["entries"] = list(entries.values())
    if not dry_run:
        tmp = RETENTION_PATH.with_suffix(RETENTION_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(RETENTION_PATH)
    return {"total": len(obj["entries"]), "added": added}


def _seed_graph(items: list[dict], dry_run: bool) -> dict:
    """种子 graph.json: 概念节点 (title/domain) + item 概念共现 uses 边。"""
    import backend.services.concept_linker as cl

    graph = {"$schema_version": "0.5.0", "nodes": [], "edges": []}
    if GRAPH_PATH.exists():
        try:
            graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        except Exception:
            graph = {"$schema_version": "0.5.0", "nodes": [], "edges": []}

    # 1) 概念节点 (从迁移后的 concepts md 读 title/domain)
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    for md in DST_CONCEPTS.glob("*.md"):
        fm = _parse_fm_text(md.read_text(encoding="utf-8", errors="replace"))
        if not fm:
            continue
        slug = fm.get("slug") or md.stem
        if slug not in nodes:
            nodes[slug] = {
                "id": slug,
                "label": fm.get("title") or slug,
                "domain": fm.get("domain"),
                "count": len(fm.get("source_items", []) or []),
                "wiki": "hotspot",
                "type": "concept",
            }
    graph["nodes"] = list(nodes.values())

    if not dry_run:
        tmp = GRAPH_PATH.with_suffix(GRAPH_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(GRAPH_PATH)

    # 2) uses 边 (共现累积) — 复用 concept_linker
    if dry_run:
        # dry-run 不写盘: 用临时路径避免污染真实 graph.json
        import tempfile
        cl.GRAPH_PATH = Path(tempfile.mkdtemp()) / "graph.json"
        cl.GRAPH_PATH.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        stats = cl.update_graph_from_batch(items)
        cl.GRAPH_PATH = _CL_GRAPH
        return stats
    return cl.update_graph_from_batch(items)


def main() -> int:
    parser = argparse.ArgumentParser(description="knowledge/ → llm-wiki-2.0 一次性迁移")
    parser.add_argument("--dry-run", action="store_true", help="只统计, 不写任何文件")
    args = parser.parse_args()

    if not SRC_ITEMS.exists() or not SRC_CONCEPTS.exists():
        print(f"ERROR: 源目录缺失 ({SRC_ITEMS} / {SRC_CONCEPTS})", file=sys.stderr)
        return 1

    item_files = sorted(SRC_ITEMS.glob("*.md"))
    concept_files = sorted(SRC_CONCEPTS.glob("*.md"))
    item_stats = [_migrate_item(f, args.dry_run) for f in item_files]
    concept_stats = [_migrate_concept(f, args.dry_run) for f in concept_files]

    item_ids = [s["id"] for s in item_stats if s["status"] == "ok"]
    item_ids_dedup = list(dict.fromkeys(item_ids))
    item_errors = [s for s in item_stats if s["status"] == "error"]
    concept_errors = [s for s in concept_stats if s["status"] == "error"]

    retention = _seed_retention(item_ids_dedup, args.dry_run)

    # items dict 用于 graph 边: 从源文件读 concepts (迁移不改 concepts 字段)
    graph_items = []
    for stat in item_stats:
        if stat["status"] != "ok":
            continue
        fm = _parse_fm_text(Path(stat["src"]).read_text(encoding="utf-8", errors="replace"))
        if fm:
            graph_items.append({"id": stat["id"], "concepts": fm.get("concepts", []) or []})
    graph = _seed_graph(graph_items, args.dry_run)

    result = {
        "dry_run": args.dry_run,
        "items_total": len(item_files),
        "items_migrated": len(item_ids_dedup),
        "items_skipped": len(item_files) - len(item_ids),
        "items_errors": len(item_errors),
        "concepts_total": len(concept_files),
        "concepts_migrated": sum(1 for s in concept_stats if s["status"] == "ok"),
        "concepts_errors": len(concept_errors),
        "retention": retention,
        "graph": graph,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 迁移必须 100%: 任何 error 都 fail
    if item_errors or concept_errors:
        print("ERROR: 存在迁移失败条目:", file=sys.stderr)
        for e in (item_errors + concept_errors)[:20]:
            print(f"  - {e['id']}: {e['msg']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
