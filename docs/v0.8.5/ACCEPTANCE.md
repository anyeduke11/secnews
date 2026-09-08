# v0.8.5 验收矩阵（真实证据）

> 每行 = spec `V0.8.5_PLAN.md` §13/§11 的一条验收项 → 证据（测试/命令/实测输出）。
> 证据采集时点: 2026-09-08, main `d4664d9`+。实现侧产材料、独立 agent 出 verdict（§2 分工）。

## 1. 一致性门

| 项 | 证据 | 结论 |
|---|---|---|
| FactCheck（spec 对照仓库事实） | 独立 Explore agent 9 项核对: 路由现状/端点注册/组件/迁移 096-107/版本/守卫语义 | **9/9 PASS** + 2 处 spec 措辞修正（cases status 重复键、adoptions 无服务端过滤, C0.1 已改） |
| G1 类型契约 | `python scripts/codegen_v1_ts.py --check` → "OK … SHA256 3cf514c9a09bd251…", exit 0 | **PASS** |
| G2 端点存在性 | `python scripts/check_v1_endpoint_parity.py` → **74/74 注册**, exit 0（独立抽查 3 端点 file:line 吻合） | **PASS** |
| G3 流程走查 | `python scripts/t085_golden_walkthrough.py`（流程验证 agent 从 §6 独立导出检查单 + 审脚本断言）→ PASS=13 / DEGRADED=1 / FAIL=0, exit 0 | **PASS-WITH-DEGRADED**（S13 出稿依赖 dsh/证据 fixture, spec §9 明示 demo 不主张, 独立 agent 判定 degraded_justified=true） |
| G4 UI/代码 | tsc 0 错 · vitest 476/476 · vite build 绿 · code-reviewer **APPROVE**（无 P0; 3 P1 已修 `321189a`/`eff9b04`） | **PASS** |

## 2. §13 最终验收

| # | 验收项 | 证据 |
|---|---|---|
| 1 | 三层可走通互达 | 守卫 `v085_route_shell.test.tsx` 14 断言（三层必须 SentinelShell+心跳条 / LAYER_DEFS 指向三层）; 实测截图 `dev_data/screenshots/v085/{home,judge,action}-1440*.png`（三层导航高亮正确） |
| 2 | 旧路由不 404 + query 透传 | 浏览器实测: `/workbench?focus=1`→`/?focus=1` ✓, `/intel`→`/` ✓, `/cases`→`/judge` ✓; 守卫含 QueryRedirect **运行时**断言（D2 补） |
| 3 | Case 详情完成 审批→运行→验收 | G3 S10 approve→start→cancel 全链 200、S11 verify→accept 全链 200（真实变异, fixture=v085-review-A）; 实弹 case 详情截图显示 "2 次运行 · 1 已业务验收" |
| 4 | 单一壳/单一导航/心跳条常驻 | 5 断点（390/768/1024/1280/1440）×3 页截图 + `/cases/:id` `/knowledge/v1`; fs+grep 双断言 V1SentinelShell 已删除; 三层页无 AppNav |
| 5 | 四门全绿 + 用户终审 | 用户浏览器实走三层动线后裁决合入（merge `a92effe`, tag `v0.8.5`） |

## 3. D1-D3 批次一等验收

| 批次 | 验收项 | 证据 |
|---|---|---|
| D1 点火 | ≥1 真实源端到端 scheduler→准入→v1_signals | 实弹 security:SecWiki: **10 entries → 10 materials → 10 signals, 0 失败**; 二轮 10+10 全部跳过/重放（零重复）; job `v1_signal_intake_tick` 300s 常驻 |
| D1.2 | 信号→Case 立项携带证据 | migration 108 `v1_case_materials`; 实弹: 立项(related_signal_ids) → aggregate `evidence_materials` 回读 1 条（hash d176964fcf2e…, 信号回链）; 反例测试（绑定+回读） |
| D1.3 | Subject 下钻 | `GET /api/v1/signals?subject_id=` 过滤; 实弹 total=2（信源: SecWiki）; SignalPanel 抽屉 |
| D2 | 真实出稿可观测（失败不显示成功） | CaseDetail 生成判断/发布/生成行动按钮（证据+CVE 门控, allowed_actions 守卫）; dsh/ai_hub 不可达 → 失败 toast 如实报错; R05/R07 已于 C07 修复（protocol 必填 + asyncio.run） |
| D2 R09 | artifact API 级 CAS | verify/accept/reject +expected_revision → 409 E_CONFLICT（实测 `expected_revision=102 current=3`）; service 反例 2 个 + repo 级 CAS 原有 |
| D3 传动 | 第二个同类 Case 自动浮现知识 + 真实采用回执 | 实弹: 新建同类 Case（无手动关联）→ aggregate `recall_candidates` 浮现「FastGate 3200 处置手册」(score 2, 关键词 3200/fastgate) → API 采用 → **回执 id=3**（reuse total=3, adopted=3, 近30天=3）; 召回反例 3（命中/无关不浮现/非 published 不参与） |
| D4 复利卡 | 诚实计数 | aggregate `reuse_summary`（adoptions_total/30d/distinct, 来自 v1_knowledge_adoptions 真实回执）; 反例: 采用前 0 → 采用后 1/1/1; **不做无基线的「节省 X」估算** |
| D4 旧路由对账 | `routes/ROUTE_REGISTRY.md` v0.8.5 第三次重写（三层/重定向/工具页/扩展域/v1 API 域行）; 守卫测试锁口径 | 完成 |
| D4 legacy 数据对账 | `/api/dsh/legacy/migrate/v1/status` → dev mapping_total=0（dev 库无 legacy 行）; builtin 26 = 20 legacy_v0 + 6 v1_active; **生产 853 行 warm 迁移为授权运维任务**（C13 工具链就绪: run/mapping/promote + 备份前置） | 已对账, 迁移待授权 |

## 4. 已知边界（诚实声明, 均有批次归属）

1. **B1 观察窗**: 点火已贯通, 「每天产出被采纳信号」需数日运行观察 + 准入规则调优（admission_log 已自动积累）。
2. **B2 出稿 provider**: dev 环境未配 LLM provider, 生成按钮点击返回真实失败原因（D2 语义=失败可观测）; 生产出稿质量验收需配 provider 后进行。
3. **B6 生产数据迁移**: 工具链就绪（C13）, 对生产 warm 库 853 行执行需改库授权 + 备份前置（T02 备份链已验证）。
4. **可访问性**: 390 断点响应式已验证; WCAG 深度审计未做（记录为后续治理项）。
5. code-review P2: CaseDetail 竞态已在 D2 修复; V1Prototype 死代码已在 D2 删除; verify 死载荷已在 D2 转真实 CAS。
