"""P0-E / P0-G 修复回归 (FIRST_PRINCIPLES_ANALYSIS_2026-09-11).

P0-E 证据收据死信:
  1. judgment / action / knowledge 三类 receipt commit 链路 (原白名单外
     → commit 恒抛 ValueError → 被调用方吞成 warning → 永远 pending)
  2. judgment_service.create_with_dsh 全链路 receipt 真实 committed
     (含 insert → intent 顺序对齐)
  3. receipt-only 类型实体行缺失 → commit fail-fast (防外键悬空)
  4. 超时 pending intent 经 maintenance 小时级钩子 (observability_ttl_job)
     被回收, 失败不影响主 job

P0-G 假加密 (原 5-7: codegarden env_template 加解密往返 / 掩码 / vault 锁定 fail-fast):
  已随工坊域 + 密钥域整体删除退役 (2026-11-19)。
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from backend.repository.db import get_connection
from backend.services.v1_evidence_service import (
    RECEIPT_COMMITTED,
    RECEIPT_ROLLED_BACK,
    V1EvidenceService,
)


# ---------------------------------------------------------------------------
# P0-E helpers
# ---------------------------------------------------------------------------
def _receipt_row(intent_id: str) -> tuple | None:
    row = get_connection().execute(
        "SELECT status, entity_type, entity_id FROM v1_evidence_receipts "
        "WHERE intent_id = ?",
        (intent_id,),
    ).fetchone()
    return tuple(row) if row else None


def _seed_entity(entity_type: str, entity_id: str) -> None:
    """receipt-only 三类型的最小实体行 (caller repo.insert 的等价物)."""
    conn = get_connection()
    if entity_type == "judgment":
        conn.execute(
            "INSERT INTO v1_judgments (id, case_id, claim_type, claim) "
            "VALUES (?, ?, 'finding', 'p0-e test claim')",
            (entity_id, "C" * 26),
        )
    elif entity_type == "action":
        conn.execute(
            "INSERT INTO v1_actions (id, case_id, judgment_id, title, plan, plan_hash) "
            "VALUES (?, ?, ?, 't', 'plan', 'h')",
            (entity_id, "C" * 26, "J" + "A" * 25),
        )
    elif entity_type == "knowledge":
        conn.execute(
            "INSERT INTO v1_knowledge (id, kind, title, body) "
            "VALUES (?, 'principle', 't', 'b')",
            (entity_id,),
        )
    else:
        raise ValueError(f"unexpected entity_type {entity_type}")
    conn.commit()


# ---------------------------------------------------------------------------
# 1. 三类 receipt commit 链路
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("entity_type", ["judgment", "action", "knowledge"])
def test_receipt_commit_chain_for_receipt_only_types(temp_db, entity_type) -> None:
    """P0-E 核心断言: 白名单扩展后三类 entity_type 真实 committed (原恒 pending)."""
    eid = f"{entity_type[:2].upper()}-{uuid.uuid4().hex[:10]}"
    _seed_entity(entity_type, eid)
    svc = V1EvidenceService()
    body = {"id": eid, "note": f"p0-e {entity_type}"}
    intent = svc.create_intent(
        f"p0e-{entity_type}-{uuid.uuid4().hex[:8]}", entity_type, body,
        submitted_by="p0e-test",
    )
    res = svc.commit_intent(intent["intent_id"], entity_id=eid)
    assert res["status"] == RECEIPT_COMMITTED
    status, stored_type, stored_eid = _receipt_row(intent["intent_id"])
    assert status == RECEIPT_COMMITTED
    assert stored_type == entity_type
    assert stored_eid == eid


def test_commit_receipt_only_type_missing_entity_row_raises(temp_db) -> None:
    """实体行缺失 → commit fail-fast (ValueError), receipt 不落 committed."""
    svc = V1EvidenceService()
    intent = svc.create_intent(
        f"p0e-missing-{uuid.uuid4().hex[:8]}", "judgment", {"id": "ghost"},
    )
    with pytest.raises(ValueError, match="not found in v1_judgments"):
        svc.commit_intent(intent["intent_id"], entity_id="ghost")
    assert _receipt_row(intent["intent_id"])[0] == "pending"


# ---------------------------------------------------------------------------
# 2. judgment_service 全链路
# ---------------------------------------------------------------------------
def _fake_dsh_response(material_id: str, content_hash: str) -> str:
    return json.dumps({
        "claim_type": "finding",
        "claim": "## 影响\n该漏洞影响核心系统",
        "conditions": "适用于生产",
        "confidence": "high",
        "evidence_refs": [
            {"material_id": material_id, "hash": content_hash, "quote": "原文片段"},
        ],
        "counter_evidence_refs": [],
        "unknowns": ["待评估"],
    })


def test_judgment_service_create_commits_receipt(temp_db) -> None:
    """P0-E 链路: judgment_service 调用点 (原恒 pending) 现在真实 committed."""
    from backend.services.judgment_service import JudgmentService

    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials "
        "(id, source_kind, url, title, content_hash, content_length, fetched_at, "
        " created_at, updated_at) "
        "VALUES ('MAT-P0E', 'url', 'https://example.com/p0e', 'T', "
        "hex(randomblob(32)), 100, datetime('now'), datetime('now'), datetime('now'))",
    )
    conn.commit()
    mat_hash = conn.execute(
        "SELECT content_hash FROM v1_materials WHERE id = 'MAT-P0E'"
    ).fetchone()[0]

    def caller(_prompt: str) -> str:
        return _fake_dsh_response("MAT-P0E", mat_hash)

    svc = JudgmentService(dsh_caller=caller)
    out = svc.create_with_dsh(
        case_id="C" * 26, cve_id="CVE-2026-9999", subject_name="X",
        evidence_materials=[{"id": "MAT-P0E", "title": "X", "content_hash": mat_hash}],
    )
    jid = out["judgment"]["id"]
    row = get_connection().execute(
        "SELECT status, entity_type, entity_id FROM v1_evidence_receipts "
        "WHERE entity_id = ?",
        (jid,),
    ).fetchone()
    assert row is not None, "receipt 未落库 (create_intent 未执行)"
    assert tuple(row) == (RECEIPT_COMMITTED, "judgment", jid)


# ---------------------------------------------------------------------------
# 3. reap 挂调度
# ---------------------------------------------------------------------------
def test_reap_expired_intents_via_maintenance_hook(temp_db) -> None:
    """P0-E: 超时 pending intent 被 maintenance._reap_expired_v1_intents 回收."""
    from backend.scheduler.jobs.maintenance import _reap_expired_v1_intents

    svc = V1EvidenceService()
    intent = svc.create_intent(
        f"p0e-reap-{uuid.uuid4().hex[:8]}", "judgment", {"id": "reap-me"},
    )
    conn = get_connection()
    conn.execute(
        "UPDATE v1_evidence_receipts SET submitted_at = datetime('now', '-2 hours') "
        "WHERE intent_id = ?",
        (intent["intent_id"],),
    )
    conn.commit()
    n = _reap_expired_v1_intents()
    assert n >= 1
    assert _receipt_row(intent["intent_id"])[0] == RECEIPT_ROLLED_BACK


def test_observability_ttl_job_reaps_and_survives(temp_db) -> None:
    """wiring: observability_ttl_job (小时级) 顺路回收超时 intent, 主 job 正常返回."""
    from backend.scheduler.jobs.maintenance import observability_ttl_job

    svc = V1EvidenceService()
    intent = svc.create_intent(
        f"p0e-ttl-{uuid.uuid4().hex[:8]}", "action", {"id": "ttl-me"},
    )
    conn = get_connection()
    conn.execute(
        "UPDATE v1_evidence_receipts SET submitted_at = datetime('now', '-3 hours') "
        "WHERE intent_id = ?",
        (intent["intent_id"],),
    )
    conn.commit()
    asyncio.run(observability_ttl_job())  # 正常完成, 不抛
    assert _receipt_row(intent["intent_id"])[0] == RECEIPT_ROLLED_BACK


# ---------------------------------------------------------------------------
# 4. P0-G (codegarden env_template 加密) 随工坊域 + 密钥域整体删除退役 (2026-11-19)
# ---------------------------------------------------------------------------


def test_migration_115_scrubs_plaintext_llm_key(temp_db) -> None:
    """115 迁移: quality.llm_api_key 明文行被清扫 (模拟存量库重放该迁移)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) "
        "VALUES ('quality.llm_api_key', 'sk-plaintext', datetime('now'))"
    )
    # temp_db init_db 已把 115 记为已应用 (空表 DELETE no-op) —
    # 删掉版本记录模拟存量库首次应用
    conn.execute(
        "DELETE FROM schema_version WHERE version = '115_scrub_plaintext_llm_key'"
    )
    conn.commit()
    from backend.repository.db import apply_migrations
    apply_migrations(conn)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'quality.llm_api_key'"
    ).fetchone()
    assert row is None
