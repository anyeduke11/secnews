"""Phase 41 密钥加密模块: PBKDF2 派生 + Fernet 加密。

设计要点
--------
- **算法选择**: Fernet (AES-128-CBC + HMAC-SHA256) — `cryptography` 标准库,
  自带认证加密 (AEAD), 密文篡改会抛 InvalidToken。
- **密钥派生**: PBKDF2-HMAC-SHA256(password, salt, iterations=600_000)
  OWASP 2023 推荐参数。
- **salt**: 每个 encryption_key 一份, 16 字节随机 (secrets.token_bytes)。
- **verify_blob**: 用派生 key 加密一段固定明文 (e.g. "verify-ok-v1"),
  后续 unlock 时尝试解密来验证密码, 比直接比对 hash 慢一些, 但复用
  Fernet 接口, 不需要额外的 HMAC 编码。

安全原则
--------
- 不接受弱口令 (长度 < 8 抛错)。
- 所有函数 fail-fast: 输入错误立即抛 InvalidToken / ValueError。
- 永远不打印 master_key / api_key / decrypted plaintext。
"""
from __future__ import annotations

import base64
import secrets
from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 派生 key 用 Fernet 期望的 32 字节 base64-url 编码形式
KDF_KEY_LENGTH: Final = 32
SALT_LENGTH: Final = 16
DEFAULT_ITERATIONS: Final = 600_000
MIN_MASTER_KEY_LENGTH: Final = 8
_VERIFY_PLAINTEXT: Final = b"hotspot-secrets:verify-ok:v1"


class CryptoError(Exception):
    """加密/解密错误基类 (用于 service 层转 HTTPException)。"""


class WeakMasterKeyError(CryptoError):
    """主密钥长度不足。"""


class InvalidMasterKeyError(CryptoError):
    """主密钥错误 (verify_blob 解密失败)。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def generate_salt() -> bytes:
    """生成 16 字节随机 salt。"""
    return secrets.token_bytes(SALT_LENGTH)


def _derive_key(master_key: str, salt: bytes, iterations: int) -> bytes:
    """PBKDF2-HMAC-SHA256 → 32 字节 base64-url-encoded key (Fernet 期望格式)。"""
    if not isinstance(master_key, str) or not master_key:
        raise CryptoError("master_key 必须为非空字符串")
    if len(master_key) < MIN_MASTER_KEY_LENGTH:
        raise WeakMasterKeyError(
            f"主密钥长度必须 >= {MIN_MASTER_KEY_LENGTH} 字符"
        )
    if not isinstance(salt, (bytes, bytearray)) or len(salt) != SALT_LENGTH:
        raise CryptoError(f"salt 必须为 {SALT_LENGTH} 字节")
    if iterations < 100_000:
        raise CryptoError(f"iterations 必须 >= 100000 (收到 {iterations})")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KDF_KEY_LENGTH,
        salt=salt,
        iterations=iterations,
    )
    raw = kdf.derive(master_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _fernet(key_b64: bytes) -> Fernet:
    return Fernet(key_b64)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def make_verify_blob(master_key: str, salt: bytes, iterations: int) -> bytes:
    """创建 verify_blob: 用派生 key 加密固定明文。

    返回 ciphertext bytes, 存到 ``encryption_keys.verify_blob``。
    """
    key = _derive_key(master_key, salt, iterations)
    return _fernet(key).encrypt(_VERIFY_PLAINTEXT)


def verify_master_key(master_key: str, salt: bytes, iterations: int, verify_blob: bytes) -> bool:
    """验证 master_key: 解密 verify_blob 并比对固定明文。

    成功 → True; 失败 → False (不抛错, 让 service 层决定 401 响应)。
    """
    try:
        key = _derive_key(master_key, salt, iterations)
        plaintext = _fernet(key).decrypt(verify_blob)
        return plaintext == _VERIFY_PLAINTEXT
    except (InvalidToken, CryptoError, ValueError):
        return False


def derive_fernet_key(master_key: str, salt: bytes, iterations: int) -> bytes:
    """验证通过后, 派生 Fernet key (用于后续 encrypt/decrypt secret)。"""
    return _derive_key(master_key, salt, iterations)


def encrypt_api_key(fernet_key: bytes, api_key: str) -> bytes:
    """加密 api_key 明文 → ciphertext bytes。"""
    if not isinstance(api_key, str) or not api_key:
        raise CryptoError("api_key 必须为非空字符串")
    return _fernet(fernet_key).encrypt(api_key.encode("utf-8"))


def decrypt_api_key(fernet_key: bytes, ciphertext: bytes) -> str:
    """解密 ciphertext → api_key 明文。

    失败 (改密文/错 key) → 抛 InvalidToken, 转 CryptoError。
    """
    try:
        plaintext = _fernet(fernet_key).decrypt(ciphertext)
    except InvalidToken as e:
        raise InvalidMasterKeyError("api_key 解密失败: 主密钥错误或密文损坏") from e
    return plaintext.decode("utf-8")


__all__ = [
    "CryptoError",
    "WeakMasterKeyError",
    "InvalidMasterKeyError",
    "generate_salt",
    "make_verify_blob",
    "verify_master_key",
    "derive_fernet_key",
    "encrypt_api_key",
    "decrypt_api_key",
    "DEFAULT_ITERATIONS",
    "MIN_MASTER_KEY_LENGTH",
]
