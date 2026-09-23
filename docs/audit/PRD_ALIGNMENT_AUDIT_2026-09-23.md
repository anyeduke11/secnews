# PRD 对齐审计 — 设置页 IA 重构落账 (2026-09-22 计划 P1-P3 收口)

- **日期**: 2026-09-23
- **审计范围**: `/settings` 页面 IA 重构（17 cat → 7 cat）全链落账 — 前端重组 + 后端端点 + settings 表 namespace 治理 + sync bundle 白名单化
- **依据**: `docs/superpowers/plans/2026-09-22-settings-refactor.md` (Task 1-17) + `docs/superpowers/specs/2026-09-22-settings-refactor-design.md` (§5/§8)
- **审计方法**: 只读落账 + 实测核对（grep 源码 / 路由 prefix / 测试结果），分支 `settings-refactor`（基线 `177b19e` → 收口 `bdd5569`）
- **留痕纪律**: 依根 AGENTS.md「单一权威 PRD 维护纪律」— 本文为审计事实源，PRD/V0.8.5_PLAN §6/DEV_LOG 同批联动

---

## 1. 前端 IA 重组 (P1, Task 1-9)

| # | 事实 | 证据 |
|---|---|---|
| 1.1 | `SectionKey` 17 cat → **7 cat / 5 组**: overview / general / models / collection / network / connectivity / ops | `frontend/src/components/settings/sections.tsx` 头注释 + Task 1 commit `fc2dd73` |
| 1.2 | 旧 cat 映射: dashboard→overview · image_models/pipeline(模型)→models · pipeline(队列)→collection · sync/integration/secrets→connectivity · maintenance/export→ops · about→overview · sentinel→general | 同上 |
| 1.3 | **删除 12 文件 / 8 定位不符组件**: FeedbackSettings / KnowledgeSettings / AlertSettings / AboutSettings / ExportSettings / secnews PipelineSettings / AgentRunnerCard / SentinelSettingsPage(+test+css) / ImageStudio(+test)；残留 grep 清零 | commit `2644f10` |
| 1.4 | redirect 3 条: `/sentinel/settings`→`/settings?cat=general` · `/secnews/image`→`/settings?cat=models` · `/secnews/settings`→`/settings?cat=collection`；ROUTE_REGISTRY.md 同步 | commit `2644f10` + `75891d7` |
| 1.5 | 模型配置唯一入口 ModelsSettings（image_models/pipeline 内模型入口消亡）+ FeatureGatesCard(只读期) + ExportActionsCard + SettingsDashboard 总览吸收 About | commits `569ed0b`/`c02c702`/`0ad5643`/`610ebb1` |

## 2. 后端端点变更 (P2, Task 10-13)

| # | 端点 | 文件 | 语义 |
|---|---|---|---|
| 2.1 | GET `/api/settings/mcp/config` | `backend/api/mcp_settings_api.py` | stdio/SSE 配置（依赖 server 本体，`feature_mcp=false` 时 404） |
| 2.2 | PUT `/api/settings/mcp/enabled` | 同上 | **ungated** 切换 server 本体旗标（kv 键 `feature.mcp`），立即生效 + 持久化 — MCP 关闭态可从 UI 重开 |
| 2.3 | GET `/api/settings/feature-gates` | `backend/api/settings_flags_api.py` | 16 gate 全量（name/enabled/source/effective_scope） |
| 2.4 | PUT `/api/settings/feature-gates/{name}` | 同上 | 写 `feature_gates.toml` + audit_log；env 覆盖时 **409** |
| 2.5 | GET `/api/settings/features` | `backend/api/settings.py` | features 16 键单源（Task 11 收敛） |
| 2.6 | settings.py 全端点走 `SettingsService` | Task 12 commits `61805f0`/`69afa8b` | 写入即审计 + target/调用形态契约 |

- `mcp.py` 旧内嵌两个 toggle 端点删除（150 行上限内只减不增）；`_registry.py` 净零行增登记。
- 架构数字: routers **87→89** / services **147→148**（`generate_meta.py --check` 实测通过）。

## 3. settings 表 namespace 契约 (P3, Task 14-16)

| # | 事实 | 证据 |
|---|---|---|
| 3.1 | 写入前缀白名单 fail-loud: `_ALLOWED_PREFIXES = (collection. / llm. / interest. / quality. / feature. / feature-gates. / state. / secrets.oauth_allowlist)`，未注册前缀 raise `InvalidParamException`（拒在 repo.set/audit 之前） | `backend/services/settings_service.py` L17-23，commit `5711291` |
| 3.2 | `webhook.secret` 迁加密存储（SecretsService / llm_secrets 体系）: `WebhookTrigger._get_secret` 改走 `find_internal_by_name`，支持注入 provider；`scripts/fix_webhook_secret_to_vault.py`（`--dry-run` 默认 True）；`_DISALLOWED_EXACT = {webhook.secret}` 明文回写通道永久关闭 | commit `c761a7b`，测试 `test_trigger_webhook_secret.py` |
| 3.3 | **sync bundle settings 白名单化**: `SETTINGS_BLOCKLIST`（4 键黑名单）反转为 `settings_sync_allowed()`（前缀白名单 `collection./llm./interest./quality.`）；与 3.1 写入契约语义对齐但更窄（`state.*`/`feature.*`/`secrets.*` 不跨端）；三处副本收敛为 `sync_service_constants` 单源，`sync_service.py` 死副本删除 | commit `bdd5569`，`backend/services/sync_service_constants.py` L14-24 |
| 3.4 | 兼容性锚定: 旧设备 bundle 携带 `webhook.secret` / `scheduler.last_run` / `state.mitre.synced_at` 等白名单外 key → apply 侧 skip 不落库（不被误覆盖）；bundle settings 缺席 ≠ 删除，本地遗留 key 原样保留（不被误清）；zip 容器 + Fernet 信封格式未动 | `test_sync_bundle_v1_7.py` P3 Task 16 三测（build 白名单 / apply skip / legacy 不误清） |

## 4. 验收口径核对 (设计稿 §8)

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 8.1 | `/settings` 侧栏 7 cat / 5 组，无只读监控/数据浏览/纯动作区块混入 | ✅ | §1.1-1.3（8 组件物理删除 + grep 清零） |
| 8.2 | 能力开关卡可切换任一 TOML gate，运行时读数 5s 内跟随；需重启项明示；MCP 关闭态可 UI 重开且重启不丢 | ✅ | §2.3-2.4（TOML 写 + 5s TTL 热重载既有机制）+ §2.2（kv `feature.mcp` 持久化）；终审修复批 2026-09-23 补齐前端证据：`FeatureGatesCard` toggle 接通 `PUT /api/settings/feature-gates/{name}`（成功更新行状态 + note；409 env 覆盖/404 行内展示；source=env 禁用），`set_toml_gate` 多节 TOML 键错插节同步修复；测试 `FeatureGatesCard.test.tsx`（成功/409/env 禁用）+ `test_feature_gates.py::TestSetTomlGate` + `test_mcp_settings_api.py::test_toggle_writes_audit_log` |
| 8.3 | LLM 模型配置唯一入口在「模型配置」cat | ✅ | §1.5（image_models/pipeline 模型入口消亡） |
| 8.4 | `webhook.secret` 不再存 settings 明文 KV；跨端 bundle 不含非 config key | ✅ | §3.2-3.4（迁移 + 白名单测试锚定） |
| 8.5 | 后端新增测试全绿、全量回归 0 失败、generate_meta --check / ruff / 行数门 / nav4 守卫全过 | ✅ | 见 §5 |

## 5. 测试证据

- 定向回归: `pytest backend/tests/ -k "sync or settings" -q` → **365 passed / 0 failed**（T16 收口实测）
- 全量回归: `pytest backend/tests/ -q` → **4715 passed / 9 skipped / 0 failed**（2026-09-23 收口实测）
- 前端: `tsc --noEmit` 0 错 / `vitest run` **85 文件全绿**（修复 3 处负载敏感 flake 后末轮全量验证）/ `vite build --logLevel error` OK
- 收口 flake 修复（3 处, 均为异步断言时序竞态, 非产品缺陷）: `ModelsSettings.test.tsx`（模型池内容裸断言→waitFor）、`SkillDetail.test.tsx`（二级 runs 请求裸断言→waitFor）、`realtime.test.tsx`（真实定时器 80ms 节流窗负载下被击穿→窗口 800ms/sleep 900ms 裕度）
- 门禁: `generate_meta.py --check` OK（89 routers / 148 services）；`ruff check` 触碰文件 0 告警；api 行数门未破（settings.py 303/mcp.py 缩减）

## 6. 遗留与边界 (设计稿 §7 YAGNI 裁决, 非缺陷)

1. 不拆 settings 表结构（无 DDL；`webhook.secret` 为数据搬移）。
2. `/secrets` `/sync` `/skills` `/maint` 兄弟直达路由未动（仅 `/settings` 页内重组）。
3. alerts 规则创建 UI 整 cat 删除，能力留在 `/knowledge` 告警域。
4. `backend/api/quality.py` 直连 repo 病灶**记遗留未动**。
5. Feature Gates 无路由级热生效（TOML 5s TTL 影响运行时读数；路由/job 注册保持启动快照，UI 明示）。
6. sync 白名单为行为变更：白名单外既有自定义 key（如有）自此不再跨端同步——属裁决意图（仅 config namespace 跨端），升级侧无数据丢失（本地键保留，见 §3.4）。
