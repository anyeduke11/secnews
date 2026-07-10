-- ============================================================================
-- 013_secrets.sql — Phase 41 密钥管理 (LLM API Keys)
--
-- 背景
-- ----
-- 用户需要集中管理 LLM 凭据 (OpenAI / Anthropic / DeepSeek / 自建 OpenAI
-- 兼容端点), 在 30 分钟内一键复制明文, 过期重新输入主密钥。
--
-- 设计要点
-- --------
-- - encryption_keys: 主密钥 (用户密码) 表, 单实例 (name='default')
--   派生算法 PBKDF2-HMAC-SHA256, salt + iterations 存 DB
--   verify_blob 是用派生 key 加密固定字符串的 ciphertext, 用于验证密码
-- - llm_secrets: 真实密钥表, api_key_encrypted 用 Fernet 加密 (派生 key)
-- - secret_access_logs: 审计日志 (可选, 记录 unlock/reveal/copy/lock)
--
-- 安全
-- ----
-- - 明文 master_key / api_key 永不写日志
-- - api_key_encrypted BLOB 不可逆推主密钥
-- - 主密钥不存 DB; 忘记 = 该主密钥下的 secret 永久不可解密
-- ============================================================================

CREATE TABLE IF NOT EXISTS encryption_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    salt        BLOB    NOT NULL,
    iterations  INTEGER NOT NULL DEFAULT 600000,
    verify_blob BLOB    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_secrets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    base_url          TEXT    NOT NULL,
    api_key_encrypted BLOB    NOT NULL,
    encryption_key_id INTEGER NOT NULL REFERENCES encryption_keys(id),
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_secrets_key_id ON llm_secrets(encryption_key_id);

CREATE TABLE IF NOT EXISTS secret_access_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    secret_id INTEGER,
    action    TEXT    NOT NULL,
    at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_secret_logs_at ON secret_access_logs(at DESC);
