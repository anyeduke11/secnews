"""knowledge 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""

import asyncio
from datetime import datetime, timezone

from backend.logging_config import logger
from backend.scheduler.jobs._runtime import job_done_event

_logger = logger.bind(component="jobs")


async def knowledge_classify_job() -> None:
    """P1-5: 批量规则分类未分类知识条目 (domain/type 为 null 的)。

    背景: 81-94% 条目的 domain/topic/type/difficulty 为 null — 分类只靠
    手动 API + 每日 02:30 编译消费者 (配额 100/天), 消费速率远低于摄入。
    新增独立 job: 每 30min 处理最多 500 条未分类条目 (纯规则, 无 LLM/网络),
    P0.4: 只更新 DB, 不回写 md (分类是中间状态, md 只由用户/编译器写)。

    v0.6.3 P2-1: 全同步体 (DB 扫描 500 行 + upsert) 移入 worker 线程,
    不再占用事件循环。
    """
    import asyncio

    def _run() -> None:
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.auto_classifier import batch_classify

        _CLASSIFY_BATCH = 500
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, tags, source_url, domain, type, difficulty "
            "FROM knowledge_items "
            "WHERE domain IS NULL OR type IS NULL OR difficulty IS NULL "
            "ORDER BY ingested_at ASC LIMIT ?",
            (_CLASSIFY_BATCH,),
        ).fetchall()
        if not rows:
            return

        items = [dict(r) for r in rows]
        classified = batch_classify(items)
        updated = 0
        errors = 0
        now = datetime.now(timezone.utc).isoformat()
        for d in classified:
            item_id = d.get("id")
            if not item_id:
                continue
            try:
                db_item = knowledge_repo.get_item(item_id)
                if db_item is None:
                    continue
                changed = False
                if d.get("domain") and not db_item.domain:
                    db_item.domain = d["domain"]
                    changed = True
                if d.get("type") and not db_item.type:
                    db_item.type = d["type"]
                    changed = True
                if d.get("difficulty") and not db_item.difficulty:
                    db_item.difficulty = d["difficulty"]
                    changed = True
                if d.get("topic") and not db_item.topic:
                    db_item.topic = d["topic"]
                    changed = True
                if not changed:
                    continue
                db_item.updated_at = now
                # P0.4: 只更新 DB, 不回写 md (分类是中间状态)
                knowledge_repo.upsert_item(db_item)
                updated += 1
            except Exception as e:
                errors += 1
                _logger.warning(f"knowledge_classify item {item_id} failed: {e}")
        _logger.info(
            f"knowledge_classify_job: scanned={len(rows)} updated={updated} errors={errors}"
        )

    await asyncio.to_thread(_run)


async def knowledge_stub_backfill_job() -> None:
    """补全知识库空壳条目 — title 为 URL 或正文过短的条目, 抓取原文提取标题+摘要。

    背景: bookmark 批量导入产生大量无标题/无正文条目 (title=URL,
    body<40 字符), 知识库"信息进入"层质量差。本 job 尽力而为:
    每 6h 处理 20 条, 并发 3, 抓取失败跳过 (下轮重试), 不阻塞主流程。

    v0.6.3 P2-1: 三段式 — 候选 SELECT 与结果回写 (同步 DB/md IO) 移入
    worker 线程; 网络抓取 (aiohttp) 保留在事件循环 (真异步不阻塞)。
    """
    try:
        import asyncio as _asyncio
        import re as _re

        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services import ai_hub
        from backend.services.knowledge_sync import ITEMS_DIR

        _BATCH = 20

        def _select_candidates():
            conn = get_connection()
            return conn.execute(
                "SELECT id, title, source_url FROM knowledge_items "
                "WHERE (title LIKE 'http%' OR title = 'Untitled' OR title = '') "
                "   AND source_url IS NOT NULL AND source_url != '' "
                "ORDER BY ingested_at ASC LIMIT ?",
                (_BATCH,),
            ).fetchall()

        rows = await _asyncio.to_thread(_select_candidates)
        if not rows:
            return

        async def _fetch_one(r) -> tuple[str, str, str] | None:
            """抓取 URL, 返回 (item_id, real_title, snippet)."""
            item_id, old_title, url = r["id"], r["title"], r["source_url"]
            try:
                from backend.collectors.session import BackendSession
                timeout = 12
                async with BackendSession(timeout=timeout) as session:
                    resp = await session.get(url, timeout=timeout)
                    if resp.status != 200:
                        return None
                    html = await resp.text(encoding="utf-8", errors="replace")
                m = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
                real_title = ""
                if m:
                    real_title = _re.sub(r"\s+", " ", m.group(1)).strip()[:200]
                # 摘要: meta description
                desc = ""
                dm = _re.search(
                    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                    html, _re.IGNORECASE,
                )
                if not dm:
                    dm = _re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                        html, _re.IGNORECASE,
                    )
                if dm:
                    desc = _re.sub(r"\s+", " ", dm.group(1)).strip()[:500]
                return item_id, real_title or old_title, desc
            except Exception:
                return None

        sem = _asyncio.Semaphore(3)

        async def _limited(r):
            async with sem:
                return await _fetch_one(r)

        results = await _asyncio.gather(*[_limited(r) for r in rows])

        def _apply_results(results) -> None:
            """结果回写 (同步 DB + md IO) — worker 线程执行。"""
            from datetime import datetime, timezone

            updated = 0
            for res in results:
                if not res:
                    continue
                item_id, real_title, snippet = res
                try:
                    db_item = knowledge_repo.get_item(item_id)
                    if db_item is None:
                        continue
                    changed = False
                    if real_title and (not db_item.title or db_item.title.startswith("http")):
                        db_item.title = real_title
                        changed = True
                    if snippet and not db_item.topic:
                        db_item.topic = snippet[:100]
                        changed = True
                    if changed:
                        db_item.updated_at = datetime.now(timezone.utc).isoformat()
                        # 同时回写 .md 正文 (把摘要作为正文骨架)
                        md_path = ITEMS_DIR / f"{item_id}.md"
                        try:
                            if md_path.exists():
                                text = md_path.read_text(encoding="utf-8")
                                m = _re.match(r"^---\s*\n.*?\n---\s*\n", text, _re.DOTALL)
                                body = text[m.end():].strip() if m else text.strip()
                                if len(body) < 40:
                                    ai_hub.write_item(
                                        db_item.to_dict(),
                                        content=(f"# {real_title}\n\n{snippet}\n" if snippet else None),
                                        agent="job:stub_backfill",
                                    )
                                    changed = True
                        except Exception as md_err:
                            _logger.warning(f"stub backfill md write failed {item_id}: {md_err}")
                        knowledge_repo.upsert_item(db_item)
                        updated += 1
                except Exception as e:
                    _logger.warning(f"stub backfill item {item_id} failed: {e}")
            _logger.info(
                f"knowledge_stub_backfill_job: candidates={len(rows)} updated={updated}"
            )

        await _asyncio.to_thread(_apply_results, results)
    except Exception as e:
        _logger.error(f"knowledge_stub_backfill_job crashed: {e}")


async def knowledge_chunk_generation_job() -> None:
    """为无 chunks 的知识条目生成段落 chunks (FTS5 触发器自动同步索引)。

    背景: knowledge_chunks 表自建表后 0 行 — 生成只靠手动 API, 全文检索
    (FTS5) 从未有数据。本 job 每 30min 处理 200 条无 chunks 条目。
    """
    try:
        from backend.repository.db import get_connection
        from backend.services.chunk_service import generate_chunks_for_item

        _BATCH = 200
        conn = get_connection()
        rows = conn.execute(
            "SELECT id FROM knowledge_items ki "
            "WHERE NOT EXISTS (SELECT 1 FROM knowledge_chunks c WHERE c.item_id = ki.id) "
            "ORDER BY ki.ingested_at ASC LIMIT ?",
            (_BATCH,),
        ).fetchall()
        if not rows:
            return

        created = 0
        skipped = 0
        for r in rows:
            result = await asyncio.to_thread(generate_chunks_for_item, r["id"])
            if result.get("created", 0) > 0:
                created += result["created"]
            else:
                skipped += 1
        _logger.info(
            f"knowledge_chunk_generation_job: candidates={len(rows)} "
            f"created_chunks={created} skipped={skipped}"
        )
    except Exception as e:
        _logger.error(f"knowledge_chunk_generation_job crashed: {e}")


async def wiki_archiver_job() -> None:
    """每日扫描 SQLite 知识条目, 把 ingested_at < now-30d 且未收藏的条目
    原子写入 ``llm-wiki-2.0/items/{id}.md``, 同时建 sources/ 抓取快照 + retention 初始 entry。

    关闭策略: ``config.llm_wiki_v2=False`` 时直接跳过。
    """
    from backend.config import config

    if not config.llm_wiki_v2:
        _logger.info("wiki_archiver_job skipped (llm_wiki_v2 disabled)")
        return

    from backend.services.wiki_archiver import archive_overdue_items

    _t0 = datetime.now(tz=timezone.utc)
    try:
        stats = archive_overdue_items(
            wiki_root=config.llm_wiki_v2_path,
            days=30,
        )
        _logger.info(
            f"wiki_archiver_job: {stats} (wiki_root={config.llm_wiki_v2_path})"
        )
    except Exception as e:
        _logger.error(f"wiki_archiver_job crashed: {e}")
        try:
            job_done_event("wiki_archiver", "wiki_archiver", 0, ok=False)
        except Exception:
            pass
        return
    duration_ms = int((datetime.now(tz=timezone.utc) - _t0).total_seconds() * 1000)
    ok = stats.get("errors", 0) == 0
    try:
        job_done_event("wiki_archiver", "wiki_archiver", duration_ms, ok=ok)
    except Exception:
        pass


async def auto_extract_job() -> None:
    """v1.7 Phase 5: 同步执行 (无 Agent 时) 的简单标签提取.

    60s 间隔: 对未提取的 hotspot 调 extract_tags, 写入 tags + hotspot_tags.
    作为 agent_task_consumer_job 的同步回退路径.
    """
    try:
        from backend.repository.db import get_connection
        from backend.repository.tags_repo import TagRepository
        from backend.services.extract_service import extract_tags

        def _scan_and_extract():
            conn = get_connection()
            # 找未提取的 hotspot (无关联 tags)
            rows = conn.execute(
                "SELECT h.id, h.title, h.summary, h.category "
                "FROM hotspots h "
                "WHERE NOT EXISTS (SELECT 1 FROM hotspot_tags ht WHERE ht.hotspot_id = h.id) "
                "AND h.summary IS NOT NULL "
                "ORDER BY h.ingested_at DESC LIMIT 20"
            ).fetchall()
            return [dict(r) for r in rows]

        items = await asyncio.to_thread(_scan_and_extract)
        tag_repo = TagRepository()
        extracted = 0
        for item in items:
            tags = extract_tags(item.get("summary") or "", item.get("title") or "", item.get("category") or "")
            for t in tags:
                tag_id = t.get("tag_id") or t.get("id")
                if not tag_id:
                    continue
                confidence = float(t.get("confidence", 0.5))
                try:
                    # ensure tag
                    existing = tag_repo.get(tag_id)
                    if existing is None:
                        tag_repo.add(
                            tag_id, tag_id, "technique",
                            weight=confidence, description=tag_id,
                        )
                    tag_repo.attach(item["id"], tag_id, confidence=confidence)
                except Exception as e:
                    _logger.warning(f"auto_extract: tag {tag_id} failed: {e}")
            extracted += 1

        if extracted:
            _logger.info(f"auto_extract_job: extracted {extracted} hotspots")
    except Exception as e:
        _logger.error(f"auto_extract_job crashed: {e}")


async def content_draft_generation_job() -> None:
    """P3-4: 从已发布/高注意力知识条目生成内容草稿, 打通"知识→内容"闭环。

    背景: content_calendar=0、drafts=1 — 内容日历/草稿层无自动输入。
    本 job: 选 kl:publish 条目 + kl:structure 且 attention_score 较高的
    条目, 若尚无对应草稿则用条目正文 (knowledge/items/{id}.md) 生成草稿。

    v0.6.3 P2-1: 全同步体 (DB + md 读取 + 草稿落盘) 移入 worker 线程。
    """
    import asyncio

    def _run() -> None:
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.content_service import create_draft
        from backend.services.knowledge_sync import ITEMS_DIR

        _DRAFT_BATCH = 10
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title FROM knowledge_items "
            "WHERE lifecycle = 'kl:publish' "
            "   OR (lifecycle = 'kl:structure' AND COALESCE(attention_score, 0) >= 20) "
            "ORDER BY COALESCE(attention_score, 0) DESC, ingested_at DESC "
            "LIMIT ?",
            (_DRAFT_BATCH,),
        ).fetchall()
        if not rows:
            return

        # 已存在草稿的 title 集合 (避免重复生成)
        existing_drafts = {
            (d.get("title") or "").strip() for d in knowledge_repo.list_drafts()
        }
        created = 0
        for r in rows:
            title = (r["title"] or "").strip()
            if not title or title in existing_drafts:
                continue
            # 从条目 .md 读正文
            body = ""
            md_path = ITEMS_DIR / f"{r['id']}.md"
            try:
                if md_path.exists():
                    import re as _re
                    text = md_path.read_text(encoding="utf-8")
                    m = _re.match(r"^---\s*\n.*?\n---\s*\n", text, _re.DOTALL)
                    if m:
                        body = text[m.end():]
            except Exception:
                body = ""
            try:
                # draft 由 create_draft 落盘, 返回值不入变量 — 失败由 create_draft 抛错
                _draft = create_draft(title=title, content=body or f"# {title}\n")
                del _draft
                existing_drafts.add(title)
                created += 1
                # P3-4 补充: 草稿自动排期到内容日历 (7 天后, 避免与既有条目撞期)
                try:
                    from datetime import timedelta as _td

                    from backend.services.content_service import create_calendar_entry
                    sched_date = (
                        datetime.now(timezone.utc) + _td(days=7)
                    ).strftime("%Y-%m-%d")
                    create_calendar_entry(
                        date=sched_date,
                        topic=title[:80],
                        type="article",
                        source_items=[r["id"]],
                    )
                except Exception as cal_err:
                    _logger.warning(f"content calendar schedule failed for {r['id']}: {cal_err}")
            except Exception as e:
                _logger.warning(f"content draft create failed for {r['id']}: {e}")
        _logger.info(
            f"content_draft_generation_job: candidates={len(rows)} created={created}"
        )

    await asyncio.to_thread(_run)


async def scheduled_migrate_job() -> None:
    """Phase 1f Task 6.10: 定时迁移高掌握度条目到本地 wiki。

    每周日 05:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.federation_service import migrate_high_mastery_items

        result = await asyncio.to_thread(migrate_high_mastery_items)
        _logger.info(
            f"scheduled_migrate_job: migrated={result.get('migrated')}, "
            f"skipped={result.get('skipped')}"
        )
    except Exception as e:
        _logger.error(f"scheduled_migrate_job crashed: {e}")
