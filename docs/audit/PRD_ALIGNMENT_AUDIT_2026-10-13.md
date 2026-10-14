# PRD 对齐审计 — DEV-0326 放行通用赞/踩 (2026-10-13)

> 格式：PRD_ALIGNMENT_AUDIT_YYYY-MM-DD.md（单一权威 PRD 维护纪律）
> 事项：兴趣引擎 reaction 语义反转——无域条目的赞/踩由「丢弃 + 前端回滚」改为「哨兵域持久化 + 权重隔离」

## 裁决链

1. **2026-10-13 owner 输入**：「`button`其他领域和类型的资讯点赞点踩功能异常」。
2. **诊断（非缺陷判定）**：经链路走查（ReactionButtons → useReactions → lib/interest → `interest_api` → `interest_engine_service.record_signal` → `hotspot_repo`），确认为 **DEV-0314「安全域门控」既定语义**——非安全域/未归类条目 reaction 被静默丢弃 + API 返 `accepted_no_domain` + 前端如实回滚乐观高亮并弹 toast「未参与推荐」。**非代码缺陷**，是产品有意设计。
3. **2026-10-13 owner 裁决**：`AskUserQuestion` 选定**「放行通用赞/踩（推荐）」**——「为所有资讯持久化赞/踩状态，真正做到「点了就记住」不再回滚；但仅安全领域条目计入兴趣推荐权重，非安全内容不污染排序。」即显式反转 DEV-0314 中关于 **reaction** 的部分。

## 冲突消解（Rule 7）

- **冲突**：DEV-0314「非安全类目维持 no-domain 语义（不入权重）」vs owner 本次裁决「放行通用赞/踩」。
- **取舍**：取**新且 owner 指向**——DEV-0326 覆盖 DEV-0314 的 reaction 分支；**累计型**信号（view/read/dwell/deep_read/favorite）无域丢弃语义**不变**（DEV-0314 此处无冲突，未触碰）。

## 设计要点（放行 + 隔离）

| 维度 | 决策 | 理由 |
|---|---|---|
| 无域 reaction 持久化 | 哨兵域 `INTEREST_UNATTRIBUTED_DOMAIN = "_unattributed"` + `weight 0.0` | `domain TEXT NOT NULL` 不能存 NULL；weight 0 保证零权重贡献 |
| 对外契约 | 仍报 `domain: None`（`{status: ok, domain: null}`） | 前端/UI 无需感知哨兵域内部表示 |
| 权重隔离 | 哨兵域不属 `PRACTICE_DOMAINS` → `aggregate()` 的 `if d in raw` 天然跳过 | 不进兴趣权重、不影响 feed 排序 |
| 内容偏好推导泄漏面 | DEV-0316 `interest_signal_stats_by_axis` SQL 加 `AND s.domain != ?` 排除哨兵域 | 该统计按 `COUNT(*)` 计 events，weight=0 行会 +1 触发 more/less 门限 → 唯一需显式封堵的泄漏面 |
| 审计视图 | `interest_audit_by_domain` 会多一哨兵行 | 仅审计可见，可接受（不删） |

## 回写落点核对

| 回写项 | 位置 | 状态 |
|---|---|---|
| 权威 PRD 变更记录 DEV-0326 条 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 变更记录末条 | ✅ |
| 兴趣引擎 PRD API 语义 | `docs/INTEREST_ENGINE_PRD_v1.0.md` §4 端点表 | ✅（DEV-0326 修订行） |
| 兴趣引擎 DEV 计划 record_signal | `docs/INTEREST_ENGINE_DEV_PLAN.md` T1.2 | ✅（DEV-0326 修订行） |
| DEV_LOG 留痕 | `DEV_LOG.md` DEV-0326 条（下一可用号 DEV-0327） | ✅ |
| V0.8.5_PLAN 唯一权威 spec | 未提及 reaction 无域语义 → 无漂移，未触碰 | 未触碰（正确） |

## 验证证据

- 后端：`pytest backend/tests/test_interest_engine.py backend/tests/test_content_pref_auto.py` **58 passed**；`ruff check backend/` **All checks passed**。
- 架构门禁：`python3 scripts/generate_meta.py --check` **OK**（58 jobs / 19 collectors / 101 routers / 161 services，编号未变）。
- 前端：`npx tsc --noEmit` **0 err**；`npx vitest run` **102 files / 722 passed**。
- 回归测试：`test_interest_engine.py` — 原 `test_non_security_category_keeps_no_domain` 拆为「累计型仍 no_domain」+「reaction 落哨兵域 weight 0 / 回读保留 / aggregate 全 0」；`test_content_pref_auto.py` 新增「无域 reaction 不进 axis stats」泄漏面守护。

## 遗留与边界

- **未做**：哨兵域行不参与任何权重/排序计算，也不出现在 UI 权重条（`GET /api/interest/weights` 只吐 10 实践域）——有意为之。
- **无 schema 变更**：复用既有 `interest_signals` 表，未新增 migration，故架构数字门禁编号不变。
- **无路由/API 新增**：`POST /api/interest/signals` 端点未增删，仅语义分支扩展，故 V0.8.5_PLAN §6 接口消费表无需改动。

---

# PRD 对齐审计 — DEV-0327 Cubox「导入目录」支持本地化 .md (2026-10-13)

> 事项：`/knowledge` 导入页「导入目录」由「仅扫顶层 `*.json`」扩为「顶层 `*.json` + 递归 `*.md`」，并修复响应缺 `imported` 导致的「入库 0 条」误报。

## 裁决链

1. **2026-10-13 owner 输入**：「`button`导入没有反应，没有识别cubox本地化的md文档」。
2. **诊断（双根因，非单点）**：① 后端 `import_cubox_dir` 只 `p.glob("*.json")`（顶层），cubox 本地化知识库的 `.md` 被完全忽略；② `/cubox/import-dir` 响应未透传 `imported`，前端 toast 恒取 `?? 0` → 即便后端有入库也显「入库 0 条」。现象「0 文件 0 卡 → 入库 0 条」正是两者叠加。
3. **2026-10-13 owner 裁决**：`AskUserQuestion` 定目标目录 `/home/user/Documents/#书籍/Cubox`、修复范围「**支持 .md（推荐）**」。

## 前提纠偏（Rule 12）

- owner 初答「md 没有 frontmatter，只有正文」与实测**矛盾**：实测该目录首个 .md **有** YAML frontmatter（`title`/`cubox_id`/`source_url`/内联 `tags: [RAG, 应用, …]`/`created`/`updated`/`folder`/嵌套 `quality:`）。**未盲信错误前提**，按实测结构实现并按实测形状补测试。

## 设计要点

| 维度 | 决策 | 理由 |
|---|---|---|
| md 识别门槛 | 有 frontmatter 且含 `source_url`/`url` | 无来源 URL 的 md（index.md/WIKI.md）非卡片，静默跳过不计卡数 |
| 两形状兼容 | `_md_to_card` 取 `fm.get("source_url") or fm.get("url")` | 覆盖本地库（A）与 cubox-cli 导出（B）两形状 |
| 内联 tags | `_normalize_md_tags` 拆回 `list[str]` | `parse_frontmatter` 对 `tags: [a, b]`（非合法 JSON）退化为字符串，需自行拆分 |
| 响应契约 | 返回体补 `md_files`/`md_cards`/`imported` | 前端据真实 `imported` 报数，消除「入库 0 条」误报 |
| 时间字段兜底 | `_card_to_item` 用 `or` 链（`update_time or create_time or now_iso()`） | md 无 `updated` 时 `_md_to_card` 产出显式 `None`，绕过 `.get(k, default)` 回退 → `knowledge_items.updated_at` NOT NULL 崩溃；边界层根治并兼顾 JSON 链路同源风险 |

## 回写落点核对

| 回写项 | 位置 | 状态 |
|---|---|---|
| 权威 PRD 变更记录 DEV-0327 条 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 变更记录 | ✅ |
| DEV_LOG 留痕 | `DEV_LOG.md` DEV-0327 条（下一可用号 DEV-0328） | ✅ |
| V0.8.5_PLAN 唯一权威 spec | 未涉及导入三链路契约 → 无漂移，未触碰 | 未触碰（正确） |

## 验证证据

- 后端：`pytest backend/tests/test_cubox_import.py` **17 passed**；ruff 0（3 文件）。
- 架构门禁：`generate_meta.py --check` **OK**（58 jobs / 19 collectors / 101 routers / 161 services，未新增 router/service，编号未变）。
- 前端：`tsc --noEmit` **0 err**；`vitest run src/components/knowledge` **73 passed**。
- 迭代留痕：新增 md 用例首跑 3 failed（`IntegrityError: NOT NULL constraint failed: knowledge_items.updated_at`）→ 修 `_card_to_item` 时间兜底后全绿。

## 遗留与边界

- **未做**：`cubox_id` 去重键（当前以来源 URL 派生 `item_id`，与三条链路共用契约，未引入新主键）；md 内嵌图片/附件未导入（`description` 仅取 frontmatter 之后正文）。
- **无 schema 变更**：复用 `knowledge_items`，未新增 migration，架构数字门禁编号不变。
- **无路由新增**：`/api/knowledge/cubox/import-dir` 端点本体未变，仅服务层与响应体扩展，V0.8.5_PLAN §6 接口消费表无需改动。

---

# PRD 对齐审计 — DEV-0328 MP-2 事件类型实例化链路修复 (2026-10-13)

> 事项：通稿审核（`/action/events`）MP-2 事件类型实例化链路的四段断裂修复（采集→抽取→入池 + 前端契约 + 语料补种 + 契约测试）

## 裁决链

1. **2026-10-13 owner 输入**：「采用第一性原理分析通告审核实际的功能和目标，检查是否达到开发预期」→「根据当前问题制定修复计划」。
2. **第一性原理分析（实际功能 vs 预期）**：MP-2 **预期链路** = 「LLM 抽取 ATT&CK 技术候选 → 程序化校验（FK/substring/confidence≥0.4）→ 候选池（pending）→ owner 人工审定 → `event_technique_map` + `audit_log_mp2_review`」。**实测链路四段断裂**：① 无调度 job 生产候选（候选池恒空，人工审定无米下锅）；② 前端字段契约与后端不符（静默漂移）；③ 语料只种 A 类 5 子目录，B/C/D/E 6 类无 `event_types` 行；④ 无契约测试锁定，三处漂移无守卫。
3. **2026-10-13 owner 裁决**：`AskUserQuestion` —— 交付范围「**全做 A+B+C+D（推荐）**」；候选生产 A1「**接通调度 job**」；agent_B~E 脚本 A2「**改脚本对齐现有 service（推荐）**」（落地方式「**脚本+薄服务方法（推荐）**」）；A1 采集范围「**全部 agent_A~E（11 类）**」；LLM 模式「**真实 ai_hub LLM（失败自动降级 mock）**」。

## 设计要点（四段闭环）

| 段 | 断裂 | 修复 | 产出物 |
|---|---|---|---|
| A1 生产端 | 无调度 job | 新增 `mp2_extract_job`（`CronTrigger(3:30, Asia/Shanghai)`，归 `security_graph` gate），`_mp2_ingest_all()` **per-agent 路由** 覆盖 11 类，`_mp2_reports_with_candidates()` 增量过滤 | `jobs/security.py` / `scheduler.py` / `extensions/__init__.py` |
| A2 脚本 | 脚本接口陈旧 | `agent_{B,C,D,E}_extract.py` 改调既有 `event_technique_extract_service` | `scripts/agent_{B,C,D,E}_extract.py` |
| B 前端 | 字段名漂移 | `candidate_id`→`id`；batch 读 `approved_count`/`skipped_count` | `EventsReviewPage.tsx` |
| C 语料 | B/C/D/E 无 event_types | migration `135_...sql` 补 6 类 | `migrations/135_mp2_event_types_seed_bcde.sql` |
| D 契约 | 无锁定 + 文案 | docstring 端点数（六→七）/空态文案/UNIMPLEMENTED 台账；新建 `test_mp2_api_contract.py` 8 用例 | 测试 + API docstring + 文档 |

## 关键契约（测试锁定）

- **候选字段名** = **`id`**（后端权威；前端 `CandidateRow` 契约必须一致）；batch 响应 = **`approved_count`/`skipped_count`**（非 `approved`/`total`）。
- **approve 链前缀**：候选 `etc_` / 映射 `etm_`；审计 `action=="approve"`、`actor=="owner"`。
- **校验门限**：confidence < 0.4 → 400；未知 event_type → 404；重复 approve → 409；驳回空 reason → 422（pydantic `min_length=1`）。
- **per-agent 路由 11 类**：agent_A 5 子目录（evt_brute_force/evt_phishing_social/evt_ransomware/evt_supply_chain/evt_web_app_intrusion）+ agent_B 3 类（frontmatter `event_type_id`：evt_ai_model_poison/evt_cloud_misconfig/evt_insider_threat）+ agent_C（evt_fraud）+ agent_D（evt_data_breach）+ agent_E（evt_regulatory_notice）。

## 回写落点核对

| 回写项 | 位置 | 状态 |
|---|---|---|
| 权威 PRD 变更记录 DEV-0328 条 | `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 变更记录 | ✅ |
| DEV_LOG 留痕 | `DEV_LOG.md` DEV-0328 条（下一可用号 DEV-0329） | ✅ |
| 架构数字门禁（jobs 58→59） | AGENTS.md / CLAUDE.md / ARCHITECTURE.md 等 7 文档 | ✅（`generate_meta --fix` 同步） |
| UNIMPLEMENTED 台账（端点六→七） | `docs/UNIMPLEMENTED.md` | ✅ |
| V0.8.5_PLAN 唯一权威 spec | 未涉及 MP-2 job 注册/端点契约 → 无漂移，未触碰 | 未触碰（正确） |

## 验证证据

- 后端：`pytest backend/tests/` **5467 passed, 9 skipped**；`test_mp2_api_contract.py` **8 passed**；`ruff check backend/` **All checks passed**。
- 架构门禁：`generate_meta.py --check` **OK**（59 jobs / 19 collectors / 101 routers / 161 services，7/7 文档一致）。
- 资产门禁：`harness_analyze.py --check` **errors 0**（warnings 5 全 waived）。
- 前端：`tsc --noEmit` **0 err**；`vitest run` **102 files / 722 passed**；`vite build` **exit 0**。
- 迭代留痕：新增 job 后 `test_feature_gates` 硬编码 58 失效（`59 == 58` failed）→ 断言改 59 + docstring；B1/B2 前端契约修复后 colocated mock 仍旧字段名 → 2 failed → 修 mock（Rule 9）。

## 遗留与边界

- **未做**：候选池的真实 LLM 抽取质量调优（当前 ai_hub 失败降级 mock 仅保链路连通，不评估抽取准确率）；`_mp2_ingest_all` 语料根路径依赖既有约定，未新增配置项。
- **无新一级入口/新壳**：能力以 `/action/events` 通稿审核页区块进入（frontend/src/AGENTS.md 硬规则），未新增路由页面。
- **无新 router/service**：架构数字仅 job +1（58→59），routers/services 编号不变，V0.8.5_PLAN §5 路由表 / §6 接口消费表无需改动。
- **schema 变更**：新增 migration `135`（补种 event_types 行），非 schema 结构变更，仅数据种子。