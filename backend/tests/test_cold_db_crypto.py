"""cold_db_crypto.py 契约测试 — v0.6 P0 清场第二批 commit 7。

覆盖 verify 端到端三种路径:
  1. missing 路径: 无 .enc 文件 → exit 1 (源码 main L130-132 行为)
  2. 真实 envelope 链: 明文 db → encrypt → .enc → decrypt → verify quick_check ok
  3. 错误 master_key: .enc 存在但密钥错 → exit + 'decrypt failed'

cold_db_crypto.py 模块级常量 COLD_DB / COLD_ENC 解析到 REPO_ROOT/backend/,
不依赖 cwd. 测试用 fixture 落到 backend/ 测试路径, 测试结束清理.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "cold_db_crypto.py"
BACKEND = REPO_ROOT / "backend"
COLD_DB = BACKEND / "hotspot-cold.db"
COLD_ENC = BACKEND / "hotspot-cold.db.enc"

TEST_KEY = "test-cold-db-master-key-fixture"


def _run_cli(
    *args: str,
    env_key: str = TEST_KEY,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """跑 cold_db_crypto.py, 注入 HOTSPOT_COLD_DB_KEY."""
    env = {**os.environ, "HOTSPOT_COLD_DB_KEY": env_key, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def cold_workspace():
    """准备明文 COLD db, 测试结束清理 .db / .enc 测试残留.

    若 backend/hotspot-cold.db 已存在 (例如本机其他测试残留), 不动它,
    直接跳过本测试 (assume_clean=False 默认为 False).
    """
    if COLD_DB.exists() or COLD_ENC.exists():
        pytest.skip(
            "backend/hotspot-cold.db(.enc) 已存在, 跳过以免覆盖真实数据"
        )
    # 写一份测试明文 db
    conn = sqlite3.connect(str(COLD_DB))
    conn.execute("CREATE TABLE cold_demo (id INTEGER PRIMARY KEY, payload TEXT)")
    conn.execute(
        "INSERT INTO cold_demo VALUES (1, 'cold-encrypted-row'), (2, 'verify-target')"
    )
    conn.commit()
    conn.close()
    try:
        yield COLD_DB
    finally:
        # 清理测试残留
        COLD_ENC.unlink(missing_ok=True)
        COLD_DB.unlink(missing_ok=True)


def test_verify_missing_enc_exits_1() -> None:
    """无 .enc 文件: verify 退 1 (源码 main L130-132 行为)."""
    # 若真实 .enc 存在 (本机已有 COLD 加密数据), 跳过本用例
    if COLD_ENC.exists():
        pytest.skip(f"{COLD_ENC} 已存在, 跳过 missing 分支")
    proc = _run_cli("verify")
    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "no encrypted cold db" in proc.stdout


def test_encrypt_decrypt_verify_roundtrip(cold_workspace: Path) -> None:
    """完整 envelope 链: 明文 db → encrypt → .enc → decrypt → verify quick_check ok."""
    plain_bytes = COLD_DB.read_bytes()

    # 1. CLI encrypt → .enc
    proc_enc = _run_cli("encrypt")
    assert proc_enc.returncode == 0, proc_enc.stderr
    assert COLD_ENC.exists()
    enc_bytes = COLD_ENC.read_bytes()
    # Fernet token 至少 100+ bytes; 密文 != 明文
    assert enc_bytes != plain_bytes
    assert len(enc_bytes) > len(plain_bytes)  # envelope 体积略增

    # 2. CLI verify → quick_check 应 ok (return 0)
    proc_verify = _run_cli("verify")
    assert proc_verify.returncode == 0, proc_verify.stderr
    assert "quick_check" in proc_verify.stdout

    # 3. CLI decrypt → tempfile, 二次确认内容完整
    proc_dec = _run_cli("decrypt")
    assert proc_dec.returncode == 0, proc_dec.stderr
    assert "decrypted to" in proc_dec.stdout
    tf_line = next(
        ln for ln in proc_dec.stdout.splitlines() if ln.startswith("decrypted to")
    )
    tf_path = Path(tf_line.split(":", 1)[1].strip())
    try:
        conn2 = sqlite3.connect(str(tf_path))
        rows = conn2.execute(
            "SELECT payload FROM cold_demo ORDER BY id"
        ).fetchall()
        conn2.close()
        assert rows == [("cold-encrypted-row",), ("verify-target",)]
    finally:
        tf_path.unlink(missing_ok=True)


def test_verify_wrong_master_key_exits(cold_workspace: Path) -> None:
    """错 master_key: decrypt 应 SystemExit('decrypt failed'); 模拟 .enc 是用
    A 密钥加密的, 用 B 密钥解密."""
    # 1. 用真 key 加密一份
    proc_enc = _run_cli("encrypt")
    assert proc_enc.returncode == 0

    # 2. 切到错的 master_key, 跑 verify → decrypt 阶段 SystemExit
    proc_bad = _run_cli("verify", env_key="WRONG-key-fixture-should-fail")
    assert proc_bad.returncode != 0
    combined = proc_bad.stdout + proc_bad.stderr
    assert "decrypt failed" in combined
