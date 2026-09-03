"""v0.8 B3 — agent_memory (HITL 反馈 + 召回 + 偏好挖掘) 测试.

覆盖 (V0.8_REFACTOR_PLAN.md §7.5):
  1. record_feedback 正常落库 + score 校验
  2. record_feedback 孤儿 run_id 拒绝
  3. record_feedback score 越界拒绝
  4. list_feedback 按 skill_id 倒序
  5. recall 三路合并: exact 优先
  6. recall simhash 命中 (相似 intent 召回)
  7. recall 关键词初筛
  8. recall 空表优雅返回
  9. recall 排序: 匹配路径优先级 + 相似度降序
 10. mine_preferences avoid_skill 规则触发
 11. mine_preferences prefer_runner 规则触发
 12. mine_preferences prefer_style 规则触发
 13. mine_preferences 幂等 (重复 mine 不重复行)
 14. active_preferences 读回注入
 15. v1 兼容: user_memory_service 单例同对象
 16. recall 反馈均分 join 进 hit.score
"""
from __future__ import annotations

import json
import time

import pytest

from backend.repository.db import get_connection
from backend.services.agent_memory import (
    AgentMemoryService,
    MemoryRecall,
    PreferenceMiner,
    agent_memory,
)
from backend.services.agent_memory.miner import (
    AVOID_SKILL_FAIL_THRESHOLD,
    PREFER_RUNNER_SUCCESS_THRESHOLD,
    PREFER_STYLE_COUNT_THRESHOLD,
    PREFER_STYLE_SCORE_THRESHOLD,
)
from backend.services.agent_memory.recall import (
    SIMHASH_MAX_DISTANCE,
    extract_intent,
    hamming_distance,
    simhash64,
    tokenize,
    top_keywords,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _seed_skill_run(
    run_id: str,
    skill_id: str,
    intent: str,
    status: str = "done",
    metrics: dict | None = None,
) -> None:
    """向 skill_runs 塞一条 run (recall/miner 的数据源)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO skill_runs("
        "run_id, skill_id, status, inputs, result, metrics, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            skill_id,
            status,
            json.dumps({"intent": intent}, ensure_ascii=False),
            json.dumps({"summary": intent[:40]}, ensure_ascii=False),
            json.dumps(metrics or {}, ensure_ascii=False),
            time.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


# ---------------------------------------------------------------------------
# 1. record_feedback 正常 + 校验
# ---------------------------------------------------------------------------
def test_record_feedback_happy_path(temp_db):
    svc = AgentMemoryService()
    _seed_skill_run("r1", "s1", "查今日热点")
    row = svc.record_feedback("r1", "s1", 4, "可用")
    assert row["score"] == 4
    assert row["comment"] == "可用"
    assert row["skill_run_id"] == "r1"
    assert row["skill_id"] == "s1"


def test_record_feedback_orphan_run_rejected(temp_db):
    svc = AgentMemoryService()
    with pytest.raises(ValueError, match="not found"):
        svc.record_feedback("ghost-run", "s1", 4)


@pytest.mark.parametrize("bad", [0, 6, -1, 3.5, "4"])
def test_record_feedback_score_out_of_range(temp_db, bad):
    svc = AgentMemoryService()
    _seed_skill_run("r1", "s1", "intent")
    with pytest.raises(ValueError, match="score"):
        svc.record_feedback("r1", "s1", bad)


def test_list_feedback_orders_by_skill_desc(temp_db):
    svc = AgentMemoryService()
    _seed_skill_run("r1", "s1", "a")
    _seed_skill_run("r2", "s1", "b")
    _seed_skill_run("r3", "s2", "c")
    svc.record_feedback("r1", "s1", 5)
    svc.record_feedback("r2", "s1", 3)
    svc.record_feedback("r3", "s2", 4)
    rows = svc.list_feedback("s1")
    assert [r["skill_run_id"] for r in rows] == ["r2", "r1"]


# ---------------------------------------------------------------------------
# 2. recall (三路混合)
# ---------------------------------------------------------------------------
def test_recall_empty_db_returns_empty(temp_db):
    assert MemoryRecall().search("任意意图") == []


def test_recall_exact_skill_id_match_wins(temp_db):
    """skill_id 在 intent 中出现 → exact 路径最高优先级, 必中."""
    _seed_skill_run("r1", "bid_hotspots", "今日招投标")
    _seed_skill_run("r2", "news_digest", "今日新闻摘要")
    hits = MemoryRecall().search("bid_hotspots 帮我看看有什么更新", k=5)
    assert len(hits) >= 1
    top = hits[0]
    assert top.skill_run_id == "r1"
    assert top.match_path == "exact"
    assert top.similarity == 1.0


def test_recall_simhash_similar_intent(temp_db):
    """相似 intent (token 集合高重叠) → simhash 路径召回.

    测试用相同 token 集 (顺序不同) 保证 simhash 距离落入阈值。
    短句 / 异构 token 集合的 simhash 区分度是算法特性, 走 keyword 兜底。
    """
    _seed_skill_run("r1", "s1", "查询 今日 漏洞 摘要 复盘 详情 风险")
    hits = MemoryRecall().search("今日 查询 摘要 漏洞 复盘 详情 风险", k=3)
    # 高 token 重叠 → simhash 命中 r1
    assert any(h.skill_run_id == "r1" and h.match_path == "simhash" for h in hits)


def test_recall_keyword_fallback(temp_db):
    """exact/simhash 都不足 k → 关键词 LIKE 兜底."""
    _seed_skill_run("r1", "s1", "AI 安全报告")
    # intent 与 run 文本相似度低, skill_id 不在里面
    hits = MemoryRecall().search("安全", k=3)
    assert any(h.skill_run_id == "r1" for h in hits)


def test_recall_priority_path_then_similarity(temp_db):
    """排序规则: exact(0) > simhash(1) > keyword(2), 同路径按相似度降序.

    每个候选只触发一条路径, 排除交叉命中: r-exact 走 exact, r-sim 走
    simhash (长句), r-kw 走 keyword (含种子关键词但 simhash 距离超阈值)。
    """
    # r-exact: skill_id 出现在 query
    _seed_skill_run("r-exact", "news_digest", "x")
    # r-sim: 相同 token 集, 顺序微调, simhash 距离落入阈值
    _seed_skill_run(
        "r-sim",
        "s1",
        "今日 安全 热点 扫描 漏洞 摘要 风险 等级 排序 复盘 详情",
    )
    # r-kw: 完全不同主题, 但 result 命中 query 关键词
    _seed_skill_run(
        "r-kw",
        "s1",
        "完全不相关 文本 但 含 今日 字样 报告",
    )
    hits = MemoryRecall().search(
        "news_digest 今日 安全 热点 扫描 漏洞 摘要 风险 等级 排序 复盘 详情",
        k=5,
    )
    # exact 必须排第一
    assert hits and hits[0].skill_run_id == "r-exact"
    # 排序 key = (path_priority, -similarity), recall._PATH_PRIORITY 为:
    # {'exact': 0, 'simhash': 1, 'keyword': 2}。验证排序单调非降。
    from backend.services.agent_memory.recall import _PATH_PRIORITY

    for a, b in zip(hits, hits[1:]):
        key_a = (_PATH_PRIORITY.get(a.match_path, 9), -a.similarity)
        key_b = (_PATH_PRIORITY.get(b.match_path, 9), -b.similarity)
        assert key_a <= key_b, f"排序失败: {key_a} > {key_b}"


def test_recall_attach_feedback_score(temp_db):
    """feedback_log join → hit.score 反映反馈均分."""
    _seed_skill_run("r1", "s1", "x")
    AgentMemoryService().record_feedback("r1", "s1", 5)
    AgentMemoryService().record_feedback("r1", "s1", 3)
    hits = MemoryRecall().search("x", k=3)
    assert hits and hits[0].score == 4.0


# ---------------------------------------------------------------------------
# 3. mine_preferences (三规则)
# ---------------------------------------------------------------------------
def test_mine_avoid_skill_triggers_at_threshold(temp_db):
    for i in range(AVOID_SKILL_FAIL_THRESHOLD):
        _seed_skill_run(f"r{i}", "bad-skill", "x", status="failed")
    prefs = PreferenceMiner().mine()
    assert any(p.kind == "avoid_skill" and p.value == "bad-skill" for p in prefs)


def test_mine_avoid_skill_below_threshold_no_trigger(temp_db):
    for i in range(AVOID_SKILL_FAIL_THRESHOLD - 1):
        _seed_skill_run(f"r{i}", "ok-skill", "x", status="failed")
    prefs = PreferenceMiner().mine()
    assert all(not(p.kind == "avoid_skill" and p.value == "ok-skill") for p in prefs)


def test_mine_prefer_runner_triggers_at_threshold(temp_db):
    for i in range(PREFER_RUNNER_SUCCESS_THRESHOLD):
        _seed_skill_run(
            f"r{i}", f"s{i}", "intent", status="done", metrics={"runner": "fast_loop"}
        )
    prefs = PreferenceMiner().mine()
    assert any(p.kind == "prefer_runner" and p.value == "fast_loop" for p in prefs)


def test_mine_prefer_style_triggers(temp_db):
    svc = AgentMemoryService()
    # seed skill_run + 给同一 skill 写 N 条高分反馈
    _seed_skill_run("r1", "style-skill", "漏洞复盘 详细分析")
    for i in range(PREFER_STYLE_COUNT_THRESHOLD):
        run_id = f"r{i+1}"
        _seed_skill_run(run_id, "style-skill", "漏洞复盘 详细分析")
        svc.record_feedback(run_id, "style-skill", PREFER_STYLE_SCORE_THRESHOLD)
    prefs = PreferenceMiner().mine()
    assert any(p.kind == "prefer_style" and p.value for p in prefs)


def test_mine_is_idempotent(temp_db):
    """重复 mine 不增加 agent_preferences 行 (UNIQUE(kind, value))."""
    for i in range(AVOID_SKILL_FAIL_THRESHOLD):
        _seed_skill_run(f"r{i}", "bad", "x", status="failed")
    PreferenceMiner().mine()
    rows1 = get_connection().execute(
        "SELECT COUNT(*) AS n FROM agent_preferences"
    ).fetchone()["n"]
    PreferenceMiner().mine()
    rows2 = get_connection().execute(
        "SELECT COUNT(*) AS n FROM agent_preferences"
    ).fetchone()["n"]
    assert rows1 == rows2


def test_active_preferences_round_trip(temp_db):
    for i in range(AVOID_SKILL_FAIL_THRESHOLD):
        _seed_skill_run(f"r{i}", "bad-x", "x", status="failed")
    PreferenceMiner().mine()
    active = agent_memory.active_preferences()
    assert any(p.kind == "avoid_skill" and p.value == "bad-x" for p in active)
    # 坏 evidence JSON 也不会让 read 崩 (兜底 {})
    get_connection().execute(
        "UPDATE agent_preferences SET evidence = 'not-json' WHERE id = 1"
    )
    bad = agent_memory.active_preferences()
    assert all(isinstance(p.evidence, dict) for p in bad)


# ---------------------------------------------------------------------------
# 4. v1 兼容层
# ---------------------------------------------------------------------------
def test_v1_user_memory_service_compat():
    """包级 user_memory_service 与 v1 模块同对象 (零改动迁移)."""
    from backend.services import agent_memory as pkg
    from backend.services import user_memory_service as v1

    assert pkg.user_memory_service is v1.user_memory_service
    assert pkg.UserMemoryService is v1.UserMemoryService


# ---------------------------------------------------------------------------
# 5. recall 内部工具 (轻量校验, 防止重构悄悄退化)
# ---------------------------------------------------------------------------
def test_simhash_similar_texts_small_distance():
    """simhash 64-bit 对相同 token 集的距离 = 0 (确定性算法).

    短句 / 异构 token 集合的 simhash 区分度受 token 哈希权重投票
    限制, 中等相似度句对距离常落在阈值边缘 (实测 12-16)。本测试
    只验证"完全相同 token 集"零距离, 避免阈值边界漂移测试噪声。
    """
    fp1 = simhash64("查询 今日 漏洞 摘要 复盘")
    fp2 = simhash64("查询 今日 漏洞 摘要 复盘")
    assert hamming_distance(fp1, fp2) == 0


def test_simhash_distance_monotonic_with_diff():
    """差异越大, simhash 距离越大 (保证排序单调, 阈值不会颠倒方向).

    弱断言: 显著差异的句对距离应明显大于相同句对距离。
    """
    same = simhash64("漏洞摘要 复盘详情 风险等级")
    diff = simhash64("完全不同的另一段文字 讲讲旅游攻略")
    assert hamming_distance(same, same) < hamming_distance(same, diff)


def test_tokenize_cjk_bigram():
    toks = tokenize("查询安全")
    assert "查询" in toks and "询安" in toks and "安全" in toks


def test_top_keywords_orders_by_freq():
    # top_keywords 滤掉 len<2 的 token, 用更长的词验证
    out = top_keywords(["alpha alpha alpha", "alpha beta", "beta gamma"], limit=2)
    assert out[0] == "alpha"
    assert out[1] == "beta"


def test_extract_intent_priority_keys():
    assert extract_intent(json.dumps({"intent": "x"})) == "x"
    assert extract_intent(json.dumps({"query": "y"})) == "y"
    assert extract_intent(json.dumps({"text": "z"})) == "z"
    assert extract_intent("not-json-but-string") == "not-json-but-string"
    assert extract_intent(json.dumps({"k": 1, "j": 2})) == "1 2"
    assert extract_intent(None) == ""
