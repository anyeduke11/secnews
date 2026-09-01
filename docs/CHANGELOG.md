# Changelog

## v0.7 Batch 3 + 4 + 5 (2026-08-31) — API 观测落地 + 阈值规则引擎 + 收口落账

> **来源**: Observability PRD v1.0 §5.3 "业务 endpoint 观测 + 阈值告警 + 看板嵌入"。本批三段子批一气呵成, 与 Batch 2 同观测轨, 不留尾巴 (除 llm_secrets 独立批次)。
## v0.7 Batch 7 (2026-09-01) — 修复遗留阻塞项 (5 项全清)

> **来源**: 用户指令 "修复遗留阻塞项" — 关闭 Batch ⑥ "不在本批范围" 全部 5 项。
> **范围**: ① webdav 密文迁移关单 (零工作) + SecretsPage 三处 window.prompt 替换 MasterKeyPromptModal (6 tests); ② codegarden/sync/dsh 三域 secrets 全量 audit_log (codegarden env_template 1 处 + sync Batch ⑥ 已覆盖 + dsh 零写入); ③ secrets TTL 自动过期 + 强制轮换提醒 (HOTSPOT_SECRETS_TTL_SECONDS env + last_rotated_at + rotation_status API); ④ 主密钥多用户分级 admin/user 双层解锁 (encryption_keys.role + get_by_role + unlock(role) + keyring/settings 后缀隔离); ⑤ SSO/OAuth 接入 SecretsService (CloudBase OAuth provider + unlock_with_oauth + frontend callback)。
> **commit 链**: `cd7187c` (T1) → `4171d2f` (T3) → T4/T5 (本段)。
> **不引入**: 新数据库连接 / 新 feature gate / 新前端页面 / 不动 ARCHITECTURE 数字。

### 批次 ㊲: Batch ⑦ — T1+T2+T3+T4+T5 遗留阻塞项全清

- [x] **T1 — webdav 密文迁移关单**: 零工作 (014_sync.sql Fernet 密文, DB 0 行存量); 前端 SecretsPage 三处 window.prompt 替换为 MasterKeyPromptModal 通用组件 (password input, autoComplete=new-password); 新增 MasterKeyPromptModal.test.tsx (6 tests: 渲染/默认 label/password input/提交回调/空值禁用/取消关闭)
- [x] **T2 — codegarden/sync/dsh 三域 secrets 全量 audit_log**: codegarden save_env_template 新增 codegarden.env_template.save audit (action/target/detail); sync Batch ⑥ C5 已覆盖 llm_secrets.sync_write; dsh agent_bridge/secnews_dashboard 零 secrets 写入; 新增 test_save_env_template_writes_audit_log (1 例, fixture 加 080 audit_log + 013 encryption_keys + patch observability_records.get_connection)
- [x] **T3 — secrets TTL 自动过期 + 强制轮换提醒**: UNLOCK_TTL_SECONDS 改为 HOTSPOT_SECRETS_TTL_SECONDS env (默认 30 分钟); encryption_keys.last_rotated_at (085 migration); SecretsService.rotation_status() → age_days + should_rotate (90 天); 新增 GET /api/secrets/rotation-status; rotate_master_key 写 last_rotated_at
- [x] **T4 — 主密钥多用户分级 (admin/user 双层解锁)**: encryption_keys.role 列 (admin|user, 086 migration); EncryptionKeyRow.role; EncryptionKeyRepository.get_by_role() + setup_user_key(); SecretsService.unlock(role=) + unlock_status(role=); _persist_master_key(key_id, role) + _load_persisted_master_key(key_id) + _clear_persisted_master_key(key_id) keyring/settings 后缀隔离; API SetupRequest/UnlockRequest 加 role 字段; unlock 返回 role
- [x] **T5 — SSO/OAuth 接入 SecretsService**: CloudBase OAuth provider 配置 (manageAppAuth ensurePublishableKey + addProvider); POST /api/secrets/unlock-with-oauth 端点 (CloudBase token 校验 → 取 openid → 映射 role → unlock); 前端 OAuth callback 路由 /secnews/settings/oauth-callback + useSecrets 加 unlockWithOAuth(provider); 凭据只从 env/keyring/settings 读取, 源码/测试不写真实 key 字面量
- [x] **前端 MasterKeyPromptModal**: 新增 frontend/src/components/secrets/MasterKeyPromptModal.tsx + .test.tsx (6/6 passed); SecretsPage.tsx 三处 window.prompt (import/export/reveal) 全替换为 promptRequest state + modal 复用
- [x] **门禁**: ruff backend 0 / pytest 全量通过 / tsc 0 / generate_meta OK / 前端 vitest 通过 / vite build OK

> **范围**: ① Batch ③ middleware 写表 (`record_api_call` + api_events + api_metrics_hourly + aggregator); ② Batch ④ 阈值引擎 (`observability_thresholds` service + observability_alerts 表 + threshold_check_job + alerts/thresholds API + Dashboard 横幅 + StatusBar 角标); ③ Batch ⑤ 集成测试 + ARCHITECTURE 同步 + PROGRESS/CHANGELOG 落账 + carry 收编。
> **不引入**: 新数据库连接 / 新传输层 (ws/SSE) / 新 feature gate / 告警通道扩展 / 观测数据采样。
> **commit 链**: `1f3d0e7` (carry merge) → `63c856c` (Batch ③ backend) → `108afde` (Batch ③ frontend) → `bf5a982` (Batch ④ backend) → `f0e01a4` (Batch ④ frontend) → 本 docs commit (Batch ⑤)。

### 批次 ㉟: Batch ③ — middleware 写表 + api_events/api_metrics_hourly + aggregator

- [x] `backend/observability_records.py::record_api_call` (NEW, def 非 async, 失败 swallow, 镜像 record_audit 模式)
- [x] `backend/repository/migrations/081_v0.7_api_observability.sql` (NEW): `api_events` (7d TTL) + `api_metrics_hourly` (30d TTL, hour+path_template 主键) + 5 索引
- [x] `backend/api/middleware.py`: dispatch 收尾 + 异常路径双调用 `record_api_call`; `path_template = request.scope["route"].path` (FastAPI 路由模板, 非 raw URL, 避免 query string 维度爆炸); `/api/health` 仍在 exclude_paths 排除
- [x] `backend/scheduler/jobs/maintenance.py::observability_aggregator_job` (NEW, 60min): Python 两步走 dict buckets 聚合 (绕开 SQLite correlated subquery 不能引用外层 SELECT 别名); `INSERT OR REPLACE` 主键幂等
- [x] `backend/scheduler/jobs/maintenance.py::observability_ttl_job` 扩到 5 张表 (新增 `api_events` 7d)
- [x] `backend/api/observability_router.py` (NEW, 无 feature flag, 无条件基础设施): `/api/observability/{summary,recent,timeseries,llm-usage}` 4 GET 端点; 全部 `def` 同步 (async→def 线程池派发规则)
- [x] `backend/tests/test_api_observability.py` (NEW, 10 例): middleware 落表 200/4xx/5xx / 排除路径 / error 截断 [:500] / aggregator 跨小时 / summary error_rate+p95 / recent desc / timeseries
- [x] `frontend/src/components/secnews/observability/ObservabilityDashboard.tsx` (NEW): 3 卡片网格 (1h 概览 / Top 5 慢路径 / 最近 20 条事件, 5s 自动刷新)
- [x] `frontend/src/components/secnews/observability/ObservabilityTab.tsx` (NEW): 路由壳; `routes/index.tsx` + `routes/lazy-imports.ts` 注册 `/secnews/observability`; `SecNewsShell.tsx` nav 加「观测」tab
- [x] `frontend/src/components/secnews/layout/StatusBar.tsx`: 第 4 段 obs 1h (total / err% / p95, err≥5% 黄 / ≥15% 红)
- [x] `frontend/src/components/secnews/observability/ObservabilityDashboard.test.tsx` (NEW, 3 例)
- [x] **门禁**: ruff 0 / pytest 10/10 pass (scoped) / tsc 0 / vitest 317 pass / vite build OK

### 批次 ㊱: Batch ④ — 阈值规则引擎 + observability_alerts + 看板嵌入

- [x] `backend/services/observability_thresholds.py` (NEW): `Breach` dataclass + `load/save/validate/evaluate`; 4 类规则 (api/llm/job/audit) 各有 warn/critical/window_minutes; 缺失/坏值兜底 `DEFAULT_THRESHOLDS` (api.error_rate_pct 5/15, api.p95_latency_ms 800/2000, llm.error_rate_pct 10/30, job.failure_rate_pct 10/25, audit.llm_config_change_per_hour 10/50); `_validate` schema 校验 (非 dict / 负值 / warn≥critical)
- [x] `backend/repository/migrations/082_v0.7_observability_alerts.sql` (NEW): `observability_alerts` 表 (level/metric/value/threshold/window_minutes/detail/fired_at/cooldown_until/acked/acacked_at/acked_by) + 3 索引
- [x] `backend/scheduler/jobs/maintenance.py::observability_threshold_check_job` (NEW, 60min, aggregator +10min 错峰): 扫 api_events 1h 摘要 → 评估 breach → 同 (metric, level) cooldown 期内跳过 (15min 默认) → 写 alerts + audit_log action=threshold.breach
- [x] `backend/scheduler/jobs/maintenance.py::observability_ttl_job` 扩到 6 张表 (新增 `observability_alerts` 30d)
- [x] `backend/api/observability_router.py` 增 4 端点: `GET /alerts/active` (24h 窗口, critical 优先) / `POST /alerts/{id}/ack` (幂等) / `GET/PUT /thresholds` (PUT 校验 + audit_log)
- [x] `backend/tests/test_observability_thresholds.py` (NEW, 14 例): load 兜底 / roundtrip / `_validate` 3 例 / evaluate warn+critical / p95 多越界 / summary dict / cooldown_until / alerts active / ack 幂等 / thresholds GET/PUT
- [x] `backend/tests/test_feature_gates.py::test_registered_job_count_matches_scheduler`: AST 计数 48 → 50
- [x] `frontend/src/components/secnews/observability/ActiveAlertsBanner.tsx` (NEW): 顶部红/黄条 + ack 按钮; 30s 刷新
- [x] `frontend/src/components/secnews/observability/ThresholdEditor.tsx` (NEW): 折叠面板; 4 大类规则编辑; PUT 200 "已保存" / 400 toast 错误
- [x] `frontend/src/components/secnews/observability/ObservabilityTab.tsx`: 顶部装 banner, 底部装 editor
- [x] `frontend/src/components/secnews/layout/StatusBar.tsx`: 告警角标 🚨 N critical (红) / ⚠ N warn (黄), 仅非零显示
- [x] `frontend/src/components/secnews/observability/Batch4.test.tsx` (NEW, 5 例)
- [x] **门禁**: ruff 0 / pytest 14/14 pass (scoped) + `test_feature_gates` 65/16 pass / tsc 0 / vitest 322 pass / vite build OK

### 批次 ㊲: Batch ⑤ — 收口落账 + carry 收编

- [x] `backend/tests/test_observability_integration.py` (NEW, 5 例): middleware→aggregator→summary / threshold breach→alert / cooldown 去重 / ack 后从 active 消失 / record_api_call 抛异常业务响应仍 200
- [x] `backend/api/middleware.py`: 双层 swallow (record_api_call 内部 try/except + middleware 外层 log_event api_observability_swallowed)
- [x] `docs/ARCHITECTURE.md`: 顶部数字带更新 routers 65→66 / services 97→98 / jobs 48→50; 框图 r 同步
- [x] `PROGRESS.md`: 加 Batch ③ + ④ + ⑤ 三段 (含 commit 链 + 关键事实表 + 不在本批范围)
- [x] `carry/earlier-session-leftovers` (`e209a57`) `--no-ff` 收编, P4 双预存债根治 (test_successors_of_raw + test_baseline_2026_08_24_counts)
- [x] **门禁**: ruff 0 / pytest 集成测试 5/5 pass / 全量 pytest 0fail (P4 清零) / `generate_meta --check` OK (routers 66 / services 98 / jobs 50) / tsc 0 / vitest 322 pass / vite build OK

## v0.7 Batch 6 (2026-08-31) — llm_secrets 接入 AIService/LLMService + key_source 兑现

### 批次 ㊳: Batch ⑥ — 加密通道接管

- [x] `backend/repository/secrets_repo.py`: 新增 `get_by_provider(provider)` helper (`ORDER BY updated_at DESC, id DESC LIMIT 1` 复用 `idx_llm_secrets_provider`)
- [x] `backend/services/ai_hub/service.py`: `_resolve_api_key` 重写为实例方法 + 四级链 (env > secrets > "" fail-soft); 新增 `_key_source` 返 `env|secrets|none`; 2 处 `key_source="env"` 硬编码改动态; 5 处调用改 `self._resolve_api_key(provider)`
- [x] `backend/services/ai_hub/gateway.py`: `_ai_key_source(provider_name)` 模块辅助函数委托 AIService; `_call_provider/_call_openai/_call_anthropic/_call_openai_compatible` 接受 `provider_name=`; 8 处 `key_source="env"` 改 `_ai_key_source(provider_name)`
- [x] `backend/api/secrets.py`: 7 audit calls (`create/update/delete/reveal/test/unlock/lock`) + `POST /api/secrets/rotate` 端点 (master_key 轮换 + 重加密 + 强审计); `RotateRequest` Pydantic 校验 (min_length=12)
- [x] `backend/services/sync_bundle.py`: 复制 llm_secrets INSERT/UPDATE 路径加 `llm_secrets.sync_write` 审计
- [x] `backend/observability_records.py`: SAVEPOINT 隔离, 兼容 autocommit / 隐式事务两种连接模式; record_audit 失败 swallow 保持业务路径不阻塞
- [x] `backend/services/secrets_service.py`: 修复 `rotate_master_key` 引用 `encryption_keys.updated_at` 列的旧 bug (该列不存在, UPDATE 失败)
- [x] `backend/api/llm_status.py`: status 返回新增 `key_source` 字段 (供前端 QualitySettings 徽章展示)
- [x] `frontend/src/components/settings/QualitySettings.tsx`: 折叠面板 "🔐 LLM 密钥管理 (加密保险箱)" + `key_source` 徽章 + 3 弹窗 (master_key_prompt / reveal_10s_auto_hide / upsert) + 7 handler; `saveLlm` 不再写 `quality.llm_api_key` settings.kv (legacy 清退)
- [x] **遗留阻塞项 ⑤ 关闭**: "加密通道接管" → llm_secrets 真正接入业务路径; key_source 三态可观测; reveal 强审计; rotate HTTP 端点就绪
- [x] **测试**: SecretRepository 5 例 + AIService 10 例 + LLMService 4 例 + QualitySettings 5 例 + secrets API 11 audit + 4 rotate = **39 例**
- [x] **门禁**: ruff 0 / pytest 3138 passed / 6 skipped / 0 failed (基线 3108 + 39 净增) / `generate_meta --check` OK (routers 66 / services 98 / jobs 50 — 不变) / tsc 0 / vitest 327 pass (基线 322 + 5 QualitySettings) / vite build OK

## v0.7 Batch 2 (2026-08-31) — LLM provider 切换 + settings.kv 覆盖 + audit_log 写入

> **来源**: Observability PRD v1.0 §5.3 + Batch 1 已落地的 `record_audit` 0 生产调用者顺接, 闭环为 audit_log 首个真实写入场景。批前盘点: ai_hub 默认 provider 仅 env/router/default 三级, 用户切换要重启进程或改 env; QualitySettings 写 `quality.llm_provider` 是 v4.4 起的 dead 字段 (ai_hub 不读)。
> **范围**: ① env AI_PROVIDER > settings.kv > yaml default_provider 四级链; ② `POST /api/settings/llm-provider` 走 settings.kv + audit_log; ③ 前端扩到 yaml 全注册; ④ 不动 llm_secrets (主密钥未解); ⑤ 不动 LLMService gateway; ⑥ 不动 GateContext (dead default)。
> **不引入**: 新数据库表 / 新 feature gate / 新前端页面 / llm_secrets 接入。
> **commit 链**: `ade3b03` (backend) → `ba69454` (frontend) → docs commit。

### 批次 ㉞：Batch 2 — 后端核心

- **`AIService._resolve_provider` 四级链** (`backend/services/ai_hub/service.py`): 在 env 之后插入 settings.kv 查询 (类型守卫 `isinstance(str) and .strip()`, 避免非字符串触发 "settings" 打标), 兜底 router → yaml default_provider; 既有 `test_s4_1_model_router.py::test_ai_service_resolve_provider_three_levels` 6 用例继续绿 (env > router > default 顺序保住 — test isolation 时 env 未设 + settings.kv 空, 新代码回退到 router/default 同既有路径)
- **`AIService._config_source()` 解析路径打标** (NEW): env|settings|router|default, 写入 `llm_usage_log.config_source` 替换原 `default/fallback` 二分; `key_source` 仍 `"env"` (TODO 留待 Batch ③+ 接 llm_secrets)
- **`POST /api/settings/llm-provider`** (`backend/api/settings.py`): 校验 provider ∈ yaml registry → `SettingsRepository.set("llm.default_provider")` → `record_audit(actor, action="llm_config.update", target="default_provider", detail={from, to, source})`; audit 失败仍 200 (PRD §10 红线 ② 审计容错); actor 默认 `"web"`, 接受 `"system"` / `"agent:<name>"`; 无效 provider → 400 `INVALID_PARAM` 含 trace_id/version envelope
- **`GET /api/llm/status` 增 `effective_provider` + `config_source`**: 帮前端确认"我现在到底用哪个 + 哪条链生效的", 复用 `_resolve_provider` / `_config_source` 同源
- **新测试 × 14**:
  - `backend/tests/test_llm_settings_override.py` NEW (8 例): env > settings > router > default 完整四链; 非字符串 / 空串 / settings_repo 异常 swallowed; 端到端 `config_source` 落到 `llm_usage_log`
  - `backend/tests/test_llm_settings_api.py` NEW (6 例): 合法切换 + audit 写入; 非法 provider → 400 `INVALID_PARAM`; audit 失败仍 200; actor 三种格式 web/system/agent:<name>; 旧值序列正确 (from=None → "sensenova"); yaml registry 缺失时退化兜底

### 批次 ㉟：Batch 2 — 前端面板

- **`frontend/src/components/settings/QualitySettings.tsx`**: 顶部新增独立面板 (与质量规则解耦)
  - 拉 `/api/llm/status` 拿到 yaml 注册的 `providers` + `effective_provider` + `config_source`, dropdown 动态渲染 (不再硬编码 2 项; yaml 几个就几个)
  - "切换默认 LLM Provider" 按钮 → `POST /api/settings/llm-provider { provider, actor: 'web' }`, 成功后重拉 status 验证 `effective_provider` 已变 + 显示 `已切换: x → y`
  - 失败 (INVALID_PARAM 等) 显示后端 `message`, 不调成功 toast
  - 沿用 settings.kv 持久化 + audit_log 写入 (后端已在 ㉞ 落地)
  - 检测子面板的提供方 dropdown 同步扩为动态渲染
  - 不动 `PUT /api/quality/rules` (那是质量规则, dead 字段 `quality.llm_provider` 保留)
  - 不引入新页面 / 新依赖
- **`frontend/src/components/settings/QualitySettings.test.tsx` NEW** (4 例全绿): 5-option 动态渲染 + effective 反映 status; POST 切换 + 成功消息; 失败显示错误无成功 toast; open=false 不触发 fetch

### 门禁

| 维度 | 结果 |
|---|---|
| ruff backend | All checks passed (含 I001 自动修) |
| 全量 pytest | **3077 passed / 6 skipped / 1 failed** (1 fail = P4 预存债 `test_snapshot_for_retirement.py::test_baseline_2026_08_24_counts` 期望 4149 wiki 文件但根已迁, 见 P4 段) |
| `generate_meta --check` | OK (routers 65 / services 97 不变 — 本批不增架构数字) |
| tsc --noEmit | 0 错 |
| vitest | **314 passed** (基线 310 + 4 new) |
| vite build | OK |

### 不在本批范围 (留作 Batch ③+ 开放尾巴)

- Batch ③ API 观测 (HTTP middleware trace_id 注入 + 业务 endpoint observability)
- Batch ④ 看板告警 (Dashboard 嵌入 + 阈值规则)
- Batch ⑤ 收尾
- llm_secrets 主密钥恢复 (Q1 禁重置沿袭, 加密通道休眠待用户裁决)
- 已知预存债 (来自 P4): `test_kl_state_machine.py::test_successors_of_raw` 期望漂移 / `test_snapshot_for_retirement.py::test_baseline_2026_08_24_counts` 期望陈旧

## v0.7 Batch 1 (2026-08-31) — Observability 观测地基 + LLM/Job/Agent/Process 执行记录

> **来源**: 用户 2026-08-30 `hotspot-observability-prd.md` 需求 (ollama + 云端 LLM 前端可切换 + 完整观测方案, 5 批次实施 ①地基 / ②LLM 切换 / ③API 观测 / ④看板告警 / ⑤收尾)。本批 = ①, 仅落地观测地基与执行记录层; 不动 LLM 配置切换 (留 ②)。commit `345ce39` (分支 `observability/batch-1`)。
> **非本批遗留隔离**: `carry/earlier-session-leftovers` 分支 `e209a57` — 7 个更早会话未 commit 的预存债文件 (kl_state_machine / t1_raw_to_refine / wiki_stats_service / test_kl_state_machine / test_snapshot_for_retirement / test_t1_trigger / snapshot_for_retirement), 显式 pathspec 隔离, 不混进本批叙事。

### 批次 ㉞：观测地基 — contextvar trace_id + observability_records 4 入口 + logging serialize 化

- **trace_id contextvar 传播** (`backend/observability.py`): 新增 `_trace_id_var: ContextVar[str|None]`, `set_trace_id(trace_id)` 返回 `Token` (`ContextVar.set()` 必须接收, 丢则后续 `reset_trace_id(None)` 抛 TypeError — 装饰器包装第一版坑过), `get_trace_id()` 不存在返 None (对齐 `ContextVar.get()` 默认值语义)
- **`log_event(event, **fields)` 入口**: 自动从 ctx 取 trace_id 注入, 走 `logger.bind(**fields).info(event)` 把字段拍平到 `record.extra` 顶层 (vs `extra={}` 嵌套到 `record.extra.extra` 的陷阱); patcher `_ensure_trace_id_default` 同时注入 trace_id 与 event 默认空串, 模板渲染不抛 KeyError
- **`observability_records.py` 4 入口** (全 `def` 同步, 阻塞业务路径按 PRD §10 红线 ② 全吞异常 — 不允许观测写入失败拖垮业务流):
  - `start_job_run(job_id, ...)` / `finish_job_run(run_id, status, error?)` — 双阶段 (P0 范式: 不允许只 finish 不 start)
  - `start_agent_run(agent_name, ...)` / `finish_agent_run(run_id, status, error?)` — 同上
  - `record_process_event(supervisor, pid, event, detail)` — 单 append
  - `record_audit(action, actor, target, detail)` — 单 append, ② LLM 切换写入审计用此
- **observability 写入**全 `def` 同步: 严禁 `async def`, 否则 FastAPI 主事件循环被 await 链拖; 若调用方在 async 上下文, 必须 `asyncio.to_thread(observability_records.start_job_run, ...)` — 由调用方显式 to_thread, 避免隐式线程池派发 (P3-1 教训: async→def 自动线程池派发 = connection affinity × SQLite ATTACH 跨线程假阴性)

### 批次 ㉟：migration 079 + 080 — llm_usage_log 9 列 + 4 张观测表

- **migration 079** (`backend/repository/migrations/079_v0.7_llm_usage_log_cols.sql`): `llm_usage_log` 加 ok / error / prompt_tokens / completion_tokens / tokens_estimated / trace_id / scene / config_source / key_source 9 列 + 3 索引 (`idx_usage_trace_id` / `idx_usage_scene_time` / `idx_usage_time`)
- **migration 080** (`backend/repository/migrations/080_v0.7_observability_tables.sql`): 4 张观测表全部带 `trace_id IS NOT NULL` 部分索引 (允许空但有则查得快):
  - `job_runs` (30d TTL) — job_id / started_at / finished_at / status / error / trigger / trace_id
  - `agent_runs` (30d TTL) — agent_name / started_at / finished_at / status / error / pid / trace_id
  - `process_events` (14d TTL) — supervisor / pid / event / detail / occurred_at / trace_id
  - `audit_log` (90d TTL) — action / actor / target / detail / occurred_at / trace_id (Batch ②/③ 主用)

### 批次 ㊱：`record_llm_call` 统一入口 + `success_stats_24h` 升 p50

- **`backend/services/ai_hub/usage.py`** 新统一入口 `record_llm_call(provider, model, task, *, ok, error=None, prompt=None, response=None, prompt_tokens=None, completion_tokens=None, total_tokens=None, cost_usd=None, latency_ms=0.0, tokens_estimated=False, scene=None, config_source=None, key_source=None, trace_id=None)`: 替代旧 `log_llm_usage` / `log_ai_usage` / `cost_monitor.record_usage` 三入口
- **`success_stats_24h()` 升级 `latency_p50_ms`**: SQLite `ROW_NUMBER() OVER (ORDER BY latency_ms)` + `COUNT(*) OVER ()` 取中位 trick, 仅统计 `ok=1 AND latency_ms IS NOT NULL`; /api/llm/status observability 块新增字段 (`v0.6.3 P3-3` 仅 success_rate, 本批补 latency 维度)
- **`AIService._record` 新方法** (`backend/services/ai_hub/service.py`): 4 必填 + 9 可选, 替代旧 `_usage`; **`_usage` 保留为 deprecated shim** 转发到 `record_llm_call` — 不删, 因旧测试桩 `lambda *a, **k` 仍在引用 (曾掩盖 arity bug, 现改 5-tuple 断言后可破, 但下游 ai_service 自调仍有引用, 一刀切会破 — shim 是最稳路径)
- **`record_llm_call` 字段**: config_source (`default` / `fallback` / `user_override`) + key_source (`env` / `secret` / `manual`) + scene (`evaluate_article` / `gate_detect` / `summarize` / `translate` / 等) — Batch ② 用户切换行为通过这 3 字段落审计

### 批次 ㊲：3 处端到端接入 — agent_bridge + process_supervisor + scheduler instrument_job

- **`backend/services/agent_bridge.py`**: `run_agent_task` 设 trace_id `f"agent:{agent_name}:{int(time.time())}"` + `start_agent_run` / `finish_agent_run` 包裹 `_run_builtin` builtin 路径 (此前裸跑无任何观测) + finally `reset_trace_id(token)` 防跨请求串味
- **`backend/services/process_supervisor.py`**: 4 lifecycle 分支 5 个写入点落 `process_events` — spawn 成功 / spawn 失败 / stop (exit) / poll auto-restart / poll hit-restart-limit
- **`backend/scheduler/jobs/_runtime.py`** `instrument_job` 装饰器: 统一入口 — 设 trace_id `job:<job_id>:<start_ms>`, `start_job_run` + finally `finish_job_run(status=ok|failed)`, **全部 job 自动覆盖** (无需逐 job 改); 关键 = `set_trace_id(trace_id)` 返回值必须接收 (Token), 丢则 reset 阶段 TypeError

### 批次 ㊳：`observability_ttl_job` (job 48) + logging_config 切 `serialize=True`

- **job 48 `observability_ttl_job`** (`backend/scheduler/jobs/maintenance.py` + scheduler.py): 1h 间隔; 4 表分别按 30/30/14/90 天阈值清理 — `job_runs`/`agent_runs` 30d, `process_events` 14d, `audit_log` 90d; `__init__.py` re-export; scheduler.py `id="observability_ttl"` 注册
- **logging_config 切 `serialize=True`** (`backend/logging_config.py`): 旧模板 `{ts/level/module/msg/trace_id/event}` 只挑 5 固定字段, `log_event` 传的 method/path/status/duration_ms 全部不进文件; 切到 loguru 内置 JSON 序列化, 读法变 `jq '.record.extra.method'` / `'.record.extra.status'`, 包一层 `record.{text,message,extra,level.name,...}`; 下游测试同步改写
- **meta 同步**: ARCHITECTURE.md 47→48 jobs; generate_meta --check OK (jobs 48 / collectors 14 / routers 65 / services 97)

### 批次 ㊴：测试 — 18 个新增 + 3 处既有用例同步

- **新增 `backend/tests/test_llm_observability.py`** (18 用例):
  - record_llm_call 4 例 (real tokens / estimated / failure ok=0 / trace_id 自动从 ctx fallback)
  - success_stats_24h 2 例 (含 p50 单测: ROW_NUMBER trick, ok=0 不进 latency 池)
  - recent_calls 1 例
  - job_runs / agent_runs 双阶段各 3 例 (ok / failed / finish 不带 start = noop)
  - process_events / audit_log append 各 1 例
  - observability_records 异常吞 2 例 (异常不外抛, 不污染业务流)
  - contextvar 隔离 1 例 (不同 asyncio.run 各自独立)
  - log_event bind pattern via serialize=True sink 1 例 (断言 `bind.assert_called_once()` + `bind.return_value.info.assert_called_once()`)
  - instrument_job 双阶段 1 例
- **既有用例同步**: test_feature_gates 47→48 jobs / test_llm_evaluate patch `_record` 替 `_usage` (4-tuple 断言) / test_logging 改 `record.extra.trace_id` 形态 / test_observability 改 `bind.assert_called_once()` 断言
- **零 skip 守住**: 18 个新增全过, 既有 6 skipped 保持 (与本批无关的 WIP 标记)

### 决策点 (本批)

1. **Token 必须捕获**: 装饰器第一版丢弃 `set_trace_id()` 返回值, `reset_trace_id(None)` 抛 TypeError — `ContextVar.set()` 返回 Token 必须接收 (与 P3-1 同类教训: 子系统包装时把 token 弄丢 = 业务崩)
2. **sink API 收 Message vs str**: 测试 sink 用 `serialize=False` 时收 Message 对象, 切 `serialize=True` 后收 JSON 字符串, 断言写法不同; 测试必须配 `serialize=True` 才与生产一致 (生产唯一)
3. **observability_records 全 def 同步**: async → FastAPI 主事件循环被拖; to_thread → connection affinity × SQLite ATTACH 跨线程假阴性; 唯一正确路径 = 纯 `def` 由调用方显式 to_thread
4. **`_usage` 不删, 标 deprecated shim**: 测试桩曾掩盖 arity bug, 改 5-tuple 断言后删看似干净, 但下游 (ai_service 自调) 还有引用, 一刀切会破 — 保留 shim 转发到 `record_llm_call` 是最稳路径
5. **7 个非本批遗留文件隔离**: 提交前 git status 出现 7 个未提交修改 (kl/t1/wiki_stats + tests), 都是更早会话落地未 commit 的预存债 — 不能混进本批, 否则污染 v0.7 叙事; 处理 = `git stash push <pathspec>` → 建 `carry/earlier-session-leftovers` 分支 (基于 P4 头 `3d3af9c`) → `git stash pop` → 单独 `e209a57` chore 提交附完整溯源注记; 主分支 (`observability/batch-1`) 保持纯净

### 门禁结果

| 维度 | 结果 |
|---|---|
| ruff backend | All checks passed |
| 全量 pytest | **3047 passed / 6 skipped / 0 failed** (基线持平; 新增 18 用例全过) |
| generate_meta --check | OK (jobs 48 / collectors 14 / routers 65 / services 97) |
| tsc --noEmit | 0 错 (前端本批无动) |
| vitest | 310 passed (前端本批无动) |
| Mimosa | `scanner_no_output` (按既有兼容策略; 不宣称项目安全) |

### 仍开放 (Batch 2+ 范围, 不在本批)

- ② LLM 配置切换: `settings` KV + env 双轨优先级 + 前端切换 UI + `record_audit` 写入审计 (用户切换行为入 `audit_log`)
- ③ API 观测: HTTP middleware 接入 trace_id 自动注入 + latency 落 `audit_log`
- ④ 看板与告警: `/api/observability/dashboard` 聚合 + 阈值告警 (success_rate < 50% / latency_p95 > 30s 触发)
- ⑤ 收尾: PROGRESS/CHANGELOG 顶部段更新 + ARCHITECTURE.md 加 observability 章节 + 前端 observability 页面
- ⚠️ **carry/earlier-session-leftovers 分支** (`e209a57`): 7 个预存债文件已独立落 commit, 待用户裁决合并回主分支 / 继续保留为 WIP / 评估是否需要回滚
- ⚠️ **dsh 实机协议未对齐** (沿袭 v0.6.3 dsh 内置化): agent_bridge 桥接端点仍按推测实现, 待用户配置真实启动命令实测

---

## v0.6.3 P4 批次 (2026-08-30/31) — 双根合并 + llm-wiki-2.0 唯一根锁定 + 周界炸弹根治

> **来源**: 用户 2026-08-30 裁决"全部切换并锁定到 llm-wiki-2.0 唯一根, 删除旧根, 并保证功能正常"+"修复周界炸弹"。批前盘点: items/concepts 1:1 对齐 (4149/96), learning/content/summaries/_MAP.md/SOUL.md 仅在旧根, 12 service 仍写旧根。

### 批次 ㉜：单一路径源 `backend/wiki_fs/paths.py` + 12 service 全迁移

- **单一真相源**: 新增 `backend/wiki_fs/paths.py` — ITEMS_DIR / CONCEPTS_DIR / INBOX_DIR / QUARANTINE_DIR / LEARNING_DIR / LEARNING_PENDING_DIR / LEARNING_DONE_DIR / LEARNING_FAILED_DIR / LEARNING_TASKS_DIR / CONTENT_DIR / DRAFTS_DIR / CALENDAR_PATH / SUMMARIES_DIR / GRAPH_PATH / SOUL_PATH 全部基于 `resolve_wiki_root()` 派生; 测试 env `HOTSPOT_WIKI_ROOT` 一键重定向, 无须逐个 monkeypatch
- **12 service 全迁移**: knowledge_sync / content_service / history_import / bookmark_sync / concept_linker / compiler / learning_service / soul_service / map_updater / cubox_sync / progress_service / federation_service + api/knowledge.py → wiki_fs/paths; SOUL_PATH 旧位 `knowledge/SOUL.md` → `llm-wiki-2.0/soul.md`; MAP_PATH 旧位 `knowledge/_MAP.md` → `llm-wiki-2.0/_MAP.md` (watcher 不再自动调用, 留运维偶发导出)
- **测试 fixture 重构**: conftest `_isolate_knowledge_dirs` 改用 `HOTSPOT_WIKI_ROOT` env + reload wiki_fs/paths, 11 个 service 模块自动跟随; 旧 fixture `kdir = tmp_path / "knowledge"` 改 `tmp_path / "wiki"`; 补回 cubox_sync/history_import/bookmark_sync 的 `from pathlib import Path` (误删)
- **数据搬移**: knowledge/learning (2062 files / 7.9M) + knowledge/content (16 files / 68K) + knowledge/summaries (8 files / 28K) + SOUL.md + _MAP.md → llm-wiki-2.0/ 对应子树; 双根 md 头字段差异已分析: 旧根 64 个条目 mtime 更新但语义是新根补齐 alive/compiled 字段 (新根 = 更完整事实源, 无需反向灌回)
- **反向引用 grep 0 命中** (生产代码 + scripts); `/api/knowledge/*` 路由字符串保留语义

### 批次 ㉝：删除 knowledge/ 旧根 + 周一边界炸弹根治

- **物理删除旧根**: `rm -rf knowledge/` — llm-wiki-2.0/ 成为唯一真相源 (items 4149 / concepts 96 / learning 2062 / content 16 / summaries 8 + soul.md + _MAP.md + 系统文件 inbox/quarantine/digest/graph.json/retention.json/sources/schema)
- **周一边界炸弹根治**: recency 28 例全过 (含 `test_few_hours_ago_passes`); 用户同日指令; 钳位逻辑 `max(now-4h, week_start+1min)` 已由并行会话在 commit `381f05f` 落地, 本批验证其稳定性
- **门禁全清**: ruff 0 错; 全量 pytest **3047 passed / 6 skipped / 0 failed** (基线持平); generate_meta --check OK (97 services 含 paths.py 新模块); tsc 0 错; vitest 310 pass
- **commit** `cdc92e9` + `78706e8`; ruff --fix 误删 `concept_linker.ITEMS_DIR` (test_graph_runtime setattr 隔离目录需属性存在) → 重导入并入 `__all__`, scoped pytest 251/251 复绿; kl:deduped (4 文件: kl_state_machine / t1_raw_to_refine / wiki_stats_service / test_t1_trigger) 显式 pathspec 排除 commit, 属并行会话另起批次
- **预存债 (不在本批)**: `test_kl_state_machine.py::test_successors_of_raw` 期望 raw→refine 单出边, kl:deduped 终态落地后 `TRANSITIONS[LIFECYCLE_RAW]` 多一条 deduped → 该用例需更新期望集合; `test_snapshot_for_retirement.py::test_baseline_2026_08_24_counts` 期望 4149 wiki 文件在 knowledge/, 旧根已 gitignore + 新根不含 → 期望值陈旧; 两条皆属 kl:deduped 并行会话落账后的待跟踪项

## v0.6.3 P3 批次 (2026-08-30/31) — feed FTS 阈值自执行 + 运行时复核 + 两个真 bug 根治

> **来源**: 用户指定 P3 收尾 = ① feed 数据量到 5 万行再 FTS 化 (卡顿审计遗留裁决); ② 运行时 py-spy 采样复核。执行中挖出并根治 2 个真 bug + 1 类周一边界测试腐坏。

### 批次 ㉘：P3-1 — feed 关键词搜索 5 万行阈值惰性 trigram FTS 化 (`secnews_dashboard.py`)

- **裁决变自执行**: 带关键词的 `get_feed` 经 TTL (10min) 行数探针发现 `hotspots` ≥ 50,000 行时, 在 worker 线程内一次性建 `hotspots_trigram_fts` (contentless FTS5) + 全量回填 + AFTER INSERT/DELETE/UPDATE 同步触发器 (幂等, 崩溃可续), 之后 ≥3 字符查询词切 `MATCH`; <3 字符与未达标时维持 LIKE, 行为零变化
- **选 trigram 而非既有 unicode61 的原因**: unicode61 不切中日韩连写 (hotspot_repo 实测 "勒索" MATCH 0 / LIKE 18), 而 trigram 引号短语查询 = 子串匹配, 与 `LIKE %kw%` 语义等价 (ASCII 大小写不敏感 + CJK 逐字), ≥3 字符零召回损失 — 5 万行时自动升级索引且不牺牲中文搜索
- **响应口径标注**: `search_engine` ("fts5_trigram" | "like") + `feed_rows` (沿用 funnel_source 模式); 当前 live 库 4700 行, 机制休眠待命
- 测试 `test_feed_fts_threshold.py` NEW (9 用例: 阈值前 LIKE / 激活后 LIKE 等价召回对照 / 进程重启恢复 / 短词回退 / 触发器同步 / 引号转义 / 崩溃续回填不重复)

### 批次 ㉙：P3-1 执行中挖出的两个真 bug (根治)

1. **contentless FTS5 'delete' 触发器缺陷** (001_init.sql 起): `hotspots_ad`/`hotspots_au` 在 'delete' 命令里只给 rowid — 不报错但词条**静默残留** (SQLite 3.53 实证), UPDATE/DELETE 后旧 title/summary 词条残留 = 搜索假阳性; 当前 hotspots 以 INSERT-only + flag 更新为主故未爆发。→ migration **078** 重建两触发器为"提供旧值"写法 + delete-all 全量重灌清历史残留; `secnews_dashboard` 新触发器直接用正确写法; `test_migrations_v1_7.py` +3 行为锁
2. **`_parse_iso_datetime` 微秒路径时区偏移 8h** (`collectors/parsing.py`): 带 `.ffffff` 的 ISO 串先 `split(".")[0]` 把 `+00:00` 时区后缀一起截掉 → naive `astimezone(UTC)` 被当本地 (+8) 解析 → published_at 偏早 8 小时 → recency 门禁误杀周界 8h 内文章。→ 先 `fromisoformat` 再处理时区 (naive 仍按 UTC); crawl4ai ×3 + rss_path ×2 测试随即转绿

### 批次 ㉚：周一边界测试腐坏根治 (2026-08-31 00:00 实际爆发)

`TimeRange.D7` 与 recency 门禁是「本周周一 00:00」日历周语义, 而 4 个测试文件用 `now - N 小时` 种 "recent" 数据 — **每逢周一 00:00-01:00 (本地) 集体腐坏 14 例** (当晚实测 9 failed)。修法 = 种子钳制进当前周窗口 (`max(seed, week_start + 1min)`, 语义不变): `test_hotspot_repo.py` (`_recent_ts` 助手) / `test_collector_recency.py` (`_in_week_ts`) / `test_recency_gate.py` / `test_rss_path.py` (`_recent_dt` 钳制)。**教训**: 日历周窗口 + now 相对种子 = 每周必炸一次的组合, 新测试一律走钳制助手。

### 批次 ㉛：P3-2 — 运行时复核 (py-spy 不可用 → 进程内 loop-lag 探针等价达成)

- py-spy 0.4.2 在 macOS 附着需 root (sudo 免密不可用) → 改用**更强证据**: 真实 `backend.main:app` 跑 8001 + 进程内事件循环滞后监视器 (每 100ms 测 `asyncio.sleep` 漂移, 直测"循环被同步段占用"), 4 并发锤打 5 端点 45s ≈ 46k 请求
- **结果: loop lag p50=0ms / p95=2ms / p99=9ms / max=63ms; >200ms 样本 0 个** (旧故障模式 = 每请求阻塞事件循环 337-1176ms)。单请求 max 1116ms 出现在 `/api/secnews/pipeline` = liveness TTL 过期的那一次 md 全量扫描, 落在 worker 线程 (设计内, 摊薄)
- 常态负载 60s 报告: 统计端点 p95 < 8ms; feed 关键词 p95 20.8ms (4700 行 LIKE 路径); 0 错误

### 门禁

| 维度 | 结果 |
|---|---|
| ruff backend | All checks passed |
| 全量 pytest | **3047 passed / 6 skipped / 0 failed** (基线 3035 → 3047, 新增 P3 锁) |
| live 后端 | 重启加载新代码, migration 078 已应用, trigram 机制休眠待命 |

## v0.6.3 P2 批次 (2026-08-30) — job 纪律补全 + wiki_fs 缓存层 + 失效接线

> **来源**: P0 修复后第一性重审 — API 面 AST 复扫 0 残留; scheduler 面新发现 6 个 async job 事件循环直接同步 IO; 指名嫌疑实测 (read_item 491ms 实锤 / ATTACH 0.2ms / feed LIKE <1ms 双双排除); **重大发现: wiki 单根裁决写路径未完成** (见下"待拍板")。

### 批次 ㉕：P2-1 — scheduler job 纪律 (6 job to_thread 化)

- `knowledge_classify_job` (30min, 500 行批) / `content_draft_generation_job` (6h) / `security_enrichment_job` / `security_entity_concept_sync_job` (10min): 全同步体抽 `_run()` → `asyncio.to_thread`
- `knowledge_stub_backfill_job` (6h): 三段式 — 候选 SELECT 与结果回写 (DB/md IO) 入线程, aiohttp 抓取保留事件循环 (真异步)
- `catchup_watchdog_job` (**60s 高频**): 扫描+标孤儿入线程, `enqueue_catchup` (async) 保留事件循环

### 批次 ㉖：P2-2 — wiki_fs mtime 缓存层 + concept_linker 甄别

- **read_item mtime+size 校验缓存** (`store.py`): stat ~10µs 命中免 read_text+YAML (~130µs); write_item 写穿刷新 (P2-3 失效单点同在此); 外部改写 mtime 变化自动失效
  - 实测: 全量 4149 条 702ms (冷) → **17-20ms** (35×); 单文件热路径 ~4µs
- **concept_linker 甄别修正**: 此前审计称"三实现并存零入口"——实为**两层不同职责**: `services/concept_linker.py` = tag→concept 归类 + llm-wiki-2.0/graph.json 6 typed 边运行时填充 (compiler 消费, M3.5 Task13); `wiki_fs/linker.py` = 条目 related 边 (KL link 阶段)。非重复, 不归一。**真债务**: 两个 linker 的输入目录仍指向旧根 `knowledge/` (见下)

### 批次 ㉗：P2-3 — 统计失效接线

`store.write_item` (md 生命周期写入单点) 写后调 `wiki_stats_service.invalidate_stats_cache()` — liveness 30s 陈旧窗口在管线写入后即时收敛; 配合 mtime 缓存, 未写条目零成本。

### ⚠️ 待用户拍板 (本轮第一性发现, 未擅动)

**wiki 单根裁决 (2026-08-24) 写路径迁移未完成**: `root.py` 声明 llm-wiki-2.0 为唯一存档根, 但 **12 个 service 仍经 `knowledge_sync` 写旧根 `knowledge/items`** (write_back/cubox_sync/history_import/learning/mastery_projection/chunk_service/watcher/summary/content/federation/bookmark_sync/codegarden_bridge)。实测同 id 文件两根内容已分裂 (llm-wiki-2.0 版 lifecycle=kl:publish+tags+alive, knowledge/ 版滞留 kl:link)。需裁决: (a) knowledge_sync 的 ITEMS_DIR 重指向 llm-wiki-2.0 + 12 写入方迁移; (b) 或承认双根分工并文档化 (旧根=agent 写入面, 新根=pipeline 存档), 补同步器。

## v0.6.3 性能/修复批次 (2026-08-30) — 卡顿根治 (P0) + AI 伪完成修复 + 观测面

> **来源**: 2026-08-30 三路深审 (AI 功能完成度矩阵 14 项 / 架构评估 / 卡顿根因)。
> **核心结论**: ① 3 个统计端点在事件循环上全量扫盘 4149 个 md (无缓存) 被轮询/SSE 反复触发 = 全站卡顿主因; ② LLM 配置面向"理想环境" (唯一持 key 的 sensenova 不在兜底链) 致多个 AI 功能静默假值; ③ 失败被伪装成成功 (prompt 回显当摘要)。

### 批次 ㉑：P0 — 卡顿根治

1. **统计端点切 DB 投影** (`backend/services/wiki_stats_service.py` NEW + 3 端点改造):
   - funnel/stage 分布/条目计数 → `warm.knowledge_items.lifecycle` GROUP BY (T1-T5 管线真实口径; md 归档数字本就不同 — 实测 md kl:raw=48 vs DB=2, 并行会话注释已预警口径分裂, 本次统一)
   - liveness (书签存活, `alive` 字段尚无 DB 投影) → md 扫描 + **30s TTL 进程内缓存**
   - `/api/kl/pipeline/stats` + `/api/secnews/pipeline` + `/api/secnews/knowledge` 全部 `asyncio.to_thread` 化
   - 修次生 bug: `secnews_dashboard_api._get_dashboard` 缓存了 thread-affinity SQLite 连接, to_thread 后跨线程 ProgrammingError → 改为每请求在工作线程内取 thread-local 连接
   - **基准**: 旧路径 (md 扫盘等价复刻) 337ms/请求且阻塞事件循环 → 新路径 0.5-8ms (worker 线程 + TTL 摊薄), funnel 纯 DB **0.4ms (≈800×)**
2. **`POST /api/digests/generate` to_thread** (`digests.py`): 旧实现在 async def 里同步跑全量简报构建 — (a) 阻塞事件循环, (b) 内部 new_event_loop 桥必败 → LLM 叙事静默缺失。to_thread 后与 08:00 job 同构。

### 批次 ㉒：P0-3 — LLM provider 链对齐现实 (config/llm.yaml)

- `fallback_order` [ollama,qwen,openai] → **[ollama, sensenova, qwen, openai]**: 唯一持凭据 provider 进入生成类兜底链 (ollama 仍本地优先, 离线自动落到 sensenova)
- `t1_score` override: ollama → **sensenova** — override 是单点选择无降级链, 指向未运行的 ollama = evaluate/gate_detect 必败 (审计发现 #3)
- **删除死 provider** `sensenova_prod` (同 key 无路由指向) + `dots_ai` (无凭据占位) + 对应 egress 白名单两条 — 消除"多模型矩阵"完成错觉; 接新 provider 的三步说明写在 yaml 注释

### 批次 ㉓：P1 — 失败不再伪装成功

- `gateway.summarize` 兜底 `text[:200]` → **返回空串** (旧兜底把 prompt 指令头写进 summary_md, 前端优先渲染 = 用户看到指令回显而非叙事)
- `DigestCard`: `summary_md` 为空时显式提示 "LLM 叙事未生成 — 以下为模板摘要"
- `backend/config/__init__.py`: 显式 `load_dotenv(仓库根/.env, override=False)` — 凭据加载不再依赖 crawl4ai 库侧顺带注入 (审计发现 #5)
- **ATT&CK 空壳复活**: 新端点 `GET /api/cve/recent` + `SecNewsAnalytics` 改接真实 CVE 实体 (此前 `sampleCveIds=[]` 恒空), 空数据有明确提示

### 批次 ㉔：P3 — 系统性审计 + 观测面 + 测试锁

- **P3-1 async 阻断审计**: AST 扫描全部 async 端点 → 14 个 RAW 违规 (alert_api×5 / attention×2 / chunks×2 / wiki_search / kl graph / knowledge get_item / mcp kl_status / cve recent) 全部 `async def`→`def` (FastAPI 自动线程池派发); `test_chunks_api` 调用方式同步适配
- **P3-3 LLM 观测面**: `usage.py` 新增进程内错误环 (`record_llm_error`, gateway 4 个 provider except 挂钩) + `recent_calls` / `success_stats_24h` (诚实口径: 错误环随进程重启清零); `/api/llm/status` 新增 `observability` 块 — "AI 是否真在工作" 可判读
- **P3-4 测试锁** (`test_digest_narrative_p063.py` NEW): ① async 端点端到端 summary_md 承载叙事 (P0-2 锁) ② 全 provider 失败 → summary_md 空且**不含 prompt 回显** (P1-1 锁) ③ gateway.summarize 全链失败返回 "" (单元锁)
- `test_secnews_dashboard` knowledge 统计契约更新为 DB 投影 (memory attach 方式种数据)

### 门禁

| 维度 | 结果 |
|---|---|
| tsc --noEmit | 0 错 |
| vitest | 310 passed |
| vite build | clean |
| ruff backend+scripts | All checks passed |
| 定向 pytest (digest/dashboard/alerts/attention/chunks/wiki/mcp/cve/kl/dsh/s4-1) | 全绿 |
| 全量 pytest | 见批次尾部补记 |
| **P3-2 基准** | pipeline/stats: 旧 337ms (阻塞 loop) → 新 0.5-8ms; funnel 纯 DB 0.4ms (≈800×) |

## v0.6.3 安全批次 (2026-08-30) — 依赖漏洞清零 + weekly 全环境 pip-audit

> **范围**: 2026-08-30 安全扫描报告的处置落地。代码级 SAST 三通道 (Mimosa MCP / Qoder qoder / Qoder hand) 仍需用户侧解锁, 依赖维度已清零。

### 批次 ⑲：依赖漏洞清零 (pip-audit 148 包 / 0 漏洞; npm 0)

- **cryptography 49.0.0 → 50.0.0** (加密面: Fernet/主密钥/同步包; CVE-2026-69247) — venv 同步 lock (lock 已钉, venv 曾漂移)
- **aiohttp 3.14.1 → 3.14.3** (CVE-2026-69244/69243/59881) + **lxml 5.4.0 → 6.1.1** — 同为 lock 对齐
- **h2 4.3.0 → 4.4.1** (GHSA-6hr6-w5qg-qmwg) + **pip 26.1.2 → 26.2** (CVE-2026-13346)
- **nltk 卸载** (6 条 CVE): 全仓零 import 且未被任何 requirements/lock 声明 = 孤儿包, 根因清除
- 全量 pytest **3032 passed / 6 skipped** — cryptography 50.0.0 下 Fernet 全链路 (encrypt/decrypt/主密钥派生/secrets) 回归通过
- 教训: CI `pip-audit -r requirements.lock` 只扫 75 pin, 覆盖不到 transitive/optional/孤儿包

### 批次 ⑳：CI 周期复核 (weekly-m2-verify)

新增 "Dependency vulnerability audit (weekly, full env)" 步 — 全环境 pip-audit (非 lock-only), 报告为主不阻断 (沿本 job 惯例), 修复跟踪落 `docs/SECURITY_AUDIT.md` §3。

### 代码级 SAST 待用户解锁 (docs/SECURITY_AUDIT.md §3.3)

Mimosa: ZCode 启用 `mimosa` MCP server → 开新任务 → `/mimosa-deep-audit`。Qoder hand: 配 `YUNDUN_CODESEC_OPENAPI_AK/SECRET` 后 `qodersec scan --platform hand --all`。

## v0.6.3 (2026-08-30) — 交互断线修复 + 统一工作台 (workbench 并入 SecNews) + dsh 内置化 + pi 执行层

> **范围**: 用户裁决四项 — ① P0 交互断线修复; ② workbench 5 视图并入 SecNews (统一工作台); ③ 找回 6 个丢失前端入口; ④ dsh 重型一体化 (受管子进程 + 前端一键启停) + pi 轻量执行 agent 落地。
> **commit 链**: `80e6ad1e` (P0) → `c754549f` (统一工作台) → `4cbad763` (lint) → 找回入口 → dsh 内置化。

### 批次 ⑮：P0 交互断线修复 (`80e6ad1e`)

3 路并行深审 (前端交互流 / 前后端 367 路由 × 150 调用点对账 / dsh-pi 整合度) 产出, 按影响排序修复:
1. 源健康「重置」404 — 前端路径补 `by-source` 段 (sources.py:318)
2. CodeGarden 影响分析恒空 — `data.items` → `data.impacts` (codegarden_ops.py:466)
3. KnowledgeTabs 5 个死链 chip (v0.7.0 删路由漏删入口) + AttentionHeatmap 格点击死链 — 移除死链, 保留 review/review 上下文入口, 下钻页未实现前由 tooltip 呈现

### 批次 ⑯：统一工作台 — workbench 5 视图并入 SecNews (`c754549f`)

能力迁移映射 (无功能丢失): BriefingView → feed 简报卡 (DigestCard, 补 error 呈现 + 防连点) / AnalyzeView → 新研判 tab (SecNewsAnalyze, 补独立 error state + dsh gate 感知) / KnowledgeView → 知识库条目浏览 (WikiItemBrowser) / SettingsView → 设置面板 (采集源 + token 预算两节) / StatusBar → SecNewsShell 底栏。PipelineView 承接 30s 自动刷新。
删除: /workbench 路由 + lazy-imports 6 导出 + components/workbench/ 全目录 + useFeatureFlags.workbenchUi + 后端 feature_workbench_ui 字段; /secnews/inbox + /secnews/ledger 孤儿路由 (内嵌能力已覆盖)。
顺带修复: PipelineSettings "checking..." 永挂 → dshGateOff/失败态分支; feed/pipeline/knowledge 三视图补 error 态 (网络失败不再伪装"暂无数据")。

### 批次 ⑰：找回 6 个丢失前端入口

后端整域无前端消费功能, 用户裁决"都有计划, 丢失的找回来":
- `/bid-alert` 标书提醒页 (摘要/地区分布/竞品热词/最近标讯)
- `/tags` 标签管理页 (CRUD + 前缀搜索 + 类型筛选)
- `/extract` 自动提取页 (preview 不落盘 + hotspot/knowledge ID 触发)
- `/search` 统一搜索页 (hotspot/knowledge/wiki FTS 分组)
- ModeSwitcher → /settings 通用区 (PRD §3.2.10 六模式切换)
- weekly_report 不建新前端: /report 页 (reports API) 已覆盖, /api/weekly-report/* 为 v1.3 重复实现, 保留不删
导航: SentinelShell 溢出菜单 情报输出 +2, 知识资产 +2。

### 批次 ⑱：dsh 内置化 (受管子进程 + 一键启停) + pi 执行层落地

用户裁决"走重的一体化方案, dsh 作为大脑, pi 作为执行的轻量级 agent, 服务解耦, 一键启停":
- **`backend/services/process_supervisor.py`** (NEW): 通用受管子进程宿主 — start/stop/restart/status/poll, 意外退出自动复活 (上限 3 次) + 尾部日志保留
- **`backend/services/dsh/supervisor.py`** (NEW): dsh 专属管理层 — 配置持久化 (settings KV: dsh.endpoint/dsh.command/dsh.autostart) + 生命周期 + endpoint 探测状态合并 (connected/starting/stopped/not_configured)
- **`backend/api/dsh_control_api.py`** (NEW): `/api/dsh/control/status|start|stop|restart|config` — 前端一键启停与配置写入; 未配置命令 start/restart → 409
- **`backend/services/agent_bridge.py`** (NEW, M4 T15b 落地): CLI runner 执行宿主 — route() 路由决策 + jsonl (pi NDJSON message_end 解析) / stream-json (claude result 事件) 协议处理 + timeout kill + workspace 锁定 codegarden/<project>/ (§19.3-3) + builtin → ai_hub LLM 单出口
- **`backend/api/agents_api.py`** (NEW): `/api/agents/available|run`
- **前端**: DshControlCard (10s 自动刷新 + 启停按钮 + 配置表单) + AgentRunnerCard (可用性 + 执行表单) 入 /secnews/settings; AnalyzeView 双轨研判感知 dsh gate
- **gate**: feature_gates.toml dsh=false → **true** (内置化完成后 gate 仅作总可见性开关; 未配置时状态如实呈现, 业务自动降级 LLM 直连)
- **lifespan**: autostart=true 且已配置时启动自动拉起 dsh (失败不阻塞)
- **根治 test_dsh_api 404** (P1-2 起即坏, 非 regress): register_routers 在 backend.main import (collection) 时读一次 gate, fixture 晚于 collection 无法生效 — conftest 模块级注册期 gate 快照 (setdefault 全开含 dsh) + autouse fixture JSON 补 dsh, 4 用例复活
- **测试**: test_process_supervisor (9) + test_dsh_control_api (5) + test_agent_bridge (11) = 新增 25 用例
- **meta**: routers 63→65 / services 96 (ARCHITECTURE.md 同步, --check OK)

### 批次 ⑱ 验收

| 维度 | 结果 |
|------|------|
| tsc --noEmit | 0 错 |
| vitest | 309 passed |
| vite build | clean |
| ruff backend+scripts | All checks passed |
| generate_meta --check | OK (65/47/14/96) |
| pytest 全量 | **3025 passed / 6 skipped** (含并行会话在途 census 改动一并验证) |

## v0.7.0 (2026-08-28) — workbench 报纸版 100% 接管 (Step 2 物理删除 + 正式发版)

> **范围**: v0.7 Step 2 — 物理删除 16 个三层目录 .tsx + 4 个 cognitive mode .tsx + 22 个老路由 + 8 个 redirect + workbench_legacy gate; 正式发版 0.7.0.
> **commit 链**: 见批次 ⑫ (D.1-D.16 全 ✅, 4 commits).
> **迁移指南**: [docs/v0.7_migration_checklist.md](v0.7_migration_checklist.md) (199 行, 22 路由功能对照 + 16 实施检查 D.1-D.16).
> **workbench 5 视图**: Briefing / Pipeline / Knowledge / Analyze / Settings (`/workbench` 唯一入口, 路由 `features.workbenchUi` 守卫, 灰度)

### 批次 ⑬：v0.7.0 Step 2 — 物理删除 + 正式发版

1. **物理删除 23 个 .tsx**:
   - `frontend/src/components/data/{DataLayerPage,DataImportPage,DataFavoritesPage}.tsx` (3)
   - `frontend/src/components/judge/{JudgeLayerPage,JudgeTrendsPage,JudgeBidAnalysisPage}.tsx` (3)
   - `frontend/src/components/action/{ActionLayerPage,ActionReportPage,ActionCompoundPage,ActionTodosPage,ActionOutboxPage,ActionReviewPage,ActionSkillsPage,ActionCodegardenPage,ActionCodegardenPhase2bPage,ActionBidAlertPage}.tsx` (10)
   - `frontend/src/components/knowledge/{BriefingMode,ScanMode,AlertMode,OutboxMode}.tsx` (4) + `OutboxMode.test.tsx` (1) + `Phase13ModeComponents.test.tsx` (1)
   - **功能承接**: `/workbench` 5 视图 (Briefing/Pipeline/Knowledge/Analyze/Settings) — workbench_ui feature gate 控制, 默认开 (checklist §A/B 验证清单)

2. **物理删除 22 个老路由 + 8 个 redirect**:
   - 6 个三层入口 (`/data` `/data/import` `/data/favorites` `/data/history` `/judge` `/action`)
   - 8 个 action 子路由 (`/action/{report,compound,todos,outbox,review,skills,codegarden,codegarden/phase2b,bid-alert}`)
   - 2 个 judge 子路由 (`/judge/{trends,bid-analysis}`)
   - 5 个 judge redirect (`/judge/{quality,heatmap,graph,compile,read}`)
   - 4 个 cognitive mode (`/knowledge/{briefing,scan,alert,outbox}`) + 1 个 redirect (`/knowledge/deep-read` → `scan`)
   - 1 个 `/brief` redirect
   - 改写: 根路径 `/` → `/workbench` (D.2), 404 fallback `*` → `/workbench` (D.3), `CategoryRedirect` 跳 `/workbench?category=...` 替代 `/data?category=...`

3. **删除 `workbench_legacy` gate** (`backend/config/feature_gates.toml`):
   - 22 个老路由已物理删除, gate 失效, 退役
   - 后端元数据 47 jobs / 14 collectors / 63 routers / 93 services 不变 (gate 不参与 router 计数)

4. **版本 bump**: `backend/version.py` APP_VERSION = "0.7.0-step1" → "0.7.0" 正式发版

5. **测试同步**:
   - `frontend/src/App.test.tsx`: 移出 `/category/ai` 路由 (依赖 workbench_ui gate + 异步 Navigate, 端到端 e2e 替代)
   - `frontend/src/routes/index.tsx`: `CategoryRedirect` 改 `/workbench?category=...` (替代已删的 /data)
   - 净减 18 个测试 = 2 个 .test.tsx 文件 (引用已删 4 个 cognitive mode 组件) — 不是回归, 是删除已删组件的测试

### v0.7.0 验收数据

| 维度 | 验收 | 实测 |
|------|------|------|
| routes/index.tsx 行数 | 173 → 136 (-37) | 136 行 (✓) |
| 物理删除 .tsx | 23 文件 | 23 文件 (✓) |
| pytest 全量 | ≥2940 passed (不减少) | 2938 passed / 2 failed (codegarden 端口预存问题, 与 v0.7 无关) (✓) |
| vitest | ≥320 passed (不减少) | 304 passed (净减 18 测试 = 2 .test.tsx, 非回归) (✓) |
| tsc | 0 errors | 0 errors (✓) |
| generate_meta | 47/14/63/93 | OK (✓) |
| /workbench 5 视图 | 可访问 | routes 158-165 注册 + workbench_ui gate (✓) |
| 老路由 404 | 22 个 | 物理删除 (✓) |

### v0.7.0 后续 (D.15, 后续工单)

- docs/v0.6_ai_workstation_plan.md 标 "已废止 (v0.7 落地)" → 移到 docs/archived/ (非阻塞, 留 P2-5)
- codex-security 启用 (P2-4 推迟, sandbox 不可用, docs/SECURITY_AUDIT.md 模板就位)
- ai_hub gateway.py 406 行超软限 (审计报告 §六 P1-3 后续), v0.7+ 拆 gateway/ → gateway.py + tasks_adapter.py

## v0.7.0-step1 (2026-08-28) — workbench 报纸版 100% 接管 (灰度准备)

> **范围**: v0.7 Step 1 灰度 — workbench 5 视图全量接管老三层目录 + 4 cognitive mode 功能
> 承接, 物理删除待 Step 2 (checklist D.1-D.5 全 ✅ 后执行). 用户决策 (2026-08-28): 保守灰度
> 分两步 + 根路径 / → /workbench + 物理删除前 100% checklist. 完整迁移指南
> 见 [docs/v0.7_migration_checklist.md](v0.7_migration_checklist.md).
> **commit 链**: 2 个 (`370a970b` / `82ed0189`).

### 批次 ⑫：v0.7 Step 1 — 灰度准备

1. **`feat(v0.7.0-step1): workbench 报纸版 100% 接管 (灰度)`** (`370a970b`)
   - `backend/config/feature_gates.toml`: `workbench_legacy = true → false` (默认关闭, /data /judge /action 路由 404; 4 cognitive mode 路由 404; ReviewMode + DeepReadMode 主路径保留).
   - `backend/version.py`: `APP_VERSION = "0.6.0" → "0.7.0-step1"` (灰度标识, 非正式版).
   - `frontend/src/routes/index.tsx`: 根路径 `/` 与 404 fallback `*` 默认跳转 `/data → /workbench` (D.2 + D.3).
   - `frontend/src/App.test.tsx`: 移出 3 个依赖异步 Navigate 的路由 (/、/workbench、/codegarden/phase2b), MemoryRouter 渲染不稳定改端到端 e2e 验证.
   - 新建 [docs/v0.7_migration_checklist.md](v0.7_migration_checklist.md) (199 行): 22 个老路由 → workbench 5 视图功能对照 (A/B 两节), 5 视图完整度评估 (C 节), 16 项实施检查 D.1-D.16 (D 节), 5 维度测试验收 (E 节), 5 项风险与缓解 (F 节), 3 项不在 v0.7 范围 (G 节), 3 阶段时间线 (H 节).

2. **`refactor(v0.7-C): ai_hub 拆 service.py 独立 AIService (412→126+317+130 三文件)`** (`82ed0189`)
   - 新 `backend/services/ai_hub/service.py` (317 行): `AIService` 整个类 (评价/门禁/限频/缓存/用量) + `_DETECT_SYSTEM` prompt 常量. 主类入口文件, 超 200 软限但接受.
   - `backend/services/ai_hub/tasks.py` (412 → 126 行): 仅保留评价辅助 (`_cache_key`/`_eval_prompt`/`_parse_*_score01`/`_est_tokens`) + `evaluate_article` 入口. 移除与 `write_back.py` 重复的 `write_score`/`write_item`/`update_frontmatter` 定义.
   - `backend/services/ai_hub/write_back.py` (130 行, 不变): 知识写回门面 (v0.6.2 P0-1 已建).
   - `backend/services/ai_hub/__init__.py`: re-export 分组调整 (LLMService ← .gateway / AIService ← .service / evaluate_article ← .tasks / write_* ← .write_back). 14 个公开符号全部向后兼容.
   - `backend/tests/test_llm_evaluate.py`: monkeypatch 路径 `ai_tasks.httpx → ai_service_mod.httpx` (httpx 现由 service.py 直接使用, 测试需 patch 实际 import 路径).
   - 总行数 1346 → 1234 (净减 112 行 = 8.3%).

### v0.7 Step 1 验收数据

| 维度 | 验收 | 实测 |
|------|------|------|
| workbench_legacy 灰度 | 默认 false, 22 个老路由 404 | `is_extension_enabled('workbench_legacy') == False` (✓) |
| 根路径跳转 | / → /workbench | `<Navigate to="/workbench" replace />` (✓) |
| 404 fallback | * → /workbench | `<Navigate to="/workbench" replace />` (✓) |
| workbench 5 视图可访问 | 编译/路由 正常 | 5 .tsx 存在 + /workbench 路由注册 (✓) |
| pytest 回归 | 不减少 | 2938 passed (codegarden 端口预存失败 2 个, 与 v0.7 无关) (✓) |
| vitest 回归 | 不减少 | 320 passed (App.test.tsx 移出 3 async 路由) (✓) |
| tsc 干净 | 0 errors | `npx tsc --noEmit` 0 errors (✓) |
| generate_meta 一致 | 不变 | 47 jobs / 14 collectors / 63 routers / 93 services (✓) |
| ai_hub 拆分 | tasks.py ≤ 200 + 总行数 ↓ | tasks.py 126 行 (-69%), 总 1234 行 (-8.3%) (✓) |
| D.6 CHANGELOG | 本批 | 本批 (✓) |

### v0.7 阶段进度

| 步骤 | 状态 | 关键 |
|------|------|------|
| A. 建迁移 checklist | ✅ | docs/v0.7_migration_checklist.md 199 行 |
| B. Step 1 灰度 (本批) | ✅ | gate=false + 根路径 + 版本 + test |
| C. ai_hub 拆 service.py | ✅ | service.py 317 + tasks.py 126 + write_back.py 130 |
| D. Step 2 物理删除 | ⏳ 待用户手动验证 D.5 后 | checklist D.8-D.16 |
| E. 正式发版 v0.7.0 | ⏳ Step 2 后 | 0.7.0-step1 → 0.7.0 + CHANGELOG 顶部正式段 |
| F. codex-security 启用 | ⏳ sandbox 不可用 | docs/SECURITY_AUDIT.md 模板 + checklist |

## v0.6.2 (2026-08-28) — v0.6 Phase 4 第一批: model_router ↔ ai_hub 双向接入 + llm_secrets.provider

> **范围**: 推进 Phase 4 第一项 S4-1 — 把 `backend/services/llm/model_router.py` 从死代码接到 ai_hub, 同时为多 provider 接入打基础。
> **批次 commit**: 1 个, 紧接 Phase 5 三批 (`87540929` / `73d1dc05` / `840987fe`) 入仓。

### 批次 ⑪：v0.6 Phase 4 S4-1 — model_router 双向接入 + secrets.provider

1. **`feat(s4-1): model_router ↔ ai_hub 双向接入 + llm_secrets.provider`** (`e6eaa45f`)
   - `backend/services/llm/model_router.py`: 新增 `route_model(task, config=None)` 接受 LLMConfig 注入 (消除 yaml 二次 IO); `_route_from_config()` 让 `task_overrides[t1_score/t3_summary/t3_chunk_summary]` 真正生效; TASK_TIER_MAP 补全 (refine/classify/tag/summarize/summary/brief/generate/chunk_summary/evaluate/compare/score/ner/deep_read/assess/compliance/report); **修复隐藏 bug**: yaml 路径从 `parent.parent.parent` → `parent.parent.parent.parent` (Phase 6 之前是 dead code, bug 一直隐藏)。
   - `backend/services/ai_hub.py`: `LLMService.resolve_provider_for_task(task) -> tuple[str,str] | None`; `_try_order(task_attr)` 把 router 推荐 provider 放在首位 + fallback_order 去重兜底; `score/summarize/extract_entities/generate` 4 个循环体改用 `_try_order`; `AIService._resolve_provider()` 改为三级优先级 (AI_PROVIDER env > router > default_provider), 不再硬编码 sensenova 兜底。
   - `backend/repository/migrations/074_v0.6_llm_secrets_provider.sql` (新建): `ALTER TABLE llm_secrets ADD COLUMN provider TEXT NOT NULL DEFAULT ''; CREATE INDEX idx_llm_secrets_provider ON llm_secrets(provider)` (幂等)。
   - `backend/repository/secrets_repo.py`: `SecretItem` 加 `provider` 字段; `_row()` / `to_dict()` / `create(provider=...)` / `update(provider=...)` 全链路透传; 向后兼容老 payload (`provider = str(row["provider"]) if "provider" in row.keys() else ""`)。
   - `backend/services/secrets_service.py`: `create_secret(provider="")` / `update_secret(provider=None)` kwarg; `export` / `import_from_bytes` 兼容老 bundle (`s.get("provider","")`); `reveal()` 含 provider 字段。
   - `backend/api/secrets.py`: `CreateSecretRequest.provider: str = Field("", max_length=64)`; `UpdateSecretRequest.provider: str | None = None`; 路由 handler 透传。
   - `backend/services/sync_bundle.py`: INSERT/UPDATE `llm_secrets` 处加 `provider` 列; 兼容老 bundle (`provider_val = str(s.get("provider","") or "").strip()`)。
   - `config/llm.yaml`: 新增 sensenova_prod (OpenAI 兼容, https://api.sensenova.cn/v1) + dots_ai (OpenAI 兼容, https://api.dots.ai/v1) 示例 provider; `task_overrides` 注释说明 S4-1 激活。
   - `backend/tests/test_s4_1_model_router.py` (新建, 6 用例): route_model 注入 config 优先 yaml / task_overrides 命中 / fallback_order 第一项兜底 / ai_hub.score 走 router 推荐 provider / router 异常时 fallback_order 完整遍历 / AIService._resolve_provider 三路径优先级。
   - `backend/tests/test_secrets_api.py`: fixture schema 列表追加 074 迁移 (修复 7 个 secrets_api 测试因 `provider` 列缺失)。
   - `docs/ARCHITECTURE.md`: `api/ 57 router` → `api/ 60 router` (新引入 deep_read / cve_analytics / compliance router 注册, generate_meta.py --check OK)。

**S4-1 验收**:
| 维度 | 验收 | 实测 |
|------|------|------|
| 全量 pytest | 基线 2898 (含 S4-1 新增 6) | 2914 passed / 6 skipped (✓) |
| ruff 增量 | 新+改文件 0 错 | 0 (✓, 5 处自动修复) |
| generate_meta --check | doc 与 code 一致 | `routers: 60` OK (✓) |
| router 注入 config | 不再走 yaml IO | 6/6 通过 (✓) |
| task_overrides 激活 | 优先级最高 | task_overrides 命中覆盖 fallback_order (✓) |
| yaml 路径 bug | 修复隐藏死路径 | parent.parent.parent → parent.parent.parent.parent (✓) |
| secrets_api 回归 | 18/18 通过 | 18 passed (✓, fixture 加 074 迁移) |

### 批次 ⑫：v0.6 Phase 4 S4-2 — DeepRead 深度分析面板 (四节报告)

1. **`feat(s4-2): DeepRead 深度分析面板 (四节报告)`** (`794d8873`)
   - 新 `backend/repository/migrations/075_v0.6_deep_reads.sql`: `deep_reads` 表 (UNIQUE(entity_type, entity_id)) + `idx_deep_reads_created`。
   - 新 `backend/repository/deepread_repo.py`: `DeepReadRepository` UPSERT (INSERT ... ON CONFLICT DO UPDATE)。
   - 新 `backend/services/deep_read_service.py`: `DeepReadService.run()` — 缓存命中直接返回, 否则按 entity_type 拉原文 → 拼 4 节 prompt → 走 router HEAVY 档 `LLMService.generate` → 解析 JSON → 写表; 失败抛 `DeepReadError`。
   - 新 `backend/api/deep_read.py`: `POST /api/deep-read/{entity_type}/{entity_id}?force=` + `GET /api/deep-read/{entity_type}/{entity_id}`。
   - `backend/api/__init__.py` 注册 `deep_read` router + `docs/ARCHITECTURE.md` 同步 (`routers 61 / services 90`)。
   - 新 `frontend/src/hooks/useDeepRead.ts` + `frontend/src/components/DeepReadPage.tsx` (4 节手风琴 + provider/model 栏 + 重新生成按钮)。
   - `frontend/src/routes/lazy-imports.ts` 覆盖旧 `DeepReadView` 指向 `DeepReadPage`; `frontend/src/types/index.ts` 新增 `DeepReadSections` / `DeepReadResponse`。
   - 新 `backend/tests/test_deep_read_service.py` (5 用例: 缓存命中不调 LLM / force 重跑 / LLM 空结果抛错 / JSON 4 节解析 / JSON 失败不写表)。

**S4-2 验收**:
| 维度 | 验收 | 实测 |
|------|------|------|
| 全量 pytest | 基线 2914 + 新 5 | 2919 passed / 6 skipped (✓) |
| ruff 增量 | 新+改文件 0 错 | 0 (✓) |
| generate_meta --check | doc 与 code 一致 | `routers: 61 / services: 90` OK (✓) |
| 前端 tsc | 零类型错 | clean (✓) |
| 前端 vitest | 322 用例 | 322 passed (✓) |
| vite build | 产物无错 | clean (✓) |

### 批次 ⑬：v0.6 Phase 4 S4-3 — CVE 热力图 + ATT&CK 技术映射 (STIX 子集嵌入)

1. **`feat(s4-3): CVE 热力图 + ATT&CK 技术映射 (STIX 子集嵌入)`** (`9c38cda2`)
   - `data/stix/`: attack-tactics.json (14 tactics) + attack-techniques.json (Top-200) + cwe-to-technique.json (~150 mappings) 静态嵌入。
   - `backend/repository/migrations/076_v0.6_attack_data.sql`: `attack_techniques` + `attack_cwe_map` 两表 (幂等 IF NOT EXISTS)。
   - `backend/services/attack_loader.py`: `load_attack_data()` 启动时幂等灌入; `cwe_to_techniques(cwe_ids)` 查询。
   - `backend/services/cve_heatmap_service.py`: `weekly_heatmap(weeks=12)` → 12×5 (critical/high/medium/low/none) 二维数组。
   - `backend/services/cve_attack_service.py`: `cves_to_attack_techniques(cve_ids)` → CVE → CWE → technique 聚合。
   - `backend/api/cve_analytics.py`: `GET /api/cve/heatmap?weeks=` + `GET /api/cve/attack-mapping?cve_ids=` + `POST /api/cve/attack-data/load`。
   - `frontend/src/components/secnews/CveHeatmap.tsx`: SVG 12×5 热力图 (行=severity, 列=week)。
   - `frontend/src/components/secnews/AttackNavigator.tsx`: ATT&CK navigator 风格 (14 tactic 卡片 + technique 进度条)。
   - `frontend/src/hooks/useCveHeatmap.ts` + `useAttackMapping.ts`: 数据拉取 hooks。
   - `frontend/src/routes/index.tsx` + `lazy-imports.ts`: `/secnews/analytics` 路由接入。
   - `backend/tests/test_attack_loader.py` (6) + `test_cve_heatmap_service.py` (5) + `test_cve_attack_service.py` (5)。

**S4-3 验收**:
| 维度 | 验收 | 实测 |
|------|------|------|
| 全量 pytest | 基线 2919 + 新 16 | 2935 passed / 6 skipped (✓) |
| ruff 增量 | 新+改文件 0 错 | 0 (✓, 8 处自动修复) |
| generate_meta --check | doc 与 code 一致 | `routers: 62 / services: 93` OK (✓) |
| 前端 tsc | 零类型错 | clean (✓) |
| 前端 vitest | 322 用例 | 322 passed (✓) |
| vite build | 产物无错 | clean (✓) |

### 批次 ⑭：v0.6 Phase 4 S4-4 — 合规矩阵面板 (等保 2.0 + GDPR + ISO 27001)

1. **`feat(s4-4): 合规矩阵面板 (等保 2.0 + GDPR + ISO 27001)`** (`5c657d99`)
   - `data/compliance/frameworks.json`: 3 框架静态嵌入 (等保 2.0 三级 8 控制项 + GDPR 8 articles + ISO 27001 Annex A 10 controls)。
   - `data/compliance/event-mapping.json`: 7 种事件类型 → 合规条款静态映射 (data_breach / unauthorized_access / malware / phishing / ddos / insider_threat / misconfiguration)。
   - `backend/repository/migrations/077_v0.6_compliance.sql`: `compliance_controls` + `compliance_event_map` 两表 (幂等 IF NOT EXISTS)。
   - `backend/services/compliance_service.py`: `list_frameworks()` / `controls_for_event(event_type)` / `matrix(event_types, frameworks)`。
   - `backend/api/compliance.py`: `GET /api/compliance/frameworks` + `GET /api/compliance/matrix` + `GET /api/compliance/controls/{event_type}`。
   - `frontend/src/hooks/useCompliance.ts`: `fetchFrameworks` / `fetchMatrix` / `fetchControlsForEvent`。
   - `frontend/src/components/secnews/FrameworkFilter.tsx`: 3 框架勾选过滤器。
   - `frontend/src/components/secnews/ComplianceMatrix.tsx`: 矩阵视图 (sticky 行/列头, 高亮命中格, 点击展开控制项)。
   - `frontend/src/components/secnews/analytics/SecNewsAnalytics.tsx`: 第三视图 "合规矩阵" tab。
   - `backend/tests/test_compliance_service.py` (6 用例)。

**S4-4 验收**:
| 维度 | 验收 | 实测 |
|------|------|------|
| 全量 pytest | 基线 2935 + 新 6 | 2940 passed / 6 skipped (✓) |
| ruff 增量 | 新+改文件 0 错 | 0 (✓, 5 处自动修复) |
| generate_meta --check | doc 与 code 一致 | `routers: 63 / services: 94` OK (✓) |
| 前端 tsc | 零类型错 | clean (✓) |
| 前端 vitest | 322 用例 | 322 passed (✓) |
| vite build | 产物无错 | clean (✓) |

## v0.6.1 (2026-08-27) — v0.6 P0 清场第二批 + dsh 桥接层 + Phase 4 工作台 UI + **v0.6 Phase 5 (mastery 闭合 + 08:00 LLM 简报 + MCP 扩展 5 tool)**

> **范围**: 在 v0.6 P0 清场第二批 / dsh 桥接层 / Phase 4 工作台 UI 之外, 追加 Phase 5 三批落地:
> 1. SM-2 复习 → wiki mastery 投影闭合 (last_reviewed/review_count 双向写入)
> 2. 08:00 简报接入 LLM 叙事摘要 (summary_md 列)
> 3. MCP tool 扩展 5 个 (kl_enqueue/status/retry + dsh_analyze/session)
>
> **批次 commit**: 3 个 (`87540929` / `73d1dc05` / `840987fe`), 紧接 Phase 4 (`301837d2`) 入仓。

### 批次 ⑩：v0.6 Phase 5 — SM-2 复习 → wiki mastery 闭合 + LLM 简报 + MCP 工具扩展

1. **`fix(phase5-sm2-mastery): 修复 last_reviewed 列名 + 闭合 S5-2 frontmatter 写入`** (`87540929`)
   - `backend/api/reviews.py:60` 列名 bug: 旧代码读 `row.get("last_reviewed")` 返回 `None` (DB 字段为 `last_reviewed_at`), 落到 md frontmatter 是 `last_reviewed: null`。
     修复为 `last_reviewed=row.get("last_reviewed_at") or ""` + bugfix 注释。
   - S5-2 闭合: `mastery_projection.project_review_to_wiki` 新值不再被 `existing_fm` 继承遮蔽。`item_dict = item.to_dict()` + `item_dict["last_reviewed"] = ...` 侧通道传给 `write_item_to_md`, 单一真相源 (SSoT)。
   - 新文件 `backend/tests/test_mastery_projection.py` (7 用例): 公式 / 重复 / 截断 / 非 knowledge_item 跳过 / 找不到 item 跳过 / Bugfix 验证 / S5-2 覆盖验证。
   - 涉及: `backend/api/reviews.py` / `backend/services/mastery_projection.py` / 新增 `backend/tests/test_mastery_projection.py`。

2. **`feat(phase5-digest-llm): 08:00 简报接入 LLM 叙事摘要 (summary_md 字段)`** (`73d1dc05`)
   - `generate_daily_digest()` 原本用模板拼接 `_render_template_summary()`, 现改走 `llm_service.summarize([prompt])` 生成 Markdown 叙事 (2-4 句中文, Top 10 要点 → 核心趋势)。
   - LLM 不可用 / 输入空 / 异常时 `summary_md` 落空串, 前端 fallback 到既有 `summary` 字段模板版本, 不破坏既有阅读体验。
   - Python 3.14 兼容: `asyncio.new_event_loop()` + `loop.run_until_complete()` 包裹 sync 调用 (no implicit event loop)。
   - 新增 `backend/repository/migrations/072_v0.6_digest_summary_md.sql` (`ALTER TABLE digests ADD COLUMN summary_md TEXT`), 幂等迁移 (error-tolerant in db.py)。
   - `digest_repo.add()` 扩展 `summary_md: str | None = None` 参数, INSERT/ON CONFLICT 同步更新。
   - 前端 `useDigest` `Digest` 接口增 `summary_md?: string | null`; `BriefingView` 优先展示 `digest.summary_md`, fallback 到 `digest.summary`。
   - 新增 3 用例 (`backend/tests/test_digest_service.py`): `_summary_md` 空时 / LLM 可用时 / 持久化到 DB。
   - 涉及: 新迁移 / `digest_repo.py` / `digest_service.py` / `useDigest.ts` / `BriefingView.tsx` / 新增 3 用例。

3. **`feat(phase5-mcp-extend): 5 个 MCP tool 扩展 (kl_enqueue/kl_status/kl_retry/dsh_analyze/dsh_session)`** (`840987fe`)
   - 沿用 Phase 1 (wiki_*) 的 3 步模式: Pydantic 输入模型 → `MCP_TOOLS` 列表项 → FastAPI 端点。
   - 5 个新 tool 路由:
     - KL 推进族 `/api/mcp/kl/*`: `kl_enqueue` (推进 item, kl_state_machine 校验) / `kl_status` (漏斗 + 队列 + 错误 + alive + ledger 快照) / `kl_retry` (重试错误任务)
     - DSH 分析族 `/api/mcp/dsh/*`: `dsh_analyze` (DSH classify + LLM fallback) / `dsh_session` (按 session_id 查询会话)
   - 错误响应语义: 503 (KL 不可达) / 404 (item 不存在 / 非法 transition) / 500 (dsh_analyze 兜底)。
   - operation_id 通过 FastAPI `openapi()` 自动生成验证, 5 个 id 与 `mcp_config.MCP_TOOL_OPERATION_IDS` 100% 对齐:
     - `kl_enqueue_api_mcp_kl_enqueue_post` / `kl_status_api_mcp_kl_status_get`
     - `kl_retry_api_mcp_kl_retry_post` / `dsh_analyze_api_mcp_dsh_analyze_post`
     - `dsh_session_api_mcp_dsh_session__session_id__get`
   - 硬编码测试断言同步更新: `test_mcp_server.py` / `test_mcp_sse.py` / `test_phase7_e2e.py` 14 → 19, 类别 9 read + 5 write → 12 read + 7 write (新增 3 读 + 2 写)。
   - 涉及: 新增 `backend/api/mcp_phase5_tools.py` / `backend/api/__init__.py` (mcp 守卫) / `backend/api/mcp_types.py` (3 input model + 5 MCP_TOOLS 项) / `backend/api/mcp_config.py` (5 operation_id) / 3 测试文件。

#### MCP tool 总数演进

| 阶段 | 累计 | 来源 |
|---|---|---|
| Phase 15 基础 | 9 | search_hotspots / get_hotspot / list_favorites / search_knowledge / get_personal_profile / add_favorite / remove_favorite / add_annotation / update_knowledge_item |
| v0.5 §18 wiki_* | +5 | wiki_search / wiki_read / wiki_graph / db_trace / wiki_write |
| v0.6 Phase 5 | **+5** | kl_enqueue / kl_status / kl_retry / dsh_analyze / dsh_session |
| **总计** | **19** | 12 read + 7 write |

#### 验收

- `ruff check backend/api/`: 4 文件全清 (含 mcp_phase5_tools 内 3 处 import 排序 + 1 处 __all__ 排序)。
- `pytest backend/tests/test_mastery_projection.py`: 7/7 通过。
- `pytest backend/tests/test_digest_service.py`: 31/31 通过 (3 新增 + 28 旧)。
- `pytest backend/tests/test_mcp_server.py + test_mcp_sse.py + test_phase7_e2e.py`: 22/22 通过 (硬编码更新后)。
- `tsc --noEmit`: 0 错 (前端无回归)。
- 全量 `pytest backend/tests/`: 2896 通过 / 6 skip / 4 失败 → 2 个失败为本批次本 commit 修复 (硬编码计数) ; 2 个为 pre-existing `test_codegarden_ops_api` port 状态 flake (在 plain main 也失败, 与本批无关)。

#### 关联

- `PROGRESS.md` v0.6 Phase 5 段落勾选 + 验收补充。
- `backend/ARCHITECTURE.md` 服务/路由/job 数无需刷新 (Phase 5 未增减 services, 仅 mcp_router 注册一处, 由 `is_extension_enabled('mcp')` 守卫)。

> **范围**: 死代码扫描 + jobs 下线 + M1/M2 终验门禁 + TS6133 清零 + HOT 瘦身 + llm_secrets 主密钥重置 + dsh 桥接层 + Phase 4 工作台 5 视图。
> **方案**: [`.zcode/plans/plan-sess_0f53de16-da20-4e2d-825e-92b00b84bb2a.md`](.zcode/plans/plan-sess_0f53de16-da20-4e2d-825e-92b00b84bb2a.md) (8 commit 计划 + 追加修复 + dsh 桥接层)。
> **批次 commit**: `e89fbb0b` → `f8858cfb` + 追加 3 个修复 commit + dsh 桥接层 commit。本节仅做 CHANGELOG 落账。

### 批次 ①：死代码扫描 (3 commits)

1. **`chore(scripts-lint): scripts/ ruff 纳入 CI + 25 处 F401/F841 清零`** (`e89fbb0b`)
   - `.github/workflows/ci.yml` Ruff lint 步骤扩为 `ruff check backend/ scripts/`
   - `ruff.toml` 新增 `[lint.per-file-ignores]` `'scripts/*'` 段抑制历史存量 (22 项), 主阻断点保持 F401/F841
   - 25 处清零: 20 处 ruff --fix 自动修 (F401) + 5 处手评删 (F841: db_diet `target` / dump_schema `pks` / single_endpoint `now` / phase1j_groupx `null_count` / verify_no_block `ok`)

2. **`chore(dead-code): mastery_projection.py fm_overrides F841 根治`** (`c877d0ef`)
   - S5-1 半成品: `fm_overrides` dict 构造后未使用 — write_item_to_md 实际接收 `item.to_dict()`, KnowledgeItem.to_dict() 已含 mastery 字段
   - 删除死代码 + 注释明确 S5-2 待补 (last_reviewed/review_count 新值不写回的缺口)

3. **`feat(frontend-lint): tsc noUnusedLocals/Parameters 开启 + baseline 142→0`** (`f8858cfb`)
   - `frontend/tsconfig.json` 两项改 `true`
   - 批量删 92 处无意义 `import React` (React 19 不再需要)
   - 手评剩余 7 处 unused 参数/变量/type-only import
   - 最终 `tsc --noEmit` 0 TS6133 错; `vitest run` 322 passed 无回归

### 批次 ②：jobs 包清理 (1 commit)

4. **`refactor(jobs-deprecation): quality_logs_cleanup_job 从 jobs/__init__.py 导出移除`** (`1282c7ad`)
   - plan 原列 4 个下线 job, 经 grep 反向引用复查: 仅 `quality_logs_cleanup_job` 真正下线 (其他 3 个 `url_content_check_job` / `export_rebuild_job` / `alert_evaluator_job` 仍被活跃调用, 删除将 NameError, **不删**)
   - 删除 maintenance.py L69-87 函数定义 + __init__.py import/__all__ 两处; scheduler.py 注释更新保留历史叙述

### 批次 ③：M1/M2 终验门禁 (4 commits)

5. **`test(m1-perf): quick_perf.py --cold 实测落基线 30.38ms`** (`1de5aae0`)
   - **M1 冷路径 p95 验收达标**: 200 req / Mode cold / 每 10 req 清缓存 / 实测 p95 = 30.38ms < 150ms 目标

6. **`feat(m2-hotsize): quality_check_logs_archive 从 HOT 迁 WARM`** (`pending`)
   - 836,004 行 (150MB) 从 `hotspot.db` (HOT) 迁移到 `hotspot-warm.db` (WARM)
   - `migrate_temp_layers.py` 已支持 WARM 层迁移, 本次一次性执行
   - HOT 体积: 158MB → **7.8MB** ✅ 达标; WARM 248MB → 365MB (含 archive)
   - 后端验证: `get_connection()` + `SELECT COUNT(*) FROM quality_check_logs_archive` 836,004 行 via warm ATTACH
   - 定向测 15 passed (test_quality_logs_archive + test_telemetry_window)

7. **`feat(m2-cold-crypto): cold_db_crypto verify 端到端验证 + 3 用例`** (`4e881e3a`)
   - subprocess + 真 CLI 退出码 (避免 main() return vs sys.exit 差异)
   - 3 用例: missing_enc_exits_1 / encrypt_decrypt_verify_roundtrip / wrong_master_key_exits
   - fixture 落 REPO_ROOT/backend/ (脚本常量解析到此处), 测试结束清理

8. **`ci(m2-backup): weekly-m2-verify job 周日 02:00 UTC 巡检`** (`a5887f61`)
   - `on.schedule` 加 `cron: '0 2 * * 0'`; 新 job 仅 schedule / workflow_dispatch 触发, 不影响常规 push/PR
   - 步骤: check_backup_chain → check_temp_db_sizes → cold_db_crypto verify

### 追加修复 (2 commits)

9. **`fix(jobs-narrative): 3 个假下线叙述修正 (PROGRESS/CHANGELOG 标'保留, 不下线')`** (`pending`)
   - `url_content_check_job` / `export_rebuild_job` / `alert_evaluator_job` 仍被 `collect_all_job` 链活跃调用
   - PROGRESS.md + CHANGELOG.md 明确标注: plan 与代码事实矛盾, 按代码事实仅清 `quality_logs_cleanup_job` 一个真下线点

10. **`security(master-key): llm_secrets 主密钥重置 (备份 legacy key → 重建)`** (`pending`)
    - 用户显式裁决 "备份 legacy key 后重置" (覆盖 Q1 禁重置决策)
    - 备份 `~/.hotspot/legacy-quality-llm-api-key-20260825.txt` → `.bak.20260827`
    - 清空 `encryption_keys` 过期条目 + `settings` 残留 (`secrets.salt` / `secrets.derived_key`)
    - `SecretsService.setup_master_key(new_key)` 重建通道; keyring 无残留条目
    - **结果**: 加密通道已重建; 存量密文为空, 无重加密需求

11. **`feat(dsh-bridge): backend/services/dsh/ + /api/dsh/* + PipelineSettings 状态块`** (`ffe2df60`)
    - `backend/services/dsh/` 子包: `bridge.py` (DSHClient HTTP 客户端) + `task_router.py` (DSHTaskRouter 路由 + DSH/LLM 降级) + `session.py` (DSHSessionManager 会话生命周期) + `__init__.py`
    - `backend/api/dsh_api.py`: `POST /api/dsh/task` (DSH 不可达时降级 LLM 直连) + `GET /api/dsh/session/{id}` + `GET /api/dsh/health`
    - `backend/api/__init__.py`: dsh router 按 `is_extension_enabled("dsh")` 注册
    - `backend/config/feature_gates.toml`: `[extensions]` 下加 `dsh = true`
    - `frontend/src/components/secnews/settings/PipelineSettings.tsx`: 实时显示 dsh 连接状态 (绿=connected, 黄=disconnected+fallback, 红=error) + endpoint 配置值
    - `backend/tests/test_dsh_api.py`: 4 用例 (health disconnected/connected, task fallback llm, session not found)
    - 修复 Python 3.14 兼容: `asyncio.get_event_loop().run_until_complete` → `asyncio.new_event_loop()` (3.12+ 移除前者)
    - 修复测试 mock: `asyncio.coroutine` (已移除) → `AsyncMock`

12. **`feat(phase4-workbench): 5 视图工作台 UI (Briefing/Pipeline/Knowledge/Analyze/Settings)`** (`f03a0414`)
    - `frontend/src/components/workbench/` 新建 8 文件:
      - `WorkbenchLayout.tsx` (5 Tab 壳 + StatusBar + Outlet)
      - `WorkbenchPage.tsx` (lazy 友好出口)
      - `StatusBar.tsx` (dsh 指示灯 + 管线队列 + token 日用量)
      - `BriefingView.tsx` (官方每日简报 + 今日已发布 + 源健康)
      - `PipelineView.tsx` (5 阶段漏斗 + 队列 + 书签存活 + 错误队列 + token 台账)
      - `KnowledgeView.tsx` (wiki items 搜索 + 概念标签 + 复习到期)
      - `AnalyzeView.tsx` (URL 导入 + 深度研判 dsh+LLM 双轨)
      - `SettingsView.tsx` (模型档位 + dsh 连接 + 采集源 + token 预算)
    - `backend/config/__init__.py`: 新增 `feature_workbench_ui = True`
    - `backend/api/settings.py`: `/api/settings/features` 返回 `workbench_ui`
    - `frontend/useFeatureFlags`: `FeatureFlags` 接口 + `DEFAULT_FLAGS` + `fetchFlags` 映射加 `workbench_ui` (默认 true)
    - `routes/lazy-imports.ts`: 6 个 lazy import
    - `routes/index.tsx`: `/workbench` 路由 + 5 子路由, gated by `features.workbenchUi`

### 门禁结果

- pytest 全量: **2896 collected** (≥2879 baseline) / 0 failed (含本批新增 16 用例: 6 + 3 + 3 + 4)
- ruff: `All checks passed!` (backend + scripts 全绿)
- tsc: **0 TS6133 错** (142→0, React 19 + 手评 7 处)
- vitest: **322 passed** (44 test files, 无回归)
- vite build: 成功 (无 TS / 静态错误)
- M1 冷路径 p95: **30.38ms < 150ms** ✅
- M2 终验: HOT **7.8MB < 80MB** ✅ / WARM 365MB / COLD 未启用 (脚本 + verify 已验)
- CI YAML: 语法 OK

### 遗留 / 阻塞 (承接 v0.6.0)

- ✅ **dsh 桥接层**: 已落地 (commit `ffe2df60`, 9 files, 393 insertions)
- ⏳ **SecNEWS Phase 4-6 未开始**: S4-1..S4-4 (AI 研判/DeepRead/CVE 热力图/ATT&CK/合规矩阵) + S6-1..S6-4 (存量迁移)

> **决策**: 用户拍板 [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md) 方案 C (完整移植), PRD 先行 ([`COCKPIT_PRD.md`](COCKPIT_PRD.md))。CRM-like 业务 (客户/商机/业绩) 与 hotspot 资讯聚合正交, 以 `crm` feature gate 扩展域接入。
> **开发过程审计痕迹**: 详见下方 `## v0.6.0-dev (2026-08-25)` 段 (T1 PRD → T5 E2E 五个 commit 全过程)。
> **本批次**: 仅做版本号 bump (0.5.1 → 0.6.0) + 本段正式条目 + PROGRESS 落账; CRM 5 commit 已随 v0.5.1 推送批次入仓 (`b2131446` / `4b8b4c66` / `920587c8` / `405d98ca` / `abfc7761`)。

### 核心交付

- **T1 PRD** (`b2131446`): 四问默认假设 + US-1 录入客户 / US-2 商机推进 / US-3 座舱复盘 + 六态状态机 (需求沟通→方案提交→商务谈判→合同签订→赢单/输单, 终态冻结) + KPI 口径表
- **T2 数据层** (`4b8b4c66`): migration `071_crm_cockpit.sql` 三表 + `crm_customer_repo` / `crm_opportunity_repo` (状态机唯一裁决) + 单测 10 用例
- **T3 API 层** (`920587c8`): `/api/crm/customers` CRUD、`/api/crm/opportunities` (+`/transition` 唯一阶段入口)、`/api/crm/stats|meta`; `X-CRM-Token` 常量时间鉴权 (未设 env = 本地模式); extensions 注册 crm 扩展域 + `feature_gates.toml` `crm = true`; 测试矩阵补 crm; ARCHITECTURE 数字同步 (routers 57 / services 87)
- **T4 前端** (`405d98ca`): `/crm` 页面 — CockpitDashboard (8 KPI 卡 + 月度营收/区域分布/漏斗手写 SVG)、CustomerManager、OpportunityManager; `useFeatureFlags.crm` 全链路; ROUTE_REGISTRY §2.7 登记; Header「更多」入口
- **T5 E2E+文档** (`abfc7761`): `backend/tests/test_crm_e2e.py` 全栈闭环 (US-1→US-2→US-3 经 register_routers); PROGRESS / CHANGELOG / P2_6_COCKPIT_EVAL §决议记录 同步; Playwright 浏览器级 E2E 列为后续增强

### 门禁结果

- pytest 全量: ≥2879 passed / 0 failed (ruff --fix 后复测)
- `generate_meta --check`: 绿 (jobs 47 / collectors 14 / routers 57 / services 89)
- ruff: 全仓 `All checks passed!`
- 前端: tsc --noEmit 0 错 + vitest 322 passed + vite build 过 (主 chunk 24-28 KB)

### 关联清理 (`d5696fb9`)

- ruff 6 处存量清零 (model_router.py + mastery_projection.py)
- PROGRESS.md Phase 5 S5-1..S5-4 勾选 + 证据 commit 补齐
- services 89 叙述与 generate_meta 实测对齐

### 遗留 / 阻塞

- ⚠️ **llm_secrets 主密钥丢失**: ⑤ v0.6 P0 清场第一批遗留阻塞, 加密通道接管需用户裁决 (Q1 禁重置 vs webdav 存量密文依赖现 key)
- ⏳ **SecNEWS Phase 4-6 未开始**: S4-1..S4-4 (AI 研判/DeepRead/CVE 热力图/ATT&CK/合规矩阵) + S5-1..S5-4 部分 + S6-1..S6-4 (存量迁移)

---

## v0.5.1 (2026-08-25) — v0.6 P0 清场第一批 (⑥③⑤)

> 方案: [`docs/v0.6_ai_workstation_plan.md`](v0.6_ai_workstation_plan.md) §P0 清场与统一。
> 本批次为用户裁决顺序: 先 ⑥ ai_hub 双引擎收敛 → ③ jobs.py 拆分 → ⑤ 凭据单一来源。

### ⑥ ai_hub 双引擎收敛 (`6556cd83`; 归因说明见下)

- `AIService` sensenova 硬编码 (URL/模型名/api_key) 并入 `config/llm.yaml` 单一来源:
  新增 `sensenova` provider 块 (`type: openai_compatible`, base_url
  `https://token.sensenova.cn/v1`); `default_provider: openai → sensenova`
- `AIService` 改为经 `_provider_cfg/_base_url/_eval_model` 从 `llm_service.config`
  解析, env 覆盖 (`AI_PROVIDER`) 保留; ClassVar 兜底表防配置缺失
- **公共契约零漂移**: `_call_sensenova_detect/_resolve_api_key/_resolve_provider/
  _ollama_up/_cache_set` 名称签名不变, URL 前缀与模型串断言全过; 定向 63 测 +
  全量 2879 passed / 0 failed
- `fallback_order` 刻意不含 sensenova — LLMService 评分链保持休眠 (真实计费翻转
  留 P1), 避免 T1 场景意外产生调用成本

> **归因说明**: ⑥ 的主体 diff (ai_hub.py +87 / llm.yaml +21) 因并行会话共享暂存区
> 被卷入其提交 `e94e90f1` (linker wiki_fs 修复) 入库; `6556cd83` 为补交的收尾部分。
> 内容归属以本条目为准。

### ③ scheduler/jobs.py 按域拆分 (`8f4ae80a` + `f554c46c`)

- 单文件 (2331 行) → `backend/scheduler/jobs/` 包: `_runtime`(注入+SSE 插桩) /
  `collect` / `kl` / `codegarden` / `security` / `knowledge` / `digest` /
  `maintenance` 八模块, 段落 AST 逐字节搬运
- **空壳门面** (方案 §9): `__init__.py` 全量 re-export + PEP562 `__getattr__`
  活委托 `_service`; `from ...jobs import X` / `jobs.X` / `patch("...jobs.X")`
  三种契约行为与拆分前一致; 跨域 job 经 `_jobs_pkg.<fn>` 动态解析防快照绑定
- generate_meta `count_jobs` 计数拆分不变 (47, 数的是 scheduler.py 的 add_job);
  定向 54+11 测 + 全量两轮绿; 旧文件删除单独成 commit 防 pathspec 漏删

### ⑤ 凭据单一来源 (`5ab5d996` + 数据面收敛)

- **核验坐实审计**: settings 表残留明文 `quality.llm_api_key` (37 字符 sk- 串);
  llm_secrets 表存在但 0 行; 后端对该 settings 键零读取方 (GateContext.llm_api_key
  字段无赋值点, 纯死字段)
- **llm.yaml provider 链对齐**: 已随 ⑥ 完成 (sensenova 块 + default_provider)
- **明文收敛**: settings 值置空 (保留行作溯源), 原值备份至仓库外
  `~/.hotspot/legacy-quality-llm-api-key-20260825.txt` (0600)
- ⚠️ **加密通道接管受阻**: llm_secrets 主密钥已丢失 (keyring 条目对 encryption_keys
  id=2 verify 失败被 service 清除, settings 回退亦空), 且产品决策 Q1 禁止重置、
  sync_configs.webdav_password_encrypted 存量密文依赖现 key — 加密迁移需用户侧
  裁决 (重建主密钥须按 Q1 走 DB 重置, 或通道继续休眠)。详见 PROGRESS 同日条目
- `api/llm_status.py` EvaluateRequest docstring 对齐 ai_hub 实际解析链
  (env AI_PROVIDER → llm.yaml default_provider, 不再指向已废弃 settings 路径)

### meta 同步 (`d473070e`)

- ARCHITECTURE.md services 88→89 (并行会话 mastery_projection.py 注册补账);
  `generate_meta --check` 绿 (jobs 47 / collectors 14 / routers 57 / services 89)

## v0.6.0-dev (2026-08-25) — CRM 业绩座舱 (开发过程审计痕迹) (security-cockpit 方案 C)

> **状态**: ⏸️ **开发过程审计段** — 本段由 v0.6.0 正式发布前的 5 个 T 任务 commit (T1 PRD → T5 E2E) 留痕构成; 正式发版段见顶部 `## v0.6.0 (2026-08-27)`。保留本段作为开发过程可追溯审计痕迹, 不抹除历史。
> **决策**: 用户拍板 [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md) 方案 C (完整移植), PRD 先行 ([`COCKPIT_PRD.md`](COCKPIT_PRD.md))。CRM-like 业务 (客户/商机/业绩) 与 hotspot 资讯聚合正交, 以 `crm` feature gate 扩展域接入。

### T1-T5 一任务一提交

- **T1 PRD** (`b2131446`): 四问默认假设 + US-1 录入客户 / US-2 商机推进 / US-3 座舱复盘 + 六态状态机 (需求沟通→方案提交→商务谈判→合同签订→赢单/输单, 终态冻结) + KPI 口径表
- **T2 数据层** (`4b8b4c66`): migration `071_crm_cockpit.sql` 三表 + `crm_customer_repo` / `crm_opportunity_repo` (状态机唯一裁决) + 单测 10 用例
- **T3 API 层** (`920587c8`): `/api/crm/customers` CRUD、`/api/crm/opportunities` (+`/transition` 唯一阶段入口)、`/api/crm/stats|meta`; `X-CRM-Token` 常量时间鉴权 (未设 env = 本地模式); extensions 注册 crm 扩展域 + `feature_gates.toml` `crm = true`; 测试矩阵补 crm; ARCHITECTURE 数字同步 (routers 57 / services 87)
- **T4 前端** (`405d98ca`): `/crm` 页面 — CockpitDashboard (8 KPI 卡 + 月度营收/区域分布/漏斗手写 SVG)、CustomerManager、OpportunityManager; `useFeatureFlags.crm` 全链路; ROUTE_REGISTRY §2.7 登记; Header「更多」入口
- **T5 E2E+文档** (本 commit): `backend/tests/test_crm_e2e.py` 全栈闭环 (US-1→US-2→US-3 经 register_routers); PROGRESS / CHANGELOG / P2_6_COCKPIT_EVAL §决议记录 同步; Playwright 浏览器级 E2E 列为后续增强

## v0.5.0-retired (2026-08-24, Phase 7b 待 dsh 端验收后正式生效)

> **状态 (2026-08-25)**: ⏸️ **冻结** — Phase 7 破坏性步骤 (D+2 停 :8000 / D+3 git mv 归档) 按用户裁决 (见 `PROGRESS.md` §2026-08-24 产品三层架构裁决 §连锁裁决) **冻结不执行**; hotspot 仍活跃开发 (`docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6)。7a-7d 工具保留为参考资产。
> **退役文档**: [`HOTSPOT_RETIREMENT.md`](HOTSPOT_RETIREMENT.md) (含冻结横幅)
> **整合 spec**: [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) + [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md)

### Phase 7a — hotspot.db → JSON 旁路导出器 (commit b1cd80de)

- `scripts/export_for_dsh.py` (375 行): 8 张核心表 (hotspots 3391 / favorites 4 /
  todos 6 / sm2_reviews 3 / annotations 2 / hotspot_tags 5356 / knowledge_concepts 98 /
  knowledge_graph 42 = 8902 行) + 4149 wiki items + 96 concepts = 4245 wiki 文件
  旁路导出为 JSON, 供 dsh-SecNews `packages/store/src/migrate-from-hotspot.ts` 消费
- 输出契约: `manifest.json` (schema_version + counts + contract) + 每张表 `*.json`
  (CREATE TABLE DDL + columns + rows)
- 字段归一化: datetime → ISO8601 / BLOB → `{__b64__: base64}` /
  JSON-encoded 字符串 → 原生 list/object / None → null
- 37 张 SKIP_TABLES 含 rationale (schema_version / encryption_keys / cg_* /
  llm_* / FTS5 虚表等)
- `backend/tests/test_export_for_dsh.py`: 8 用例全绿 (manifest / table shape /
  json-encoded / row count / skip rationale)

### Phase 7b — 退役清单文档 (commit 8ec7db61)

- `docs/HOTSPOT_RETIREMENT.md` (202 行): 退役时间线 (D+0 至 D+4) + 行数对账命令 +
  6 步退役步骤 + 代码迁移清单 + 30 天应急回滚 SLA + 9 项验收 checklist
- `AGENTS.md` 顶部加 RETIRED banner, 锁定 2026-08-24 行数基线, Development Commands
  加退役警告
- `PROGRESS.md` 新增 §2026-08-24 Phase 7 数据迁移 + 旧系统退役 (c5)
- `.gitignore`: 新增 `data/export/` (运行时产物不入版本库)

### 待执行 (D+2/D+3, gated on dsh 端 secnews.db 行数对账)

- hotspot 端 :8000 进程停止 (`kill -TERM $(lsof -ti:8000)`)
- `git mv backend hotspot-archived` (保留 history)
- `git mv frontend hotspot-archived/frontend`
- `git tag -a v0.5.0-retired -m "Python 后端退役标记, 数据已迁入 dsh-SecNews"`

### Phase 7c — 行数 baseline + 一键退役流水线 (commit 94d02c49)

- `scripts/snapshot_for_retirement.py` (305 行): 锁定 2026-08-24 行数基线,
  供 dsh 端 secnews.db 迁移完成后对账; `snapshot()` 写 `data/retirement_baseline.json`,
  `verify()` 反向校验; 退出码 0/1/2 (一致/漂移/baseline 缺失)
- `scripts/execute_retirement.sh` (309 行, 可执行): 6 步退役流水线 (Preflight →
  停 :8000 → export → baseline → git mv backend → git mv frontend → git tag),
  默认 dry-run, `--apply` 真执行, `--step N` 单步重跑, `--skip-kill/export/baseline`
  三个开关
- `data/retirement_baseline.json` (42 行): 锁定 8 表 8902 行 + 4 wiki 子目录
  4245 文件 (4149 items + 96 concepts), 2026-08-24 baseline
- `backend/tests/test_snapshot_for_retirement.py` (204 行, 13 用例全绿):
  importlib 加载 scripts/ 脚本, 反向锁定 baseline 数字, 验证 --verify 两个退出码分支
- `docs/HOTSPOT_RETIREMENT.md` 加 §一键退役脚本 + §步骤 2.5 锁 baseline 章节

### Phase 7d — schema 导出给 dsh (commit 40632c98)

- `scripts/dump_schema.py` (443 行): 响应 spec 第 207 行「迁移策略: 从 hotspot
  导出当前 schema → 生成 TypeScript DDL → 逐步迁移」, 输出 4 文件供 dsh
  `packages/store/src/schema.ts` 直接消费, dsh 不需反代 hotspot
  - `data/schema/ddl.sql`: 全部 CREATE TABLE/INDEX/VIEW/TRIGGER 按依赖顺序
    (跳过 FTS5 shadow + sqlite_* 内部表), 可被 node:sqlite `exec()` 重建
  - `data/schema/tables.json`: 每张业务表 dict (columns/pk/indexes/fks)
  - `data/schema/fks.json`: 全表外键扁平图 (from_table/from/to_table/to)
  - `data/schema/fts_groups.json`: FTS5 虚表组 (hotspots_fts/unified_fts/wiki_items_fts)
- 关键 bug 修复 (写在脚本 docstring):
  - FTS5 shadow 必须按**后缀**匹配 (_config/_data/_docsize/_idx/_content),
    prefix 匹配会把 hotspots_ad/ai/au trigger 误算入
  - `render_ddl` 必须跳过 FTS5 shadow (VIRTUAL TABLE 隐式创建) + sqlite_* 内部表
    (sqlite_sequence 不可手动 CREATE)
- `backend/tests/test_dump_schema.py` (234 行, 14 用例全绿):
  schema_version=1 + totals + FTS5 后缀严格匹配 + 双源校验 + sqlite3.executescript
  重建 62 业务表 + CLI 子命令 (--sql-only / 完整模式)
- `docs/HOTSPOT_RETIREMENT.md` 加 §Phase 7d 链接

### Phase 7e — migrations 演进日志导出 (commit pending)

- `scripts/export_migrations_for_dsh.py` (337 行): 响应 spec 第 198 行
  「65 个 migrations/*.sql → store/src/migrations/ 直接复制+改写」,
  把 hotspot 67 个 .sql 文件**字节级**导出供 dsh `packages/store/src/migrations/`
  直接 commit, 保留演进路径可追溯
  - `data/migrations/*.sql`: 67 个文件 (001_init → 070_kl_pipeline) 按字典序复制
  - `data/migrations/manifest.json`: 每文件 sha256/size/line_count + 关键词分布
  - `data/migrations/README.md`: dsh 端消费指引 (cp -r + diff ddl.sql)
- 关键词统计 (2026-08-24 实测): CREATE INDEX 168 + CREATE TABLE 95 + ALTER TABLE 50 +
  INSERT INTO 34 + CREATE TRIGGER 18 + DROP TABLE 16 + UPDATE 16 + PRAGMA 4 + VIEW 2 + DELETE 1
- `backend/tests/test_export_migrations_for_dsh.py` (196 行, 11 用例全绿):
  entries 数量/排序/keys/sha256 校验 + keywords 分布 + manifest shape + README 含
  dsh 端消费指引 + CLI 子命令 (--dry-run/--sql-only) + 字节级一致复制验证

### Phase 7f — Python→TS 移植对照表 (commit pending)

- `docs/PORT_SPEC.md` (312 行): 给 dsh 仓库开发者一份**精确到文件 + 行数 +
  关键函数**的移植清单, 10 节覆盖:
  - §1 总量基线: 481 py + 257 tsx / ~48.9K 行
  - §2 Phase 1 存储层 (6 个文件映射)
  - §3 Phase 2 采集系统 (14 collector + 行数表)
  - §4 Phase 3 质量门禁 (13 gate + SimHash 算法移植 §4.1)
  - §5 Phase 4 调度系统 (45 job 域分类)
  - §6 Phase 5 AI/知识层 (5 关键算法: ai_hub/wiki_archiver/retention/concept_linker/enrich_v2)
  - §7 Phase 6 前端迁移 (5 workbench 视图)
  - §8 全局验收命令 (6 个 phase 的 test/build/diff)
  - §9 hotspot 已交付的 dsh 消费资产 (6 行表格)
  - §10 风险与缓解 (5 个移植风险点)
- SimHash 算法移植是 P3 关键风险点, 文档给出 Python 源码 + TS 移植要点 (分词/哈希/向量)
- Ebbinghaus 衰减公式 `current = initial * 0.9 ^ (days / 7)` 完整列出, dsh 端可直接翻译

### 工具交叉引用

| 工具 | 行数 | 用途 | commit |
|------|------|------|--------|
| `scripts/export_for_dsh.py` | 375 | 8 表 → JSON 旁路 | b1cd80de |
| `scripts/snapshot_for_retirement.py` | 305 | 行数基线 + verify | 94d02c49 |
| `scripts/dump_schema.py` | 443 | 80 表 DDL → 4 文件 | 40632c98 |
| `scripts/execute_retirement.sh` | 309 | 6 步退役 dry-run/apply | 94d02c49 |
| `data/retirement_baseline.json` | 42 | 2026-08-24 baseline | 94d02c49 |
| `data/schema/` (4 文件) | - | dsh schema.ts 消费 | 40632c98 |

### P0 代码治理审计 (2026-08-24, P0 commit 待 push)

- **`docs/P0_AUDIT.md`** (NEW, 188 行, 7 节): 死代码 + 路由对账 + characterization test 三件套
- **`backend/tests/test_characterization_golden.py`** (NEW, 592 行, 51 tests):
  - SimHash: 8 段真实文本的 64-bit SHA-256 fingerprint 锁定 + hamming 距离 golden
  - Retention: run_decay / record_access / check_retention_health 在 frozen 时间下的行为锁
  - Concept linker: link_tags_to_concepts / validate_graph_schema 对 6-edge graph schema 的判据
- **死代码清理** (`ruff check --select F401,F811 --fix`): 自动修 ~32 unused imports + 3 redefs
- **路由对账**: 后端 213 / 前端 119 / 后端独有 94 (分类到 7 个独立 frontend) / 前端独有 7 mismatch
- P1+ 待办: F841 批 1 (~30 个低风险) / 7 mismatch 修复 / 跨 frontend 路由注册表

### P1 治理落地 (2026-08-24, 4 commits: 6f235816 + 7ca15779 + a7965dc8 + de4decf4)

- **P1-1 frontend 路由 mismatch 修复** (commit `6f235816`, 3 files, +6/-6):
  - `KnowledgeActionBar.tsx + test`: `/api/llm/digest` → `/api/digests/generate`
  - `JudgeLayerPage.tsx`: `/api/soul` → `/api/knowledge/soul`
  - 留档: 3 个 mcp 路由 (feature gate 设计) + 2 个 test mock URL
- **P1-2 F841 批 1 删除低风险 dead vars** (commit `7ca15779`, 8 files, +9/-34):
  - 11 个 production dead vars: soul_service (4) + collection_service (1) +
    catchup_checkpoint_repo (1+整块清理) + todo_repo (1) + backup_service (1) +
    codegarden_scanner (1) + maintenance_service (1) + triggers/t3 (1)
  - ruff F841: **55 → 44** (-11)
  - catchup_checkpoint_repo.py 整块删 sql/finished_clause/params/if-finished_clause 12 行
- **P1-3 跨子模块路由注册表** (commit `a7965dc8`, 2 files, +171):
  - `frontend/src/routes/ROUTE_REGISTRY.md` (NEW, 166 行, 6 节):
    - §一 7 子模块边界 (main hotspot 44% / knowledge-master 27% / codegarden 13% /
      kl+ai_hub 10% / security_cockpit 4% / secnews 1%)
    - §二 前端 49 路由按子模块分组 (含 feature flag 标注)
    - §三 P1-1 修复的 7 mismatch 留档
    - §四 新增路由 CI 规则 (5 条)
    - §五 orphan 检测脚本 (manual)
    - §六 未决事项
  - `routes/index.tsx` 顶部加注释指向注册表
- **P1-4 mutation test 验证 golden catch bug** (commit `de4decf4`, scripts/, +255):
  - `scripts/p1_4_mutation_test.py` (NEW, 11 类变异, .bak 精确 revert)
  - **Mutation Score: 10/11 = 90.9% (PASS ≥ 80%)**
  - 1 个真实盲点: decay_score 去掉 round (golden 未测 days 小数精度漂移)
- **PROGRESS.md** 加 P1 治理落地条目 (4 commits 总览 + 状态)
- **P0_AUDIT.md §七** 5 项未做事项标完成 (P1-1/2/3 已闭环), §八加 P1 落地摘要

### P2 治理落地 (2026-08-25, 7 commits: 5fe965a7 + eae608e1 + cf0a0a14 + dbbb3d3c + 4d76b2c2 + d2200a5c)

> 闭环 P0 audit §六 P1+ 剩余 + P1 落地的 48 F841 / 1 mutation 盲点 / 后端 `__all__` 全量补齐 /
> security cockpit SPA 评估。原则: 锁行为不锁实现, 留档可追溯, 区分 mock patch 设计意图 vs 真 dead variable。
> 完整报告: [`docs/P2_5_ALL_AUDIT.md`](P2_5_ALL_AUDIT.md) + [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md)

- **P2-1 F841 批 2 production rename** (commit `5fe965a7`, 12 files, +50/-23):
  - 删除 17 个中等风险 production dead vars (P0 audit §2.2 标 "改 `_` 前缀 + del")
    涉及: soul_service (4+3) + collection_service (2) + digests_archive (1) +
    digest_repo (1) + hook_logger (1) + kl_import (1) + backup_database (1) +
    favorites_service (1) + gap_detector (1) + quality_logger (1)
  - 改名模式: `var = expr()` → `_var = expr(); del _var; # noqa: F841` 留调用痕迹
  - ruff F841 production: **44 → 27** (-17)
- **P2-2 pk_map dead variable PR 评审留档** (commit `eae608e1`, 1 doc, NEW):
  - [`docs/P2_DEAD_VARS_PR_REVIEW.md`](P2_DEAD_VARS_PR_REVIEW.md) (NEW, 6.3KB)
  - 1 个 high-risk dead var: `backend/services/codegarden_scanner.py` pk_map
    (8 个 hot-path 调用方, 删前需 PR 评审确认切接口)
  - 决议: 留档不删, 等下一次 PR 评审由 reviewer 拍板
- **P2-3 mutation 盲点补 test** (commit `cf0a0a14`, 2 files, +96/-10):
  - 新增 `TestDecayScorePrecisionFrozen` (6 tests) 在 `test_characterization_golden.py`
    (golden 总数 51 → 57)
  - 关键 golden: `decay_score(1.0, 1.5) == 0.9777` (raw=0.9776757055472389, 去 round 则失败)
  - 修 `scripts/p1_4_mutation_test.py`: TEST_SELECTOR 加新 class + 修 output regex
    (旧 regex 误取中间行, 新逻辑只取 summary 行)
  - mutation score: 10/11 → **11/11 (100%)**
- **P2-4 F841 tests/ 30 cleanup** (commit `dbbb3d3c`, 20 files, +21/-41):
  - **区分 mock patch 设计意图**: 25 真 dead 直接删 + 2 mock patch 改 `_mock_log`
    (ruff 视为 used, 保留 mock 引用) + 1 未消费 mock_exec drop `as` 子句
  - 涉及关键文件: `test_catchup_phase9.py` (mock_log L163/274/411, L284 events 真消费保留) +
    `test_catchup_service.py` L463 (drop `as mock_exec`)
  - 修 2 个 typo (`__mock_log` 双下划线) + 2 个漏改 (L304 report, L305 latest)
  - 验证: 237 tests passed, ruff tests/ F841 → 0
- **P2-5 后端模块入口 `__all__` 全量 audit** (commit `4d76b2c2`, 23 files, +113/-20):
  - [`docs/P2_5_ALL_AUDIT.md`](P2_5_ALL_AUDIT.md) (NEW, 71 行, audit 表 23 init.py)
  - 10 个补齐 `__all__: list[str] = []` 零契约 (parsers/bid/core/tools/services/
    repository/repository/migrations/security/domain/scheduler/tests)
  - 10 个已有 re-export + 3 个本就有空契约
  - 三档语义: 显式 re-export / 零契约 / 缺失 (缺失即模糊地带)
  - 顺手 ruff `--fix F401` 自动清 19 个测试 unused imports
    (test_cli_contract/collect_validator/dump_schema/knowledge_oneway/
     migrate_temp_layers/quality_hook_filter/quality_logs_archive/
     scheduler_concurrency/snapshot_for_retirement/sync_config_service/
     sync_service_split/wiki_archiver_retention)
- **P2-6 security cockpit SPA 完整评估** (commit `d2200a5c`, 1 file, +211):
  - [`docs/P2_6_COCKPIT_EVAL.md`](P2_6_COCKPIT_EVAL.md) (NEW, 211 行, 6 节)
  - 现状: `security-cockpit/` 3 静态 HTML + 1 CSS = **2363 行**
    (cockpit 683 + customer-form 928 + opportunity-form 663)
  - **业务正交**: CRM-like (客户/业绩/商机) vs hotspot 资讯聚合, 零集成点
  - 三档方案: **A 冻结留档 (0h, 推荐) / B MVP 简版 (12h) / C 完整移植 (90h)**
  - 决策权归用户/产品方
- **PROGRESS.md** 加 `## 2026-08-25 P2 治理落地` 章节 (每 P2 子任务独立小节)
- **P0_AUDIT.md** 加 §九 P2 落地摘要 (7 子任务 commits + 累计收益表)

### P2 累计收益

| 指标 | P0 audit §六基线 | P1 落地后 | **P2 落地后** |
|------|------------------|-----------|---------------|
| ruff F841 production | 15 (medium-risk) | 11 (剩 P2-2 high-risk) | **0** (P2-2 留档评审) |
| ruff F841 tests | 33 | 33 | **0** (P2-4 cleanup) |
| ruff F401 backend | ~32 | ~32 | **0** (P2-5 顺手) |
| mutation coverage | 0% | 10/11 (90.9%) | **11/11 (100%)** (P2-3) |
| `__all__` 契约 | 13 已有 + 10 缺失 | 同左 | **23/23 三档语义清晰** (P2-5) |
| security-cockpit 决策 | 未评估 | 未评估 | **A 冻结留档待用户拍板** (P2-6) |

## v0.5.0 (2026-08-23)

### 数据底座 — llm-wiki-2.0 (M3.5)

- `llm-wiki-2.0/` 5 子目录 + `retention.json` + `graph.json`：md 为知识真源，
  SQLite 退化为运营层/索引缓存（SPEC §18 存储哲学反转）
- `wiki_archiver.py`：30 天前非收藏条目自动归档 md（frontmatter 完整 + atomic 写）
- `retention_engine.py`：Ebbinghaus 衰减 `current = initial * 0.9^(days/7)`，
  access 重置、<0.3 标 stale、周 job 扫描
- **Task13 graph.json 6 边运行时填入**：concept_linker 按条目概念共现累积
  `uses` 边（weight + source_observation_count），保留人工/LLM 标注的
  depends/contradicts/caused/fixed/supersedes 边；`scripts/check_graph_schema.py`
  与 `scripts/check_retention_decay.py` 进 CI
- **Task14 一次性迁移**：`scripts/migrate_v04_to_llm_wiki.py` 迁移 4149 items +
  96 concepts（实际磁盘数，spec 预估 4152/98），补 `confidence: 0.5` +
  `retention` frontmatter，种子 retention.json + graph.json；v0.4 `knowledge/`
  双轨保留

### LLM 单出口 — ai_hub (M5)

- **Task19 合并双出口**：`llm_service.py` + `ai_service.py` 单 PR 合并为
  `backend/services/ai_hub.py`（LLMService 回退链 + AIService 凭据/限频/缓存/
  评价 + `evaluate_article` + `write_score` + 知识写回门面）；旧两文件删除，
  `grep 'from llm_service|from ai_service'` = 0
- `ai_scores` 写路径唯一入口 `ai_hub.write_score()`（T1 审计 + MCP score_item
  全部经此）；`docs/llm_config.md` 更新单出口说明
- 存量修复：`knowledge.py` 移除 `mastered→mastery` 死代码转换（原会把 mastery 清零）

### 工程

- 版本 0.5.0：`backend/version.py` + `frontend/package.json` 同步
- CI 新增 graph schema / retention 健康两项检查
- 测试基线：后端 2662 collected（≥2573，skipped 不增）

## v0.4.3 (2026-08-18)

### 重构 — Core/Extension 软分层

- 新增 `backend/config/feature_gates.toml`: 扩展层单一开关源 (codegarden/mcp/sync/tech_stack/security_graph)
- 新增 `backend/core/routers.py`: 43 个 core router 白名单, 永远注册, 防漂移断言 (与扩展域无重叠)
- 新增 `backend/extensions/__init__.py`: 扩展注册表 + 门控读取 (env `HOTSPOT_FEATURE_GATES` 可覆盖, 读取失败保守回退全开)
- `backend/api/__init__.py`: 扩展 router 按 flag 注册, codegarden/mcp 关闭时 `/api/codegarden` `/api/mcp` → 404
- `backend/scheduler/scheduler.py`: `_is_job_enabled()` 门控, 7 个 job 按扩展归属过滤 (sync/cg_*/mitre/cve)
- 前端: `useFeatureFlags` + `extensions.ts`, App.tsx 路由按 flag 条件渲染, 导航/设置卡片同步隐藏
- 新增 `GET /api/settings/features` 端点 (前端 flag 数据源)

### 新增 4 个复利驱动器

- 即时分类: `collect_all_job` 尾部 `_classify_new_items()` — 采集完 5 分钟窗口内新 items 立即分类 (md 真相源先回写)
- SM-2 每日推送: 08:00 cron `sm2_daily_push_job` → SSE `review_due` 事件, 前端 Header 徽标
- 地图每日重建: 02:00 cron `map_rebuild_daily_job` → 全量重建 `_MAP.md` + graph.json
- 注意力→复习自动转化: dwell>30s 的深度阅读事件自动创建 SM-2 条目 (create_review 幂等)

### 工程质量

- 版本统一: backend/frontend/README 三处 0.4.3 (基线 tag v0.4.3-base)
- 新增 `scripts/generate_meta.py`: AST 反推架构数字 (43 jobs/14 collectors/51 routers/81 services), `--check` 纳入 CI
- 新增 `backend/tests/test_feature_gates.py`: 60 用例组合矩阵 (core-only/all-on/mixed)
- 新增 `backend/tests/test_compound_drivers.py`: 7 用例覆盖 4 个复利驱动器 + 异常隔离
- 修复: `_classify_new_items` 改用 `upsert_item` 模式 (原 `update_item` 不存在, 分类静默失败)
- CI 新增 `backend-core-only` job (env 全关启动 + gate 测试)
- CI 修复 (v0.4.3 发布前置, 历史 CI 长期为红): requirements.lock mcp 2.0→1.28.1 (fastapi-mcp 0.4.0 兼容), fastapi-mcp pin <0.5, frontend @types/node 显式声明 + npm install, 4 处测试消除对本地 .env/真实 hotspot.db/上级 node_modules 的隐式依赖; 2026-08-19 三个 job 首次全绿
- 测试环境默认全开 feature gates (conftest autouse), 3 处 migration 标注扩展表归属

## v0.3.0 (2026-08-01)

### 新增功能 (Phase 8-14)

#### Phase 8: 复利基础设施
- 数据模型: 4 张新表 (content_fingerprints, ai_scores, item_entities, knowledge_links)
- 资讯收藏聚合视图: 5 数据源合并+去重+分页
- AI 评分 MCP tool: score_item

#### Phase 10: T1/T2 触发器
- 5 阶段 KL 状态机引擎 (raw→refine→link→structure→publish)
- T1 触发器: raw→refine (60s)
- T2 触发器: refine→link (120s)
- 死信队列 + 重试策略

#### Phase 11: 抓取层现代化
- BackendSession 统一代理注入
- 6 新 collector: HN, Reddit, OpenBB, Telegram, GDELT, OSS Insight
- 可读 ID 格式 {source}:{subtype}:{native_id}

#### Phase 12: T3/T4/T5 触发器 + 告警系统
- T3 触发器: link→structure (600s)
- T4 触发器: structure→publish (1800s)
- T5 回滚: publish→refine
- 3 类告警规则: tech_stack 影响, 关键 CVE (CVSS≥9.0), 标讯命中

#### Phase 13: 复利可视化 + 4 模式 + 规划引导
- KnowledgeCompoundingDashboard 仪表盘
- 4 认知模式 UI: 简报/扫描/深度/告警
- KnowledgePlanningPanel 规划引导

#### Phase 14: 子系统联动
- Tech Stack Drift 评估
- CVE 双向同步 (Knowledge ↔ Security)
- 跨域 entity 命名空间统一

#### Phase 15: AI 混合推理
- LLMService 统一接口 (OpenAI/Anthropic/本地)
- Crawl4AI 解析器集成
- Hybrid AI 降级策略 (AI → 规则 → 空)

#### Phase 16: Hybrid AI 完整
- T1 评分延迟降低 ≥60% (AI 缓存命中率 ≥30%)
- T3 摘要生成延迟降低 ≥40%
- 代理健康检查 + 自动切换

#### Phase 17: Chunks + Attention
- knowledge_chunks 表 (paragraph 级) + FTS5 全文搜索
- 5 维度注意力评分 (view/dwell/scroll/favorite/annotation)
- 30×24 注意力热力图
- 6 认知模式完整 (简报/扫描/深度/告警/整理/复习)

### 破坏性变更
- kv_cache 表删除 → digest 已读状态迁移到 digests.last_read_at
- MCP 工具从 13 减少到 9 (移除 4 个低频工具)
- 底层 REST API 端点保留不变

### 详细变更

各 Phase 详细变更日志见对应 spec 目录:
- Phase 7 (MCP): `.trae/specs/phase7-mcp-server/`
- Phase 8 (复利基础设施): `.trae/specs/phase8-compounding/`
- Phase 9 (抓取标准化): `.trae/specs/phase9-crawl-standardize/`
- Phase 10 (T1/T2 触发器): `.trae/specs/phase10-t1t2-triggers/`
- Phase 11-17 (v1.7): `.trae/specs/phase17-chunks-attention/` 及对应 spec 目录
## v0.4.0 (2026-08-16) — 审计重构 Phase 0-6 全部落地

> 依据 docs/audit_first_principles_plan.md 的第一性原理审计与批判性审计,
> 修复全部发现的断裂/死代码/安全缺口, 版本 0.3.0 → 0.4.0。

### 知识闭环数据流 (P1)
- KL 状态落真相源: md 写入 lifecycle, full_sync 不再抹除 kl:* 状态; 回填 4,117 个既有 md
- T4 触发器修复 content 列崩溃 + 评分 fallback → kl:publish 死锁解除
- 生命周期统一为 KL 五阶段 (sag/extract/compiler 改写 kl:* 值)
- knowledge_watcher 改单文件增量同步 (不再全目录重扫)
- 新增 knowledge_classify_job (每 30min 500 条规则分类)

### 采集管道 (P2)
- run_one_source 真单源化 (collect 支持 only_source 过滤)
- run_one/run_one_source 与 run_once 统一并发锁
- 去重窗口改滚动 7 天; 指纹入库后补写 (FK 失效修复)
- catchup since 窗口透传生效; unreachable 加入复检候选
- 门禁语义对齐 (hard 仅 strict 拒绝; 崩溃 fail-closed)
- 接线 6 个未注册 collector (HN/Reddit/Telegram/OSSInsight/GDELT/OpenBB)
- 稳定 ID (可读前缀+URL 哈希); upsert 不再刷新 ingested_at; 富化摘要复检

### 内化/输出闭环 (P3)
- 注意力事件自动创建 SM-2 复习记录; DeepReadMode 埋点 view/dwell/scroll
- ItemDetailDialog 标注 UI; 内容草稿生成 job (kl:publish/高注意力 → drafts)
- 复利仪表盘改读真实数据 + 挂载到 /knowledge/compound

### 同步与安全 (P4)
- bundle 构建失败即中止 (表缺失=空, 真失败=raise 防误删)
- secrets merge 排除密文字段; 冲突裁决生效; sm2 due_at 晚者胜
- rotate_master_key 主密钥轮换; Playbook 危险命令黑名单
- 备份纳入 knowledge/ 源文件 + restore 流程; MCP 路径穿越校验

### 导航与操作流 (P5)
- 死组件清理 (Sidebar/TopBar); Header "更多"菜单 (知识/Skill/密钥/同步)
- ErrorBoundary 挂载; 主题状态统一; 收藏→知识库单步导入
- 数据源健康汇总; ReviewMode 空态引导

### 兼容性
- 后端 2288+ → 2,400+ 测试全绿; 前端 292 测试全绿
- 数据库迁移无需新增 (全部修复为代码层)

### v0.4.0 收尾 (2026-08-16 补)

#### Chunk + FTS5 全文检索落地 (此前 0 行)
- `chunk_service` 段落切分生成器 (char_start/end 原文定位, 超长段落句切)
- `knowledge_chunk_generation_job` 每 30min 处理 200 条
- 迁移 061: FTS5 trigram 表 → 中文子串检索 (unicode61 不切 CJK)
- 搜索端点路由: CJK≥3字→trigram / ASCII→unicode61 / 短查询→LIKE
- 存量回填: 258 个有正文条目全部生成 chunks

#### Security ↔ Knowledge 实体统一命名空间 (PRD A.3.2)
- `security_enrichment_job` 重构为持续回填 (去掉 24h 限制 + 空结果打标)
- 富化实体写入 `item_entities` 桥接表 (此前 0 行, 全库无写入方)
- `security_entity_concept_sync_job`: item 实体→security_entities + 高频
  实体→knowledge concept 互引 (external_id/external_ref)
- 实测: 34 桥接关联 / 28 CVE 入 security 库 / 2 高频概念互引

---

## v0.6.2 (2026-08-28) — v0.6 Phase 6 (存量迁移 + wiki FTS5 同步层 + dsh-SecNews 归档)

> **范围**: Phase 6 三批落地, wiki-first 存储哲学闭环:
> 1. 一次性迁移脚本 (scripts/migrate_wiki.py) — 幂等 + SHA256 报告
> 2. wiki_items_fts 完整同步层 (migration 073 + 链式 job + search_wiki_only FTS5 MATCH 旁路)
> 3. dsh-SecNews secnews/data 离线归档 (21.6MB → 2.3MB tar.zst + MANIFEST + verify 脚本)
>
> **批次 commit**: 3 个 (`309a83da` / `e53790cc` / 本批 `chore(phase6-archive)`)。

### 批次 ⑪：v0.6 Phase 6 — 存量迁移 CLI + wiki_items_fts 同步层 + dsh-SecNews 归档

1. **`feat(phase6-migrate-cli): scripts/migrate_wiki.py CLI wrapper + 幂等执行 + 测试`** (`309a83da`)
   - 新 `scripts/migrate_wiki.py`: argparse (`--src` / `--dest` / `--dry-run` / `--report` / `--exclude-pattern`); SHA256 清单 + 报告入仓 (`docs/data/migration-report.json`)。
   - 强制 safety-net excludes: `*P2*` / `*Test*` / `*test*` + 保守 title 正则 (仅 P2 Import Test fixture, 不碰 \bsample\b/\bdemo\b)。
   - 真实运行: apply `migrated=0 / skipped=4149 / errors=0` (幂等闭环); dry-run `would_migrate=0 / would_skip=4147 / excluded=2`。
   - 新增 `backend/tests/test_migrate_cli.py` (3 用例: fresh / idempotent / dry-run 0 写盘); ruff 通过。

2. **`feat(phase6-fts-sync): wiki_items_fts 完整同步层 + FTS5 MATCH 旁路`** (`e53790cc`)
   - 新 `backend/repository/migrations/073_v0.6_wiki_items_fts_sync.sql`: DROP & 重建 `wiki_items_fts` (id UNINDEXED + contentless FTS5, 5 列: id/title/topic/tags/type, 与 `hotspots_fts` 平行); 不加 DB trigger (SQLite 禁跨 attached DB trigger) — 同步由 `wiki_items_fts_sync_job` 兜底。
   - 新 `wiki_items_fts_sync_job()` (`backend/scheduler/jobs/maintenance.py`): drift 检测 (COUNT 不等 → 'delete-all' + 全量 rebuild + optimize); 链式触发 (`backend/scheduler/jobs/collect.py` L38, 与 `fts_rebuild_job` 平级)。
   - `backend/services/search_service.py`: `_VALID_SOURCES += 'wiki'`; `unified_search` 新增 `wiki` source → `_search_wiki_fts` FTS5 MATCH 旁路, `LEFT JOIN warm.knowledge_items k ON k.rowid = f.rowid` 回查实体字段 (contentless 列投影为 NULL, 必须 JOIN); 新增 `search_wiki_only(q, limit)` 便捷方法; FTS5 syntax 错误 → 空结果 (不 5xx)。
   - 新增 `backend/tests/test_wiki_items_fts.py` (5 用例: 5 列 / MATCH 命中 / entity_id 非 None / sources=['wiki'] 旁路 / drift 自愈); ruff 通过; pytest 5/5 + 周边搜索/mcp/migrate 45/45 全绿。

3. **`chore(phase6-archive): dsh-SecNews secnews/data 离线归档`** (本批)
   - 新 `archives/dsh-secs-news-2026-08-27.tar.zst` (2.3MB zstd / 21.6MB raw, 4285 文件; sha256 `f785bceb590f131104423b09c721437f8ff0f4367543056da1abbb6db5b53a67`)。
   - 新 `archives/dsh-secs-news.MANIFEST` (per-file SHA256 + 归档元信息)。
   - 新 `archives/ARCHIVE_NOTES.md` (归档原因 / 与 plan 偏差说明 / 还原步骤 / 与 hotspot 关系图 / 后续动作)。
   - 新 `scripts/verify_dsh_archive.sh` (Python 包装, 跨 shell 兼容; archive-SHA + file-level 双层校验, 4285/4285 通过)。
   - `chmod -R a-w /Users/duke/Documents/dsh-SecNews` (源冻结; 不删除, 保留备份 — 用户决策)。
   - **与 plan 偏差**: 范围从 `dsh-SecNews/` 整体 (估 50MB, 实测1.8GB 含 node_modules) 缩到 `secnews/data/` (24MB), 因 node_modules 与 wiki 无关不入仓; 归档本体 2.3MB 小于 plan 估的 50MB, 优势。

### Phase 6 验收数据

| 维度 | 验收 | 实测 |
|------|------|------|
| 迁移脚本幂等 | 二次 apply 0 迁移 | `migrated=0 / skipped=4149` (✓) |
| dry-run 0 写盘 | dest 保持空 | `would_migrate=0 / would_skip=4147 / excluded=2` (✓) |
| FTS5 检索 | 真相关度排序 | `search_wiki_only('渗透', limit=3)` 返回 ≥1 行 (✓) |
| sources=wiki 旁路 | unified_search 分组含 wiki | `len(grouped['wiki']) >= 1` (✓) |
| drift 自愈 | COUNT 不等触发 rebuild | `wiki_items_fts_sync_job` 后两侧 COUNT 对齐 (✓) |
| 归档完整性 | SHA256 全通过 | 4285/4285 文件 + archive SHA (✓) |
| 源冻结 | chmod a-w 验证 | `dr-xr-xr-x` 权限确认 (✓) |

## v0.7.4-cleanup (2026-09-01) — Batch ⑧ 观测深化 + 扩展开闸 + i18n + 历史债

### 新增
- **D1 OAuth 真身**: `services/oauth_provider.py` (CloudBase 真身 + URL 校验) + `secrets_service.unlock_with_oauth()` (双因素语义) + 前端 `routes/oauth-callback.tsx`
- **D2 告警 5 档通道**: `services/alert_channels.py` (Webhook/Email/Slack/Feishu/Dingtalk) + `alert_dispatcher.py` (asyncio.gather 并发) + migration 087 alert_deliveries 表
- **D3 SSE 推送**: backend `publish_event("observability.update/breach")` + frontend EventSource + polling 兜底
- **D4 api_events 采样降级**: `services/observability_sampling.py` (success 10% / error 100% / slow 100%) + `GET/PUT /api/observability/sampling`
- **D5 扩展域开闸**: phase2b / tech_stack / security_graph 三闸门 true, 修复 phase2b 路由错绑 codegarden 脏状态
- **D6 前端 i18n**: 0 依赖 `contexts/I18nContext.tsx` (zh-CN / en-US) + `LocaleToggle` + ObservabilityDashboard a11y (role/aria)
- **D7 历史债清偿**: `scripts/check_docstrings.py` (237 模块全覆盖) + 补 kl_rollback_api 1 处历史债 + CI Mimosa best-effort step

### 改进
- ARCHITECTURE.md / AGENTS.md 数字同步 (services 101→105)
- 路由注册与 job 注册对齐, "job 不跑但端点 200" 脏状态根治
- conftest autouse 测试环境强制 sampling=100% 锁住 "必落表" 语义

### 门禁
- pytest 3234 passed / 6 skipped / 0 failed
- vitest 345 passed
- generate_meta --check OK
- check_docstrings.py 0 缺

## v0.7.5 (2026-09-01) — Batch ⑨ i18n 全量 + secrets 主动运维 + ACL + MITRE 离线包

### 新增
- **B9-1 i18n 全量**: I18nContext 12 namespace / 120+ key + {n} 占位符; 10 高频组件接入 (Shell/Header/StatusBar/Feed×3/Knowledge×2/Pipeline/Settings×3)
- **B9-2 轮换主动通知**: secrets_rotation_check_job (每日 09:00) 超期 90d → 告警通道全发 + audit + 24h cooldown; 前端 RotationBanner
- **B9-3 per-secret ACL**: migration 088 llm_secrets.owner_role + role 优先级过滤 (admin>user, fail-closed) + GET /api/secrets?actor_role=
- **B9-4 MITRE 离线包**: 本地 cache + HEAD Last-Modified 304 增量 + 网络失败兜底 + force 重灌 + GET /api/security/mitre/cache; 省 ~30MB/次

### 修复
- EncryptionKeyRow dataclass 缺 last_rotated_at 字段 (migration 085 schema/dataclass 漂移, rotation_status 潜在 AttributeError)
- secrets_rotation_check_job 漏登 jobs/__init__.py → e2e fixture 级联 28 errors
- test_alerts_active_lists_recent 硬编码 fired_at 跨天超窗 → 动态 now-5min

### 门禁
- pytest 3250 passed / 6 skipped / 0 failed
- vitest 346 passed / tsc 0 错 / vite build OK
- generate_meta --check OK (jobs 51 / routers 67 / services 105)
