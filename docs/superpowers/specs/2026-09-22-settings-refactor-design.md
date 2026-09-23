# 设置页结构化重构 · 设计稿 (Settings IA Refactor)

> **日期**: 2026-09-22 · **状态**: 已批准 (owner 逐项裁决后整体确认)
> **落点**: `/settings` SettingsHub (17 cat → 7 cat) + 设置语义后端修正 + settings 表 namespace 治理
> **方法**: 第一性原理 — 设置页唯一本质 = **用户对系统可持久化偏好的低频写入口**; 只读监控 / 一次性动作 / 数据浏览均不属于设置页

---

## 1. 背景与第一性原理诊断

`/settings` 现状 17 cat / 6 组 / ~4700 行前端 + 60+ 后端端点, 六个结构性病灶:

1. **监控混入**: sentinel (587 行, 零写操作只读控制台) / dashboard (285 行体检) / about (192 行运行状态) 三重叠, 各自调 `/api/health`;
2. **数据浏览混入**: feedback (点赞点踩画像) / knowledge (统计跳转卡) 零配置项;
3. **动作混入**: export (三个导出按钮) / AgentRunnerCard (可运行 agent, POST /api/agents/run);
4. **入口重复**: image_models 与 pipeline 内模型档位同为三场景模型选择 (且文生图宿主已下线);
5. **半截功能**: alerts 只有列表+删除, 规则创建在 `/knowledge` 告警区;
6. **后端病灶**: ① `PUT /api/settings/mcp/enabled` 只改进程内单例不持久化, 响应却称"重启后生效" (实际重启即丢); ② `/api/settings/features` 手写 9 键 vs 16 gate 漏 7 键; ③ 该两端点物理住在 gated `mcp.py` (TOML 默认 false → 404), **gate 关闭时 UI 无法开启 MCP 的自锁**; ④ settings 表为万能 KV, 混装配置/密钥材料 (`webhook.secret`)/运行状态, 且整表进跨端 sync bundle。

## 2. 裁决记录 (owner, 2026-09-22)

| 问题 | 裁决 |
|---|---|
| 范围 | **全量**: 前端 IA + 后端 bug + settings 表治理 |
| 监控三区块 (sentinel/dashboard/about) | **合并降位+删冗余**: dashboard+about 合并为唯一总览; sentinel 能力开关盘点化为可写卡; 危险区/安全姿态删除 (观测在 /secnews/observability) |
| feedback / export / knowledge | export 入运维; **feedback/knowledge 物理删除** |
| 模型配置 | **新建独立「模型配置」cat**, 集中 LLM 配置/模型池/模型选择/图片模型 |
| pipeline 非模型部分 | **按性质拆归**: KL 队列/源健康→采集区; dsh 启停→运维区; AgentRunner 删除 |
| alerts | **删除** (规则管理留 /knowledge 告警域) |
| 执行方案 | **方案一 三期渐进**: P1 前端 IA / P2 后端修正 / P3 表治理不拆表 |
| 微裁决 | 能力开关卡放「通用」; `/sentinel/settings` redirect 指 `?cat=general` |

## 3. P1 — 前端 IA 重组 (17 cat → 7 cat / 5 组)

### 3.1 新 SectionKey 与装配

`frontend/src/components/settings/sections.tsx` 重写:

| 组 | cat | 装配内容 | 来源 |
|---|---|---|---|
| 总览 | `overview` (默认) | 4 子状态体检卡 + 跳转 tiles (QUICK_JUMPS 更新) + 版本/运行状态卡 | dashboard + about 合并 |
| 通用偏好 | `general` | ModeSwitcher + GeneralSettings + PracticeDomainsCard + **FeatureGatesCard (新)** | general + sentinel tab2 可写化 |
| 系统配置 | `models` | **新 ModelsSettings**: ProviderPanel + SecretsPanel (自 QualitySettings 迁出) + 模型池状态卡 (`/api/llm/status`) + ScenarioModelsPanel | 新建 (收 pipeline 模型部分 + image_models + collection 内嵌面板) |
| | `collection` | CollectionScheduleInfo + QualitySettings (瘦身为规则+LLM 检测) + SourceSettings + KL 队列/token 预算卡 + InfoFilterCard | collection + pipeline 拆入 + info_filter |
| | `network` | ProxySettings 原样 | network |
| 连接与凭据 | `connectivity` | SyncSettings + MCPSettingsCard + SecretsStatusCard | sync+integration+secrets 合并 |
| 运维 | `ops` | DatabaseMaintenance + 导出动作卡 + DshControlCard | maintenance + export 拆入 + DshControlCard 拆入 |

- PipelineSettings 的「源健康前 18」与 SourceSettings 重叠 → **删除**。
- `layout: 'mixed'` 版式提示沿用 (general/collection/models)。

### 3.2 物理删除清单

`FeedbackSettings` / `KnowledgeSettings` / `AlertSettings` / `AboutSettings` (并入总览) / `PipelineSettings` (拆解消亡) / `AgentRunnerCard` / `SentinelSettingsPage` (+test + `sentinel-settings.css`) / `ImageStudio` (+test, 死页)。

sentinel 区块内容去向: 能力开关 tab → FeatureGatesCard; 模型与密钥 tab → models 区; 采集调度只读 tab → 总览体检覆盖; DANGER ZONE / 安全姿态 → 删除。

### 3.3 redirect 与路由账

- `/sentinel/settings` → `/settings?cat=general` (能力开关新家)
- `/secnews/settings` → `/settings?cat=collection`
- `/secnews/image` → `/settings?cat=models`
- `routes/ROUTE_REGISTRY.md` 同步; 未知 cat 兜底落 `overview`; NAV4 四菜单纪律无涉 (零新增路由, 全部为既有 redirect 目标变更)。

## 4. P2 — 后端修正 (4 项)

1. **MCP 自锁解除**: 新 ungated `backend/api/mcp_settings_api.py` 承接 `GET /api/settings/mcp/config` + `PUT /api/settings/mcp/enabled`; `mcp.py` 只留 gated `/api/mcp/status|tools`; `_registry.py` 登记 (注意 api 行数豁免门: `_registry.py` 当前 271/271 上限, 需净零行增手法 — 并入既有 import 行)。
2. **toggle 持久化**: `feature_flag_service.enable/disable` 补写 settings kv `feature.mcp_server` + `main.py` 启动回读 setattr `config.feature_mcp` (refresh-interval 回读同款先例); 响应 note 如实化 (server 开关立即+持久; `/api/mcp/*` 调试路由随 TOML gate 重启生效)。
3. **features 单源 + 能力开关端点**: `GET /api/settings/features` 键从 extensions 16-gate 白名单派生; 新 `backend/api/settings_flags_api.py`: `GET /api/settings/feature-gates` (name/enabled/source: default|toml|env/生效域 runtime|startup) + `PUT /api/settings/feature-gates/{name}` (白名单校验 + 写 TOML + audit_log; env 覆盖存在时 409 提示走 env)。
4. **R3 对齐**: 新薄 `backend/services/settings_service.py` 封装 settings repo (get/set/list + audit + P3 prefix 校验); `settings.py` 改走 service。`api/quality.py` 同病灶记遗留不动。

## 5. P3 — settings 表 namespace 治理 (不拆表)

- settings_service 立 `_ALLOWED_PREFIXES` 契约 (`collection.` / `llm.` / `interest.` / `quality.` / `feature.` / `secrets.oauth_allowlist` / `state.` 例外清单), 未注册前缀写入 fail-loud;
- **迁移 `webhook.secret`** → 加密存储 (llm_secrets/encryption_keys 体系), trigger_gate 读点改造, `fix_` 脚本带 `--dry-run` (scripts/AGENTS 纪律);
- mitre 同步状态 / dsh 运行模式等 state 类 key 登记 `state.*` 例外 (不硬迁);
- `sync_bundle` 打包改白名单 (仅 config namespace 进跨端同步)。

## 6. 测试与守卫

- **前端**: 7 cat 各一 colocated 装配测试; FeatureGatesCard 测试 (toggle → PUT / 409 env 提示); nav4_shell 与 redirect 测试更新; tsc + vitest + build 全量。
- **后端**: mcp ungated 断言 (extensions.mcp=false 时 PUT enabled 仍 200); 持久化重启回读断言; features 16 键断言; flags PUT 白名单/audit/persist 断言; settings_service prefix 校验; 全量 pytest。
- **守卫**: generate_meta 同步 (预计 routers 87→89 / services 147→148, ARCHITECTURE.md + 各 AGENTS.md 同步); ruff 触碰文件; api 行数门; `docs/audit/PRD_ALIGNMENT_AUDIT_2026-09-22.md` 留痕; 权威 PRD 同步 + DEV_LOG 联动。

## 7. YAGNI 边界 (本批不做)

- 不拆 settings 表结构 (无 migration 拆表; `webhook.secret` 迁移为数据搬移不是 DDL 变更)。
- 不动 `/secrets` `/sync` `/skills` `/maint` 设置菜单兄弟直达路由 (仅 `/settings` 页内)。
- 不补 alerts 规则创建 UI (整 cat 删除, 能力留 /knowledge 告警域)。
- 不动 api/quality.py 直连 repo 病灶 (记遗留)。
- 不做 Feature Gates 的路由级热生效 (TOML 写入靠既有 5s TTL 热重载影响运行时读数; 路由/job 注册保持启动快照, UI 明示)。

## 8. 验收口径

1. `/settings` 侧栏 7 cat / 5 组, 无只读监控 / 数据浏览 / 纯动作区块混入 (总览首屏除外);
2. 能力开关卡可切换任一 TOML gate, 运行时读数 5s 内跟随; 路由/任务需重启有明示; MCP 关闭态下可从 UI 重新开启且重启不丢;
3. LLM 模型配置唯一入口在「模型配置」cat (image_models/pipeline 内模型入口消亡);
4. `webhook.secret` 不再存于 settings 明文 KV; 跨端 bundle 不含非 config key;
5. 后端新增测试全绿, 全量回归 0 失败, generate_meta --check / ruff / 行数门 / nav4 守卫全过。
