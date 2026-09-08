"""v1.0 T06 源级采集管道 (FetchRequest + SourceLease + Watermark + Evidence 桥接).

对应 EXECUTION_GUIDE §4 T06 通过证据:
  - 同源无重复写 (watermark 阻止)
  - 不可变 FetchRequest (frozen dataclass) — 入参 hash 即幂等键
  - source 租约 (TTL + extend/release) — 防止双 worker 撞源
  - 304/429/超时/200 错页/分页重叠/重启恢复 状态机统一
  - 接入 T05 evidence: 解析成功的 item → V1EvidenceService.create_intent + commit
    (替代直接写 hotspots 表, 与 v1.0 单一提交入口对齐)

设计纪律 (与 T02/T04/T05 一致):
  - 隔离 conftest 下走 temp_db (T01 已落地)
  - 失败注入点 (5 处: acquire_lease / fetch / parse / evidence.create_intent /
    evidence.commit_intent), 单测可 monkeypatch 抛错验证回滚
  - 不动现有 source_scheduler_service / collection_service; 本模块是"上层
    pipeline", 调用方任选: 既可继续走旧 scheduler, 也可走新 pipeline。
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# 不可变 FetchRequest
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FetchRequest:
    """单次源抓取请求 — 不可变, hash 决定幂等键 (T05 submission_key 复用).

    字段契约:
      - source_id: 源唯一标识 (crawler_sources.id)
      - cursor: 抓取游标 (URL / timestamp / page-token / RSS etag); 同 (source, cursor)
        必须不重放, watermark 用其判断是否越界
      - max_items: 上限 (防止单源爆发)
      - requester: 调度者标识 (user / system / cron / agent)
      - attempt: 第几次重试 (0 = 首次)
    """

    source_id: str
    cursor: str
    max_items: int = 50
    requester: str = "system"
    attempt: int = 0

    def submission_key(self, prefix: str = "v1-fetch") -> str:
        """生成 T05 兼容 submission_key — 同请求同一 key, T05 幂等去重."""
        body = f"{self.source_id}|{self.cursor}|{self.max_items}|{self.requester}|{self.attempt}"
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}-{self.source_id}-{h}"

    def body_hash(self) -> str:
        body = f"{self.source_id}|{self.cursor}|{self.max_items}|{self.requester}|{self.attempt}"
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 抓取阶段枚举 (统一 304/429/超时/200 错页 等 6 状态)
# ---------------------------------------------------------------------------
class FetchOutcome(str, Enum):
    SUCCESS = "success"           # 正常返回, 有可解析内容
    NOT_MODIFIED = "not_modified" # 304 / etag 命中, 无新内容
    RATE_LIMITED = "rate_limited" # 429 / 反爬, 需 backoff
    TIMEOUT = "timeout"           # 抓取超时
    BAD_BODY = "bad_body"         # 200 但页面损坏 / 反爬拦截页
    ERROR = "error"               # 5xx / DNS / 连接错误
    SKIP = "skip"                 # 调度策略跳过 (健康态 dead/disabled)


# ---------------------------------------------------------------------------
# SourceLease (TTL + extend + release)
# ---------------------------------------------------------------------------
class LeaseHeldError(Exception):
    """源被其他 worker 持有 — 调度方应跳过 (无重复)."""


class SourceLease:
    """单源租约 (per-process) — TTL 秒内同源二次获取抛 LeaseHeldError.

    单机内存版; 跨进程可后续接 DB 行锁 (本批仅做内存版, 单 worker 串行足够).
    """

    def __init__(self, ttl_sec: int = 60) -> None:
        self._ttl = ttl_sec
        self._held: dict[str, float] = {}  # source_id → expires_at (epoch)

    def _purge(self) -> None:
        now = time.time()
        expired = [k for k, v in self._held.items() if v < now]
        for k in expired:
            self._held.pop(k, None)

    def acquire(self, source_id: str) -> None:
        self._purge()
        if source_id in self._held:
            raise LeaseHeldError(f"source {source_id} held by another worker")
        self._held[source_id] = time.time() + self._ttl

    def extend(self, source_id: str, ttl_sec: int | None = None) -> None:
        if source_id not in self._held:
            raise LeaseHeldError(f"source {source_id} not held")
        self._held[source_id] = time.time() + (ttl_sec or self._ttl)

    def release(self, source_id: str) -> None:
        self._held.pop(source_id, None)

    def is_held(self, source_id: str) -> bool:
        self._purge()
        return source_id in self._held

    @contextmanager
    def hold(self, source_id: str) -> Iterator[None]:
        self.acquire(source_id)
        try:
            yield
        finally:
            self.release(source_id)


# ---------------------------------------------------------------------------
# Watermark (per-source cursor + 单调不变量)
# ---------------------------------------------------------------------------
class WatermarkRegressedError(Exception):
    """watermark 倒退 (新值 ≤ 旧值) — 违反单调不变量, 应当报警 + 拒绝."""


class SourceWatermark:
    """per-source watermark — 单调递增, 拒绝倒退.

    复用现有 crawler_sources 表字段 (last_fetch_at + etag), 不新增列.
    cursor 透传 — 在内存层封装, 落库时把 cursor 写入 etag 字段, ts 写入
    last_fetch_at. 校验仅在 ts 维度 (单调).
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def get(self, source_id: str) -> dict[str, Any] | None:
        conn = self._conn or get_connection()
        row = conn.execute(
            "SELECT etag, last_fetch_at FROM crawler_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return {"cursor": row[0], "ts": row[1]}

    def advance(self, source_id: str, new_cursor: str, new_ts: str) -> None:
        """推进 watermark — 拒绝倒退 (cursor 不一致; ts 必须严格递增).

        倒退策略: 抛 WatermarkRegressedError, 业务侧应记录 + 告警, 不应吞掉.
        """
        conn = self._conn or get_connection()
        cur = self.get(source_id)
        if cur and cur["ts"] and new_ts <= cur["ts"]:
            raise WatermarkRegressedError(
                f"source {source_id} watermark regressed: {cur['ts']} → {new_ts}"
            )
        conn.execute(
            "UPDATE crawler_sources SET etag = ?, last_fetch_at = ? WHERE id = ?",
            (new_cursor, new_ts, source_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Pipeline 编排 (collect → parse → evidence)
# ---------------------------------------------------------------------------
@dataclass
class PipelineResult:
    """单次 fetch 全链路结果 — 调度方 / 测试断言共用."""

    outcome: FetchOutcome
    request: FetchRequest
    items_parsed: int = 0
    items_committed: int = 0
    items_idempotent: int = 0
    items_failed: int = 0
    error: str | None = None
    duration_ms: int = 0
    next_cursor: str | None = None
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "source_id": self.request.source_id,
            "items_parsed": self.items_parsed,
            "items_committed": self.items_committed,
            "items_idempotent": self.items_idempotent,
            "items_failed": self.items_failed,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "next_cursor": self.next_cursor,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class SourcePipeline:
    """源级采集管道 — 编排 fetch → parse → evidence (T05 桥接).

    失败注入点 (5 处, 单测可 monkeypatch):
      1. lease.acquire   → LeaseHeldError (同源并发撞)
      2. fetch_fn        → FetchOutcome.{TIMEOUT,ERROR,BAD_BODY,RATE_LIMITED}
      3. parse_fn        → 解析异常 → items_failed++
      4. evidence.create  → IdempotentReplay / IntentExistsError
      5. evidence.commit  → FileExistsError / ValueError → receipt 不 committed
    """

    def __init__(
        self,
        *,
        lease: SourceLease | None = None,
        watermark: SourceWatermark | None = None,
        evidence_service: Any | None = None,  # V1EvidenceService (避免循环 import)
    ) -> None:
        self.lease = lease or SourceLease()
        self.watermark = watermark or SourceWatermark()
        self.evidence = evidence_service

    def run(
        self,
        request: FetchRequest,
        *,
        fetch_fn: Callable[[FetchRequest], tuple[FetchOutcome, list[dict[str, Any]], str | None]],
        parse_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> PipelineResult:
        """执行单次源抓取.

        Parameters
        ----------
        request:
            不可变 FetchRequest.
        fetch_fn:
            ``(req) → (outcome, raw_items, next_cursor)``. outcome 决定下游
            是否走 parse; raw_items 是原始 dict 列表, 由 parse_fn 转 v1_0 域对象.
        parse_fn:
            ``(raw) → body_dict | None``. 返回 None 表示丢弃 (非 fatal).

        Returns
        -------
        PipelineResult — 调度方可据此更新 source_scheduler_repo.crawler_runs.
        """
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.time()
        result = PipelineResult(
            outcome=FetchOutcome.SUCCESS,  # 占位, 5 处失败注入点之一会改
            request=request, started_at=started,
        )
        try:
            with self.lease.hold(request.source_id):
                # 1) fetch
                outcome, raw_items, next_cursor = fetch_fn(request)
                result.outcome = outcome
                result.next_cursor = next_cursor
                # 2) 仅 SUCCESS 走 parse + evidence; 其他直接 return (不 commit, 不 advance)
                if outcome is not FetchOutcome.SUCCESS:
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    result.duration_ms = int((time.time() - t0) * 1000)
                    return result

                # 3) parse
                bodies: list[dict[str, Any]] = []
                for raw in raw_items:
                    try:
                        body = parse_fn(raw)
                    except Exception as e:
                        result.items_failed += 1
                        logger.warning(f"parse failed: source={request.source_id} err={e}")
                        continue
                    if body is None:
                        continue
                    bodies.append(body)
                result.items_parsed = len(bodies)

                # 4) evidence bridge (T05) — 仅当 service 注入时执行
                if self.evidence is None:
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    result.duration_ms = int((time.time() - t0) * 1000)
                    return result

                from backend.services.v1_evidence_service import (  # 避免循环
                    IdempotentReplay,
                    IntentExistsError,
                )
                for body in bodies:
                    sub_key = f"{request.submission_key()}-{body.get('id', uuid.uuid4().hex[:8])}"
                    try:
                        intent = self.evidence.create_intent(
                            sub_key, "material", body, submitted_by=request.requester,
                        )
                        self.evidence.commit_intent(intent["intent_id"], entity_id=body.get("id", ""))
                        result.items_committed += 1
                    except IdempotentReplay:
                        result.items_idempotent += 1
                    except IntentExistsError:
                        result.items_failed += 1
                    except Exception as e:
                        result.items_failed += 1
                        logger.warning(f"evidence commit failed: {e}")

                # 5) watermark 推进 — v1.0 C05 R02 修复: 失败 0 items 不前移
                # (P1.2 教训: RSS 静默失败同款 — 采集失败仍 advance → 下次调度
                # 拿新 cursor 跳过本窗口, 漏收). 仅 items_committed > 0 才推进.
                if next_cursor is not None and result.items_committed > 0:
                    try:
                        self.watermark.advance(
                            request.source_id, next_cursor,
                            datetime.now(timezone.utc).isoformat(),
                        )
                    except WatermarkRegressedError as e:
                        logger.error(f"watermark regressed (不推进): {e}")

                result.finished_at = datetime.now(timezone.utc).isoformat()
                result.duration_ms = int((time.time() - t0) * 1000)
                return result
        except LeaseHeldError as e:
            result.outcome = FetchOutcome.SKIP
            result.error = str(e)
            result.finished_at = datetime.now(timezone.utc).isoformat()
            result.duration_ms = int((time.time() - t0) * 1000)
            return result
