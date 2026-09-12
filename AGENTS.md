# SecNews Knowledge Dashboard — 安全从业者 AI 助手的平台看板层

> **当前状态 (2026-09-09, v0.8.5)**: v0.8 Sentinel 三层 (`/` 资料层 → `/judge` 判断层 → `/action` 行动层) 是**唯一壳** (SentinelShell + 管道心跳条全站常驻), v1.0 九领域对象/三类 receipt 只能以嵌入三层的能力区块进入 (SignalPanel/CaseQueuePanel/ExecOverviewPanel); v1 四入口 `/workbench` `/intel` `/cases` 仅为重定向兼容 (透传 query)。唯一权威 spec = `docs/v0.8.5/V0.8.5_PLAN.md` (§5 路由表 / §6 接口消费表 / §10 一致性门); 实现与验证分离, 实现侧不得自评 PASS。新能力只能以三层区块进入, 禁止新一级入口/新壳 (frontend/src/AGENTS.md 硬规则)。**2026-09-10 壳统一 (DEV-0168)**: 工具页 `PageLayout` 亦以 `<SentinelShell layer={null}>` 为壳 (顶部横向导航 + 更多菜单高亮当前页), 左侧 AppNav 物理删除, SK 能力包 / 知识管理能力归位 `/skill-store` `/knowledge` 页内; spec §5 已附修订注。dsh 为受管子进程, :3210 降级链 `not_configured→mock→ai_hub`, 新文档勿再写"独立网关"。
> 历史决策 (三层架构裁决 / wiki-first 存储哲学 / Phase 7 退役冻结 / v1.0 四入口弯路与回摆) 见 `PROJECT.md`、`PROGRESS.md`、`docs/README.md` 与 `git log`, 不在此重复。

## 文档地图

- 接手顺序: 本文件 → `PROJECT.md` → `PROGRESS.md` 活跃段
- **审计事实源**: `docs/CRITICAL_REVIEW_2026-09-03.md` (19 finding 逐项标 ✅/◐/❌) — 动手前先查对应项状态, 勿凭旧印象
- **ai_hub 红线**: 未裁决前勿动 ai_hub 调用链 (`gateway._try_order` / `service._resolve_provider`)
- 归档: 已交付版本族/一次性审计在 `docs/archived/` (2026-09-09 整理批 = `2026-09-09-sweep/`), 台账中的旧路径以归档目录同名文件为准
- **架构图**: `hotspot-architecture.html` + `hotspot-architecture.candidate.json` 已入仓 — **candidate.json 是唯一编辑入口**, HTML 由 `archify deliver` 生成不手改; 硬约束: viewBox 宽 ≤~1390 (context 字号 9px 上限 × 投影 ≥6px @1440) / 列距 ≥40px (26px 以下渲染器崩溃) / 副标签长度按盒宽预算 → **加节点必先删节点**; 复跑 archify 会覆盖入仓产物

## 架构数字门禁

架构数字由 `scripts/generate_meta.py` AST 反推维护 (57 jobs / 13 collectors / 86 routers / 132 services)。改动注册代码后必须同步 ARCHITECTURE.md: `python scripts/generate_meta.py` (CI 有 `--check`)。

## v0.4.3 — Core/Extension 软分层 + Feature Gates

- **开关源**: `backend/config/feature_gates.toml` — 13 gate: 默认开启 12 (codegarden / codegarden_phase2b / sync / tech_stack / security_graph / secnews / crm / dsh + v0.8 四 gate info_filter·skill_registry·trigger_gate·user_skills); 默认关闭 1 (mcp — extension gate 只管 /api/mcp/* 调试路由, server 本体由 is_mcp_enabled() 读 config.feature_mcp, 双开关契约见 mcp_config.py docstring)。gate 化须随消费点同时登记 (user_skills 先例)
- **core 永不消失**: `backend/core/routers.py` core router 白名单, 与扩展域防重叠断言; 扩展 router 按 `is_extension_enabled()` 条件注册 (关闭时路由 404)
- **job 门控**: `scheduler.py` `_is_job_enabled()` 按扩展归属过滤 8 个扩展 job
- **env 覆盖**: `HOTSPOT_FEATURE_GATES='{"extensions": {...}}'` 优先级高于 TOML (CI core-only 用)
- **测试约定**: conftest autouse fixture 测试环境全开 gates; 组合矩阵见 `backend/tests/test_feature_gates.py`
- 详细设计: [`docs/CodeGarden_PRD_v1.7.md`](docs/CodeGarden_PRD_v1.7.md) (CodeGarden 域唯一设计入口; cg_resources 端口保护 + Fernet 加密)

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

- **CI**: `.github/workflows/ci.yml` 的 `backend` job 追加 `python scripts/harness_analyze.py --check` 步骤, errors 非零 → job 失败; warnings 通过 reviewer 备注保留。
- **本地**: `python scripts/harness_analyze.py` (默认人类可读) 或 `--format json` (脚本消费)。CI 与本地两条路径均执行同一脚本同一规则, 避免声明与验证漂移。
- **豁免收紧**: 在 `scripts/harness_baseline.json` 删除某 skill 条目 = 立刻对该 skill 强制 ERROR (用于逐步清理历史债)。

## 安全扫描插件消歧 — `codex-security` vs `security-scan`

两条名称相似的安全插件为**并存 (complementary)** 关系, 不互为 rename/disable。触发关键词均含 "security scan", 按以下规则**首命中即停**路由:

1. 显式调用 `$codex-security:<skill>` 或声明 "Codex Security / OpenAI Codex security / Codex 安全工作流" → 走 `codex-security:*` 完整生命周期 (扫描+验证+攻击路径+追踪+修复+加固+报告)。
2. 显式调用 `/security-scan` / "Qoder 安全扫描 / L2 轻量 / L3 深度 / cloud scan / 扫描这个项目" → 走 Qoder `security-scan` 单技能三档。
3. Edit/Write 后未显式调用但 Qoder hooks 已自动触发 edit-time review → 由 `security-scan` 静默处理, **不**反向触发 `codex-security`。
4. "验证/追踪/修复 finding、攻击路径分析、漏洞 write-up、威胁建模、架构加固、SECURITY.md 政策" → **必须** `codex-security:*` (另一插件无对应子技能)。

```text
$codex-security:security-scan <path>     # 单遍扫+验证+攻击路径+报告
$codex-security:deep-security-scan <path> / :security-diff-scan <diff>
$codex-security:fix-finding <id> / :vulnerability-writeup <id>
/security-scan [--layer=l2|l3] [paths...]  # bare → picker
```

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

# dev 并行模式 (与生产后端共存时禁用本实例调度器, API 正常可用)
HOTSPOT_DISABLE_SCHEDULER=1 python run.py

# Test
python -m pytest backend/tests/ --tb=short -q

# Agent assets lint gate (warning/error 分离, error 阻断 CI)
python scripts/harness_analyze.py --check        # CI 同款
python scripts/harness_analyze.py                # 本地预览
```

### Frontend (React / Vite / Tailwind)

```bash
# Setup
cd frontend && npm install

# Run (dev server)
cd frontend && npm run dev

# Type-check + Test + Build
cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error
```

## Scoped AGENTS.md — Near-Context Index

> 代理进入高频源目录时, 根 AGENTS.md + 就近 scoped AGENTS.md 在两次加载内即可定位 owner 与测试入口。

| 路径 | 何时加载 | 单一职责 |
|------|----------|----------|
| [`frontend/src/AGENTS.md`](frontend/src/AGENTS.md) | 进入 `frontend/src/` 任何 React/TS 文件 | 组件/hook/context 命名约束、Tailwind 优先、colocated test、Tailwind 配置需重启 dev server |
| [`backend/services/AGENTS.md`](backend/services/AGENTS.md) | 进入 `backend/services/` 任何 `*_service.py` 或 `triggers/` | 服务命名、依赖方向(禁 `import backend.api`)、ai_hub 唯一性、Feature Gate 守卫、generate_meta 同步 |
| [`backend/api/AGENTS.md`](backend/api/AGENTS.md) | 进入 `backend/api/` 任何路由文件 | 路由 ≤150 行、lazy import 协议、Feature Gate 注册、core 白名单防重叠断言 |
| [`scripts/AGENTS.md`](scripts/AGENTS.md) | 进入 `scripts/` 任何自动化脚本 | 审计/检查/清理/修复/生成 类别前缀、破坏性脚本 `--dry-run`、generate_meta `--check` 是 CI |

加载协议: 根文件必读; 进入上表四目录前加载对应 scoped 文件 (只读一次); 不进入则不加载。`docs/AGENTS.md` 已退化为只读自动产物。

## ZCode Hooks (workspace-level, 2026-09-02 起)

> 跨事件注入 `additionalContext` 备忘, 镜像 CI 阻断门 + MEMORY.md 高频失误模式。全部 **warn-only**, 永不阻断。

- **配置源**: `.zcode/config.json`; 事件 = `PreToolUse(Bash)` / `PostToolUse(Edit|Write|MultiEdit)` / `UserPromptSubmit` / `Stop`
- **Dispatcher**: `scripts/hook_runner.py` (单文件派发, ≤250 行), 子进程复用既有 CI 脚本, 不 fork
- **Check 模块**: `scripts/hooks/bash_risk.py` + `scripts/hooks/post_edit_quality.py`
- **状态日志**: `.zcode/hook-status/<sessionId>.json` (0600, gitignored)
- **回滚**: 删除 `.zcode/config.json` 即全部关闭
- 与 `.gemini/settings.json` / `.claude/settings.local.json` 的 gortex 钩子独立 runner, 互不干扰
