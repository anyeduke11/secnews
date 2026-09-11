# P2-6 Security Cockpit SPA 完整评估报告

> **日期**: 2026-08-25
> **范围**: `security-cockpit/` 设计稿 → 真实 SPA 的可行性 + 路径 + 工作量
> **目标**: 决策"是否移植、何时移植、如何移植"

## 1. 现状盘点

### 1.1 文件结构与体量

```
security-cockpit/
├── security-cockpit.design       # 设计元数据 (Stitch/canvas 格式)
├── validation-report.json        # 自动化验证报告 (7 soft warnings)
├── colors_and_type.css           # 设计 token 源 (89 行)
├── pages/
│   ├── cockpit.html              # 主座舱 (683 行)
│   ├── customer-form.html        # 客户管理 (928 行)
│   └── opportunity-form.html     # 商机管理 (663 行)
├── assets/                       # 静态资源 (空目录)
└── partials/                     # 部分模板 (空目录)
```

**总规模**: 2363 行 (含 CSS)。3 个静态 HTML + 1 个 design token CSS。

### 1.2 业务定位

| 页面 | 业务领域 | 复杂度 |
|------|---------|--------|
| **cockpit** | 安全服务业绩分析座舱 (KPI 仪表盘) | 中: 22 个卡片 + 3 个图表 + 3 标签导航 |
| **customer-form** | 客户管理 (CRM 客户 CRUD) | 高: 54 个表单元素 (text/email/date/number/select) |
| **opportunity-form** | 商机管理 (签单/合同/业绩) | 中: 17 个交互 (表单 + 状态机) |

业务关键字: 客户、业绩、商机、签单、合同 — 这是 **CRM-like 业务**，与现有 hotspot (资讯聚合) 业务正交。

### 1.3 设计验证状态 (validation-report.json)

```
renderBlockingErrorCount: 0  ✅
softWarningCount:          7  ⚠️
operatingMode:             free-explore
skillProvenance:           solo-design (read_status: missing)
expectedPages:             3 (符合)
requireInteractions:       6 个导航交互已声明
```

**7 个 soft warning 全部是 html-quality 类别**:

| # | 文件 | 警告类别 | 详细 |
|---|------|---------|------|
| 1 | colors_and_type.css | color tokens | `--brand-secondary/accent/accent-dim/accent-glow/color-accent/color-accent-dim` 不应出现在 free-explore 模式 |
| 2 | colors_and_type.css | radius tokens | `--radius-xl: 20px` 超规 (允许 2/4/8/12/16) |
| 3 | colors_and_type.css | shadow tokens | `--shadow-card/hover/glow-accent/glow-info` alpha > 0.05 (仅 floating layer 可用) |
| 4 | cockpit.html | color tokens | 同 #1 — 页面用了 brand-secondary/accent |
| 5 | customer-form.html | color tokens | 同 #1 |
| 6 | opportunity-form.html | color tokens | 同 #1 |

**严重度判断**: 全部为非阻塞警告。但说明设计 token 与 `solo-design` skill 的 free-explore 模式约束有冲突 — **移植到生产时需要先重做 token 体系**。

### 1.4 与现有架构的对齐情况

| 维度 | 现有 (hotspot) | security-cockpit mockup | 对齐情况 |
|------|---------------|------------------------|----------|
| 前端框架 | React 18 + Vite + Tailwind + shadcn/ui | 静态 HTML (零框架) | ❌ 不对齐 |
| 后端 API | 51 routers (`backend/api/*.py`) | **无对应 router** | ❌ 完全缺失 |
| 数据库 | SQLite (hotspot.db) | 无 schema | ❌ 业务领域未建表 |
| 路由注册 | `frontend/src/routes.tsx` (7 子模块) | mockup 用 `data-dom-id` 切页 | ❌ 不对齐 |
| 设计 token | Tailwind config + shadcn theme | `colors_and_type.css` 自定义 | ⚠️ 需迁移 |
| 测试覆盖 | 170+ pytest + frontend vitest | 零测试 | ❌ 移植时新建 |

**结论**: security-cockpit/ 是一个 **孤岛式设计稿**，与 hotspot 现有架构无任何集成点。

## 2. 设计稿技术债务评估

### 2.1 mockup HTML 的可移植性

| 维度 | cockpit.html | customer-form.html | opportunity-form.html |
|------|--------------|-------------------|----------------------|
| 行数 | 683 | 928 | 663 |
| 交互数 | 37 (data-/button) | 9 (form submit + button) | 17 |
| 组件复用度 | 低 — 每个卡片是手写 div | 低 — 表单字段扁平 | 低 |
| 数据绑定 | **零** — 全是静态数据 | **零** — 表单 submit 无 handler | **零** |
| 状态管理 | **零** — 无 JS | **零** | **零** |
| 路由 | nav-tab 用 `data-dom-id` 标注 | 同左 | 同左 |

**关键观察**:
- mockup 完全 **静态** — 没有真实数据、没有 fetch、没有状态机
- 没有 `<script>` 块 — 即使是简单交互也未实现
- 大量 `data-lucide` icon — 移植需 lucide-react 适配
- 用 `style="color: var(--color-accent);"` 等内联 — Tailwind CSS classes 需重写

### 2.2 设计 token 冲突清单

`colors_and_type.css` 与现有 Tailwind/shadcn 主题有 **3 类冲突**:

1. **品牌色**: `--brand-primary: #0A1628` (深蓝) vs Tailwind 默认 `slate/zinc` — 需自定义 palette
2. **强调色**: `--brand-accent: #00E5A0` (亮绿) — 需在 Tailwind config 加
3. **状态色**: `--brand-warning/danger/info/gold` — 需映射到 shadcn 的 `destructive/secondary` 等

迁移路径选择:
- (a) **完整重做 token**: 用 Tailwind theme.extend 重写为 design system
- (b) **保留 CSS variables**: 在 `:root` 注入, Tailwind config 引用 var(--token)

(b) 更稳 — 与现有 shadcn theme 兼容。

## 3. 移植工作量评估

### 3.1 假设: 完整移植为 React SPA + Backend API

| 子任务 | 估计工时 | 备注 |
|--------|---------|------|
| 设计 token 迁移 (Tailwind theme.extend) | 4h | 89 行 CSS → theme.ts |
| Cockpit 页面: 22 卡片 + 3 图表组件 | 16h | chart 选型 (recharts/echarts) |
| Customer CRUD: 表单 + 验证 + API 集成 | 16h | React Hook Form + Zod |
| Opportunity CRUD: 状态机 + API 集成 | 12h | 业务状态机 5+ 状态 |
| Backend: 3 routers + 2 repositories + 2 SQL tables | 20h | customers, opportunities, opportunities_history |
| Database migration + seed | 4h | FK 关系, 索引 |
| Auth + 权限控制 (Multi-tenant) | 8h | 当前 hotspot 无 multi-tenant 抽象 |
| E2E test (Playwright) | 8h | 3 page flows |
| 路由注册 + navigation | 2h | routes.tsx 加 cockpit 模块 |
| **合计** | **~90h (~11 工作日)** | 单人单线 |

### 3.2 假设: 仅做"设计验证 mockup 落地"

如果目标是 **生产可用但 MVP 简版**:

| 子任务 | 工时 |
|--------|------|
| Tailwind token 迁移 | 2h |
| Cockpit 页面骨架 (无真实数据) | 4h |
| 静态展示页 + mock 数据 | 4h |
| 路由接入 + navigation | 2h |
| **合计** | **~12h (1.5 工作日)** |

### 3.3 ROI 评估

| 收益 | 评估 |
|------|------|
| 复用现有 React/Vite/Tailwind 工具链 | ✅ 高 (零基础设施投入) |
| 复用现有 FastAPI 模式 (routers + repos) | ✅ 中 (业务新, 模式成熟) |
| 复用现有测试栈 (pytest + vitest + playwright) | ✅ 高 |
| 设计稿完整度 | ⚠️ 中 (静态, 缺数据/状态/交互) |
| 业务领域契合度 (CRM) | ❌ 低 — 与资讯聚合正交, 需独立 Product Context |
| 用户群体 | ⚠️ 不明 — 当前 hotspot 用户是安全资讯消费者, CRM 客户是新群体 |

**ROI 关键问题**:
1. 是否有真实的 CRM 业务需求 (或仅是设计演示)?
2. 谁来用 cockpit? 内部销售/BD 还是客户自助?
3. 与现有 hotspot 业务是否捆绑 (如把 cockpit 作为 hotspot 的付费增值模块)?
4. 数据来源: 手工录入 vs 抓取自外部 CRM (Salesforce/HubSpot)?

**没有这 4 个问题的答案前**, 不建议投入 90h 做完整移植; 建议先做 12h MVP 验证产品契合度。

## 4. 三档行动方案

### 方案 A: **冻结 mockup 留档** (推荐, 0h)

- 不投入移植
- 保留 `security-cockpit/` 作为设计探索留档
- 与现有 hotspot 业务正交, 不强行整合
- 适用: 暂无明确 CRM 业务需求, 设计稿作为 UI 风格探索

**前置**: 在 `docs/ARCHITECTURE.md` 标注 `security-cockpit/` 为 "已冻结设计探索", 不进入 v1.7+ 路线图

### 方案 B: **MVP 简版** (12h, 1.5 工作日)

- Tailwind token 迁移 + 路由接入
- Cockpit 页面骨架 + mock 数据
- 静态展示页 (无后端集成)

**适用**: 验证产品契合度, 给 stakeholder 演示

**前置**: 确认业务需求方, MVP 验收标准

### 方案 C: **完整移植** (90h, 11 工作日)

- 完整 React SPA + FastAPI + DB + Auth
- E2E 测试 + 文档
- 可作为 hotspot 的 CRM 增值模块上线

**前置**: 完整的 Product Requirements Document (PRD) + 用户故事 + 数据所有权 + 法务/合规审核

## 5. 与 P2 治理的关系

| P2 任务 | 与 security-cockpit 关系 |
|--------|------------------------|
| P2-1 ~ P2-5 (F841 / __all__ audit) | **无关** — 这是 hotspot 后端代码治理, security-cockpit 是 mockup |
| P2-6 (本评估) | **决策性文档** — 不写代码, 评估是否投入 |
| P2-7 (P2 同步) | **会引用本报告** — 在 PROGRESS 标注 P2-6 决策 |

## 6. 建议下一步

按 **方案 A (冻结留档)** 处理:
1. 在 `docs/ARCHITECTURE.md` 加一节"已冻结设计探索 — security-cockpit"
2. 不动 `security-cockpit/` 现有文件
3. **不在 P2 commit 中触碰** security-cockpit/ 目录
4. 等待明确 CRM 业务需求后, 再评估方案 B/C

如果用户后续明确要方案 B (MVP), 建议:
- 把 `security-cockpit/pages/*.html` 翻译成 `frontend/src/pages/cockpit/*.tsx`
- 用 Tailwind 重写所有 `style="..."` 为 class
- 不引入额外图表库 — 用 React + SVG 手写 3 个简单图表
- 后端暂用 mock data (Vite proxy 到 `/api/cockpit/*` 返回 fixtures)

如果用户明确要方案 C, 建议先写 PRD + 至少 3 个用户故事验收, 再排期。

---

**报告生成**: 由 P2-6 audit 任务自动产出, 调研基于 `security-cockpit/` 现状 + 现有 hotspot 架构盘点。
**决策权**: 用户/产品方。
**下一步**: 用户决策方案后, 再决定 P2-7 (同步文档) 是否引用本报告的某个具体方案。

---

## 7. 决议执行记录 (2026-08-25) — 方案 C 已交付

用户拍板 **方案 C (完整移植)**, 按本文档 §6 建议先写 PRD + 3 用户故事, 随后 T1-T5 一任务一提交落地:

| 任务 | commit | 内容 |
|------|--------|------|
| C1/T1 PRD | `b2131446` | [`docs/COCKPIT_PRD.md`](COCKPIT_PRD.md): 四问默认假设 / US-1 录入客户 / US-2 商机推进 / US-3 座舱复盘 / 六态状态机 / KPI 口径 |
| T2 数据层 | `4b8b4c66` | migration 071 三表 (crm_customers / crm_opportunities / crm_opportunity_events) + 客户/商机 repo + 状态机单测 10 用例 |
| T3 API 层 | `920587c8` | `/api/crm/customers` CRUD + `/api/crm/opportunities` 状态机 + `/api/crm/stats|meta`; X-CRM-Token 鉴权; crm 扩展域注册; API 测试 20 用例 |
| T4 前端 | `405d98ca` | `/crm` 页面 (座舱复盘 KPI+3 SVG 图表 / 客户管理 / 商机推进); crm feature flag 全链路; ROUTE_REGISTRY 登记 |
| T5 E2E+文档 | (本 commit) | 全栈 E2E (US-1→US-2→US-3 闭环经 register_routers) + 三文档同步 |

与原方案的偏差 (均为收紧而非缩水):
- **90h → 实际约 1 个工作日**: 复用 hotspot 既有分层 (extensions gate / repo 模式 / apiFetch / ROUTE_REGISTRY), 未引入图表库 (React + 手写 SVG)
- **Playwright 浏览器级 E2E 暂缓**: 当前沙箱无法跑真实浏览器矩阵; 以 TestClient 全栈链路测试替代 (`backend/tests/test_crm_e2e.py`), Playwright 列为后续增强项
- **Auth v1 单操作者 Token**: 多租户为 PRD §5 明确非目标
- 原 §6 "方案 A 冻结" 建议被用户决策覆盖; `security-cockpit/` 静态稿目录保持只读未动

后续增强 backlog: 商机编辑/删除 UI、事件时间线抽屉、月度目标线、导出报表。