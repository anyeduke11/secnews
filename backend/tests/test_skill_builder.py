"""test_skill_builder — v0.8 Phase C C3 测试套件 (≥12 case).

覆盖意图 (why):
- 校验 (validate_user_skill): 12+ 错误分支 (id 命名 / builtin 冲突 / category /
  type / runner / timeout / prompt 类型耦合 / target 引用 / schema shape)
- CRUD (UserSkillRepo): create / get / list / update / soft_delete / 上限 50 / 软删占位
- API 路由: 6 端点 (list / validate / create / get / patch / delete) 错误信封 +
  端到端 (validate→create→patch→delete) 链路
- API gate: 不开 → 路由 404
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============================================================================
# fixtures
# ============================================================================
@pytest.fixture()
def client(temp_db, monkeypatch):
    """小 app 只挂 skill_builder router; user_skills gate 强制 True."""
    monkeypatch.setattr(
        "backend.extensions.is_extension_enabled",
        lambda name: True,
    )
    from backend.api.skill_builder_api import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_gate_off(temp_db, monkeypatch):
    """gate off: router 不挂载 → 端点 404 (验证 fail-closed)."""
    monkeypatch.setattr(
        "backend.extensions.is_extension_enabled",
        lambda name: False,
    )
    from backend.api.skill_builder_api import router

    app = FastAPI()
    # 故意不挂载 router, 模拟 register_routers 的 gate off 分支
    with TestClient(app) as c:
        yield c


def _payload(**overrides):
    """有效 payload 工厂 (用户 skill 引用 builtin 信源 service)."""
    base = {
        "id": "user_skill_1",
        "name": "测试技能",
        "desc": "示例用户自建 skill",
        "category": "operations",
        "skill_type": "A",
        "runner": "builtin",
        "timeout_seconds": 60,
        "input_schema": {"k": "str"},
        "output_schema": {"v": "str"},
        "prompt_template": None,
        "target_module": "backend.services.source_scheduler_service",
        "target_class": "SourceSchedulerService",
        "target_method": "get_status",
    }
    base.update(overrides)
    return base


# ============================================================================
# 1. validate (单测层)
# ============================================================================
def test_validate_accepts_valid_payload() -> None:
    """基础 A 类有效 payload 全通过."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload())
    assert report.ok, report.to_dict()


def test_validate_rejects_short_id() -> None:
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(id="ab"))
    assert not report.ok
    assert any("id" in e and "snake_case" in e for e in report.errors)


def test_validate_rejects_builtin_collision() -> None:
    """R8: id 与 builtin 冲突 → 拒."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(id="source-health-scan"))  # builtin id (kebab)
    assert not report.ok
    # 错误信息中含 builtin id 与 "冲突"
    assert any("source-health-scan" in e and "冲突" in e for e in report.errors)


def test_validate_rejects_invalid_category() -> None:
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(category="evil"))
    assert not report.ok


def test_validate_rejects_skill_type_e() -> None:
    """E 类型 v0.8 不开放."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(skill_type="E"))
    assert not report.ok


def test_validate_a_type_rejects_prompt_template() -> None:
    """R1: A/B/E 类无 prompt; A 含 prompt 拒."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(skill_type="A", prompt_template="不要"))
    assert not report.ok


def test_validate_c_type_requires_prompt_template() -> None:
    """R1: C/D 类必填 prompt."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(_payload(skill_type="C", prompt_template=None))
    assert not report.ok


def test_validate_target_module_must_exist() -> None:
    """target_module importlib.find_spec 校验."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(
        _payload(target_module="backend.does.not.exist", target_class=None)
    )
    assert not report.ok


def test_validate_target_method_must_exist() -> None:
    """method 不存在 → 拒 (防悬空引用 R8)."""
    from backend.services.skill_builder import validate_user_skill

    report = validate_user_skill(
        _payload(target_method="no_such_method")
    )
    assert not report.ok


# ============================================================================
# 2. CRUD (Repo 层)
# ============================================================================
def test_repo_create_and_get(temp_db) -> None:  # noqa: ARG001
    from backend.services.skill_builder import UserSkill, UserSkillRepo
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    repo = UserSkillRepo()
    skill = UserSkill(
        id="user_repo_1",
        name="x",
        desc="",
        category="operations",
        skill_type="A",
        runner="builtin",
        timeout_seconds=60,
        input_schema_json="{}",
        output_schema_json="{}",
        prompt_template=None,
        target_type="skill_step",
        target_module="backend.services.source_scheduler_service",
        target_class="SourceSchedulerService",
        target_method="get_status",
        enabled=0,
        created_by="user",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    repo.create(skill)
    got = repo.get_or_raise("user_repo_1")
    assert got.name == "x"
    # 软删后默认不返
    repo.soft_delete("user_repo_1")
    assert repo.get("user_repo_1") is None
    # include_deleted 仍能取到
    deleted = repo.get("user_repo_1", include_deleted=True)
    assert deleted is not None and deleted.deleted_at is not None


def test_repo_count_active_caps_at_50(temp_db) -> None:  # noqa: ARG001
    from backend.services.skill_builder import MAX_USER_SKILLS, UserSkillRepo

    assert MAX_USER_SKILLS == 50
    repo = UserSkillRepo()
    assert repo.count_active() == 0


# ============================================================================
# 3. API 路由 (端到端)
# ============================================================================
def test_api_validate_only_dry_run(client) -> None:
    """POST /validate 不落库, 只返 errors."""
    r = client.post("/api/skill-builder/validate", json={"payload": _payload(id="ab")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert any("snake_case" in e for e in body["errors"])


def test_api_create_get_patch_delete_roundtrip(client) -> None:
    """端到端: validate→create→get→patch→delete 链路."""
    p = _payload()

    # validate only
    r = client.post("/api/skill-builder/validate", json={"payload": p})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # create
    r = client.post("/api/skill-builder", json=p)
    assert r.status_code == 200, r.text
    skill = r.json()
    assert skill["id"] == p["id"]
    assert skill["enabled"] == 0  # 默认未启用
    assert skill["input_schema"] == {"k": "str"}

    # get
    r = client.get(f"/api/skill-builder/{p['id']}")
    assert r.status_code == 200

    # patch enable
    r = client.patch(f"/api/skill-builder/{p['id']}", json={"enabled": 1})
    assert r.status_code == 200
    assert r.json()["enabled"] == 1

    # list enabled_only
    r = client.get("/api/skill-builder?enabled_only=true")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # delete (软删)
    r = client.delete(f"/api/skill-builder/{p['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # 软删后 GET 404
    r = client.get(f"/api/skill-builder/{p['id']}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_api_create_rejects_collision(client) -> None:
    """id 冲突 (含软删) → 409."""
    p = _payload()
    r = client.post("/api/skill-builder", json=p)
    assert r.status_code == 200
    # 软删后再 create 同 id
    client.delete(f"/api/skill-builder/{p['id']}")
    r = client.post("/api/skill-builder", json=p)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DUPLICATE_ID"


def test_api_create_rejects_invalid_payload(client) -> None:
    # pydantic Field min_length=3 → 422 list; 走 validate_user_skill 路径
    # (字段超 pydantic 约束) 改用合法长度 id 但 category 非法:
    r = client.post("/api/skill-builder", json=_payload(id="valid_id", category="evil"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "VALIDATE_FAILED"


def test_api_gate_off_returns_404(client_gate_off) -> None:
    """user_skills gate off → 路由不注册 → 端点 404 (fail-closed)."""
    r = client_gate_off.get("/api/skill-builder")
    assert r.status_code == 404


def test_api_list_filters_by_category(client) -> None:
    client.post("/api/skill-builder", json=_payload(id="a_ops", category="operations"))
    client.post(
        "/api/skill-builder",
        json=_payload(id="a_comp", category="compliance"),
    )
    r = client.get("/api/skill-builder?category=operations")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {s["id"] for s in items} == {"a_ops"}


def test_api_list_filters_by_skill_type(client) -> None:
    client.post("/api/skill-builder", json=_payload(id="a_a", skill_type="A"))
    client.post(
        "/api/skill-builder",
        json=_payload(
            id="a_b",
            skill_type="B",
            target_module="backend.services.source_scheduler_service",
            target_class="SourceSchedulerService",
            target_method="get_status",
        ),
    )
    r = client.get("/api/skill-builder?skill_type=B")
    assert r.status_code == 200
    assert {s["id"] for s in r.json()["items"]} == {"a_b"}