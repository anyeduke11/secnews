# SECURITY_AUDIT.md — 安全扫描审计记录

> **状态 (2026-08-28, P2-4)**: ⏸️ **未启用** — Claude Code / DSH sandbox 中
> `codex-security` MCP 服务与 `Mimosa` 封闭扫描工具均不可用, 本文件作为
> 启用前的占位与 checklist. 启动后自动填充扫描结果.
> **2026-08-30 v0.6.3 安全批次**: 依赖风险维度完成清零 (§3.1), 代码级 SAST
> 三通道仍未接入 (§1), weekly 巡检补全环境 pip-audit (§3.2).

---

## 3.1 依赖漏洞清零 (2026-08-30, v0.6.3 安全批次)

pip-audit 实测 **148 包 / 0 漏洞**; npm audit **0 漏洞**。处置清单:

| 包 | 处置 | 依据 | 关闭的 CVE |
|---|---|---|---|
| cryptography 49.0.0 → **50.0.0** | venv 同步 lock (lock 已钉) | 加密面 (Fernet/主密钥/同步包) | CVE-2026-69247 |
| aiohttp 3.14.1 → **3.14.3** | venv 同步 lock | lock 已 prescribe | CVE-2026-69244/69243/59881 |
| lxml 5.4.0 → **6.1.1** | venv 同步 lock | lock 已 prescribe | GHSA-vfmq-68hx-4jfw |
| h2 4.3.0 → **4.4.1** | 直接升级 (lock 未收, transitive) | patch 级 | GHSA-6hr6-w5qg-qmwg |
| pip 26.1.2 → **26.2** | venv 升级 | 安装器 | CVE-2026-13346 |
| nltk 3.9.4 → **卸载** | 全仓零 `import nltk` + 未被任何 requirements/lock 声明 = 孤儿包, 根因清除而非升级 | — | 6 条 (CVE-2026-12061 等) |

全量 pytest **3032 passed / 6 skipped** (cryptography 50.0.0 下 Fernet 加解密/主密钥派生/secrets 全链路回归通过)。

### 教训

- **CI 的 `pip-audit -r requirements.lock` 只扫 75 个 lock pin**, 覆盖不到 venv 实际安装的 transitive/optional/孤儿包 (本次 nltk/h2/pip 即从该缝隙漏进) → weekly-m2-verify 已补"全环境"审计步 (§3.2)。
- lock 与 venv 曾漂移 (lock 已钉 50.0.0 而 venv 49.0.0): 升级后须 `.venv/bin/pip install -r backend/requirements.lock` 或对照 `pip list` 复核。

---

## 3.2 CI 周期复核 (2026-08-30 落地)

`weekly-m2-verify` job (周日 02:00 UTC) 新增 **"Dependency vulnerability audit (weekly, full env)"** 步:
全环境 pip-audit (非 lock-only), 沿用本 job 报告为主不阻断惯例 (新 CVE 披露不可控), 输出
`packages / vulnerable / total` 摘要 + 每条 CVE 与 fix 版本; 触发时按上方 §3.1 模式处置。

## 3.3 代码级 SAST 三通道现状 (截至 2026-08-30 仍全部未接入)

| 通道 | 阻塞点 | 解锁动作 (用户侧) |
|---|---|---|
| Mimosa 密封扫描 | MCP server 激活是宿主侧开关 (插件不覆盖宿主激活状态), 且 MCP 配置在任务启动时快照 | 在 ZCode 中启用 `mimosa` MCP server → **开新任务** → `/mimosa-deep-audit` |
| Qoder CodeSec (qoder 模式) | 需 Qoder IDE 环境标记 (`QODER_CLI=1` 等) | 在 Qoder IDE 内触发 `/security-scan` |
| Qoder CodeSec (hand 模式) | 需 `YUNDUN_CODESEC_OPENAPI_AK` + `YUNDUN_CODESEC_OPENAPI_SECRET` | 配置凭证后: `~/.qodersec/bin/qodersec scan --platform hand --all --fail-on none` |

依赖审计不能替代 SAST — 三通道任一接入后应跑一次全仓深度扫描并回填 §3 记录。

---

## 1. 工具链现状

| 工具 | 类型 | 入口 | 现状 |
|---|---|---|---|
| `codex-security` | MCP STDIO 服务 | `codex-security` (OpenAI 0.1.14) | ❌ 不可用 (sandbox 限制) |
| `security-scan` | Qoder PostToolUse Hook | `~/.qoder/plugins/cache/security-scan` (CodeSec 0.8.1) | ❌ 不可用 (同上) |
| `Mimosa` | 本地封闭扫描 | `mimosa` 命令 | ❌ 不可用 (同上) |
| `pip-audit` | Python 依赖审计 | `pip-audit` (CI step) | ✅ 已有 (CI `.github/workflows/ci.yml`) |
| `npm audit` | Node 依赖审计 | `npm audit` (CI step) | ✅ 已有 (CI 同上) |
| `ruff` | Python Lint | `ruff check backend/ scripts/` | ✅ 已有 |
| `tsc --noEmit` | TypeScript 类型检查 | frontend tsc | ✅ 已有 |

---

## 2. 启用 checklist (当 codex-security / Mimosa 可用时)

按顺序完成下列步骤, 每步完成后在 `## 3. 扫描记录` 加一条:

- [ ] **2.1** 安装 codex-security: `pip install openai-codex-security` 或 `npm i -g @openai/codex-security`
- [ ] **2.2** 配置 codex-security MCP server: `~/.codex/mcp_servers/codex-security.json`
- [ ] **2.3** 在 `.github/workflows/ci.yml` `backend` job 加 `codex-security --workspace-scan` 步骤
- [ ] **2.4** 在 `.github/workflows/ci.yml` 失败时自动 append 到 `docs/SECURITY_AUDIT.md` §3
- [ ] **2.5** 安装 Mimosa 封闭扫描: `pip install mimosa-scanner`
- [ ] **2.6** 配置 cron 每周日 03:00 跑 Mimosa full scan, 结果落 `## 3`
- [ ] **2.7** 修复或标记 accepted 所有 high/critical findings
- [ ] **2.8** 更新 CLAUDE.md "Mimosa 密封扫描未跑" 行, 改为 "Mimosa 扫描已启用, 详见 SECURITY_AUDIT.md"

---

## 3. 扫描记录

> 格式: `<日期> · <工具> · <commit SHA> · <finding 数 (critical/high/medium/low)> · <备注>`

(暂无 — 等待 codex-security / Mimosa 启用后填充)

---

## 4. 已知安全姿态 (静态审计)

即使无自动扫描, 下列安全姿态已在 v0.6.2 落地:

- **Fernet 加密** (PBKDF2 600k 迭代 + 16B 随机 salt): `cg_resources.webdav_password_encrypted` / `sync_*` 加密列 / `llm_api_key_encrypted` / `master_key` / `qrcode` 验签
- **DSH 桥接层** 默认关闭 (P1-2 降级, 需 DSH_ENDPOINT 才启用)
- **workbench_legacy gate** (P2-3 新增) — 关闭后 16 个三层目录路由 404
- **mcp gate** 默认关闭 — 9+5 个 MCP 工具外部 Agent 不可见
- **Mimosa 扫描** — 不可用 (本文件存在即承认此事实)
- **无 multi-user auth** (产品定位: 单人本地工作站)
- **WORKERS=1** (SQLite WAL 单写者约束)
- **DRAFT 文档校验** (`scripts/generate_meta.py --drafts-only`) — 防止规划文档被遗忘

---

## 5. 故障排查 (启用后)

| 症状 | 可能原因 | 解决 |
|---|---|---|
| CI 加 codex-security 后失败: `command not found` | MCP binary 未安装 | 回到 2.1 重装 |
| Mimosa full scan 报 `permission denied` | 加密文件 cold.db 未解密 | `python scripts/cold_db_crypto.py decrypt` |
| high/critical finding 累积 | 误报 | 用 `.security-audit-baseline.json` 标记 accepted |
