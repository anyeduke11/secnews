# Security Policy

> **本仓库是单人本地工作站**，默认不对外提供网络服务，但作为公开开源仓库，仍应遵守负责任的漏洞披露流程。

## Supported Versions

| Version | Supported          | 备注 |
|---------|--------------------|------|
| v0.7.x  | :white_check_mark: | 当前活跃分支 — Sentinel Terminal |
| v0.6.x  | :white_check_mark: | 仅安全修复 |
| v0.5.x  | :x:                | EOL — 建议升级到 v0.7.0 |
| v0.4.x  | :x:                | EOL |
| < v0.4  | :x:                | EOL |

## Reporting a Vulnerability

**请勿在 GitHub Issues 公开披露安全漏洞** — 走私密渠道：

1. **首选**：在 GitHub 仓库页面右上角 `Security` → `Advisories` → `New draft security advisory`
2. **备选**：邮件到 `anyeduke11@users.noreply.github.com`（GitHub 隐私邮箱）

请包含：
- 受影响版本（commit SHA / tag / release zip）
- 复现步骤 / POC
- 潜在影响面（数据泄露 / RCE / 越权 / SSRF / …）
- 是否已自行修复或绕过方案

## Response Timeline

- **首响**（确认收到）：≤ 72 小时
- **修复发布**：视严重程度 7-30 天
- **公开披露**：修复后 ≥ 7 天，或与 reporter 协调后更早

## Scope

以下内容在 scope 内：
- 后端 FastAPI 路由层（[backend/api/](./backend/api)）
- 采集器（[backend/collectors/](./backend/collectors)）— 涉及 SSRF / 代理逃逸
- MCP Server（[backend/mcp_server/](./backend/mcp_server)）— 涉及外部 AI Agent 接入的信任边界
- 加密层（[backend/crypto.py](./backend/crypto.py)）— Fernet / 主密钥派生
- 同步系统（[backend/services/sync_*.py](./backend/services)）— 涉及跨设备 bundle 加解密

不在 scope 内：
- 单机 SQLite 数据库（物理文件访问不在 threat model 内）
- `llm-wiki-2.0/` 个人 wiki（属于用户私有数据）
- 文档 / SVG / 注释（无执行面）

## Disclosure Policy

- 我们接受 **coordinated disclosure**（修复后再公开）
- 不接受 **full disclosure**（修复前公开）— 这会让任何 fork 部署都暴露窗口期
- 不接受针对 EOL 版本的修复请求

## Security Tooling

CI 流水线已启用：
- :white_check_mark: Secret scanning（含 push protection）
- :white_check_mark: Dependabot security updates（`disabled`，手动 pip-audit 替代）
- :white_check_mark: weekly 全环境 `pip-audit`（见 commit history）
- 启用方法：[`.github/workflows/ci.yml`](./.github/workflows/ci.yml)

## Acknowledgements

公开致谢所有负责任披露安全问题的 reporter（贡献者名单随下次 release 更新）。

---

_Last updated: 2026-08-30 (v0.7.0)_