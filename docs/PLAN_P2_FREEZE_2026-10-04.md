# P2 收敛冻结阶段规划 (v0.8.6)

> **日期**: 2026-10-04 · **工期**: 1 周 (PRD §10 定义) · **编号**: DEV-0277 (本规划立案)
> **权威依据**: `docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md` §10 Phase P2 + 审计 E8/F1 遗留池
> **阶段里程碑**: P2 完成 = **G2 清零确认** (三类静默失败 100% 落显式 outcome, 失败面板可见)

## 0. P1 交接状态 (规划输入)

P1 八项全部交付 (DEV-0263~0276, commit 16179e2..428492d)。交接清单:

| 交接项 | 状态 | 归宿 |
|---|---|---|
| signals ≥120/30d | 2117 ✓ 超额 | — |
| ai_scores >0 (T4 前置) | 421 行/1d ✓ | — |
| T4 发布增速 / llm_used 水位 / 转化率带 15-30% | **待 24h 复核** | → P2-0 |
| G2③ 写库失败 439 次 | P0-7 断根 ✓ | → P2-0 确认归零 |
| G2② 55 job 静默 misfire | P0-5 ops_runs ✓ | → P2-0 确认归零 |
| G2① gate-detect fail-open 1,006/日 | **P0-6/P0-12 修了 score 面, 调用失败显式 outcome 未闭环** | → P2-1 |
| SentinelJudgePage 死代码 | DEV-0258 已物理删除 | → P2-3 清尾巴 (css+文档) |
| E8 投影不可重建 | 未动 (26 列表 upsert 写 16 列; md 缺 entities/compiled) | → P2-2 |
| failed Run 重试按钮 / requestId 竞态 / 弹窗类 20 文件 | P1 列后续批 | → P2-5 (可选) |
| SK-04 直写端点收编 | P1-3 开出工单 | → P2-4 |
| pi 执行体 / TanStack / raw_items.content / accessor 双库歧义 | 工单池 | → **P2 不做** (见 §3) |

## 1. 阶段纪律 (冻结定义)

- **冻结不加**: 不新增能力/页面/Skill 包; Skill* 家族零投入 (R5 教训, PRD §10 原文)。
- **死代码删除仅限审计点名且验证无引用者**。
- **只修不改**: P2 允许的代码变更为 — G2 收口、E8 补列、存量尾巴; 不做重构/优化类顺手改 (Rule 3)。
- TanStack Query 评估、i18n、移动端: 维持 D5/PRD 原裁决 (另议/不做)。

## 2. 任务分解 (按序执行, 单人带宽)

### P2-0 生产观测窗口复核 (半天, 纯查询+报告, 无代码) — 开场任务

24h 窗口三项生产核对 + G2 两类归零确认, 产出一份观测纪要 (落 PROGRESS):

| 核对项 | 口径 | 通过线 |
|---|---|---|
| T4 发布增速 | kl:publish 增量 vs skipped_low_score 积压 | 有分条目持续发布; 无分积压可见但不阻塞 |
| llm_used 水位 | `_classify_new_items` 日志 | 若常顶预算 20 → 调 AI_CLASSIFY_BUDGET_PER_BATCH (记录不调码) |
| signals 转化率带 | signals/hotspots 7d 比率 | 落在 15-30% 目标带 (P1-6 报告口径) |
| G2③ 写库失败 | 生产日志 grep `no such table: warm.` | **0 次** (P0-7 后断根确认) |
| G2② misfire | job_runs status=missed + 调度日志 | misfire 有显式记录 (非静默) 即达标 |

**验收**: 纪要落账, 未达标项转 P2 内修复任务。

### P2-1 G2① gate-detect 显式 outcome (半天~1 天) — G2 清零最后一块

**现状**: `ai_service.gate_detect` 超时/拒绝 → 返回 None → AIQualityGate fail-open 放行 (审计 1,006 次/日的路径)。P0-6 修了 score 缓存污染, P0-12 修了 gate 崩溃 fail-closed, 但 **LLM 调用失败的显式 outcome 仍未落**。

**修法** (最小面): gate_detect 失败路径落显式可见性 — `llm_usage_log` 记 outcome=timeout/refused (gateway 记账已全量, 补 outcome 字段语义) + 日志从分散 WARNING 升为可聚合信号; AIQualityGate 侧维持 fail-open 采集 (门禁放行语义经 P0-12 裁决不动), 但 **失败必须可见可数**。

**验收** (G2①): 构造 gate_detect 超时用例 → llm_usage_log 有 outcome≠ok 行 + 失败面板/计数可查; 生产 24h 后 gate-detect 失败 100% 有显式 outcome (对照审计 1,006/日基线)。

**红线**: 不动 `gateway._try_order` / `service._resolve_provider` (AGENTS.md ai_hub 红线)。

### P2-2 E8 真源缺列补齐 (1 天) — 需 owner 一项裁决

**现状** (审计 E8): knowledge_items 26 列, `upsert_item` 只写 16 列; `write_item_to_md` frontmatter 省略 `entities`/`compiled` (还有 body/attention_score) → 投影不可从 md 完整重建, 违背 wiki-first。

**推荐方案** (审计 §6.2 原则 "要么进 frontmatter, 要么明确标注派生缓存可丢", 二分):
- `entities`/`compiled` → **写进 md frontmatter** (可由正文推导/人工维护的语义列, 属真源);
- `body` → md 正文本就是 body (投影从正文读), 标注对齐即可;
- `attention_score` → **标注派生缓存可丢** (attention_scorer 5 维聚合的运行时产物, 1800s job 重算, 丢可重建)。

**验收**: ① write_item_to_md 产出的 frontmatter 含 entities/compiled; ② md→SQLite 重投影断言列覆盖 (抽 3 列 roundtrip); ③ upsert_item 未覆盖列清单成文 (哪些是派生缓存, 落 knowledge_repo docstring)。

**owner 裁决点**: entities/compiled 进 frontmatter vs 全部标注派生缓存 (推荐前者; attention_score 推荐后者)。

### P2-3 死代码尾巴 (半天)

SentinelJudgePage 主体已删 (DEV-0258), 清剩余:
- `frontend/src/components/sentinel/sentinel-judge.css` 死文件 (无引用验证后删);
- `docs/code-wiki/03-frontend.md` `/judge → SentinelJudgePage` 行过时更正 (Gortex 自动产物, 按其生成规则更正或标注);
- 全仓 grep `SentinelJudgePage` 残留引用归零。

**验收**: 引用 = 0 + tsc/build 绿。

### P2-4 SK-04 直写端点收编 (半天)

`KnowledgeService.create_with_dsh` 的 HTTP 面 (经 skill_registry SK-04 触发) 绕过提案审批 — 与 judgment generate 同模式。收编为: HTTP 调用改落 `copilot_draft(kind='report')` 提案 (人审后生效), service 保留 (registry target 引用)。**验收**: SK-04 触发路径产生 proposal 而非直写 knowledge; 既有 SK 测试适配。

### P2-5 (可选, 带宽富余时) P1-7 第二批

弹窗类 20 文件 useAbortGuard 同模式 + requestId 依赖变更序竞态 (filter 连点旧覆新)。**非 P2 验收项**, 冻结期优先级最低。

### P2-6 竞品参照复盘 (一次会话, [假设] 项)

PRD "[假设] 竞品参照复盘一次" — 对标对象与维度需 owner 点名 (候选: Gemini for Security 的 Assisted workflows 嵌入式能力分布, PRD §2 竞品表)。产出: 复盘纪要落 docs/。**owner 未点名则本项挂起不阻塞 P2 验收**。

## 3. P2 明确不做 (冻结清单)

| 项 | 理由 | 归宿 |
|---|---|---|
| pi 执行体 (needs_human 出口的真实执行) | 大体量独立批次; P1-1 finish_run 入口已备 | 单独立项 (建议 P3 或专项) |
| TanStack Query / 前端状态库 | D5 裁决 (c) 维持, 修竞态已完成 | D5 长期项 |
| raw_items.content 正文留存 | 采集增强 | 工单池 |
| accessor main/warm 双库同表歧义 | 存储治理 (migrate_temp_layers 式清理) | 工单池 |
| i18n / 移动端 / 多用户 | PRD 原裁决 | — |
| 依赖变更序竞态 requestId | 归 P2-5 可选 | — |

## 4. 验收汇总 (P2 完成 = G2 清零确认)

1. **G2 三类 100% 显式 outcome**: ①gate-detect (P2-1) ②写库失败 (P0-7 已断根, P2-0 确认) ③misfire (P0-5 已修, P2-0 确认) — 生产 24h 窗口证据;
2. E8: entities/compiled 入 frontmatter (或按裁决标注), 重投影断言过 (P2-2);
3. SentinelJudgePage 引用归零含尾巴 (P2-3);
4. SK-04 HTTP 面走提案通道 (P2-4);
5. 冻结纪律零违反 (无新能力/Skill* 零投入);
6. 观测纪要落账 (P2-0)。

## 5. 排期建议 (1 周)

| 日 | 内容 |
|---|---|
| D1 | P2-0 观测窗口开场 (启动 24h 计时) + P2-3 死代码尾巴 |
| D2 | P2-1 gate-detect 显式 outcome |
| D3 | P2-2 E8 补列 (含 owner 裁决点确认) |
| D4 | P2-4 SK-04 收编 + P2-0 复核收尾 |
| D5 | 缓冲 / P2-5 可选 / P2-6 复盘会 (owner 到场) |
