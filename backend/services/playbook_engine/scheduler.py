"""playbook_engine.scheduler — Playbook cron 调度 (Phase C C2).

设计:
- **独立 APScheduler 实例** (BackgroundScheduler): 不接入主 AsyncIOScheduler,
  避免循环依赖 + 主调度器单线程异步执行被 playbook 长任务阻塞 (R6 1h 上限风险).
- **SQLite 持久化**: ``playbook_schedules`` 表 (migration 094) 存 (name, cron_spec,
  timezone, inputs_json, enabled); 启动时按 enabled 加载到 APScheduler; 每次
  upsert 即时生效 (add_job / remove_job).
- **CronTrigger 直读 cron_spec**: 5 字段 unix cron (minute hour day month weekday);
  用户决策默认时区 Asia/Shanghai (与现有 source_revival_check 等 job 一致).
- **execute 入口**: ``PlaybookEngine.execute()`` 同步跑完, 结果落 ``playbook_runs``
  表 (migration 094) — audit + dashboard 共用数据源 (R3).
- **失败处理**: 单次 cron tick 抛错 → 落 playbook_runs status=failed, **不影响** 调度
  下一次触发 (与 Phase 24+ P0.5 max_instances=1 / coalesce=True 一致).
- **生命周期**: start() / shutdown() 显式管理; FastAPI lifespan 集成 (startup=start,
  shutdown=shutdown).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.playbook_engine import PlaybookEngine

_log = logger.bind(component="playbook_scheduler")

DEFAULT_TZ = "Asia/Shanghai"


# ---------------------------------------------------------------------------
# Repo — playbook_schedules CRUD (thin layer, table 单表平铺)
# ---------------------------------------------------------------------------
class PlaybookScheduleRepo:
    """playbook_schedules 表 DAO — 字段与 migration 094 一一对齐.

    所有写路径幂等 (INSERT OR REPLACE on UNIQUE(playbook_name)); 读路径
    保持行结构扁平, JSON 字段按需反序列化.
    """

    def upsert(
        self,
        *,
        playbook_name: str,
        cron_spec: str,
        timezone: str = DEFAULT_TZ,
        inputs: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO playbook_schedules(
                playbook_name, cron_spec, timezone, inputs_json, enabled, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                COALESCE(
                    (SELECT updated_at FROM playbook_schedules WHERE playbook_name = ?),
                    datetime('now', 'localtime')
                )
            )
            """,
            (
                playbook_name,
                cron_spec,
                timezone,
                json.dumps(inputs or {}, ensure_ascii=False),
                1 if enabled else 0,
                playbook_name,
            ),
        )
        row = conn.execute(
            "SELECT * FROM playbook_schedules WHERE playbook_name = ?",
            (playbook_name,),
        ).fetchone()
        return _row_to_dict(row)

    def get(self, playbook_name: str) -> dict[str, Any] | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM playbook_schedules WHERE playbook_name = ?",
            (playbook_name,),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def list_enabled(self) -> list[dict[str, Any]]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM playbook_schedules WHERE enabled = 1 ORDER BY playbook_name"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM playbook_schedules ORDER BY playbook_name"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def delete(self, playbook_name: str) -> bool:
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM playbook_schedules WHERE playbook_name = ?",
            (playbook_name,),
        )
        return cur.rowcount > 0

    def set_enabled(self, playbook_name: str, enabled: bool) -> bool:
        conn = get_connection()
        cur = conn.execute(
            """
            UPDATE playbook_schedules
            SET enabled = ?, updated_at = datetime('now', 'localtime')
            WHERE playbook_name = ?
            """,
            (1 if enabled else 0, playbook_name),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Repo — playbook_runs (audit / dashboard 共用数据源)
# ---------------------------------------------------------------------------
class PlaybookRunRepo:
    """playbook_runs 表 DAO — execute 后落库."""

    def insert(
        self,
        *,
        run_id: str,
        playbook_name: str,
        status: str,
        inputs: dict[str, Any],
        steps: list[dict[str, Any]],
        started_at: str,
        finished_at: str | None,
        duration_ms: int | None,
        error: str | None,
    ) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO playbook_runs(
                run_id, playbook_name, status, inputs_json, steps_json,
                started_at, finished_at, duration_ms, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                playbook_name,
                status,
                json.dumps(inputs, ensure_ascii=False),
                json.dumps(steps, ensure_ascii=False),
                started_at,
                finished_at,
                duration_ms,
                error,
            ),
        )

    def list_for_playbook(
        self, playbook_name: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM playbook_runs WHERE playbook_name = ?
            ORDER BY started_at DESC, run_id DESC LIMIT ?
            """,
            (playbook_name, limit),
        ).fetchall()
        return [_run_row_to_dict(r) for r in rows]

    def get(self, run_id: str) -> dict[str, Any] | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM playbook_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _run_row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# row → dict helpers
# ---------------------------------------------------------------------------
def _row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    raw_inputs = out.get("inputs_json")
    if isinstance(raw_inputs, str) and raw_inputs:
        try:
            out["inputs_json"] = json.loads(raw_inputs)
        except (TypeError, ValueError):
            pass
    return out


def _run_row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    for col in ("inputs_json", "steps_json"):
        raw = out.get(col)
        if isinstance(raw, str) and raw:
            try:
                out[col] = json.loads(raw)
            except (TypeError, ValueError):
                pass
    return out


# ---------------------------------------------------------------------------
# PlaybookScheduler — APScheduler + repo 集成
# ---------------------------------------------------------------------------
class PlaybookScheduler:
    """独立 BackgroundScheduler; 启动时按 enabled schedule 加 APScheduler cron job.

    fields:
        scheduler: APScheduler BackgroundScheduler (线程池, 不阻塞 asyncio)
        repo: PlaybookScheduleRepo (CRUD + 持久化)
        run_repo: PlaybookRunRepo (execute 后落 audit)
        engine: PlaybookEngine (execute 入口; 可注入 fake)
    """

    def __init__(
        self,
        *,
        engine: PlaybookEngine | None = None,
        repo: PlaybookScheduleRepo | None = None,
        run_repo: PlaybookRunRepo | None = None,
    ) -> None:
        self.scheduler: BackgroundScheduler | None = None
        self.repo = repo or PlaybookScheduleRepo()
        self.run_repo = run_repo or PlaybookRunRepo()
        self._engine = engine  # 推迟构造, 避免 skill_registry 顶层依赖

    def _get_engine(self) -> PlaybookEngine:
        if self._engine is None:
            self._engine = PlaybookEngine()
        return self._engine

    def start(self) -> None:
        """启动 APScheduler + 加载所有 enabled schedules."""
        if self.scheduler is not None:
            return  # 幂等
        self.scheduler = BackgroundScheduler(timezone="UTC")
        for entry in self.repo.list_enabled():
            try:
                self._register(entry)
            except Exception as e:  # noqa: BLE001 — 启动期 fail loud 但不阻断其他 schedule
                _log.warning(
                    f"playbook_scheduler start: skip {entry['playbook_name']!r}: {e}"
                )
        self.scheduler.start()
        _log.info(f"playbook_scheduler started, loaded schedules")

    def shutdown(self, *, wait: bool = False) -> None:
        """停止调度器 — wait=False 默认异步, 测试或显式等待可改 True."""
        if self.scheduler is None:
            return
        try:
            self.scheduler.shutdown(wait=wait)
        finally:
            self.scheduler = None

    def upsert_schedule(
        self,
        *,
        playbook_name: str,
        cron_spec: str,
        timezone: str = DEFAULT_TZ,
        inputs: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """upsert 一条 schedule; 启动后即时生效 (移除旧 APScheduler job + 重新加)."""
        # 1. validate cron spec 提前抛 (避免启用了无效 schedule)
        CronTrigger.from_crontab(cron_spec, timezone=timezone)
        entry = self.repo.upsert(
            playbook_name=playbook_name,
            cron_spec=cron_spec,
            timezone=timezone,
            inputs=inputs,
            enabled=enabled,
        )
        # 2. 即时同步 APScheduler
        if self.scheduler is not None:
            job_id = _job_id(playbook_name)
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            if enabled:
                self._register(entry)
        return entry

    def remove_schedule(self, playbook_name: str) -> bool:
        """删除 schedule (同时从 APScheduler 移除)."""
        if self.scheduler is not None:
            self.scheduler.remove_job(_job_id(playbook_name))
        return self.repo.delete(playbook_name)

    def set_enabled(self, playbook_name: str, enabled: bool) -> bool:
        """启停 schedule — 停用时从 APScheduler 移除 job, 启用时重新注册."""
        self.repo.set_enabled(playbook_name, enabled)
        if self.scheduler is not None:
            job_id = _job_id(playbook_name)
            if enabled:
                entry = self.repo.get(playbook_name)
                if entry is not None:
                    self._register(entry)
            else:
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
        return True

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _register(self, entry: dict[str, Any]) -> None:
        assert self.scheduler is not None
        trigger = CronTrigger.from_crontab(
            entry["cron_spec"], timezone=entry["timezone"]
        )
        self.scheduler.add_job(
            self._run_tick,
            trigger=trigger,
            id=_job_id(entry["playbook_name"]),
            name=f"playbook {entry['playbook_name']}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            kwargs={"playbook_name": entry["playbook_name"]},
        )

    def _run_tick(self, *, playbook_name: str) -> None:
        """单次 cron tick: 加载 → execute → 落 playbook_runs.

        与 trigger-gate 不同 (即时入队, 异步执行): playbook schedule 是直接
        同步执行 (R6 1h 上限内必须跑完), 失败也不阻塞下调度 (max_instances=1
        + coalesce=True 控制重叠).
        """
        from backend.services.playbook_engine import load_playbook

        entry = self.repo.get(playbook_name)
        if entry is None:
            _log.warning(f"playbook_schedule {playbook_name!r} vanished before tick")
            return
        try:
            loaded = load_playbook(entry.get("_path") or _find_playbook_path(playbook_name))
        except Exception as e:
            _log.error(f"playbook load failed: {playbook_name!r}: {e}")
            self._persist_failure(playbook_name, error=str(e))
            return

        engine = self._get_engine()
        inputs = entry.get("inputs_json") or {}
        run = engine.execute(loaded, inputs=inputs)
        self.run_repo.insert(
            run_id=run.run_id,
            playbook_name=playbook_name,
            status=run.status,
            inputs=dict(run.inputs),
            steps=[s.to_dict() for s in run.steps],
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=sum(s.elapsed_ms for s in run.steps),
            error=run.error,
        )

    def _persist_failure(self, playbook_name: str, *, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.run_repo.insert(
            run_id=f"pb-fail-{int(datetime.now().timestamp())}",
            playbook_name=playbook_name,
            status="failed",
            inputs={},
            steps=[],
            started_at=now,
            finished_at=now,
            duration_ms=0,
            error=error,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _job_id(playbook_name: str) -> str:
    return f"playbook::{playbook_name}"


def _find_playbook_path(playbook_name: str) -> str:
    """按 playbook_name 找 yaml 路径 (新 examples + 旧 codegarden/playbooks 优先新).

    兼容 YAML 文件名风格 (snake_case / kebab-case): 两个候选同时尝试.
    """
    from backend.services.playbook_engine.loader import EXAMPLES_DIR

    snake = playbook_name.replace("-", "_")
    kebab = playbook_name.replace("_", "-")
    candidates = [
        EXAMPLES_DIR / f"{snake}.yml",
        EXAMPLES_DIR / f"{kebab}.yml",
        Path("codegarden/playbooks") / f"{snake}.yml",
        Path("codegarden/playbooks") / f"{kebab}.yml",
    ]
    seen: set[str] = set()
    for p in candidates:
        s = str(p)
        if s in seen:
            continue
        seen.add(s)
        if p.exists():
            return s
    raise FileNotFoundError(f"playbook yaml not found: {playbook_name}")


from pathlib import Path  # 尾部 import 避免循环


__all__ = [
    "DEFAULT_TZ",
    "PlaybookRunRepo",
    "PlaybookScheduleRepo",
    "PlaybookScheduler",
]