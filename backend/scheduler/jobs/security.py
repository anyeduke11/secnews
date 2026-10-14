"""security 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio
from pathlib import Path

from backend.logging_config import logger

_logger = logger.bind(component="jobs")

# MP-2 抽取模型名 — 非 MOCK_LLM_MODEL("mock-extract-v1") ⇒ 触发真实 ai_hub LLM 调用,
# 调用失败/返回非 JSON 时 extract_for_report 自动降级 mock.
MP2_LLM_MODEL = "ai_hub-extract"


async def mitre_sync_job() -> None:
    """Phase 2: 每周同步 MITRE ATT&CK STIX 数据到 security_entities + security_edges。

    触发条件
    --------
    - scheduler 每周日 04:00 Asia/Shanghai 触发
    - 失败只 log.error，不抛异常（与既有 job 模式一致）

    注意
    ----
    - 首次同步建议手动触发 /api/security/mitre/sync (clear=True)
    - 后续增量同步由 clear=False 控制
    """
    try:
        from backend.security.mitre_attack import MitreAttackClient

        client = MitreAttackClient()
        # v0.7 Batch ⑨ B9-4: 增量同步 (默认 force=False, 304 跳过下载)
        result = await asyncio.to_thread(client.sync_to_db, clear=False, force=False)
        _logger.info(
            f"mitre_sync_job: entities={result['entities']} edges={result['edges']} "
            f"from_cache={result['from_cache']} new_modified={result['new_modified']}"
        )
    except Exception as e:
        _logger.error(f"mitre_sync_job crashed: {e}")


async def security_enrichment_job() -> None:
    """Phase 3: 每 300s 扫描未 enrichment 的 knowledge items，异步 enrichment.

    不阻塞采集主路径，独立 job 运行。

    P0-6 (2026-08-15): 修复两处致命错误:
    1. SELECT 从 hotspots 查 cve_ids/attack_techniques/compliance_refs —
       这些列只存在于 knowledge_items, hotspots 无此列 → 每轮必抛
       "no such column" 崩溃。改为查询 knowledge_items。
    2. UPDATE 用字符串拼接 JSON (COALESCE || ',' || ?) — 产生非法 JSON。
       改为 json 模块安全合并 (去重追加)。

    v0.4.0 收尾 (2026-08-16):
    3. 去掉「近 24h」限制 — 历史条目 (含 CVE/ATT&CK 标题模式) 从未被富化,
       富化字段全 NULL, item_entities 无数据可桥接。改为持续回填 (最旧优先,
       已富化条目因字段非 NULL 自动排除)。
    4. 无实体的条目打标 cve_ids='[]' — 避免每轮重复扫描无匹配条目。
    5. 富化出的实体写入 item_entities 桥接表 (item ↔ security entity),
       security graph 与 knowledge 由此统一命名空间。
    """
    try:
        import asyncio

        def _run() -> None:
            _run_enrichment_sync()

        await asyncio.to_thread(_run)
    except Exception as e:
        _logger.error(f"security_enrichment_job crashed: {e}")


def _run_enrichment_sync() -> None:
    """security_enrichment_job 的同步体 (v0.6.3 P2-1: 移入 worker 线程)。"""
    try:
        import json as _json

        from backend.domain.security_models import _now_iso
        from backend.repository.db import get_connection, knowledge_items_table
        from backend.security.enricher import enrich_batch

        conn = get_connection()

        # v0.4.0 预回填: 已富化 (字段非空) 但无 item_entities 桥接的条目
        # (历史富化发生在桥接逻辑之前, 字段有数据但桥接表为空)
        try:
            backfilled = 0
            rows_with_ent = conn.execute(
                "SELECT id, cve_ids, attack_techniques, compliance_refs "
                f"FROM {knowledge_items_table()} "
                "WHERE (cve_ids IS NOT NULL AND cve_ids != '[]') "
                "   OR (attack_techniques IS NOT NULL AND attack_techniques != '[]') "
                "   OR (compliance_refs IS NOT NULL AND compliance_refs != '[]')"
            ).fetchall()
            for r in rows_with_ent:
                exists = conn.execute(
                    "SELECT 1 FROM item_entities WHERE item_id = ? LIMIT 1", (r["id"],)
                ).fetchone()
                if exists:
                    continue
                for field, etype in (
                    ("cve_ids", "cve"),
                    ("attack_techniques", "attack_technique"),
                    ("compliance_refs", "compliance"),
                ):
                    val = r[field]
                    if not val:
                        continue
                    try:
                        for v in _json.loads(val):
                            conn.execute(
                                "INSERT OR IGNORE INTO item_entities "
                                "(item_id, entity_name, entity_type, confidence, source, created_at) "
                                "VALUES (?, ?, ?, 0.5, 'rule', ?)",
                                (r["id"], str(v), etype, _now_iso()),
                            )
                            backfilled += 1
                    except (ValueError, TypeError):
                        pass
            if backfilled:
                # P0-10: 例行回填 (每日同量) → DEBUG
                _logger.debug(f"security_enrichment_job: backfilled {backfilled} item_entities")
        except Exception as e:
            _logger.warning(f"item_entities backfill failed: {e}")

        # 未富化条目 (不限时间; 优先含 CVE/ATT&CK/合规模式的标题 — 富化价值
        # 高, 避免先被无实体空壳条目占满批次; 富化后字段非 NULL 自动排除)
        # (knowledge_items 无 summary 列 — 正文在 .md 文件; 富化文本用
        # title + tags 拼接, enricher 的 CVE/ATT&CK/合规正则主要匹配标题)
        rows = conn.execute(
            f"SELECT id, title, tags FROM {knowledge_items_table()} "
            "WHERE (cve_ids IS NULL AND attack_techniques IS NULL AND compliance_refs IS NULL) "
            "ORDER BY "
            "  (title LIKE '%CVE%' OR title LIKE '%漏洞%' OR title LIKE '%ATT%CK%' "
            "   OR title LIKE '%攻击%' OR title LIKE '%安全%' OR title LIKE '%风险%') DESC, "
            "  ingested_at ASC LIMIT 200"
        ).fetchall()
        if not rows:
            return

        items = []
        for r in rows:
            item = {"id": r["id"], "title": r["title"] or ""}
            tags = r["tags"] or ""
            if tags:
                item["summary"] = " ".join(tags) if isinstance(tags, str) else " ".join(tags)
            items.append(item)
        enriched = enrich_batch(items)
        if not enriched:
            # v0.4.0: 无匹配 → 给本批条目打标, 防重复扫描
            now0 = _now_iso()
            for r in rows:
                try:
                    conn.execute(
                        f"UPDATE {knowledge_items_table()} SET cve_ids = '[]', updated_at = ? WHERE id = ?",
                        (now0, r["id"]),
                    )
                except Exception:
                    pass
            conn.commit()
            _logger.info(
                f"security_enrichment_job: {len(rows)} items no entities, marked done"
            )
            return

        now = _now_iso()
        count = 0
        for e in enriched:
            eid = e.get("id")
            if not eid:
                continue
            try:
                row = conn.execute(
                    "SELECT cve_ids, attack_techniques, compliance_refs "
                    f"FROM {knowledge_items_table()} WHERE id = ?",
                    (eid,),
                ).fetchone()
                if row is None:
                    continue

                def _merge_json(existing: str | None, new_val: str | None) -> str | None:
                    """合并 JSON 数组字段 (去重, 保持顺序)。"""
                    merged: list = []
                    if existing:
                        try:
                            merged.extend(_json.loads(existing))
                        except (ValueError, TypeError):
                            pass
                    if new_val:
                        try:
                            merged.extend(_json.loads(new_val))
                        except (ValueError, TypeError):
                            pass
                    # 去重且保留顺序
                    seen = set()
                    deduped = []
                    for v in merged:
                        if v not in seen:
                            seen.add(v)
                            deduped.append(v)
                    return _json.dumps(deduped, ensure_ascii=False) if deduped else None

                updates = {}
                entity_rows: list[tuple[str, str, float]] = []
                for field, etype in (
                    ("cve_ids", "cve"),
                    ("attack_techniques", "attack_technique"),
                    ("compliance_refs", "compliance"),
                ):
                    merged = _merge_json(row[field], e.get(field))
                    if merged:
                        updates[field] = merged
                        try:
                            for v in _json.loads(merged):
                                entity_rows.append((str(v), etype, 0.5))
                        except (ValueError, TypeError):
                            pass
                if updates:
                    updates["updated_at"] = now
                    set_sql = ", ".join(f"{f} = ?" for f in updates)
                    conn.execute(
                        f"UPDATE {knowledge_items_table()} SET {set_sql} WHERE id = ?",
                        (*updates.values(), eid),
                    )
                    count += 1

                # v0.4.0 收尾: 写入 item_entities 桥接表 (item → security entity)
                # 此前 item_entities 全库无写入方 (0 行), security graph 与
                # knowledge 完全隔离。enrichment 出的 CVE/ATT&CK/合规实体
                # 在此落桥接, 供图谱/查询/实体统一命名空间使用。
                # (注意: item_entities.source 有 CHECK 约束 ('rule','agent','manual'))
                if entity_rows:
                    for name, etype, conf in entity_rows:
                        conn.execute(
                            "INSERT OR IGNORE INTO item_entities "
                            "(item_id, entity_name, entity_type, confidence, source, created_at) "
                            "VALUES (?, ?, ?, ?, 'rule', ?)",
                            (eid, name, etype, conf, now),
                        )
            except Exception as item_err:
                _logger.warning(f"security_enrichment_job item {eid} failed: {item_err}")

        conn.commit()
        # P0-10: 零富化例行 → DEBUG
        _log = _logger.info if count else _logger.debug
        _log(f"security_enrichment_job: processed {len(rows)} items, enriched {count}")
    except Exception as e:
        _logger.error(f"security_enrichment_job crashed: {e}")


async def cve_sync_to_security_job() -> None:
    """Phase 14: 每 30 分钟同步 CVE 到 security_entities."""
    try:
        from backend.services.cve_knowledge_sync import sync_cve_to_security
        report = await asyncio.to_thread(sync_cve_to_security)
        # P0-10: 全零同步 (例行幂等命中) → DEBUG
        _log = (
            logger.info
            if (report["synced"] or report["updated"] or report["failed"])
            else logger.debug
        )
        _log(
            f"cve_sync_to_security_job: synced={report['synced']} "
            f"updated={report['updated']} failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"cve_sync_to_security_job crashed: {e}")


async def security_entity_concept_sync_job() -> None:
    """统一 security_entities 与 knowledge_concepts 命名空间。

    PRD A.3.2 遗留: security 实体 (CVE/ATT&CK/合规) 与 knowledge concepts
    两套库完全隔离, 同一实体重复无互引。此前 item_entities 无写入方 (0 行)。

    v0.4.0 收尾, 本 job 三件事:
    1. item_entities 中的实体 → 确保 security_entities 存在
       (CVE 编号以 type='cve' 入库, name 为 CVE-ID, id 为实体名)
    2. 高频实体 (≥3 条引用) → 创建 knowledge concept, 通过 entity_type +
       external_id 指向 security_entity (两库互引)
    3. 幂等: 已存在的跳过

    v0.6.3 P2-1: 全同步体 (聚合查询 + upsert + commit) 移入 worker 线程。
    """
    try:
        import asyncio

        await asyncio.to_thread(_run_entity_concept_sync)
    except Exception as e:
        _logger.error(f"security_entity_concept_sync_job crashed: {e}")


def _run_entity_concept_sync() -> None:
    """security_entity_concept_sync_job 的同步体 (v0.6.3 P2-1)。"""
    try:
        from backend.domain.security_models import _now_iso
        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo

        conn = get_connection()
        now = _now_iso()

        # 1. item_entities → security_entities (按实体名/类型聚合)
        rows = conn.execute(
            "SELECT entity_name, entity_type, COUNT(*) AS cnt "
            "FROM item_entities GROUP BY entity_name, entity_type"
        ).fetchall()
        synced = 0
        for r in rows:
            name = r["entity_name"]
            etype = r["entity_type"]
            try:
                exists = conn.execute(
                    "SELECT 1 FROM security_entities WHERE name = ? AND entity_type = ? LIMIT 1",
                    (name, etype),
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO security_entities "
                        "(id, entity_type, name, description, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (f"{etype}:{name}", etype, name, f"自动同步自知识库实体 ({etype})", now, now),
                    )
                    synced += 1
            except Exception as e:
                _logger.warning(f"security_entity sync {name} failed: {e}")

        # 2. 高频实体 → knowledge concept 互引 (≥3 条引用, 防概念污染)
        from backend.domain.knowledge_models import KnowledgeConcept
        concept_created = 0
        concept_linked = 0
        for r in rows:
            if r["cnt"] < 3:
                continue
            name = r["entity_name"]
            etype = r["entity_type"]
            slug = f"{etype}-{name}".lower().replace(":", "-").replace("/", "-")[:120]
            try:
                concept = knowledge_repo.get_concept(slug)
                if concept is None:
                    knowledge_repo.upsert_concept(KnowledgeConcept(
                        slug=slug,
                        title=name,
                        domain="security",
                        source_items=[],
                        updated_at=now,
                        entity_type=etype,
                        external_id=f"{etype}:{name}",
                        external_ref=f"security_entity:{etype}:{name}",
                    ))
                    concept_created += 1
                elif not concept.external_id:
                    concept.entity_type = etype
                    concept.external_id = f"{etype}:{name}"
                    concept.external_ref = f"security_entity:{etype}:{name}"
                    concept.updated_at = now
                    knowledge_repo.upsert_concept(concept)
                    concept_linked += 1
            except Exception as e:
                _logger.warning(f"concept link {name} failed: {e}")

        conn.commit()
        # P0-10: 全零同步 (例行幂等命中) → DEBUG
        _log = (
            _logger.info
            if (synced or concept_created or concept_linked)
            else _logger.debug
        )
        _log(
            f"security_entity_concept_sync_job: entities={len(rows)} "
            f"synced={synced} concept_created={concept_created} concept_linked={concept_linked}"
        )
    except Exception as e:
        _logger.error(f"security_entity_concept_sync_job crashed: {e}")


async def secrets_rotation_check_job() -> None:
    """v0.7 Batch ⑨ B9-2: secrets 主密钥轮换检查 (每日 09:00 Asia/Shanghai).

    通过 SecretsService.rotation_status() 拉 should_rotate 标志,
    若 True 调 AlertDispatcher 发所有启用 channel (webhook/slack/feishu/dingtalk/email),
    并写 audit_log 落 (secrets.rotation_reminded).

    cooldown 24h: 同一天不会重复发, 防止反复刷屏.
    cooldown 状态落在 settings.kv key 'secrets.rotation.last_notified_at'.
    """
    try:
        from datetime import datetime, timezone

        from backend.observability_records import record_audit
        from backend.repository.settings_repo import SettingsRepository
        from backend.services.alert_dispatcher import AlertPayload, dispatch
        from backend.services.secrets_service import SecretsService

        status = await asyncio.to_thread(SecretsService().rotation_status)
        if not status.get("setup") or not status.get("should_rotate"):
            return

        repo = SettingsRepository()
        last_iso = repo.get("secrets.rotation.last_notified_at", None)
        today = datetime.now(timezone.utc).date().isoformat()
        if last_iso == today:
            _logger.info("secrets_rotation_check_job: already notified today, skip")
            return

        age = status.get("age_days", 0)
        last_rotated = status.get("last_rotated_at", "?")
        remind = status.get("remind_days", 90)
        payload = AlertPayload(
            metric="secrets.rotation_age_days",
            level="warn",
            value=float(age),
            threshold=float(remind),
            window_minutes=0,
            detail={
                "title": "Secrets 主密钥需轮换",
                "message": (
                    f"Secrets 主密钥已使用 {age} 天 (>= {remind} 天阈值)。\n"
                    f"最后轮换时间: {last_rotated}\n"
                    f"建议立即通过 POST /api/secrets/rotate 轮换以保 LLM 凭据安全。"
                ),
                "age_days": age,
                "last_rotated_at": last_rotated,
                "remind_days": remind,
                "action": "POST /api/secrets/rotate",
            },
            fired_at=datetime.now(timezone.utc).isoformat(),
            source="secrets_rotation_check_job",
        )
        await dispatch(payload, alert_id=None)
        repo.set("secrets.rotation.last_notified_at", today)
        try:
            record_audit(
                "system",
                action="secrets.rotation_reminded",
                target="secrets.master_key",
                detail={"age_days": age, "remind_days": status.get("remind_days", 90)},
            )
        except Exception:
            pass
        _logger.warning(f"secrets_rotation_check_job: notified (age_days={age})")
    except Exception as e:
        _logger.error(f"secrets_rotation_check_job crashed: {e}")


# ---------------------------------------------------------------------------
# MP-2 事件类型实例化 (采集 → 抽取 → 入候选池)
# ---------------------------------------------------------------------------
def _mp2_ingest_all() -> dict[str, str]:
    """采集 agent_A~E 语料到 incident_reports; 返回 {event_type_id: agent_owner}.

    同步 (供 asyncio.to_thread 包裹). 路由差异:
      - agent_A: 每子目录 = 一个 event_type (5 类)
      - agent_B: 扁平目录, 按 frontmatter event_type_id 分组 (3 类混合)
      - agent_C/D/E: 扁平单类目录, bulk_ingest 绑定固定 event_type
    """
    from backend.services.incident_report_service import (
        MIN_REPORT_BODY_LEN,
        IncidentReportService,
        _split_frontmatter,
    )

    corpus_root = Path(__file__).resolve().parents[3] / "data" / "security" / "incidents"
    svc = IncidentReportService()
    et_owner: dict[str, str] = {}

    # agent_A — 每子目录一个 event_type
    agent_a = corpus_root / "agent_A"
    if agent_a.exists():
        for sub in sorted(p for p in agent_a.iterdir() if p.is_dir()):
            svc.bulk_ingest_from_dir(sub, sub.name, "A")
            et_owner[sub.name] = "A"

    # agent_B — 扁平目录, frontmatter event_type_id 分类 (bulk_ingest 不支持混合类)
    agent_b = corpus_root / "agent_B"
    if agent_b.exists():
        for md in sorted(agent_b.glob("*.md")):
            front, body = _split_frontmatter(md.read_text(encoding="utf-8"))
            et_id = (front.get("event_type_id") or "").strip()
            if not et_id:
                _logger.warning(f"mp2_ingest: {md.name} missing event_type_id, skipped")
                continue
            if not body or len(body.strip()) < MIN_REPORT_BODY_LEN:
                _logger.warning(f"mp2_ingest: {md.name} body too short, skipped")
                continue
            svc.ingest_report(
                source_url=(front.get("source_url") or "").strip()
                or f"mp2-agent-B-local://{md.stem}",
                title=(front.get("title") or md.stem).strip(),
                fetched_at=(front.get("fetched_at") or "").strip(),
                report_md=body,
                event_class_hint=et_id,
                agent_owner="B",
            )
            et_owner[et_id] = "B"

    # agent_C/D/E — 扁平单类目录
    for owner, dirname, et_id in (
        ("C", "agent_C", "evt_fraud"),
        ("D", "agent_D", "evt_data_breach"),
        ("E", "agent_E", "evt_regulatory_notice"),
    ):
        d = corpus_root / dirname
        if d.exists():
            svc.bulk_ingest_from_dir(d, et_id, owner)
            et_owner[et_id] = owner

    return et_owner


def _mp2_reports_with_candidates(event_type_id: str) -> set[str]:
    """返回该 event_type 下已产出候选的 source_report_id 集合 (增量过滤)."""
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT source_report_id FROM event_technique_candidates "
        "WHERE event_type_id = ?",
        (event_type_id,),
    ).fetchall()
    return {r[0] for r in rows}


async def mp2_extract_job() -> None:
    """MP-2 事件类型实例化 — 采集 agent_A~E 语料 → 逐报告抽取 technique 候选 → 入候选池.

    - 覆盖 agent_A~E 全部 11 类 event_type
    - 走真实 ai_hub LLM (MP2_LLM_MODEL); 调用失败/非 JSON 自动降级 mock
    - 增量: 已产出候选的 source_report_id 跳过, 避免每 tick 重跑 LLM
    - 失败只 log.error, 不抛异常 (与既有 job 模式一致)
    """
    try:
        from backend.services.event_technique_extract_service import (
            EventTechniqueExtractService,
        )
        from backend.services.incident_report_service import IncidentReportService

        et_owner = await asyncio.to_thread(_mp2_ingest_all)
        svc = EventTechniqueExtractService()
        report_svc = IncidentReportService()

        reports_processed = 0
        candidates_inserted = 0
        for et_id, owner in et_owner.items():
            done = await asyncio.to_thread(_mp2_reports_with_candidates, et_id)
            reports = await asyncio.to_thread(
                report_svc.list_reports_by_event_type, et_id, 50
            )
            for r in reports:
                if r["id"] in done:
                    continue
                try:
                    res = await svc.extract_for_report(r["id"], et_id, MP2_LLM_MODEL, owner)
                except Exception as e:
                    _logger.error(f"mp2_extract: report {r['id']} ({et_id}) failed: {e}")
                    continue
                reports_processed += 1
                candidates_inserted += res["candidates_inserted"]

        _logger.info(
            f"mp2_extract_job: event_types={len(et_owner)} "
            f"reports_processed={reports_processed} "
            f"candidates_inserted={candidates_inserted}"
        )
    except Exception as e:
        _logger.error(f"mp2_extract_job crashed: {e}")
