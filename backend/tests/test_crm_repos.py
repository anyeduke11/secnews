"""CRM repos 单测 (migration 071): 客户 CRUD / 商机状态机 / 事件留痕。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """独立临时 SQLite + 071 迁移 + get_connection 打桩 (仿 test_sync_api)。"""
    db_file = tmp_path / "test_crm.db"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        Path("backend/repository/migrations/071_crm_cockpit.sql").read_text(encoding="utf-8")
    )
    import backend.repository.crm_customer_repo as cust_mod
    import backend.repository.crm_opportunity_repo as opp_mod
    from backend.repository import db as db_mod

    # repo 模块是 `from ..db import get_connection` 名字绑定, 必须 patch 到
    # 各 repo 模块本身, 只 patch db_mod 不生效 (P2-2 sync.py 同款教训)
    for mod in (db_mod, cust_mod, opp_mod):
        monkeypatch.setattr(mod, "get_connection", lambda: conn, raising=True)
    yield conn
    conn.close()


class TestCustomerRepo:
    def test_create_get_defaults(self, db):
        from backend.repository import crm_customer_repo as cust

        row = cust.create({"name": "招商银行"})
        assert row.id > 0 and row.name == "招商银行"
        assert row.industry == "其他" and row.level == "B" and row.status == "活跃"
        assert row.contract_amount == 0.0 and row.nps_score is None
        fetched = cust.get(row.id)
        assert fetched is not None and fetched.name == "招商银行"

    def test_duplicate_name_raises(self, db):
        from backend.repository import crm_customer_repo as cust
        from backend.repository.crm_customer_repo import CrmCustomerExistsError

        cust.create({"name": "重复客户"})
        with pytest.raises(CrmCustomerExistsError):
            cust.create({"name": "重复客户"})

    def test_list_filters_and_search_ordering(self, db):
        from backend.repository import crm_customer_repo as cust

        a = cust.create({"name": "甲证券", "industry": "证券", "status": "活跃"})
        b = cust.create({"name": "乙银行", "industry": "银行", "status": "流失"})
        assert {c.id for c in cust.list_all()} >= {a.id, b.id}
        assert all(c.industry == "证券" for c in cust.list_all(industry="证券"))
        assert [c.name for c in cust.list_all(q="乙")] == ["乙银行"]
        # updated_at DESC: 新建的乙银行排最前
        assert cust.list_all()[0].id == b.id

    def test_update_partial_and_delete(self, db):
        from backend.repository import crm_customer_repo as cust

        row = cust.create({"name": "升级客户", "level": "B"})
        upd = cust.update(row.id, {"level": "S", "nps_score": 9, "contract_amount": 120000})
        assert upd.level == "S" and upd.nps_score == 9 and upd.contract_amount == 120000.0
        assert upd.name == "升级客户"  # 未传字段不动
        assert cust.delete(row.id) is True
        assert cust.get(row.id) is None


class TestOpportunityStateMachine:
    def _mk_opp(self, name="等保测评商机"):
        from backend.repository import crm_customer_repo as cust
        from backend.repository import crm_opportunity_repo as opp_repo

        c = cust.create({"name": f"客户-{name}"})
        return opp_repo.create({"customer_id": c.id, "name": name, "amount": 500000})

    def test_create_default_stage_and_event(self, db):
        from backend.repository import crm_opportunity_repo as opp_repo

        o = self._mk_opp()
        assert o.stage == "需求沟通"
        evs = opp_repo.events(o.id)
        assert evs[0]["to_stage"] == "需求沟通" and evs[0]["from_stage"] is None

    def test_happy_path_to_win_sets_won_at(self, db):
        from backend.repository import crm_opportunity_repo as opp_repo

        o = self._mk_opp()
        for stage in ("方案提交", "商务谈判", "合同签订", "赢单"):
            o = opp_repo.transition(o.id, stage)
        assert o.stage == "赢单" and o.won_at is not None
        assert len(opp_repo.events(o.id)) == 5  # created + 4 迁移

    def test_skip_transition_rejected(self, db):
        from backend.repository import crm_opportunity_repo as opp_repo
        from backend.repository.crm_opportunity_repo import InvalidTransitionError

        o = self._mk_opp("跳跃商机")
        with pytest.raises(InvalidTransitionError, match="需求沟通"):
            opp_repo.transition(o.id, "合同签订")

    def test_terminal_stage_frozen(self, db):
        from backend.repository import crm_opportunity_repo as opp_repo
        from backend.repository.crm_opportunity_repo import InvalidTransitionError

        o = self._mk_opp("终态商机")
        opp_repo.transition(o.id, "方案提交")
        opp_repo.transition(o.id, "输单", lost_reason="预算砍掉")
        assert opp_repo.get(o.id).lost_reason == "预算砍掉"
        with pytest.raises(InvalidTransitionError):
            opp_repo.transition(o.id, "需求沟通")

    def test_update_fields_cannot_change_stage(self, db):
        """改阶段唯一入口是 transition — update_fields 白名单不含 stage。"""
        from backend.repository import crm_opportunity_repo as opp_repo

        o = self._mk_opp("白名单商机")
        upd = opp_repo.update_fields(o.id, {"stage": "赢单", "amount": 888888})
        assert upd.stage == "需求沟通"  # stage 被忽略
        assert upd.amount == 888888.0

    def test_delete_customer_cascades_opportunities(self, db):
        from backend.repository import crm_customer_repo as cust
        from backend.repository import crm_opportunity_repo as opp_repo

        o = self._mk_opp("级联商机")
        cust.delete(o.customer_id)
        assert opp_repo.get(o.id) is None
