-- 104_v10_outbox.sql
-- v1.0 C11 R18: 业务事务写 outbox, 后台 dispatcher 广播 + 持久化重放
-- 设计:
--   - 主键 id 整数自增, 严格单调, SSE 客户端用 last_id 续传
--   - aggregate_type+aggregate_id 便于按对象失效前端缓存
--   - revision 让前端能识别 CAS 漂移 + 丢弃过期重放
--   - payload_json + event_type + trace_id 业务自描述
--   - delivered_at NULL = 未广播, dispatcher 轮询取 NULL 段
--   - (occurred_at, id) 二级索引让 list_since 单边扫描
CREATE TABLE IF NOT EXISTS v1_outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT    NOT NULL,
    aggregate_type  TEXT    NOT NULL,   -- case | judgment | action | run | artifact | knowledge | signal
    aggregate_id    TEXT    NOT NULL,
    revision        INTEGER NOT NULL DEFAULT 0,
    payload_json    TEXT    NOT NULL,
    trace_id        TEXT    NOT NULL,
    occurred_at     TEXT    NOT NULL,
    delivered_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_v1_outbox_undelivered
    ON v1_outbox(id) WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_v1_outbox_aggregate
    ON v1_outbox(aggregate_type, aggregate_id, id);
CREATE INDEX IF NOT EXISTS idx_v1_outbox_trace
    ON v1_outbox(trace_id);
