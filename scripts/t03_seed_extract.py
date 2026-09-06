#!/usr/bin/env python3
"""
t03_seed_extract — 从生产库抽取样本, 脱敏后落 dev_data/seed.json.

来源映射 (T03-D):
  Subject       ← knowledge_concepts (98 行, 取 20)
  Material      ← hotspots (7223 行, 随机取 25)
  Signal        ← hotspots 作为事件 (取 20, 与 Material 同源但不同视角)
  Case          ← todos (6 行, 全取)
  Judgment      ← 合成 (10, 关联 Case)
  Action        ← 合成 (10, 关联 Judgment)
  Run           ← agent_runs (321 行, 取 15)
  Artifact      ← 合成 (10, 关联 Run)
  Knowledge     ← knowledge_concepts 另一子集 (15, 与 Subject 不重叠)

脱敏规则:
  - url: 保留域名, 路径替换为 /path/<id>
  - title/summary/claim/plan: 截断至 80 字符, 或替换为 "[REDACTED]"
  - source: 保留来源名 (非 PII)
  - hash: 替换为 "seed_<sha256(original)>[:16]" (可复现)
  - 时间戳: 保留结构, 年改为 2025 (避免暴露真实采集窗口)

输出: dev_data/seed.json (gitignored, dev 环境用)
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

random.seed(2026)  # 可复现

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"
OUT_PATH = REPO_ROOT / "dev_data" / "seed.json"


# ---------------------------------------------------------------------------
# 脱敏工具
# ---------------------------------------------------------------------------

def _redact_text(text: str | None, max_len: int = 80) -> str | None:
    """截断文本至 max_len, 末尾标 …"""
    if not text:
        return None
    text = str(text).strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def _fake_url(url: str | None, idx: int) -> str | None:
    """把真实 URL 替换为假域名, 保留结构."""
    if not url:
        return None
    domain = url.split("/")[2] if "://" in url else "example.com"
    return f"https://{domain}/path/{idx}"


def _seed_hash(value: str) -> str:
    """可复现的伪 hash (不暴露原始值)."""
    return "seed_" + hashlib.sha256(value.encode()).hexdigest()[:16]


def _fix_time(iso: str | None) -> str | None:
    """把时间戳年份统一为 2025, 保留月日时分秒结构."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.replace(year=2025, tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:
        return iso


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ---------------------------------------------------------------------------
# 抽取函数
# ---------------------------------------------------------------------------

def _fetch_subjects(con: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """从 knowledge_concepts 抽取 Subject (关注对象)."""
    rows = con.execute(
        "SELECT slug, title, domain, entity_type, updated_at FROM knowledge_concepts LIMIT ?",
        (limit,),
    ).fetchall()
    subjects = []
    for i, (slug, title, domain, entity_type, updated_at) in enumerate(rows, 1):
        etype = (entity_type or "custom").lower()
        if etype not in {"product", "vendor", "cve", "technique", "regulation", "person", "org", "custom"}:
            etype = "custom"
        subjects.append(
            {
                "id": f"SUBJ{str(i).zfill(3)}",
                "entity_type": etype,
                "name": _redact_text(title, 60) or slug,
                "aliases": [slug],
                "importance": "normal",
                "revision": 1,
                "context_revision": None,
                "tags": [domain] if domain else [],
                "notes": None,
                "created_at": _fix_time(updated_at) or _utcnow(),
                "updated_at": _fix_time(updated_at) or _utcnow(),
                "allowed_actions": ["edit", "archive"],
                "reason": None,
            }
        )
    return subjects


def _fetch_materials(con: sqlite3.Connection, limit: int = 25) -> list[dict[str, Any]]:
    """从 hotspots 抽取 Material (原始资料)."""
    rows = con.execute(
        "SELECT id, title, source, url, published_at, fetched_at, summary, category "
        "FROM hotspots WHERE url IS NOT NULL AND url != '' LIMIT ?",
        (limit,),
    ).fetchall()
    materials = []
    for i, (hid, title, source, url, pub, fetched, summary, category) in enumerate(rows, 1):
        src = _redact_text(source, 30) or "unknown"
        mat_url = _fake_url(url, i)
        content_key = f"{src}|{mat_url}|{pub or fetched or ''}"
        materials.append(
            {
                "id": f"MAT{str(i).zfill(3)}",
                "source": src,
                "url": mat_url,
                "title": _redact_text(title, 80),
                "author": None,
                "published_at": _fix_time(pub),
                "first_seen_at": _fix_time(fetched) or _utcnow(),
                "hash": _seed_hash(content_key),
                "parser_version": "seed_v1.0",
                "snapshot_path": None,
                "revision": 1,
                "extra": {"category": category, "original_id": hid},
                "quality_flags": [],
                "is_fallback": False,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": [],
                "reason": None,
            }
        )
    return materials


def _fetch_signals(materials: list[dict[str, Any]], subjects: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """从 Material 集合派生 Signal (情报事件)."""
    signals = []
    for i, mat in enumerate(materials[:limit]):
        subj = random.choice(subjects) if subjects else None
        signals.append(
            {
                "id": f"SIG{str(i+1).zfill(3)}",
                "subject_id": subj["id"] if subj else None,
                "material_id": mat["id"],
                "summary": _redact_text(mat.get("title"), 100) or "signal",
                "occurred_at": mat.get("published_at") or mat.get("first_seen_at") or _utcnow(),
                "admission_rule_version": "v1.0_seed",
                "admission_reason": "seed_extraction",
                "supersedes_signal_id": None,
                "confidence": random.choice(["likely", "verified", "unverified"]),
                "revision": 1,
                "status": "likely",
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["promote_verified", "retract"],
            }
        )
    return signals


def _fetch_cases(con: sqlite3.Connection, subjects: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """从 todos 抽取 Case (工作事项), 不足则合成补足."""
    rows = con.execute(
        "SELECT id, title, note, status, important, urgent, deadline, created_at, updated_at "
        "FROM todos LIMIT ?",
        (limit,),
    ).fetchall()
    cases = []
    for tid, title, note, status, important, urgent, deadline, created_at, updated_at in rows:
        subj = random.choice(subjects) if subjects else None
        priority = "p1" if urgent else ("p2" if important else "p3")
        cases.append(
            {
                "id": f"CASE{str(tid).zfill(3)}",
                "title": _redact_text(title, 60) or f"事项 #{tid}",
                "question": _redact_text(note, 120) or f"处理事项 #{tid}",
                "goal": "完成研判并形成可执行结论",
                "scope": None,
                "priority": priority,
                "status": status if status in {"open", "in_progress", "blocked", "closed", "archived"} else "open",
                "due_at": _fix_time(deadline),
                "subject_id": subj["id"] if subj else None,
                "related_subject_ids": [s["id"] for s in random.sample(subjects, min(2, len(subjects)))] if subjects else [],
                "related_signal_ids": [],
                "related_case_ids": [],
                "tags": [],
                "owner_role": "user",
                "revision": 1,
                "closed_at": _fix_time(updated_at) if status in {"closed", "archived"} else None,
                "created_at": _fix_time(created_at) or _utcnow(),
                "updated_at": _fix_time(updated_at) or _utcnow(),
                "allowed_actions": ["edit", "close", "archive"],
                "reason": None,
            }
        )
    # 若不足 limit, 合成补足
    for i in range(len(cases), limit):
        subj = random.choice(subjects) if subjects else None
        cases.append(
            {
                "id": f"CASE{str(100 + i).zfill(3)}",
                "title": f"合成研判事项 #{i+1}",
                "question": f"分析样本 #{i+1} 的安全影响与行动建议",
                "goal": "形成判断与行动",
                "scope": None,
                "priority": random.choice(["p0", "p1", "p2", "p3"]),
                "status": random.choice(["open", "in_progress", "closed"]),
                "due_at": None,
                "subject_id": subj["id"] if subj else None,
                "related_subject_ids": [],
                "related_signal_ids": [],
                "related_case_ids": [],
                "tags": [],
                "owner_role": "user",
                "revision": 1,
                "closed_at": None,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["edit", "close", "archive"],
                "reason": None,
            }
        )
    return cases


def _fetch_judgments(cases: list[dict[str, Any]], materials: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """合成 Judgment (判断)."""
    claim_types = ["finding", "assessment", "recommendation", "warning", "hypothesis"]
    confidences = ["low", "medium", "high", "proved"]
    judgments = []
    for i in range(min(limit, len(cases))):
        case = cases[i]
        mat = random.choice(materials) if materials else None
        claim_text = f"样本判断 #{i+1}: 基于现有证据, 该事项的核心风险为 [REDACTED], 建议优先跟进相关领域动态。"
        judgments.append(
            {
                "id": f"JUDG{str(i+1).zfill(3)}",
                "case_id": case["id"],
                "subject_id": case.get("subject_id"),
                "claim_type": random.choice(claim_types),
                "claim": claim_text,
                "conditions": "适用条件: v1.0_seed 数据集",
                "confidence": random.choice(confidences),
                "evidence_refs": [
                    {
                        "material_id": mat["id"],
                        "signal_id": None,
                        "chunk_id": None,
                        "offset": None,
                        "hash": mat.get("hash", "seed_unknown"),
                        "quote": _redact_text(mat.get("title"), 200),
                    }
                ] if mat else [],
                "counter_evidence_refs": [],
                "unknowns": ["完整影响范围待评估"],
                "status": random.choice(["draft", "published"]),
                "revision": 1,
                "wiki_path": None,
                "content_hash": _seed_hash(claim_text),
                "published_at": _utcnow() if random.random() > 0.5 else None,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["edit", "publish", "discard"] if random.random() > 0.5 else ["view_only"],
            }
        )
    return judgments


def _fetch_actions(cases: list[dict[str, Any]], judgments: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """合成 Action (行动)."""
    actions = []
    for i in range(min(limit, len(cases))):
        case = cases[i]
        judg = judgments[i] if i < len(judgments) else None
        plan_text = f"## 行动计划 #{i+1}\n\n1. 收集更多样本\n2. 完成初步分析\n3. 输出结论\n\n验收标准: 完成上述步骤。"
        actions.append(
            {
                "id": f"ACT{str(i+1).zfill(3)}",
                "case_id": case["id"],
                "judgment_id": judg["id"] if judg else f"JUDG{str(i+1).zfill(3)}",
                "title": f"行动 #{i+1}: {case['title'][:40]}",
                "scope": None,
                "plan": plan_text,
                "plan_hash": _seed_hash(plan_text),
                "tool_versions": {"seed": "v1.0"},
                "expected_artifacts": ["report"],
                "success_criteria": "产出至少 1 份报告",
                "expires_at": None,
                "status": random.choice(["planned", "approved", "running", "succeeded"]),
                "approved_by": None,
                "approved_at": None,
                "revision": 1,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["edit", "cancel", "start"],
            }
        )
    return actions


def _fetch_runs(con: sqlite3.Connection, actions: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    """从 agent_runs 抽取 Run (执行运行)."""
    rows = con.execute(
        "SELECT id, agent, protocol, task_kind, trigger_source, started_at, finished_at, "
        "status, duration_ms, result_excerpt, error FROM agent_runs LIMIT ?",
        (limit,),
    ).fetchall()
    runs = []
    for i, (rid, agent, protocol, task_kind, trigger, started, finished, status, dur_ms, result, error) in enumerate(rows):
        action = actions[i % len(actions)] if actions else None
        runs.append(
            {
                "id": f"run_{rid:012d}",
                "action_id": action["id"] if action else f"ACT{str(i+1).zfill(3)}",
                "attempt": 1,
                "skill_id": task_kind or "unknown",
                "protocol": random.choice(["dsh", "pi", "direct", "mock"]),
                "trigger_source": trigger if trigger in {"user", "agent", "system", "scheduled", "webhook"} else "system",
                "idempotency_key": f"seed_run_{rid:012d}",
                "status": "succeeded" if status == "ok" else ("failed" if status == "failed" else "cancelled"),
                "inputs": {"task_kind": task_kind, "seed": True},
                "steps": [],
                "budget_tokens": None,
                "budget_seconds": None,
                "started_at": _fix_time(started) or _utcnow(),
                "finished_at": _fix_time(finished) or _utcnow(),
                "duration_ms": dur_ms,
                "result_excerpt": _redact_text(result, 200),
                "error": _redact_text(error, 200) if error else None,
                "artifact_ids": [],
                "revision": 1,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["view_only"],
            }
        )
    return runs


def _fetch_artifacts(runs: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """合成 Artifact (产物)."""
    kinds = ["report", "file", "data", "chart", "code_patch", "message"]
    formats = ["md", "json", "csv", "png", "txt", "zip"]
    artifacts = []
    for i in range(min(limit, len(runs))):
        run = runs[i]
        kind = random.choice(kinds)
        fmt = random.choice(formats)
        title = f"{kind}_run{run['id'][-6:]}_{i+1}"
        content = f"# {title}\n\nseed artifact content for testing."
        artifacts.append(
            {
                "id": f"ART{str(i+1).zfill(3)}",
                "run_id": run["id"],
                "kind": kind,
                "title": title,
                "content_ref": None,
                "content_hash": _seed_hash(content),
                "format": fmt,
                "size_bytes": len(content.encode()),
                "verified_by": None,
                "verified_at": None,
                "verified_result": None,
                "accepted_by": None,
                "accepted_at": None,
                "accepted_note": None,
                "status": random.choice(["pending", "verified", "accepted"]),
                "revision": 1,
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["view_only"],
            }
        )
    return artifacts


def _fetch_knowledge(con: sqlite3.Connection, subjects: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    """从 knowledge_concepts 抽取 Knowledge (经验), 避开 Subject 已用行."""
    # 取与 _fetch_subjects 不同 offset 的行
    rows = con.execute(
        "SELECT slug, title, domain, entity_type, updated_at, source_items "
        "FROM knowledge_concepts LIMIT ? OFFSET 20",
        (limit,),
    ).fetchall()
    knowledge = []
    kinds = ["principle", "pattern", "anti_pattern", "reference", "playbook", "checklist"]
    for i, (slug, title, domain, etype, updated_at, source_items) in enumerate(rows):
        body = f"# {title}\n\n基于 {source_items or '[]'} 的样本经验。"
        knowledge.append(
            {
                "id": f"KNOW{str(i+1).zfill(3)}",
                "kind": random.choice(kinds),
                "title": _redact_text(title, 60) or slug,
                "body": body,
                "prerequisites": [],
                "counter_examples": [],
                "evidence_refs": [],
                "expiry_at": None,
                "review_at": _fix_time(updated_at),
                "reuse_count": 0,
                "last_reused_at": None,
                "status": random.choice(["draft", "published", "deprecated"]),
                "revision": 1,
                "wiki_path": None,
                "content_hash": _seed_hash(body),
                "published_at": _utcnow() if random.random() > 0.3 else None,
                "created_at": _fix_time(updated_at) or _utcnow(),
                "updated_at": _utcnow(),
                "allowed_actions": ["edit", "publish", "discard"],
            }
        )
    return knowledge


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def extract(db_path: Path = DEFAULT_DB, out_path: Path = OUT_PATH, counts: dict[str, int] | None = None) -> dict[str, Any]:
    """抽取全部 9 域对象, 返回 seed dict."""
    counts = counts or {
        "subjects": 20,
        "materials": 25,
        "signals": 20,
        "cases": 20,
        "judgments": 10,
        "actions": 10,
        "runs": 15,
        "artifacts": 10,
        "knowledge": 15,
    }
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    print(f"读取生产库: {db_path}")

    subjects = _fetch_subjects(con, counts["subjects"])
    print(f"  Subject:  {len(subjects)}")

    materials = _fetch_materials(con, counts["materials"])
    print(f"  Material: {len(materials)}")

    signals = _fetch_signals(materials, subjects, counts["signals"])
    print(f"  Signal:   {len(signals)}")

    cases = _fetch_cases(con, subjects, counts["cases"])
    print(f"  Case:     {len(cases)}")

    judgments = _fetch_judgments(cases, materials, counts["judgments"])
    print(f"  Judgment: {len(judgments)}")

    actions = _fetch_actions(cases, judgments, counts["actions"])
    print(f"  Action:   {len(actions)}")

    runs = _fetch_runs(con, actions, counts["runs"])
    print(f"  Run:      {len(runs)}")

    artifacts = _fetch_artifacts(runs, counts["artifacts"])
    print(f"  Artifact: {len(artifacts)}")

    knowledge = _fetch_knowledge(con, subjects, counts["knowledge"])
    print(f"  Knowledge:{len(knowledge)}")

    con.close()

    seed = {
        "_meta": {
            "version": "v1.0_seed",
            "extracted_at": _utcnow(),
            "source_db": str(db_path),
            "counts": {k: len(v) for k, v in [
                ("subjects", subjects), ("materials", materials), ("signals", signals),
                ("cases", cases), ("judgments", judgments), ("actions", actions),
                ("runs", runs), ("artifacts", artifacts), ("knowledge", knowledge),
            ]},
            "desensitization": "urls_faked, texts_truncated, hashes_seeded, timestamps_2025",
            "notes": "用于 dev 环境填充; 不包含真实 PII/密钥; 生产数据仅用于结构参考",
        },
        "subjects": subjects,
        "materials": materials,
        "signals": signals,
        "cases": cases,
        "judgments": judgments,
        "actions": actions,
        "runs": runs,
        "artifacts": artifacts,
        "knowledge": knowledge,
    }
    return seed


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="T03-D: 生产数据脱敏抽取")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="生产库路径")
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="输出路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印统计, 不写盘")
    parser.add_argument("--counts", type=str, help="JSON 对象覆盖默认条数, e.g. {'subjects':5}")
    args = parser.parse_args()

    counts = None
    if args.counts:
        try:
            counts = json.loads(args.counts)
        except json.JSONDecodeError:
            print(f"ERROR: --counts 必须是合法 JSON: {args.counts}", file=sys.stderr)
            sys.exit(1)

    seed = extract(db_path=args.db, out_path=args.out, counts=counts)

    if args.dry_run:
        print("\n=== dry-run 统计 ===")
        print(json.dumps(seed["_meta"], ensure_ascii=False, indent=2))
        return

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"\n已写入: {out_path}  ({size_kb:.1f} KB)")
    print(f"总计:  {sum(seed['_meta']['counts'].values())} 条 v1.0 域对象")


if __name__ == "__main__":
    main()
