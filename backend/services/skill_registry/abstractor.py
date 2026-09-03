"""skill_registry.abstractor — Skill 候选反模式 linter (v0.8 Phase A · A2a).

职责边界 (见 docs/V0.8_SKILL_ABSTRACTION.md §5):
- 本模块只做 **客观信号** 反模式检查, 在 skill 注册流程 (A2b) 前拦截
  "不该抽象为 skill" 的候选 (CRUD 内部端点 / 高频 cron / 高 QPS 热路径)。
- **不做 A-E 分类** — 巡检/查询/报告/分析/操作涉及"用户可感知增益"的
  主观判断, 由人工裁决; 机器只拦反模式。
- 纯函数实现, 无 DB / 无网络 / 无全局状态, 便于测试与复用。

三条规则 (与文档 §5.2 检查清单一一对应, 出处 plan §17.4 反模式 #1/#2/#4):
- R1 CRUD 内部端点: kind=endpoint 且写方法 (POST/PUT/PATCH/DELETE)
  且 path 形如 /api/<resource>... (GET 读操作放行)
- R2 已有高频 cron: kind=job 且 cron_interval_seconds < 300s (5 分钟)
  — skill 触发等于双调度
- R3 高 QPS 热路径: kind=endpoint 且 path/name 含 collect/refresh/run
  关键词 (采集热路径家族)

裁决语义: findings 非空 → check_candidate() 返回 eligible=False;
severity 恒为 "warning" — 客观启发式允许人工复议 (如 v0.9 的 E 类
操作型 skill 会合法命中 R1, 见文档 §5.5)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "AbstractorVerdict",
    "AntiPatternFinding",
    "SkillCandidate",
    "check_candidate",
    "find_anti_patterns",
]

#: R1 信号 — 内部资源 API 路径形态 ^/api/[a-z_]+(/.*)?$
#: ("/api/knowledge/"、"/api/secrets/1" 命中; "/healthz" 不命中)
_INTERNAL_API_PATH_RE = re.compile(r"^/api/[a-z_]+(/.*)?$")
#: R1 信号 — 资源写方法集合 (GET 读操作放行, B 类查询型合法)
_CRUD_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: R2 信号 — 高频 cron 阈值 (秒): 低于该值视为已有调度在跑
_HIGH_FREQUENCY_CRON_SECONDS = 300
#: R3 信号 — 采集/刷新热路径关键词家族 (path 或 name 子串命中任一即算)
_HOT_PATH_KEYWORDS = ("collect", "refresh", "run")


@dataclass(frozen=True)
class SkillCandidate:
    """待审查的 skill 候选 — 来自 endpoint / service / job 三类既有能力。

    字段语义随 kind 演化:
    - kind="endpoint": path 为 API 路径 (如 "/api/knowledge/"),
      http_method 携带动词 (GET 放行, 写方法触发 R1)
    - kind="service": path 为 service module 路径
      (如 "backend.services.source_scheduler_service")
    - kind="job": path 为 job 名或模块 (如 "collect_all_hotspots"),
      cron_interval_seconds 携带既有调度周期 (触发 R2)

    name 为候选 skill 的语义名 (如 "source-health-scan"),
    与 path 一起参与 R3 热路径关键词匹配。
    """

    kind: Literal["endpoint", "service", "job"]
    path: str
    name: str
    http_method: str | None = None
    cron_interval_seconds: int | None = None


@dataclass(frozen=True)
class AntiPatternFinding:
    """单条反模式命中记录。

    severity 恒为 "warning": R1-R3 是客观启发式信号, 拦截注册流程
    但不终审 — 允许人工复议 (复议须记录裁决理由, 禁止静默绕过,
    见 docs/V0.8_SKILL_ABSTRACTION.md §5.5)。
    """

    rule_id: str
    rule_name: str
    severity: str = "warning"
    reason: str = ""
    suggestion: str = ""


@dataclass(frozen=True)
class AbstractorVerdict:
    """check_candidate() 的裁决结果: findings 非空 → eligible=False。"""

    eligible: bool
    findings: list[AntiPatternFinding] = field(default_factory=list)


def _check_r1_crud_endpoint(candidate: SkillCandidate) -> AntiPatternFinding | None:
    """R1 — CRUD 内部端点: 资源写操作包装成 skill 无用户增益。

    信号 (全部客观): kind=endpoint 且 http_method ∈ 写方法
    且 path 匹配内部资源路径形态; GET 读操作不算 (B 类查询型合法)。
    """
    if candidate.kind != "endpoint":
        return None
    method = (candidate.http_method or "").upper()
    if method not in _CRUD_METHODS:
        return None
    if not _INTERNAL_API_PATH_RE.match(candidate.path):
        return None
    return AntiPatternFinding(
        rule_id="R1",
        rule_name="CRUD 内部端点",
        reason=(
            f"{method} {candidate.path} 是内部资源写操作, "
            "wiki-first UI 已提供直接入口, skill 包装无用户增益"
        ),
        suggestion="不抽象; 确属操作型 (E 类) 增益时人工复议并记录裁决理由",
    )


def _check_r2_high_frequency_cron(
    candidate: SkillCandidate,
) -> AntiPatternFinding | None:
    """R2 — 已有高频 cron: < 300s 的 job 再包 skill 等于双调度。"""
    if candidate.kind != "job":
        return None
    if candidate.cron_interval_seconds is None:
        return None
    if candidate.cron_interval_seconds >= _HIGH_FREQUENCY_CRON_SECONDS:
        return None
    return AntiPatternFinding(
        rule_id="R2",
        rule_name="已有高频 cron",
        reason=(
            f"job '{candidate.path}' 已配 {candidate.cron_interval_seconds}s cron "
            f"(< {_HIGH_FREQUENCY_CRON_SECONDS}s), skill 触发等于双调度"
        ),
        suggestion="不抽象为触发; 需要'看结果'时改走 A 类巡检 (读统计不触发执行)",
    )


def _check_r3_hot_path(candidate: SkillCandidate) -> AntiPatternFinding | None:
    """R3 — 高 QPS 热路径: collect/refresh/run 家族端点, skill 包装拖慢主路径。"""
    if candidate.kind != "endpoint":
        return None
    haystack = f"{candidate.path} {candidate.name}".lower()
    if not any(keyword in haystack for keyword in _HOT_PATH_KEYWORDS):
        return None
    return AntiPatternFinding(
        rule_id="R3",
        rule_name="高 QPS 热路径",
        reason=(
            f"path/name 命中采集热路径关键词家族 "
            f"({_HOT_PATH_KEYWORDS}): '{candidate.path}'"
        ),
        suggestion="不包装热路径; 健康状态走 A 类巡检旁路观察 (读日志/指标)",
    )


def find_anti_patterns(candidate: SkillCandidate) -> list[AntiPatternFinding]:
    """对候选执行 R1-R3 全部客观信号检查, 返回命中清单 (可为空 / 多条)。

    纯函数: 同一输入恒等输出, 不读全局状态, 无副作用。
    """
    checks = (
        _check_r1_crud_endpoint,
        _check_r2_high_frequency_cron,
        _check_r3_hot_path,
    )
    findings: list[AntiPatternFinding] = []
    for check in checks:
        finding = check(candidate)
        if finding is not None:
            findings.append(finding)
    return findings


def check_candidate(candidate: SkillCandidate) -> AbstractorVerdict:
    """注册门 (A2b 流程第 2 步): findings 非空 → eligible=False。

    eligible=False 不是终审 — severity 均为 warning, 允许人工复议
    (复议须记录裁决理由, 见 docs/V0.8_SKILL_ABSTRACTION.md §5.5)。
    """
    findings = find_anti_patterns(candidate)
    return AbstractorVerdict(eligible=not findings, findings=findings)
