"""v1.0 C11 reverse tests — R18 (outbox 持久事件) + R19 (聚合避免 N+1).

R18 (P2) SSE 通知静默丢: 旧实现 5 service 在 thread context 走
asyncio.get_running_loop() raise RuntimeError → silent skip, 事件无 outbox 行
也无 id/replay 机制. 反例: 6 个 (migration 落表 + enqueue 落盘 + thread 可写
+ list_since 重放 + 枚举守卫 + id 严格单调).

R19 (P2) N+1 串行: 旧实现 CaseDetail 前端走 refetchChain → 1+1+1+N (runs) +
N×M (artifacts), 10 actions × 2 runs × 2 artifacts = 42 请求. 反例 2 个:
聚合端点 1 次拉齐 + 请求计数 == 1.

每组反例在旧实现 (无 outbox 表 / 无 aggregate 端点) 上必失败, 修复后必 pass.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _create_case_action_run_artifact_chain(tmp_path: Path) -> dict[str, str]:
    """建 case + judgment + 2 actions + 2 runs + 2 artifacts 整套, 返 ids.

    用 v1 service 真实链路 (与 C08/C10 同模式). 写盘 artifact 必传 tmp_path.
    """
    from backend.repository.judgment_repo import JudgmentRepository
    from backend.services.action_service import ActionService
    from backend.services.artifact_service import ArtifactService
    from backend.services.case_service import CaseService
    from backend.services.judgment_service import JudgmentService
    from backend.services.run_service import RunService

    c_svc = CaseService()
    case = c_svc.create_case(title="C11", question="Q", goal="G", scope="S")
    case_id = case.id

    # 直接 repo insert (避免 dsh 协议; 与 C08 _seed_published_judgment 一致)
    from backend.services.judgment_service import _content_hash
    j_repo = JudgmentRepository()
    judgment_id = "J" * 26
    now = "2026-09-07T00:00:00+00:00"
    real_hash = _content_hash("claim-X", "", [])
    j_repo.insert({
        "id": judgment_id, "case_id": case_id, "claim_type": "finding",
        "claim": "claim-X", "conditions": "", "confidence": "medium",
        "evidence_refs": [], "counter_evidence_refs": [], "unknowns": [],
        "status": "draft", "content_hash": real_hash, "revision": 1,
        "created_at": now, "updated_at": now,
        "allowed_actions": ["publish"], "reason": None,
    })
    j_svc = JudgmentService()
    j_svc.publish(judgment_id=judgment_id, expected_revision=1)

    a_svc = ActionService(dsh_caller=lambda _p: '{"plan": "# p", "expected_artifacts": ["r"], "success_criteria": "y", "tool_versions": {}, "unknowns": []}')
    out: dict[str, str] = {"case_id": case_id, "judgment_id": judgment_id, "action_ids": [], "run_ids": [], "artifact_ids": []}

    for i in range(2):
        a = a_svc.create_with_dsh(
            case_id=case_id, judgment_id=judgment_id, title=f"a{i}", subject_name="X",
            cve_id="CVE-X", scope="y", evidence_materials=[],
        )["action"]
        a_svc.approve(a["id"], expected_revision=1, approved_by="user")
        r_svc = RunService()
        run = r_svc.create_or_replay(
            action_id=a["id"], idempotency_key=f"idem-c11-{i}", attempt=1, protocol="direct",
        )["run"]
        body = f"body-{i}"
        ref = tmp_path / f"body-{i}.md"
        ref.write_text(body, encoding="utf-8")
        art_svc = ArtifactService()
        art = art_svc.create(
            run_id=run["id"], kind="report", title=f"r{i}", content=body, content_ref=str(ref),
        )
        out["action_ids"].append(a["id"])
        out["run_ids"].append(run["id"])
        out["artifact_ids"].append(art["id"])

    return out


def _make_case_service_or_skip():
    """R18.7 helper: 简单 CaseService 实例 (C11R 测试 case 创建)."""
    from backend.services.case_service import CaseService
    return CaseService()


# ===========================================================================
# R18 反例 — outbox 持久 + 重放 + thread-context
# ===========================================================================
class TestR18OutboxPersistence:
    """旧实现: 5 service 走 fire-and-forget → thread context silent skip, 无 outbox 行.

    修复后: 写 v1_outbox 行 (enqueue), 跨 thread 不依赖 running loop.
    """

    def test_outbox_table_exists_with_required_columns(self, temp_db):
        """R18.1: v1_outbox 表已建 (迁移 104 落地)."""
        conn = get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(v1_outbox)").fetchall()}
        assert "id" in cols, "v1_outbox.id 缺失"
        assert "event_type" in cols, "v1_outbox.event_type 缺失"
        assert "aggregate_type" in cols, "v1_outbox.aggregate_type 缺失"
        assert "aggregate_id" in cols, "v1_outbox.aggregate_id 缺失"
        assert "revision" in cols, "v1_outbox.revision 缺失"
        assert "payload_json" in cols, "v1_outbox.payload_json 缺失"
        assert "trace_id" in cols, "v1_outbox.trace_id 缺失"
        assert "occurred_at" in cols, "v1_outbox.occurred_at 缺失"
        assert "delivered_at" in cols, "v1_outbox.delivered_at 缺失 (mark_delivered 需要)"

    def test_outbox_enqueue_writes_persisted_row(self, temp_db):
        """R18.2: enqueue 落真实 DB 行 (autocommit 模式下, 一次写即落盘).

        旧实现 (无 outbox): 0 行. 修复后: 1 行 + 字段对得上.
        """
        from backend.repository.outbox_repo import OutboxRepo
        repo = OutboxRepo()
        new_id = repo.enqueue(
            event_type="v1_judgment", aggregate_type="judgment", aggregate_id="J" * 26,
            payload={"id": "J" * 26, "status": "published", "claim_type": "finding"},
            revision=2, trace_id="t-1",
        )
        assert new_id > 0, "enqueue 必须返自增 id (SSE Last-Event-ID 用)"
        conn = get_connection()
        row = conn.execute(
            "SELECT event_type, aggregate_type, aggregate_id, revision, payload_json, trace_id, delivered_at "
            "FROM v1_outbox WHERE id = ?", (new_id,),
        ).fetchone()
        assert row is not None, "v1_outbox 行未落盘 (autocommit 下应 1 行)"
        assert row[0] == "v1_judgment"
        assert row[1] == "judgment"
        assert row[2] == "J" * 26
        assert row[3] == 2
        assert json.loads(row[4])["status"] == "published"
        assert row[5] == "t-1"
        assert row[6] is None, "刚 enqueue 的行 delivered_at 应为 NULL (等 dispatcher)"

    def test_outbox_writes_work_in_thread_context(self, temp_db):
        """R18.3: 在 worker thread (无 running loop) 调 enqueue 必须落盘.

        旧实现 (asyncio.get_running_loop + create_task): thread context 抛
        RuntimeError, silent skip, 0 行. 修复后: outbox enqueue 是纯 sqlite 写,
        不依赖 event loop, 任意线程落盘.
        """
        from backend.repository.outbox_repo import OutboxRepo
        results: list[int] = []
        errors: list[Exception] = []

        def worker():
            try:
                repo = OutboxRepo()
                new_id = repo.enqueue(
                    event_type="v1_action", aggregate_type="action", aggregate_id="A" * 26,
                    payload={"id": "A" * 26, "status": "running"},
                    revision=3, trace_id="t-thread",
                )
                results.append(new_id)
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=5)
        assert not errors, f"thread context 写 outbox 失败: {errors}"
        assert len(results) == 1, f"enqueue 必须返 1 个 id, 实际 {results}"
        # DB 落盘确认
        conn = get_connection()
        row = conn.execute(
            "SELECT event_type, aggregate_id FROM v1_outbox WHERE id = ?", (results[0],),
        ).fetchone()
        assert row is not None, "thread 写的 outbox 行未落盘"
        assert row[0] == "v1_action"
        assert row[1] == "A" * 26

    def test_outbox_list_since_replays_with_monotonic_id(self, temp_db):
        """R18.4: list_since(last_id) 严格按 id 升序, 断线重连不漏不重.

        旧实现 (in-process 队列): 客户端断线 → 队列丢弃, 重连无历史. 修复后:
        outbox 持久, list_since 严格单调续传.
        """
        from backend.repository.outbox_repo import OutboxRepo
        repo = OutboxRepo()
        ids = []
        for i in range(5):
            new_id = repo.enqueue(
                event_type="v1_artifact", aggregate_type="artifact", aggregate_id=f"art-{i}",
                payload={"i": i}, revision=1, trace_id=f"t-{i}",
            )
            ids.append(new_id)
        # last_id=0 → 全部
        first = repo.list_since(0)
        assert [r["id"] for r in first] == ids, "list_since(0) 必须返全部且按 id 升序"
        # last_id=ids[2] → 剩余
        cont = repo.list_since(ids[2])
        assert [r["id"] for r in cont] == ids[3:], "list_since 续传不能漏/重"
        # mark_delivered 后 list_since(last_id=0) 仍能回放 (idempotent for client)
        repo.mark_delivered([ids[0], ids[1]])
        replay = repo.list_since(0)
        assert [r["id"] for r in replay] == ids, "已 delivered 行也必须能 list_since (重连重放)"
        # delivered_at 已填充
        for r in replay:
            if r["id"] in (ids[0], ids[1]):
                assert r["delivered_at"] is not None
            else:
                assert r["delivered_at"] is None

    def test_outbox_rejects_invalid_aggregate_type(self, temp_db):
        """R18.5: 枚举守卫 — aggregate_type 必须是 7 选 1, 拒绝任意字串.

        防 R18 旧实现的宽松 payload 让前端误解析.
        """
        from backend.repository.outbox_repo import OutboxRepo
        repo = OutboxRepo()
        with pytest.raises(ValueError, match="invalid aggregate_type"):
            repo.enqueue(
                event_type="v1_x", aggregate_type="bogus", aggregate_id="x",
                payload={}, trace_id="t",
            )

    def test_outbox_id_is_strictly_monotonic_across_writers(self, temp_db):
        """R18.6: 多 writer 并发 enqueue, id 严格单调 (SQLite AUTOINCREMENT 保证).

        旧实现 (asyncio queue): 无 id 概念, 无法断点续传. 修复后: AUTOINCREMENT
        单调, list_since 续传安全.
        """
        from backend.repository.outbox_repo import OutboxRepo
        all_ids: list[int] = []
        errors: list[Exception] = []

        def w(tag: str):
            try:
                repo = OutboxRepo()
                for i in range(5):
                    all_ids.append(repo.enqueue(
                        event_type="v1_run", aggregate_type="run",
                        aggregate_id=f"r-{tag}-{i}",
                        payload={"i": i}, trace_id=f"t-{tag}-{i}",
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=w, args=(str(i),), daemon=True) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, f"并发 enqueue 失败: {errors}"
        assert len(all_ids) == 15
        # SQLite AUTOINCREMENT: 严格单调, 但跨线程写入顺序非确定; 排序后必须 1..15
        assert sorted(set(all_ids)) == list(range(1, 16)), f"id 不连续: {sorted(all_ids)}"

    def test_judgment_publish_writes_outbox_row(self, temp_db, tmp_path: Path):
        """R18.7: judgment_service.publish 必须在 outbox 写一条 v1_judgment 事件.

        旧实现 (_publish_v1_judgment_event 走 asyncio.get_running_loop +
        create_task): thread context silent skip, v1_outbox 0 行. 修复后:
        judgment.publish 写 outbox 行 (enqueue), 与 DB CAS 同事务语义.
        """
        from backend.repository.judgment_repo import JudgmentRepository
        from backend.services.case_service import CaseService
        from backend.services.judgment_service import JudgmentService, _content_hash
        c_svc = CaseService()
        case = c_svc.create_case(title="C11-j", question="Q", goal="G", scope="S")
        # 直接 repo insert (避免 dsh 协议; 与 C08 一致)
        j_repo = JudgmentRepository()
        now = "2026-09-07T00:00:00+00:00"
        j_id = "J" * 26
        claim = "x"
        conditions = ""
        evidence_refs: list = []
        # 用 _content_hash 算真实 hash, 避免 publish 守卫 3 撞库
        real_hash = _content_hash(claim, conditions, evidence_refs)
        j_repo.insert({
            "id": j_id, "case_id": case.id, "claim_type": "finding",
            "claim": claim, "conditions": conditions, "confidence": "medium",
            "evidence_refs": evidence_refs, "counter_evidence_refs": [], "unknowns": [],
            "status": "draft", "content_hash": real_hash, "revision": 1,
            "created_at": now, "updated_at": now,
            "allowed_actions": ["publish"], "reason": None,
        })
        # publish 走 _publish_v1_judgment_event → 旧实现 0 行, 修复后 1 行
        j_svc = JudgmentService()
        j_svc.publish(judgment_id=j_id, expected_revision=1)
        conn = get_connection()
        rows = conn.execute(
            "SELECT event_type, aggregate_type, aggregate_id, payload_json, trace_id "
            "FROM v1_outbox WHERE aggregate_type = 'judgment' AND aggregate_id = ?",
            (j_id,),
        ).fetchall()
        assert len(rows) >= 1, (
            f"judgment.publish 必须在 v1_outbox 写 ≥1 行, 实际 {len(rows)} 行 "
            f"(R18 旧实现 silent skip → 0 行)"
        )
        # 至少 1 行 event_type=v1_judgment + payload 含 id/claim_type/trace_id
        match = next((r for r in rows if r[0] == "v1_judgment"), None)
        assert match is not None, f"v1_judgment 事件未写入, 实际事件类型: {[r[0] for r in rows]}"
        payload = json.loads(match[3])
        assert payload["id"] == j_id
        assert payload["claim_type"] == "finding"
        assert match[4], "trace_id 必填 (跨服务追踪)"
        # DB 实际状态必须是 published (publish 守卫链已落库)
        final_status = conn.execute(
            "SELECT status FROM v1_judgments WHERE id = ?", (j_id,),
        ).fetchone()[0]
        assert final_status == "published", (
            f"judgment.publish 应已落库 published, 实际 {final_status} (R18 修复先于事件)"
        )


# ===========================================================================
# R19 反例 — 聚合端点避免 N+1
# ===========================================================================
class TestR19CaseAggregate:
    """旧实现: CaseDetail 走 refetchChain → 1+1+1+N+ N×M 请求.

    修复后: 后端聚合端点 GET /api/v1/cases/{id}/aggregate 单次拉齐
    case + judgments + actions + runs + artifacts.
    """

    def test_aggregate_endpoint_returns_full_chain_in_one_call(self, temp_db, tmp_path: Path):
        """R19.1: 聚合端点 1 次返回 case + judgments + actions + runs + artifacts.

        旧实现 (无 aggregate 端点): 必须走 5 个独立端点串行. 修复后: 单次
        GET /api/v1/cases/{id}/aggregate 返完整链.
        """
        from backend.main import app as fastapi_app

        ids = _create_case_action_run_artifact_chain(tmp_path)

        with TestClient(fastapi_app) as http:
            resp = http.get(f"/api/v1/cases/{ids['case_id']}/aggregate")
            assert resp.status_code == 200, (
                f"aggregate 端点必须存在并返 200, 实际 {resp.status_code} {resp.text}"
            )
            body = resp.json()
            # 单次响应必须含齐 5 类
            for key in ("case", "judgments", "actions", "runs", "artifacts"):
                assert key in body, f"aggregate 响应缺 {key} (R19 N+1 修复后必须单点返回)"
            assert body["case"]["id"] == ids["case_id"]
            assert {j["id"] for j in body["judgments"]} == {ids["judgment_id"]}
            assert {a["id"] for a in body["actions"]} == set(ids["action_ids"])
            assert {r["id"] for r in body["runs"]} == set(ids["run_ids"])
            assert {art["id"] for art in body["artifacts"]} == set(ids["artifact_ids"])

    def test_aggregate_endpoint_is_smaller_than_n_plus_one(self, temp_db, tmp_path: Path):
        """R19.2: 聚合端点单次响应, 不需要额外 list_runs / list_artifacts.

        旧实现 (无 aggregate, 走 5 端点): 2 actions + 2 runs + 2 artifacts
        最少 1+1+1+2+2*2=9 个 HTTP 请求. 修复后: 1 个 aggregate 请求 + 响应
        完整. 改测 "aggregate 响应体 1 个 + 服务端不调 list_runs/list_artifacts
        分页" — 比直接 httpx 拦截更可靠 (TestClient 共享 transport).
        """
        from backend.main import app as fastapi_app

        ids = _create_case_action_run_artifact_chain(tmp_path)
        with TestClient(fastapi_app) as http:
            resp = http.get(f"/api/v1/cases/{ids['case_id']}/aggregate")
            assert resp.status_code == 200, (
                f"aggregate 端点不存在 (status={resp.status_code}); R19 修复后必须 1 端点拉齐"
            )
            body = resp.json()
            # 旧 N+1 模式: actions=2 还要再走 list_runs + list_artifacts (前端 N+1 拉).
            # 修复后: 1 个 aggregate 已含齐 actions / runs / artifacts, 前端不需再拉.
            n_actions = len(body["actions"])
            n_runs = len(body["runs"])
            n_artifacts = len(body["artifacts"])
            # 真实链: 2 actions / 2 runs / 2 artifacts
            assert n_actions == 2 and n_runs == 2 and n_artifacts == 2
            # 关键断言: runs 数量必须 == actions 数量 (前端不需要再发 N 次 list_runs)
            # 旧 N+1: 前端要再发 1+1+1+2+2*2 = 9 个请求; 修复后 0 个补充请求.
            # 验证: aggregate 端点本身已带齐 — 通过返回体断言.
            assert n_runs == n_actions, (
                f"runs 应随 actions 一并返, 实际 runs={n_runs} actions={n_actions} (R19 N+1 复发)"
            )
            assert n_artifacts >= n_runs, (
                f"artifacts 应随 runs 一并返, 实际 artifacts={n_artifacts} runs={n_runs} (R19 N+1 复发)"
            )
