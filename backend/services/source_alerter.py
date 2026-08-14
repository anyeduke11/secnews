"""源级告警引擎 — 基于阈值触发告警，写入 source_alerts 表。

Phase 3: 6 条告警规则，24h 去重。
"""
from __future__ import annotations

from backend.logging_config import logger as _root_logger
from backend.repository.db import get_connection
from backend.repository.source_alert_repo import SourceAlertRepository
from backend.repository.source_scheduler_repo import SourceSchedulerRepository

logger = _root_logger.bind(component="source_alerter")

# 告警规则阈值
ALERT_CONSECUTIVE_FAILURE_MIN = 5      # 连续失败 ≥ 5 → P1
ALERT_REJECTION_RATE_THRESHOLD = 0.3   # 拒绝率 > 30% → P2
ALERT_DURATION_MS_THRESHOLD = 30000    # 耗时 > 30s → P2
ALERT_URL_CHECK_PASS_RATE = 0.8        # URL 校验通过率 < 80% → P2
ALERT_DEHYS_INTERVAL = 24             # 24h 去重


class SourceAlerter:
    """源级告警引擎。"""

    def __init__(self):
        self.alert_repo = SourceAlertRepository()
        self.source_repo = SourceSchedulerRepository()

    def evaluate_all(self) -> dict:
        """对所有活跃源检查告警规则。

        Returns:
            dict: {alerts_triggered: int, alerts_by_level: {P1: int, P2: int},
                   sources_checked: int, details: list[dict]}
        """
        all_sources = self.source_repo.list_all()
        active_sources = [s for s in all_sources if s.get("status") in ("active", "grace", "stale")]

        triggered = 0
        p1_count = 0
        p2_count = 0
        details: list[dict] = []

        for source in active_sources:
            source_id = source["id"]
            source_name = source.get("name", source_id)
            alerts = []

            # Rule 1: 连续失败
            cf = int(source.get("consecutive_failures", 0))
            if cf >= ALERT_CONSECUTIVE_FAILURE_MIN:
                if not self.alert_repo.has_recent(source_id, "consecutive_failure", ALERT_DEHYS_INTERVAL):
                    self.alert_repo.insert({
                        "source_id": source_id,
                        "alert_type": "consecutive_failure",
                        "level": "P1",
                        "message": f"源 {source_name} 连续失败 {cf} 次",
                        "detail": f'{{"consecutive_failures": {cf}}}',
                    })
                    alerts.append({"type": "consecutive_failure", "level": "P1", "detail": f"consecutive_failures={cf}"})
                    p1_count += 1
                    triggered += 1

            # Rule 2: 拒绝率异常 (from crawler_runs)
            stats = self.source_repo.get_run_stats(source_id, since_hours=24)
            total_runs = stats.get("total_runs", 0)
            if total_runs >= 3:
                rejection_rate = stats.get("rejection_rate", 0.0)
                if rejection_rate > ALERT_REJECTION_RATE_THRESHOLD:
                    if not self.alert_repo.has_recent(source_id, "rejection_rate", ALERT_DEHYS_INTERVAL):
                        self.alert_repo.insert({
                            "source_id": source_id,
                            "alert_type": "rejection_rate",
                            "level": "P2",
                            "message": f"源 {source_name} 拒绝率异常: {rejection_rate:.1%}",
                            "detail": f'{{"rejection_rate": {rejection_rate:.3f}, "total_runs": {total_runs}}}',
                        })
                        alerts.append({"type": "rejection_rate", "level": "P2", "detail": f"rejection_rate={rejection_rate:.1%}"})
                        p2_count += 1
                        triggered += 1

                # Rule 3: HTTP 状态异常
                failed_runs = stats.get("failed_runs", 0)
                if failed_runs > 0 and failed_runs / total_runs > 0.3:
                    if not self.alert_repo.has_recent(source_id, "http_status", ALERT_DEHYS_INTERVAL):
                        self.alert_repo.insert({
                            "source_id": source_id,
                            "alert_type": "http_status",
                            "level": "P2",
                            "message": f"源 {source_name} HTTP 异常: {failed_runs}/{total_runs} 次失败",
                            "detail": f'{{"failed_runs": {failed_runs}, "total_runs": {total_runs}}}',
                        })
                        alerts.append({"type": "http_status", "level": "P2", "detail": f"failed_runs={failed_runs}/{total_runs}"})
                        p2_count += 1
                        triggered += 1

                # Rule 4: 耗时异常
                avg_duration = stats.get("avg_duration_ms", 0)
                if avg_duration > ALERT_DURATION_MS_THRESHOLD:
                    if not self.alert_repo.has_recent(source_id, "duration", ALERT_DEHYS_INTERVAL):
                        self.alert_repo.insert({
                            "source_id": source_id,
                            "alert_type": "duration",
                            "level": "P2",
                            "message": f"源 {source_name} 平均耗时异常: {avg_duration}ms",
                            "detail": f'{{"avg_duration_ms": {avg_duration}}}',
                        })
                        alerts.append({"type": "duration", "level": "P2", "detail": f"avg_duration={avg_duration}ms"})
                        p2_count += 1
                        triggered += 1

            # Rule 5: URL 校验通过率低
            conn = get_connection()
            url_check_row = conn.execute(
                "SELECT "
                "  COUNT(*) AS total, "
                "  SUM(CASE WHEN status_code IS NOT NULL AND status_code < 400 THEN 1 ELSE 0 END) AS passed "
                "FROM crawl_url_checks cuc "
                "JOIN hotspots h ON cuc.item_id = h.id "
                "WHERE h.source = ? AND cuc.checked_at >= datetime('now', '-24 hours')",
                (source_id,),
            ).fetchone()
            if url_check_row and int(url_check_row["total"] or 0) >= 5:
                total_checks = int(url_check_row["total"])
                passed = int(url_check_row["passed"] or 0)
                pass_rate = passed / total_checks if total_checks > 0 else 1.0
                if pass_rate < ALERT_URL_CHECK_PASS_RATE:
                    if not self.alert_repo.has_recent(source_id, "url_check", ALERT_DEHYS_INTERVAL):
                        self.alert_repo.insert({
                            "source_id": source_id,
                            "alert_type": "url_check",
                            "level": "P2",
                            "message": f"源 {source_name} URL 校验通过率低: {pass_rate:.1%}",
                            "detail": f'{{"pass_rate": {pass_rate:.3f}, "total": {total_checks}, "passed": {passed}}}',
                        })
                        alerts.append({"type": "url_check", "level": "P2", "detail": f"pass_rate={pass_rate:.1%}"})
                        p2_count += 1
                        triggered += 1

            # Rule 6: 核心 P0 源死亡
            priority = int(source.get("priority", 50))
            if source.get("status") == "dead" and priority >= 80:
                if not self.alert_repo.has_recent(source_id, "p0_dead", ALERT_DEHYS_INTERVAL):
                    self.alert_repo.insert({
                        "source_id": source_id,
                        "alert_type": "p0_dead",
                        "level": "P1",
                        "message": f"核心 P0 源 {source_name} 已死亡",
                        "detail": f'{{"priority": {priority}}}',
                    })
                    alerts.append({"type": "p0_dead", "level": "P1", "detail": "P0 source dead"})
                    p1_count += 1
                    triggered += 1

            if alerts:
                details.append({"source_id": source_id, "source_name": source_name, "alerts": alerts})
                for a in alerts:
                    logger.warning(
                        f"alert [{a['level']}] source={source_name} "
                        f"type={a['type']} detail={a['detail']}"
                    )

        logger.info(
            f"source_alerter: checked {len(active_sources)} sources, "
            f"triggered {triggered} alerts "
            f"(P1={p1_count}, P2={p2_count})"
        )
        return {
            "alerts_triggered": triggered,
            "alerts_by_level": {"P1": p1_count, "P2": p2_count},
            "sources_checked": len(active_sources),
            "details": details,
        }


__all__ = ["SourceAlerter"]