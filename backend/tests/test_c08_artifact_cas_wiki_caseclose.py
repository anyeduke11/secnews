"""v1.0 C08 reverse tests — R08/R09/R10/R17 (4 finding groups).

R08 产物正文没有保存仍能 accepted: 反例 3 个 (缺文件/篡改hash/没存盘).
R09 update_status_cas 缺 revision+old_status 原子守卫: 反例 2 个 (交错 accepted + 旧状态覆盖).
R10 publish 写失败伪发布: 反例 2 个 (写 raise 阻断 publish + canonical path 一致).
R17 Case close 不检 active Run / 无 artifact / 无 judgment: 反例 5 条 (成功/cancelled/仍 running/无 artifact/研究型).

每组反例在旧实现上必失败, 修复后必 pass.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.repository.db import get_connection
from backend.services.action_service import ActionService
from backend.services.artifact_service import (
    ArtifactConflictError,
    ArtifactService,
    ArtifactValidationError,
)
from backend.services.case_service import CaseConflictError, CaseService
from backend.services.judgment_service import JudgmentService
from backend.services.knowledge_service import (
    KnowledgeConflictError,
    KnowledgeService,
)
from backend.services.run_service import RunService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _seed_published_judgment(judgment_id: str = "J" * 26, case_id: str = "C" * 26) -> None:
    """直接走 repo: published judgment (供 case 关闭验收用)."""
    from backend.repository.judgment_repo import JudgmentRepository
    repo = JudgmentRepository()
    now = "2026-09-07T00:00:00+00:00"
    body = {
        "id": judgment_id, "case_id": case_id, "claim_type": "finding",
        "claim": "X", "conditions": "", "confidence": "high",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "published", "content_hash": "h" * 64, "revision": 1,
        "published_at": now, "created_at": now, "updated_at": now,
        "allowed_actions": ["view_only"], "reason": None,
    }
    repo.insert(body)


def _seed_action_run(
    action_status: str = "succeeded",
    run_status: str = "succeeded",
    with_artifact: bool = True,
    artifact_status: str = "accepted",
    tmp_path: Path | None = None,
) -> tuple[str, str, str]:
    """建 case + judgment + action + run + artifact 全套; 返 (case_id, action_id, run_id).

    C08 R17: case 必须是真实 row 才能被 close_case 找到 (不能用 "C"*26 占位 ID).
    C08 R08: artifact 必传 content_ref (落盘文件); 自动写 tmp_path/body.md.
    """
    # R17 fix: 真实 case row (不写字面 "C"*26 占位, CaseService.get_case 会 404)
    c_svc = CaseService()
    c = c_svc.create_case(title="C08", question="Q", goal="G", scope="S")
    case_id = c.id
    judgment_id = "J" * 26
    _seed_published_judgment(judgment_id=judgment_id, case_id=case_id)
    a_svc = ActionService(dsh_caller=lambda _p: '{"plan": "# p", "expected_artifacts": ["r"], "success_criteria": "y", "tool_versions": {}, "unknowns": []}')
    a = a_svc.create_with_dsh(
        case_id=case_id, judgment_id=judgment_id, title="t", subject_name="X",
        cve_id="CVE-X", scope="y", evidence_materials=[],
    )["action"]
    a_svc.approve(a["id"], expected_revision=1, approved_by="user")
    if action_status != "approved":
        conn = get_connection()
        conn.execute("UPDATE v1_actions SET status = ?, revision = revision + 1 WHERE id = ?", (action_status, a["id"]))
        conn.commit()
    r_svc = RunService()
    run = r_svc.create_or_replay(
        action_id=a["id"], idempotency_key=f"idem-{a['id'][:8]}", attempt=1, protocol="direct",
    )["run"]
    if run_status != "queued":
        conn = get_connection()
        conn.execute("UPDATE v1_runs SET status = ? WHERE id = ?", (run_status, run["id"]))
        conn.commit()
    if with_artifact:
        art_svc = ArtifactService()
        body = "body-1"
        if tmp_path is not None:
            ref = tmp_path / "body.md"
            ref.write_text(body, encoding="utf-8")
            content_ref = str(ref)
        else:
            content_ref = None
        try:
            art = art_svc.create(
                run_id=run["id"], kind="report", title="r", content=body,
                content_ref=content_ref,
            )
        except ArtifactValidationError:
            # 旧 fallback: 无 content_ref 时也允许 (兼容非 C08 R08 测试)
            art = art_svc.create(
                run_id=run["id"], kind="report", title="r", content=body,
            )
        art_svc.verify(art["id"], verified_by="user", verified_result="pass")
        if artifact_status == "accepted":
            art_svc.accept(art["id"], accepted_by="user")
    return case_id, a["id"], run["id"]


# ===========================================================================
# R08 产物正文必须先存盘才能 accepted (反例 3)
# ===========================================================================
def test_r08_artifact_content_ref_required(tmp_path, temp_db) -> None:
    """R08 反例 1: 不传 content_ref → create() 必须 raise (旧实现默许空)."""
    case_id, _action_id, run_id = _seed_action_run(tmp_path=tmp_path)
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="content_ref required"):
        svc.create(run_id=run_id, kind="report", title="r", content="x")


def test_r08_artifact_missing_file_blocks_accept(tmp_path, temp_db) -> None:
    """R08 反例 2: content_ref 指向不存在文件 → create() raise (旧实现默许)."""
    case_id, _action_id, run_id = _seed_action_run(tmp_path=tmp_path)
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="not found"):
        svc.create(
            run_id=run_id, kind="report", title="r", content="hello",
            content_ref=str(tmp_path / "does_not_exist.md"),
        )


def test_r08_artifact_tampered_hash_blocks_create(tmp_path, temp_db) -> None:
    """R08 反例 3: content_ref 指向篡改后文件 (hash 不匹配) → create() raise.

    create() 时已落盘 hash 与 content 不一致 → 不允许入库; 旧实现 create 时不校验,
    accept 时再读 (但已被 §8.3 拒重传逻辑串扰, 行为不稳定).
    """
    case_id, _action_id, run_id = _seed_action_run(tmp_path=tmp_path)
    # 写一个 content 不同于文件的 body (触发 hash 不一致)
    body_path = tmp_path / "tampered.md"
    body_path.write_text("tampered content", encoding="utf-8")
    svc = ArtifactService()
    with pytest.raises(ArtifactValidationError, match="hash mismatch"):
        svc.create(
            run_id=run_id, kind="report", title="r", content="original content",
            content_ref=str(body_path),
        )


# ===========================================================================
# R09 update_status_cas 原子守卫 (反例 2)
# ===========================================================================
def test_r09_two_window_interleave_only_one_succeeds(tmp_path, temp_db) -> None:
    """R09 反例 1: 两个并发 update_status_cas(expected_revision=1) → 只应 1 成功."""
    case_id, _action_id, run_id = _seed_action_run(tmp_path=tmp_path)
    body_path = tmp_path / "r09a.md"
    body_path.write_text("x", encoding="utf-8")
    svc = ArtifactService()
    a = svc.create(run_id=run_id, kind="report", title="r", content="x", content_ref=str(body_path))
    # 修复后: 第一次 update_status_cas 必须传 expected_revision + old_status
    n1 = svc.repo.update_status_cas(
        a["id"], "rejected", expected_revision=a["revision"], old_status="pending",
        reason="t1",
    )
    # 旧实现: 第二次也成功 (无 expected_revision 守卫); 修复后: 应 0 行
    n2 = svc.repo.update_status_cas(
        a["id"], "verified", expected_revision=a["revision"], old_status="pending",
        allowed_actions=["accept", "reject"],
    )
    assert n1 == 1
    assert n2 == 0  # 旧实现 1, 修复后 0


def test_r09_old_status_mismatch_raises_cas_conflict(tmp_path, temp_db) -> None:
    """R09 反例 2: old_status 传错 (如 pending vs verified) → update_status_cas 应 0 行."""
    case_id, _action_id, run_id = _seed_action_run(tmp_path=tmp_path)
    body_path = tmp_path / "r09b.md"
    body_path.write_text("x", encoding="utf-8")
    svc = ArtifactService()
    a = svc.create(run_id=run_id, kind="report", title="r", content="x", content_ref=str(body_path))
    svc.verify(a["id"], verified_by="u")
    # 此时 status=verified, 但传 old_status=pending → 应 0 行
    n = svc.repo.update_status_cas(
        a["id"], "accepted", expected_revision=a["revision"], old_status="pending",
        accepted_by="u", accepted_at="2026-09-07T00:00:00+00:00",
    )
    assert n == 0  # 旧实现 1, 修复后 0


# ===========================================================================
# R10 publish 写失败伪发布 (反例 2)
# ===========================================================================
def _seed_knowledge_draft(knowledge_id: str = "K" * 26) -> dict:
    """直接走 repo: 建 draft knowledge (供 publish 反例用)."""
    from backend.repository.v1_knowledge_repo import V1KnowledgeRepository
    repo = V1KnowledgeRepository()
    now = "2026-09-07T00:00:00+00:00"
    body = {
        "id": knowledge_id, "title": "K1", "kind": "playbook", "body": "b",
        "prerequisites": [], "counter_examples": [],
        "status": "draft", "content_hash": "h" * 64, "revision": 1,
        "published_at": None, "deprecated_at": None, "retracted_at": None,
        "review_at": None, "wiki_path": None,
        "created_at": now, "updated_at": now,
        "allowed_actions": ["publish", "edit"], "reason": None,
    }
    repo.insert(body)
    return body


def test_r10_knowledge_publish_raises_on_wiki_write_failure(temp_db) -> None:
    """R10 反例 1: Wiki 写失败 → publish 必须 raise, 不能 published."""
    k = _seed_knowledge_draft()
    k_svc = KnowledgeService()
    # 模拟 WikiFs 写失败 (monkeypatch _write_wiki raise)
    with patch.object(k_svc, "_write_wiki", side_effect=RuntimeError("disk full")):
        # 修复后: 旧 except Exception → logger.warning 然后继续 publish; 现应 raise
        with pytest.raises(RuntimeError, match="disk full"):
            k_svc.publish(k["id"], expected_revision=k["revision"])


def test_r10_canonical_wiki_path_is_items_under_root(temp_db) -> None:
    """R10 反例 2: knowledge.publish 落 wiki_path 必须真实可读, 与 record 一致.

    旧实现 wiki_path = "knowledge/{id}.md" (相对 cwd), 实际写 "<root>/items/knowledge_{id}.md".
    修复后: wiki_path 必为 items/knowledge_{id}.md (绝对), 从 root 可读.
    """
    from backend.wiki_fs.root import resolve_wiki_root
    k = _seed_knowledge_draft(knowledge_id="K2" + "X" * 24)
    k_svc = KnowledgeService()
    out = k_svc.publish(k["id"], expected_revision=k["revision"])
    wiki_path = out.get("wiki_path", "")
    root = Path(resolve_wiki_root())
    assert wiki_path, f"wiki_path empty: {out}"
    if Path(wiki_path).is_absolute():
        assert Path(wiki_path).exists(), f"wiki_path not on disk: {wiki_path}"
        assert str(Path(wiki_path).resolve()).startswith(str(root.resolve()))
    else:
        candidate = root / wiki_path
        assert candidate.exists(), f"wiki_path not on disk: {candidate}"


# ===========================================================================
# R17 Case close 检 active Run / artifact / judgment (反例 5 条路径)
# ===========================================================================
def _create_case_with_judgment() -> str:
    """建 case + 走 judgment repo 直接插 published (供研究型路径用)."""
    c_svc = CaseService()
    c = c_svc.create_case(title="T", question="Q", goal="G", scope="S")
    _seed_published_judgment(judgment_id="J" * 26, case_id=c.id)
    return c.id


def test_r17_case_close_succeeds_when_all_done(tmp_path, temp_db) -> None:
    """R17 路径 1: action+run 全 succeeded + artifact accepted + judgment published → 可关."""
    case_id, action_id, _run_id = _seed_action_run(
        action_status="succeeded", run_status="succeeded",
        with_artifact=True, artifact_status="accepted",
        tmp_path=tmp_path,
    )
    c_svc = CaseService()
    c = c_svc.get_case(case_id)
    closed = c_svc.close_case(case_id, expected_revision=c.revision)
    assert closed.status.value == "closed"


def test_r17_case_close_succeeds_when_all_cancelled(tmp_path, temp_db) -> None:
    """R17 路径 2: action+run 全 cancelled (无 artifact) → 可关 (兜底)."""
    case_id, _action_id, _run_id = _seed_action_run(
        action_status="cancelled", run_status="cancelled",
        with_artifact=False,
        tmp_path=tmp_path,
    )
    c_svc = CaseService()
    c = c_svc.get_case(case_id)
    closed = c_svc.close_case(case_id, expected_revision=c.revision)
    assert closed.status.value == "closed"


def test_r17_case_close_blocked_when_run_running(tmp_path, temp_db) -> None:
    """R17 路径 3: run 仍 running → close 必须 raise."""
    case_id, _action_id, _run_id = _seed_action_run(
        action_status="running", run_status="running",
        with_artifact=False,
        tmp_path=tmp_path,
    )
    c_svc = CaseService()
    c = c_svc.get_case(case_id)
    with pytest.raises(CaseConflictError, match=r"active run|active action|not in terminal|active"):
        c_svc.close_case(case_id, expected_revision=c.revision)


def test_r17_case_close_blocked_when_no_artifact(tmp_path, temp_db) -> None:
    """R17 路径 4: action succeeded 但无 verified artifact → close 必须 raise."""
    case_id, _action_id, _run_id = _seed_action_run(
        action_status="succeeded", run_status="succeeded",
        with_artifact=False,
        tmp_path=tmp_path,
    )
    c_svc = CaseService()
    c = c_svc.get_case(case_id)
    with pytest.raises(CaseConflictError, match=r"artifact|verified|missing"):
        c_svc.close_case(case_id, expected_revision=c.revision)


def test_r17_case_close_succeeds_research_no_action(temp_db) -> None:
    """R17 路径 5: 研究型 (无 action) 但有 published judgment → 可关."""
    case_id = _create_case_with_judgment()
    c_svc = CaseService()
    c = c_svc.get_case(case_id)
    closed = c_svc.close_case(case_id, expected_revision=c.revision)
    assert closed.status.value == "closed"
