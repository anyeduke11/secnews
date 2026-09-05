"""skill_registry 测试 — A2b 20 个内置 skill 静态注册 (契约 + 校验 + 启停)。

覆盖四层:
1. 注册面对账 — 数量 20 / id 唯一 / A-E 与四分类计数 (plan §4 官方清单)
2. R1 契约 — A/B 类零 prompt_template, C/D 类 prompt+pipeline 齐备,
   target/pipeline 互斥二选一, feature_gate 与 id 自洽 (§4.0 三条硬规则)
3. loader 校验 — 六条规则逐条违规注入各被拦截; BUILTIN 全量 0 errors
4. 启停 — enable/disable 写 settings kv (真实 SettingsRepository 读回),
   is_skill_enabled = kv AND 父 gate (父 gate fail-closed 行为单独锁定)

target 真实性: ServiceTarget.module 全量 find_spec + 与实地核验清单对账;
ApiTarget.path 与仓库真实路由清单对账 (注册期锁死, 防止后续改路由漂移)。
"""
from __future__ import annotations

import importlib.util
from collections import Counter
from dataclasses import replace

import pytest

from backend.repository.settings_repo import SettingsRepository
from backend.services.skill_registry import (
    BUILTIN,
    BUILTIN_SKILLS,
    ApiTarget,
    ServiceTarget,
    SkillCandidate,
    SkillDef,
    SkillNotFoundError,
    SkillRegistry,
    SkillRegistryValidationError,
    Step,
    check_candidate,
    load_validation,
)

#: 实地核验过的 module 集合 (A2b 开工时逐一 grep/ls 确认, 注册期锁死对账)
_VERIFIED_MODULES = {
    "backend.services.source_scheduler_service",
    "backend.services.hotspot_service",
    "backend.services.cve_heatmap_service",
    "backend.repository.source_scheduler_repo",
    "backend.services.source_census_service",
    "backend.repository.todo_repo",
    "backend.extensions",
    "backend.repository.db",
    "backend.wiki_fs.root",
    "backend.services.search_service",
    "backend.services.source_health_service",
    "backend.services.security_graph_service",
    "backend.services.daily_report_overview_service",
    "backend.services.weekly_report_overview_service",
}

#: 实地核验过的 GET 路由集合 (secrets.py:348 / agents_api.py:30 /
#: observability_router.py:25,113 / mcp.py:66)
_VERIFIED_API_PATHS = {
    "/api/secrets/rotation-status",
    "/api/agents/available",
    "/api/observability/summary",
    "/api/observability/timeseries",
    "/api/mcp/tools",
}


def _iter_service_targets(skill: SkillDef):
    """收集 skill 本体 + pipeline service 步的全部 ServiceTarget。"""
    if isinstance(skill.target, ServiceTarget):
        yield skill.target
    for step in skill.pipeline or []:
        if step.target is not None:
            yield step.target


def _make_skill(**overrides) -> SkillDef:
    """最小合法 SkillDef — 违规注入测试的基线 (dataclasses.replace 改单项)。"""
    defaults: dict = dict(
        id="test-skill",
        name="测试技能",
        desc="测试用最小合法定义",
        category="operations",
        skill_type="A",
        target=ServiceTarget(
            module="backend.extensions", method="get_enabled_extensions"
        ),
        feature_gate="skill.test-skill.enabled",
    )
    defaults.update(overrides)
    return SkillDef(**defaults)


_C_PIPELINE = [
    Step(
        kind="service",
        target=ServiceTarget(
            module="backend.extensions", method="get_enabled_extensions"
        ),
    ),
    Step(kind="llm"),
    Step(kind="wiki", path="digest/{{ run.date }}.md", content="{{ steps.1.output }}"),
]


# ===========================================================================
# 1. 注册面对账
# ===========================================================================
class TestRoster:
    """20 skill 名册 — 数量 / 唯一性 / 分类计数与 plan §4 官方清单对账。"""

    def test_registry_has_20_skills(self):
        """注册数量恒为 20 (plan §4: 8 运营 + 6 合规 + 4 分析 + 2 报告)。"""
        assert len(BUILTIN_SKILLS) == 20
        assert len(BUILTIN) == 20

    def test_ids_globally_unique(self):
        """id 全局唯一 — 重复 id 会让 get()/前端路由歧义 (loader 规则 ①)。"""
        ids = [s.id for s in BUILTIN_SKILLS]
        assert len(set(ids)) == 20

    def test_skill_type_counts(self):
        """A=12 / B=1 / C=4 / D=3 / E=0 — E 操作型 v0.9 才落地, 契约禁现。"""
        counts = Counter(s.skill_type for s in BUILTIN_SKILLS)
        assert counts == {"A": 12, "B": 1, "C": 4, "D": 3}
        assert counts.get("E", 0) == 0

    def test_category_counts(self):
        """四分类计数 — operations=8 / compliance=6 / analysis=4 / report=2。"""
        counts = Counter(s.category for s in BUILTIN_SKILLS)
        assert counts == {
            "operations": 8,
            "compliance": 6,
            "analysis": 4,
            "report": 2,
        }

    def test_default_enabled_all_false(self):
        """default_enabled 全部 False — 新 skill 一律 opt-in, 不静默开放。"""
        assert all(s.default_enabled is False for s in BUILTIN_SKILLS)

    def test_runner_all_builtin_and_timeout_default(self):
        """runner 恒为 builtin (LLM 只藏在 pipeline llm 步) + timeout 默认 300s。"""
        assert all(s.runner == "builtin" for s in BUILTIN_SKILLS)
        assert all(s.timeout_seconds == 300 for s in BUILTIN_SKILLS)

    def test_mcp_skill_requires_mcp_gate_check(self):
        """R12: #13 mcp-tools-availability 前置检查 mcp 父 gate, 其余无。"""
        mcp = BUILTIN.get("mcp-tools-availability")
        assert mcp.requires_gate_check == ["mcp"]
        others = [s for s in BUILTIN_SKILLS if s.id != "mcp-tools-availability"]
        assert all(not s.requires_gate_check for s in others)


# ===========================================================================
# 2. R1 契约 (§4.0 三条硬规则)
# ===========================================================================
class TestContract:
    """SkillDef 契约 — prompt 归属 / target-pipeline 互斥 / gate 自洽。"""

    def test_ab_types_have_no_prompt_template(self):
        """A/B 类 prompt_template 必须 None — 巡检/查询藏 LLM 属无差别包装。"""
        for s in BUILTIN_SKILLS:
            if s.skill_type in ("A", "B"):
                assert s.prompt_template is None, f"{s.id} (A/B) 带了 prompt"

    def test_cd_types_have_prompt_and_pipeline(self):
        """C/D 类 prompt_template 与 pipeline 必须齐备 — LLM 编排是其全部增益。"""
        for s in BUILTIN_SKILLS:
            if s.skill_type in ("C", "D"):
                assert s.prompt_template, f"{s.id} (C/D) 缺 prompt_template"
                assert s.pipeline, f"{s.id} (C/D) 缺 pipeline"

    def test_target_pipeline_exactly_one(self):
        """target/pipeline 互斥二选一 — 都空或都有即设计错误 (契约规则 1)。"""
        for s in BUILTIN_SKILLS:
            assert (s.target is not None) != bool(s.pipeline), (
                f"{s.id}: target/pipeline 必须恰好其一"
            )

    def test_b_type_uses_api_target(self):
        """B 类查询型用 ApiTarget (单 GET + 展示层封装, §2.3)。"""
        b_skills = [s for s in BUILTIN_SKILLS if s.skill_type == "B"]
        assert len(b_skills) == 1
        assert isinstance(b_skills[0].target, ApiTarget)

    def test_feature_gate_format_self_consistent(self):
        """feature_gate 恒为 skill.<id>.enabled — 与 id 自洽 (loader 规则 ②)。"""
        for s in BUILTIN_SKILLS:
            assert s.feature_gate == f"skill.{s.id}.enabled"

    def test_service_target_modules_exist(self):
        """ServiceTarget.module 全量 find_spec 通过 — 注册期拦拼写错误。"""
        for skill in BUILTIN_SKILLS:
            for t in _iter_service_targets(skill):
                assert importlib.util.find_spec(t.module) is not None, (
                    f"{skill.id}: module {t.module} 不存在"
                )

    def test_service_target_modules_match_verified_set(self):
        """module 集合与实地核验清单完全一致 — 防止未核验引用混入。"""
        modules = {t.module for s in BUILTIN_SKILLS for t in _iter_service_targets(s)}
        assert modules == _VERIFIED_MODULES

    def test_api_target_paths_match_verified_routes(self):
        """ApiTarget.path 集合与真实路由核验清单一致 — 防路由漂移。"""
        paths = {
            s.target.path
            for s in BUILTIN_SKILLS
            if isinstance(s.target, ApiTarget)
        }
        assert paths == _VERIFIED_API_PATHS


# ===========================================================================
# 3. abstractor 反模式门 (§6.2 注册流程第 2 步)
# ===========================================================================
class TestAbstractorGate:
    """20 skill 全部通过反模式 linter — eligible, 零 findings (§6.3 验收)。"""

    def test_all_skills_pass_abstractor_linter(self):
        """逐 skill 构造候选: service 引用 → kind=service, ApiTarget → GET。"""
        for skill in BUILTIN_SKILLS:
            if skill.pipeline:  # C/D: 取首个 service 步的引用形态
                step = next(st for st in skill.pipeline if st.kind == "service")
                candidate = SkillCandidate(
                    kind="service", path=step.target.module, name=skill.id
                )
            elif isinstance(skill.target, ServiceTarget):
                candidate = SkillCandidate(
                    kind="service", path=skill.target.module, name=skill.id
                )
            else:
                candidate = SkillCandidate(
                    kind="endpoint",
                    path=skill.target.path,
                    name=skill.id,
                    http_method=skill.target.http_method,
                )
            verdict = check_candidate(candidate)
            assert verdict.eligible is True, (
                f"{skill.id} 命中反模式: {[f.rule_id for f in verdict.findings]}"
            )
            assert verdict.findings == []


# ===========================================================================
# 4. loader 校验 — 全量通过 + 逐条违规注入
# ===========================================================================
class TestLoaderValidation:
    """load_validation 六条规则 — 合法清单 0 errors, 每类违规各被拦截。"""

    def test_builtin_skills_validation_clean(self):
        """BUILTIN_SKILLS 全量校验通过 — 内置清单是契约的活样例。"""
        report = load_validation(BUILTIN_SKILLS)
        assert report.ok
        assert report.errors == []

    def test_duplicate_id_rejected(self):
        """规则 ①: 重复 id → 违规。"""
        report = load_validation([_make_skill(), _make_skill()])
        assert not report.ok
        assert any("重复" in e for e in report.errors)

    def test_empty_feature_gate_rejected(self):
        """规则 ②: feature_gate 为空 → 违规。"""
        report = load_validation([_make_skill(feature_gate="")])
        assert any("feature_gate 不能为空" in e for e in report.errors)

    def test_gate_format_mismatch_rejected(self):
        """规则 ②: gate 与 id 不自洽 → 违规。"""
        report = load_validation([_make_skill(feature_gate="skill.other-one.enabled")])
        assert any("不自洽" in e for e in report.errors)

    def test_type_a_with_prompt_rejected(self):
        """规则 ③: A 类带 prompt_template → 违规 (设计纪律 2)。"""
        report = load_validation([_make_skill(prompt_template="偷偷加摘要")])
        assert any("禁止 prompt_template" in e for e in report.errors)

    def test_type_c_missing_prompt_rejected(self):
        """规则 ④: C 类缺 prompt_template → 违规。"""
        report = load_validation(
            [_make_skill(skill_type="C", pipeline=_C_PIPELINE, target=None)]
        )
        assert any("缺 prompt_template" in e for e in report.errors)

    def test_type_c_missing_pipeline_rejected(self):
        """规则 ④: C 类缺 pipeline → 违规。"""
        report = load_validation(
            [
                _make_skill(
                    skill_type="C",
                    prompt_template="排序以下事件",
                    target=None,
                    pipeline=None,
                )
            ]
        )
        assert any("缺 pipeline" in e for e in report.errors)

    def test_target_pipeline_both_missing_rejected(self):
        """规则 ⑤: target 与 pipeline 都空 → 违规。"""
        report = load_validation([_make_skill(target=None, pipeline=None)])
        assert any("均为空" in e for e in report.errors)

    def test_target_pipeline_both_present_rejected(self):
        """规则 ⑤: target 与 pipeline 同时出现 → 违规 (契约规则 1)。"""
        report = load_validation(
            [_make_skill(skill_type="C", pipeline=_C_PIPELINE, prompt_template="x")]
        )
        assert any("同时出现" in e for e in report.errors)

    def test_type_a_with_pipeline_rejected(self):
        """规则 ⑦: A 类不允许 pipeline 编排 — A/B 只能 target 单步直调。"""
        report = load_validation(
            [_make_skill(pipeline=[_C_PIPELINE[0]], target=None)]
        )
        assert any("只允许 target 单步" in e for e in report.errors)

    def test_missing_module_rejected(self):
        """规则 ⑥: ServiceTarget.module 不存在 → 违规 (find_spec=None)。"""
        report = load_validation(
            [
                _make_skill(
                    target=ServiceTarget(
                        module="backend.services.no_such_module", method="x"
                    )
                )
            ]
        )
        assert any("不存在" in e for e in report.errors)

    def test_service_step_with_prompt_rejected(self):
        """契约规则 3 (步骤级): service 步携带 prompt_template → 违规。"""
        bad_pipeline = [
            replace(_C_PIPELINE[0], prompt_template="越权 prompt"),
            _C_PIPELINE[1],
            _C_PIPELINE[2],
        ]
        report = load_validation(
            [
                _make_skill(
                    skill_type="C",
                    pipeline=bad_pipeline,
                    target=None,
                    prompt_template="合法的 skill 级 prompt",
                )
            ]
        )
        assert any("service 步禁止 prompt_template" in e for e in report.errors)

    def test_register_rejects_invalid_skills(self):
        """register() 对违规清单整体拒绝 (SkillRegistryValidationError), 不部分注册。"""
        registry = SkillRegistry()
        with pytest.raises(SkillRegistryValidationError):
            registry.register([_make_skill(feature_gate="")])
        assert len(registry) == 0

    def test_register_validates_across_batches(self):
        """规则 ① 跨批次查重 — 第二批注册与存量同 id 仍被拦截。"""
        registry = SkillRegistry()
        registry.register([_make_skill()])
        with pytest.raises(SkillRegistryValidationError):
            registry.register([_make_skill()])


# ===========================================================================
# 5. registry 查询 — get / list
# ===========================================================================
class TestRegistryQuery:
    """get 命中/未命中 + list 分类过滤与启用态过滤。"""

    def test_get_returns_skill(self):
        """get(id) 命中 — 返回完整 SkillDef。"""
        skill = BUILTIN.get("source-health-scan")
        assert skill.id == "source-health-scan"
        assert skill.name == "信源质量巡检"
        assert skill.skill_type == "A"

    def test_get_unknown_raises(self):
        """get 未知 id 抛 SkillNotFoundError — fail loud, 不静默返回 None。"""
        with pytest.raises(SkillNotFoundError):
            BUILTIN.get("no-such-skill")

    def test_list_filter_by_category(self):
        """list(category=...) 只返回该分类 — compliance 恰 6 个。"""
        skills = BUILTIN.list(category="compliance")
        assert len(skills) == 6
        assert all(s.category == "compliance" for s in skills)

    def test_list_enabled_only_respects_gate(self, temp_db, monkeypatch):
        """enabled_only 过滤: 父 gate 开 + kv 写 True 的恰好在列。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: True,
        )
        BUILTIN.enable("daily-briefing")
        enabled = BUILTIN.list(enabled_only=True)
        assert [s.id for s in enabled] == ["daily-briefing"]

    def test_list_enabled_only_empty_when_gate_off(self, temp_db, monkeypatch):
        """父 gate 关 → enabled_only 恒空 (显式 monkeypatch, 不依赖 toml 默认:
        v0.8.1 Day 0 通电后 toml skill_registry=true, 父 gate 关闭语义由测试自持)。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: False,
        )
        BUILTIN.enable("daily-briefing")
        assert BUILTIN.list(enabled_only=True) == []


# ===========================================================================
# 6. enable/disable — settings kv 真实落库
# ===========================================================================
class TestEnableDisable:
    """enable/disable 写 settings.kv — 用真实 SettingsRepository 读回验证。"""

    def test_enable_writes_settings_kv_true(self, temp_db):
        """enable → settings 表 feature_gate key 写 True。"""
        BUILTIN.enable("source-health-scan")
        assert (
            SettingsRepository().get("skill.source-health-scan.enabled") is True
        )

    def test_disable_writes_settings_kv_false(self, temp_db):
        """disable → 同 key 显式写 False (与 enable 对称覆盖)。"""
        BUILTIN.enable("source-health-scan")
        BUILTIN.disable("source-health-scan")
        assert (
            SettingsRepository().get("skill.source-health-scan.enabled") is False
        )

    def test_enable_unknown_raises(self, temp_db):
        """enable 未知 id 抛 SkillNotFoundError — 不允许写无人认领的 kv key。"""
        with pytest.raises(SkillNotFoundError):
            BUILTIN.enable("no-such-skill")


# ===========================================================================
# 7. gate — is_skill_enabled 联合读数
# ===========================================================================
class TestSkillGate:
    """is_skill_enabled = settings kv AND 父扩展 gate。"""

    def test_kv_true_parent_true_enabled(self, temp_db, monkeypatch):
        """kv True + 父 gate True → True (唯一启用路径)。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: True,
        )
        BUILTIN.enable("source-health-scan")
        from backend.services.skill_registry.gate import is_skill_enabled

        assert is_skill_enabled("source-health-scan") is True

    def test_kv_false_parent_true_disabled(self, temp_db, monkeypatch):
        """kv 显式 False → False (父 gate 开也救不回显式停用)。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: True,
        )
        BUILTIN.disable("source-health-scan")
        from backend.services.skill_registry.gate import is_skill_enabled

        assert is_skill_enabled("source-health-scan") is False

    def test_kv_unset_defaults_disabled(self, temp_db, monkeypatch):
        """kv 未写 → 回落 default_enabled=False → False。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: True,
        )
        from backend.services.skill_registry.gate import is_skill_enabled

        assert is_skill_enabled("source-health-scan") is False

    def test_parent_gate_fail_closed(self, temp_db, monkeypatch):
        """父 gate 关 → False: is_extension_enabled 返回 False 时, kv 写 True
        也不放行 (fail-closed, 防漏登记即开放)。
        v0.8.1 Day 0 通电后 toml skill_registry=true — 父 gate 关闭语义由
        monkeypatch 显式自持, 不依赖 toml 默认。"""
        monkeypatch.setattr(
            "backend.services.skill_registry.gate.is_extension_enabled",
            lambda name: False,
        )
        BUILTIN.enable("source-health-scan")
        from backend.services.skill_registry.gate import is_skill_enabled

        assert is_skill_enabled("source-health-scan") is False

    def test_unknown_skill_raises(self, temp_db):
        """未知 skill_id 抛 SkillNotFoundError — gate 查询不吞掉调用方 bug。"""
        from backend.services.skill_registry.gate import is_skill_enabled

        with pytest.raises(SkillNotFoundError):
            is_skill_enabled("no-such-skill")
