# SecNews Knowledge Dashboard — 安全从业者 AI 助手的平台看板层

> **当前状态 (2026-09-05, v0.8.0)**: Sentinel Terminal 全屏页已上线 (`/` `/judge` `/action` `/garden`); data/judge/action 三层目录与 6 cognitive modes 已物理删除; `/secnews` 为统一工作台 (6 tab); dsh 内置为受管子进程 — 前端 `/secnews/settings` 一键启停 (gate dsh=true, 控制面 `/api/dsh/control/*`); ai_hub 已包化, LLM provider 四级切换链落地; v0.8 Skills 四阶段全部收口 — Phase A 触发门 + Skill Store + 20 内置 skill / Phase B 详情页历史回放反馈打分 (B6) / Phase C Playbook 引擎 + Cron 调度 + Skill Builder + Eval 评测框架 (C1-C5) / Phase D webhook + KL 事件 + collector failure 三触发源 (D1) + /dashboard 看板 (D2) + i18n 双语补齐 (D3) + 文档迁移指南 (D5), 详见 `PROGRESS.md` v0.8 Skills 段; v0.8.0-post 治理收口 (架构图 archify 0-error 重渲 / CRITICAL_REVIEW 09-05 全文复核 / 过期文档修正) 见 `PROGRESS.md` v0.8.0-post 段, **v0.8.1 方向已立项待裁决** — `docs/V0.8.1_PLAN.md` (推荐 A: 断路器 + provider_health 联动 5 天; 裁决点 D1-D6; 前置 = 七 gate 开闸演练 1 天)。
> 历史决策 (产品三层架构裁决 / wiki-first 存储哲学 / Phase 7 退役冻结) 见 `PROGRESS.md` 与 `git log`，不在此重复。

---

## CodeGarden Phase 2b — Service Mesh / Resource Hub / Orchestration Engine (v0.3.0)

- M2 `cg_services` 表 + 自动发现 (lsof/docker/pm2) + 拓扑图 SVG + 日志/指标/重启
- M3 `cg_resources` 表 (port/domain/env_template/volume) + 8898 端口保护 + Fernet 加密
- M4 `cg_dependencies` 表 + `cg_events` 表 + Playbook YAML 执行 + BFS 影响分析
- 调度器: job 16 `cg_service_scan` (300s) + job 17 `cg_event_process` (60s)
- 详细设计: [`docs/CodeGarden_PRD_v1.7.md`](docs/CodeGarden_PRD_v1.7.md)

## v0.4.3 — Core/Extension 软分层 + Feature Gates (2026-08-18)

> **架构数字由 `scripts/generate_meta.py` AST 反推维护** (51 jobs / 14 collectors / 73 routers / 107 services),
> 改动注册代码后必须同步 ARCHITECTURE.md: `python scripts/generate_meta.py` (CI 有 `--check`)。

- **开关源**: `backend/config/feature_gates.toml` — 当前 16 gate: 默认开启 15 (codegarden / codegarden_phase2b / sync / tech_stack / security_graph / secnews / crm / dsh + v0.8 七 gate info_filter·skill_registry·trigger_gate·agent_loop·playbook_engine·user_skills·skill_eval, 2026-09-05 Day 0 开闸演练通电);
  默认关闭 1 (mcp — extension gate 只管 /api/mcp/* 调试路由, server 本体由 is_mcp_enabled() 读 config.feature_mcp, 两套开关语义分裂)
- **core 永不消失**: `backend/core/routers.py` 45 个 core router 白名单, 与扩展域防重叠断言;
  扩展 router 按 `is_extension_enabled()` 条件注册 (关闭时路由 404)
- **job 门控**: `scheduler.py` `_is_job_enabled()` 按扩展归属过滤 8 个扩展 job
- **env 覆盖**: `HOTSPOT_FEATURE_GATES='{"extensions": {...}}'` 优先级高于 TOML (CI core-only 用)
- **测试约定**: conftest autouse fixture 测试环境全开 gates; 组合矩阵见 `backend/tests/test_feature_gates.py`

## v0.8.0-post 治理与 v0.8.1 立项 (2026-09-05)

- **项目心智/阶段台账**: `PROJECT.md` (2026-09-05 project-brain 刷新) — 生命周期当前阶段 + 阶段检查记录; 接手顺序 = 本文件 → PROJECT.md → `PROGRESS.md` 活跃段
- **审计事实源**: `docs/CRITICAL_REVIEW_2026-09-03.md` (2026-09-05 复核版, 19 finding 逐项标 ✅/◐/❌) — 动手前先查对应项状态, 勿凭旧印象; `docs/V0.8_REFACTOR_PLAN.md` 已加已完结横幅 (25 个 `[ ]` 是计划态留痕, 执行记录以 `PROGRESS.md` 为准)
- **v0.8.1 下一 batch**: `docs/V0.8.1_PLAN.md` — 推荐 A = CRITICAL_REVIEW §1.2 断路器 + §2.1 provider_health/场景权重联动 (5 天, 复用 `retry_policy.py` 模式与 dsh runtime 3 连败先例, 不引新依赖); 备选 B (断路器 alone 2 天) / C (react-query 5-7 天) / D-a~d (error_classifier 2 天 / graceful shutdown 0.5 天 / GZip 2 天 / pi 协议实测 1 周); 裁决点 D1-D6 待用户拍板 — **未裁决前勿动 ai_hub 调用链** (`gateway._try_order` / `service._resolve_provider`)
- **前置项**: 七 gate 开闸演练 (skill_registry/trigger_gate/agent_loop/playbook_engine/user_skills/skill_eval/info_filter 全开后全量回归 + ARCHITECTURE 同步, 1 天)
- **架构图**: `hotspot-architecture.html` + `hotspot-architecture.candidate.json` 已入仓 — **candidate.json 是唯一编辑入口**, HTML 由 `archify deliver` 生成不手改; 硬约束: viewBox 宽 ≤~1390 (context 字号 9px 上限 × 投影 ≥6px @1440) / 列距 ≥40px (26px 以下渲染器崩溃) / 副标签长度按盒宽预算 → **加节点必先删节点**; 复跑 archify 会覆盖入仓产物
- **dsh 真相 (叙事锚点)**: 受管子进程, :3210 降级链 `not_configured→mock→ai_hub` — 图/docs/代码 (`dsh/runtime.py:resolve_effective` 三态) 三层已对齐, 新文档沿用此口径, 勿再写"独立网关"

## Core 路径边界声明 (core.include / core.exclude)

> **目的**: 让 review-trigger (`generate_meta.py --classify` / 各类 lint gate) 能定向识别 "core 内" vs "core 外" 变更, 两类变更对应不同门槛, 不让 non-core 改动被无谓的完整架构门拖慢。

- **配置源**: 仓库根 `core.include` / `core.exclude` (gitignore-style glob; tests / build artifacts / cache 在 exclude 排除); 无 `core.include` 时回退到 `_FALLBACK_CORE_DIRS` + WARN
- **解析规则**: `scripts/generate_meta.py --classify` 优先读 include/exclude; `--strict-config` 缺文件 → exit 2; 匹配语义: 前导 `/` = 锚定根; `**` = 跨段; 不支持 negation `!`
- **CI 集成**: `.github/workflows/ci.yml` `backend` job 加 step `Classify changed paths (core vs non-core review gate)` — 仅 PR 触发, `git diff --name-only` 经 `--classify --batch --strict-config` 输出 `has_core` / `tier` 到 `GITHUB_OUTPUT`
- **门槛差异**: Core 内变更必跑 `generate_meta.py --check` + `pytest backend/tests/` + `ruff check backend/` + `pip-audit` + 启动冒烟 + 全开/全闭 feature_gates 矩阵; non-core 可缩到 `pytest -k <scope>` / touched files ruff
- **修改配置**: 新建核心模块 (`backend/foo/`) → 同步 `core.include` 加 glob; 新建测试目录 → `core.exclude` 加 glob; 改 `core.include` 自身算 core 变更

### 本地用法

```bash
# 单路径分类
python scripts/generate_meta.py --classify backend/services/ai_hub.py

# 批量 (从 stdin 读, git diff 风; exit 0=核心命中, 1=全 non-core, 2=配置错误)
git diff --name-only origin/main | python scripts/generate_meta.py --classify --batch --json
```

## Agent Assets Lint Policy (agent-assets-review)

声明级别 (声明与机械化门一致, 不可被静默忽略):

- **warning** = 非阻断建议 (reviewer 备注 / PR 评论, 不阻断 CI); 资产当前可保留使用, 但需附 reviewer 在 PR 中说明后续处理计划。
- **error** = 强制阻断 (CI 退出非零, 必须修复才能合并); 声明的验证步骤在 `.github/workflows/ci.yml` `backend` job 中机械化执行, 任何 error 都标记 job 失败。

资产规则 (`.agents/skills/<name>/SKILL.md`):

- **ERROR** — 新增长 skill (`>500 行`) 必须包含 `references/` 子文档。Baseline 豁免名单见 `scripts/harness_baseline.json`; 任何不在 baseline 中的长 skill 立即按 ERROR 处理, 不被静默忽略。
- **WARNING** — SKILL.md 缺失 YAML frontmatter 的 `name` / `description` 字段; 或在 baseline 内已豁免的长 skill 暂缺 `references/` (reviewer 在 PR 中跟踪迁移进度)。

机械执行:

- **CI**: `.github/workflows/ci.yml` 的 `backend` job 追加
  `python scripts/harness_analyze.py --check` 步骤, errors 非零 → job 失败; warnings 通过 reviewer 备注保留。
- **本地**: `python scripts/harness_analyze.py` (默认人类可读) 或 `--format json` (脚本消费)。CI 与本地两条路径均执行同一脚本同一规则, 避免声明与验证漂移。
- **豁免收紧**: 在 `scripts/harness_baseline.json` 删除某 skill 条目 = 立刻对该 skill 强制 ERROR (用于逐步清理历史债)。

## 安全扫描插件职责分工 — `codex-security` vs `security-scan`

两条名称家族相似的安全插件均为本工作区**并存(complementary)**关系,不互为 rename 或 replacement。两者触发关键词均含 "security scan / 安全扫描",需要靠本节文档 + description 关键词消歧。

### Capability Fingerprint 对比

| 维度 | `codex-security`(local, OpenAI `0.1.14`) | `security-scan`(qoder-bundler, CodeSec `0.8.1`) |
|---|---|---|
| 入口 | MCP STDIO `codex-security` 服务 | `~/.qodersec/bin/qodersec` 二进制 + Qoder 云端后端 |
| hooks | **无**(不自动触发) | `SessionStart`(ensure-deps)+ `PostToolUse: Edit\|Write\|MultiEdit\|NotebookEdit`(每次编辑后自动 review) |
| 默认启用 | 否(用户本地加装) | 是(`defaultEnabled: true`) |
| 触发关键词 | "Codex Security"、"OpenAI Codex security"、"Codex 安全工作流" | "Qoder security scan"、"L2 lightweight"、"L3 deep"、"cloud scan" |
| 适用场景 | 完整安全生命周期(扫+验证+攻击路径+追踪+修复+加固+报告) | 编辑即时轻量 review + 显式三档扫描 |
| 不适用场景 | 即时轻量 edit-time warning(无 hook) | 漏洞验证 / 攻击路径 / 修复建议 / 报告生成(无对应子技能) |

### 路由规则(首命中即停)

1. 用户显式调用 `$codex-security:<skill>` 或声明 "Codex Security" / "OpenAI Codex security" / "Codex 安全工作流" → 走 `codex-security:*` 全套工作流。
2. 用户显式调用 `/security-scan` / "Qoder 安全扫描" / "L2 轻量扫描" / "L3 深度扫描" / "cloud scan" / "扫描这个项目/文件/目录" → 走 `security-scan` 单技能 + 三档 picker。
3. 用户在 Edit/Write 后未显式调用,但 `security-scan` hooks 已自动触发 edit-time review → 由 `security-scan` 静默处理;**不**反向触发 `codex-security`。
4. 用户请求 "验证/追踪/修复这个 finding"、"攻击路径分析"、"漏洞 write-up"、"威胁建模"、"架构加固方案"、"SECURITY.md 政策" → **必须**走 `codex-security:*`(另一插件无对应子技能)。

### 显式消歧调用

同名 `security-scan` 子技能必须按插件名前缀调用:

```text
# Codex Security 完整工作流(单遍扫 + 验证 + 攻击路径 + 报告)
$codex-security:security-scan <repo-or-path>
$codex-security:deep-security-scan <repo-or-path>     # 深度多遍
$codex-security:security-diff-scan <diff-target>      # PR/commit/branch
$codex-security:fix-finding <finding-id>
$codex-security:vulnerability-writeup <finding-id>

# Qoder 内置 — 三档 picker + cloud scan
/security-scan                       # bare → picker(L3/L2/Project-file)
/security-scan --layer=l2            # 显式 L2
/security-scan --layer=l3            # 显式 L3
/security-scan backend/api/          # cloud scan,具体路径
/security-scan backend/ frontend/    # 多路径
```

### Trigger 关键词补全建议

> **注意**:`~/.qoder/plugins/cache/` 下两个插件目录当前为**只读**(Qoder bundler 自动管理缓存),无法就地 patch SKILL.md。需要重新打包插件或通过 Qoder 插件管理面板下发。下面是建议值,作为 patch 参考。

`codex-security/skills/security-scan/SKILL.md` description 字段建议在首句加 "OpenAI Codex Security" + 排除规则:

```yaml
description: "OpenAI Codex Security standard single-pass audit. Use ONLY when the user invokes Codex Security explicitly or via the '$codex-security:' prefix. Do NOT use for Edit-time review, L2 lightweight, L3 deep, or Qoder cloud scan; route those to the Qoder security-scan plugin instead."
```

`security-scan/skills/security-scan/SKILL.md` description 首句已含 "Qoder" + L2/L3/picker 关键词,无需调整;若需进一步消歧,可在末尾追加反指语句:

```yaml
description: "... Prefer this skill for Qoder Edit-time review and cloud/L2/L3 scans. For full Codex Security lifecycle (validation, attack-path, fix-finding, vulnerability write-up, hardening, threat modeling), use the '$codex-security:' prefix instead."
```

### 替换关系

无。两条插件均保留活跃状态,不互相 disable。`codex-security/README.md` 上游已显式承认并存:

> "If another installed plugin also ships a `security-scan` skill (e.g. Qoder's built-in security-scan plugin), disambiguate by plugin when invoking."

## Available Design Skills (`.agents/skills/`)

15 个设计族技能按方向分组。Agent 接到 UI/UX / 视觉设计 / 前端重构类任务时,
按下方 **Selection Precedence** 确定性路由到唯一首选技能。

> **核心原则**: 任何设计任务只激活一个主技能。按优先级从高到低匹配, 命中即停。
> 同层内通过 `triggers` 关键词区分, 不允许同时加载两个同层技能。

| Tier | 技能 | 触发关键词 / 场景 | 互斥 |
|------|------|----------|------|
| 0 | `design-taste-frontend-v1` | **RETIRED** — 仅当用户**显式指名** "v1" 或项目 `package.json` 硬编码引用时才加载; 模糊请求一律路由到 v2 | 与 v2 互斥 |
| 1.1 | `design-taste-frontend` | 新建页面/组件 / landing / portfolio / 通用前端设计 | 与 v1 / high-end / gpt-taste / redesign 互斥 |
| 1.2 | `redesign-existing-projects` | 现有项目 UI 升级 / 重构/改造 / 审计去 AI 味 | 与 design-taste-frontend 互斥 |
| 1.3 | `ui-ux-pro-max` | 查询色板/字体/风格数据库 / 设计决策参考 / UX 审查 | 非独占, 可作为辅助参考层 |
| 2.a | `high-end-visual-design` | 高端/奢华/代理级/Awwwards/$150k | 与 gpt-taste / v2 互斥 |
| 2.b | `gpt-taste` | GSAP / ScrollTrigger / 编辑式宽排版 / AIDA / bento grid 动效 | 与 high-end / v2 互斥 |
| 2.c | `minimalist-ui` | 极简 / 编辑风 / 暖色单色 / 无渐变 / 扁平 | 与 industrial-brutalist-ui 互斥 |
| 2.d | `industrial-brutalist-ui` | 工业风 / 粗野主义 / 瑞士印刷 / 军事终端 / 数据密集仪表盘 | 与 minimalist-ui 互斥 |
| 3.a | `image-to-code` | 先生成设计图 → 再实现为代码（完整流程） | 与 imagegen-web 互斥 |
| 3.b | `imagegen-frontend-web` | 仅生成 Web 各 Section 设计参考图（不写代码） | 与 image-to-code 互斥 |
| 3.c | `imagegen-frontend-mobile` | 仅生成移动端屏幕概念图/Mockup（不写代码） | 与 imagegen-web 互斥 |
| 4.a | `brandkit` | 品牌指南 / Logo / Identity Deck / 视觉世界构建 | 独占 |
| 4.b | `beautify-github-readme` | GitHub README 视觉 / SVG / GIF / Hero 资产 | 独占, 仅 README 场景 |
| 4.c | `stitch-design-taste` | 生成 DESIGN.md 语义设计契约（Google Stitch 格式） | 独占, 仅设计系统文档生成 |
| E.1 | `full-output-enforcement` | 禁止截断/占位符，强制完整代码输出 | 工程辅助层 |
| E.2 | `leader` | 一句话想法 → Agent 可独立执行的目标任务书 | 工程辅助层 |
| E.3 | `vibehub` | Vibe Coding 术语学习 / 概念解释 / 边做边学 | 工程辅助层 |

**Tier 速查**: 0=退役隔离 / 1=默认路由 / 2=显式风格路由 / 3=图像生成专用 / 4=领域专用资产 / E=工程辅助。模糊请求命中 Tier 1.1 (design-taste-frontend)。

## Development Commands

### Backend (Python / FastAPI)

```bash
# Setup
pip install -r backend/requirements.txt

# Run (dev server)
python run.py                        # 默认 127.0.0.1:8000
# 或: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Test
python -m pytest backend/tests/ --tb=short -q

# Agent assets lint gate (warning/error 分离, error 阻断 CI; 见上文 *Agent Assets Lint Policy*)
python scripts/harness_analyze.py --check        # CI 同款: --format json + errors 非零 exit 1
python scripts/harness_analyze.py --format json  # JSON 输出 (脚本消费 / 报告归档)
python scripts/harness_analyze.py                # 本地预览, 人类可读
```

### Frontend (React / Vite / Tailwind)

```bash
# Setup
cd frontend && npm install

# Run (dev server, port 8898)
cd frontend && npm run dev

# Type-check + Test + Build
cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error
```

## Scoped AGENTS.md — Near-Context Index

> 代理进入高频源目录时,**根 AGENTS.md + 就近 scoped AGENTS.md 在两次加载内
> 即可定位 owner 与测试入口**,不再依赖命名约定或外部工具推断。
> 每个 scoped 文件只承载该子树的 always-needed 约束,不重复根级内容。

| 路径 | 何时加载 | 单一职责 |
|------|----------|----------|
| [`frontend/src/AGENTS.md`](frontend/src/AGENTS.md) | 进入 `frontend/src/` 任何 React/TS 文件 | 组件/hook/context 命名约束、Tailwind 优先、colocated test、Tailwind 配置需重启 dev server |
| [`backend/services/AGENTS.md`](backend/services/AGENTS.md) | 进入 `backend/services/` 任何 `*_service.py` 或 `triggers/` | 服务命名、依赖方向(禁 `import backend.api`)、ai_hub 唯一性、Feature Gate 守卫、generate_meta 同步 |
| [`backend/api/AGENTS.md`](backend/api/AGENTS.md) | 进入 `backend/api/` 任何路由文件 | 路由 ≤150 行、lazy import 协议、Feature Gate 注册、core 白名单防重叠断言 |
| [`scripts/AGENTS.md`](scripts/AGENTS.md) | 进入 `scripts/` 任何自动化脚本 | 审计/检查/清理/修复/生成 类别前缀、破坏性脚本 `--dry-run`、generate_meta `--check` 是 CI |

### 加载协议(避免重复加载)

1. 根 AGENTS.md 始终作为项目级入口与命令清单(本文) — 必读。
2. 进入 `frontend/src/` / `backend/services/` / `backend/api/` / `scripts/`
   **其中任一目录前**,先加载对应 scoped AGENTS.md(只读一次,不必每次返回重读)。
3. 不进入上述四个目录时,不要主动加载 scoped 文件(避免 token 浪费)。
4. `docs/AGENTS.md` 已退化为只读自动产物,不再承担跨项目路由职责。

## ZCode Hooks (workspace-level, 2026-09-02 起)

> **目的**: 跨事件注入 `additionalContext` 形式的备忘,镜像 CI 阻断门 + MEMORY.md 高频失误模式。
> **策略**: 全部 **warn-only**(exit 0/1),永不阻断 — 与 Mimosa `MIMOSA_HOOK_PROJECT=1` 模式一致。

- **配置源**: `.zcode/config.json`(`hooks.enabled: true`),事件 = `PreToolUse(Bash)` / `PostToolUse(Edit|Write|MultiEdit)` / `UserPromptSubmit` / `Stop`
- **Dispatcher**: `scripts/hook_runner.py` (单文件派发,≤250 行),通过子进程复用既有 CI 脚本 — **不 fork** `check_docstrings.py` / `harness_analyze.py` / `generate_meta.py`
- **Check 模块**: `scripts/hooks/bash_risk.py` (Bash 风险) + `scripts/hooks/post_edit_quality.py` (编辑后质量门)
- **状态日志**: `.zcode/hook-status/<sessionId>.json` (per-session 覆写, 0600, gitignored)
- **回滚**: 删除 `.zcode/config.json` 即关闭全部钩子(configuration hooks 默认禁用,一行回滚)
- **与现有钩子关系**: `.gemini/settings.json` / `.claude/settings.local.json` 里的 gortex 钩子独立 runner,**互不干扰**(schema 不同)

