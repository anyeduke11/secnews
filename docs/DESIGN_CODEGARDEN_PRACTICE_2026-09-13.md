# 已废止（superseded）

> **本文档已被取代**：权威产品文档 = [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](../HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md)；0.8.6 版本族详细文档 = [`docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`](../HOTSPOT_V0.8.6_AI_NATIVE_PRD.md)。本文仅作历史设计留痕，**不作为当前事实源**（取代依据见权威 PRD 头部「取代」名单 + `docs/audit/PRD_ALIGNMENT_AUDIT_2026-10-02.md`）。

---

# CodeGarden 转型设计 — 安全实践域（已批准 · 含全量识别修订）

- 日期：2026-09-13（v2 修订）
- 状态：**已批准（owner 2026-09-13 复议）** — 修订点：**S1 资讯信号提取改为对全部资讯进行识别**（不限安全域）；其余内容复议无异议。分期实施待排期
- 定位：CodeGarden 从"项目生命周期管理"（休眠，全 0 数据）转型为**安全实践域**——行动侧的"练武场"：从资讯流发现开源工具/项目 → 立项研究 → 上手实践 → 产出可沉淀的经验

---

## 1. 转型逻辑（为什么这个定位成立）

现有资产盘点（转型不是从零开始）：

| 既有能力 | 转型后的角色 |
|---|---|
| 资讯流 9,872 条 + 兴趣引擎 | **实践选题的来源**：全量资讯中提取开源项目信号（见 S1 修订） |
| `POST /api/codegarden/projects/from-knowledge`（已存在） | 选题→立项的现成桥 |
| cg_projects / stages / activities / links | 实践项目容器：research→setup→exercise→retro 四阶段 |
| cg_dependencies / cg_events | 工具链依赖与实验事件记录 |
| playbook_engine / skill（休眠中） | 实践任务编排执行体（与 P1-0 执行器衔接） |
| Action/Run/Artifact（v1 行动层） | 实践任务作为一类 Action 走"审批→执行→产物"链 |

**闭环**：资讯（任意域的开源项目信号）→ 选题入库 → 立项实践 → 上手跑通 → 产出笔记/脚本/复现环境（Artifact）→ 沉淀知识（Knowledge）→ 反哺判断力。

## 2. 四个核心场景

### S1 开源项目信号提取（选题来源）★ owner 修订：全量资讯识别

- **做什么**：对**全部资讯**（hotspots 全量，不限 category——ai/tech/security 都可能埋着值得实践的开源项目，如 AI 辅助安全工具常出现在 ai 域）做开源项目信号识别：GitHub 链接（`github.com/<org>/<repo>` 正则）、项目/工具命名模式、release/版本发布语义；生成"实践候选池"
- **识别管线**：规则先行（零 LLM 成本，存量 9,872 条一次跑完）→ 候选池内再做实践域分类与兴趣加权排序（分类发生在候选层，不在来源层过滤）
- **落地位置**：`auto_classifier` 增加 practice 信号维度（与既有二级打标同构）+ 候选池聚合查询 1 端点；不动采集链
- **与 mitre 设计的衔接**：候选项目可打 ATT&CK 战术覆盖标签（该设计的 M5 场景），让"学战术→找工具练"双向可查

### S2 实践立项与阶段管理（复用 cg_projects）

- 候选 → 一键立项（from-knowledge 桥扩展）→ 四阶段：`research`（摸底）→ `setup`（搭环境）→ `exercise`（跑通/演练）→ `retro`（复盘沉淀）；阶段完成登记 activity
- `exercise` 阶段执行可走 P1-0 执行器（已批准，pi 边界内执行），也可人工

### S3 实践产物沉淀（复用 v1 Artifact + Knowledge）

- 产出（笔记/命令清单/复现脚本/截图）登记为 Artifact；复盘写 Knowledge（条件化经验："该工具适用于 X 场景，前提是 Y"）
- 价值：复利律兑现——第二次遇同类工具/场景，上次实践自动浮现

### S4 工具链健康（cg_services/cg_resources 窄用途保留）

- 本机已部署安全工具台账（版本/可用性），供 setup 阶段查"我装过什么"
- 克制原则：服务网格/漂移评估（原 phase2b M2-M4）与实践域无关，**列入删除候选**（下批裁决）

## 3. 明确收缩的部分

| 原能力 | 处置 |
|---|---|
| codegarden_phase2b（M2-M4） | gate 保持关闭；S4 不用则列删除候选 |
| github/import、sync、lifecycle | 保留（实践项目管理仍需要） |
| CRM 残留关联 | 已随 CRM 删除清空 |

## 4. 数据与界面（最小改动面）

- **表**：cg_projects 加 `practice_domain`（对标 interest 8 域）+ `source_hotspot_id`（选题溯源）两列（migration 117）；候选池不加新表（查询态派生）
- **界面**：行动侧入口（按 NAV4 行动菜单结构归位），改造现有 codegarden 组件为实践视角；不动三层壳
- **API**：候选池查询 1 + 立项扩展 1，阶段流转复用现有

## 5. 分期

| 期 | 内容 | 验收 |
|---|---|---|
| CP-1 | S1 全量信号提取 + 候选池（存量 9,872 条实跑） | 候选池 ≥20 条真实开源项目（不限域） |
| CP-2 | S2 立项四阶段 + 行动侧入口 | 候选一键立项并走完一个阶段 |
| CP-3 | S3 产物沉淀 + 知识联动 | 一个实践闭环产出 Artifact + Knowledge |
| CP-4 | S4 工具台账 + phase2b 删除裁决 | 台账可用；无用 gate 清理 |

## 6. 裁决与开放问题

- ~~选题口味（offensive/defensive）~~ → **已裁决**：全量识别不限域，候选池内排序。
- **实践深度**：候选立项后是"读 README 写笔记"级还是"部署跑通复现"级？影响 exercise 阶段定义与执行器需求强度（推荐：按项目分级，候选池带 effort 标签）。
- **入口位置**：推荐改造现有 /codegarden 页（避免新一级入口，符合壳纪律）。
- **NAV4 归位**：落地时按四大菜单 demo 的行动区结构归位。
