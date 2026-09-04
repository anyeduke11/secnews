"""v0.8 Phase B (B6) — skill_registry 运行历史 + 反馈打分 API.

路由清单
--------
- GET  /api/skill-registry/{skill_id}/runs        — 运行历史 (倒序最近 limit 条)
- GET  /api/skill-registry/runs/{run_id}          — 单次运行详情 (历史回放数据源)
- POST /api/skill-registry/runs/{run_id}/feedback — 反馈打分 (写 agent_memory feedback_log)

与 A3 主路由 (skill_registry_api.py, 150 行上限已满) 拆分独立文件, 同前缀
同 gate (skill_registry); 两段式路径与主路由单段 ``/{skill_id}`` 段数不同,
Starlette 全路径匹配互不遮蔽。错误信封 (P3-2): detail 三字段必填
``{message, code, hint}``。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.agent_memory import agent_memory
from backend.services.skill_registry import BUILTIN, SkillNotFoundError
from backend.services.skill_runner.result import SkillRunRepo

router = APIRouter(prefix="/api/skill-registry", tags=["skill-registry"])

#: 单例 (SkillRunRepo 不持连接, thread-local 安全, 仓库惯例)
_runs = SkillRunRepo()


class FeedbackRequest(BaseModel):
    """反馈打分请求体 — score 1-5 (👍=5 / 👎=1), comment 可选文字评论。"""

    score: int
    comment: str = ""


def _http_error(status: int, message: str, code: str, hint: str) -> HTTPException:
    """统一错误信封 — detail 三字段必填 (P3-2)。"""
    return HTTPException(
        status_code=status, detail={"message": message, "code": code, "hint": hint}
    )


def _skill_not_found(skill_id: str) -> HTTPException:
    """未知 skill_id 标准 404 — 与 A3 主路由同信封。"""
    return _http_error(
        404, f"skill not found: {skill_id!r}", "SKILL_NOT_FOUND",
        "GET /api/skill-registry 列出全部可用 skill id",
    )


def _run_not_found(run_id: str) -> HTTPException:
    return _http_error(
        404, f"skill run not found: {run_id!r}", "RUN_NOT_FOUND",
        "GET /api/skill-registry/{skill_id}/runs 列出该 skill 的全部运行",
    )


@router.get("/{skill_id}/runs")
def list_skill_runs(skill_id: str, limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    """运行历史 — 先 404 校验 skill 存在, 再按 skill 维度倒序取最近 limit 条
    (SkillRunRepo 已反序列化 inputs/result/metrics JSON 字段)。"""
    try:
        BUILTIN.get(skill_id)
    except SkillNotFoundError:
        raise _skill_not_found(skill_id) from None
    return _runs.list_for_skill(skill_id, limit=limit)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    """单次运行详情 — RunHistory 回放展开 (含 result/metrics 全量产物)。"""
    run = _runs.get(run_id)
    if run is None:
        raise _run_not_found(run_id)
    return run


@router.post("/runs/{run_id}/feedback")
def submit_feedback(run_id: str, req: FeedbackRequest) -> dict:
    """反馈打分 — 校验 run 存在后写 feedback_log (agent_memory 单出口)。

    校验链: run 不存在 → 404 RUN_NOT_FOUND (先查, 保证状态码语义);
    score 越界 (record_feedback ValueError) → 400 FEEDBACK_INVALID。
    落库成功返回反馈完整行 (含 created_at)。
    """
    run = _runs.get(run_id)
    if run is None:
        raise _run_not_found(run_id)
    try:
        return agent_memory.record_feedback(
            run_id, skill_id=str(run["skill_id"]), score=req.score, comment=req.comment
        )
    except ValueError as e:
        raise _http_error(
            400, str(e), "FEEDBACK_INVALID", "score 须为 1-5 整数 (👍=5 / 👎=1)"
        ) from None


__all__ = ["router"]
