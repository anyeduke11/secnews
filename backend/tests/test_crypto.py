"""Phase 41 加密模块测试 (backend.crypto)。

覆盖:
- salt 长度
- weak master_key 拒绝
- make_verify_blob → verify_master_key 成功 round-trip
- 错密码 verify 失败 (返回 False)
- 派生 key 跨调用一致 (salt + iterations + password 相同)
- encrypt/decrypt round-trip
- 篡改密文 → InvalidToken / CryptoError
"""
from __future__ import annotations

import pytest

from backend.crypto import (
    CryptoError,
    DEFAULT_ITERATIONS,
    InvalidMasterKeyError,
    WeakMasterKeyError,
    decrypt_api_key,
    derive_fernet_key,
    encrypt_api_key,
    generate_salt,
    make_verify_blob,
    verify_master_key,
)


def test_generate_salt_length():
    salt = generate_salt()
    assert isinstance(salt, bytes)
    assert len(salt) == 16


def test_generate_salt_unique():
    s1 = generate_salt()
    s2 = generate_salt()
    assert s1 != s2  # 几乎不可能相同


def test_make_verify_blob_and_verify():
    salt = generate_salt()
    mk = "my-strong-master-key"
    blob = make_verify_blob(mk, salt, DEFAULT_ITERATIONS)
    assert isinstance(blob, bytes) and len(blob) > 0
    assert verify_master_key(mk, salt, DEFAULT_ITERATIONS, blob) is True


def test_verify_wrong_password():
    salt = generate_salt()
    blob = make_verify_blob("correct-password-1234", salt, DEFAULT_ITERATIONS)
    assert verify_master_key("wrong-password-1234", salt, DEFAULT_ITERATIONS, blob) is False


def test_weak_master_key_rejected():
    salt = generate_salt()
    with pytest.raises(WeakMasterKeyError):
        make_verify_blob("short", salt, DEFAULT_ITERATIONS)


def test_derive_key_consistency():
    salt = generate_salt()
    k1 = derive_fernet_key("password-1234", salt, DEFAULT_ITERATIONS)
    k2 = derive_fernet_key("password-1234", salt, DEFAULT_ITERATIONS)
    assert k1 == k2  # 同一密码 + salt + iter → 同一 key


def test_derive_key_differs_by_salt():
    k1 = derive_fernet_key("password-1234", generate_salt(), DEFAULT_ITERATIONS)
    k2 = derive_fernet_key("password-1234", generate_salt(), DEFAULT_ITERATIONS)
    assert k1 != k2  # 不同 salt → 不同 key


def test_encrypt_decrypt_roundtrip():
    salt = generate_salt()
    fk = derive_fernet_key("password-1234", salt, DEFAULT_ITERATIONS)
    plaintext = "sk-1234567890abcdef"
    cipher = encrypt_api_key(fk, plaintext)
    assert cipher != plaintext.encode()
    out = decrypt_api_key(fk, cipher)
    assert out == plaintext


def test_decrypt_wrong_key():
    salt = generate_salt()
    fk1 = derive_fernet_key("password-A-1234", salt, DEFAULT_ITERATIONS)
    fk2 = derive_fernet_key("password-B-1234", salt, DEFAULT_ITERATIONS)
    cipher = encrypt_api_key(fk1, "sk-abcdef")
    with pytest.raises((InvalidMasterKeyError, CryptoError)):
        decrypt_api_key(fk2, cipher)


def test_decrypt_tampered_ciphertext():
    salt = generate_salt()
    fk = derive_fernet_key("password-1234", salt, DEFAULT_ITERATIONS)
    cipher = encrypt_api_key(fk, "sk-abcdef")
    tampered = bytes(b ^ 0xFF for b in cipher[:5]) + cipher[5:]
    with pytest.raises((InvalidMasterKeyError, CryptoError)):
        decrypt_api_key(fk, tampered)
