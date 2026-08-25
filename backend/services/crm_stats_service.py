"""CRM 座舱 KPI 聚合服务 (口径定义: docs/COCKPIT_PRD.md §3)。

全部只读 SQL, 直接走 get_connection (聚合查询不经过行对象仓库)。
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.repository.db import get_connection


def _year_start() -> str:
    return f"{datetime.now(timezone.utc).year}-01-01"


def cockpit_stats() -> dict:
    """8 KPI + 3 图表数据 (PRD §1 US-3)。"""
    conn = get_connection()
    year_start = _year_start()

    revenue_row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS rev, COALESCE(SUM(cost),0) AS cost, "
        "COUNT(*) AS n FROM crm_opportunities WHERE stage='赢单' AND won_at >= ?",
        (year_start,),
    ).fetchone()
    revenue, cost_sum = float(revenue_row["rev"]), float(revenue_row["cost"])
    gross_margin = round((revenue - cost_sum) / revenue, 4) if revenue > 0 else None

    customers_total = conn.execute("SELECT COUNT(*) FROM crm_customers").fetchone()[0]

    repeat_row = conn.execute(
        """
        WITH won_per_customer AS (
            SELECT customer_id, COUNT(*) AS wins FROM crm_opportunities
            WHERE stage='赢单' GROUP BY customer_id
        )
        SELECT SUM(CASE WHEN wins >= 2 THEN 1 ELSE 0 END) AS repeat_n,
               COUNT(*) AS base_n
        FROM won_per_customer
        """
    ).fetchone()
    repeat_base = repeat_row["base_n"] or 0
    repeat_n = repeat_row["repeat_n"] or 0
    repeat_rate = round(repeat_n / repeat_base, 4) if repeat_base else None

    in_pipeline = conn.execute(
        "SELECT COUNT(*) FROM crm_opportunities WHERE stage IN "
        "('需求沟通','方案提交','商务谈判','合同签订')"
    ).fetchone()[0]
    won_total = conn.execute(
        "SELECT COUNT(*) FROM crm_opportunities WHERE stage='赢单'"
    ).fetchone()[0]
    lost_total = conn.execute(
        "SELECT COUNT(*) FROM crm_opportunities WHERE stage='输单'"
    ).fetchone()[0]
    win_rate = round(won_total / (won_total + lost_total), 4) if (won_total + lost_total) else None

    avg_deal = round(revenue / revenue_row["n"], 2) if revenue_row["n"] else None

    nps_row = conn.execute(
        "SELECT AVG(CASE WHEN nps_score >= 9 THEN 1.0 WHEN nps_score <= 6 THEN 0.0 END) AS p, "
        "AVG(CASE WHEN nps_score <= 6 THEN 1.0 WHEN nps_score >= 9 THEN 0.0 END) AS d "
        "FROM crm_customers WHERE nps_score IS NOT NULL"
    ).fetchone()
    nps = None
    if nps_row["p"] is not None and nps_row["d"] is not None:
        nps = round((nps_row["p"] - nps_row["d"]) * 100)

    monthly = [
        {"month": r[0], "revenue": float(r[1])}
        for r in conn.execute(
            """
            SELECT strftime('%Y-%m', won_at) AS m, SUM(amount)
            FROM crm_opportunities
            WHERE stage='赢单' AND won_at >= date('now', '-11 months', 'start of month')
            GROUP BY m ORDER BY m
            """
        )
    ]
    regions = [
        {"region": r[0], "amount": float(r[1])}
        for r in conn.execute(
            """
            SELECT c.region AS region, COALESCE(SUM(o.amount),0) AS amount
            FROM crm_opportunities o JOIN crm_customers c ON c.id = o.customer_id
            WHERE o.stage='赢单' AND o.won_at >= ?
            GROUP BY c.region ORDER BY amount DESC
            """,
            (year_start,),
        )
    ]
    funnel = [
        {"stage": s, "count": 0, "amount": 0.0} for s in
        ("需求沟通", "方案提交", "商务谈判", "合同签订")
    ]
    for r in conn.execute(
        "SELECT stage, COUNT(*) AS n, COALESCE(SUM(amount),0) AS amt "
        "FROM crm_opportunities WHERE stage NOT IN ('赢单','输单') GROUP BY stage"
    ):
        for f in funnel:
            if f["stage"] == r["stage"]:
                f["count"], f["amount"] = r["n"], float(r["amt"])

    return {
        "kpi": {
            "annual_revenue": revenue,
            "gross_margin": gross_margin,
            "customers_total": customers_total,
            "repeat_rate": repeat_rate,
            "in_pipeline": in_pipeline,
            "win_rate": win_rate,
            "avg_deal_size": avg_deal,
            "nps": nps,
        },
        "charts": {
            "monthly_revenue": monthly,
            "region_distribution": regions,
            "funnel": funnel,
        },
    }


__all__ = ["cockpit_stats"]
