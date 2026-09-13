"""v0.8.5 D1 点火反例测试 — v1_ingest_bridge (spec docs/v0.8.5/V0.8.5_PLAN.md §11 D1).

先写反例再实现 (批次纪律). 断言点火核心语义:
  - allow/neutral: material+signal+subject+admission_log 全落, watermark 推进
  - deny: admission_log deny 行, material 仍入库, **不产信号**
  - fetch ERROR: 全空, watermark 不推进 (R03 语义)
  - 部分失败可辨别: materials_failed 计数 + 失败 material 无 signal
  - 幂等重放: 第二轮 materials/signals 全走 IdempotentReplay, 库不重复
"""
from __future__ import annotations

import asyncio

from backend.repository.db import get_connection
from backend.services.source_pipeline import FetchOutcome
from backend.services.v1_ingest_bridge import V1IngestBridge

# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

ENTRIES = [
    {
        "title": "FastGate 3200 路径遍历漏洞通告",
        "link": "https://example.com/advisory-1",
        "summary": "认证前路径遍历, CVSS 9.8",
        "published_parsed": (2026, 9, 8, 0, 0, 0, 0, 0, 0),
    },
    {
        "title": "某 VPN 网关在野利用情报",
        "link": "https://example.com/intel-2",
        "summary": "WAF 观测到探测",
        "published_parsed": (2026, 9, 8, 1, 0, 0, 0, 0, 0),
    },
]


def _seed_source(source_id: str = "security:SecWiki") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO crawler_sources "
        "(id, category, name, kind, url, feed_url, enabled, etag, last_fetch_at) "
        "VALUES (?, 'security', '点火测试源', 'rss', ?, ?, 1, NULL, NULL)",
        (source_id, f"https://example.com/{source_id}", f"https://example.com/{source_id}/feed"),
    )
    conn.commit()


def _source(source_id: str = "security:SecWiki") -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, category, kind, url, feed_url FROM crawler_sources WHERE id = ?",
        (source_id,),
    ).fetchone()
    return dict(row)


def _make_bridge(source_id: str = "security:SecWiki") -> V1IngestBridge:
    bridge = V1IngestBridge(_source(source_id))
    # 反例测试不打真网络: 预置 SUCCESS + 2 entries (fetch 语义由三态映射单测覆盖)
    bridge._fetch_rss = lambda: asyncio.sleep(  # type: ignore[method-assign]
        0, result=(FetchOutcome.SUCCESS, ENTRIES, "etag-ignition-1")
    )
    return bridge


def _counts(table: str, where: str = "", params: tuple = ()) -> int:
    conn = get_connection()
    row = conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# 反例 1: allow/neutral 全链贯通
# ---------------------------------------------------------------------------
def test_neutral_flow_commits_material_signal_subject_and_watermark(temp_db) -> None:
    _seed_source()
    summary = asyncio.run(_make_bridge().run())

    assert summary["outcome"] == "success"
    assert summary["materials_committed"] == 2
    assert summary["signals_committed"] == 2
    assert summary["signals_denied"] == 0
    # 库内四表全落
    assert _counts("v1_materials") == 2
    assert _counts("v1_signals") == 2
    assert _counts("v1_subjects") == 1
    assert _counts("admission_log") == 2
    # 信号 FK 完整 (subject/material 均真实存在)
    conn = get_connection()
    orphan = conn.execute(
        "SELECT COUNT(*) FROM v1_signals s WHERE NOT EXISTS "
        "(SELECT 1 FROM v1_subjects WHERE id = s.subject_id) OR NOT EXISTS "
        "(SELECT 1 FROM v1_materials WHERE id = s.material_id)"
    ).fetchone()[0]
    assert orphan == 0
    # watermark 推进 (committed>0)
    wm = conn.execute(
        "SELECT etag FROM crawler_sources WHERE id = 'security:SecWiki'"
    ).fetchone()[0]
    assert wm == "etag-ignition-1"


# ---------------------------------------------------------------------------
# 反例 2: deny → quarantine 落日志, 不产信号 (material 仍入库)
# ---------------------------------------------------------------------------
def test_deny_flow_quarantines_without_signal(temp_db, monkeypatch) -> None:
    _seed_source()
    monkeypatch.setattr(
        "backend.services.info_filter_service.evaluate",
        lambda rules, **kw: ("deny", {"id": "r-deny", "note": "deny-for-test"}),
    )
    summary = asyncio.run(_make_bridge().run())

    assert summary["signals_denied"] == 2
    assert summary["signals_committed"] == 0
    assert _counts("v1_materials") == 2          # material 仍入库 (证据在, 信号不出)
    assert _counts("v1_signals") == 0            # 核心反例断言
    assert _counts("admission_log", "WHERE verdict = 'deny'") == 2


# ---------------------------------------------------------------------------
# 反例 3: fetch ERROR → 全空 + watermark 不推进 (R03)
# ---------------------------------------------------------------------------
def test_fetch_error_commits_nothing_and_watermark_holds(temp_db) -> None:
    _seed_source()
    bridge = V1IngestBridge(_source())
    bridge._fetch_rss = lambda: asyncio.sleep(  # type: ignore[method-assign]
        0, result=(FetchOutcome.ERROR, [], None)
    )
    summary = asyncio.run(bridge.run())

    assert summary["outcome"] == "error"
    assert _counts("v1_materials") == 0
    assert _counts("v1_signals") == 0
    conn = get_connection()
    etag = conn.execute(
        "SELECT etag FROM crawler_sources WHERE id = 'security:SecWiki'"
    ).fetchone()[0]
    assert etag is None  # 失败不推进游标


# ---------------------------------------------------------------------------
# 反例 4: 部分失败可辨别 — 失败 material 无 signal, 成功路径不受影响
# ---------------------------------------------------------------------------
def test_partial_material_failure_is_discernible(temp_db, monkeypatch) -> None:
    _seed_source()
    orig_commit = type(_make_bridge().pipeline.evidence).commit_intent

    def flaky_commit(self, intent_id, entity_id, projection=None):
        if entity_id and str(entity_id).startswith("mat"):
            # 第二个 material (按 id 排序确定性地挑一个) 注入失败
            fail_target = sorted(e["link"] for e in ENTRIES)[0]
            import hashlib
            mat_id = "mat" + hashlib.sha256(
                f"{fail_link}|{fail_title}".encode()
            ).hexdigest()[:24]
            if entity_id == mat_id:
                raise FileExistsError("injected projection failure")
        return orig_commit(self, intent_id, entity_id=entity_id, projection=projection)

    fail_link = ENTRIES[0]["link"]
    fail_title = ENTRIES[0]["title"]
    monkeypatch.setattr(
        "backend.services.v1_evidence_service.V1EvidenceService.commit_intent", flaky_commit
    )
    summary = asyncio.run(_make_bridge().run())

    assert summary["materials_failed"] == 1
    assert summary["materials_committed"] == 1
    assert summary["signals_committed"] == 1     # 失败 material 不产信号
    assert _counts("v1_signals") == 1
    # 失败 material 的 signal 绝不存在
    import hashlib
    failed_mat = "mat" + hashlib.sha256(
        f"{fail_link}|{fail_title}".encode()
    ).hexdigest()[:24]
    assert _counts("v1_signals", "WHERE material_id = ?", (failed_mat,)) == 0


# ---------------------------------------------------------------------------
# 反例 5: 幂等重放 — 第二轮全走 IdempotentReplay, 库不重复
# ---------------------------------------------------------------------------
def test_second_run_skips_known_items(temp_db) -> None:
    """去重语义 (D1.1): parse 上提 + 内容寻址 id → 已入库条目在管线外跳过,
    避免 summary 漂移引发主键冲突噪音; 库不重复."""
    _seed_source()
    s1 = asyncio.run(_make_bridge().run())
    assert s1["materials_committed"] == 2
    assert _counts("v1_signals") == 2

    summary2 = asyncio.run(_make_bridge().run())  # 新实例, 同库
    assert summary2["skipped_known"] == 2
    assert summary2["materials_committed"] == 0
    assert _counts("v1_materials") == 2
    assert _counts("v1_signals") == 2


# ---------------------------------------------------------------------------
# 反例 6: 无 feed_url 的源 → run_intake_tick 跳过不炸 (job 层护栏)
# ---------------------------------------------------------------------------
def test_run_intake_tick_skips_source_without_feed_url(temp_db) -> None:
    from backend.services.v1_ingest_bridge import run_intake_tick
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO crawler_sources "
        "(id, category, name, kind, url, enabled) "
        "VALUES ('security:no-feed', 'security', '无 feed 源', 'rss', 'https://example.com/x', 1)"
    )
    conn.commit()
    summary = asyncio.run(run_intake_tick(["security:no-feed"]))
    assert summary["sources_skipped"] == 1
    assert summary["sources_run"] == 0


# ---------------------------------------------------------------------------
# 反例 7: feed 卫生 — 占位条目与 HTML 标签不进 material/signal
# ---------------------------------------------------------------------------
def test_placeholder_entry_and_html_tags_are_sanitized(temp_db) -> None:
    _seed_source()
    bridge = V1IngestBridge(_source())
    placeholder = {"title": "今日暂未更新资讯~", "link": "https://example.com/empty", "summary": "x"}
    html_entry = {
        "title": "<b>正常情报标题</b>",
        "link": "https://example.com/real",
        "summary": "<a href='https://x.com'>来源链接</a> 正文内容",
    }
    assert bridge._parse_entry(placeholder) is None          # 占位条目丢弃
    body = bridge._parse_entry(html_entry)
    assert body is not None
    assert body["title"] == "正常情报标题"                    # 标签已剥离
    assert "<a" not in body["summary"] and "正文内容" in body["summary"]


# ---------------------------------------------------------------------------
# D1.2: 信号立项携带证据 — v1_case_materials 绑定 + aggregate 证据回读
# ---------------------------------------------------------------------------
def test_case_creation_binds_signal_evidence_and_aggregate_reads_it(temp_db) -> None:
    _seed_source()
    asyncio.run(_make_bridge().run())
    conn = get_connection()
    sig_id = conn.execute("SELECT id FROM v1_signals LIMIT 1").fetchone()[0]

    # 立项: related_signal_ids → v1_case_materials 绑定
    from backend.services.case_service import CaseService
    case = CaseService().create_case(
        title="证据链贯通测试",
        question="立项携带证据 (D1.2)",
        priority="p2",
        related_signal_ids=[sig_id],
    )
    bound = conn.execute(
        "SELECT material_id, signal_id FROM v1_case_materials WHERE case_id = ?",
        (case.id,),
    ).fetchall()
    assert len(bound) == 1 and bound[0][1] == sig_id

    # aggregate 回读证据材料 (TestClient 只挂 case router — 隔离且轻量)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.case_api import router as case_router
    app = FastAPI()
    app.include_router(case_router)
    r = TestClient(app).get(f"/api/v1/cases/{case.id}/aggregate")
    assert r.status_code == 200
    evidence = r.json()["evidence_materials"]
    assert len(evidence) == 1
    assert evidence[0]["signal_id"] == sig_id
    assert evidence[0]["content_hash"]


def test_signals_api_filters_by_subject_id(temp_db) -> None:
    _seed_source()
    asyncio.run(_make_bridge().run())
    conn = get_connection()
    subject_id = conn.execute("SELECT subject_id FROM v1_signals LIMIT 1").fetchone()[0]

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.v1_signals_api import router as signals_router
    app = FastAPI()
    app.include_router(signals_router)
    client = TestClient(app)

    r = client.get(f"/api/v1/signals?subject_id={subject_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(i["subject_id"] == subject_id for i in body["items"])

    r404 = client.get("/api/v1/signals?subject_id=subj-not-exist-000000")
    assert r404.json()["total"] == 0


# ---------------------------------------------------------------------------
# D3 (SK-05 自动召回): 已发布知识 × case 文本匹配 — 复利飞轮「传动」
# ---------------------------------------------------------------------------
def _seed_knowledge(kid: str, title: str, body: str, status: str = "published") -> None:
    conn = get_connection()
    now = "2026-09-08T00:00:00+00:00"
    conn.execute(
        "INSERT OR REPLACE INTO v1_knowledge "
        "(id, kind, title, body, status, revision, "
        " prerequisites_json, counter_examples_json, evidence_refs_json, review_at, "
        " content_hash, created_at, updated_at) VALUES "
        "(?, 'playbook', ?, ?, ?, 1, '[]', '[]', '[]', ?, 'h', ?, ?)",
        (kid, title, body, status, now, now, now),
    )
    conn.commit()


def test_auto_recall_matches_published_knowledge(temp_db) -> None:
    from backend.services.knowledge_service import auto_recall_for_case
    _seed_knowledge(
        "KNOW01HBWXAZ2P3XQV5M8B7CDE",
        "FastGate 3200 路径遍历应急处置手册",
        "固件 <7.2.0 升级步骤…",
    )
    hits = auto_recall_for_case({"title": "FastGate 3200 漏洞研判", "question": "升级与排查"})
    assert len(hits) == 1
    assert hits[0]["id"] == "KNOW01HBWXAZ2P3XQV5M8B7CDE"
    assert hits[0]["reasons"]
    # 无关 case → 不浮现
    assert auto_recall_for_case({"title": "季度业绩回顾会议纪要", "question": "统计口径"}) == []


def test_auto_recall_ignores_non_published(temp_db) -> None:
    from backend.services.knowledge_service import auto_recall_for_case
    _seed_knowledge("KNOWDRAFT01HBWXAZ2P3XQV5MB", "FastGate 3200 手册", "正文", status="draft")
    _seed_knowledge("KNOWRETRA01HBWXAZ2P3XQV5M", "FastGate 3200 手册二", "正文", status="retracted")
    assert auto_recall_for_case({"title": "FastGate 3200 研判", "question": ""}) == []


def test_aggregate_includes_recall_candidates(temp_db) -> None:
    _seed_source()
    asyncio.run(_make_bridge().run())
    conn = get_connection()
    sig_id = conn.execute("SELECT id FROM v1_signals LIMIT 1").fetchone()[0]
    _seed_knowledge(
        "KNOWAGGR01HBWXAZ2P3XQV5M8B7",
        "FastGate 3200 路径遍历手册",
        "CVE-2026-31337 升级步骤",
    )
    from backend.services.case_service import CaseService
    case = CaseService().create_case(
        title="FastGate 3200 漏洞研判 (召回走查)",
        question="CVE-2026-31337 排查",
        related_signal_ids=[sig_id],
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.case_api import router as case_router
    app = FastAPI()
    app.include_router(case_router)
    r = TestClient(app).get(f"/api/v1/cases/{case.id}/aggregate")
    assert r.status_code == 200
    candidates = r.json()["recall_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["id"] == "KNOWAGGR01HBWXAZ2P3XQV5M8B7"
    assert candidates[0]["reasons"]


# ---------------------------------------------------------------------------
# D4: 复利卡 (诚实计数) — aggregate reuse_summary
# ---------------------------------------------------------------------------
def test_aggregate_reuse_summary_counts_real_adoptions(temp_db) -> None:
    _seed_source()
    asyncio.run(_make_bridge().run())
    conn = get_connection()
    sig_id = conn.execute("SELECT id FROM v1_signals LIMIT 1").fetchone()[0]
    _seed_knowledge(
        "KNOWSUM01HBWXAZ2P3XQV5M8B7",
        "FastGate 3200 路径遍历手册",
        "CVE-2026-31337 升级步骤",
    )
    from backend.services.case_service import CaseService
    case = CaseService().create_case(
        title="复利卡走查 (D4)",
        question="采用回执计数",
        related_signal_ids=[sig_id],
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.case_api import router as case_router
    from backend.api.knowledge_api import router as knowledge_router
    app = FastAPI()
    app.include_router(case_router)
    app.include_router(knowledge_router)
    client = TestClient(app)

    # 采用前: 0 (诚实计数, 非估算)
    body = client.get(f"/api/v1/cases/{case.id}/aggregate").json()
    assert body["reuse_summary"] == {"adoptions_total": 0, "adoptions_30d": 0, "distinct_knowledge": 0}

    # 采用后: 1/1/1 (真实回执计数)
    r_adopt = client.post("/api/v1/knowledge/KNOWSUM01HBWXAZ2P3XQV5M8B7/adopt", json={
        "case_id": case.id, "decision": "adopted", "condition_diff": [], "decided_by": "d4-test",
    })
    assert r_adopt.status_code in (200, 201)
    body2 = client.get(f"/api/v1/cases/{case.id}/aggregate").json()
    rs = body2["reuse_summary"]
    assert rs == {"adoptions_total": 1, "adoptions_30d": 1, "distinct_knowledge": 1}
