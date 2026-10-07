# P2-6 竞品参照复盘纪要（v0.8.6）

> **日期**: 2026-10-04 · **编号**: DEV-0285 · **范围**: owner 裁决「深挖+快扫组合」
> **深挖**: Google Gemini for Security（Assisted workflows 嵌入式能力分布，计划点名候选）
> **快扫**: Microsoft Security Copilot / Filigran OpenBAS(→OpenAEV) / DefectDojo
> **方法**: 联网取证 2026 年公开资料（厂商官方 blog / Learn / 产品页），对照 PRD §1.5 竞品表 [假设] 行逐行验证 + 本产品四轴（M1-M4）/ 三目标（G1-G3）现状
> **性质**: PRD §1.5 原文「[假设] 本产品为单人内部工具，以下竞品为设计参照而非直接对位」——本纪要为该假设的首次实证复核，P2-6 验收交付物

---

## 1. 深挖：Gemini for Security — Assisted workflows 的 2026 形态

PRD 假设（2026-09 撰写）：「模型按任务分层（Gemini Flash/Pro 分档），能力以 Assisted workflows 嵌入既有界面」。

**2026 现状：Assisted workflows 已演进为 agentic SOC，但「嵌入式分布」原则不仅没变，反而被加倍下注。**

| 能力面 | 2026 状态 | 嵌入位置（对应我们的面） |
|---|---|---|
| Triage and Investigation agent | 已投产：年处理 500 万+ 告警，30min 人工研判 → 60s | 告警分诊流内（≈ 我们 signals→case 链） |
| Threat Hunting agent / Detection Engineering agent | Next '26（4 月）preview | 威胁狩猎 / 检测工程工作流内 |
| Agentic automation | RSAC '26 preview：agent 嵌入自动化动作，动态 AI × 确定性自动化结合 | SOAR playbook 内（≈ 我们 pi 执行体设想） |
| Gemini Investigation Assistant | 投产：对话式过滤 → 摘要 → 上下文内起草 YARA-L 规则 / SOAR playbook，「从告警到自动防御的无断点管线」 | Search/UDM 界面内（NLS 2023 起原生） |
| MCP server | **GA**；SecOps 聊天界面内直接可调 MCP client（preview） | 平台能力以 MCP 协议对外暴露 |
| 模型分档 | SecLM（安全调优 LLM）+ Gemini 分档延续 | 任务分层路由（≈ 我们 scenarios/HEAVY-STANDARD） |
| Gemini Enterprise 层 | Agent Designer / **Inbox（管理 agent 活动的收件箱）** / long-running agents / Skills | 跨产品 agent 治理（≈ 我们 ApprovalInbox + 提案通道） |

**嵌入式能力分布的结构性读法**（对照本产品）：

1. **能力入口在工位点，不在独立聊天页**——NLS 在搜索框、assistant 在分诊流、规则起草在检测工程页。我们 M3 副驾四卡挂四菜单区块、M4 命令栏常驻 masthead 的「零新路由」纪律与之同构，方向被头部产品强化验证。
2. **agent 产出 = 带证据链的结论**——分诊 agent 的 verdict 附完整解释与证据（BBVA 案例），Threat Hunting agent 直接产出 findings report（产物化）。我们 run 账本「禁止成功但无产物」+ artifact sha256 与之收敛。
3. **agent 治理走 Inbox 模式**——Gemini Enterprise 用 Inbox 管理 agent 活动；我们提案通道（draft → 人审 → 产物化）是单人版同构。人主律不是差异，是行业共识。

## 2. 快扫 ×3（现状校准）

### Microsoft Security Copilot

- **agents 全家桶化**：Security Analyst Agent（2026-04 preview，独立或嵌入双形态）、Conditional Access Optimization Agent GA、Data Security Posture/Triage Agent 等；结论均「附清晰理由与佐证证据」。
- **Agent 365**（2026-05-01 GA，$15/user/月）：agent 作为一等可审计实体的控制平面——身份、审计、姿态、授权。365 E7「Frontier Suite」打包。
- **对照 PRD 假设行**「对话式入口即审计对象：每轮交互落 session 记录」——✅ 成立且被行业升维：从「会话审计」走到「agent 本体审计」。我们以本地 SQLite run 账本替代云端 session 的差异化点维持，且「账本方向」获行业印证。

### Filigran OpenBAS → **OpenAEV**（已更名/升维）

- 2026-09 OpenAEV v3：**Attack Chaining**（自主攻击链——每步产出喂下一步、条件分支、live 攻击路径图）、Adversarial Exposure 评分、AI red-teaming injectors、自动化报告；**operator-led vs agent-led 双模编排**显式切换。
- **对照 PRD 假设行**「Action→Injector→Result 全程原子化执行记录」——✅ 成立（v3 的 live graph 是原子记录的图形化升维）。Run 账本纪律仍是其架构基座。
- **新可借鉴**：operator/agent-led 双模正是我们 needs_human → pi 执行体的光谱两端；条件链（if credential valid → pivot）是 run 步骤依赖的参照形态。

### DefectDojo

- **DefectDojo Sensei**（2025-11 发布）：自包含 AI agent——**不依赖任何第三方 LLM**（自托管/气隙可用），auto-triage / dedup / KEV-EPSS 富化 / 风险看板 / 报告生成；**MCP server**「把 DefectDojo 情报带给任何 AI/模型」。
- **对照 PRD 假设行**「证据回执（evidence receipt）一等公民」——✅ 成立（finding 带证据引用 + 生命周期仍是核心）。
- **关键印证**：Sensei 的卖点恰是我们 ai_hub 差异化的行业版——**本地/自托管 AI 池在敏感数据场景已是公认差异化**，单人内部工具的「9 平台自选 + 数据不出机」从边缘选择变成正名的设计。

## 3. PRD §1.5 假设逐行验证汇总

| 竞品行 | [假设] 现状 | 可借鉴点落地情况 | 差异化点现状 |
|---|---|---|---|
| Security Copilot | ✅ 成立，行业升维到 agent 审计 | session 审计 → 已落地（command_log + run ledger） | 本地账本 vs 云端 session：维持，方向被印证 |
| Gemini for Security | ⚠️ 表述过时：Assisted workflows → agentic SOC（嵌入原则不变） | 分档路由 → scenarios ✓；界面内嵌 → M3 区块 ✓ | 模型池开放：维持（Sensei 侧证） |
| OpenBAS | ✅ 成立，产品更名 OpenAEV 升维 | outcome 枚举/防无产物 → run ledger ✓ | 单人研判 vs 团队仿真：维持 |
| DefectDojo | ✅ 成立 | 证据回执 → evidence receipts ✓ | 资讯侧全链切入：维持（无人对标） |

**结论：四行假设无一被推翻；一行表述过时（Gemini，建议 PRD 措辞更新）；全部「可借鉴点」已在 P0-P2 落地或有对应物。差异化四点全部维持，其中「本地 AI 池」获 DefectDojo Sensei 行业级背书。**

## 4. 行业共性模式（2026）与本产品对照

| # | 模式 | 头部动作 | 本产品现状 | 判定 |
|---|---|---|---|---|
| 1 | agent 是一等审计实体 | Agent 365 / Google Agent Identities | run ledger + proposal + command_log（单机版） | 同构 ✓ |
| 2 | MCP/A2A 协议化分发 | Google MCP GA / DefectDojo MCP / MSFT Agent 365 | mcp gate 存在（默认关），仅有调试路由 | **差距 → 工单池** |
| 3 | Inbox 式 agent 治理 | Gemini Enterprise Inbox | ApprovalInbox + CopilotCards | 同构 ✓ |
| 4 | 嵌入式工位入口 > 独立聊天页 | Gemini 全线 | 四菜单区块 + 常驻命令栏（零新路由纪律） | 同构 ✓ |
| 5 | 结论默认带证据链产物 | 两家头部均为默认行为 | receipt/artifact/sha256 + 拒收回放 | 同构 ✓ |
| 6 | 任务分档模型路由 | SecLM + Flash/Pro 分档 | scenarios deep/light + HEAVY/STANDARD | 同构 ✓ |
| 7 | 双模编排（operator/agent-led） | OpenAEV Attack Chaining | needs_human 出口已备，pi 执行体未接 | **参照 → pi 立项** |

## 5. 可行动发现（全部入工单池，不属 P2 冻结范围）

1. **MCP server 导出本产品能力**（run/proposal 只读查询、case 召回）——行业已全面 MCP 化，我们 mcp gate 管道现成、只缺 server 面；成本低收益高（P3 候选）。
2. **pi 执行体设计参照 OpenAEV 双模编排**：operator-led（现在，人审批）↔ agent-led（目标态）；条件链语义（步骤结果驱动分支）可直接映射 run 步骤依赖。pi 单独立项时引入本纪要为设计输入。
3. **KPI 口径行业对标**：头部产品量级是「分诊时延」（30min→60s）而非流量比率；我们 15-30% 转化率带已证与质量门槛结构性冲突（DEV-0284）。建议 P3 将 KPI 从比率切换为「信号→case 时延 + artifact 产出率」类指标——**此为 DEV-0284 结构性发现的对标佐证**。
4. **PRD §1.5 措辞更新**（本纪要落账时同步）：Gemini 行「Assisted workflows」→「agentic SOC agents（嵌入式分布原则不变）」。

## 6. 明确不做（冻结纪律延续）

- 不引入 agent 治理控制面（Agent 365 类）——单机单人以账本即审计，无需独立平面。
- 不做攻击仿真/BAS——OpenAEV 领域，非本产品射程。
- 不做多 agent 互操协议实现——MCP server 导出（发现 1）已覆盖最小需求。

## Sources

- [Next '26: Redefining security for the AI era with Google Cloud and Wiz](https://cloud.google.com/blog/products/identity-security/next26-redefining-security-for-the-ai-era-with-google-cloud-and-wiz)
- [RSAC '26: Supercharging agentic AI defense with frontline threat intelligence](https://cloud.google.com/blog/products/identity-security/rsac-26-supercharging-agentic-ai-defense-with-frontline-threat-intelligence)
- [Gemini in Google SecOps（官方文档）](https://docs.cloud.google.com/chronicle/docs/secops/gemini-secops)
- [Adoption Guide: Best practices for using Gemini Search in Google SecOps](https://security.googlecloudcommunity.com/google-security-operations-66/adoption-guide-best-practices-for-using-gemini-search-in-google-secops-7799)
- [Welcome to Google Cloud Next '26](https://cloud.google.com/blog/topics/google-cloud-next/welcome-to-google-cloud-next26/)
- [Secure agentic AI end-to-end | Microsoft Security Blog](https://www.microsoft.com/en-us/security/blog/2026/03/20/secure-agentic-ai-end-to-end/)
- [What's new in Microsoft Security Copilot（April 2026）](https://learn.microsoft.com/ru-ru/copilot/security/whats-new-copilot-security)
- [Microsoft Agent 365](https://www.microsoft.com/en-us/microsoft-agent-365)
- [OpenAEV — Adversarial Exposure Validation Platform | Filigran](https://filigran.io/products/openaev)
- [Filigran Adds Attack Chaining to OpenAEV（2026-09-01）](https://filigran.io/ja/press-releases/filigran-adds-attack-chaining-to-openaev)
- [XTM One: An agentic AI layer | Filigran](https://filigran.io/platform/xtm-one/)
- [DefectDojo AI（Sensei / MCP）](https://defectdojo.com/ai)
- [DefectDojo Sensei 发布公告（2025-11-04）](https://defectdojo.com/news/defectdojo-supercharges-and-safeguards-ai-poweredcybersecurity-with-defectdojo-sensei)
