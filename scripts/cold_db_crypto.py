"""T6.6: COLD db Fernet 加密 (文件级 envelope)。

设计
----
- 存储格式: ``hotspot-cold.db.enc`` = ``Fernet.encrypt(open(hotspot-cold.db, 'rb').read())``
  - 不试图 SQL-level 加密 (避免引入 SQLCipher 依赖)
  - 备份的 ``hotspot-cold.db`` 即密文, 离线安全
- 运行期:
  - 启动时若 ``config.cold_db_key`` 非空 AND ``hotspot-cold.db.enc`` 存在:
    解密到 tempfile, ATTACH tempfile 为 ``cold``
  - 关机时 (或 db_diet 后): tempfile 内容 re-encrypt → 覆盖 ``hotspot-cold.db.enc``
- 性能: cold 表读多为审计/历史查询, 不频繁; 启动期一次性解密 ~30MB 几秒

CLI:
    PYTHONPATH=. .venv/bin/python scripts/cold_db_crypto.py encrypt  # hotspot-cold.db → .enc
    PYTHONPATH=. .venv/bin/python scripts/cold_db_crypto.py decrypt  # .enc → tempfile
    PYTHONPATH=. .venv/bin/python scripts/cold_db_crypto.py verify   # 解密后跑 quick_check
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COLD_DB = REPO_ROOT / "backend" / "hotspot-cold.db"
COLD_ENC = REPO_ROOT / "backend" / "hotspot-cold.db.enc"


def get_fernet(master_key: str):
    """从 master_key 派生 Fernet。复用 backend.crypto._derive_key 接口。"""
    from backend.crypto import _derive_key, generate_salt

    if not master_key:
        raise SystemExit("HOTSPOT_COLD_DB_KEY not set (env var)")
    salt = generate_salt()
    key = _derive_key(master_key, salt, iterations=600_000)
    from cryptography.fernet import Fernet

    # 实际 salt 应该持久化 (env 或单独 .salt 文件); 这里用固定 salt + env key
    # 简化: 用 static salt (可接受 — master_key 已经是 secret)
    return Fernet(key)


def encrypt(src: Path = COLD_DB, dst: Path = COLD_ENC) -> int:
    """加密 src → dst, 返回密文字节数。"""
    master_key = os.environ.get("HOTSPOT_COLD_DB_KEY", "")
    if not master_key:
        raise SystemExit("HOTSPOT_COLD_DB_KEY not set")
    from cryptography.fernet import Fernet

    from backend.crypto import _derive_key, generate_salt

    salt = generate_salt()
    key = _derive_key(master_key, salt, iterations=600_000)
    fernet = Fernet(key)
    plain = src.read_bytes()
    token = fernet.encrypt(plain)
    # header: 16 bytes salt + Fernet token
    payload = salt + token
    dst.write_bytes(payload)
    print(f"encrypted: {src} ({len(plain)} B) → {dst} ({len(payload)} B)")
    return len(payload)


def decrypt_to_tempfile(src: Path = COLD_ENC, master_key: str | None = None) -> Path:
    """解密 src → tempfile, 返回 tempfile 路径 (caller 负责清理)。"""
    master_key = master_key or os.environ.get("HOTSPOT_COLD_DB_KEY", "")
    if not master_key:
        raise SystemExit("HOTSPOT_COLD_DB_KEY not set")
    from cryptography.fernet import Fernet, InvalidToken

    from backend.crypto import _derive_key

    payload = src.read_bytes()
    salt, token = payload[:16], payload[16:]
    key = _derive_key(master_key, salt, iterations=600_000)
    fernet = Fernet(key)
    try:
        plain = fernet.decrypt(token)
    except InvalidToken as e:
        raise SystemExit(f"decrypt failed (wrong master key or corrupted file): {e}") from e
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.write(plain)
    tf.close()
    return Path(tf.name)


def verify(tempfile_path: Path) -> bool:
    """解密后跑 quick_check + size sanity。"""
    conn = sqlite3.connect(str(tempfile_path))
    try:
        r = conn.execute("PRAGMA quick_check").fetchall()
        ok = all(row[0] == "ok" for row in r)
        size = tempfile_path.stat().st_size
        print(f"verify: quick_check={ok} size={size} B")
        return ok
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("encrypt")
    sub.add_parser("decrypt")
    sub.add_parser("verify")
    args = p.parse_args()

    if args.cmd == "encrypt":
        if not COLD_DB.exists():
            print(f"nothing to encrypt: {COLD_DB} not exists")
            return 0
        encrypt()
        return 0
    if args.cmd == "decrypt":
        if not COLD_ENC.exists():
            print(f"nothing to decrypt: {COLD_ENC} not exists")
            return 0
        tf = decrypt_to_tempfile()
        print(f"decrypted to: {tf}")
        print(f"size: {tf.stat().st_size} B")
        # 不删 tempfile, 留给 caller; 这里给个 cleanup 提示
        print(f"NOTE: clean up {tf} after use")
        return 0
    if args.cmd == "verify":
        if not COLD_ENC.exists():
            print(f"no encrypted cold db: {COLD_ENC}")
            return 1
        tf = decrypt_to_tempfile()
        try:
            ok = verify(tf)
            return 0 if ok else 2
        finally:
            tf.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
