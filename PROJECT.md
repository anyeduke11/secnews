# PROJECT.md — 项目心智模型

> **壳规则 (现行)**: v0.8 Sentinel 四菜单是唯一壳; v1.0 九领域对象以能力区块嵌入; 新能力只能以四菜单区块进入, 禁止新一级入口/新壳; 工具页经 `PageLayout` + `menuOf(pathname)` 自动归属四菜单; 主题 3 态 (light/dark/paper)。裁决与历史见 `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` + git log。





## 项目概述

- **一句话描述**: 面向 AI + 安全从业者的单机 AI Native 证据工作台 — SecNews 资讯聚合 + 知识复利 + 行动闭环 (v0.8.9, SentinelShell 四菜单唯一壳 + 资讯→Signal→Case→Claim→Run→Artifact→Knowledge 全链证据账本)。
- **核心目标**:
  1. 行动闭环: 资讯 → Signal → Case → Run → Artifact → Knowledge 的证据链落地 (人工回执 + pi 执行)
  2. 知识复利闭环: 采集 → wiki-first md 真源 → 学习/掌握 → 输出
  3. 安全领域纵深: MITRE ATT&CK / NVD CVE / 等保·关基·数安法 知识图谱
- **技术栈**: Python FastAPI + SQLite (WAL+FTS5, HOT/WARM/COLD ATTACH) + APScheduler; React 18 + Vite 5 + TS + Tailwind 3; Fernet (PBKDF2); pytest / Vitest+jsdom

## 架构概览

```
Frontend :8898 (React SPA, 路由全 lazy, 真源 routes/index.tsx, 速查 ROUTE_REGISTRY.md)
  SentinelShell 四菜单 / · /knowledge · /action · /settings (工具页经 PageLayout+menuOf 挂入) · /quality · /history · /maint
        │ HTTP/JSON/SSE
FastAPI :8000
  ├─ 88 routers (65 core 白名单, 扩展按 feature gate 条件注册, lazy include)
  ├─ 138 services / 7 包 (ai_hub · dsh · llm · pi · execution_plan · execution_runner · triggers) ·
  ├─ 19 collectors · 48 jobs (APScheduler) · MCP server (23 tools, config.feature_mcp 默认关)
  └─ ai_hub (LLM 单出口, 密钥来源 env-only) · dsh (Brain, 受管子进程
      not_configured→mock→ai_hub) · SSRF url_safety 单一真相源
        │
Data: SQLite HOT/WARM/COLD (ATTACH, Fernet) · llm-wiki-2.0/ md 真源 (FTS5 trigram+porter, watchdog) · COLD 密文备份 (scripts/cold_db_crypto.py)
```

- **关键路径**: `backend/main.py` → `api/__init__.py register_routers()` (core 白名单 + 扩展按 gate 条件注册) → `scheduler/scheduler.py` (48 job 集中注册, 实现在 `scheduler/jobs/` 按域拆分) → `repository/db.py` 启动期 ATTACH warm/cold。
- **feature gates**: `backend/config/feature_gates.toml` 10 gate — 开 9 (tech_stack/security_graph/secnews/dsh + info_filter/interest_engine/semantic_filter/ai_classify/pipeline_ner), 关 1 (mcp, 只管 /api/mcp/* 调试路由; server 本体走 config.feature_mcp)。crm 键已随 migration 116 删除; 四域删除 (2026-11-19) 退役 codegarden/codegarden_phase2b/sync/skill_registry/trigger_gate/user_skills 6 键。

## 模块地图

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| API 路由 | `backend/api/` | 88 router, ≤150 行, lazy import, `_registry.py` 按 gate 注册 | 已完成 |
| 服务层 | `backend/services/` | 138 services / 7 包; 依赖方向: 禁 `import backend.api` | 已完成 |
| — ai_hub | `backend/services/ai_hub/` (12 文件 3717 行) | LLM 单出口: gateway/_try_order + service/_resolve_provider + scenarios (deep/light/image); 密钥 env-only | 已完成 |
| — dsh | `backend/services/dsh/` (7 文件) | Brain: `runtime.resolve_effective` 三态 + ProcessSupervisor + bridge | 已完成 (真子进程未实测) |
| — execution | `backend/services/{execution_plan,execution_runner,pi}/` | pi 执行 agent 桥 + 计划生成 + 执行器 (工作区根 `workspace/`) | 已完成 |
| 采集器 | `backend/collectors/` | 19 collector, SSRF 防护走 url_safety | 已完成 |
| 调度器 | `backend/scheduler/` | 48 job 集中注册 + `_is_job_enabled()` gate 门控 | 已完成 |
| 存储层 | `backend/repository/` | 46 *_repo.py + migrations 134 个 .sql (编号至 137, 缺号 066-069) | 已完成 |
| 前端 | `frontend/src/` | 338 ts/tsx (不含测试), 17 组件域, I18nContext; 无数据层库 (fetch+interval) | 已完成 |
| wiki | `llm-wiki-2.0/` | md+YAML 真源, 路径只走 `backend/wiki_fs/paths.py` 单一源 | 已完成 |

## 编码约定

- **后端**: snake_case; router ≤150 行 + lazy import 协议; service 禁 `import backend.api`; ai_hub 是 LLM 唯一出口; wiki 路径改动只走 `wiki_fs/paths.py` (+`HOTSPOT_WIKI_ROOT`); 新服务 ≥30% docstring (CI `check_docstrings.py` 强制); monkeypatch 用全限定子模块路径; SQLite 连接线程亲和 × asyncio.to_thread 必须线程内构造
- **前端**: PascalCase 组件 / camelCase 变量; Tailwind 优先 + 测试 colocated; 路由 lazy 走 `routes/lazy-imports.ts`; i18n 走 I18nContext `t(key, fallback)` (无 react-i18next); Tailwind 配置改动需重启 dev server
- **测试**: pytest 4,727 / vitest 674 / tsc 0 错 (2026-11-20) / **零失败是硬要求** (skip 须环境性且留痕); conftest autouse 全开 gates; 日历周窗口 + now 相对种子必须钳制进周窗口 (周一炸弹)
- **提交纪律**: **必须 `git commit <显式 pathspec>`**, 禁 `git add -A` (2026-08-30 3840 文件事故); 远端推送/tag push 须用户授权 (V2-C11)

## 质量红线

1. **不删除已有 ingested 信息**; 列表排序用 `ingested_at DESC`
2. **SSRF 单一真相源**: 所有出站请求走 `backend/utils/url_safety.py` (`validate_url` / `safe_aiohttp_connector` / `safe_urllib_request`), 禁裸 httpx/urllib 出站
3. **LLM 调用必经 ai_hub 单出口**; 密钥来源 env-only (fail-soft 不抛)
4. **feature gate fail-closed**: 新扩展默认 false; gate import 时读一次 (conftest 注册期快照)
5. **wiki-first**: md 是真源, SQLite 是读缓存; 路径单一源 `wiki_fs/paths.py`
6. **前端端口 8898 / 后端 8000 禁止漂移** (dev/prod 共用, `--strictPort`; 后端任一时刻只能跑一份, dev/prod 切换前 stop; 数据根仍隔离 dev_data/ vs 仓库根 backend/data)
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

## 已知问题 (2026-09-05, 源 = CRITICAL_REVIEW 复核 ❌/◐ + Day 0 演练发现 + v0.8.2 收尾批判性审查)

- ~~七 gate 全 false 未开闸~~ → **已通电 (2026-09-05 Day 0)**: 7 gate true; 20 skill 真实运行验证随弹性层观察
- ~~运行时弹性缺失~~ → **已落地 (v0.8.1 Day 1-4)**; ~~graceful shutdown 缺~~ → **已落地 (Day 0)**
- ~~agent_loop/playbook_engine/skill_eval 死 gate 键~~ → **已移除 (v0.8.2 X-B3, 16→13)**; ~~mcp 语义分裂~~ → **已契约化 (X-B3, 双开关分工 docstring + 启动两态日志)**
- ~~备份完整性校验缺 (§2.4)~~ → **已落地 (v0.8.2 A4)**; ~~配置热重载缺 (§2.6)~~ → **已落地 (v0.8.2 A2, 动态读数层; 注册期快照仍需重启)**
- **[P1] provider 饱和排队尾延迟放大** (v0.8.2 A1 设计代价, 首轮审查 F1) — deep 场景 provider 缓慢故障 (未达熔断) 时 max_concurrent 之外的调用在 semaphore 排队; 熔断 trip 后每个已排队调用仍烧一轮 timeout (sensenova 90s) 才落 fallback。修复设计: `_call_provider` 获槽后重查 breaker state=="open" → 专用 skip 异常 + 循环头不计账 (拒绝≠失败); **需动 ai_hub 调用链 (D1"未裁决勿动"精神) 待裁决**
- **[P1] CI 从未真跑** (收尾审查 F2) — 推送禁止 → GitHub Actions 未执行过 v0.7.x~v0.8.2 任何提交, "门禁绿"均为本地模拟; 首推时 pip-audit / core-only 矩阵 / classify gate 首次真跑可能爆历史问题。首推前本地预演: pip-audit (**2026-09-05 已预演: 零已知漏洞**) + core-only env 矩阵 pytest
- **[P2] CI core-only job 语义漂移** (F3) — ci.yml env 只显式关 5 个扩展键, v0.8 七 gate TOML 通电后 core-only job 实际会注册扩展路由 (origin/main 未通电故当前 CI 无感, 推送后生效); 推送前应显式全关或重裁定
- **[P2] restore_from_backup 零测试覆盖** (F4) — A4 验证备份完整性但恢复路径无任何测试, "verify ok ≠ 可恢复"; 建议 A4 续篇补 E2E restore 测试
- **[P2] A1×A2 交互缺口** (F5) — max_concurrent 热更新不影响已建 semaphore (首现定容); recovery_timeout 热重载不影响已创建 breaker 实例 → /health thresholds 块可能与 breaker 实际值不一致
- **[P2] backup_verify 无新鲜度检查** (F6) — BACKUP_RETENTION=1 下备份可 8 天旧仍 integrity ok; 应加 mtime age 检查
- **[P2] /api/quality/rules Cache-Control 用户可感知** (F7) — PUT 后 ≤10s 浏览器缓存可能回旧规则 (前端 10s 轮询周期掩盖大半; 代码注释已声明)
- **pi CLI message_update 流式语义未接** (v0.8.1 D6 残项) — bridge 只取最终 message_end, 流式 UI §4.3.B (D1 独立窗口)
- **services 层 320 处宽泛 except Exception** — error_classifier 缺 (D-a, 未选)
- **前端数据层原始** — 25 处 setInterval/15 文件, 无 react-query/swr (方案 C, 未选)
- Toast 零使用 (UX 审计遗留)
- ~~pi CLI 未实测~~ → **已实测 (v0.8.1 D6, 0.84.4 live)**: 协议吻合 + 修 2 假阳性; soaktest 探针可重跑
- ~~stdlib logging 全仓不可见~~ (Day 0 发现) — 无 InterceptHandler, main.py 自身 log.info 隐形; 新代码一律 loguru (红线, 持续有效)

## 生命周期

当前阶段：**v0.8.9 主干流量专项 P0~P6 已交付**（人工回执闭环 + 观测收口 + 边界协议 + pi 执行 + L3 系统层加固 + Case 闭环/知识回流；试点演练①~⑥ 全 PASS，artifact_yield 活体 1.0）。P7 收口 **C7-1 已交付**（版本 0.8.9 置位 + 全链版本对齐 + 权威 PRD 回写）；**C7-2 `git tag v0.8.9` 待 owner**（前置：观测窗 2026-11-14 → 2026-12-14 满窗判定 M-9/M-10 + G1 计数达标 + T8 三主题人工走查归档）。M-4 包体遗留项已修（echarts tree-shaking，577,813 B / −23.6%）。
**远端推送/tag 须用户授权**（长期约束）。完整交付流水见 `docs/CHANGELOG.md` 与 `PROGRESS.md` 活跃段。

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
| 需求+发布 (v0.8.2) | 2026-09-05 | 通过 (发布 ◐) | X+Y 合批推荐 (上会话收尾, 无独立 PRD, 来源已摘录 PROGRESS); tag `v0.8.2` 本地已打 | 推送用户明令禁止 |
| 开发+测试 (v0.8.2) | 2026-09-05 | 通过 | X(5 项)+Y(3 项) 12 commits; pytest 3868/0 / vitest 425 / tsc 0 / ruff 全仓 0 / generate_meta 4/4 / vite build 0 / **pip-audit 零已知漏洞** | — |
| 批判性审查 (v0.8.2 收尾) | 2026-09-05 | 通过 (带发现) | 第一性原理逐变更面排查: **F1-F7 = P1×2 + P2×5** (饱和排队尾延迟 / CI 从未真跑 / core-only 漂移 / restore 无测试 / A1×A2 交互 / 备份新鲜度 / Cache-Control 体感), 全部落「已知问题」 | F2 部分 (pip-audit 预演 ✅); 其余待裁决/续篇 |
