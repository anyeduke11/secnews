"""场景 fallback 权重表 — v0.8.1 Day 4 (CRITICAL_REVIEW §2.1 "场景感知"支柱)。

PRD §2.2: deep/light/image 三档各自 fallback 顺序; health 数据作为排序输入。

- **仅 deep 场景重排** (质量感知: sensenova → anthropic → openai → qwen →
  ollama); light (评分/摘要/NER 热路径) 保持配置 fallback_order — 既有行为
  零变化, 爆炸半径最小; image 为单 provider 直连 (见 image_service), 无链可排。
- **health 作为排序输入的实现方式**: 权重只决定"尝试偏好顺序", OPEN 的
  provider 由 gateway 循环头的 breaker 检查跳过 (Day 3) — 两者叠加即
  "健康感知的场景降级": primary OPEN → 按场景质量偏好逐个尝试其余。
- 权重表外 provider (配置了但不在表内) 保持相对顺序缀尾 — 不丢配置。
"""
from __future__ import annotations

SCENARIO_FALLBACK_WEIGHTS: dict[str, list[str] | None] = {
    "deep": ["sensenova", "anthropic", "openai", "qwen", "ollama"],
    "light": None,
    "image": None,
}

_DEEP_TASKS = frozenset({"deep_read", "deep"})


def task_to_scenario(task: str) -> str:
    """task_attr → 场景 (deep/light); 未知任务一律 light (保守)。"""
    return "deep" if task in _DEEP_TASKS else "light"


def scenario_fallback_order(task: str, base_order: list[str]) -> list[str]:
    """按场景权重稳定重排 fallback 尝试顺序。

    - light (默认): 原样返回 — 既有调用顺序零变化;
    - deep: base_order 中命中权重表的 provider 按权重升序, 表外缀尾;
    - 稳定排序保证同 rank 不换位。
    """
    weights = SCENARIO_FALLBACK_WEIGHTS.get(task_to_scenario(task))
    if not weights:
        return base_order
    rank = {p: i for i, p in enumerate(weights)}
    known = sorted((p for p in base_order if p in rank), key=lambda p: rank[p])
    unknown = [p for p in base_order if p not in rank]
    return known + unknown
