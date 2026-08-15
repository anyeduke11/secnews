"""质量门禁钩子 Mixin（v1.8 R3 从 base.py 拆出）。

``QualityGatesMixin`` 承载 BaseCollector 的 Phase 3.5 质量门禁集成：

- ``_skip_quality``      — ClassVar 开关，测试置 True 跳过门禁
- ``_run_quality_gates`` — 跑 :class:`QualityGatePipeline`

依赖宿主类的 ``logger`` 属性；quality 相关依赖全部惰性导入，
保持与原 base.py 行为一致（DB 不可用时兜底跳过）。
"""
from __future__ import annotations

from backend.collectors.parsing import _now_utc
from backend.domain.models import HotspotItem


class QualityGatesMixin:
    """BaseCollector 的质量门禁集成（依赖宿主类的 ``logger``）。"""

    # ------------------------------------------------------------------
    # Phase 3.5 — 质量门禁集成
    # ------------------------------------------------------------------
    # ``True`` 时 collect() 跳过同步门禁（fallback 路径也跳过）。
    # 测试可在 setUp() 里置 True 避免构造 QualityConfig 依赖。
    _skip_quality: bool = False

    async def _run_quality_gates(
        self, items: list[HotspotItem]
    ) -> list[HotspotItem]:
        """跑 :class:`QualityGatePipeline`；fallback 数据原样保留。

        Phase 9.2: 改为 async，每个 item 用 :func:`asyncio.to_thread` 包到
        thread pool 跑，避免 FinalUrlGate 内部 sync urllib 阻塞 event loop。
        """
        import asyncio

        from backend.exceptions import QualityGateFailed
        from backend.quality.config import QualityConfig
        from backend.quality.pipeline import (
            QualityGatePipeline,
            build_context,
        )

        try:
            cfg = QualityConfig()
        except Exception as e:  # pragma: no cover — DB 不可用时兜底
            self.logger.warning(
                f"QualityConfig init failed, skip gates: {e}"
            )
            return items

        # 预拉取 URL / title 集合
        existing_urls: set[str] = set()
        existing_titles: list[str] = []
        try:
            from backend.repository.hotspot_repo import HotspotRepository

            hrepo = HotspotRepository()
            # P2-2: 去重窗口用「滚动 7 天」而非 TimeRange.D7 (本周一 00:00 起) —
            # D7 的日历周语义是 UI 展示约定, 用于去重会让上周入库的条目
            # 本周被重复抓取时不在去重视野内 → 系统性跨周重复入库。
            from datetime import datetime, timedelta, timezone
            now_utc = datetime.now(timezone.utc)
            roll_start = now_utc - timedelta(days=7)
            db_items, _ = hrepo.query_in_range(
                start=roll_start,
                end=now_utc,
                limit=2000,
            )
            existing_urls = {str(it.url) for it in db_items}
            existing_titles = [it.title for it in db_items]
        except Exception:
            pass

        # Phase 8 Addendum: 构造本批次 url/title/source 三元组，注入到
        # context.url_title_pairs，供 DuplicateGate 做"同 URL 不同 title"
        # 歧义识别。失败/字段缺失时退化为空列表（DuplicateGate 会跳过该检测）。
        url_title_pairs: list[dict] = []
        try:
            url_title_pairs = [
                {
                    "url": str(it.url),
                    "title": it.title,
                    "source": it.source,
                    "id": it.id,
                    "is_fallback": it.is_fallback,
                    "fetched_at": it.fetched_at,
                }
                for it in items
            ]
        except Exception:
            url_title_pairs = []

        try:
            ctx = build_context(
                cfg,
                existing_urls=existing_urls,
                existing_titles=existing_titles,
                url_title_pairs=url_title_pairs,
            )
            pipeline = QualityGatePipeline(cfg)
        except Exception as e:
            self.logger.warning(
                f"pipeline init failed, skip gates: {e}"
            )
            return items

        out: list[HotspotItem] = []
        for item in items:
            if item.is_fallback:
                out.append(item)
                continue
            try:
                # Phase 9.2: 放到 thread pool 跑，避免 FinalUrlGate 内
                # 同步 urllib 阻塞 event loop
                presult = await asyncio.to_thread(pipeline.run_all, item, ctx)
            except QualityGateFailed as e:
                # 严格模式拒绝：丢弃该 item
                self.logger.warning(
                    f"strict-mode reject: id={item.id} score={e.score} flags={e.flags}"
                )
                # Phase 0.5 (Crawler v2): 旁路写入 quality_rejection_log
                await asyncio.to_thread(
                    self._write_quality_rejection, item, "strict_mode", str(e.flags)
                )
                continue
            except Exception as e:
                # 门禁本身崩了：保留原 item
                self.logger.error(f"gate pipeline error: {e}")
                out.append(item)
                continue

            # 写回 quality_score / quality_flags / quality_checked_at
            out.append(
                item.model_copy(
                    update={
                        "quality_score": presult.final_score,
                        "quality_flags": presult.final_flags,
                        "quality_checked_at": _now_utc(),
                    }
                )
            )
        return out

    # ------------------------------------------------------------------
    # Phase 0.5 (Crawler v2): 旁路写入 quality_rejection_log
    # ------------------------------------------------------------------
    def _write_quality_rejection(
        self,
        item: HotspotItem,
        rejected_by: str,
        reason: str,
    ) -> None:
        """旁路写入 quality_rejection_log 表。

        记录被质量门禁拒绝的条目，用于审计视图。
        不阻塞主流程，失败只打 warning。

        Args:
            item: 被拒绝的 HotspotItem。
            rejected_by: gate 名称。
            reason: 拒绝原因描述。
        """
        try:
            from backend.repository.db import get_connection

            conn = get_connection()
            conn.execute(
                """
                INSERT INTO quality_rejection_log
                    (source_id, item_title, item_url, rejected_by, reason, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    item.source or "",
                    item.title[:500] if item.title else "",
                    str(item.url) if item.url else "",
                    rejected_by,
                    reason[:500],
                ),
            )
        except Exception as e:
            self.logger.warning(f"quality_rejection_log write skipped: {e}")


__all__ = ["QualityGatesMixin"]
