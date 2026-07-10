"""故障演练 1 — GitHub Trending 503 — Phase 7 Task 4.1.

monkey-patch ``GitHubCollector.fetch_source`` 抛
``aiohttp.ClientResponseError(status=503)``，然后调
``CollectionService.run_once()``：

- 验证 6 个分类全部成功
- 验证 GitHubCollector 返回的 items 含 ``is_fallback=True`` 标记

结果写入 ``scripts/logs/chaos_1_<ts>.json``。
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
def _patch_github_503() -> Any:
    """替换 GitHubCollector.fetch_source 为抛 ClientResponseError(503)."""
    import aiohttp  # type: ignore
    from backend.collectors.github_collector import GitHubCollector  # type: ignore

    original = GitHubCollector.fetch_source

    async def _boom(self, source: dict):
        # 模拟 HTTP 503
        raise aiohttp.ClientResponseError(
            request_info=aiohttp.RequestInfo(
                url=source["url"],
                method="GET",
                headers={},
                real_url=source["url"],
            ),
            history=(),
            code=503,
            message="Service Unavailable (chaos-injected)",
            headers={},
        )

    GitHubCollector.fetch_source = _boom
    return original


def _restore(original) -> None:
    from backend.collectors.github_collector import GitHubCollector  # type: ignore

    GitHubCollector.fetch_source = original


# ---------------------------------------------------------------------------
def main() -> int:
    out_path = LOGS_DIR / f"chaos_1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report: dict[str, Any] = {
        "scenario": "chaos_1_github_503",
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    # 信号处理
    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    original = _patch_github_503()
    print("[chaos_1] GitHubCollector.fetch_source patched to raise 503", flush=True)

    try:
        from backend.services.collection_service import CollectionService  # type: ignore

        # 跑一次 collection
        # 复制现有 collector（避免污染全局）
        svc = CollectionService()
        # 强制只用 GitHubCollector 的 fallback
        t0 = time.time()
        report_obj = asyncio.run(svc.run_once())
        duration = round((time.time() - t0) * 1000, 1)

        per_category = []
        all_succeed = True
        github_fallback_count = 0
        for r in report_obj.results:
            ok = r.error is None
            all_succeed = all_succeed and ok
            is_github = r.category.value == "github"
            if is_github:
                github_fallback_count = r.fallback_count
            per_category.append(
                {
                    "category": r.category.value,
                    "ok": ok,
                    "item_count": r.item_count,
                    "fallback_count": r.fallback_count,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
            )

        # 显式验证 GitHub 分类有 fallback
        from backend.domain.enums import Category  # type: ignore

        gh_result = next(
            (r for r in report_obj.results if r.category == Category.GITHUB), None
        )
        github_has_fallback_items = False
        if gh_result is not None:
            github_has_fallback_items = any(it.is_fallback for it in gh_result.items)

        report.update(
            {
                "duration_ms": duration,
                "total_items": report_obj.total,
                "success_count": report_obj.success_count,
                "failed_count": report_obj.failed_count,
                "fallback_count": report_obj.fallback_count,
                "per_category": per_category,
                "all_6_categories_succeeded": all_succeed and report_obj.success_count == 6,
                "github_fallback_count": github_fallback_count,
                "github_has_fallback_items": github_has_fallback_items,
                "pass": all_succeed
                and report_obj.success_count == 6
                and github_has_fallback_items
                and report_obj.failed_count == 0,
            }
        )
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        report["traceback"] = traceback.format_exc()
        report["pass"] = False
    finally:
        _restore(original)
        report["finished_at"] = datetime.utcnow().isoformat() + "Z"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[chaos_1] pass={report.get('pass')} report={out_path}", flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
