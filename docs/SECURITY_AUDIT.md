# SECURITY_AUDIT.md — 安全扫描审计记录

> **状态 (2026-08-28, P2-4)**: ⏸️ **未启用** — Claude Code / DSH sandbox 中
> `codex-security` MCP 服务与 `Mimosa` 封闭扫描工具均不可用, 本文件作为
> 启用前的占位与 checklist. 启动后自动填充扫描结果.

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
