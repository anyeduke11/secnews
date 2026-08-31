-- 079_v0.7_llm_usage_log_cols.sql
-- v0.7 Observability Batch 1: llm_usage_log 加列, 失败路径持久化 + 真实 metrics。
--
-- 现状 (052_v1.7_llm_cache.sql:20-33):
--   llm_usage_log(provider, model, task, tokens, cost_usd, latency_ms, occurred_at)
-- 缺口 (docs/Observability_PRD_v1.0.md §1.3):
--   - 失败调用完全不落表 (llm_usage_log 无 ok/error 列) -> 成功率无法判读
--   - gateway / usage.py 写入时 latency_ms 写 0 (usage.py:101,124) -> 慢不慢无据
--   - tokens 按 len//4 估算 -> cost 偏离
--   - 无 trace_id -> job / LLM 调用无法串联
--   - 无 scene / config_source / key_source -> 业务侧场景不可聚类
--
-- 兼容性:
--   旧行 (无 ok 列) 默认 ok=1 (历史写入全部视为成功) - 缺失字段以 DEFAULT 补齐。
--   旧行 error=NULL / latency_ms=0 保留, 不回填 (新查询按 IS NULL 判口径即可)。
--   cost_monitor.record_usage (cost_monitor.py:65-86) 与 usage.log_llm_usage
--   两条独立写入路径在批次① 改走统一入口 record_llm_call, 不再独立 INSERT。
--
-- 索引: (occurred_at) 已存在 (052); 增量加 (provider, task, occurred_at)
--       + (ok, occurred_at) 覆盖失败/成功两类聚合。

ALTER TABLE llm_usage_log ADD COLUMN ok INTEGER NOT NULL DEFAULT 1;
ALTER TABLE llm_usage_log ADD COLUMN error TEXT;
ALTER TABLE llm_usage_log ADD COLUMN prompt_tokens INTEGER;
ALTER TABLE llm_usage_log ADD COLUMN completion_tokens INTEGER;
ALTER TABLE llm_usage_log ADD COLUMN tokens_estimated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE llm_usage_log ADD COLUMN trace_id TEXT;
ALTER TABLE llm_usage_log ADD COLUMN scene TEXT;
ALTER TABLE llm_usage_log ADD COLUMN config_source TEXT;
ALTER TABLE llm_usage_log ADD COLUMN key_source TEXT;

CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_task_at
  ON llm_usage_log (provider, task, occurred_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_ok_at
  ON llm_usage_log (ok, occurred_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_trace
  ON llm_usage_log (trace_id) WHERE trace_id IS NOT NULL;
