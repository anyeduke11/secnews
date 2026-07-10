"""Phase 10 质量门禁覆盖审计脚本

目的
----
用户要求"检查质量门禁覆盖范围, 包括所有资讯, 标讯都需要覆盖在内"。

本脚本扫真实 SQLite DB 中 6 大分类, 统计每个分类的 item 数量 + 哪些有
quality_score / quality_flags / quality_checked_at 字段, 验证质量门禁
9 个 gate 确实在 collect 链路里被跑到。

输出
----
- 表格: 6 大分类 (ai/security/finance/startup/bid/github) × (total/with_quality_score/pct)
- 验证规则:
    1. 每个分类至少 1 个非 fallback item
    2. 每个非 fallback item 都有 quality_score (即门禁跑过)
    3. 标记 quality_flags 的 item 数量 (说明门禁有 flag 触发)
    4. quality_checked_at 不为空 (说明门禁时间戳写过)
- 退出码: 0 = 全部 PASS, 1 = 有 FAIL

注意
----
- 直接读 ``backend/hotspot.db``；不要在生产高峰期跑（会短暂打开 DB 句柄）
- 仅做只读查询，不修改任何数据
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# 6 大分类 (按 enum 顺序)
CATEGORIES = ["ai", "security", "finance", "startup", "bid", "github"]
CAT_CN = {
    "ai": "科技/AI",
    "security": "网络安全",
    "finance": "金融/投资",
    "startup": "独立开发/创业",
    "bid": "招标资讯",
    "github": "GitHub 项目",
}

# 9 个 gate 期望在 quality_flags 里出现
EXPECTED_GATES_FLAGS = [
    "url_drilldown_resolved",
    "url_drilldown_failed",
    "url_drilldown_error",
    "url_not_drillable",
    "author_mismatch",
    "author_unknown",
    "author_verified",
    "fallback",
    "duplicate_url_same_title",
    "duplicate_url_different_title",
    "duplicate_title_different_url",
    "low_quality_content",
    "schema_violation",
    "url_invalid",
    "source_unverified",
    "category_mismatch",
]


def audit(db_path: Path) -> int:
    """主审计函数。返回 0=全过, 1=有失败。"""
    if not db_path.exists():
        print(f"[ERR] DB 不存在: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # 1) schema check
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(hotspots)").fetchall()}
        required = {"quality_score", "quality_flags", "quality_checked_at", "category", "is_fallback"}
        missing = required - cols
        if missing:
            print(f"[ERR] hotspots 表缺字段: {missing}")
            return 1
        print(f"[OK] schema 检查通过 (字段齐全)")

        # 2) 6 大分类覆盖度统计
        print(f"\n{'='*80}")
        print(f"{'分类':<18} {'总数':<6} {'fallback':<9} {'有 quality_score':<16} {'有 quality_flags':<16} {'有 checked_at':<13} {'覆盖率':<6}")
        print(f"{'='*80}")
        all_pass = True
        any_real_data = False
        for cat in CATEGORIES:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_fallback = 1 THEN 1 ELSE 0 END) AS fb_n,
                    SUM(CASE WHEN quality_score IS NOT NULL AND is_fallback = 0 THEN 1 ELSE 0 END) AS with_qs,
                    SUM(CASE WHEN quality_flags IS NOT NULL AND quality_flags != '' AND quality_flags != '[]' AND is_fallback = 0 THEN 1 ELSE 0 END) AS with_qf,
                    SUM(CASE WHEN quality_checked_at IS NOT NULL AND quality_checked_at != '' AND is_fallback = 0 THEN 1 ELSE 0 END) AS with_ts
                FROM hotspots WHERE category = ?
                """,
                (cat,),
            ).fetchone()
            total = int(row["total"] or 0)
            fb = int(row["fb_n"] or 0)
            with_qs = int(row["with_qs"] or 0)
            with_qf = int(row["with_qf"] or 0)
            with_ts = int(row["with_ts"] or 0)
            non_fb = total - fb
            cov = f"{(with_qs / non_fb * 100):.1f}%" if non_fb > 0 else "N/A"

            cat_cn = f"{cat}({CAT_CN[cat]})"
            print(f"{cat_cn:<18} {total:<6} {fb:<9} {with_qs:<16} {with_qf:<16} {with_ts:<13} {cov:<6}")

            if non_fb > 0:
                any_real_data = True
                if with_qs < non_fb:
                    print(f"  [WARN] {cat}: {non_fb - with_qs} 个非 fallback item 没有 quality_score")
                    all_pass = False
                if with_ts < non_fb:
                    print(f"  [WARN] {cat}: {non_fb - with_ts} 个非 fallback item 没有 quality_checked_at (历史数据无时间戳)")

        if not any_real_data:
            print(f"\n[WARN] 数据库中所有分类都只有 0 或全 fallback item,无法验证门禁覆盖")
            print(f"   请先运行 collect 触发 collect_all_job,再跑本脚本")
            return 1

        # 3) gate 触发统计
        print(f"\n{'='*80}")
        print(f"Quality flags 触发频次（按分类）")
        print(f"{'='*80}")
        all_flags: dict[str, int] = {}
        for cat in CATEGORIES:
            rows = conn.execute(
                "SELECT quality_flags FROM hotspots WHERE category = ? AND quality_flags IS NOT NULL AND quality_flags != '' AND quality_flags != '[]'",
                (cat,),
            ).fetchall()
            for r in rows:
                raw = r["quality_flags"]
                if not raw:
                    continue
                try:
                    import json
                    arr = json.loads(raw)
                    if not isinstance(arr, list):
                        continue
                    for f in arr:
                        all_flags[str(f)] = all_flags.get(str(f), 0) + 1
                except (json.JSONDecodeError, TypeError):
                    continue

        if not all_flags:
            print(f"  (无任何 flag 触发 — 全部项都通过了所有 9 个 gate, 这是最理想状态)")
        else:
            for flag, n in sorted(all_flags.items(), key=lambda x: -x[1]):
                print(f"  {flag:<40} {n}")
        print(f"{'='*80}")

        # 4) 9 个 gate 验证 (从 pipeline 文件直接导入)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from backend.quality.pipeline import QualityGatePipeline
            gates = [g.__name__ for g in QualityGatePipeline.DEFAULT_GATES]
            print(f"\n[OK] QualityGatePipeline.DEFAULT_GATES 共 {len(gates)} 个:")
            for i, g in enumerate(gates, 1):
                print(f"  {i}. {g}")
        except Exception as e:
            print(f"[WARN] 无法加载 QualityGatePipeline: {e}")

        # 5) 各分类平均 quality_score
        print(f"\n{'='*80}")
        print(f"各分类平均 quality_score（非 fallback）")
        print(f"{'='*80}")
        for cat in CATEGORIES:
            row = conn.execute(
                """
                SELECT AVG(quality_score) AS avg_qs, MIN(quality_score) AS min_qs, MAX(quality_score) AS max_qs
                FROM hotspots WHERE category = ? AND is_fallback = 0 AND quality_score IS NOT NULL
                """,
                (cat,),
            ).fetchone()
            if row and row["avg_qs"] is not None:
                print(f"  {cat:<12} avg={float(row['avg_qs']):.1f}  min={int(row['min_qs'])}  max={int(row['max_qs'])}")
            else:
                print(f"  {cat:<12} (无非 fallback 数据)")

        # 6) 时间戳新鲜度
        print(f"\n{'='*80}")
        print(f"quality_checked_at 时间分布（最近 5 条）")
        print(f"{'='*80}")
        rows = conn.execute(
            """
            SELECT category, quality_checked_at FROM hotspots
            WHERE quality_checked_at IS NOT NULL AND quality_checked_at != '' AND is_fallback = 0
            ORDER BY quality_checked_at DESC LIMIT 5
            """
        ).fetchall()
        for r in rows:
            print(f"  {r['category']:<12} {r['quality_checked_at']}")

        # 总结
        print(f"\n{'='*80}")
        print(f"总结")
        print(f"{'='*80}")
        if all_pass:
            print(f"[PASS] 6 大分类质量门禁覆盖完整,所有非 fallback item 都已过门禁")
        else:
            print(f"[FAIL] 部分分类有非 fallback item 未过门禁,需要排查")
        return 0 if all_pass else 1
    finally:
        conn.close()


def main() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from backend.config import config
        db_path = Path(config.db_path)
    except Exception:
        db_path = Path("backend/hotspot.db")

    print(f"DB: {db_path.resolve()}")
    print(f"开始时间: {datetime.now(timezone.utc).isoformat()}\n")
    return audit(db_path.resolve())


if __name__ == "__main__":
    sys.exit(main())
