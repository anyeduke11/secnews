# PROJECT.md — 项目心智模型

> **2026-09-05 全面刷新** (project-brain 中途接入): 本文件曾冻结在 2026-08-07 "架构阶段", 描述的前端三层 (资料/判断/行动, /data/judge/action) 已于 v0.7.0 **物理删除** (历史见 git log + ~~docs/superpowers/specs/2026-08-06-second-brain-three-layer-architecture-prd.md~~ 废止)。现按 v0.8.0 现实重写; 决策日志历史行保留。

## 项目概述

- **一句话描述**: 面向 AI + 安全从业者的单人本地工作站 — SecNews 资讯聚合 + 知识复利 + Skill/Playbook 看板型 AI 智能体 (v0.8.0)。
- **核心目标**:
  1. 看板型 AI 智能体: 常用对话/prompt/skill 固化为主面板可启停功能 (非 chatbox) — Skill 商店 + Playbook YAML 双轨
  2. 知识复利闭环: 采集 → wiki-first md 真源 → 学习/掌握 → 输出
  3. CodeGarden: AI 协作全生命周期管理 (服务网格/资源/编排)
- **技术栈**: Python FastAPI + SQLite (WAL+FTS5, HOT/WARM/COLD ATTACH) + APScheduler; React 18 + Vite 5 + TS + Tailwind 3; Fernet (PBKDF2); pytest / Vitest+jsdom

## 架构概览

```
Frontend :8898 (React SPA, 53 路由全 lazy)
  /secnews 6-tab 工作台 · SettingsHub 17 cat · Sentinel Terminal · /skill-store(+Builder) · /dashboard · /codegarden · /crm · /knowledge/*
        │ HTTP/JSON/SSE
FastAPI :8000
  ├─ 73 routers (45 core 白名单 + 10 组扩展, lazy include, feature gate 守卫)
  ├─ 107 services / 12 包 — v0.8 Skills 8 包: trigger_gate · skill_registry(20 内置) · agent_loop ·
  │   agent_memory · skill_runner · playbook_engine · skill_builder · skill_eval (gate 全 false)
  ├─ 14 collectors · 51 jobs (APScheduler) · MCP server (19 tools, gate=false)
  └─ ai_hub (LLM 单出口, 5 providers 四级链 env>kv>router>yaml) · dsh (Brain, 受管子进程
      not_configured→mock→ai_hub) · SSRF url_safety 单一真相源
        │
Data: SQLite HOT/WARM/COLD (ATTACH, Fernet) · llm-wiki-2.0/ md 真源 (FTS5 trigram+porter, watchdog) · WebDAV 坚果云
```

- **关键路径**: `backend/main.py` → `api/__init__.py register_routers()` (core 白名单 + 扩展按 gate 条件注册) → `scheduler/scheduler.py` (51 job 集中注册, 实现在 `scheduler/jobs/` 按域拆分) → `repository/db.py` 启动期 ATTACH warm/cold。
- **feature gates**: `backend/config/feature_gates.toml` 16 gate — 开 8 (codegarden/codegarden_phase2b/sync/tech_stack/security_graph/secnews/crm/dsh), 关 8 (mcp/info_filter + v0.8 Skills 六 gate, fail-closed 未开闸)。

## 模块地图

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| API 路由 | `backend/api/` | 73 router, ≤150 行, lazy import, `_registry.py` 按 gate 注册 | 已完成 (v0.8.0) |
| 服务层 | `backend/services/` | 107 services / 12 包; 依赖方向: 禁 `import backend.api` | 已完成 |
| — ai_hub | `backend/services/ai_hub/` (11 文件 2495 行) | LLM 单出口: gateway/_try_order + service/_resolve_provider 四级链 + scenarios (deep/light/image) | 已完成 |
| — dsh | `backend/services/dsh/` (7 文件) | Brain: `runtime.resolve_effective` 三态 + ProcessSupervisor + bridge | 已完成 (真子进程未实测) |
| — v0.8 Skills | `backend/services/{trigger_gate,skill_registry,agent_loop,agent_memory,skill_runner,playbook_engine,skill_builder,skill_eval}/` | 触发门(限流+队列) / 20 内置 skill / 五阶段状态机 / 记忆 / 分流 / YAML 编排 / 自建 / 评测 | 已完成, **gate 全 false 未实战** |
| 采集器 | `backend/collectors/` | 14 collector, SSRF 防护走 url_safety | 已完成 |
| 调度器 | `backend/scheduler/` | 51 job 集中注册 + `_is_job_enabled()` gate 门控 | 已完成 |
| 存储层 | `backend/repository/` | 43 *_repo.py + migrations 92 .sql (编号至 095) | 已完成 |
| 前端 | `frontend/src/` | 284 ts(x), 18 组件域, I18nContext ~300 key×2; 无数据层库 (fetch+interval) | 已完成 |
| wiki | `llm-wiki-2.0/` | md+YAML 真源, 路径只走 `backend/wiki_fs/paths.py` 单一源 | 已完成 |

## 编码约定

- **后端**: snake_case; router ≤150 行 + lazy import 协议; service 禁 `import backend.api`; ai_hub 是 LLM 唯一出口; wiki 路径改动只走 `wiki_fs/paths.py` (+`HOTSPOT_WIKI_ROOT`); 新服务 ≥30% docstring (CI `check_docstrings.py` 强制); monkeypatch 用全限定子模块路径; SQLite 连接线程亲和 × asyncio.to_thread 必须线程内构造
- **前端**: PascalCase 组件 / camelCase 变量; Tailwind 优先 + 测试 colocated; 路由 lazy 走 `routes/lazy-imports.ts`; i18n 走 I18nContext `t(key, fallback)` (无 react-i18next); Tailwind 配置改动需重启 dev server
- **测试**: pytest 3740 / vitest 425 / tsc 0 错 / **零 skip 是硬要求** (环境性失败必须根治); conftest autouse 全开 gates; 日历周窗口 + now 相对种子必须钳制进周窗口 (周一炸弹)
- **提交纪律**: **必须 `git commit <显式 pathspec>`**, 禁 `git add -A` (2026-08-30 3840 文件事故); 远端推送/tag push 须用户授权 (V2-C11)

## 质量红线

1. **不删除已有 ingested 信息**; 列表排序用 `ingested_at DESC`
2. **SSRF 单一真相源**: 所有出站请求走 `backend/utils/url_safety.py` (`validate_url` / `safe_aiohttp_connector` / `safe_urllib_request`), 禁裸 httpx/urllib 出站
3. **LLM 调用必经 ai_hub 单出口**; provider 配置四级链, llm_secrets 不动
4. **feature gate fail-closed**: 新扩展默认 false; gate import 时读一次 (conftest 注册期快照)
5. **wiki-first**: md 是真源, SQLite 是读缓存; 路径单一源 `wiki_fs/paths.py`
6. **前端端口 8898 / 后端 8000 禁止漂移** (allocate-port 已定 8766 为 dsh 预留)
7. **敏感数据**: Fernet 加密, 未解锁显示 `******`; 不提交 .env/credentials; 主密钥丢失不可自助重置
8. **API 错误格式** 统一 `{"detail": {"message": "...", ...}}`; playbook/用户命令走危险命令黑名单
9. **架构数字同步**: 改注册代码后 `generate_meta.py --check` (CI 门), ARCHITECTURE.md + 4 个 AGENTS.md 同步
10. **不宣称项目安全审计完成** (Mimosa scanner_no_output 本地误报常态, 照常提交但不得背书)

## 决策日志

| 日期 | 决策 | 理由 | 替代方案 |
|------|------|------|----------|
| 2026-07-14 | 知识管理 4 大领域分类 | 符合知识生命周期 | 三层分类（后期演进） |
| 2026-07-20 | CodeGarden Phase 2b 服务网格 | 自动发现 + 拓扑图 + 联动 | 手动配置（未采纳） |
| 2026-08-06 | 第二大脑三层架构 (前端) | 统一抽象资讯/知识/项目 | 领域分类导航（当时采纳, **v0.7.0 已物理删除**） |
| 2026-08-24 | 终审: agent 三层 (Harness/pi/hotspot) + wiki 单根 + 退役冻结 | 第一性原理收敛 | — |
| 2026-08-30 | v0.6.3 P4: llm-wiki-2.0 唯一根, knowledge/ 旧根删除 | 根治周一炸弹 | 双根共存（未采纳） |
| 2026-08-31 | LLM provider 四级链 env>kv>router>yaml (Batch 2) | 配置弹性 | 硬编码（未采纳） |
| 2026-09-02 | 禁零散管理类孤页, 统一收编 /settings; commit 显式 pathspec | 孤页扩散失控; 3840 文件事故 | — |
| 2026-09-03 | v0.8 形态 = Skill 商店 + Playbook 双轨 (非 chatbox); 内置+用户可建 | 复用度 100%, 契合工作站 | 重做 chatbox（未采纳） |
| 2026-09-04 | dsh mock 优先 (真二进制仅搭桥); runner_pool 3; tag `v0.8.0-skills` | 风险控制 | — |
| 2026-09-05 | 架构图 dsh 诚实化 (选项 A 中庸版: 保留 :3210 + 暴露降级链); CRITICAL_REVIEW 09-05 复核; **V0.8.1_PLAN v1.1 推荐方案 A (断路器+health 单一真相源), 裁决点 D1-D6 待用户拍板** | 看图即知真相 | 选项 B 独立网关（1 月工作量, 未采纳） |
| 2026-09-05 | **v0.8.1 D1 = 方案 A 锁定** (断路器 + provider_health 单一真相源联动, 5 天); D2-D6 按默认; PRD v1.0 立项 | 雪崩防御 + 通电前置; 单一真相源避免双记账矛盾 | B (2 天, 缺健康度数据源) / C (SWR, 与弹性正交) / D-d pi 实测 (顺延次周, 非否决) |
| 2026-09-05 | **Day 0 通电裁定**: 7 个 v0.8 gate → true (演练通过后保持全开, PRD F5 [假设]); mcp 回关 (gate 语义分裂, server 本体归 config.feature_mcp); 修复 user_skills gate 漏登记 P0 | 演练 = 通电验收; fail-closed 随时可回关 | mcp 同开 (拒绝: 调试路由扩面非本批目标) |

## 已知问题 (2026-09-05, 源 = CRITICAL_REVIEW 复核 ❌/◐ + Day 0 演练发现)

- ~~七 gate 全 false 未开闸~~ → **已通电 (2026-09-05 Day 0)**: 7 gate true, 演练 pytest 3755/0 fail; 20 skill 真实运行验证仍随弹性层落地观察
- **运行时弹性缺失** — 断路器 + provider_health 缺 (V0.8.1 方案 A, Day 1-5)
- **graceful shutdown 缺** → **已落地 (Day 0)**: drain + WAL checkpoint + 20× soak 0 损坏
- **agent_loop / playbook_engine / skill_eval 三 gate 无消费点** (Day 0 演练发现) — toml 死配置键, 服务本体不受 gate 控制; 随未来消费点登记
- **mcp extension gate 与 is_mcp_enabled() 语义分裂** (Day 0 发现) — 两套开关, mcp 回关 + P2 备忘
- **stdlib logging 全仓不可见** (Day 0 发现) — 无 InterceptHandler, main.py 自身 log.info 全隐形; 新代码一律 loguru (PROJECT 红线)
- **pi CLI 未实测** — agent_bridge jsonl 协议字段仍推测 (V0.8.1 D-d, live 测试不进 CI)
- **services 层 320 处宽泛 except Exception** — error_classifier 缺 (D-a, 未选)
- **前端数据层原始** — 25 处 setInterval/15 文件, 无 react-query/swr (方案 C, 未选)
- 备份完整性校验缺 (§2.4) / 配置热重载缺 (§2.6) — v0.8.2 候选
- Toast 零使用 / SecretsPage 主密钥明文输入 (UX 审计遗留)

## 生命周期

当前阶段：**开发 (v0.8.1 batch)** — Day 0 完成 (graceful + 演练 + 通电, `3bfce93`); Day 1 完成 (CircuitBreaker 薄状态机 + 14 测试); **Day 2 完成 (2026-09-05)**: ProviderHealth 唯一判定源 (5min 窗判定 + min_samples 防单发误熔断 + breaker 驱动, 23 测试, services 107 不变); 下一 Day 3 = gateway + image_service 接入 → Day 4 /api/llm/health + scenario 权重 → Day 5 回归; 规格 = [`docs/V0.8.1_PRD.md`](docs/V0.8.1_PRD.md) v1.0 + [`docs/V0.8.1_PLAN.md`](docs/V0.8.1_PLAN.md) v1.2。

### 阶段检查记录

| 阶段 | 检查时间 | 结果 | 发现的问题 | 修复状态 |
|------|----------|------|------------|----------|
| 需求 (v0.5-v0.8.0) | 2026-08-06 ~ 09-04 | 通过 | 各版本 PRD/PLAN + 用户裁决 | 已落地 |
| 初始化 | 2026-08-06 | 通过 | PROJECT.md 覆盖 8 段落 | **2026-09-05 全面刷新** |
| 架构 (v0.5 三层) | 2026-08-07 | 通过 | 该架构 v0.7.0 已被替代删除 | 已退役 |
| 架构审查 (全仓) | 2026-09-05 | 通过 (带发现) | CRITICAL_REVIEW 复核 19 finding (✅/◐/❌) | ❌ 项转 V0.8.1_PLAN |
| 开发审查 | 2026-09-04 | 通过 | v0.8 Phase A-D 22 commits; `generate_meta --check` 过 | — |
| 测试对齐 | 2026-09-04 | 通过 | pytest 3740 / vitest 425 / tsc 0 / 零回归 | — |
| 安全扫描 | 2026-09-03 | ◐ 部分 | P0 SSRF 11 出站加固 + url_safety 57 case; Mimosa 本地误报, **不宣称完整审计** | 持续 |
| 交付 | 2026-09-04 | 通过 | V0.8_USER_GUIDE / MIGRATION_TO_V0.8 / CHANGELOG | — |
| 发布 (v0.8.0) | 2026-09-04 | ◐ 部分 | tag `v0.8.0-skills` 本地已打 | 远端推送待用户授权 |
| 需求 (v0.8.1) | 2026-09-05 | 通过 | V0.8.1_PLAN v1.1 (审查 P0×3 已修) → **D1=方案 A 用户裁决锁定**; PRD v1.0 立项 (三维审查 P1×2/P2×2 已修) | 已闭合, 转开发阶段 |
