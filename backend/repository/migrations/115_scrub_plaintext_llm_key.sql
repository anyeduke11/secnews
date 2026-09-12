-- P0-G (FIRST_PRINCIPLES_ANALYSIS_2026-09-11): settings 表 quality.llm_api_key
-- 行历史上以明文 API key 落库 (37 字符 sensenova key) — 违反 "明文密钥不入库"。
--
-- 删除安全性核查 (2026-09-12):
--   - 代码层 0 读取方: ``grep quality.llm_api_key`` 全仓只命中
--     backend/quality/base.py 的 GateContext.llm_api_key 死字段 (v4.4 起
--     ai_hub 不接, 默认 "" 且无任何赋值点) 与文档。
--   - 运行链不受影响: ai_hub provider 密钥走 env (api_key_env) >
--     settings.kv "llm.default_provider" (只存 provider 名, 不存 key) >
--     router > config/llm.yaml 四级链, 均不读本 key。
--   - PUT /api/quality/rules 维护的 quality.llm_provider 同为死字段。
--
-- 销毁型迁移: 不可回滚 (明文本就不应保留; 如需恢复走 env 注入)。

DELETE FROM settings WHERE key = 'quality.llm_api_key';
