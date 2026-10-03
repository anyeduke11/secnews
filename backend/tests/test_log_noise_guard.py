"""kl_trigger job 空转日志级别守卫 — v0.8.6 P0-10 日志降噪。

审计 R1/R2: `kl_trigger_t{1,2,3}_job: candidates=0 ...` 空转合计 7,643 次/日
(t1 4793 + t2 2395 + t3 455), 是 backend/logs 52MB/日的噪声主力。
P0-10 语义: **空转 (candidates=0 且 failed=0) → DEBUG** (生产 INFO 基线
不落盘); **有候选或有失败 → INFO** (审计 R2: 真实进展/失败必须可见)。
本测试锁定该双向语义, 回潮 (空转回 INFO) 或矫枉 (有候选也 DEBUG) 均红。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.scheduler.jobs import kl as kl_jobs

_IDLE = {"candidates": 0, "advanced": 0, "skipped_duplicate": 0,
         "low_link": 0, "failed": 0}
_ACTIVE = {"candidates": 3, "advanced": 3, "skipped_duplicate": 0,
           "low_link": 0, "failed": 0}
_FAILED = {"candidates": 1, "advanced": 0, "skipped_duplicate": 0,
           "low_link": 0, "failed": 1}


@pytest.mark.parametrize("job_fn,trigger_path", [
    (kl_jobs.kl_trigger_t1_job, "backend.services.triggers.t1_raw_to_refine.T1Trigger"),
    (kl_jobs.kl_trigger_t2_job, "backend.services.triggers.t2_refine_to_link.T2Trigger"),
    (kl_jobs.kl_trigger_t3_job, "backend.services.triggers.t3_link_to_structure.T3Trigger"),
])
class TestKlTriggerLogLevel:
    def _run(self, job_fn, trigger_path, report, log_cap):
        trigger = MagicMock()
        trigger.run_once.return_value = report
        with patch(trigger_path, return_value=trigger), \
             patch.object(kl_jobs, "_logger") as mock_logger:
            mock_logger.debug = log_cap["debug"]
            mock_logger.info = log_cap["info"]
            import asyncio
            asyncio.run(job_fn())
        return log_cap

    def test_idle_tick_logs_debug_not_info(self, job_fn, trigger_path):
        """空转 (全零) → DEBUG — 审计验收: 例行成功不入生产 INFO 基线。"""
        cap = {"debug": MagicMock(), "info": MagicMock()}
        self._run(job_fn, trigger_path, dict(_IDLE), cap)
        cap["debug"].assert_called_once()
        cap["info"].assert_not_called()

    def test_active_tick_logs_info(self, job_fn, trigger_path):
        """有候选 → INFO (真实进展可见, 不得矫枉过正降成 DEBUG)。"""
        cap = {"debug": MagicMock(), "info": MagicMock()}
        self._run(job_fn, trigger_path, dict(_ACTIVE), cap)
        cap["info"].assert_called_once()
        cap["debug"].assert_not_called()

    def test_failed_tick_logs_info(self, job_fn, trigger_path):
        """有失败 → INFO (审计 R2: 失败不得静默)。"""
        cap = {"debug": MagicMock(), "info": MagicMock()}
        self._run(job_fn, trigger_path, dict(_FAILED), cap)
        cap["info"].assert_called_once()
