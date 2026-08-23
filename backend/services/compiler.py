"""Compiler service — create + consume compile tasks.

Design: backend creates task records + pending task files, and (P0 消费策略)
now also executes them with a deterministic rule-based consumer
(``consume_compile_tasks``). The LLM 深度编译 (概念提取/摘要) 仍由 Agent
通过 knowledge-base-manager skill 完成 — 但存量积压的分类核心价值由
auto_classifier 的确定性规则覆盖, 不再依赖 Agent 人工消化。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.compiler")

# P0 背压: 单次 stale 检测配额。历史 bug: 把所有 compiled=false 条目
# 全部视为 stale, 每日定时任务一次生成 ~400 个任务 (10 条/批), 积压到
# 1980+ 无消费者。现在每次最多返回 STALE_ITEM_DAILY_QUOTA 条 (按
# updated_at 最旧优先), 形成自然背压, 让 Agent 有节奏地消化积压。
STALE_ITEM_DAILY_QUOTA = 50

# P0 消费策略: 自动消费者单次配额 (按 item 数计)。每日任务创建配额为
# 50 条, 消费者配额 100 条/次 > 创建速率, 队列可以净流出 (存量归档 +
# 新任务当天被消费)。
CONSUME_DAILY_QUOTA = 100

# 归档阈值: pending compile 任务超过该天数仍未被执行, 视为积压并归档
# (标记 failed + 文件移入 failed/)。与 scheduled_compile_job 的背压配合,
# 保证队列即使消费者短暂失速也不会再次无限增长。
ARCHIVE_MAX_AGE_DAYS = 7

# 每个 compile 任务包含的 item 数上限 (创建与消费共用同一批大小)。
COMPILE_BATCH_SIZE = 10

# v1.7 后 lifecycle 已切换到 5 阶段 KL (kl:raw → kl:refine → kl:link →
# kl:structure → kl:publish)。detect_stale_items 的 "已编译" 判定需要同时
# 识别 legacy 3 阶段 (generate) 与 KL 阶段 (kl:structure / kl:publish),
# 否则已结构化的条目会被当作 stale 无限重新入队。
COMPILED_LIFECYCLES = frozenset({"generate", "kl:structure", "kl:publish"})

# 归档失败任务文件的前置标记 (对齐 Phase 1j failed/task-100.md 惯例)。
ARCHIVE_REASON = (
    "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
)

PENDING_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "pending"
)

DONE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "done"
)

FAILED_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "failed"
)

ITEMS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "items"
)

# 任务文件 frontmatter 提取 (与 knowledge_sync 相同的最小 YAML 子集)。
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_updated_at(item) -> datetime | None:
    """解析 item.updated_at 为可比较的 datetime (用于最旧优先排序).

    兼容 ISO 8601 带 Z 后缀 / 无时区 (按 UTC 处理) / 解析失败返回 None。
    """
    updated_at_str = item.updated_at
    if not updated_at_str:
        return None
    if updated_at_str.endswith("Z"):
        updated_at_str = updated_at_str[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(updated_at_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def detect_stale_items(limit: int = STALE_ITEM_DAILY_QUOTA) -> dict:
    """Detect items that need recompilation.

    Conditions:
      1. compiled=false → reason="compiled=false"
      2. .md file mtime > SQLite updated_at → reason="file_modified"

    P0 背压修复:
      - 不再把全部 compiled=false 视为 stale — 默认只返回 ``limit`` 条
        (50), 按 updated_at 最旧优先排序, 避免历史积压一次性全量入队。
      - ``limit=0`` 表示不限制 (预览全量用)。

    Returns: {"stale_items": [id1, id2], "reasons": {id1: "compiled=false", ...}}
    """
    stale_items: list = []
    reasons: dict[str, str] = {}

    items = knowledge_repo.list_items(limit=10000)
    for item in items:
        # Condition 1: 未编译 (legacy compiled=false 语义; v1.7 后兼容 KL
        # 5 阶段 — kl:structure / kl:publish 视为已编译, 避免无限重新入队)
        if item.lifecycle not in COMPILED_LIFECYCLES:
            stale_items.append(item)
            reasons[item.id] = "compiled=false"
            continue

        # Condition 2: file mtime > SQLite updated_at
        md_path = ITEMS_DIR / f"{item.id}.md"
        if not md_path.exists():
            continue
        try:
            file_mtime = os.path.getmtime(md_path)
            file_mtime_dt = datetime.fromtimestamp(file_mtime, tz=timezone.utc)
        except OSError:
            continue

        updated_at_dt = _parse_updated_at(item)
        if updated_at_dt is None:
            continue
        if file_mtime_dt > updated_at_dt:
            stale_items.append(item)
            reasons[item.id] = "file_modified"

    # 背压: 按 updated_at 最旧优先 (缺失 updated_at 视为最旧, 优先处理),
    # 只取前 limit 条。limit<=0 表示不限制。
    if limit and limit > 0 and len(stale_items) > limit:
        _SENTINEL_OLD = datetime.min.replace(tzinfo=timezone.utc)
        stale_items.sort(key=lambda it: _parse_updated_at(it) or _SENTINEL_OLD)
        stale_items = stale_items[:limit]

    return {
        "stale_items": [it.id for it in stale_items],
        "reasons": {it.id: reasons[it.id] for it in stale_items},
    }


def _pending_compile_item_ids() -> set[str]:
    """收集所有 pending compile 任务中已入队的 item_id (创建前去重用).

    knowledge_tasks 表没有 item_id 列 — item_ids 存在 params JSON 里
    ({"item_ids": [...]}), 因此遍历 pending 任务解析 params 求并集。
    查询失败时返回空集 (不去重, 仅 log 警告, 不阻断任务创建)。
    """
    queued: set[str] = set()
    try:
        tasks = knowledge_repo.list_tasks(status="pending")
    except Exception as e:
        log.warning(f"failed to list pending tasks for dedup: {e}")
        return queued
    for t in tasks:
        if t.task_type != "compile":
            continue
        params = t.params or {}
        item_ids = params.get("item_ids")
        if isinstance(item_ids, list):
            queued.update(str(i) for i in item_ids)
    return queued


def create_compile_task(item_ids: list[str] | None = None) -> dict:
    """Create a compile task.

    Args:
        item_ids: specific item IDs to compile. If None, detect stale items
                  (compiled=false or file modified, 背压限 50 条). If empty
                  list, return no_items.

    P0 去重: 创建前检查 pending 队列中是否已有同 item 的任务, 命中则跳过。

    Returns:
        ≤10 items: {task_id, status, items_to_compile, skipped_duplicates}
        >10 items: {tasks: [{task_id, items_count}], total_tasks, items_to_compile,
                    skipped_duplicates}
    """
    if item_ids is None:
        # Detect stale items (compiled=false OR file modified, 限量背压)
        stale = detect_stale_items()
        item_ids = stale["stale_items"]
    elif not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": 0}

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": 0}

    # P0 去重: 跳过 pending 队列中已存在的同 item 任务
    skipped_duplicates = 0
    pending_ids = _pending_compile_item_ids()
    if pending_ids:
        deduped = [iid for iid in item_ids if iid not in pending_ids]
        skipped_duplicates = len(item_ids) - len(deduped)
        item_ids = deduped

    if not item_ids:
        return {"task_id": None, "status": "no_items", "items_to_compile": 0,
                "skipped_duplicates": skipped_duplicates}
    if skipped_duplicates:
        log.info(
            f"create_compile_task: skipped {skipped_duplicates} item(s) "
            f"already pending in queue"
        )

    # Batch processing: COMPILE_BATCH_SIZE items per task
    BATCH_SIZE = COMPILE_BATCH_SIZE
    if len(item_ids) <= BATCH_SIZE:
        task_id = _create_single_compile_task(item_ids)
        _trigger_map_update()
        return {
            "task_id": task_id,
            "status": "pending",
            "items_to_compile": len(item_ids),
            "skipped_duplicates": skipped_duplicates,
        }

    # Multiple batches
    batches = [
        item_ids[i:i + BATCH_SIZE]
        for i in range(0, len(item_ids), BATCH_SIZE)
    ]
    tasks_created: list[dict] = []
    for batch in batches:
        task_id = _create_single_compile_task(batch)
        tasks_created.append({"task_id": task_id, "items_count": len(batch)})

    _trigger_map_update()
    return {
        "tasks": tasks_created,
        "total_tasks": len(tasks_created),
        "items_to_compile": len(item_ids),
        "skipped_duplicates": skipped_duplicates,
    }


def _create_single_compile_task(item_ids: list[str]) -> int:
    """Create a single compile task record + pending task file. Returns task_id."""
    task = knowledge_repo.create_task("compile", {"item_ids": item_ids})

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    task_path = PENDING_DIR / f"task-{task.id}.md"
    id_list = "\n".join(f"- [[{iid}]]" for iid in item_ids)

    task_path.write_text(
        f"""---
task_type: "compile"
status: "pending"
created_at: "{now_iso()}"
params:
  item_ids: {item_ids}
---

# 编译任务

请对以下知识条目执行编译：

{id_list}

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{{slug}}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
""",
        encoding="utf-8",
    )

    log.info(f"created compile task {task.id}: {len(item_ids)} items")
    return task.id


def _trigger_map_update() -> None:
    """Proactively update _MAP.md after creating compile tasks."""
    try:
        from backend.services.map_updater import update_map
        update_map()
    except Exception as e:
        log.warning(f"failed to update _MAP.md after compile task: {e}")


# ═══════════════════════════════════════════════════════════════
# P0 消费策略 — 规则式自动消费者 + 存量积压归档
# ═══════════════════════════════════════════════════════════════

def _advance_compile_lifecycle(current: str) -> str | None:
    """规则式编译后的 lifecycle 推进 (compile 语义第 4 步: 标记 compiled)。

    P1-3: 统一为 KL 五阶段规范。
    - ``kl:link`` → ``kl:structure``: KL 状态机 T3 转移 (摘要+结构化完成)。
      规则式编译以"分类完成"作为结构化的确定性代理。
    - legacy 3 阶段 (``signal`` / ``amplify:*``) → ``kl:structure``
      (旧语义 ``generate``/``compiled=true`` 对应 KL 的 structure→publish 之间,
      取 structure 为确定性落点, 后续由 T4 发布)。
    - 其余状态 (``kl:raw`` / ``kl:refine`` / ``kl:structure`` /
      ``kl:publish`` / ``generate``) 不推进, 由 KL 状态机 / Agent 负责。

    注意: 未命中分类规则的条目也推进 — 否则它们会每天被 detect_stale_items
    重新入队, 造成"消费→done→重新入队"死循环。分类缺口 (如标签名与规则表
    不完全匹配) 留给后续规则增强或 LLM 通道, 而不是阻塞队列。
    """
    if current == "kl:link":
        return "kl:structure"
    if current in ("signal", "amplify:tagged", "amplify:linked", "amplify:complete"):
        return "kl:structure"
    return None


def _task_created_dt(task) -> datetime | None:
    """解析任务 created_at 为 aware datetime (解析失败返回 None)."""
    raw = getattr(task, "created_at", "") or ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _older_than_days(task, max_age_days: int) -> bool:
    """任务创建是否早于 ``max_age_days`` 天前。

    ``max_age_days`` 为 None 时不限年龄 (全部视为积压)。created_at 解析
    失败按积压处理 (不阻塞清理)。
    """
    if max_age_days is None:
        return True
    dt = _task_created_dt(task)
    if dt is None:
        return True
    return (datetime.now(timezone.utc) - dt) > timedelta(days=max_age_days)


def _read_task_file_body(task_id: int) -> str:
    """读取 pending 任务文件的正文 (frontmatter 之后的部分)。

    用于归档时保留任务描述; 文件不存在/无 frontmatter 时返回原始文本。
    """
    src = PENDING_DIR / f"task-{task_id}.md"
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = _FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def _write_failed_task_file(task, reason: str) -> str:
    """把 pending 任务文件改写为 failed 态并移动到 failed/ 目录。

    对齐 Phase 1j 惯例 (failed/task-100.md): 保留正文, frontmatter 增加
    ``reason`` + ``failed_at``。返回 failed 文件路径。
    """
    task_id = task.id
    body = _read_task_file_body(task_id)
    failed_at = now_iso()
    failed_path = FAILED_DIR / f"task-{task_id}.md"
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    failed_path.write_text(
        f"""---
task_type: "compile"
status: "failed"
created_at: "{task.created_at}"
reason: "{reason}"
failed_at: "{failed_at}"
params:
  item_ids: {((task.params or {}).get("item_ids") or [])}
---

{body}""",
        encoding="utf-8",
    )
    _unlink_pending_file(task_id)
    return str(failed_path)


def _write_done_task_file(task, result: dict) -> str:
    """把 pending 任务文件改写为 done 态并移动到 done/ 目录。

    格式对齐 done/task-10.md (Phase 1h 产物): status=done + completed_at +
    result 摘要 + 执行结果正文。返回 done 文件路径。
    """
    task_id = task.id
    item_ids = (task.params or {}).get("item_ids") or []
    id_list = "\n".join(f"- [[{iid}]]" for iid in item_ids)
    completed_at = now_iso()

    # result 只含标量 (简单 YAML 子集, parse_frontmatter 可读);
    # domains/types 只进正文摘要, 不进 frontmatter (嵌套 dict 超出子集)
    domains = result.pop("domains", None) or {}
    types = result.pop("types", None) or {}
    result_lines = "\n".join(
        f"  {k}: {v}" for k, v in result.items()
    )
    domain_summary = ", ".join(f"{k}({v})" for k, v in sorted(domains.items()))
    type_summary = ", ".join(f"{k}({v})" for k, v in sorted(types.items()))

    done_path = DONE_DIR / f"task-{task_id}.md"
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    done_path.write_text(
        f"""---
task_type: "compile"
status: "done"
created_at: "{task.created_at}"
completed_at: "{completed_at}"
params:
  item_ids: {item_ids}
result:
{result_lines}
---

# 编译任务

请对以下知识条目执行编译：

{id_list}

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{{slug}}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true

## 执行结果
- {result.get('items', 0)}/{result.get('items', 0)} items 规则式编译完成（确定性分类, 非 LLM）
- 完成分类: {result.get('classified', 0)} 条
- lifecycle 推进: {result.get('lifecycle_advanced', 0)} 条
- domains: {domain_summary or '-'}
- types: {type_summary or '-'}
- 缺失条目: {result.get('missing', 0)} | 失败: {result.get('errors', 0)}
""",
        encoding="utf-8",
    )
    _unlink_pending_file(task_id)
    return str(done_path)


def _unlink_pending_file(task_id: int) -> None:
    """删除 pending 目录下对应任务文件 (幂等)."""
    try:
        (PENDING_DIR / f"task-{task_id}.md").unlink(missing_ok=True)
    except OSError as e:
        log.warning(f"failed to remove pending file task-{task_id}.md: {e}")


def _execute_compile_task(task, item_ids: list[str]) -> dict:
    """执行单个 compile 任务 (规则式编译) 并落盘 done。

    执行内容 = 旧 Agent 编译任务的确定性部分:
      1. 分类: auto_classifier.batch_classify (domain/topic/type/difficulty)
      2. 概念关联: concept_linker.link_tags_to_concepts (纯映射, 不新建文件)
      3. 状态流转: _advance_compile_lifecycle
      4. 写回 md frontmatter (md 是真相源) + 同步 SQLite
      5. 任务文件 pending/ → done/ + knowledge_tasks 标记 done
    """
    result = {
        "items": len(item_ids),
        "classified": 0,
        "lifecycle_advanced": 0,
        "missing": 0,
        "errors": 0,
        "executor": "auto-consumer",
    }
    domains: dict[str, int] = {}
    types: dict[str, int] = {}

    # 1. 加载条目 (缺失的跳过, 计入 missing)
    loaded: list = []
    for iid in item_ids:
        item = knowledge_repo.get_item(iid)
        if item is None:
            result["missing"] += 1
        else:
            loaded.append(item)

    # 2. 批量规则分类 (纯函数, 无 LLM / 无网络)
    if loaded:
        from backend.services import ai_hub
        from backend.services.auto_classifier import batch_classify
        from backend.services.concept_linker import link_tags_to_concepts

        classified = batch_classify([it.to_dict() for it in loaded])

        for d in classified:
            item = next(it for it in loaded if it.id == d["id"])
            try:
                new_lifecycle = _advance_compile_lifecycle(item.lifecycle)
                if d.get("domain"):
                    result["classified"] += 1
                    domains[d["domain"]] = domains.get(d["domain"], 0) + 1
                if d.get("type"):
                    types[d["type"]] = types.get(d["type"], 0) + 1

                # 应用分类结果到 item
                item.domain = d.get("domain")
                if d.get("topic") and not item.topic:
                    item.topic = d["topic"]
                item.type = d.get("type")
                item.difficulty = d.get("difficulty")

                # 概念关联 (纯映射: tags → 已知 concept slugs)
                linked = link_tags_to_concepts(item.tags)
                if linked:
                    item.concepts = list(dict.fromkeys(list(item.concepts) + linked))

                if new_lifecycle:
                    item.lifecycle = new_lifecycle
                    result["lifecycle_advanced"] += 1
                item.updated_at = now_iso()

                # md 是真相源: 先回写 md, 再同步 DB (回写失败则跳过 DB,
                # 避免 DB 领先于 md 被下次 full_sync 回滚)
                ai_hub.write_item(item.to_dict(), agent="kl:compiler")
                knowledge_repo.upsert_item(item)
            except Exception as e:
                result["errors"] += 1
                log.warning(f"compile item {item.id} failed: {e}")

    # 3. done 文件 + DB 标记
    result["domains"] = domains
    result["types"] = types
    done_path = _write_done_task_file(task, dict(result))
    knowledge_repo.update_task_status(
        task.id, "done", result_path=f"knowledge/learning/tasks/done/task-{task.id}.md"
    )
    log.info(
        f"compile task {task.id} done: items={result['items']} "
        f"classified={result['classified']} lifecycle={result['lifecycle_advanced']} "
        f"path={Path(done_path).name}"
    )
    # v0.5 M2-Task5: 任务完成推 task_done SSE 事件 (SPEC §6.2 契约:
    # payload = {task_id, action, result}, action=compile)
    try:
        import asyncio
        from backend.api.events import publish_event
        asyncio.get_event_loop().create_task(
            publish_event("task_done", {
                "task_id": task.id,
                "action": "compile",
                "result": {
                    "items": result["items"],
                    "classified": result["classified"],
                    "lifecycle_advanced": result["lifecycle_advanced"],
                    "missing": result["missing"],
                    "errors": result["errors"],
                },
            })
        )
    except Exception:
        pass  # SSE 推送失败不阻塞主流程
    return result


def consume_compile_tasks(limit_items: int = CONSUME_DAILY_QUOTA) -> dict:
    """自动消费者: 批量执行 pending compile 任务 (规则式编译)。

    策略: 按 ``limit_items`` (item 数, 默认 100) 限额, 任务按 created_at
    最旧优先, 达到配额即停 (整任务粒度, 不截断), 剩余任务留待下次运行。
    与 scheduled_compile_job 的创建配额 (50/天) 配合, 队列净流出。

    Returns: {"processed_tasks": n, "items_consumed": m, "details": [...]}
    """
    tasks = [
        t for t in knowledge_repo.list_tasks(status="pending")
        if t.task_type == "compile"
    ]
    tasks.sort(key=lambda t: _task_created_dt(t) or datetime.min.replace(tzinfo=timezone.utc))

    processed = 0
    items_consumed = 0
    details: list[dict] = []
    for task in tasks:
        item_ids = (task.params or {}).get("item_ids") or []
        if not item_ids:
            # 空任务: 直接标记 done, 不占配额
            result = _execute_compile_task(task, [])
            processed += 1
            details.append({"task_id": task.id, **result})
            continue
        if items_consumed + len(item_ids) > limit_items:
            # 超出剩余配额 — 整任务跳过, 留待下次
            break
        result = _execute_compile_task(task, item_ids)
        processed += 1
        items_consumed += len(item_ids)
        details.append({"task_id": task.id, **result})

    if processed:
        _trigger_map_update()
    log.info(
        f"consume_compile_tasks: processed={processed} items={items_consumed} "
        f"limit={limit_items}"
    )
    return {
        "processed_tasks": processed,
        "items_consumed": items_consumed,
        "details": details,
    }


def archive_stale_compile_tasks(
    max_age_days: int = ARCHIVE_MAX_AGE_DAYS,
    keep_recent: int = 0,
    reason: str = ARCHIVE_REASON,
) -> dict:
    """归档存量积压的 pending compile 任务 (标记 failed + 文件移入 failed/)。

    混合策略的第一步: 先清空存量积压, 让新的 (有背压的) 任务从干净状态
    开始, 由自动消费者 (consume_compile_tasks) 以配额消费。

    - 只处理 task_type=compile 的 pending 任务。
    - 创建早于 ``max_age_days`` 天前的最旧任务先归档; ``keep_recent`` > 0
      时, 最新的 ``keep_recent`` 条无论如何保留 (交给消费者)。默认 7 天:
      超过一周未被执行的任务视为积压。
    - ``max_age_days=None`` 表示不限年龄; 建议一次性清理时用
      ``archive_stale_compile_tasks(max_age_days=None, keep_recent=5)``。
    - 幂等: 已归档任务 status=failed, 不会再次匹配。

    Returns: {"archived": n, "kept": m, "total": t, "reason": str}
    """
    tasks = [
        t for t in knowledge_repo.list_tasks(status="pending")
        if t.task_type == "compile"
    ]
    total = len(tasks)
    if not tasks:
        return {"archived": 0, "kept": 0, "total": 0, "reason": reason}

    # created_at 升序 (最旧在前)
    tasks.sort(key=lambda t: _task_created_dt(t) or datetime.min.replace(tzinfo=timezone.utc))

    if keep_recent > 0 and len(tasks) > keep_recent:
        doomed = [t for t in tasks[:-keep_recent] if _older_than_days(t, max_age_days)]
    else:
        doomed = [t for t in tasks if _older_than_days(t, max_age_days)]

    archived = 0
    for task in doomed:
        try:
            knowledge_repo.update_task_status(task.id, "failed", error_message=reason)
            _write_failed_task_file(task, reason)
            archived += 1
        except Exception as e:
            log.error(f"archive compile task {task.id} failed: {e}")

    kept = total - archived
    log.info(
        f"archive_stale_compile_tasks: archived={archived} kept={kept} "
        f"total={total} max_age_days={max_age_days}"
    )
    return {"archived": archived, "kept": kept, "total": total, "reason": reason}
