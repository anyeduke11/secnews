"""自动入管规则引擎 — 高价值资讯自动进入 KL 管线 (2026-09-26)。

设计稿: ``docs/superpowers/specs/2026-09-26-auto-intake-design.md`` §3。
入管判据 (owner 裁决 B 方案): quality_score ≥ 阈值 **且** (可选) 命中关注域
**且** 每日限量。收藏通道不变 (source='secnews' vs 'secnews_auto' 区分,
收藏不占每日上限)。不新增 feature gate — 开关即 kv ``knowledge.auto_intake.enabled``。

评估挂 collect_all_job 尾部 (30min 一轮, 六步):
1. enabled=false → return
2. 今日已入管 ≥ daily_limit → return (计数 = 实时 COUNT knowledge_items
   WHERE source='secnews_auto' AND ingested_at ≥ 今日 0 点 — 实现简且重启安全)
3. 候选 = hotspots WHERE ingested_at > kv 游标 AND quality_score ≥ 阈值
   AND summary 非空, ORDER BY quality_score DESC LIMIT 余量
   (首跑游标 = 当前时刻, 不回填历史 — design §6 非目标)
4. require_domain_hit 时 batch_classify 规则现算 practice_domain
   (无 LLM), 命中 interest.practice_domains 才入管; 未命中跳过
   (空画像 = 无偏好不过滤 — interest 系统一贯语义, 先例 hotspots 加权/M_i)
5. 入管 = promote_favorite_to_knowledge 扩展版 (md 先写, url 幂等,
   带 content=summary / category / source='secnews_auto')
6. 游标推进到本轮 max(ingested_at) (含跳过条目 — 不重扫)

全程 try-except 包裹不抛 (job 安全, 不阻塞采集主流程)。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.settings_repo import SettingsRepository
from backend.services.settings_service import SettingsService

log = logging.getLogger("hotspot.auto_intake")

# 自动入管来源通道 (区分收藏通道 'secnews'; 亦为每日上限的 COUNT 口径)
AUTO_SOURCE = "secnews_auto"
# kv 游标: 存上一轮 max(ingested_at), 防重复扫描
CURSOR_KEY = "knowledge.auto_intake.cursor"
# 关注域画像 (与 /api/settings/interests 同源)
_INTEREST_KEY = "interest.practice_domains"

_DEFAULTS: dict[str, bool | int] = {
    "enabled": False,
    "min_quality_score": 85,
    "daily_limit": 20,
    "require_domain_hit": True,
}


def get_auto_intake_config() -> dict[str, bool | int]:
    """读配置 (kv ``knowledge.auto_intake.*``, 缺省回落默认值)。"""
    svc = SettingsService()
    return {
        key: svc.get(f"knowledge.auto_intake.{key}", default)
        for key, default in _DEFAULTS.items()
    }


def set_auto_intake_config(
    *,
    enabled: bool | None = None,
    min_quality_score: int | None = None,
    daily_limit: int | None = None,
    require_domain_hit: bool | None = None,
    actor: str = "web",
) -> dict[str, bool | int]:
    """部分更新配置 (PATCH 语义); 每键经 SettingsService.set → audit_log。"""
    updates = {
        "enabled": enabled,
        "min_quality_score": min_quality_score,
        "daily_limit": daily_limit,
        "require_domain_hit": require_domain_hit,
    }
    svc = SettingsService()
    for key, value in updates.items():
        if value is None:
            continue
        svc.set(
            f"knowledge.auto_intake.{key}",
            value,
            actor=actor,
            action="auto_intake.config.set",
            target=key,
        )
    return get_auto_intake_config()


def today_intaken_count(now: datetime | None = None) -> int:
    """今日 (本机时区自然日) 已自动入管条数 — 实时 COUNT, 重启安全。"""
    ref = now or datetime.now(timezone.utc)
    local_midnight = ref.astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    since = local_midnight.astimezone(timezone.utc).isoformat()
    return knowledge_repo.count_by_source_since(AUTO_SOURCE, since)


def run_auto_intake() -> dict[str, object]:
    """评估一轮自动入管 (六步, design §3.2); 返回
    {evaluated, intaken, skipped_domain, limit_reached}, 全程不抛。"""
    result: dict[str, object] = {
        "evaluated": 0,
        "intaken": 0,
        "skipped_domain": 0,
        "limit_reached": False,
    }
    try:
        cfg = get_auto_intake_config()
        if not cfg["enabled"]:  # 步骤 1: 总开关
            return result
        # 步骤 2: 每日上限 (防风暴主闸)
        intaken_today = today_intaken_count()
        if intaken_today >= int(cfg["daily_limit"]):
            result["limit_reached"] = True
            return result
        # 步骤 3: 候选查询 (游标防重扫; 首跑游标 = now 不回填历史)
        cursor = SettingsRepository().get(CURSOR_KEY)
        since = str(cursor) if cursor else datetime.now(timezone.utc).isoformat()
        if not cursor:
            SettingsRepository().set(CURSOR_KEY, since)
        candidates = HotspotRepository().candidates_for_auto_intake(
            since=since,
            min_quality_score=int(cfg["min_quality_score"]),
            limit=int(cfg["daily_limit"]) - intaken_today,
        )
        if not candidates:
            return result
        result["evaluated"] = len(candidates)
        # 步骤 4: 域命中过滤 (规则现算, 无 LLM; 空画像 = 不过滤)
        hits: dict[str, str | None] = {}
        want: set[str] = set()
        if cfg["require_domain_hit"]:
            configured = SettingsRepository().get(_INTEREST_KEY, []) or []
            want = set(configured)
            if want:
                from backend.services.auto_classifier import batch_classify

                probes = batch_classify(
                    [
                        {
                            "id": c["id"],
                            "title": c["title"],
                            "tags": c.get("tags") or [],
                            "source_url": c.get("url") or "",
                        }
                        for c in candidates
                    ]
                )
                hits = {p["id"]: p.get("practice_domain") for p in probes}
        # 步骤 5: 逐条入管 (md 先写; url 幂等; 单条失败不中断本轮)
        from backend.services.sag_service import promote_favorite_to_knowledge

        for cand in candidates:
            if want and hits.get(cand["id"]) not in want:
                result["skipped_domain"] += 1
                continue
            try:
                promote_favorite_to_knowledge(
                    title=cand["title"],
                    url=cand["url"],
                    content=cand.get("summary"),
                    category=cand.get("category"),
                    source=AUTO_SOURCE,
                )
                result["intaken"] += 1
            except Exception as e:
                log.warning(f"auto_intake: promote failed for {cand['id']}: {e}")
        # 步骤 6: 游标推进到本轮 max(ingested_at) (含跳过条目 — 不重扫)。
        # min(..., now) 钳制: 脏数据未来时间戳会把游标顶到未来, 合法新条目
        # 在追上之前被静默跳过 — 钳到当前时刻封顶。
        now_iso = datetime.now(timezone.utc).isoformat()
        SettingsRepository().set(
            CURSOR_KEY, min(max(c["ingested_at"] for c in candidates), now_iso)
        )
    except Exception as e:
        log.error(f"run_auto_intake crashed: {e}")
    return result


__all__ = [
    "AUTO_SOURCE",
    "CURSOR_KEY",
    "get_auto_intake_config",
    "run_auto_intake",
    "set_auto_intake_config",
    "today_intaken_count",
]
