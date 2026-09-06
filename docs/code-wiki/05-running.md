# 05 — 运行与开发指南

> 基准: **v0.7.x** (2026-09-03)。

## 1. 前置要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 代码用 `tomllib` (3.11 标准库); 建议用 `.venv` |
| Node.js | 18+ | 前端构建 |
| SQLite | 内置 | WAL 模式, 无独立服务 |
| 代理 (可选) | `127.0.0.1:7897` | security / github 采集与 git push 直连超时时使用 |

## 2. 安装

```bash
# 后端
pip install -r backend/requirements.txt          # 开发可加 -r backend/requirements-dev.txt

# 前端
cd frontend && npm install
```

**代理配置 (采集器必需)**: `backend/proxy_config.json` 在 `.gitignore` 中, 首次安装需自配
(最小配置示例见 `README.md`)。标讯抓取策略: 先 HTTP 直连, 失败再走代理 `127.0.0.1:7897`。

## 3. 启动

### 3.1 后端

```bash
python run.py                                    # 默认 127.0.0.1:8000
# 等价: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

HOTSPOT_PORT=8999 python run.py                  # 自定义端口
HOTSPOT_HOST=0.0.0.0 python run.py               # 局域网访问 (无认证, 慎用)
```

- `WORKERS` 固定 1 (SQLite WAL 锁竞争)
- 启动后自动: 迁移 → 缓存预热 → 调度器 (5s 后首跑采集) → knowledge watchdog →
  自动追抓本周一 00:00 以来的资讯
- 健康检查: `GET /api/health` (含 scheduler 状态与 APP_VERSION 0.7.0)

### 3.2 前端

```bash
cd frontend && npm run dev                       # http://localhost:8898 → 哨兵终端首页
```

端口 8898 **严格绑定** (`--strictPort`), 被占用直接报错 (禁止自动漂移);
`/api` 经 vite 代理到 `127.0.0.1:8000`。
**v0.7.x 首页行为**: `/` 直达**哨兵终端全屏页** (v0.7.1 起; v0.7.0 的 `/workbench` 报纸版已退役,
`/editorial` 仅重定向到 `/`)。设置入口统一为 `/settings?cat=pipeline|image_models|sentinel`
(SettingsHub, 原 3 处孤页永久 redirect)。

### 3.3 MCP stdio (外部 Agent 接入, 需先开 mcp gate)

```bash
python -m backend.mcp_stdio_main
```

SSE 通道随主服务启动 (`/mcp/sse`, 受 `mcp` feature gate 控制, 默认关)。

### 3.4 UI demo 静态服务器 (可选)

```bash
python3 -m http.server 8899 -d .ui-preview       # secnews-v4.html 真实数据 demo
```

后端 CORS 白名单已含 8899, demo 页可直接拉 `:8000` 实时数据。

## 4. 配置体系

| 配置 | 位置 | 用途 |
|------|------|------|
| 环境变量 | 前缀 `HOTSPOT_` (`backend/config.py`) | host/port/采集间隔/watchdog/catchup/feature_* (含 feature_workbench_ui) |
| Feature gates | `backend/config/feature_gates.toml` | 扩展开关单一来源; env `HOTSPOT_FEATURE_GATES` (JSON) 可覆盖 |
| LLM | `config/llm.yaml` + `backend/config/llm_schema.py` | provider / fallback_order (v0.5.1 起单一来源) |
| 质量门禁 | settings 表 (`quality.strict_mode` / `quality.min_score` / `quality.llm_*`) | DB 覆盖优先于代码默认 |
| 代理 | `backend/proxy_config.json` (gitignore) | 采集代理 |
| 管线 | `config/pipeline.json` + `pipeline.schema.json` | 管线运行时配置 |
| DSH | `DSH_ENDPOINT` 环境变量 (默认 `http://localhost:3210`) | DSH 桥接 (gate dsh 默认关) |

## 5. 测试

```bash
# 后端 (v0.7.4 验收快照 ~3234 passed / 2 failed 为 codegarden 端口预存, 与功能无关)
python -m pytest backend/tests/ --tb=short -q
.venv/bin/python3 -m pytest backend/tests/test_sync_merge.py -v   # 单文件
.venv/bin/python3 -m pytest backend/tests/ -k "merge"             # 关键字
.venv/bin/python3 -m py_compile backend/services/ai_hub/gateway.py  # 编译检查

# 前端 (~370+ passed, tsc 0 errors)
cd frontend && npx tsc --noEmit && npx vitest run && npx vite build --logLevel error

# 架构数字一致性 (改注册代码后必跑; 当前验收口径 51 jobs / 14 collectors / 68 routers / 105 services)
python scripts/generate_meta.py               # 重写 docs/ARCHITECTURE.md
python scripts/generate_meta.py --check       # CI 同款校验

# Agent 资产 lint (error 阻断 CI)
python scripts/harness_analyze.py             # 人类可读
python scripts/harness_analyze.py --check     # CI 同款

# 路径分类 (core vs non-core)
python scripts/generate_meta.py --classify backend/services/ai_hub.py
git diff --name-only origin/main | python scripts/generate_meta.py --classify --batch --json
```

注意: 跨 suite 偶发失败可能是既有测试隔离脆弱性 (线程本地连接复用), 隔离运行可通过
即非当前改动引入。

## 6. CI 门禁 (`.github/workflows/ci.yml`)

| 门 | 内容 |
|----|------|
| 后端 | Python 编译 + pytest + ruff + pip-audit + 启动冒烟 |
| 前端 | tsc + vitest + vite build |
| 架构一致性 | `generate_meta.py --check` (router/service/job/collector 数字与 ARCHITECTURE.md 一致) |
| Agent 资产 | `harness_analyze.py --check` (长 skill >500 行必须有 `references/`) |
| core 分流 | 仅 PR: `--classify --batch` 输出 `has_core`/`tier`; core 变更必跑全量门 + feature gates 全开/全闭矩阵 |
| 路由契约 | 前端新增 `<Route>` 必须登记 `frontend/src/routes/ROUTE_REGISTRY.md` |

## 7. 常用运维 API

| 端点 | 用途 |
|------|------|
| `GET /api/health` | 健康 + scheduler 状态 + 版本 |
| `POST /api/refresh` | 手动触发一轮采集 |
| `POST /api/catchup` | 手动追抓 (per-source checkpoint 断点续抓) |
| `POST /api/maintenance/cleanup-quality-logs?days=2` | 质量日志归档 |
| `GET /api/cache/*` / `POST /api/cache/clear` | 缓存统计/清理 |
| `GET /api/events` | SSE 实时事件流 |
| `GET /api/settings/features` | feature flags (前端 useFeatureFlags 数据源; 可验证 workbench_ui) |
| `GET /api/kl/metrics` | KL 触发器指标 |
| `GET /api/llm/status` | LLM provider 状态 |

日常维护 job 已调度化: 每日 04:30 SQLite 在线备份 (保留 7 份)、周日 05:00 遥测窗口清理、
`maintenance_service` (vacuum/cleanup)。

## 8. 开发约定 (速查)

- **Scoped AGENTS.md**: 进入 `frontend/src/` / `backend/services/` / `backend/api/` /
  `scripts/` 前先读对应子树的 AGENTS.md (只读一次)
- 路由文件 ≤ 150 行 (注册表 `_registry.py` 除外); 服务层禁止 `import backend.api`;
  router 禁止 import collectors/repository (DB 必须经 service)
- `api/__init__.py` 保持薄壳 (≤30 行), 注册逻辑进 `_registry.py`, 全部 lazy import
- 新建核心模块 (`backend/foo/`) → 同步 `core.include`; 新建测试目录 → `core.exclude`
- 改注册代码 (router/job/collector/service 增删) → 必跑 `python scripts/generate_meta.py`
- 新 collector: 遵循 Phase 13 硬约束不实现 `_fallback()`; 需导出到
  `backend/collectors/__init__.py`; `item_builder.py` 支持可读 ID 透传
- feature flag 命名用单数形式 (`feature_tag` 而非 `feature_tags`)
- 前端组件测试 colocated; 图表统一用 echarts (已移除 recharts)
- Commit 前: 禁止提交敏感信息 (proxy_config.json / .env / 密钥) 到远程

## 9. 首页演进 (v0.7.0 → v0.7.1 → v0.7.x) 与回退

### 9.1 演进时间线 (首页变化是发版预期行为, 不是故障)

| 版本 | 首页 | 说明 |
|------|------|------|
| ≤ v0.6.3 | 三层架构 / 工作台 | 旧 data/judge/action 三层 + workbench 灰度 |
| **v0.7.0** | **报纸版工作台** | commit `370a970b` (灰度) + `795189ca` (发版): 物理删除 23 个 .tsx 与 22 个老路由; `workbench_legacy` gate 退役; `/` → `/workbench`; `APP_VERSION="0.7.0"` |
| **v0.7.1** | **哨兵终端全屏页** | V2 设计稿还原: `/` `/judge` `/judge/graph` `/action` `/garden` 独立全屏 (不走 PageLayout); 报纸版 EditorialView 退役 (仅 `/editorial` → `/` 重定向); `*` fallback → `/` |
| **v0.7.x** | 设置 = SettingsHub | `/secnews/settings` `/secnews/image` `/sentinel/settings` → `/settings?cat=pipeline\|image_models\|sentinel`, 永久 redirect 保留外部书签 |

决策与验收记录: `PROGRESS.md` §2026-08-28、`docs/CHANGELOG.md` v0.7.0 段、
`docs/v0.7_migration_checklist.md` (v0.7.0 的 22 路由功能对照表)。

### 9.2 若需要更早的首页

旧 UI 已物理删除 (非 gate 开关), 回退方式是 git 历史版本:

```bash
# 方案 A: 整体回退到 v0.7 之前 (放弃 v0.6.2~v0.7.0 全部变更)
git revert 795189ca 370a970b          # 生成反向 commit (推荐, 保留历史)

# 方案 B: 只想要灰度期行为 — 回退 v0.7.0 发版步:
git revert 795189ca
```

不建议 `git reset --hard` (破坏性)。若只是想临时查看旧版, 可 `git checkout 82ed0189`
(v0.7 Step 1 前) 起一套 detached dev server。**哨兵首页 (v0.7.1+) 无独立 gate**, 回退只能走代码。
每次首页类变更后, 请同步更新本表与 `docs/code-wiki/` (行为文档无人肉门禁, 见 01 §9 债-5)。

### 9.3 功能去向对照 (当前 v0.7.x)

| 想找的旧功能 | 现在去处 |
|--------------|----------|
| `/data` 资料层浏览 | `/secnews/feed` (信息流, `?category=` 筛选) |
| `/judge/quality` 质量流 | `/secnews/pipeline` 或 `/quality/rejection` |
| `/judge/trends` 趋势 / CVE | `/secnews/analytics` (CVE 热力图 + ATT&CK) |
| 知识简报/扫描/告警 | `/secnews/feed` (DigestCard 简报) · `/secnews/pipeline` (告警) · 哨兵 `/judge` |
| `/knowledge/briefing` 简报 | `/secnews/feed` |
| `/knowledge/outbox` 整理 | `/knowledge/process` |
| `/workbench/*` (报纸版) | 已退役: `/editorial` → 重定向到哨兵首页 `/` |
| `/action/*` 行动层各页 | `/todos` `/skills` `/report` 独立保留 + 哨兵 `/action` |
| `/secnews/settings` `/secnews/image` `/sentinel/settings` | `/settings?cat=pipeline\|image_models\|sentinel` (SettingsHub) |

完整对照: `docs/v0.7_migration_checklist.md`。

## 10. 已知注意事项 (运维 gotchas)

- 列表排序一律 `ingested_at DESC`, 不是 `published_at`
- 同步包文件名必须 ASCII; 严禁中文 (坚果云 WebDAV quirk)
- 前端端口 8898 被占用时直接报错, 不要改端口绕过
- `046_v1.7_lifecycle.sql` 需手动先行迁移 (旧 3 阶段 → kl: 5 阶段)
- 推送 GitHub 直连超时可走代理 `127.0.0.1:7897`; 远程地址
  `https://github.com/anyeduke11/secnews.git`
- 测试环境必须 `HOTSPOT_CATCHUP_ON_STARTUP=false`, 否则启动即触发追抓
- pytest 有 2 个 codegarden 端口相关**预存失败** (v0.7 验收记录在案, 非回归)
- **crawl4ai 渲染是可选依赖** (`backend/requirements-optional.txt`: `crawl4ai>=0.8.9` +
  `playwright>=1.40`): 不安装则 `renderer="crawl4ai"` 的源 (新浪/东财/GitHub Trending, 36kr/雪球等)
  静默退化裸 aiohttp (不会崩); 测试环境 conftest 把配置指到 disabled YAML, 不拉起浏览器
- crawler-aihub-gateway 两步整合: 第 1 步 (YAML 单一开关) **已落地**,
  第 2 步 (LLM 提取走 ai_hub OpenAI-compatible 网关) **未实施** —
  启用 crawl4ai `LLMExtractionStrategy` 前必须先补网关, 否则绕过 ai_hub egress/观测红线
- `/api/image/*` (v0.7.4-image) 后端面保留, 前端仅 `/settings?cat=image_models` 三场景模型配置消费;
  属潜在 dead surface (01 §9 债-4)
