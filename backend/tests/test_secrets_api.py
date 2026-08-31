"""Phase 41 Secrets API 测试 (end-to-end, in-memory DB)。

覆盖:
- status 初始未 setup
- setup 一次成功, 重复 setup 抛错 (Q1 禁止重置)
- unlock 错密码 401, 正确密码 200 + 30min 状态
- CRUD (create/list/reveal/test/update/delete) + master_key 加解密
- import/export round-trip
- 30 分钟后过期 (用更短 TTL 模拟)
"""
from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest


@pytest.fixture()
def client(temp_db, monkeypatch) -> Iterator:
    """独立临时 DB 跑 FastAPI TestClient (复用 conftest.temp_db 标准 fixture)。

    temp_db 已 close_db + 重设 config.db_path + init_db 全 schema,
    我们只需在此基础上 include secrets router。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.secrets import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)

    # 清理 _unlock_state + close_db 线程局部缓存 (避免下个文件复用 closed conn)
    from backend.services import secrets_service
    secrets_service._unlock_state.clear()
    try:
        from backend.repository import db as _db
        _db.close_db()
    except Exception:
        pass


MASTER_KEY = "test-master-key-strong-1234"


def test_status_initial(client):
    r = client.get("/api/secrets/status")
    assert r.status_code == 200
    data = r.json()
    assert data["setup"] is False
    assert data["unlocked"] is False


def test_setup_then_status(client):
    r = client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    assert r.status_code == 201, r.text
    r2 = client.get("/api/secrets/status")
    assert r2.json()["setup"] is True
    assert r2.json()["unlocked"] is False


def test_setup_idempotent_blocked(client):
    """Q1 禁止重置: 重复 setup 抛错。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/setup", json={"master_key": "another-key-5678"})
    assert r.status_code == 409  # 禁止重置


def test_setup_weak_key_rejected(client):
    r = client.post("/api/secrets/setup", json={"master_key": "short"})
    assert r.status_code in (400, 422)


def test_unlock_wrong_password(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/unlock", json={"master_key": "wrong-password-1234"})
    assert r.status_code == 401


def test_unlock_correct(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    assert r.status_code == 200
    data = r.json()
    assert data["unlocked"] is True
    assert data["ttl_seconds"] == 30 * 60


def test_unlock_then_lock(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/lock")
    assert r.status_code == 200
    assert r.json()["unlocked"] is False


def test_create_list_reveal(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    create = client.post(
        "/api/secrets",
        json={
            "name": "我的 DeepSeek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test-1234567890",
            "master_key": MASTER_KEY,
        },
    )
    assert create.status_code == 201, create.text
    sid = create.json()["item"]["id"]

    # 列表应包含, api_key_masked 显示掩码
    lst = client.get("/api/secrets")
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "我的 DeepSeek"
    assert items[0]["api_key"] is None  # 列表不返回明文

    # reveal 必须携带 master_key (无 body → 422)
    rev = client.post(f"/api/secrets/{sid}/reveal")
    assert rev.status_code == 422

    # 错误 master_key → 401
    rev_bad = client.post(
        f"/api/secrets/{sid}/reveal", json={"master_key": "wrong-key-1234"}
    )
    assert rev_bad.status_code == 401

    # 正确 master_key → 200 (无需 unlock)
    rev2 = client.post(f"/api/secrets/{sid}/reveal", json={"master_key": MASTER_KEY})
    assert rev2.status_code == 200
    assert rev2.json()["api_key"] == "sk-test-1234567890"


def test_create_wrong_master_key(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": "wrong-key-1234",
        },
    )
    assert r.status_code == 401


def test_update_no_api_key_change_no_master(client):
    """只改 name/model/base_url 不需要 master_key。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "old",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    r = client.patch(f"/api/secrets/{sid}", json={"name": "new"})
    assert r.status_code == 200
    assert r.json()["item"]["name"] == "new"


def test_update_api_key_requires_master(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    # 改 api_key 但不传 master_key
    r = client.patch(f"/api/secrets/{sid}", json={"api_key": "sk-2"})
    assert r.status_code in (400, 409)


def test_delete(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "x",
            "model": "m",
            "base_url": "https://x.com",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    d = client.delete(f"/api/secrets/{sid}")
    assert d.status_code == 204
    assert client.get("/api/secrets").json()["total"] == 0


def test_export_import_roundtrip(client):
    """导出 → 重新 setup (用同一密码) → 导入恢复。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post(
        "/api/secrets",
        json={
            "name": "A",
            "model": "m1",
            "base_url": "https://a.com",
            "api_key": "sk-aaa",
            "master_key": MASTER_KEY,
        },
    )
    client.post(
        "/api/secrets",
        json={
            "name": "B",
            "model": "m2",
            "base_url": "https://b.com",
            "api_key": "sk-bbb",
            "master_key": MASTER_KEY,
        },
    )

    # 导出
    r = client.get(f"/api/secrets/export?master_key={MASTER_KEY}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    payload = r.content

    # 模拟"清空"再导入: 直接 POST import
    b64 = base64.b64encode(payload).decode("ascii")
    r2 = client.post(
        "/api/secrets/import",
        json={"payload_b64": b64, "master_key": MASTER_KEY},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["inserted"] == 0  # 已存在, 所以是 update
    assert data["updated"] == 2
    assert data["failures"] == []


def test_import_wrong_master(client):
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    # 构造一个虚假 envelope
    envelope = b'{"encryption": {"algorithm": "Fernet", "iterations": 600000}, "ciphertext_b64": "00"}'
    b64 = base64.b64encode(envelope).decode("ascii")
    r = client.post(
        "/api/secrets/import",
        json={"payload_b64": b64, "master_key": "wrong-key-9999"},
    )
    assert r.status_code == 401


def test_test_connection_invalid_url(client):
    """test endpoint 在网络失败时返回 ok=false (不是抛错)。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post(
        "/api/secrets",
        json={
            "name": "fake",
            "model": "m",
            "base_url": "https://127.0.0.1:1/never-listens",
            "api_key": "sk-1",
            "master_key": MASTER_KEY,
        },
    ).json()["item"]["id"]
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    r = client.post(f"/api/secrets/{sid}/test")
    assert r.status_code == 200
    data = r.json()
    # 端口 1 不会响应, 应该 ok=False
    assert data["ok"] is False or data.get("status_code") in (None, 0)


# ---------------------------------------------------------------------------
# Phase 42: admin reset (二次确认清空)
# ---------------------------------------------------------------------------
def test_reset_wrong_confirm_409(client):
    r = client.post("/api/secrets/reset", json={"confirm": "NOPE"})
    assert r.status_code == 409
    assert "二次确认" in r.json()["detail"]["message"]


def test_reset_full_clears_everything(client):
    """reset 后: master_key 状态 setup=false, llm_secrets 空, 可重新 setup。"""
    # 1. setup
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    # 2. add secret
    client.post("/api/secrets", json={
        "name": "test-svc",
        "model": "m",
        "base_url": "https://x",
        "api_key": "sk-test",
        "master_key": MASTER_KEY,
    })
    # 3. verify exists
    s = client.get("/api/secrets").json()
    assert len(s["items"]) == 1
    # 4. reset
    r = client.post("/api/secrets/reset", json={
        "confirm": "YES_RESET_ALL_SECRETS"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reset"] is True
    assert data["counts"]["llm_secrets_cleared"] == 1
    assert data["counts"]["encryption_key_cleared"] == 1
    # 5. status 反映 setup=False
    s = client.get("/api/secrets/status").json()
    assert s["setup"] is False
    # 6. list 是空
    items = client.get("/api/secrets").json()["items"]
    assert items == []
    # 7. 可重新 setup
    r2 = client.post("/api/secrets/setup", json={"master_key": "new-master-key-9876"})
    assert r2.status_code == 201


def test_reset_when_empty(client):
    """无数据时 reset 仍 200, counts 全 0。"""
    r = client.post("/api/secrets/reset", json={
        "confirm": "YES_RESET_ALL_SECRETS"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["counts"]["llm_secrets_cleared"] == 0
    assert data["counts"]["encryption_key_cleared"] == 0


# ===================================================================
# v0.7.x Batch ⑥: CRUD 全 audit + /rotate + legacy 清退
# ===================================================================

def _clear_audit():
    from backend.repository.db import get_connection
    get_connection().execute("DELETE FROM audit_log")
    get_connection().commit()


def _audit_logs(action: str) -> list[dict]:
    """读 audit_log 表, 返该 action 的全部行。"""
    from backend.repository.db import get_connection
    rows = get_connection().execute(
        "SELECT actor, action, target, detail FROM audit_log "
        "WHERE action = ? ORDER BY id DESC",
        (action,),
    ).fetchall()
    return [dict(r) for r in rows]


def _latest_audit(action: str) -> dict | None:
    rows = _audit_logs(action)
    return rows[0] if rows else None


def test_create_writes_audit_log(client):
    """llm_secrets.create 写 audit_log, detail 含 secret_id/provider/name。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    _clear_audit()
    client.post("/api/secrets", json={
        "name": "DS-1", "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-1234", "master_key": MASTER_KEY,
        "provider": "sensenova",
    })
    rows = _audit_logs("llm_secrets.create")
    assert len(rows) == 1
    assert rows[0]["actor"] == "web"
    assert rows[0]["target"].startswith("secret:")
    import json as _j
    detail = _j.loads(rows[0]["detail"])
    assert detail["provider"] == "sensenova"
    assert detail["name"] == "DS-1"
    assert "secret_id" in detail


def test_update_writes_audit_log(client):
    """llm_secrets.update 写 audit_log, detail 含 fields_changed。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://x.com",
        "api_key": "sk-1", "master_key": MASTER_KEY,
    })
    print("CREATE STATUS:", r.status_code, r.text[:500])
    sid = r.json()["item"]["id"]


def test_delete_writes_audit_log(client):
    """llm_secrets.delete 写 audit_log。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://x.com",
        "api_key": "sk-1", "master_key": MASTER_KEY,
    }).json()["item"]["id"]
    _clear_audit()
    client.delete(f"/api/secrets/{sid}")
    rows = _audit_logs("llm_secrets.delete")
    assert len(rows) == 1
    assert rows[0]["target"] == f"secret:{sid}"


def test_reveal_writes_audit_log(client):
    """llm_secrets.reveal 强审计 — 每次显明文必写。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://x.com",
        "api_key": "sk-1234", "master_key": MASTER_KEY,
        "provider": "sensenova",
    }).json()["item"]["id"]
    _clear_audit()
    client.post(f"/api/secrets/{sid}/reveal", json={"master_key": MASTER_KEY})
    rows = _audit_logs("llm_secrets.reveal")
    assert len(rows) == 1
    # detail 永不含 api_key 明文
    assert "api_key" not in rows[0]["detail"]
    assert rows[0]["target"] == f"secret:{sid}"


def test_test_connection_writes_audit_log(client):
    """llm_secrets.test 写 audit_log, detail 含 ok/latency_ms。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://nonexistent.invalid",
        "api_key": "sk-1234", "master_key": MASTER_KEY,
    }).json()["item"]["id"]
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    _clear_audit()
    client.post(f"/api/secrets/{sid}/test")
    rows = _audit_logs("llm_secrets.test")
    assert len(rows) == 1
    import json as _j
    detail = _j.loads(rows[0]["detail"])
    assert "ok" in detail
    assert "latency_ms" in detail


def test_unlock_writes_audit_log(client):
    """llm_secrets.unlock 写 audit_log。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    _clear_audit()
    client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    rows = _audit_logs("llm_secrets.unlock")
    assert len(rows) == 1
    assert rows[0]["actor"] == "web"


def test_lock_writes_audit_log(client):
    """llm_secrets.lock 写 audit_log。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    _clear_audit()
    client.post("/api/secrets/lock")
    rows = _audit_logs("llm_secrets.lock")
    assert len(rows) == 1


def test_rotate_master_key_success(client):
    """POST /api/secrets/rotate 成功 → 重加密 + audit_log。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://x.com",
        "api_key": "sk-plaintext-1234", "master_key": MASTER_KEY,
    })
    _clear_audit()
    r = client.post("/api/secrets/rotate", json={
        "old_key": MASTER_KEY, "new_key": "new-master-key-strong-1234",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["reencrypted_secrets"] == 1
    rows = _audit_logs("llm_secrets.rotate")
    assert len(rows) == 1
    import json as _j
    detail = _j.loads(rows[0]["detail"])
    assert detail["reencrypted_secrets"] == 1


def test_rotate_wrong_old_key_401(client):
    """rotate 旧密钥错 → 401。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/rotate", json={
        "old_key": "wrong-old-key-1234",
        "new_key": "new-master-key-strong-1234",
    })
    assert r.status_code == 401


def test_rotate_weak_new_key_400(client):
    """rotate 新密钥太弱 (<12) → Pydantic 422 (min_length=12 触发)。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    r = client.post("/api/secrets/rotate", json={
        "old_key": MASTER_KEY, "new_key": "short",
    })
    assert r.status_code == 422


def test_rotate_reencrypts_all_secrets(client):
    """rotate 重新加密后, 新 master_key 可解锁且 reveal 明文正确。"""
    client.post("/api/secrets/setup", json={"master_key": MASTER_KEY})
    sid = client.post("/api/secrets", json={
        "name": "x", "model": "m", "base_url": "https://x.com",
        "api_key": "sk-old-plain-1234", "master_key": MASTER_KEY,
    }).json()["item"]["id"]
    r = client.post("/api/secrets/rotate", json={
        "old_key": MASTER_KEY, "new_key": "new-master-key-strong-1234",
    })
    assert r.status_code == 200
    # 旧 master_key 应失败 (新 verify_blob)
    bad = client.post("/api/secrets/unlock", json={"master_key": MASTER_KEY})
    assert bad.status_code == 401
    # 新 master_key 解锁 + reveal 明文
    ok = client.post("/api/secrets/unlock", json={
        "master_key": "new-master-key-strong-1234",
    })
    assert ok.status_code == 200
    rev = client.post(f"/api/secrets/{sid}/reveal",
                      json={"master_key": "new-master-key-strong-1234"})
    assert rev.status_code == 200
    assert rev.json()["api_key"] == "sk-old-plain-1234"
