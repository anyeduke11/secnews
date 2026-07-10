-- ============================================================================
-- 014_sync.sql — Phase 42 跨端配置同步 (WebDAV / Nutstore)
--
-- 背景
-- ----
-- 用户在多台设备 (macbook / iPad / 公司电脑) 间需要同步
-- 收藏 / 待办 / Skill / 自定义信源 / 质量门禁 / 密钥元数据。
-- 选用 WebDAV (坚果云自带) 作为载体, 整个 bundle 加密后 PUT 到云端。
--
-- 设计要点
-- --------
-- - sync_configs: 单实例 (name='default'), 存 WebDAV 凭据 (独立 salt 加密)
-- - sync_history: 每次同步的审计日志 (push/pull/both + status)
-- - sync_states: 上次同步后的 merged bundle (作为 3-way merge 的 base)
-- - 时区: 服务器内部用 UTC, 调度时转 Asia/Shanghai
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_configs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    name                        TEXT    NOT NULL UNIQUE DEFAULT 'default',
    webdav_url                  TEXT,
    webdav_username             TEXT,
    webdav_password_encrypted   BLOB,                       -- Fernet ciphertext
    webdav_password_salt        BLOB,                       -- 16 字节, 独立 salt
    webdav_password_iters       INTEGER NOT NULL DEFAULT 600000,
    remote_path                 TEXT    NOT NULL DEFAULT '/hotspot/config.json',
    auto_sync_enabled           INTEGER NOT NULL DEFAULT 0,
    auto_sync_interval_minutes  INTEGER NOT NULL DEFAULT 10080,    -- 7 天 = 10080 分钟
    last_sync_at                TEXT,
    last_sync_status            TEXT,                       -- success | error | never
    last_sync_error             TEXT,
    last_sync_direction         TEXT,                       -- push | pull | bidirectional
    device_id                   TEXT,                       -- 本机唯一 ID (首次启动生成)
    created_at                  TEXT    NOT NULL,
    updated_at                  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id       INTEGER NOT NULL REFERENCES sync_configs(id),
    direction       TEXT    NOT NULL,                      -- push | pull | bidirectional
    status          TEXT    NOT NULL,                      -- success | error
    records_count   INTEGER,                               -- 同步了多少条记录
    conflict_count  INTEGER NOT NULL DEFAULT 0,            -- 冲突数 (3-way merge 时)
    error_message   TEXT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_history_config ON sync_history(config_id, started_at DESC);

CREATE TABLE IF NOT EXISTS sync_states (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id       INTEGER NOT NULL REFERENCES sync_configs(id) UNIQUE,
    bundle_json     TEXT    NOT NULL,                      -- 上次同步后的 merged bundle (明文 JSON, 用于 3-way merge)
    merged_at       TEXT    NOT NULL                       -- 合并时间
);
