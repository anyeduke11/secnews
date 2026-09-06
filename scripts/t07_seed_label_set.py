#!/usr/bin/env python3
"""t07_seed_label_set — T07 监督批次起步标注集加载器.

读取 dev_data/annotation_set_seed_60_80.json, 通过 V1AdmissionService
写入 admission_label + admission_set + admission_set_items.

约束:
  - dry-run 默认 (打印会写入多少条, 不真落库)
  - --apply 真落库
  - 隔离目录: 接受 --db 指向临时库; 不写真实库 (默认走 env HOTSPOT_DB_PATH, T01 conftest 自动隔离)
  - 加载前 assertion: 维度 × 值 都在 ANNOTATION_DIMENSIONS 内, 否则抛 ValueError

输出: 一条 admission_set (name="t07-supervisor-v1") + N 条 admission_label +
N*8 条 admission_set_items (每 material 8 维 × 1 label).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 让脚本可独立运行 (python scripts/t07_seed_label_set.py --apply) — 加 REPO_ROOT 到 sys.path
REPO_ROOT_HERE = Path(__file__).resolve().parent.parent
if str(REPO_ROOT_HERE) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_HERE))

REPO_ROOT = REPO_ROOT_HERE
DEFAULT_SEED = REPO_ROOT / "dev_data" / "annotation_set_seed_60_80.json"
SET_NAME = "t07-supervisor-v1"
SCHEMA_VERSION = "v1.0"


def _validate(annotations: list[dict[str, Any]]) -> None:
    """加载前 assertion: 每条 annotations 的 dimension × value 都在 ANNOTATION_DIMENSIONS 内."""
    from backend.services.v1_admission_service import ANNOTATION_DIMENSIONS

    for i, ann in enumerate(annotations):
        labels = ann.get("labels") or {}
        for dim, val in labels.items():
            if dim not in ANNOTATION_DIMENSIONS:
                raise ValueError(
                    f"annotation[{i}] 未知维度 {dim!r}; 允许: {sorted(ANNOTATION_DIMENSIONS)}"
                )
            if val not in ANNOTATION_DIMENSIONS[dim]:
                raise ValueError(
                    f"annotation[{i}] 维度 {dim} 值 {val!r} 越界; "
                    f"允许: {ANNOTATION_DIMENSIONS[dim]}"
                )


def _load_seed(seed_path: Path) -> dict[str, Any]:
    if not seed_path.exists():
        print(f"ERROR: 找不到 seed 文件 {seed_path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(seed_path.read_text(encoding="utf-8"))


def dry_run(seed: dict[str, Any]) -> None:
    annotations = seed.get("annotations", [])
    print(f"=== dry-run ===")
    print(f"set name        : {SET_NAME}")
    print(f"schema version  : {SCHEMA_VERSION}")
    print(f"annotation rows : {len(annotations)}")
    print(f"label rows      : {len(annotations) * 8}  (每条 8 维)")
    set_items = len(annotations) * 8
    print(f"set_items rows  : {set_items}")
    print(f"source seed     : {seed.get('_meta', {}).get('version', '?')}")
    print(f"first 3 samples :")
    for ann in annotations[:3]:
        print(f"  {ann['material_id']:>8}  annotator={ann['annotator']}  "
              f"labels={list(ann['labels'].keys())}")


def apply(seed: dict[str, Any]) -> None:
    """真落 admission_label + admission_set + admission_set_items.

    隔离: 调用方通过 conftest 或 env HOTSPOT_DB_PATH 隔离; 脚本本身不直接写真实库.
    """
    from backend.services.v1_admission_service import V1AdmissionService

    annotations = seed.get("annotations", [])
    svc = V1AdmissionService()
    set_id = svc.create_label_set(SET_NAME, schema_version=SCHEMA_VERSION)
    if set_id <= 0:
        print("ERROR: create_label_set 失败 (返回 0, 通常因表不存在 = migration 097 未跑)",
              file=sys.stderr)
        sys.exit(2)
    print(f"created admission_set id={set_id} name={SET_NAME}")

    failed = 0
    for ann in annotations:
        try:
            svc.add_to_set(set_id, ann["material_id"], ann["labels"])
        except (ValueError, RuntimeError) as e:
            failed += 1
            print(f"  skip {ann['material_id']}: {e}", file=sys.stderr)

    items = svc.get_set_items(set_id)
    print(f"\n=== apply 结果 ===")
    print(f"  requested  : {len(annotations)}")
    print(f"  failed     : {failed}")
    print(f"  set_items  : {len(items)}")
    print(f"  distinct materials: {len({i['material_id'] for i in items})}")
    # 维度覆盖统计
    dim_counts: dict[str, set[str]] = {}
    for item in items:
        dim_counts.setdefault(item["dimension"], set()).add(item["value"])
    print(f"  dimension coverage:")
    for dim, vals in sorted(dim_counts.items()):
        print(f"    {dim:>15}: {len(vals)} 档  ({sorted(vals)})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T07 监督批次起步标注集加载器"
    )
    parser.add_argument(
        "--seed", type=Path, default=DEFAULT_SEED,
        help=f"seed JSON 路径 (默认 {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="真落 admission_label + admission_set_items (默认 dry-run)",
    )
    args = parser.parse_args()

    seed = _load_seed(args.seed)
    _validate(seed.get("annotations", []))

    if args.apply:
        apply(seed)
    else:
        dry_run(seed)


if __name__ == "__main__":
    main()
