"""v0.8.5 G2: demo 消费端点与后端路由注册一致性校验 (check_* 只读, 无副作用)。

事实源: docs/v0.8.5/V0.8.5_PLAN.md §6 (三层接口消费表) — 路由表漂移时以文档为准回改本表。
机制: import backend.main:app 枚举 app.routes, 断言下方 METHOD+path 全部注册。
路径模板匹配: {param} 段视为通配 (要求段数 + 字面段一致), 参数名不要求一致。
注意: /api/skill-registry/v1* 注册受 feature gate ``skill_registry`` 影响 —
本脚本按默认 feature_gates.toml (true) 校验; 若以 core-only env 运行, 相关行会 FAIL,
请恢复默认 gates 后重跑。

用法: .venv/bin/python scripts/check_v1_endpoint_parity.py [--format json]
退出: 0 = 全部注册; 1 = 有缺失; 2 = app 导入失败。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# spec §6 demo 消费端点 (G3 检查单同源; v0 部分含 /garden /judge 恢复页依赖)
EXPECTED: list[tuple[str, str, str]] = [
    # -- 资料层 / (§6.1) --
    ("GET",  "/api/hotspots",                      "资料层情报流 (useHotspotData)"),
    ("GET",  "/api/sources/health",                "心跳条源健康"),
    ("GET",  "/api/kl/pipeline/stats",             "心跳条漏斗+队列"),
    ("GET",  "/api/favorites",                     "收藏"),
    ("GET",  "/api/quality/summary",               "右栏质量门禁"),
    ("GET",  "/api/todos",                         "右栏今日行动"),
    ("POST", "/api/kl/import/url",                 "URL 导入"),
    ("GET",  "/api/v1/signals",                    "v1 受管信号区块"),
    ("POST", "/api/v1/cases",                      "信号立项 → /cases/{id}"),
    # -- 判断层 /judge (§6.2) --
    ("GET",  "/api/trends",                        "判读台趋势 rail"),
    ("GET",  "/api/kl/compounding",                "复利 rail"),
    ("POST", "/api/llm/evaluate",                  "LLM 判读"),
    ("POST", "/api/favorites",                     "归档收藏"),
    # -- 判断层深链 /cases/:caseId (§6.3) --
    ("GET",    "/api/v1/cases",                          "Case 列表/队列"),
    ("GET",    "/api/v1/cases/{case_id}",                "Case 详情"),
    ("PATCH",  "/api/v1/cases/{case_id}",                "CAS 更新"),
    ("POST",   "/api/v1/cases/{case_id}/close",          "关闭 (R17 守卫)"),
    ("GET",    "/api/v1/cases/{case_id}/aggregate",      "C11 单点聚合"),
    ("POST",   "/api/v1/judgments/generate",             "SK-02 出稿 (dsh/ai_hub)"),
    ("GET",    "/api/v1/judgments",                      "判断列表 (case_id 必填)"),
    ("GET",    "/api/v1/judgments/{judgment_id}",        "判断详情"),
    ("POST",   "/api/v1/judgments/{judgment_id}/publish", "三重守卫发布"),
    ("POST",   "/api/v1/actions/generate",               "SK-03 行动生成"),
    ("GET",    "/api/v1/actions",                        "行动列表 (case_id 必填)"),
    ("GET",    "/api/v1/actions/{action_id}",            "行动详情"),
    ("POST",   "/api/v1/actions/{action_id}/approve",    "批准"),
    ("POST",   "/api/v1/actions/{action_id}/start",      "启动 (idempotency_key)"),
    ("POST",   "/api/v1/actions/{action_id}/cancel",     "取消"),
    ("GET",    "/api/v1/runs",                           "运行列表 (action_id 必填)"),
    ("GET",    "/api/v1/runs/{run_id}",                  "运行详情"),
    ("POST",   "/api/v1/artifacts",                      "产物创建 (hash)"),
    ("GET",    "/api/v1/artifacts",                      "产物列表 (run_id 必填)"),
    ("GET",    "/api/v1/artifacts/{artifact_id}",        "产物详情"),
    ("POST",   "/api/v1/artifacts/{artifact_id}/verify", "验证"),
    ("POST",   "/api/v1/artifacts/{artifact_id}/accept", "业务验收"),
    ("POST",   "/api/v1/artifacts/{artifact_id}/reject", "拒绝 (防重传)"),
    ("GET",    "/api/v1/knowledge",                      "知识列表 (case_id 可选)"),
    ("GET",    "/api/v1/knowledge/{knowledge_id}",       "知识详情"),
    ("GET",    "/api/v1/knowledge/{knowledge_id}/reuse", "复用 receipt"),
    ("POST",   "/api/v1/knowledge/generate",             "SK-04/05/06 生成"),
    ("POST",   "/api/v1/knowledge/{knowledge_id}/publish",   "发布 (CAS)"),
    ("POST",   "/api/v1/knowledge/{knowledge_id}/deprecate", "弃用"),
    ("POST",   "/api/v1/knowledge/{knowledge_id}/retract",   "撤回"),
    ("POST",   "/api/v1/knowledge/{knowledge_id}/adopt",     "采用回执"),
    ("GET",    "/api/v1/knowledge/{knowledge_id}/adoptions", "采用列表 (无服务端过滤, FactCheck #1)"),
    ("POST",   "/api/v1/knowledge/{knowledge_id}/outcome",   "采用结果回填"),
    ("GET",    "/api/v1/knowledge/{knowledge_id}/recall",    "case 适用性召回"),
    # -- 行动层 /action (§6.4) --
    ("PATCH", "/api/todos/{todo_id}",                        "待办勾选"),
    ("POST",  "/api/todos",                                  "待办新增"),
    ("GET",   "/api/kl/planning-actions",                    "规划行动队列"),
    ("PUT",   "/api/kl/planning-actions/{action_id}/status", "规划推进"),
    ("GET",   "/api/reviews/due",                            "SM-2 到期"),
    ("GET",   "/api/reviews/stats",                          "复习统计"),
    ("POST",  "/api/reviews/{review_type}/{item_id}/grade",  "复习评分"),
    ("GET",   "/api/secnews/stats",                          "看板统计"),
    # -- /judge/graph (恢复页依赖) --
    ("GET",   "/api/knowledge/graph",                        "知识图谱"),
    ("GET",   "/api/knowledge/concepts",                     "概念列表"),
    # -- /garden (恢复页依赖, gate codegarden) --
    ("GET",   "/api/codegarden/projects",                    "泳道项目"),
    ("GET",   "/api/codegarden/services",                    "服务列表"),
    ("GET",   "/api/codegarden/events",                      "事件流"),
    ("GET",   "/api/codegarden/dependencies",                "依赖"),
    # -- 工具页 (§6.6; 流程验证补充: SSE + dsh 健康 + 观测 + legacy skill-registry 变异端点) --
    ("GET",   "/api/skill-registry/v1",                           "技能商店 v1 分桶 (gate skill_registry)"),
    ("GET",   "/api/skill-registry/v1/{skill_id}",                "v1 技能详情"),
    ("GET",   "/api/events",                                       "SSE 事件流 (last_id 重放)"),
    ("GET",   "/api/dsh/health",                                   "dsh 健康 (secnews StatusBar)"),
    ("GET",   "/api/observability/summary",                        "观测摘要"),
    ("GET",   "/api/observability/alerts/active",                  "活跃告警"),
    ("GET",   "/api/skill-registry",                               "技能列表 (legacy 全量)"),
    ("POST",  "/api/skill-registry/{skill_id}/run",                "技能运行 (排队)"),
    ("POST",  "/api/skill-registry/{skill_id}/enable",             "技能启用"),
    ("POST",  "/api/skill-registry/{skill_id}/disable",            "技能停用"),
    ("GET",   "/api/skill-registry/{skill_id}/runs",               "运行历史"),
    ("GET",   "/api/skill-registry/runs/{run_id}",                "运行详情"),
    ("POST",  "/api/skill-registry/runs/{run_id}/feedback",       "反馈打分"),
]


def _segments(path: str) -> list[str]:
    return [s for s in path.strip("/").split("/") if s != ""]


def _template_matches(route_path: str, spec_path: str) -> bool:
    rs, ss = _segments(route_path), _segments(spec_path)
    if len(rs) != len(ss):
        return False
    for r, s in zip(rs, ss):
        if r.startswith("{") and r.endswith("}"):
            continue
        if r != s:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    try:
        from backend.main import app
    except Exception as e:  # noqa: BLE001 — 导入失败要给出可读诊断
        print(f"FAIL import backend.main: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    # 经 OpenAPI schema 枚举注册路由 — 对 fastapi 嵌套路由 (_IncludedRouter) 版本无关
    try:
        schema = app.openapi()
    except Exception as e:  # noqa: BLE001
        print(f"FAIL app.openapi(): {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    registered: dict[str, set[str]] = {}
    for path, methods in (schema.get("paths") or {}).items():
        registered.setdefault(path, set()).update(m.upper() for m in methods)

    rows, missing = [], []
    for method, spec_path, note in EXPECTED:
        hit = any(
            method in registered.get(rp, set()) and _template_matches(rp, spec_path)
            for rp in registered
        )
        rows.append({"method": method, "path": spec_path, "note": note, "registered": hit})
        if not hit:
            missing.append((method, spec_path, note))

    if args.format == "json":
        print(json.dumps({
            "total": len(EXPECTED),
            "registered": len(EXPECTED) - len(missing),
            "missing": missing,
            "rows": rows,
        }, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            mark = "OK  " if r["registered"] else "MISS"
            print(f"[{mark}] {r['method']:<6} {r['path']:<52} {r['note']}")
        print(f"\n{len(EXPECTED) - len(missing)}/{len(EXPECTED)} 端点已注册")
        if missing:
            print("缺失清单:")
            for m, p, n in missing:
                print(f"  - {m} {p}  ({n})")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
