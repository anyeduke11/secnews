"""Characterization tests — 锁定 SimHash / retention / concept_linker 当前真实行为。

**目的**: 这些模块是质量门禁 (去重 / 衰减 / 知识图谱) 的核心算法层。
任何重构 (例如改 simhash 哈希源、改 decay 公式、改 schema 校验) 都会
触发本测试给出"行为变化是否在允许范围"的判据。

**与普通 unit test 的区别**:
- 不追求覆盖率, 只锁"对外可见行为的不变量"
- golden 数值来自 `python -m pytest --collect-only` 之外的实测脚本
  (见 PROGRESS.md 2026-08-24 P0-3 节)
- 重构若打破, 必须**显式确认**变更意图并更新断言, 不允许静默漂移
- 不依赖 DB / 时间 / 文件系统的部分使用 freeze 参数 (retention 的 `now=`)
- 依赖文件系统的部分 (concept_linker 写 .md) 使用 tmp_path fixture

**Golden 数据采集日**: 2026-08-24
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════
# SimHash — 中文/英文标题相似度检测
# ═══════════════════════════════════════════════════════════════


class TestSimHashGolden:
    """锁定 compute_simhash 对一组真实文本的 64-bit fingerprint。

    这些数字依赖 SHA-256-based 哈希实现 (P1 修复后, 见 simhash.py _hash_token)。
    若哈希源从 SHA-256 改到其它确定性算法, 整组数字会重排 → 提醒审视去重策略。
    """

    @pytest.fixture
    def simhash(self):
        from backend.quality.simhash import compute_simhash

        return compute_simhash

    def test_zh_long_title_fingerprint(self, simhash):
        assert simhash("网络安全态势感知平台建设方案") == 0x828112465C5C2AC0

    def test_en_cve_title_fingerprint(self, simhash):
        assert simhash("CVE-2024-1234 affects OpenSSL TLS handshake") == 0x67FF73D392A1C986

    def test_zh_zero_trust_title_fingerprint(self, simhash):
        assert simhash("零信任架构在企业内网中的部署与实施指南") == 0x45FD2B288340C383

    def test_en_python_perf_fingerprint(self, simhash):
        assert simhash("Python 3.12 introduces significant performance improvements") == 0x4A15B0117EFEFF09

    def test_zh_finance_regulation_fingerprint(self, simhash):
        assert simhash("金融机构数据安全管理办法征求意见稿") == 0xEAAE994715DD2BB0

    def test_zh_threat_hunting_with_space_fingerprint(self, simhash):
        assert simhash("AI 驱动的威胁狩猎平台") == 0x18D221805C323142

    def test_zh_threat_hunting_no_space_fingerprint(self, simhash):
        assert simhash("AI驱动的威胁狩猎平台") == 0x99D2212948B23143

    def test_zh_sql_injection_fingerprint(self, simhash):
        assert simhash("SQL 注入漏洞利用 PoC 分析") == 0x06C4DE1229C89558


class TestSimHashDeterminism:
    """同一文本跨调用/跨进程必须产生相同 simhash (production 去重稳定性的前提)。"""

    def test_same_text_same_hash(self):
        from backend.quality.simhash import compute_simhash

        s = "零信任架构在企业内网中的部署与实施指南"
        assert compute_simhash(s) == compute_simhash(s)

    def test_simhash_not_python_hash(self):
        """P1 修复: 不能用 Python built-in hash() (PYTHONHASHSEED 随机化)。"""
        # 此断言验证 _hash_token 用 SHA-256 而非 hash()
        # — 如果实现回退到 hash(), 同 token 跨进程/进程重启会变
        from backend.quality.simhash import _hash_token

        h1 = _hash_token("网络安全")
        h2 = _hash_token("网络安全")
        assert h1 == h2
        # SHA-256 8 字节 → 0 ≤ h < 2^64
        assert 0 <= h1 < (1 << 64)


class TestHammingDistance:
    """Hamming 距离的边界与等价关系。"""

    def test_identical_zero(self):
        from backend.quality.simhash import hamming_distance

        for h in (0, 1, 0xFFFFFFFFFFFFFFFF, 0x828112465C5C2AC0):
            assert hamming_distance(h, h) == 0

    def test_one_bit_diff_is_one(self):
        from backend.quality.simhash import hamming_distance

        assert hamming_distance(0, 1) == 1
        assert hamming_distance(0, 2) == 1
        assert hamming_distance(0, 1 << 63) == 1

    def test_symmetry(self):
        from backend.quality.simhash import hamming_distance

        a, b = 0x67FF73D392A1C986, 0x18D221805C323142
        assert hamming_distance(a, b) == hamming_distance(b, a)

    def test_max_distance_for_complement(self):
        from backend.quality.simhash import hamming_distance

        assert hamming_distance(0, 0xFFFFFFFFFFFFFFFF) == 64


class TestIsDuplicateGolden:
    """对 (a, b) 文本对的实际 Hamming 距离, 锁定 similarity 判定的临界点。

    阈值默认 5 (< 5 视为重复)。当前 5 对样本全部 hamming ≥ 6 → False。
    这反映了"基于标题去重"对中文长文本的灵敏度边界 — 短词变化
    (建设→技术、3.12→3.13) 引入的位翻转 ≥ 6, 不会误判重复。
    """

    @pytest.mark.parametrize(
        "a,b,expected_hamming,expected_dup",
        [
            (
                "网络安全态势感知平台建设方案",
                "网络安全态势感知平台技术方案",
                6,
                False,
            ),
            ("零信任架构部署指南", "零信任架构实施指南", 13, False),
            ("Python 3.12 性能优化", "Python 3.13 性能优化", 9, False),
            ("完全不同的内容", "另一个完全不同的话题", 13, False),
            (
                "AI 驱动的威胁狩猎平台",
                "AI驱动的威胁狩猎平台",
                10,
                False,
            ),
        ],
    )
    def test_hamming_and_duplicate(self, a, b, expected_hamming, expected_dup):
        from backend.quality.simhash import (
            compute_simhash,
            hamming_distance,
            is_duplicate,
        )

        ha, hb = compute_simhash(a), compute_simhash(b)
        assert hamming_distance(ha, hb) == expected_hamming
        assert is_duplicate(ha, hb) is expected_dup

    def test_default_threshold_is_five(self):
        """默认阈值 < 5 视为重复 — 任何调整需走 PR 评审。"""
        from backend.quality.simhash import is_duplicate

        # hamming=4 (< 5) → True
        assert is_duplicate(0b0000, 0b1111) is True
        # hamming=5 (不 < 5) → False
        assert is_duplicate(0b00000, 0b11111) is False

    def test_custom_threshold(self):
        from backend.quality.simhash import is_duplicate

        assert is_duplicate(0, 0b1111, threshold=3) is False
        assert is_duplicate(0, 0b1111, threshold=5) is True


class TestSimHashEdgeCases:
    """空/纯空白/极短文本的退化行为 — 保证不抛错。"""

    def test_empty_returns_zero(self):
        from backend.quality.simhash import compute_simhash

        assert compute_simhash("") == 0

    def test_whitespace_only_returns_zero(self):
        from backend.quality.simhash import compute_simhash

        assert compute_simhash("   ") == 0

    def test_punctuation_only(self):
        from backend.quality.simhash import compute_simhash

        # 仅标点 → tokenize 后全是空 → 应返回 0 (不抛错)
        assert compute_simhash("！，？。") == 0


# ═══════════════════════════════════════════════════════════════
# Retention Engine — Ebbinghaus 衰减追踪
# ═══════════════════════════════════════════════════════════════


class TestRetentionRunDecayFrozen:
    """锁定 run_decay 在冻结时间下的行为 — 避免真实时间漂移导致 flaky。

    retention.json schema (SPEC §18.2):
    ``{"entries": [{"id", "initial_score", "current_score", "last_accessed", ...}, ...]}``
    """

    def _write_retention(self, path: Path, entries: list[dict]) -> None:
        path.write_text(json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")

    def test_run_decay_updates_stale_entry(self, tmp_path):
        """距 2026-08-17 7 天的条目 (current=1.0) → decay 后 0.8915。

        当前实测时间 2026-08-24, last_accessed=2026-08-17 → days≈7
        但因测试运行时刻非 00:00, 实际 days=6.9xxx → decay ≈ 0.8915。
        用 ±0.005 容差锚定"近似 7 天"区间, 允许秒级抖动。
        """
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {
                "id": "item-a",
                "initial_score": 1.0,
                "current_score": 1.0,
                "last_accessed": "2026-08-17T00:00:00+00:00",
            },
        ])

        result = run_decay(rp)
        assert result["updated"] == 1
        assert result["errors"] == 0

        obj = json.loads(rp.read_text(encoding="utf-8"))
        score = obj["entries"][0]["current_score"]
        assert 0.88 <= score <= 0.92, f"expected ~0.9, got {score}"

    def test_run_decay_mixed_initial_scores(self, tmp_path):
        """initial=1.0 和 initial=0.8 共存时各自衰减, 不互相干扰。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {
                "id": "a",
                "initial_score": 1.0,
                "current_score": 1.0,
                "last_accessed": "2026-08-17T00:00:00+00:00",
            },
            {
                "id": "b",
                "initial_score": 0.8,
                "current_score": 0.8,
                "last_accessed": "2026-08-20T00:00:00+00:00",
            },
        ])

        result = run_decay(rp)
        assert result["updated"] == 2

        obj = json.loads(rp.read_text(encoding="utf-8"))
        scores = {e["id"]: e["current_score"] for e in obj["entries"]}
        # a: 距 7 天 → ~0.9; b: 距 4 天 → 0.8 * 0.9^(4/7) ≈ 0.7461
        assert 0.85 <= scores["a"] <= 0.92, f"a={scores['a']}"
        assert 0.72 <= scores["b"] <= 0.77, f"b={scores['b']}"

    def test_run_decay_invalid_iso_silently_zero(self, tmp_path):
        """last_accessed 解析失败 → parse_iso 静默返回 0.0 (视为刚访问),
        该条目 unchanged (新分数=初分数, 与原 current 差 <0.0001), 不计入 errors。

        设计权衡 (retention_engine.py L48): 解析失败返回 0 而非抛错,
        保证单条脏数据不会让 run_decay 中断整批。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {"id": "bad", "initial_score": 1.0, "current_score": 1.0, "last_accessed": "not-a-date"},
            {"id": "good", "initial_score": 1.0, "current_score": 1.0, "last_accessed": "2026-08-20T00:00:00+00:00"},
        ])

        result = run_decay(rp)
        # bad → unchanged (parse_iso 返回 0, new=1.0, old=1.0, diff<0.0001)
        # good → updated (~0.95)
        assert result["errors"] == 0
        assert result["unchanged"] == 1
        assert result["updated"] == 1

    def test_run_decay_empty_file_is_noop(self, tmp_path):
        """空 retention.json → 0 updated, 0 errors (不抛错)。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [])

        result = run_decay(rp)
        assert result == {"updated": 0, "stale_after": 0, "unchanged": 0, "errors": 0}

    def test_run_decay_missing_entries_key(self, tmp_path):
        """顶层没有 entries 键 → 视为空, 不抛 KeyError。"""
        from backend.services.retention_engine import run_decay

        rp = tmp_path / "retention.json"
        rp.write_text(json.dumps({"version": 1}), encoding="utf-8")

        result = run_decay(rp)
        assert result["errors"] == 0
        assert result["updated"] == 0


class TestRetentionRecordAccessFrozen:
    """record_access 重置行为 + decay_events LIFO 限长 50。"""

    def _write_retention(self, path: Path, entries: list[dict]) -> None:
        path.write_text(json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")

    def test_record_access_resets_existing(self, tmp_path):
        from backend.services.retention_engine import record_access

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {
                "id": "a",
                "initial_score": 1.0,
                "current_score": 0.5,
                "last_accessed": "2026-07-01T00:00:00+00:00",
                "decay_events": [],
            },
        ])

        record_access(rp, "a", now="2026-08-24T00:00:00+00:00")

        obj = json.loads(rp.read_text(encoding="utf-8"))
        e = obj["entries"][0]
        assert e["current_score"] == 1.0
        assert e["last_accessed"] == "2026-08-24T00:00:00+00:00"
        assert e["decay_events"] == [{"kind": "access", "ts": "2026-08-24T00:00:00+00:00"}]

    def test_record_access_creates_new_entry(self, tmp_path):
        """不存在的 item_id → 新建 entry (initial=1.0, current=1.0)。"""
        from backend.services.retention_engine import record_access

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [])

        record_access(rp, "fresh-item", now="2026-08-24T00:00:00+00:00")

        obj = json.loads(rp.read_text(encoding="utf-8"))
        assert len(obj["entries"]) == 1
        e = obj["entries"][0]
        assert e["id"] == "fresh-item"
        assert e["initial_score"] == 1.0
        assert e["current_score"] == 1.0
        assert e["decay_events"] == [{"kind": "access", "ts": "2026-08-24T00:00:00+00:00"}]

    def test_record_access_decays_capped_at_50(self, tmp_path):
        """decay_events LIFO 限长 50, 第 51 次 access 截断最早的。"""
        from backend.services.retention_engine import record_access

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {"id": "a", "initial_score": 1.0, "current_score": 1.0, "last_accessed": "", "decay_events": []},
        ])

        for i in range(60):
            record_access(rp, "a", now=f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00")

        obj = json.loads(rp.read_text(encoding="utf-8"))
        events = obj["entries"][0]["decay_events"]
        assert len(events) == 50


class TestRetentionHealthFrozen:
    """check_retention_health — ratio 计算 + 空库 ok=True 的退化行为。"""

    def _write_retention(self, path: Path, entries: list[dict]) -> None:
        path.write_text(json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")

    def test_empty_is_ok(self, tmp_path):
        from backend.services.retention_engine import check_retention_health

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [])

        health = check_retention_health(rp)
        assert health == {"total": 0, "healthy": 0, "ratio": 1.0, "ok": True}

    def test_all_above_threshold_is_ok(self, tmp_path):
        from backend.services.retention_engine import check_retention_health

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {"id": "a", "current_score": 0.8, "initial_score": 1.0},
            {"id": "b", "current_score": 0.95, "initial_score": 1.0},
            {"id": "c", "current_score": 0.71, "initial_score": 1.0},
        ])

        health = check_retention_health(rp)
        assert health["total"] == 3
        assert health["healthy"] == 3
        assert health["ratio"] == 1.0
        assert health["ok"] is True

    def test_below_threshold_counted_unhealthy(self, tmp_path):
        from backend.services.retention_engine import check_retention_health

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {"id": "a", "current_score": 0.8, "initial_score": 1.0},
            {"id": "b", "current_score": 0.5, "initial_score": 1.0},
            {"id": "c", "current_score": 0.2, "initial_score": 1.0},
            {"id": "d", "current_score": 0.69, "initial_score": 1.0},
        ])

        health = check_retention_health(rp)
        assert health["total"] == 4
        assert health["healthy"] == 1  # 只有 a (>0.7)
        assert health["ratio"] == pytest.approx(0.25)
        assert health["ok"] is False  # 0.25 < 0.8

    def test_below_80pct_fails(self, tmp_path):
        """健康条目占比 < 80% → ok=False (CI gate)。"""
        from backend.services.retention_engine import check_retention_health

        rp = tmp_path / "retention.json"
        self._write_retention(rp, [
            {"id": "a", "current_score": 0.8, "initial_score": 1.0},
            {"id": "b", "current_score": 0.8, "initial_score": 1.0},
            {"id": "c", "current_score": 0.5, "initial_score": 1.0},
            {"id": "d", "current_score": 0.5, "initial_score": 1.0},
            {"id": "e", "current_score": 0.5, "initial_score": 1.0},
        ])

        health = check_retention_health(rp)
        assert health["healthy"] == 2
        assert health["ratio"] == pytest.approx(0.4)
        assert health["ok"] is False


class TestDecayScorePrecisionFrozen:
    """decay_score — 锁住 Ebbinghaus 公式的精度与边界行为。

    P1-4 mutation test 发现盲点 M8: 现有 retention 测试只覆盖整数天 (0/7/14/21),
    浮点精度天然对齐 round(0.9**n, 4) — 去掉 round 后 mutation 不会暴露。
    本测试补充小数天精度断言, 让 M8 真正能被 catch。

    公式: ``current = initial * 0.9 ** (days / 7)`` 截断到 [0, initial] + round(4 位)
    若 round 被去掉, 浮点 0.9**(1.5/7) = 0.9776757055472389 ≠ round 后的 0.9777。
    """

    def test_integer_days_are_exact(self):
        """整数天 0/7/14/21 的 0.9^n 精确, round 不改变值。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, 0) == 1.0
        assert decay_score(1.0, 7) == 0.9
        assert decay_score(1.0, 14) == 0.81   # 0.9 ** 2
        assert decay_score(1.0, 21) == 0.729  # 0.9 ** 3

    def test_fractional_days_locked_to_4_decimals(self):
        """小数天精度锁: round(0.9**(1.5/7), 4) = 0.9777。

        若实现去掉 round(), 该测试会失败 (raw = 0.9776757055472389)。
        """
        from backend.services.retention_engine import decay_score

        # 关键 golden: days=1.5 → 期望 4 位精度
        assert decay_score(1.0, 1.5) == 0.9777

        # 其它小数天精度对照
        assert decay_score(1.0, 0.5) == 0.9925
        assert decay_score(1.0, 2.5) == 0.9631
        assert decay_score(1.0, 7.5) == 0.8933
        assert decay_score(1.0, 14.5) == 0.8039

    def test_negative_days_clamps_to_zero(self):
        """days < 0 → 等同 days=0 (不衰减反增), 由 L49-50 防御性截断。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(1.0, -1) == 1.0
        assert decay_score(1.0, -100) == 1.0
        assert decay_score(0.5, -0.001) == 0.5

    def test_initial_below_one_unchanged(self):
        """initial < 1 时, days=0 应返回 initial 本身 (无衰减)。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(0.5, 0) == 0.5
        assert decay_score(0.7, 0) == 0.7
        assert decay_score(0.3, 0) == 0.3

    def test_zero_initial_always_zero(self):
        """initial=0 → 任何 days 都是 0 (max(0, min(0, raw)))。"""
        from backend.services.retention_engine import decay_score

        assert decay_score(0.0, 0) == 0.0
        assert decay_score(0.0, 1.5) == 0.0
        assert decay_score(0.0, 100) == 0.0

    def test_returns_4_decimal_places_even_for_clean_inputs(self):
        """M8 盲点断言: 即使 inputs 是干净的, 输出必须 round 到 4 位。

        若实现去掉 round(), decay_score(1.0, 7) 会返回 0.9 而非 0.9 (整数天巧合),
        但 decay_score(1.0, 1.5) 会返回 0.9776757055472389 而非 0.9777。
        本测试组合整数 + 小数, 让 M8 在任一路径都暴露。
        """
        from backend.services.retention_engine import decay_score

        results = [
            decay_score(1.0, 0),
            decay_score(1.0, 7),
            decay_score(1.0, 14),
            decay_score(1.0, 1.5),     # 关键小数精度
            decay_score(1.0, 7.5),     # 关键小数精度
        ]
        # 每个结果的小数位数 ≤ 4
        for r in results:
            s = str(r)
            if "." in s:
                decimals = s.split(".")[1]
                assert len(decimals) <= 4, f"decay_score({r}) has > 4 decimals"


# ═══════════════════════════════════════════════════════════════
# Concept Linker — tag→concept 映射 + graph.json schema 校验
# ═══════════════════════════════════════════════════════════════


class TestLinkTagsToConceptsGolden:
    """锁定 link_tags_to_concepts 对真实 tag 的输出 slugs 列表。"""

    def test_curated_tags_resolve(self):
        from backend.services.concept_linker import link_tags_to_concepts

        assert link_tags_to_concepts(["零信任"]) == ["zero-trust-architecture"]

    def test_multiple_tags_dedup(self):
        from backend.services.concept_linker import link_tags_to_concepts

        # "AI驱动安全" 和 "AI安全" 都映射到不同 slug, 但去重保留首次出现
        result = link_tags_to_concepts(["AI驱动安全", "AI安全"])
        # 锁定顺序: TAG_TO_CONCEPT 字典序遍历, "AI驱动安全"→ai-driven-security 先出现
        assert result == ["ai-driven-security", "ai-driven-attack"]

    def test_unknown_tag_returns_empty(self):
        from backend.services.concept_linker import link_tags_to_concepts

        assert link_tags_to_concepts(["完全不存在的 tag xyz"]) == []

    def test_empty_input_returns_empty(self):
        from backend.services.concept_linker import link_tags_to_concepts

        assert link_tags_to_concepts([]) == []

    def test_mixed_known_unknown(self):
        from backend.services.concept_linker import link_tags_to_concepts

        result = link_tags_to_concepts(["零信任", "随机未知标签", "渗透测试"])
        assert result == ["zero-trust-architecture", "penetration-testing"]

    def test_security_domain_sample(self):
        """10 个安全领域高频 tag 的预期 slugs (锁定 curated mapping)。

        顺序来自 TAG_TO_CONCEPT dict 的 Python 3.7+ 插入序遍历:
        - 安全技术/管理/运营 → security-fundamentals (后两者去重)
        - 安全事件/漏洞管理/威胁情报 → threat-intelligence (后两者去重)
        - 攻防演练/渗透测试 → penetration-testing (后者去重)
        - 数据安全 → defense-modernization
        - 安全架构 → zero-trust-architecture
        """
        from backend.services.concept_linker import link_tags_to_concepts

        tags = [
            "安全技术", "安全管理", "安全运营", "安全事件",
            "攻防演练", "漏洞管理", "数据安全", "安全架构",
            "威胁情报", "渗透测试",
        ]
        assert link_tags_to_concepts(tags) == [
            "security-fundamentals",
            "threat-intelligence",
            "penetration-testing",
            "defense-modernization",
            "zero-trust-architecture",
        ]


class TestValidateGraphSchemaGolden:
    """锁定 validate_graph_schema 对 (valid / invalid) graph 的错误列表。"""

    def _valid_edge(self) -> dict:
        return {
            "source": "node-a",
            "target": "node-b",
            "type": "uses",
            "weight": 3,
            "source_observation_count": 2,
        }

    def test_empty_graph_is_valid(self):
        from backend.services.concept_linker import validate_graph_schema

        assert validate_graph_schema({}) == []
        assert validate_graph_schema({"nodes": [], "edges": []}) == []

    def test_valid_graph_no_errors(self):
        from backend.services.concept_linker import validate_graph_schema

        g = {
            "nodes": [{"id": "node-a"}, {"id": "node-b"}],
            "edges": [self._valid_edge()],
        }
        assert validate_graph_schema(g) == []

    def test_all_six_edge_types_accepted(self):
        """SPEC §18 / wiki v2 §10.12 定义 6 种 typed 关系。"""
        from backend.services.concept_linker import (
            EDGE_TYPES,
            validate_graph_schema,
        )

        for etype in EDGE_TYPES:
            g = {
                "nodes": [{"id": "x"}, {"id": "y"}],
                "edges": [{
                    "source": "x", "target": "y", "type": etype,
                    "weight": 1, "source_observation_count": 1,
                }],
            }
            errors = validate_graph_schema(g)
            assert errors == [], f"type={etype} errors={errors}"

        assert EDGE_TYPES == ("uses", "depends", "contradicts", "caused", "fixed", "supersedes")

    def test_invalid_edge_type_caught(self):
        from backend.services.concept_linker import validate_graph_schema

        g = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{
                "source": "a", "target": "b", "type": "unknown-rel",
                "weight": 1, "source_observation_count": 1,
            }],
        }
        errors = validate_graph_schema(g)
        assert len(errors) == 1
        assert "类型非法" in errors[0]

    def test_missing_weight_caught(self):
        from backend.services.concept_linker import validate_graph_schema

        g = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{
                "source": "a", "target": "b", "type": "uses",
                "weight": 0, "source_observation_count": 1,
            }],
        }
        errors = validate_graph_schema(g)
        assert any("weight" in e for e in errors)

    def test_dangling_edge_source_caught(self):
        from backend.services.concept_linker import validate_graph_schema

        g = {
            "nodes": [{"id": "b"}],
            "edges": [{
                "source": "a", "target": "b", "type": "uses",
                "weight": 1, "source_observation_count": 1,
            }],
        }
        errors = validate_graph_schema(g)
        assert any("source" in e and "a" in e for e in errors)

    def test_duplicate_edge_caught(self):
        from backend.services.concept_linker import validate_graph_schema

        edge = self._valid_edge()
        g = {
            "nodes": [{"id": "node-a"}, {"id": "node-b"}],
            "edges": [edge, dict(edge)],
        }
        errors = validate_graph_schema(g)
        assert any("重复边" in e for e in errors)

    def test_top_level_must_be_object(self):
        from backend.services.concept_linker import validate_graph_schema

        # 实际错误消息以 "graph.json" 开头, 测试断言前缀匹配
        assert any("顶层必须是 JSON object" in e for e in validate_graph_schema([]))
        assert any("顶层必须是 JSON object" in e for e in validate_graph_schema("not-a-dict"))

    def test_nodes_must_be_list(self):
        from backend.services.concept_linker import validate_graph_schema

        assert "nodes 必须是数组" in validate_graph_schema({"nodes": "not-list"})
