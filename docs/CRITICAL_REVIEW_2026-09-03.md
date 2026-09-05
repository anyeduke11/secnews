# Critical Review — hotspot 架构 (2026-09-03 · 状态复核 2026-09-05)

> **复核 (2026-09-05, main HEAD `d22bcd7`, v0.8.0-skills post-merge)**: 自本文成文以来, v0.8 Skills Phase A-D (20 commits, merge `39e3fb0`) / P0 SSRF 副作用根除 (`9911cfd`+`f9ac22a`) / 架构图 v0.8 重画 (`771d5f4`) / §4.4 dsh 真相落账 (`d22bcd7`) 已落地。本次复核逐项标注 ✅ 已落地 / ◐ 部分 / ❌ 仍开放, §〇 快照与 §六 路线图按 v0.8.0 现实重写; 复核证据均为 2026-09-05 grep/ls/generate_meta 实测。
> **目的**: 基于 [`hotspot-architecture.html`](../hotspot-architecture.html) 渲染的实际图与代码事实 (services 107 / routers 73 / migrations 至 095 (92 .sql) / collectors 14 / jobs 51), 从 5 维做第一性原理批判。
> **范围**: 质量/健壮性 / 灵活性/可靠性 / 前后端效率 / pi.dev 整合现状 / BS-AI-Agent 最终形态路径。
> **方法**: 不只列问题, 每项给 (a) 代码证据, (b) 影响, (c) 推荐方案 (P0/P1/P2 分级 + 工作量估算)。
> **性质**: 这是 audit 不是 task list, 用户裁决后转 plan.md (memory `prd-iterative` 工作流)。

---

## 〇、当前架构快照 (2026-09-05 复核, on main HEAD `d22bcd7`, v0.8.0-skills)

```
Frontend (React 18 + Vite :8898, 425 vitest)
  ├─ 6-tab 工作台 (/secnews) + SettingsHub 17 cat + Sentinel + CodeGarden + CRM + Knowledge
  ├─ v0.8 新增: /skill-store (+详情 /skill-store/:id) + /skill-store/new Builder + /dashboard 看板
  └─ 数据: 路由全量 lazy (lazy-imports.ts 1:1 映射) + manualChunks vendor 拆分; 数据层仍 fetch+轮询 (无 SWR/Query)
Backend (FastAPI + uvicorn :8000, 3740 pytest)
  ├─ 14 collectors (P0 SSRF url_safety 单一真相源 + P1 信源管道 8 项根治后)
  ├─ 51 jobs (APScheduler 单进程)
  ├─ 107 services (v0.8 起以"包"扩张: trigger_gate/ skill_registry/ agent_loop/ agent_memory/ playbook_engine/ skill_builder/ skill_eval/ dsh/)
  ├─ 73 routers (lazy include, feature gate 守卫; v0.8 +5: skill-registry / runs / builder / trigger-webhook / dashboard)
  └─ MCP server (HTTP/SSE + stdio, 19 tools, gate=false)
Data Plane (本地单机)
  ├─ SQLite WAL+FTS5 (HOT/WARM/COLD 三库 ATTACH; migrations 至 095 · 92 .sql: 091 trigger_tickets / 093 agent_memory / 094 playbook / 095 user_skills)
  ├─ llm-wiki-2.0/ md 真源 (FTS5 trigram, watchdog 即时同步)
  └─ WebDAV 坚果云 (zip+Fernet 加密, 周一 10:30)
External
  ├─ 5 LLM providers (四级链 env>settings.kv>router>yaml + llm_secrets; 仍缺 provider_health 语义降级)
  ├─ dsh (Brain) — ProcessSupervisor 受管子进程, :3210 (not_configured→mock→ai_hub 降级链, §4.4 已落账)
  └─ v0.8 Skills 全家桶: trigger_gate / skill_registry (20 内置) / agent_loop / agent_memory / playbook_engine / skill_builder / skill_eval — 7 gate 全 false (fail-closed, 未实战)
```

**关键事实 (2026-09-05 实测):**
- **服务数 107 / Router 数 73 / jobs 51 / collectors 14** (`scripts/generate_meta.py` 实测)
- **migrations 至 095** (92 个 .sql 文件)
- **测试基线**: pytest 3740 / vitest 425 (v0.8 Phase D 验收)
- **feature gates 16 个**: 8 开 (codegarden / codegarden_phase2b / sync / tech_stack / security_graph / secnews / crm / dsh) / 8 关 (mcp / info_filter / skill_registry / trigger_gate / agent_loop / playbook_engine / user_skills / skill_eval)
- **架构图**: v0.8 重画 (`771d5f4`, 5 叙事修复); 2026-09-05 archify 重梳 (11 components / 4 boundaries / 3 guided views, 9/9 artifact checks + visual-check 全视口通过)

---

## 一、质量与健壮性 (Quality & Robustness)

### 1.1 [P1] 缺统一的并发限流与背压层

> **复核 2026-09-05**: ◐ 部分 — v0.8 A1 `trigger_gate/throttle.py` 落了**入口级** RateLimiter (60/min·user + 600/min 全局, 仅覆盖 trigger-gate 入口); collector / LLM 出站的并发仍零散 Semaphore, 全局 TokenBucket 单一真相源仍缺。

**证据**: `grep -l "asyncio.Semaphore" backend` 仅 7 个文件零散使用 (collectors/session.py / quality/jobs.py / crawl4ai_client.py / source_scheduler_service / url_batch_check / summary_enricher), **没有全局 TokenBucket / 进程级 BoundedSemaphore**。

**影响**:
- 51 个 job 同窗口触发可能打爆 SQLite WAL 锁 (卡顿根因之一, P3 `381f05f` 自执行 trigram FTS 才缓解)
- 多 collector 并发抓同一 source → 对方源站 429 风险 (memory `gateway-s1-s4-spike-flow` 提到 P6 multimodal 429 限流)
- LLM 调用并发无上限 → provider rate limit 击穿 → 401/429 雪崩

**推荐**: 在 `backend/utils/concurrency.py` 建单一真相源 (借鉴 `url_safety.py` 模式):
- `GlobalSemaphore()` — 按 extension 名 (`llm` / `collect` / `db_write`) 分组
- `RateLimiter(provider, qps, burst)` — provider 级别令牌桶 (基于 `tenacity` 已有 import, 加 retry)
- Job scheduler 加 `max_concurrent_jobs=N` 闸门 (APScheduler `max_instances=1` 已部分做到, 但跨 job 全局无闸)

**工作量**: ~3 天 (utils + 全局 init + 5 个关键路径接入 + 测试)。

---

### 1.2 [P0] 缺断路器 (Circuit Breaker) — 单源/单 provider 失败拖垮全系统

> **复核 2026-09-05**: ❌ 仍开放 — `CircuitBreaker` 类 0 命中 (grep 命中仅为注释/无关词)。**v0.8.1 推荐首选** (与 §2.1 联动, 见 §6.0 三选一)。

**证据**: `grep -rE "circuit|breaker" backend` 0 命中。`tenacity` 仅在 `tools/import_cache.py` 用到。

**影响**:
- 一个 LLM provider 持续 500 时, 每个请求重试 5 次 → 100ms → 5s/请求 → 51 job 排队雪崩
- 一个 collector 持续超时 → aiohttp 连接池占满 → 其他 collector 等连接
- memory `gateway-s1-s4-spike-flow` 提到 P6 multimodal 429, 没自动熔断 → 后续请求持续失败

**推荐**: 三态断路器 (CLOSED/OPEN/HALF_OPEN), per-provider 配置 (失败 N 次 → OPEN 30s → HALF_OPEN 探针 1 个):
```python
# backend/utils/circuit_breaker.py
class CircuitBreaker:
    state: Literal["closed", "open", "half_open"]
    failure_count: int
    opened_at: float
    recovery_timeout: float = 30.0
```
接入点: `ai_hub` 调用前 / `collectors/fetch_source` / `webdav_sync` / `llm_secrets` unlock 失败。

**工作量**: ~2 天 (utils + 4 接入点 + per-provider config + 测试)。

---

### 1.3 [P1] SQLite 单进程锁竞争 — 长事务持锁阻塞采集

> **复核 2026-09-05**: ◐ 部分 — 卡顿根治已全链闭环 (P0 `f423af9` + P2 `d2fc1ea` + P3 `381f05f` 自执行 trigram FTS); 但 observability/audit 表拆 cold db 仍未做, 长事务拆批未系统化。

**证据**: 88 个 migrations + 51 jobs + ATTACH 3 个 db → 主库写并发压力大。memory `hotspot-perf-lag-audit` 已记录 3 统计端点扫盘 4149 md (337-1176ms/次) 是 P0 卡顿主因。

**影响**:
- WAL 模式允许多读单写, 但写锁仍独占 → 51 job 写排队的隐式瓶颈
- 大量 FTS5 INSERT 触发内部 update → 长事务

**推荐**:
1. 拆 `audit_log` / `observability_*` 到 `hotspot-cold.db` (已 ATTACH, 但 router 仍走主库连接) — 让热路径只剩采集/分析
2. 引入 `pg-lite` (pglite) 替代 SQLite for observability? 评估迁移成本 (~2 周, P2)
3. **最小改动**: 长事务拆批, commit_every=N 行 (memory `sqlite-fts5-attached-db` 提到 `record_audit SAVEPOINT` 模式可借鉴)

---

### 1.4 [P0] 错误处理"宽容到掩盖问题" — `try/except: pass` 散布

> **复核 2026-09-05**: ❌ 仍开放 (证据修正) — 字面 `except: pass` 实测 **0 处** (原文估计 30+ 偏悲观); 真实形态是 **services 层 320 处宽泛 `except Exception`** (各自 logger.warning, 无分类/聚合/告警)。P1.7 failure_rate 三档聚合 (`1c6c6b1`) 只覆盖采集管道, error_classifier 仍缺。

**证据**: `grep -c "except Exception" backend/services` = 320 (2026-09-05 实测); `unified-error-handling` 不存在, 每个模块自定 `except Exception as e: logger.warning(...)`, 没分类/聚合/告警。

**影响**:
- 用户在 PROGRESS.md 看到 "执行成功", 实际 5/10 job 静默失败 → 信任债
- 真正出问题时定位困难 (memory `parallel-session-stash-wipes` 提到 "stash 清走未提交" 类似问题: 缺审计)

**推荐**: 建 `backend/utils/error_classifier.py`:
- `classify(exc) -> ErrorKind` (LLMError / NetworkError / DBError / ValidationError / UnknownError)
- 聚合窗口 (5min) → 触发 ActiveAlertsBanner (memory `v0.7 Batch ④` 已落告警引擎, 但只盯阈值不盯错误率)
- 用户裁决: 是否升级为 Sentry-like SDK?

---

### 1.5 [P1] 缺统一的 Schema 校验 — Pydantic 散落 router, 服务间用 dict

> **复核 2026-09-05**: ❌ 仍开放 — v0.8 新包 (SkillDef dataclass 等) 是局部改进, 服务间 dict 传参主流未变。

**证据**: `grep -l "BaseModel" backend/api | wc -l` 估算 60+ 文件。`backend/services` 之间传 `dict[str, Any]` 占多数, 缺乏服务级 Pydantic DTO。

**影响**:
- service 间 refactor 改动, 编译期不报错 (Python 鸭子类型) → 运行时崩溃
- 测试 fixture 维护成本高 (memory `env-test-failures-fix-root-cause` 提及)

**推荐**: 给每个 service 暴露的 method 加 `Pydantic` 返回类型契约, 渐进式迁移 (新代码必须, 老代码不强制)。

---

## 二、灵活性与可靠性 (Flexibility & Reliability)

### 2.1 [P0] LLM Provider 切换是真"四级链"但缺"语义降级"

> **复核 2026-09-05**: ❌ 仍开放 — ai_hub 包 11 模块 (egress/gateway/scenarios/usage/...) 无 provider_health; v0.7.4 三场景路由 (deep/light/image) 落地后场景维度更丰富, 降级决策依据更缺。**v0.8.1 推荐与 §1.2 联动** (见 §6.0)。

**证据**: memory `hotspot-batch2-llm-provider-chain` 提到四级链 env > settings.kv > router > yaml, 走通。但缺:
- **健康度感知的 fallback** (一个 provider 持续 500 → 自动切下个)
- **场景感知的 fallback** (deep 档 sensenova 降级 → ollama 还是 anthropic? 决策依据缺失)
- **配额感知** (5 LLM provider 各有 RPM/TPM 限制, 无统一配额管理)

**影响**: "配置链"通了, 但"运行时弹性"未通。S1-S4 spike (memory `gateway-s1-s4-spike-flow`) P6 multimodal 429 只能被动重试, 不会自动切换。

**推荐**:
- `backend/services/provider_health.py` — per-provider 滑动窗口 (1min/5min/1h) 失败率
- 与 1.2 断路器联动 → 自动 OPEN → 切 yaml router 默认
- `quality/scenario_router.py` 加场景权重表 (deep 优先 sensenova → anthropic → ollama)

**工作量**: ~3 天 (provider_health + 联动 + 场景权重 + 测试)。

---

### 2.2 [P1] Feature Gate 模式优秀但"开关粒度太粗"

> **复核 2026-09-05**: ❌ 仍开放 — gate 总数 8→16 (v0.8 新增 7 个全 fail-closed, 模式健康), 但"同 extension 内子开关"粒度问题不变; settings.kv 逐 skill 开关 (`skill.<id>.enabled`) 是 A2b 已落的部分替代。

**证据**: `backend/config/feature_gates.toml` 当前 16 个总开关, `is_extension_enabled()` 二态。

**影响**:
- 想"开 codegarden 但关 codegarden_phase2b"已支持 (嵌套)
- 但"开 info_filter 但只启用 Layer 1 (源级), 关 Layer 2 (item 级)" → 做不到
- 不能做 A/B (同一 extension 两个分支对比)

**推荐**: 引入 `feature_flags` (plural) 而非 `feature_gates`:
```toml
[info_filter]
enabled = false
layer_1_enabled = true   # 源级
layer_2_enabled = false  # item 级
mode = "allowlist"       # "allowlist" / "blocklist" / "hybrid"
```
实现层 `is_extension_enabled("info_filter")` AND `is_feature_on("info_filter.layer_1")`。

**工作量**: ~2 天 (config schema + util 函数 + 1 个 extension (info_filter) 改造为样板 + 测试)。

---

### 2.3 [P0] 单点故障: uvicorn 单进程 + SQLite 单文件

> **复核 2026-09-05**: ❌ 仍开放 — `grep "SIGTERM|graceful" backend/main.py run.py` 0 命中 (2026-09-05 实测)。

**证据**: `python run.py` 单进程, 无 graceful shutdown (SIGTERM → 直接 kill, WAL 检查点可能丢)。

**推荐**:
- uvicorn `--workers 1` 但加 `--loop uvloop` + `--http httptools` (性能 +30%)
- `signal.signal(SIGTERM, graceful_shutdown)` → flush WAL + finish in-flight job
- P1 引入 `supervisord` 或 `systemd` 守护进程 (生产部署)

---

### 2.4 [P1] 备份策略粗 — 周日 full + 每日 WAL, 缺增量校验

> **复核 2026-09-05**: ❌ 仍开放 — `backend/scripts/` 仅有 verify_phase13.py, 无 backup_verify。

**证据**: PROGRESS 提到 "周日 full + 每日 WAL 增量", 但缺:
- 备份完整性校验 (Fernet 解密 → 行数对比)
- 备份不可写 (immutable, 防误删)
- 异地备份 (只本地)

**影响**: 主库损坏 + 备份损坏 = 数据丢 (虽然概率小但灾难性)。

**推荐**: `backend/scripts/backup_verify.py` 周一 02:00 跑, 解密 + 行数 + 抽样 md5 对比, 失败 → ActiveAlertsBanner。

---

### 2.5 [P2] 三层 db (HOT/WARM/COLD) 设计正确但路由层混用

> **复核 2026-09-05**: ❌ 仍开放 (P2 远景, 无新进展)。

**证据**: 启动期 `db.get_connection()` ATTACH 3 db, 但 router/service 经常跨 db 写 (实际生产代码对 WARM 表写操作必须指 `warm.` alias, PROGRESS 已记)。

**影响**: 重构期可能漏 alias → 写入主库而非 WARM → 容量失控。

**推荐**: DAO 层引入 `Repository[T]` 范型, 编译期锁定 db (类似 `backend/repository/db.py` 的命名约定)。

---

### 2.6 [P1] 配置热重载缺 — 改 `feature_gates.toml` / `llm.yaml` 必须重启

> **复核 2026-09-05**: ❌ 仍开放 — info_filter 5s TTL cache 是唯一局部样板 (settings.kv 写后 invalidate), 全局 watcher 未做。

**证据**: memory `hotspot-env-operational-quirks` 提到 `feature gate 在 import 时读一次, conftest 注册期快照根治 404`。生产侧同样问题。

**推荐**: `backend/config/watcher.py` (watchdog 监听 .toml/.yaml), reload 时调 `invalidate_*()` 系列 (info_filter 5s TTL 模式可借鉴)。

---

## 三、前后端效率 (Frontend & Backend Efficiency)

### 3.1 [P0] 前端无 SWR / React Query — 每个组件自管 fetch + setInterval

> **复核 2026-09-05**: ❌ 仍开放 — `frontend/package.json` 无 @tanstack/react-query / swr (2026-09-05 实测); v0.8 新组件 (SkillStore / Dashboard) 仍 fetch+interval 模式。**v0.8.1 三选一备选③** (见 §6.0)。

**证据**: `frontend/package.json` 依赖只有 react / react-dom / react-router-dom / echarts (无 `@tanstack/react-query` / `swr`)。`InfoFilterCard.tsx` 我刚写的就用了 `window.setInterval(refresh, 10_000)` —— 典型反模式:
- 每个组件独立 poll, 同一端点被 N 个组件打 N 次
- 离开页面不停 (memory leak)
- 没 stale-while-revalidate, 用户看到 loading skeleton
- 没错误重试 / dedup / focus 暂停

**影响**:
- 51 个 job 的 status 端点被前端 N 个组件同时 poll → 后端 QPS 倍增
- 网络/电池 浪费 (用户移动端用 hotspot)
- 已有 SSE 通道 (memory `v0.7 Batch ⑧ D3`) 但前端没用, 仍轮询

**推荐**: 引入 `@tanstack/react-query` (5KB gzip, 已成 React 生态标准):
- 统一 `staleTime` / `cacheTime` / `retry`
- `refetchInterval` 内置, 支持 `refetchIntervalInBackground: false`
- 与现有 SSE (D3) 集成: SSE event → `queryClient.setQueryData(...)` → 全局无 refetch
- 渐进迁移: 新组件 (InfoFilterCard v2) 用 react-query, 老组件保持 (memory `parallel-session-stash-wipes` 警惕不要 `git add -A` 全扫)

**工作量**: ~1 周 (依赖 + QueryClient 配置 + 重构 10 个核心组件 + 测试)。

---

### 3.2 [P1] 后端无 HTTP 压缩 + 缓存头

> **复核 2026-09-05**: ❌ 仍开放 — 全局 `GZipMiddleware` 0 命中; 仅 `export.py:129` 单端点手写 `Cache-Control: max-age=1800`。

**证据**: `grep -E "Cache-Control|ETag|gzip|compress" backend/main.py` 0 命中。前端 vite build 默认 gzip 但后端 FastAPI 没配 `GZipMiddleware`。

**影响**:
- SettingsHub 17 cat 渲染的 JSON (含 i18n 30+ key + secrets 状态) 每次全量返 → 浪费带宽
- 重复访问 `/api/quality/rules` (每 10s poll) → 同一响应不缓存

**推荐**:
```python
# main.py
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 静态/字典端点加 Cache-Control
@router.get("/api/quality/rules", response_model=...)
async def quality_rules(response: Response):
    response.headers["Cache-Control"] = "public, max-age=10"  # 10s
    ...
```

---

### 3.3 [P1] 后端 router 懒加载但服务级是单例

> **复核 2026-09-05**: ❌ 仍开放 (P1 大改, 无新进展; v0.8 包化反而加深了模块级单例)。

**证据**: `extensions/__init__.py` + `api/_registry.py` 实现 router lazy include (feature gate 关闭时不挂载), 但 service 实例通常模块级 `_instance = Service()` 单例 → 测试期 + 进程内不可热替换。

**影响**: 重启即生效 (不优雅, 但单机场景可接受)。

**推荐**: 服务级 DI (FastAPI Depends) — 当前 service 直接 import 调用, 缺依赖注入 → 单元测试必须 monkeypatch。重构为 FastAPI Depends 注入 → 测试无需 monkeypatch。

**工作量**: ~2 周 (大改, 风险高)。

---

### 3.4 [P1] 前端 bundle 单体 — 无路由级 lazy + 无 vendor chunk 拆分

> **复核 2026-09-05**: ✅ **已落地 (本文当时判断有误)** — v0.5 M1-Task3 已拆 `manualChunks` (vendor-react / vendor-echarts, 主 chunk <300KB, 拆分前基线 1.14MB); 路由全量 lazy (`routes/index.tsx` 集中声明 + `lazy-imports.ts` 1:1 映射, v0.8 /dashboard·/skill-store 均走此机制)。本项从路线图移除。

**证据 (修正)**: `frontend/vite.config.ts` manualChunks 配置 + `frontend/src/routes/lazy-imports.ts` (2026-09-05 实测)。

---

### 3.5 [P2] 实时性依赖 poll — 应转 SSE / WebSocket

> **复核 2026-09-05**: ◐ 部分 — `/api/events` (events.py `publish_event` EventBus) + attention_events + codegarden_ops SSE 端点 + 观测面板接入 (Batch⑧ D3) 已有; kl_pipeline 进度 / 采集状态 / 告警激活仍 poll, 与 react-query 集成未做。

**证据**: memory `v0.7 Batch ⑧ D3` 已规划 SSE 接入观测面板, 但只针对观测面板, 其他实时性需求 (kl_pipeline 进度 / 采集任务状态 / 告警激活) 仍走 poll。

**推荐**: 全站统一 SSE channel `/api/events`:
- event types: `kl_progress` / `collect_status` / `alert_fired` / `agent_run` / `info_filter_changed`
- 与 react-query 集成 (3.1): SSE → setQueryData → UI 自动更新, 零 refetch

**工作量**: ~3 天 (后端 EventBus + SSE endpoint + 前端 SSE client + react-query 集成)。

---

### 3.6 [P1] 后端 API 无版本号 — 改 endpoint 必须前端同步

> **复核 2026-09-05**: ❌ 仍开放 (无新进展)。

**证据**: router prefix 全是 `/api/xxx`, 无 `/api/v1/`。

**影响**: 重命名 / 字段删 → 前端 breaking change 难协调 (用户多端用)。

**推荐**: 加 `/api/v1/` 前缀, 老路由保留 6 个月做 deprecation warning。

---

## 四、pi.dev 整合现状 (Critical)

> **复核 2026-09-05**: v0.8 B4 (`d7ed96b`) 落了 dsh runtime 三态切换 (`not_configured→mock→subprocess`) — §4.1 "runtime 是占位符"的表述对 **dsh builtin** 已不成立 (mock 可跑); 但 **pi 真实 CLI 调用仍未实测** (§4.3.A Phase A 前置), agent_bridge jsonl 协议字段仍是推测。§4.3 Phase B/C 未动。

### 4.1 当前状态: **配置文件存在, 但 runtime 是占位符**

**代码证据**:
- `config/agents.yaml` (line 53-61) 完整注册 `pi` runner: `command: ["pi", "-p", "--mode", "json"]`, `protocol: jsonl`, `task_types: [execute]`
- `backend/services/agent_bridge.py` (v0.6.3 落地) 完整支持 `jsonl` 协议解析 (`message_end.message.content[]`)
- `backend/api/agents_api.py` 暴露 `/api/agents/*` 端点
- `backend/config/agent_runner_schema.py` (line 36-44) `route()` 纯函数支持 `pi` 路由

**实际行为 (memory `gateway-s1-s4-spike-flow` + memory `hotspot-dsh-pi-integration-gap`):**
> "dsh 实机协议未对齐 (桥接端点仍按推测), 待用户配置真实启动命令实测"
> "Step 2 维持 pause (trigger-gate 三选一, 当前 0 触发)"

**判断**:
- **schema 完整** ✅ (yaml + 协议解析 + 路由)
- **runner 注册完整** ✅ (detect_available_agents + run_agent_task)
- **dsh 网关未启动** ❌ (vendor/dsh/ 不存在, M4 Task16 未落地)
- **UI 未暴露** ❌ (前端 AgentRunnerCard 显示 "dsh not configured" / "stopped")
- **真实跑通未验证** ❌ (无 E2E 测试触发 pi 真实调用, test_agent_bridge.py 只 mock subprocess)

### 4.2 [P0] pi 作为 hotspot 组件的差距清单

| 维度 | 当前 | 目标 (作为 hotspot 组件) | 差距 |
|------|------|-------------------------|------|
| **配置** | agents.yaml 已含 | 注册为 "pi runner" 完整配置 | ✅ 已达标 |
| **协议** | jsonl (推测) | 实际跑通 + 容错 | ⚠️ 协议推测, 需实测验证 |
| **调用** | subprocess.Popen (通用) | wrapper class `PiRunner` (类型化) | ❌ 当前是 dict in/out, 缺 Pydantic |
| **观测** | observability_records.finish_agent_run 钩 | 完整 trace + 流式 UI 反馈 | ⚠️ 有记录但前端不显示进度 |
| **安全** | cwd 锁定 codegarden/<project>/ | 加 sandbox flag + 出口审计 | ⚠️ 仅 cwd 锁定, 缺 syscall 限制 |
| **持久化** | cg_events 表 (CodeGarden) | pi run 全程 transcript 入库可检索 | ❌ transcript 写入 cg_events, 检索难 |
| **重试** | 仅 timeout kill | 断路器 (1.2) + 任务重排 | ❌ 重试逻辑缺失 |
| **Web UI** | AgentRunnerCard (开关) | 流式进度条 + 工具调用可视化 | ❌ 仅有 启停 按钮, 无运行时 |
| **触发** | 无 trigger-gate | 用户在 CardRunnerCard 看到 "触发" 按钮 | ◐ v0.8 A1 trigger_gate + D1 三触发源已落 (gate=false 未开闸) |
| **Multi-agent** | 4 runner 并存 (builtin / claude / codex / pi) | 协同调度 (claude 出方案 → pi 执行) | ❌ 当前是单 runner 单 task |

### 4.3 [P1] 真正整合路径 (3 阶段)

**Phase A: 协议实测 + 容错 (1 周)**
- 在真实 macOS 环境跑 `pi -p --mode json "hello"`, 抓 NDJSON 流
- 修正 `agent_bridge.py` 中 jsonl 协议解析的字段路径推测
- E2E 测试: `test_pi_real_invocation.py` 真实启动 pi CLI, 断言 transcript 完整入库

**Phase B: PiRunner 类型化 + 观测增强 (1 周)**
- `backend/services/pi_runner.py` 抽出 pi-specific runner 类 (Pydantic input/output)
- `backend/observability_records.py` 加 `record_pi_session(id, transcript_path, exit_reason)`
- 前端 AgentRunnerCard 加 SSE 流式进度条 (复用 Batch ⑧ D3 SSE 基建)

**Phase C: 协同调度 (2 周, P2)**
- `backend/services/multi_agent_orchestrator.py` 编排: claude-code 出方案 → pi 执行 (参考 v0.5 §19.3)
- 触发面: 用户在 dsh 卡片点 "Multi-agent Refactor" → 拆子任务 → 派发到不同 runner
- 取消 trigger-gate 的 "0 触发" 现状, 落地真实触发

### 4.4 [P1] dsh (DeepSeek Harness) :3210 是真"独立网关"还是"占位端口"

**证据**: 架构图 dsh 标 `:3210`, `backend/api/dsh_api.py` + `backend/services/process_supervisor.py` 完整支持 ProcessSupervisor (受管子进程)。前端 DshControlCard 一键启停。

**判断**:
- **受管子进程 ✅** (ProcessSupervisor 落到位)
- **独立网关 ❌** (无 vendor/dsh/, 实际是 ai_hub builtin DeepSeek runner, 不是独立 dsh 服务)
- **:3210 端口 ❌** (代码 grep "3210" 仅在 docstring 注释, 实际进程是 uvicorn :8000 内 builtin)

**结论**: 当前架构图把 dsh 画成"独立网关"是**视觉误导**, 实际是 uvicorn 进程内的 builtin runner。重构方向:
- 选项 A: 移除 :3210 节点, 把 dsh 改为 "internal runner pool" 框
- 选项 B: 真正拆出独立网关 (vendor/dsh/ 子模块, gunicorn worker 模式, 端口 3210) — 大改, 1 月工作量

**落账 (2026-09-05)**: 走选项 A 的"诚实化中庸版" — 保留 :3210 端口标注 (用户可能配的 endpoint) + 显式暴露降级链, 不移除节点:
- `backend/services/dsh/runtime.py:resolve_mode()` 3 状态返回 `("mock"|"subprocess"|"not_configured", reason)` (B4 commit `d7ed96b` 已落)
- `backend/services/dsh/supervisor.py:139` status 暴露 4 态 `connected/starting/stopped/not_configured` (CHANGELOG line 462)
- 架构图 `★ DSH (Brain) · ProcessSupervisor · :3210 (not_configured→mock→ai_hub)` 副标签 (v0.8.0-post `771d5f4` 5 叙事修复) — 把降级链写进图, 用户看图即知真实语义, 不再误导成"独立网关"

---

## 五、未来形态: BS-AI-Agent (Browser + Server AI Agent)

### 5.1 当前架构 → BS-AI-Agent 演化路径

**BS-AI-Agent 定义**:
- **B (Browser)**: React SPA 是 UI, 用户交互面, 实时响应
- **S (Server)**: FastAPI 是执行宿主, 长任务/工具调用/LLM 网关
- **AI-Agent**: 自主决策 + 工具调用 + 多步推理 (claude / pi / dsh builtin 协同)

**当前 hotspot 已具备要素**:
- ✅ Browser (React SPA :8898, 372 tests)
- ✅ Server (FastAPI :8000, 3111 tests)
- ✅ AI 单能力 (ai_hub LLM 单出口, 5 providers, 四级链)
- ⚠️ Agent 半成品 (4 CLI runners, dsh 受管子进程, protocol 解析)
- ❌ Agent 自主性 (用户每次点按钮触发, 无 trigger-gate 自动)
- ❌ 多 Agent 协同 (4 runner 单跑, 无 orchestrator)

### 5.2 [P0] BS-AI-Agent 三大核心组件缺口

> **复核 2026-09-05**: ✅ **三大缺口全部落地 (v0.8 Skills Phase A/B)** — ① Trigger Layer = `trigger_gate/` (A1: 限流+持久化队列+三档优先级+worker 泵; D1 三触发源 webhook/KL/collector); ② Reasoning Layer = `agent_loop/` (B1: Intent→Plan→Execute→Reflect→Commit 五状态机 + checkpoint 崩溃恢复); ③ Memory Layer = `agent_memory/` (B3: recall/miner + B6 feedback_log 回灌)。**注意: 三者 gate 全 false, 未实战开闸**。

| 组件 | 当前 | 缺口 | 推荐实现 |
|------|------|------|----------|
| **1. Trigger Layer** (触发层) | 仅手动按钮 | 自动 trigger-gate (信息源触发 / 时间触发 / 异常触发) | `backend/services/trigger_gate.py` + 三类 trigger config (TOML), 与 4.4 dsh trigger-gate 三选一打通 |
| **2. Reasoning Layer** (推理层) | 单步 ai_hub | 多步推理 (ReAct / Plan-and-Execute / Reflection) | `backend/services/agent_loop.py` — 拆 plan → act → observe → reflect 四阶段, 每步独立 checkpoint |
| **3. Memory Layer** (记忆层) | llm-wiki-2.0 文档 | Agent 短期记忆 (对话上下文/工具调用栈) + 长期记忆 (用户偏好/历史决策) | `backend/services/agent_memory.py` — 短期: Redis-like in-proc (TTL); 长期: SQLite 表 `agent_sessions` / `agent_decisions` / `user_preferences` |

### 5.3 [P1] Agent ↔ User 协作模式 (Human-in-the-loop)

**当前**: 用户触发 → Agent 跑 → 返结果 (单轮, 无中途介入)。

**目标 BS-AI-Agent 协作模式**:
```
User: "把这周所有金融安全的资讯整理成报告"
  ↓
Agent Loop:
  Step 1: 拆解任务 (Plan)
    - 抓取本周资讯 (collect API)
    - 按 5 大方向分类 (classify)
    - 提取关键事件 (summarize)
    - 生成结构化报告 (write md)
  Step 2: 执行 (Act) + 用户实时反馈
    - 进度条实时更新
    - 中途用户可 "暂停 / 调整方向 / 跳过某源"
  Step 3: 反思 (Reflect)
    - 检查覆盖率 (本应 200 篇, 实际 150 篇, 差 50)
    - 提示用户补充
  Step 4: 提交 (Commit)
    - 写入 knowledge/<date>.md
    - audit_log 留痕
    - 用户最终确认 / 修订
```

**实现层**:
- `backend/api/agents_api.py` 加 `POST /api/agents/loop` + SSE 流式进度
- `frontend/src/components/SecNews/AgentRunnerCard.tsx` 重写为流式 UI (类似 ChatGPT)
- 持久化: `agent_sessions` 表 + `agent_decisions` 表 + `agent_transcript` 表

### 5.4 [P1] Agent 工具调用生态

**当前**: MCP server (19 tools, HTTP/SSE) 已落地 (memory `hotspot-mcp-extension-pattern`), 但 hotspot 内部 service 没注册为 MCP tool → Agent 无法调用 hotspot 自身能力。

**目标**: 全站 service 注册为 MCP tool:
- `mcp_invoke_collect_source(name)` / `mcp_query_knowledge(query)` / `mcp_add_info_filter_rule(...)` / `mcp_run_kl_pipeline(stage)` ...
- Agent 通过 MCP 调用 hotspot 自身能力 (类似 Claude Code 调用 Bash/Read)

**工作量**: ~2 周 (tools schema 注册 + Agent runner 集成 + 测试)。

### 5.5 [P2] Agent 评估 (Eval) 与可观测

> **复核 2026-09-05**: ◐ 大幅推进 — v0.8 C5 `skill_eval/` 落地 (5 黄金 fixtures × 32 assertions + judge 评分 + SQLite 报告 + markdown 渲染); 真实 LLM judge engine 留 v0.9, agent run 成功率周报仍未做。

**当前**: 观测覆盖 LLM / Job / Agent / Process 4 类型 (memory `v0.7 Batch ①`), 但缺:
- Agent transcript 检索/分析
- Agent 成功率 (task type → runner → 成功率)
- 人类评分 (feedback API 已落, 但未绑定 agent run)

**推荐**: `backend/services/agent_eval.py`:
- 跑 30 个 fixture task → 各 runner 评分
- 失败模式聚类 (timeout / parse_error / llm_500 / auth_fail)
- 周报: 各 runner 周成功率 + 平均耗时 + token 成本

### 5.6 [P0] BS-AI-Agent 终极形态: 9 大特征

| # | 特征 | 当前 (2026-09-05 复核) | 距离 | 优先级 |
|---|------|------|------|--------|
| 1 | 触发层 (自动/手动) | ✅ v0.8 A1 trigger_gate + D1 三触发源 | gate=false 未实战 | 已落地 |
| 2 | 推理层 (多步) | ✅ v0.8 B1 agent_loop 五状态机 + checkpoint | gate=false | 已落地 |
| 3 | 记忆层 (短期+长期) | ✅ v0.8 B3 agent_memory + B6 feedback 回灌 | gate=false | 已落地 |
| 4 | 工具调用 (MCP) | 19 tools 外部 | 全站 service 注册 MCP | P1 |
| 5 | 协作层 (HITL) | ◐ B6 历史回放+反馈打分 + D2 /dashboard | SSE 实时流式 UI | P1 |
| 6 | 协同调度 (Multi-agent) | 4 runner 单跑 | orchestrator 落地 | P2 |
| 7 | 评估层 (Eval) | ✅ v0.8 C5 skill_eval (5 fixtures) | 真实 LLM judge (v0.9) | 已落地 |
| 8 | 安全层 (sandbox) | ◐ cwd 锁定 + playbook 危险命令黑名单 (C1) | syscall + 出口审计 | P1 |
| 9 | 部署层 (独立网关) | uvicorn 单进程 | gunicorn + supervisor | P2 |

> **复核 2026-09-05**: 9 特征中 **1/2/3/7 已落地, 5/8 部分落地** — 原计划 1 季的量, v0.8 一个 batch 干完 4 项; 剩余 4/5/6/8/9 约 1 个月量。当前瓶颈从"组件缺失"变为"**gate 未开闸 + pi 未实测**"。

---

## 六、综合推荐: 短期 (1 月) 与中期 (1 季) 路线 (2026-09-05 复核版)

### 6.0 v0.8.1 方向三选一 (承 v0.8.0-post Task 3, 用户待裁决)

| 选项 | 内容 | 工作量 | 理由 |
|---|---|---|---|
| **① (推荐)** | §1.2 断路器 + §2.1 provider_health/语义降级 **联动 batch** | ~5 天 | 两者强依赖: provider_health 滑动窗口 → 触发断路器 OPEN → 自动切下个 provider; 拆开做技术债翻倍。20 内置 skill + 4 runner 开闸后, provider 500 雪崩是第一风险 |
| ② | §1.2 断路器 alone | ~2 天 | 最小防御, 但没有健康度数据源, 熔断阈值只能拍脑袋 |
| ③ | §3.1 前端 react-query (SWR) | ~1 周 | 体验收益最大, 但与 provider 弹性正交, 可后置 |

### 6.1 短期 1 月 (P0 必修, 复核后余量)

| # | 项 | 工作量 | 风险 | 复核状态 |
|---|----|-------|------|---|
| 1.2+2.1 | 断路器 + provider 健康度联动 (= v0.8.1 推荐①) | 5 天 | 低 | ❌ 仍开放 |
| 2.3 | uvicorn graceful shutdown | 0.5 天 | 低 | ❌ 仍开放 |
| 1.4 | 错误分类器 (320 处宽泛 except 收敛 + 聚合告警) | 2 天 | 低 | ❌ 仍开放 |
| 4.3.A | pi 协议实测 + E2E | 1 周 | 中 (需真实 pi CLI) | ❌ 仍开放 |
| 新增 | **v0.8 七 gate 开闸演练** (skill_registry / trigger_gate / agent_loop / playbook_engine / user_skills / skill_eval / info_filter 实战验证 + ARCHITECTURE 同步) | 1 天 | 低 (fail-closed 随时回关) | 新增项 |

**已从短期清单移除 (v0.8 已落地)**: ~~5.2.1 trigger_gate~~ (A1+D1) / ~~5.2.2 agent_loop~~ (B1) / ~~5.2.3 agent_memory~~ (B3) / ~~5.5 agent_eval~~ (C5, 原 P2 提前)。

### 6.2 中期 1 季 (P1 演进, 复核后)

- 1.1 全局并发限流 (把 `trigger_gate/throttle.py` 升级为全局单一真相源, 借鉴 `url_safety.py` 模式) + 1.5 Pydantic DTO
- 2.2 feature flags 细粒度 + 2.4 备份校验 + 2.6 配置热重载
- 3.1 react-query 全站迁移 (若 6.0 选③ 则提前) + 3.2 HTTP 压缩 + 3.5 SSE↔react-query 集成 + 3.6 API 版本
- 5.4 全站 service MCP 化 + 5.3 HITL 流式 UI (B6 已有回放/打分, 缺 SSE 实时流)
- 1.3 observability/audit 表拆 cold db
- 4.3.B PiRunner 类型化 + 观测增强

### 6.3 长期 (P2 远景)

- 2.5 Repository 范型 + 3.3 服务级 DI
- 4.3.C Multi-agent orchestrator (claude 出方案 → pi 执行的 4 runner 协同)
- 5.6.8 sandbox (syscall + 出口审计) + 5.6.9 gunicorn/supervisor
- 4.4 选项 B: dsh 真独立网关 (仅当 multi-runner 并发成为实际瓶颈)

---

## 七、结语 (2026-09-05 复核更新)

hotspot 当前架构是 **"健康的中年, 刚完成一次大手术"**:
- ✅ 单一事实源清晰 (DAO / llm-wiki / agents.yaml / feature_gates.toml)
- ✅ Feature Gate 受管扩展域优秀 (16 gate, v0.8 新增 7 个全 fail-closed)
- ✅ 测试基线扎实 (pytest 3740 + vitest 425, v0.8 Phase D 验收)
- ✅ **BS-AI-Agent 四大件已齐**: trigger_gate (A1+D1) / agent_loop 五阶段 (B1) / agent_memory (B3) / skill_eval (C5) — 本文成文时的"三大核心组件缺口"已全部落地
- ✅ 减法已做: P0 SSRF 单一真相源 (11 出站点) + P1 信源管道 8 项根治 + 卡顿根治 P0-P3 闭环

**当前最大的 gap (复核后重排)**:
1. **gate 全关未实战** — 20 skill / agent loop / playbook / eval 全部 gate=false, "建成了但没通电"; 开闸演练是 v0.8.1 的前置 (1 天)
2. **运行时弹性缺失** — 断路器 + provider_health (§1.2+§2.1) 仍开放, 开闸后 provider 500 雪崩是第一风险 (= v0.8.1 推荐①)
3. **真实 pi 集成未跑通** (§4.3.A) — 4 runner 中 pi 协议字段仍是推测
4. **前端数据层原始** — 无 react-query, 轮询/SSE 割裂 (§3.1+§3.5)

**第一性原理结论 (复核后)**:
- **services 107 已到顶**: v0.8 用"包化" (trigger_gate/ agent_loop/ skill_registry/ 等 6 个新子包) 而非新增平铺 service 文件, 方向正确, 保持
- **"建成" ≠ "通电"**: v0.8 的价值要等 gate 开闸 + 三触发源真实跑起来才能兑现; 下一步优先"通电"而非"再加件"
- **pi 集成仍是分水岭**: 判断不变 — 4 runner 真实跑通 + orchestrator 才算真"AI Agent"
- **BS-AI-Agent 终态时间表提前**: 9 特征中 4 项已落地 (原计划 1 季), 剩余约 1 个月量 + Eval 真实引擎 (v0.9)

---

## 附录 A: 文件证据索引 (2026-09-05 复核实测)

| 论点 | 文件 | 2026-09-05 实测 |
|------|------|-----|
| 断路器缺失 | `grep -r "CircuitBreaker" backend` | 0 类命中 (仅注释/无关词) — 仍缺 |
| react-query 缺失 | `frontend/package.json` | 无 @tanstack/* / swr — 仍缺 |
| pi 协议推测 | `backend/services/agent_bridge.py` | jsonl 字段仍推测, pi CLI 未实测 |
| dsh :3210 真相 | `backend/services/dsh/runtime.py:resolve_mode` | B4 `d7ed96b` 三态落账; §4.4 选项 A 已执行 (`771d5f4` 图 + `d22bcd7` docs) |
| graceful shutdown 缺 | `grep "SIGTERM" backend/main.py run.py` | 0 命中 — 仍缺 |
| 错误宽容掩盖 | `grep -c "except Exception" backend/services` | 320 处宽泛捕获 (字面 `except: pass` 0 处) |
| services 107 | `scripts/generate_meta.py` | 107 (2026-09-05 实测) |
| routers 73 | `scripts/generate_meta.py` | 73 (v0.8 +5) |
| migrations 92 | `ls backend/repository/migrations/*.sql \| wc -l` | 92 个 .sql, 最高 095 |
| trigger-gate | `backend/services/trigger_gate/` | A1 落地 (5 模块 + migration 091), gate=false 未实战 |
| agent_loop / memory | `backend/services/agent_loop/ agent_memory/` | B1/B3 落地, gate=false |
| skill_eval | `backend/services/skill_eval/` | C5 落地 (5 fixtures × 32 assertions), gate=false |
| bundle 拆分 | `frontend/vite.config.ts manualChunks` + `routes/lazy-imports.ts` | v0.5 已落地 — §3.4 原判断有误, 已移出路线图 |
| 全局限流 | `backend/services/trigger_gate/throttle.py` | 仅入口级; 全局 TokenBucket 仍缺 |
| MCP 19 tools | memory `hotspot-mcp-extension-pattern` | test_mcp_server 断言锁定 |

## 附录 B: 优先级矩阵 (2026-09-05 复核版)

| 维度 | P0 (1 月) | P1 (1 季) | P2 (远景) |
|------|-----------|-----------|-----------|
| 健壮性 | 断路器+provider_health (v0.8.1①) / graceful shutdown / 错误分类 | 全局限流 / Pydantic DTO | Repository 范型 / 服务级 DI |
| 灵活性 | ~~provider 健康度~~ (并入 v0.8.1①) | feature flags 细化 / 配置热重载 / 备份校验 | 独立网关 (仅按需) |
| 效率 | — (react-query 降为 v0.8.1 备选③) | HTTP 压缩 / SSE↔react-query / API 版本 | — |
| pi 集成 | 协议实测 + E2E | 类型化 / 观测 | Multi-agent 协同 |
| Agent 终态 | **v0.8 七 gate 开闸演练** (新增) | 全站 MCP 化 / HITL 流式 UI / sandbox | orchestrator / Eval 真实引擎 / gunicorn |

> **提交策略**: 用户裁决后, 短期 P0 转 plan.md 分批落地, 严格 pathspec (memory `parallel-session-stash-wipes`)。PROGRESS.md 加对应段。