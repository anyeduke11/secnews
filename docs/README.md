# docs/ 导读

> 读者 = 第一次接触本仓库的人（人类同事 / 接手 AI）。5 分钟看完本页即可定位所需文档。
> 项目接手顺序：根目录 `AGENTS.md` → `PROJECT.md` → `PROGRESS.md` 活跃段（本页不替代，只做 docs/ 的地图）。

## 当前权威（active）

| 文档 | 职责 |
|---|---|
| `v0.8.5/V0.8.5_PLAN.md` | **唯一权威 spec**：路由表 §5 / 接口消费表 §6 / 一致性门 §10 |
| `v0.8.5/ACCEPTANCE.md` | v0.8.5 验收矩阵（真实证据） |
| `ARCHITECTURE.md` | 现状架构导览（数字经 `generate_meta.py --check` 门禁） |
| `CRITICAL_REVIEW_2026-09-03.md` | 审计事实源（19 finding 逐项状态，动手前先查） |
| `CHANGELOG.md` | 版本交付流水（时序真相） |
| `RUNBOOK.md` / `ADMIN_MANUAL.md` | 运维手册 / 管理员手册 |
| `PORT_SPEC.md` | hotspot → dsh-SecNews 移植对照表（跨仓库读者） |
| `CodeGarden_PRD_v1.7.md` | CodeGarden 域当前 PRD（feature gate `codegarden*`） |
| `Observability_PRD_v1.0.md` | 可观测性 PRD（Batch 1+2 已交付，③④⑤ 排期中） |
| `SECURITY_KNOWLEDGE_GRAPH{,_PRD,_DEV_PLAN}.md` | 安全图谱域（feature gate `security_graph`） |
| `V0.8_SKILLS.md` / `V0.8_USER_GUIDE.md` | Skills 双轨体系 / 用户指南 |
| `DESIGN_SYSTEM.md` / `DESIGN_GUIDE.md` / `DIAGRAMS.md` | 设计契约 / 设计规范 / 图表集 |
| `v1.0/contracts.md` | v1.0 九领域对象契约（§5 状态机 / §6.4 幂等 / receipt，v0.8.5 能力区块的底层契约） |
| `quality_gates.md` / `llm_config.md` / `mcp_integration.md` / `mcp_tools_schema.json` | 质量门禁 / LLM 配置 / MCP 集成参考 |
| `code-wiki/` | 代码 Wiki（5 分章 + V0.8.1 版） |

## 版本目录（快照，不再更新）

- `v0.8.5/` — 反向收敛 demo（进行中的当前版本）
- `v1.0/` — v1.0 任务制交付台账（closeout/review/任务状态；UI 四入口路线已被 v0.8.5 裁决取代，见各文件横幅）

## 归档（archived/）

`archived/` = 已交付版本的计划/PRD/审计 + 被后续裁决取代的方案。**只读参考，不再维护**；引用它们的活跃文档均已改指本目录。

- `2026-09-09-sweep/` — 全仓整理批归档（49 项）：v0.4/v0.5/v1.7/爬虫 v2/CodeGarden v1.0 等已交付版本族、Phase 8 验收等一次性审计、被 v0.8.5 裁决取代的 v1.0 四入口 PRD 族、v1.4 时代 `superpowers/`、过期 HTML 产物
- 其余更早归档（v0.5/v0.6 计划分片、旧 ACCEPTANCE/AGENTS 等）

## 台账（root，不在 docs/）

- `PROGRESS.md` / `DEV_LOG.md` / `CHECK_LOG.md` — 执行/开发/检查台账（只追加）
- 历史文档若在台账中出现旧路径，以 `archived/2026-09-09-sweep/` 内同名文件为准
