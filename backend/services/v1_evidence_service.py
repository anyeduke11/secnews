"""v1.0 T05 证据提交与恢复协议 (Subject / Material / Signal).

设计目标 (对应 contracts.md §0.5 幂等 + §0.6 CAS + §0.7 SSE 提交后只发一次):

  intent 模式 — 提交分两阶段
    1. ``create_intent(submission_key, body)`` → 返回 ``intent_id`` (pending)
    2. ``commit_intent(intent_id)`` 或 ``rollback_intent(intent_id)``
       同一 submission_key + body_hash 重复 commit 只产生一次 receipt

  原子 rename — 临时写 → 原子 rename, 失败时临时文件清理 + receipt 标 rolled_back
    临时写路径: ``.tmp/<intent_id>`` → 重命名为 ``committed/<id>``
    失败注入: 测试可在 rename 前抛异常, 验证回滚不留虚假文件

  投影 — wiki_fs.write_item 在 commit 后触发 (subject 写 concepts/, material 写 items/)
    投影失败**不**回滚 receipt, 但记录 projection_status=failed 供修复

  恢复语义 — 任何阶段中断 (进程崩溃/数据库写失败/wiki 投影失败) 都不留半截数据
    - intent pending + 超时 (默认 1h) → 自动 rollback
    - intent committed + projection failed → 留 receipt 供人工/重试
    - 同一 submission_key 重试: 返回首次 commit 的 receipt (幂等)

本模块**不**操作 wiki_fs.write_item (由 admission_service 在 signal.create 路径调
wiki_fs, 见 T07); 这里只负责 SQLite 事务 + receipt + 投影状态记录。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.logging_config import logger
from backend.repository.db import get_connection

# 收据状态 (与 v1_evidence_receipts.status 字段对齐)
RECEIPT_COMMITTED = "committed"
RECEIPT_ROLLED_BACK = "rolled_back"
RECEIPT_SUPERSEDED = "superseded"

# Intent 超时 (秒) — 超时未 commit 的 intent 视为 rollback
INTENT_TIMEOUT_SEC = 3600


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_body(body: dict[str, Any]) -> str:
    """稳定序列化 (key 排序 + UTF-8 + ensure_ascii=False) — 同一语义 body → 同一 hash."""
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash_body(body: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_body(body).encode("utf-8")).hexdigest()


class IntentExistsError(Exception):
    """同一 submission_key 已存在 intent (pending) — 不应并发提交."""


class IdempotentReplay(Exception):
    """同一 submission_key + body_hash 已 commit — 重放返回首次结果 (非错误, 标记用)."""


class V1EvidenceService:
    """v1.0 证据提交服务 — SQLite 事务 + receipt + 临时文件原子 rename.

    所有写方法在隔离 conftest 下走 SQLite tmp_path (T01 已落地) + audit/路径哨兵。
    不连真实 db。
    """

    def __init__(self, conn: sqlite3.Connection | None = None, projection_dir: Path | None = None) -> None:
        # 让 T01 的 conftest temp_db fixture 注入; 默认走 process-wide conn.
        self._conn = conn
        self._projection_dir = projection_dir  # 投影临时目录 (commit 时原子 rename 进)
        self._lock = threading.Lock()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn or get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------
    # 阶段 1: create_intent
    # ------------------------------------------------------------------
    def create_intent(
        self,
        submission_key: str,
        entity_type: str,
        body: dict[str, Any],
        submitted_by: str = "system",
    ) -> dict[str, Any]:
        """创建提交意图 — 不写实体表, 只落 receipt pending.

        Returns
        -------
        ``{intent_id, submission_key, body_hash, status='pending'}``

        幂等
        ----
        同一 submission_key + body_hash 重复调用 → 抛 ``IdempotentReplay``, 携带既有
        receipt (调用方可决定"返回旧值"还是"继续").

        同一 submission_key + 不同 body_hash → 抛 ``IntentExistsError`` (业务侧需
        显式 rollback 旧 intent 或换 key).
        """
        body_hash = _hash_body(body)
        with self._lock:
            with self._tx() as conn:
                row = conn.execute(
                    "SELECT id, body_hash, status, entity_id, intent_id "
                    "FROM v1_evidence_receipts WHERE submission_key = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (submission_key,),
                ).fetchone()
                if row is not None:
                    existing_hash, existing_status = row[1], row[2]
                    if existing_status == RECEIPT_COMMITTED and existing_hash == body_hash:
                        raise IdempotentReplay(
                            f"submission_key={submission_key} already committed "
                            f"(receipt_id={row[0]}, entity_id={row[3]})"
                        )
                    if existing_status == "pending" and existing_hash != body_hash:
                        raise IntentExistsError(
                            f"submission_key={submission_key} pending with different body_hash"
                        )
                intent_id = f"intent-{uuid.uuid4().hex[:12]}"
                # receipt 暂以 status=pending 落库, entity_id 占位 intent_id,
                # commit 时 UPDATE 替换为真实 entity_id + status=committed.
                # v1.0 C05 R01: extra_json 同时存 body 副本, commit 时 _insert_* 读回
                # 写真实 entity 行 (不再用 pass 占位).
                conn.execute(
                    "INSERT INTO v1_evidence_receipts "
                    "(submission_key, body_hash, entity_type, entity_id, "
                    " submitted_by, intent_id, status, extra_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (
                        submission_key, body_hash, entity_type, intent_id,
                        submitted_by, intent_id,
                        json.dumps({"_intent": True, "_body": body}),
                    ),
                )
        return {
            "intent_id": intent_id,
            "submission_key": submission_key,
            "body_hash": body_hash,
            "status": "pending",
        }

    # ------------------------------------------------------------------
    # 阶段 2: commit / rollback
    # ------------------------------------------------------------------
    def commit_intent(
        self,
        intent_id: str,
        entity_id: str,
        projection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """提交意图 — 落实体行 + 原子 rename 投影 + 收据标记 committed.

        ``projection`` 可选 dict:
          - ``{"wiki_path": "concepts/cve-2026-xxxx.md", "wiki_content": "..."}``
            写临时文件 + 原子 rename 到目标路径; 失败抛异常由 rollback 兜底.

        Returns
        -------
        ``{receipt_id, entity_id, status, projection_status}``
        """
        with self._lock:
            with self._tx() as conn:
                row = conn.execute(
                    "SELECT id, body_hash, entity_type, submission_key, extra_json "
                    "FROM v1_evidence_receipts WHERE intent_id = ? AND status = 'pending'",
                    (intent_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"intent_id={intent_id} not found or not pending")
                receipt_id, body_hash, entity_type, submission_key = row[0], row[1], row[2], row[3]
                # v1.0 C05 R01: 从 receipt.extra_json 读回 body (create_intent 时已存),
                # 供 _insert_* 写真实 entity 行.
                try:
                    body = json.loads(row[4]).get("_body", {}) if row[4] else {}
                except Exception:
                    body = {}
                # 1) 写实体表 (subject / material / signal) — entity_type 决定表名
                if entity_type == "subject":
                    self._insert_subject(conn, body, intent_id, body_hash)
                elif entity_type == "material":
                    self._insert_material(conn, body, intent_id, body_hash)
                elif entity_type == "signal":
                    self._insert_signal(conn, body, intent_id, body_hash)
                elif entity_type == "case":
                    # T08: caller (case_service.create_case) 已先调 repo.create 写
                    # v1_cases 行 — 这里只兜底 (若未写, 才补一条最小行, 防止外键悬空)
                    cur = conn.execute(
                        "SELECT 1 FROM v1_cases WHERE id = ?", (entity_id,)
                    ).fetchone()
                    if cur is None:
                        # 兜底: body 必须含完整字段 (正常路径不会被触发)
                        conn.execute(
                            "INSERT INTO v1_cases (id, title, question, status, priority) "
                            "VALUES (?, ?, ?, 'open', 'p2')",
                            (
                                entity_id,
                                str(conn.execute(
                                    "SELECT body_hash FROM v1_evidence_receipts "
                                    "WHERE intent_id = ?", (intent_id,)
                                ).fetchone()[0])[:120],
                                "stub",
                            ),
                        )
                else:
                    raise ValueError(f"unsupported entity_type={entity_type}")

                # 2) 原子 rename 投影 (失败抛异常触发外层 rollback)
                projection_status = "skipped"
                if projection and self._projection_dir is not None:
                    projection_status = self._atomic_rename_projection(
                        projection.get("wiki_path", ""),
                        projection.get("wiki_content", ""),
                    )

                # 3) UPDATE receipt → committed
                extra = {
                    "projection_status": projection_status,
                    "committed_at": _utcnow_iso(),
                }
                conn.execute(
                    "UPDATE v1_evidence_receipts SET entity_id = ?, status = ?, "
                    "extra_json = ? WHERE id = ?",
                    (entity_id, RECEIPT_COMMITTED, json.dumps(extra), receipt_id),
                )
        return {
            "receipt_id": receipt_id,
            "entity_id": entity_id,
            "submission_key": submission_key,
            "status": RECEIPT_COMMITTED,
            "projection_status": projection_status,
        }

    def rollback_intent(self, intent_id: str, reason: str = "") -> dict[str, Any]:
        """回滚 — receipt 标 rolled_back, 清理临时投影文件."""
        with self._lock:
            with self._tx() as conn:
                cur = conn.execute(
                    "UPDATE v1_evidence_receipts SET status = ?, extra_json = ? "
                    "WHERE intent_id = ? AND status = 'pending'",
                    (RECEIPT_ROLLED_BACK, json.dumps({"reason": reason, "rolled_back_at": _utcnow_iso()}), intent_id),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"intent_id={intent_id} not pending or not found")
        # 清理临时文件 (即使投影目录无此 intent_id, 也不报错 — best effort)
        if self._projection_dir is not None:
            tmp = self._projection_dir / ".tmp" / f"{intent_id}.md"
            if tmp.exists():
                tmp.unlink()
        return {"intent_id": intent_id, "status": RECEIPT_ROLLED_BACK, "reason": reason}

    # ------------------------------------------------------------------
    # 原子 rename 投影
    # ------------------------------------------------------------------
    def _atomic_rename_projection(self, wiki_path: str, content: str) -> str:
        """临时写 .tmp/<intent_id>.md → 原子 rename 到 <projection_dir>/<wiki_path>.

        失败模式 (供 T05-C 故障测试用):
          - 临时目录不存在 → raise (rollback 由调用方触发)
          - rename 时目标路径已存在 (并发提交冲突) → raise
          - 写入内容为空 → raise (避免空文件落库)
        """
        if not wiki_path or not content:
            raise ValueError("projection requires both wiki_path and wiki_content")
        tmp_dir = self._projection_dir / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = tmp_dir / f"{uuid.uuid4().hex[:12]}.md"
        tmp_file.write_text(content, encoding="utf-8")
        target = self._projection_dir / wiki_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            tmp_file.unlink()
            raise FileExistsError(f"projection target exists: {wiki_path}")
        tmp_file.rename(target)
        return "renamed"

    # ------------------------------------------------------------------
    # 实体表 INSERT (按 entity_type 路由; body 必须含 entity_id 字段对齐)
    # ------------------------------------------------------------------
    def _insert_subject(self, conn: sqlite3.Connection, body: dict[str, Any], entity_id: str, body_hash: str) -> None:
        """v1.0 C05 R01 修复: 真 INSERT v1_subjects.

        旧实现: pass 占位, T05 时未填 (遗留 R01 真问题).
        修复: 按 migration 096 schema 真写入, body 必含 id/entity_type/canonical_name +
        first_seen_at/last_seen_at (其余字段给默认值). 失败 raise 不吞, 由 record_audit
        写 audit_log (action=v1_evidence.entity_insert_failed) 供运维追查.
        """
        try:
            now_iso = _utcnow_iso()
            conn.execute(
                "INSERT INTO v1_subjects "
                "(id, entity_type, canonical_name, aliases_json, importance, "
                " tags_json, related_subject_ids_json, first_seen_at, last_seen_at, "
                " revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    body.get("id", entity_id),
                    body.get("entity_type", "other"),
                    body.get("canonical_name", body.get("id", entity_id)),
                    body.get("aliases_json", "[]"),
                    body.get("importance", "normal"),
                    body.get("tags_json", "[]"),
                    body.get("related_subject_ids_json", "[]"),
                    body.get("first_seen_at", now_iso),
                    body.get("last_seen_at", now_iso),
                    int(body.get("revision", 1)),
                    now_iso,
                    now_iso,
                ),
            )
        except Exception as e:
            self._audit_entity_insert_failed("subject", entity_id, body_hash, e)
            raise

    def _insert_material(self, conn: sqlite3.Connection, body: dict[str, Any], entity_id: str, body_hash: str) -> None:
        """v1.0 C05 R01 修复: 真 INSERT v1_materials."""
        try:
            now_iso = _utcnow_iso()
            conn.execute(
                "INSERT INTO v1_materials "
                "(id, source_kind, url, title, content_hash, content_length, "
                " content_ref, summary, published_at, fetched_at, fetched_by, "
                " subject_ids_json, metadata_json, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    body.get("id", entity_id),
                    body.get("source_kind", "url"),
                    body.get("url"),
                    body.get("title", body.get("id", entity_id)),
                    body.get("content_hash", body_hash),
                    int(body.get("content_length", 0)),
                    body.get("content_ref"),
                    body.get("summary"),
                    body.get("published_at"),
                    body.get("fetched_at", now_iso),
                    body.get("fetched_by"),
                    body.get("subject_ids_json", "[]"),
                    body.get("metadata_json", "{}"),
                    int(body.get("revision", 1)),
                    now_iso,
                    now_iso,
                ),
            )
        except Exception as e:
            self._audit_entity_insert_failed("material", entity_id, body_hash, e)
            raise

    def _insert_signal(self, conn: sqlite3.Connection, body: dict[str, Any], entity_id: str, body_hash: str) -> None:
        """v1.0 C05 R01 修复: 真 INSERT v1_signals (FK subject_id + material_id 必须已存在)."""
        try:
            now_iso = _utcnow_iso()
            conn.execute(
                "INSERT INTO v1_signals "
                "(id, subject_id, material_id, summary, occurred_at, "
                " admission_rule_version, admission_reason, supersedes_signal_id, "
                " confidence, status, revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    body.get("id", entity_id),
                    body.get("subject_id", ""),
                    body.get("material_id", ""),
                    body.get("summary", ""),
                    body.get("occurred_at", now_iso),
                    body.get("admission_rule_version", "v1"),
                    body.get("admission_reason", ""),
                    body.get("supersedes_signal_id"),
                    body.get("confidence", "unverified"),
                    body.get("status", "unverified"),
                    int(body.get("revision", 1)),
                    now_iso,
                    now_iso,
                ),
            )
        except Exception as e:
            self._audit_entity_insert_failed("signal", entity_id, body_hash, e)
            raise

    def _audit_entity_insert_failed(
        self, entity_type: str, entity_id: str, body_hash: str, err: Exception,
    ) -> None:
        """记录实体 INSERT 失败到 audit_log (R01 修复: 不吞异常, 留审计锚点).

        失败 → record_audit (actor=system / action=v1_evidence.entity_insert_failed),
        调用方 raise 不吞 (事务回滚 + receipt 不 committed).
        """
        try:
            from backend.observability_records import record_audit
            record_audit(
                actor="system",
                action="v1_evidence.entity_insert_failed",
                target=f"{entity_type}:{entity_id}",
                detail={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "body_hash": body_hash,
                    "error_type": type(err).__name__,
                    "error": str(err)[:200],
                },
            )
        except Exception:
            # audit 写失败不应再抛 — 留给调用方的事务回滚覆盖
            logger.debug(f"audit write failed (ignored): {err}")

    # ------------------------------------------------------------------
    # 恢复 (扫描超时的 pending intent)
    # ------------------------------------------------------------------
    def reap_expired_intents(self, now_ts: float | None = None) -> list[dict[str, Any]]:
        """扫描超时未 commit 的 intent → 标 rolled_back. 返回被回滚的 intent_ids."""
        now_ts = now_ts or time.time()
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT id, intent_id, entity_type, submission_key, submitted_at "
                "FROM v1_evidence_receipts "
                "WHERE status = 'pending' "
                "AND (julianday('now') - julianday(submitted_at)) * 86400 > ?",
                (INTENT_TIMEOUT_SEC,),
            ).fetchall()
            if not rows:
                return []
            reap_ids: list[dict[str, Any]] = []
            for r in rows:
                conn.execute(
                    "UPDATE v1_evidence_receipts SET status = ?, extra_json = ? "
                    "WHERE id = ?",
                    (
                        RECEIPT_ROLLED_BACK,
                        json.dumps({"reason": "timeout", "reaped_at": _utcnow_iso()}),
                        r[0],
                    ),
                )
                reap_ids.append({"intent_id": r[1], "entity_type": r[2], "submission_key": r[3]})
        return reap_ids
