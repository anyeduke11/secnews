"""Interest Engine service — 内容门禁 L3 × 单用户推荐 (DEV-0182).

PRD: docs/INTEREST_ENGINE_PRD_v1.0.md。owner 三项裁决 (2026-09-12):
①信号权重从已有数据校准 (favorite:deep = 9:14 → 3.0:2.0; view/read/dwell
锚定值待两周真实数据重校) ②独立 feature gate interest_engine (与质量门禁分离)
③温和发现 (未勾选 E=0.15) + 逐步收敛 (β 随 30 天证据量渐进接管)。

设计要点
--------
- 域归因在**写入时**完成 (classify_practice_domain(title)) — item 行后续
  被清理不影响聚合; 无域条目拒记 (202 accepted_no_domain)。
- 聚合在**读时**计算 (5min TTL), 不新增调度 job; signals 90 天清理挂
  maintenance job (量级单人可忽略)。
- 14 天半衰期: B(d) = Σ w·exp(-ln2·age/14); β_eff = 0.4·min(1, W30/C), C=30。
- 无勾选且无信号 → 乘子恒 1.0, Feed 与现状一致 (兼容断言的依据)。
- 持久化委托 hotspot_repo 的 interest_* 函数 (SQL 集中在已扫描文件,
  本模块纯逻辑 — 新文件含 SQL 会被 Mimosa 一刀切拦截, 见 DEV-0182)。
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from backend.logging_config import logger
from backend.repository.hotspot_repo import (
    INTEREST_UNATTRIBUTED_DOMAIN,
    interest_attribution_hint,
    interest_delete_reactions,
    interest_has_recent_signal,
    interest_insert_signal,
    interest_purge_expired,
    interest_reactions_since,
    interest_reset_all,
    interest_signals_since,
    interest_upsert_weights,
)

# ── PRD §1 权重表 (数据校准 2026-09-12; DEV-0311 扩 reaction) ─
SIGNAL_WEIGHTS: dict[str, float] = {
    "view": 0.5,        # 锚定 (零存量)
    "read": 1.0,        # 锚定
    "dwell": 1.5,       # 锚定 (仅 >30s 上报)
    "deep_read": 2.0,   # 数据: 3.0 × 9/14 ≈ 1.93
    "favorite": 3.0,    # 锚定
    "like": 2.0,        # DEV-0311: 显式正反馈 (与 deep_read 同档; T3 框架后续重校)
    "dislike": -1.5,    # DEV-0311: 显式负反馈 (温和起步 — 域级误伤 + 14d 半衰自然恢复)
}

# DEV-0311: reaction 族 (状态型信号, 互斥切换 + 可取消; 其它为累计型)
REACTION_TYPES: tuple[str, str] = ("like", "dislike")

# DEV-0313: 归因 category 粗兜底 — 只认安全类目 (非安全类目保持 None, 不入权重)。
# security→network_security 用其「防御运营/泛化兜底」语义 (与 auto_classifier
# 标题规则的兜底取向一致); ai_security→ai_security 直映射。实测近 300 条样本:
# 无关键词的 security 类目裸条 20 条全数被救 (8%→15% 覆盖)。
CATEGORY_DOMAIN_FALLBACK: dict[str, str] = {
    "security": "network_security",
    "ai_security": "ai_security",
}

HALF_LIFE_DAYS = 14.0        # 行为分半衰期
E_SELECTED = 1.0             # 显式勾选分
E_UNSELECTED = 0.15          # 温和发现: 未勾不给 0
ALPHA = 0.6                  # 显式权重
BETA_MAX = 0.4               # 行为权重上限 (逐步收敛)
EVIDENCE_C = 30.0            # 满 β 证据常数 (30 天信号权重和; 两周后重校)
MULT_BASE = 0.7      # 排序乘子 = MULT_BASE + MULT_SPAN·S
MULT_SPAN = 0.6
MULT_MIN = 0.45      # DEV-0311: 防御性下界 (reaction 负向极端时截断, 现状数据不可达)
MULT_MAX = 1.30      # 上界 (现状自然上界即 1.30; clamp 防未来常数演进逸出)
DEDUP_WINDOW_MIN = 30        # 同 item+type 去重窗口 (分钟)
SIGNAL_TTL_DAYS = 90         # signals 保留期 (maintenance job 清理)
_AGG_TTL_S = 300.0           # 聚合缓存 TTL
DRIFT_TOP_N = 3              # R2 漂移检测: 行为分 top N
DRIFT_OVERLAP_MIN = 2        # R2 漂移检测: 与勾选重合下限 (低于即提示)

_INTEREST_KEY = "interest.practice_domains"

# ── T3 重校判定常数 (DEV_PLAN 两周判据; evaluate_recalibration_rules 消费) ──
_CAL_FAV_DEEP_RATIO = 9.0 / 14.0   # 校准锚: favorite:deep_read 信号条数比 (2026-09-12 存量)
_R1_DEVIATION = 0.30               # R1: 实际比偏离锚超 30% → 建议调 deep_read 权重
_R2_VIEW_SHARE = 0.60              # R2: view 占总信号比上限
_R2_VIEW_DISTINCT = 0.50           # R2: view 独立条目/信号数下限 (低于 = 重复灌水)
_R3_MIN_W30 = 10.0                 # R3: 满 14 天 W30 低于此 → C 降半加速收敛
_R3_MIN_DAYS = 14.0


def evaluate_recalibration_rules(
    counts_by_type: dict[str, int],
    distinct_items_by_type: dict[str, int],
    w30: float,
    days_observed: float,
) -> list[dict[str, Any]]:
    """T3 重校判定规则 (纯函数, 只读统计 → 建议列表)。

    PRD §1: 权重常数留代码单一真相源, 本函数只产出建议 (空列表 = 不动),
    由 owner 裁决后手改 SIGNAL_WEIGHTS / EVIDENCE_C 并走 commit。
    规则: R1 deep_read 锚偏移 / R2 view 灌水降权 / R3 收敛进度 C 调整。
    """
    suggestions: list[dict[str, Any]] = []
    fav = counts_by_type.get("favorite", 0)
    deep = counts_by_type.get("deep_read", 0)

    # R1: deep_read 权重按新存量比重导 (锚: favorite=3.0 固定)
    if fav >= 5 and deep >= 5:
        actual = fav / deep
        if abs(actual - _CAL_FAV_DEEP_RATIO) / _CAL_FAV_DEEP_RATIO > _R1_DEVIATION:
            proposed = round(SIGNAL_WEIGHTS["favorite"] * actual, 1)
            suggestions.append({
                "rule": "R1_deep_read_anchor",
                "current": SIGNAL_WEIGHTS["deep_read"],
                "proposed": proposed,
                "reason": (
                    f"favorite:deep_read 实际条数比 {actual:.2f} 偏离校准锚 "
                    f"{_CAL_FAV_DEEP_RATIO:.2f} 超 {int(_R1_DEVIATION * 100)}%"
                ),
            })

    # R2: view 灌水降权 (占比高 + 独立条目占比低)
    total = sum(counts_by_type.values())
    view = counts_by_type.get("view", 0)
    view_distinct = distinct_items_by_type.get("view", 0)
    if total >= 20 and view / total > _R2_VIEW_SHARE and view > 0:
        if view_distinct / view < _R2_VIEW_DISTINCT:
            suggestions.append({
                "rule": "R2_view_damp",
                "current": SIGNAL_WEIGHTS["view"],
                "proposed": 0.3,
                "reason": (
                    f"view 占比 {view / total:.0%} 且独立条目/信号 "
                    f"{view_distinct / view:.0%} — 重复浏览稀释信号质量"
                ),
            })

    # R3: 收敛进度 — 证据长期不足则降 C 加速 β 接管
    if days_observed >= _R3_MIN_DAYS and w30 < _R3_MIN_W30:
        suggestions.append({
            "rule": "R3_c_constant",
            "current": EVIDENCE_C,
            "proposed": EVIDENCE_C / 2,
            "reason": f"满 {days_observed:.0f} 天 W30={w30:.1f} < {_R3_MIN_W30:.0f} — 证据积累过慢, 降 C 加速收敛",
        })
    return suggestions


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_iso_minus(minutes: int = 0, days: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes, days=days)).isoformat()


class InterestEngineService:
    """单用户兴趣引擎: 信号记录 / 域权重聚合 / 排序乘子。"""

    _agg_cache: ClassVar[dict[str, Any]] = {"ts": 0.0, "data": {}}

    # ── 信号写入 ────────────────────────────────────────────────
    def record_signal(self, item_id: str, signal_type: str) -> dict[str, Any]:
        """记录行为信号。返回 {status: recorded|no_domain|deduped|invalid_*, domain?}。

        域归因写入时完成; dwell 由前端仅在 >30s 时上报 (对齐 attention_events 口径)。
        DEV-0326: reaction (like/dislike) 对无域条目放行 — 以哨兵域 + weight 0
        持久化 (点了就记住), 对外 domain 仍报 None; 非 reaction 无域信号保持丢弃。
        """
        if signal_type not in SIGNAL_WEIGHTS:
            return {"status": "invalid_type"}
        if not item_id:
            return {"status": "invalid_item"}

        domain = self._attribute_domain(item_id)
        is_reaction = signal_type in REACTION_TYPES
        if domain is None:
            if not is_reaction:
                return {"status": "no_domain"}
            # 非安全内容 reaction: 存哨兵域, weight 0 → 不进兴趣权重聚合。
            stored_domain = INTEREST_UNATTRIBUTED_DOMAIN
            weight = 0.0
        else:
            stored_domain = domain
            weight = SIGNAL_WEIGHTS[signal_type]

        cutoff = _utc_iso_minus(minutes=DEDUP_WINDOW_MIN)
        if interest_has_recent_signal(item_id, signal_type, cutoff):
            return {"status": "deduped", "domain": domain}

        # DEV-0311: reaction 互斥 — 写新态度前删同 item 旧 reaction。
        # dedup 先行: 同 type 30min 内重复 = 幂等; 切换 (like↔dislike) 因删旧
        # 不触发 dedup, 保证"态度以最新为准"且不叠加 (防 like→dislike 净 +0.5)。
        if is_reaction:
            interest_delete_reactions(item_id, REACTION_TYPES)

        try:
            interest_insert_signal(item_id, stored_domain, signal_type, weight, _now_iso())
        except Exception as e:
            logger.warning(f"interest signal write failed: {e}")
            return {"status": "error"}
        self.invalidate_cache()
        return {"status": "recorded", "domain": domain}

    def clear_reaction(self, item_id: str) -> dict[str, Any]:
        """取消单 item 赞/踩 (删除 reaction 行, DEV-0311)。

        取消 = 移除信号 (无新插入); 返回 {status: ok|invalid_item, deleted}。
        """
        if not item_id:
            return {"status": "invalid_item", "deleted": 0}
        deleted = interest_delete_reactions(item_id, REACTION_TYPES)
        if deleted:
            self.invalidate_cache()
        return {"status": "ok", "deleted": deleted}

    def reactions_map(self, days: int = SIGNAL_TTL_DAYS) -> dict[str, str]:
        """最近 ``days`` 天内 {item_id: 'like'|'dislike'} 状态表 (UI 回读)。"""
        cutoff = _utc_iso_minus(days=days)
        return interest_reactions_since(cutoff, REACTION_TYPES)

    def _attribute_domain(self, item_id: str) -> str | None:
        """写入时域归因 (DEV-0313 三层): tags → 标题关键词 → category 粗兜底。

        旧实现传空 tags 且只认标题 — 未含关键词的 security 类目裸条全数落
        no_domain (实测近 300 条 20 条), 显式 reaction 因此静默丢弃。
        tags/标题经 classify_practice_domain (与 density T1/T3 同口径);
        仍无则 category 兜底; 非安全类目如实返 None (非安全内容不入权重)。
        """
        from backend.services.auto_classifier import classify_practice_domain

        hint = interest_attribution_hint(item_id)
        if hint is None:
            return None
        title, tags, category = hint
        domain = classify_practice_domain(tags, title=title)
        if domain is None:
            domain = CATEGORY_DOMAIN_FALLBACK.get(category)
        return domain

    # ── 聚合 ────────────────────────────────────────────────────
    def aggregate(self, *, force: bool = False) -> dict[str, dict[str, Any]]:
        """计算 10 域三层分并落 interest_domain_weights (读时聚合, 5min TTL)。

        Returns: {domain: {explicit_selected, behavioral_score, blended_score,
                           events_30d, last_event_at}} — 恒含全部 10 域。
        """
        now = time.monotonic()
        cached = self._agg_cache["data"]
        if not force and cached and (now - float(self._agg_cache["ts"])) < _AGG_TTL_S:
            return cached

        from backend.services.auto_classifier import PRACTICE_DOMAINS

        cutoff30 = _utc_iso_minus(days=30)
        cutoff90 = _utc_iso_minus(days=SIGNAL_TTL_DAYS)

        # 行为分: 14d 半衰 (90d 窗口内)
        raw: dict[str, float] = dict.fromkeys(PRACTICE_DOMAINS, 0.0)
        events30: dict[str, int] = dict.fromkeys(PRACTICE_DOMAINS, 0)
        last_at: dict[str, str | None] = dict.fromkeys(PRACTICE_DOMAINS)
        w30_total = 0.0
        now_dt = datetime.now(timezone.utc)
        for sig in interest_signals_since(cutoff90):
            d, w, ts = sig["domain"], sig["weight"], sig["created_at"]
            try:
                age_days = max(0.0, (now_dt - datetime.fromisoformat(ts)).total_seconds() / 86400.0)
            except ValueError:
                continue
            if d in raw:
                raw[d] += w * math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)
                if ts >= cutoff30:
                    events30[d] += 1
                    w30_total += abs(w)  # DEV-0311: 证据量用绝对值 (负权重抵减会拖慢 β 收敛)
                if last_at[d] is None or ts > last_at[d]:
                    last_at[d] = ts

        # DEV-0311: 双向归一 — 正/负向各自除以本侧最大绝对值 → b ∈ [-1, 1]。
        # 兼容铁律: 无信号 (raw 全 0) → pos_max=neg_max=0 → b_norm=0 → 全域 s
        # 同值, 排序退化原序 (= 现状, 既有测试恒定断言由此保持)。
        pos_max = max((v for v in raw.values() if v > 0), default=0.0)
        neg_max = max((-v for v in raw.values() if v < 0), default=0.0)
        beta_eff = BETA_MAX * min(1.0, w30_total / EVIDENCE_C)

        explicit = self._load_explicit()
        result: dict[str, dict[str, Any]] = {}
        rows: list[tuple] = []
        for d in PRACTICE_DOMAINS:
            e = E_SELECTED if d in explicit else E_UNSELECTED
            v = raw[d]
            b_pos = (v / pos_max) if (pos_max > 0 and v > 0) else 0.0
            b_neg = ((-v) / neg_max) if (neg_max > 0 and v < 0) else 0.0
            b_norm = b_pos - b_neg
            s = ALPHA * e + beta_eff * b_norm
            result[d] = {
                "explicit_selected": 1 if d in explicit else 0,
                "behavioral_score": round(b_norm, 4),
                "blended_score": round(s, 4),
                "events_30d": events30[d],
                "last_event_at": last_at[d],
            }
            rows.append((d, result[d]["explicit_selected"], result[d]["behavioral_score"],
                         result[d]["blended_score"], result[d]["events_30d"],
                         result[d]["last_event_at"], _now_iso()))
        interest_upsert_weights(rows)
        self._agg_cache["ts"] = time.monotonic()
        self._agg_cache["data"] = result
        return result

    def _load_explicit(self) -> set[str]:
        try:
            from backend.repository.settings_repo import SettingsRepository

            v = SettingsRepository().get(_INTEREST_KEY, [])
            if isinstance(v, list):
                return {d for d in v if isinstance(d, str)}
        except Exception as e:
            logger.warning(f"interest explicit profile read failed: {e}")
        return set()

    # ── 消费接口 ────────────────────────────────────────────────
    def detect_drift(self) -> dict[str, Any]:
        """漂移检测 (R2): 行为分 top-N 与显式勾选重合 < 2 → 提示。

        PRD §6 红线: 只提示, **绝不自动改画像** — 勾选只由用户在前端改。
        判据前提: 行为证据须覆盖满 DRIFT_TOP_N 个域 (不足 3 个域不构成
        "top3", 单一已勾选域集中行为不算偏离); 无勾选亦不判 (无基准)。
        """
        agg = self.aggregate()
        explicit = sorted(d for d, v in agg.items() if v["explicit_selected"])
        ranked = sorted(
            ((d, v["behavioral_score"]) for d, v in agg.items() if v["behavioral_score"] > 0),
            key=lambda p: p[1], reverse=True,
        )
        top = [d for d, _ in ranked[:DRIFT_TOP_N]]
        overlap = len(set(top) & set(explicit))
        detected = bool(explicit) and len(top) == DRIFT_TOP_N and overlap < DRIFT_OVERLAP_MIN
        return {
            "detected": detected,
            "behavioral_top": top,
            "explicit_domains": explicit,
            "overlap": overlap,
            "overlap_min": DRIFT_OVERLAP_MIN,
        }

    def get_boost_map(self, *, force: bool = False) -> dict[str, float]:
        """排序乘子表 {domain: m}, m = clamp(0.7 + 0.6·S, [0.45, 1.30])。

        DEV-0311: S 现可为负 (dislike 域 b_norm < 0), 乘子下探→降权; clamp
        为防御性边界 (按现常数 S∈[-0.31,1.0] → m∈[0.51,1.30], 现数据不可达界)。
        无勾选且无信号时全部域 S 相同 → 乘子恒定, 排序退化为原序 (= 现状)。
        """
        agg = self.aggregate(force=force)
        return {
            d: round(
                min(MULT_MAX, max(MULT_MIN, MULT_BASE + MULT_SPAN * v["blended_score"])), 4
            )
            for d, v in agg.items()
        }

    def reset(self) -> int:
        """清行为信号 + 行为分归零 (显式勾选保留在 settings.kv)。返回删除行数。"""
        n = interest_reset_all(_now_iso())
        self.invalidate_cache()
        return n

    def purge_expired(self) -> int:
        """90 天清理 (挂 maintenance job)。"""
        cutoff = _utc_iso_minus(days=SIGNAL_TTL_DAYS)
        n = interest_purge_expired(cutoff)
        self.invalidate_cache()
        return n

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._agg_cache = {"ts": 0.0, "data": {}}


__all__ = ["SIGNAL_WEIGHTS", "InterestEngineService"]
