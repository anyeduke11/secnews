# PRD 对齐审计 — 2026-11-19 四域整体删除

> **依据**: owner 2026-11-19 裁决（工坊 CodeGarden / 技能库 skills / 密钥 secrets / 跨端同步 sync **四域整体删除**）
> **权威 PRD**: [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](../HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md)（增「阅读前提：2026-11-19 四域整体删除裁决」）
> **日期**: 2026-11-19 ｜ **阶段**: d5（代码删除已先行，本阶段文档回写收口）｜ **版本**: 0.8.9 不变（不升版本）
> **性质**: 删除型变更的 PRD 对齐留痕 + 证据索引; 实现与验证分离, 本文不承担 d6 门禁结论

---

## 0. 决策来源

- **裁决主体 / 时间**: owner, 2026-11-19
- **裁决口径**: 四域**整体删除**（非冻结、非降级、非 410）。前端页面与路由、后端 router/service/repo、feature gate、数据库表、技能域内部运行时全量移除。
- **产品理由**: 四域均不参与「资讯 → Signal → Case → Claim → Run → Artifact → Knowledge」主干流量; 技能域内部运行时（trigger/worker/loop/playbook）长期无真实消费面, 且构成密钥 vault 与跨端同步的耦合源。删除后 ai_hub 密钥解析收敛为 **env-only**, 主链单出口更薄。
- **壳不变**: SentinelShell 四菜单（`/` `/knowledge` `/action` `/settings`）仍是唯一壳; v1 九领域对象 / 三类 receipt 只能以嵌入区块进入。

## 1. 影响范围（删除 / 改造 / 数据）

### 1.1 删除

| 层 | 内容 |
|---|---|
| 前端 | `frontend/src/components/{codegarden,secrets,skills,sync}/` 四目录、对应页面与路由、api 客户端（共 94 文件）; `/garden` 仅保留重定向到 `/action` |
| 后端 services | `skill_registry` / `skill_runner` / `skill_eval` / `skill_builder` / `trigger_gate` / `playbook_engine` / `agent_loop` / `agent_memory` / `worker_coordinator` / `legacy_hold_service` / `sync_service` / `sync_bundle` / `sync_merge` / `codegarden_*` / `secrets_service` |
| 后端 repository | `secrets_repo` / `codegarden_repo` / `encryption_keys_repo` |
| 后端 api | 四域路由文件（codegarden / codegarden_ops / skills 系 / secrets / sync 系） |
| 调度 | `backend/scheduler/jobs/worker_pump.py`（worker pump / legacy hold reap job） |
| feature gate | `codegarden` / `codegarden_phase2b` / `sync` / `skill_registry` 四键删除; 连带技能域 `trigger_gate` / `user_skills` 共退役 6 键 → gate 总数 **16 → 10**（默认开 9 + mcp 默认关 1） |
| 端点 | content publish 流退役（skill 驱动）; `/api/tech-stack/impact`、`/api/digests/priority` 删除; MCP `trigger-codegarden-drift` 删除 |

### 1.2 改造

- **ai_hub 密钥解析 → env-only**: env 主名 > 别名 > 无, fail-soft 不抛, 无 secrets vault 回退。
- **告警 SMTP 凭据**: 改用环境变量 `HOTSPOT_ALERT_SMTP_PASSWORD`（`backend/services/alert_channels.py`）。
- **执行链工作区根**: `codegarden/` → `workspace/`（agent_bridge / execution_plan/enforcer / 演练脚本 `p4-drill` `p5-drill` `p6-drill` / `.gitignore`）。

### 1.3 数据

- 新增 `backend/repository/migrations/137_drop_four_domains.sql`（**append-only**: 历史 SQL 文件不删, 只追加销毁迁移）:
  - 工坊 9 表（`cg_*`）
  - 技能库 4 表（`knowledge_skill_config` / `user_skills` / `skill_runs` / `skills`）
  - 密钥 3 表（`secret_access_logs` / `llm_secrets` / `encryption_keys`）
  - 同步 3 表（`sync_history` / `sync_states` / `sync_configs`）
  - 内部运行时孤儿 8 表（`dead_letter` / `worker_runs` / `loop_checkpoints` / `feedback_log` / `agent_preferences` / `playbook_runs` / `playbook_schedules` / `trigger_tickets`）
- 迁移文件累计 **134 个**（001-137, 066-069 为历史空洞）。

## 2. PRD 已改章节清单

权威 PRD 本次新增 / 回写以下章节（**PRD 为唯一权威, 本文不重复其正文**）:

| 章节 | 回写内容要点 |
|---|---|
| §阅读前提：2026-11-19 四域整体删除裁决 | 裁决范围、密钥 env-only、137 销毁迁移、`workspace/` 根切换、壳不变、文档效力声明 |
| §1.1 一句话定位 | 去除四域能力表述, 定位收敛为主干证据链 + 四菜单 |
| §3.2 功能清单 | 删除工坊 / 技能库 / 密钥库 / 同步四类功能区 |
| §3.4 设置页能力 | 同步 / 密钥保险箱 / Skill registry 面板退出功能清单 |
| §4.3 外部依赖 | 去除 secrets vault 与同步传输（WebDAV）依赖 |
| §5.2 ~~CodeGarden 安全实践域~~ | 标记已废止（4 期规划作废） |
| §6.1 后端 | routers 99 → 88、services 155 → 138、jobs 56 → 48、gate 16 → 10 |
| §6.2 前端 | 组件 239 + 66 测试 / 17 组件域; 四目录移除 |
| §6.3 数据 | 137 销毁迁移 + 表数变化 + 迁移文件 134 个 |

## 3. 代码与迁移证据路径

| 证据 | 路径 |
|---|---|
| 销毁迁移 | `backend/repository/migrations/137_drop_four_domains.sql` |
| gate 配置文件 | `backend/config/feature_gates.toml`（现存 10 键） |
| 密钥 env-only 改造点 | `backend/services/ai_hub/*`（密钥解析）; `backend/services/alert_channels.py`（SMTP） |
| 执行链新根 | `workspace/`（`p4-drill` / `p5-drill` / `p6-drill` 演练脚本保留） |
| 架构数字权威 | `python scripts/generate_meta.py --check`（48 / 19 / 88 / 138） |
| 版本注释 | `backend/version.py`（v0.8.0 Phase A/B/C 段加注「已于 2026-11-19 随技能域退役」，版本号仍 0.8.9） |
| 删除事实源 | `git status` 中四域源文件为 `D`（deleted）; 对应 `__pycache__` 空壳目录残留为未跟踪产物 |

## 4. 门禁执行方式（不在此自评 PASS）

- **d6 门禁清单**: `pytest backend/tests/`（全量）+ `npx tsc --noEmit` + `npx vitest run` + `npx vite build` + `python scripts/generate_meta.py --check` + `python scripts/harness_analyze.py --check` + `ruff check backend/`
- **判定纪律**: 实现与验证分离, 门禁结论以 d6 实际执行结果为准; 本审计只登记「待执行清单」与「执行入口」, 不写 PASS。
- **架构数字门禁**: `generate_meta.py --check` 为 CI 阻断项, 数字已由 `--fix` 置位（48 jobs / 19 collectors / 88 routers / 138 services）; 后续任何注册代码改动必须复跑。

## 5. 遗留项（显式声明）

1. **前端 `/settings` 残留面板清理待完成** — 设置域内同步 / 密钥保险箱 / Skill registry 等面板的入口与文案需在后续批次清零（本轮仅删除组件目录与路由, 设置域字符串与占位面板尚未逐项清理）。
2. **`backend/services/<已删域>/__pycache__` 空壳目录** — 源文件已删除（git 记录为 `D`）, 仅 Python 字节码缓存残留在工作区, 未跟踪; 无需入仓清理, 重启/清理缓存即消失。
3. **历史文档降级** — `docs/CodeGarden_PRD_v1.7.md` / `V0.8_SKILLS.md` 已降为历史档案（已在 CLAUDE.md 标注）, 尚未加 `# 已废止` 横幅（后续按单一权威 PRD 纪律处理）。