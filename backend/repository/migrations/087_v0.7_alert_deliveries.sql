-- 087_v0.7_alert_deliveries.sql
-- D2 (Batch ⑧): 告警分发留痕表 — 每条 alert 投递到各 channel 的成功/失败/响应码

CREATE TABLE IF NOT EXISTS alert_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER,                              -- 可空: 写时还没拿到 (race condition)
    channel TEXT NOT NULL,                         -- webhook / email / slack / feishu / dingtalk
    ok INTEGER NOT NULL,                           -- 1=success, 0=failed
    status_code INTEGER,                            -- HTTP status (webhook/slack/feishu/dingtalk)
    error TEXT,                                    -- 异常 message (≤500 字符)
    delivered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert
    ON alert_deliveries(alert_id, delivered_at DESC);

CREATE INDEX IF NOT EXISTS idx_alert_deliveries_channel
    ON alert_deliveries(channel, delivered_at DESC);