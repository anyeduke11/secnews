# Contributing to SecNews

感谢你考虑为 SecNews 贡献。本仓库是单人本地工作站，但欢迎以负责任的方式参与。

## 快速导航

- [README.md](./README.md) — 产品定位 + 快速开始
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 架构详解（数字由 `scripts/generate_meta.py` AST 反推维护）
- [docs/RUNBOOK.md](./docs/RUNBOOK.md) — 运维手册
- [docs/ADMIN_MANUAL.md](./docs/ADMIN_MANUAL.md) — 管理员手册
- [AGENTS.md](./AGENTS.md) / [CLAUDE.md](./CLAUDE.md) — 开发者约定（必读）

## 环境要求

- Python 3.11+ / Node 18+
- SQLite（内置，无需安装）
- 代理（可选）：采集外网源时需 `backend/proxy_config.json`，见 [backend/proxy_config.example.json](./backend/proxy_config.example.json)

## 本地开发

```bash
# 后端
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python run.py                        # http://127.0.0.1:8000

# 前端（端口 8898）
cd frontend && npm install && npm run dev   # http://localhost:8898
```

## 测试

```bash
# 后端（3025 用例）
.venv/bin/python3 -m pytest backend/tests/ --tb=short -q

# 前端（309 用例）
cd frontend && npx tsc --noEmit && npx vitest run
```

## 提交前检查

- [ ] `python scripts/generate_meta.py --check`（改动注册代码后必跑，CI 强约束）
- [ ] `python scripts/harness_analyze.py --check`（改动 `.agents/skills/` 后必跑）
- [ ] 后端 pytest 全绿；前端 tsc + vitest 全绿
- [ ] 新增代码不引入 `backend/api/` 循环 import（lazy import 协议）
- [ ] 不改动 `core.include` / `core.exclude` 除非有意（见 [AGENTS.md](./AGENTS.md) 分类门）
- [ ] 不提交敏感信息（`.env` / `proxy_config.json` / `*.db` 均已 gitignore，勿 `git add -f`）

## Commit 规范

参考 [docs/CHANGELOG.md](./docs/CHANGELOG.md) 既有风格，使用 conventional commits：

```
feat(scope): 描述
fix(scope): 描述
chore(scope): 描述
docs(scope): 描述
```

## Pull Request 流程

1. Fork 仓库或开分支
2. 提交满足上述检查的改动
3. 在 PR 描述中说明：改动动机、影响面（core / non-core）、测试结果
4. CI 会跑：Python compile + pytest + tsc + vitest + vite build + `generate_meta.py --check` + `harness_analyze.py --check`

> 安全漏洞请走 [SECURITY.md](./SECURITY.md) 的私密渠道，**不要**在 Issue/PR 中公开。

## 分支 / Release 哲学

- `main` 始终可部署
- 版本遵循 semver 近似（v0.x 为预发布期，破坏性变更仅在 minor 中发生）
- 历史版本源码以 GitHub Release zip 归档，勿在 repo 中堆积二进制

_Last updated: 2026-08-30 (v0.7.0)_