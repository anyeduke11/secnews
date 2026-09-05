"""ProviderHealth — LLM provider 健康度唯一计数/判定源 (v0.8.1 Day 2)。

V0.8.1_PRD v1.0 §2.2 / V0.8.1_PLAN v1.2 §2.2 定稿契约:

- **单一真相源** (prd-iterative 审查 P0-1): 全部失败记账与"不健康"判定都在
  此处; CircuitBreaker (Day 1) 只做薄状态机, ``trip()`` 由本模块判定驱动。
- **判定只用 5min 窗口**; 1min / 1h 仅为 /api/llm/health 展示段 (审查 P2-1)。
- **min_samples 防单发误熔断** (审查批判性补强): 样本数不足时永不判不健康 —
  否则 1 次失败 = 100% 失败率, 单发抖动即熔断 (PRD §9 风险表)。
- 进程内 deque, **不持久化** — 重启清零, 重启后最多再失败 N 次即重 OPEN
  (可接受语义, PRD §9 明示)。
- 线程安全: 单把 ``threading.Lock``; breaker 操作在锁外 (breaker 自带锁,
  判定→trip 的竞态由 trip 的 no-op 语义吸收)。
- **驱动 breaker**: ``record(fail)`` 且判定不健康 → 自动 ``trip()``;
  ``record(ok)`` 且 breaker 处于 half_open (探针成功) → ``reset()``;
  窗口自行恢复**不**自动闭合 breaker — 恢复必须经探针 (PRD F3)。

环境变量 (裁决点 D3, 演练后校准):
- ``HOTSPOT_BREAKER_FAILURE_THRESHOLD``  5min 失败率阈值, 默认 0.5 (">50%")
- ``HOTSPOT_BREAKER_MIN_SAMPLES``        判定最小样本数, 默认 4
- ``HOTSPOT_BREAKER_RECOVERY_TIMEOUT``   breaker OPEN 时长秒, 默认 30

per-provider 覆盖 (v0.8.2 X-B1, v0.8.1 PRD §7 推迟项偿还):
- ``config/llm.yaml`` 的 ``providers.<name>.breaker.{failure_threshold,
  min_samples, recovery_timeout}`` 覆盖该 provider 的全局阈值
- 解析链: **provider yaml > env 全局 > 内建默认** (特异性优先);
  未声明字段沿用全局; yaml 读取失败静默降级为纯 env (LLM 主链不受观测配置拖垮)
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Callable

from loguru import logger as _logger

from backend.utils.circuit_breaker import CircuitBreaker

_WINDOW_DISPLAY = (60.0, 300.0, 3600.0)  # 1min / 5min(判定) / 1min 展示段
_RETENTION_SECONDS = 3600.0  # 最长保留 1h, 之外逐出
_THRESHOLD_RELOAD_TTL = 5.0  # v0.8.2 Y-A2: 阈值热重载 TTL (info_filter 模式)

DEFAULT_FAILURE_THRESHOLD = 0.5
DEFAULT_MIN_SAMPLES = 4
DEFAULT_RECOVERY_TIMEOUT = 30.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v >= 0 else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return v if v >= 0 else default


def _audit_transition(provider: str, pre: str, post: str, reason: str) -> None:
    """breaker 状态迁移 → audit_log (PRD §2.2 可观测: 迁移 100% 留痕)。"""
    try:
        from backend.observability_records import record_audit
        record_audit(
            actor="system",
            action="llm_breaker.transition",
            target=provider,
            detail={"from": pre, "to": post, "reason": reason},
        )
    except Exception as exc:  # pragma: no cover - 防御性
        _logger.warning(f"breaker audit failed (ignored): {exc}")


class ProviderHealth:
    """per-provider 滑动窗口 + 唯一"不健康"判定 + breaker 驱动。"""

    def __init__(
        self,
        failure_threshold: float = DEFAULT_FAILURE_THRESHOLD,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT,
        clock: Callable[[], float] | None = None,
        per_provider: dict[str, dict[str, float]] | None = None,
        reload_thresholds: bool = False,
    ) -> None:
        if not 0 < failure_threshold <= 1:
            raise ValueError("failure_threshold 必须在 (0, 1]")
        if min_samples < 1:
            raise ValueError("min_samples 必须 >= 1")
        self._failure_threshold = float(failure_threshold)
        self._min_samples = int(min_samples)
        self._recovery_timeout = float(recovery_timeout)
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        # provider -> deque[(ts, ok)]；仅保留 RETENTION_SECONDS 内样本
        self._windows: dict[str, deque] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        # v0.8.2 Y-A2: 阈值热重载状态 (5s TTL + config 对象身份比对)。
        # 仅单例 (yaml-backed) 开启 — 直接构造 (测试/DI) 的合成 overrides 不被覆盖。
        self._overrides = self._normalize_overrides(per_provider or {})
        self._reload_enabled = reload_thresholds
        self._thresholds_checked_at: float = 0.0
        self._last_overrides: dict[str, dict[str, float]] = dict(self._overrides)

    @staticmethod
    def _normalize_overrides(
        per_provider: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """非法覆盖条目跳过不抛 — LLM 主链不因观测配置炸 (与 record 防御一致)。"""
        out: dict[str, dict[str, float]] = {}
        for prov, ov in per_provider.items():
            clean: dict[str, float] = {}
            ft = ov.get("failure_threshold")
            ms = ov.get("min_samples")
            rt = ov.get("recovery_timeout")
            if ft is not None:
                if 0 < ft <= 1:
                    clean["failure_threshold"] = float(ft)
                else:
                    _logger.warning(f"provider_health: {prov} failure_threshold={ft} 非法, 忽略")
            if ms is not None:
                if int(ms) >= 1:
                    clean["min_samples"] = int(ms)
                else:
                    _logger.warning(f"provider_health: {prov} min_samples={ms} 非法, 忽略")
            if rt is not None:
                if rt > 0:
                    clean["recovery_timeout"] = float(rt)
                else:
                    _logger.warning(f"provider_health: {prov} recovery_timeout={rt} 非法, 忽略")
            if clean:
                out[prov] = clean
        return out

    def maybe_reload_thresholds(self) -> None:
        """v0.8.2 Y-A2: llm.yaml per-provider 阈值热重载 (5s TTL)。

        只换判定参数, **窗口与 breaker 状态原样保留** (在跑的健康历史不属于
        配置); 判定/熔断语义立即按新阈值生效。yaml 解析在锁外, 换值在锁内
        (record 的记账锁段会读 _overrides)。
        仅单例 (reload_thresholds=True, yaml-backed) 生效。
        """
        if not self._reload_enabled:
            return
        now = self._clock()
        if now - self._thresholds_checked_at < _THRESHOLD_RELOAD_TTL:
            return
        fresh = self._normalize_overrides(_load_yaml_breaker_overrides())
        with self._lock:
            self._thresholds_checked_at = now
            if fresh != self._last_overrides:
                self._overrides = fresh
                self._last_overrides = dict(fresh)
                _logger.info(f"provider 阈值热重载: {sorted(fresh) or '无 per-provider 覆盖'}")

    # ------------------------------------------------------------------
    # 内部 (调用方须已持锁)
    # ------------------------------------------------------------------
    def _evict_locked(self, dq: deque, now: float) -> None:
        while dq and now - dq[0][0] > _RETENTION_SECONDS:
            dq.popleft()

    def _rate_locked(self, dq: deque, now: float, window: float) -> tuple[int, int, float]:
        total = failures = 0
        for ts, ok in reversed(dq):
            if now - ts > window:
                break  # deque 按 ts 递增, 从新到旧, 出窗即止
            total += 1
            failures += 0 if ok else 1
        rate = failures / total if total else 0.0
        return total, failures, rate

    def _unhealthy_locked(self, dq: deque, now: float, provider: str = "") -> bool:
        total, failures, _ = self._rate_locked(dq, now, 300.0)
        ov = self._overrides.get(provider, {})
        threshold = ov.get("failure_threshold", self._failure_threshold)
        min_samples = int(ov.get("min_samples", self._min_samples))
        if total < min_samples:
            return False
        return failures / total > threshold

    def _get_breaker_locked(self, provider: str) -> CircuitBreaker:
        breaker = self._breakers.get(provider)
        if breaker is None:
            recovery = self._overrides.get(provider, {}).get(
                "recovery_timeout", self._recovery_timeout
            )
            breaker = CircuitBreaker(recovery_timeout=recovery, clock=self._clock)
            self._breakers[provider] = breaker
        return breaker

    def _effective_thresholds(self, provider: str) -> dict[str, float | int]:
        """单 provider 生效阈值 (yaml 覆盖优先) — snapshot 暴露用。"""
        ov = self._overrides.get(provider, {})
        return {
            "failure_threshold": ov.get("failure_threshold", self._failure_threshold),
            "min_samples": int(ov.get("min_samples", self._min_samples)),
            "recovery_timeout": ov.get("recovery_timeout", self._recovery_timeout),
        }

    # ------------------------------------------------------------------
    # 公有 API
    # ------------------------------------------------------------------
    def record(self, provider: str, ok: bool) -> None:
        """记账一次 provider 调用结果, 并驱动 breaker (判定→trip / 探针成功→reset)。

        永不抛异常 — 记账失败只告警 (调用路径在 LLM 主链上, 不因观测拖垮业务)。
        """
        self.maybe_reload_thresholds()  # v0.8.2 Y-A2: 阈值 5s TTL 热重载
        now = self._clock()
        breaker: CircuitBreaker | None = None
        unhealthy = False
        try:
            with self._lock:
                dq = self._windows.setdefault(provider, deque())
                dq.append((now, ok))
                self._evict_locked(dq, now)
                unhealthy = self._unhealthy_locked(dq, now, provider)
                breaker = self._get_breaker_locked(provider)
        except Exception as exc:  # pragma: no cover - 防御性
            _logger.warning(f"provider_health record failed (ignored): {exc}")
            return
        # breaker 自带锁, 判定→trip 的竞态由 trip 的 no-op 语义吸收;
        # 最后写者赢的 reset/trip 交错由下一轮 record 再纠正。
        try:
            if breaker is None:
                return
            pre = breaker.state
            reason = ""
            if not ok:
                if breaker.state == "half_open":
                    # 探针失败 → 立即重回 OPEN (PRD F3)。探针结果本身即判定,
                    # 不等 5min 窗口 — 否则窗口样本 < min_samples 时探针失败
                    # 无法 trip, breaker 卡 half_open 直到滞留超时。
                    breaker.trip()
                    reason = "probe_failed"
                elif unhealthy:
                    breaker.trip()
                    reason = "window_verdict"
            elif ok and breaker.state == "half_open":
                breaker.reset()  # 探针成功
                reason = "probe_success"
            if reason and breaker.state != pre:
                _audit_transition(provider, pre, breaker.state, reason)
        except Exception as exc:  # pragma: no cover - 防御性
            _logger.warning(f"provider_health breaker drive failed (ignored): {exc}")

    def is_unhealthy(self, provider: str) -> bool:
        """5min 窗口判定 (唯一真相源)。样本 < min_samples 恒 False。"""
        now = self._clock()
        with self._lock:
            dq = self._windows.get(provider)
            if not dq:
                return False
            return self._unhealthy_locked(dq, now, provider)

    def get_breaker(self, provider: str) -> CircuitBreaker:
        """per-provider breaker (懒创建复用; gateway 调用前 allow() 检查用)。"""
        with self._lock:
            return self._get_breaker_locked(provider)

    def snapshot(self, provider: str) -> dict:
        """单 provider 快照 — /api/llm/health (Day 4) 输出体。"""
        now = self._clock()
        with self._lock:
            dq = self._windows.get(provider)
            windows = {}
            for w in _WINDOW_DISPLAY:
                total, failures, rate = self._rate_locked(dq, now, w) if dq else (0, 0, 0.0)
                key = f"{int(w // 60)}m"
                windows[key] = {
                    "total": total,
                    "failures": failures,
                    "failure_rate": round(rate, 4),
                }
            breaker = self._get_breaker_locked(provider)
            unhealthy = self._unhealthy_locked(dq, now, provider) if dq else False
        return {
            "provider": provider,
            "windows": windows,
            "unhealthy": unhealthy,
            "breaker": breaker.snapshot(),
            # v0.8.2 X-B1: 生效阈值 (yaml per-provider > env 全局 > 内建默认)
            "thresholds": self._effective_thresholds(provider),
        }

    def snapshot_all(self) -> dict[str, dict]:
        """全 provider 快照 (含仅 trip 过但尚无记录的 provider 不出现)。"""
        with self._lock:
            providers = sorted(self._windows.keys())
        return {p: self.snapshot(p) for p in providers}


# ---------------------------------------------------------------------------
# 模块级单例 (对齐 trigger_webhook_api 的 wh_mod._default 可测性模式)
# ---------------------------------------------------------------------------
_default: ProviderHealth | None = None


def _load_yaml_breaker_overrides() -> dict[str, dict[str, float]]:
    """llm.yaml per-provider breaker 阈值 (v0.8.2 X-B1)。

    任何失败 (文件缺失/校验错/读盘异常) 都静默降级为空表 — 观测配置
    永不拖垮 LLM 主链; pydantic 已挡住非法值, 这里再兜一层防御。
    """
    try:
        from backend.config.llm_schema import load_llm_config

        cfg = load_llm_config()
    except Exception as exc:
        _logger.warning(f"provider_health: llm.yaml 读取失败, per-provider 阈值降级为 env 全局 ({exc})")
        return {}
    if cfg is None:
        return {}
    out: dict[str, dict[str, float]] = {}
    for name, pc in cfg.providers.items():
        if pc.breaker is None:
            continue
        ov: dict[str, float] = {}
        if pc.breaker.failure_threshold is not None:
            ov["failure_threshold"] = float(pc.breaker.failure_threshold)
        if pc.breaker.min_samples is not None:
            ov["min_samples"] = int(pc.breaker.min_samples)
        if pc.breaker.recovery_timeout is not None:
            ov["recovery_timeout"] = float(pc.breaker.recovery_timeout)
        if ov:
            out[name] = ov
    return out


def get_provider_health() -> ProviderHealth:
    """进程级单例 (懒创建, env + llm.yaml 参数只读一次)。gateway/image 接入 (Day 3) 用此。"""
    global _default
    if _default is None:
        _default = ProviderHealth(
            failure_threshold=_env_float("HOTSPOT_BREAKER_FAILURE_THRESHOLD", DEFAULT_FAILURE_THRESHOLD),
            min_samples=_env_int("HOTSPOT_BREAKER_MIN_SAMPLES", DEFAULT_MIN_SAMPLES),
            recovery_timeout=_env_float("HOTSPOT_BREAKER_RECOVERY_TIMEOUT", DEFAULT_RECOVERY_TIMEOUT),
            per_provider=_load_yaml_breaker_overrides(),
            reload_thresholds=True,
        )
    return _default


def reset_provider_health() -> None:
    """测试/运维复位单例 (下一 get 重建)。"""
    global _default
    _default = None
