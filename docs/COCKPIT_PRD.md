# CRM 业绩座舱 (security-cockpit) 方案 C 完整移植 PRD

> **决策**: 用户拍板方案 C (2026-08-25) — 完整 React SPA + FastAPI + DB + Auth。
> **来源**: `docs/P2_6_COCKPIT_EVAL.md` 三档评估 → C 档；设计稿 `security-cockpit/`。
> **状态**: 交付中 (分阶段提交，见 PROGRESS.md)

## 0. 业务问题定案 (P2-6 §3.3 四问的默认假设)

用户未逐条回答四问即拍板方案 C，按以下默认假设执行（PR 评审可推翻，改动集中在本文档）:

| # | 问题 | 默认假设 |
|---|------|---------|
| 1 | 真实 CRM 需求? | 是 — 安全服务团队需要管理客户/商机/业绩，非纯设计演示 |
| 2 | 谁用? | **内部**销售/BD/交付负责人（登录后使用），不做客户自助门户 |
| 3 | 与 hotspot 关系? | 作为 hotspot 的**增值扩展模块**（feature gate `crm` 门控），共享现有 SQLite/前端工具链 |
| 4 | 数据来源? | **手工录入** CRUD，不对接外部 CRM (Salesforce/HubSpot) |

## 1. 用户故事与验收标准

- **US-1 录入客户**: 作为 BD，我可以新增客户（名称/行业/等级 S-A-B-C/状态/区域/负责人/联系人/电话/邮箱/合同起止/金额/NPS/备注），在列表按行业+状态筛选、按名称搜索 → 列表实时反映。
- **US-2 商机推进**: 作为负责人，我创建商机挂到客户下，沿管线 `需求沟通→方案提交→商务谈判→合同签订→赢单/输单` 推进；非法跳跃（如需求沟通→合同签订）被 400 拒绝；每次迁移留痕到事件表。
- **US-3 座舱复盘**: 作为团队负责人，打开座舱页看到 8 个 KPI（年度总营收/毛利率/客户总数/复购续签率/在途商机/赢单率/平均客单价/NPS）与 3 个图表（月度营收趋势/区域营收分布/项目漏斗），数值由真实商机数据聚合而来。

## 2. 数据模型 (`071_crm_cockpit.sql`)

```
crm_customers      id, name(必填唯一), industry, level(S/A/B/C), status(活跃/续约中/停滞/流失),
                   region, owner, contact_name, contact_phone, email,
                   contract_start_date, contract_end_date, contract_amount(元),
                   nps_score(0-10 可空), notes, created_at, updated_at
crm_opportunities  id, customer_id→customers(CASCADE), name, service_type,
                   stage(六态), amount(元), cost(元, 毛利率分母), owner,
                   expected_close_date, description, won_at, lost_reason,
                   created_at, updated_at
crm_opportunity_events  id, opportunity_id(CASCADE), from_stage, to_stage, note, created_at
```

### 商机状态机 (非法迁移一律 400)

```
需求沟通 → 方案提交 → 商务谈判 → 合同签订 → 赢单
   ↘输单      ↘输单       ↘输单       ↘输单
赢单 / 输单 为终态; 进入 赢单 时写 won_at=now
```

## 3. KPI 口径 (座舱页)

| KPI | 公式 |
|-----|------|
| 年度总营收 | 当年 `stage=赢单` 的 amount 求和 |
| 毛利率 | 当年赢单 `(amount-cost)/amount` 加权 |
| 客户总数 | count(crm_customers) |
| 复购续签率 | ≥2 单赢单客户 ÷ ≥1 单赢单客户 |
| 在途商机 | stage ∉ {赢单,输单} 计数 |
| 赢单率 | 赢单 ÷ (赢单+输单) |
| 平均客单价 | 当年赢单 amount 均值 |
| NPS | 推荐者(9-10)% − 贬损者(0-6)% |

图表: 月度营收趋势(近12月赢单额)、区域营收分布(当年赢单额按客户 region)、项目漏斗(各活跃 stage 计数)。

## 4. 架构接入

- **后端**: 扩展域 `crm`（feature gate 默认 true）— `EXTENSION_ROUTERS["crm"]` 注册
  `crm_customers_api` / `crm_opportunities_api` / `crm_stats_api` 三路由（各 ≤150 行），
  前缀 `/api/crm/*`；repo 层复用 `get_connection` + 迁移体系。
- **Auth (v1)**: `X-CRM-Token` 头比对环境变量 `HOTSPOT_CRM_TOKEN`（secrets.compare_digest）；
  未设置该变量 = 本地单机模式放行并响应头提示。多租户/角色明确为**非目标**（eval §Auth 8h 项的 v1 简化，留档待后续）。
- **前端**: `/crm`（座舱）、`/crm/customers`、`/crm/opportunities`；组件
  `components/crm/*`；图表用 React + SVG 手写（不引图表库）；token 存 localStorage。
- **E2E**: pytest TestClient 全栈三故事流（US-1/2/3 各一条链路测试）+ vitest 组件测试；
  Playwright 浏览器级 E2E 明确列为后续项（沙箱环境浏览器安装不可控）。

## 5. 非目标 (v1 明确不做)

多租户/角色权限、外部 CRM 同步、审批流、发票回款、邮件提醒、i18n、移动端适配。
