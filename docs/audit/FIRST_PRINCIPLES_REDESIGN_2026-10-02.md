# Hotspot 第一性原理深度分析与架构优化方案

> **日期**: 2026-10-02
> **基线 commit**: `18dd6f3` (main，工作树仅 2 个前端文件未提交修改)
> **方法**: 5 路并行代码取证 (后端架构 / 管线可靠性 / 前端架构 / AI 层 / 安全数据层) + 生产库只读盘点 + 生产日志分类统计
> **性质**: 深度分析方案 (决策前文档)；**不修改**既有权威 PRD / spec，待 owner 裁决后按决策逐项回写
> **关联**: 取代并扩写 `docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md` (已废止)；与 `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` 互补 (本文提供诊断，PRD 提供产品定义)

---

## 0. 摘要 (一屏)

**一句话结论**: 这个项目已经不缺功能，缺的是**让已有功能产生可验证结果的那条主干**。当前系统在 24 天里用 405 次提交、20 万行后端代码、485 个端点，把一个安全从业者 24 天内的真实工作成果沉淀为 **0 个 Artifact、0 次 Run**。

**根因 (第一性原理层，三条)**:

| # | 根因 | 一句话表述 | 最硬证据 |
|---|------|-----------|---------|
| **R1** | **主干是旁路，不是干道** | 系统的"资讯→行动"主干流量接近于零，而支路（自我体检、索引维护、门禁写日志）以数千次/周期的量级空转 | 31,907 条 hotspots 只挤出 13 条 v1_signals (0.041%)；kl 管线 T1/T2/T3 共 **7,643 次** `candidates=0` 空转 |
| **R2** | **失败即沉默，成功即幻觉** | 坏结果被降级为"可接受结果"或根本不留痕，因此系统无法区分"没事发生"和"出事了" | `ai gate-detect failed: ReadTimeout` **1,006 次**仍 fail-open 放行；`no such table: warm.hotspots` **439 次**写入失败只留 WARNING；58 个定时任务中 **55 个** misfire 容忍默认 **1 秒** |
| **R3** | **控制面是散文，不是代码** | 配置、注释、文档描述的行为与实际执行路径脱钩，且无任何机制能发现脱钩 | `config/llm.yaml` 声称"yaml-only 改动 → deep_read 路由自动生效"，实际 router 选中的 model 被丢弃，deep_read 一直跑 flash-lite |

**第二层根因 (工程层，三条)**:

| # | 根因 | 硬证据 |
|---|------|--------|
| **R4** | 一个概念三套本体、三种门禁系统、两个配置真源 | hotspots 31,907 / v1_materials 14 / wiki md 4,348 互不相认；扩展 gate + `config.feature_*` 双门禁；`CORE_ROUTERS` 白名单 7 个假 member + 24 个漏登记 |
| **R5** | 只做加法，无删除纪律 | `SentinelJudgePage` 563 行不可达；`codegarden_scanner_service` 619 行无运行期引用；`v1_signals` 13 行 / 19 张 v1 表；1,019 处宽泛 `except Exception`（133 处静默吞掉） |
| **R6** | **安全边界是"可选启用"，且写入路径不原子** | 鉴权中间件只覆盖 `/api/*`（`/mcp/sse` 19 个含写工具默认开启且绕过）；迁移器把 `duplicate column` 当"已应用"记录版本后**跳过文件剩余全部语句**；sync 应用无事务却把整包记为成功 |

**最危险的 3 条已核实缺陷 (本次审计新增，优先级高于功能)**:

| # | 缺陷 | 位置 | 后果 |
|---|------|------|------|
| **S1** | `TokenAuthMiddleware` 对非 `/api/` 路径直接放行；`/mcp/sse` 挂在 `/mcp/sse` 且 `feature_mcp=True` 默认开启，暴露 19 个工具（含 `wiki_write` / `update_knowledge_item`） | `api/middleware.py:184`、`api/mcp_config.py:122`、`config/__init__.py:117` | 设了 token 也**没锁住写入口** |
| **S2** | 迁移器 `if "duplicate column" in msg:` → 记录版本 + `continue`（跳过该文件剩余语句） | `repository/db.py:326-337` | 未来任何"已存在列 + 后续语句"的迁移会**静默半应用且永久标记完成** |
| **S3** | `apply_bundle` 逐条写库无 `BEGIN`，随后把整包记为 merge base | `services/sync_bundle.py:687-760` + `sync_service.py:377-379` | 中途崩溃 → 本地缺失但 base 声称存在 → **远端记录永久静默丢失** |

**核心建议 (不是"重写"，是"换主干")**:
不再新增域，而是把系统从"**记录型平台**"改造成"**证据账本 + 一条可验证工作循环**"：
1. **一条主干**: Material → Signal → Case → (Judgment | Action) → Run → Artifact → Knowledge，且每一步都有 run record 与证据引用；
2. **一个控制面**: 单一声明式 manifest 驱动路由 / 门禁 / job / 前端面，CN 门禁保证四者不漂移；
3. **一条铁律**: **模型永不宣称成功** —— 只有 harness 能判定 done/failed/partial，且必须落账。

**AI Native 补充卷**: [AI_NATIVE_DESIGN_2026-10-02.md](AI_NATIVE_DESIGN_2026-10-02.md) —— AI 层专项设计。

核心判断：当前 AI 是**事后加速器**（在采集打标 / 摘要 / 分类 / 拒绝原因等旁路工作），不是**结构本身**（研判与行动环节几乎空白，各只有 1 条 skill 路径）。
AI Native 的落地形态是 **Proposal (提案) 账本**：AI 唯一的一等产出物是**带证据引用、置信度、未知项、模型与提示版本的草稿态领域对象**；AI 永不直接写事实、永不宣称完成；人的采纳 / 拒绝 / 修改**连同理由**沉淀为审计证据与改进信号。
最关键的一点：这个系统**已经无意中做对过** AI Native 的样子 —— `parse_cve_impact_brief_response` 的 schema 化判断（含 `evidence_refs`/`counter_evidence_refs`/`unknowns`）、`knowledge_ai` 的证据哈希校验与条件化硬约束、`auto_classifier` 的"规则优先 + 白名单采纳 + fail-safe"、以及 `domain/v1_0_models.py` 的 `Judgment` 类型本身。**所以 AI Native 不是加功能，是把这 4 个局部正确模式提升为平台级不变量。**

---

## 1. 方法与判据 (第一性原理在这里怎么用)

### 1.1 从"安全从业者实际在做什么"往回推

不先问"系统有什么功能"，先问"这个人在产出什么、卡在哪"。

安全从业者 (研究 / 运营 / 合规 / 管理) 的每一天实际在做四件事：

1. **观察**: 读到值得注意的信号 (漏洞、情报、开源工具、监管动态、风险趋势)；
2. **判断**: 形成一个**要在别人面前站得住的结论** —— 这是整个职业的瓶颈，不是信息获取；
3. **行动**: 在明确边界内执行 (复现、处置、整改、评审)；
4. **复用**: 把这次判断和行动的边界条件留给下一次。

关键洞察：**第 2 步是全链路瓶颈**。信息从来不缺，缺的是"结论 + 证据 + 边界"三件套。因此这个系统的不可约产出物不是资讯列表，而是：

> **一条带证据、带责任人、带规则版本、带结果状态的判断链。**

### 1.2 不可约产出物 (irreducible artifact)

一个安全从业者工作台的**最小完备数据模型**只有 6 个概念：

| 概念 | 定义 | 不可省的原因 |
|------|------|------------|
| **Source** | 原始资料 (含 URL / 抓取时间 / 哈希) | 没有来源，结论不可辩护 |
| **Signal** | 通过门禁、被判定"值得占用注意力"的最小单元 | 门禁结论本身就是审计对象 |
| **Case** | 一个"需要有人负责"的工作单元 | 责任必须可归属 |
| **Claim** | 一个有证据引用的判断 (Judgment)，或一个待执行动作 (Action) | 结论与动作是两种不同承诺 |
| **Artifact** | 可验证的产出物 (含哈希 / 版本 / 验收状态) | 没有产物就没有"完成" |
| **Knowledge** | 带适用条件与失效期的可复用经验 | 无条件经验等于噪声 |

**注意**：`Run` 不是第 7 个概念，而是**贯穿上述每一步的执行账本 (execution ledger)** —— 这一点是本方案与现有实现的关键分歧 (现有实现把 Run 当成 Action 的附属表，导致它永远为 0 行)。

### 1.3 四条守恒律

| # | 律 | 表述 | 违反时会发生什么 |
|---|----|------|----------------|
| **L1** | **溯源律** | 任何结论必须能沿引用链回溯到原始资料 | 结论不可辩护，系统退化为浏览器书签 |
| **L2** | **可证伪律** | 系统必须能区分"没事发生"与"出事了"；失败必须显式且可归因 | 静默降级堆积，运维凭运气 |
| **L3** | **人主律** | 模型只能产出**提案 (proposal)**，不能产出**事实 (fact)**；所有权必须留在人 | 幻觉被当成结论发布，责任链断裂 |
| **L4** | **删除律** | 不能被删除的东西不能被信任；无删除/归档语义的系统只能增长 | 复杂度单调递增，最终无人能改 |

### 1.4 五条架构判据 (用来给每个模块打分)

| # | 判据 | 反例特征 |
|---|------|---------|
| **C1** | **单一真相源** | 同一概念两套表示，且互不连通 |
| **C2** | **单向依赖** | HTTP 层直接 import 数据层；service 互相 import 成网 |
| **C3** | **失败显式** | `except Exception: pass`；默认值冒充真实值 |
| **C4** | **可观测** | 有 job 无 run record；有门禁无拒绝原因；有降级无状态位 |
| **C5** | **契约可验证** | 前端类型手写；后端契约无 CI 校验；配置改动能被静默忽略 |

---

## 2. 事实基线 (2026-10-02 实测，可复现)

### 2.1 规模与构成

| 维度 | 数值 | 备注 |
|------|------|------|
| 后端 `.py` | 938 文件 / 204,919 行 | 生产 555 文件 / 114,073 行 |
| 后端测试 | 383 文件 / 90,846 行 | 测试/生产 = **0.80** |
| 前端 `.ts/.tsx` | 358 文件 / 63,527 行 | 297 `.tsx` (含 93 测试) |
| 文档 `docs/*.md` | **72,495 行** | 与生产代码比 = **0.64** |
| 采集器 / 门禁 / job / 服务 / router | 14 / 13 / 58 / 153 / 91 | `generate_meta.py --check` 通过 |
| API 端点 | **485** (GET 247 / POST 175 / PUT 21 / PATCH 18 / DELETE 24) | `backend/api/` |
| 迁移 | 127 个 SQL (编号 001–130，有空洞) | 无 schema version 快照 |
| 前端路由 | 63 声明 → **47 可达** / 14 重定向 / **2 个被自身遮蔽** | `/judge`, `/judge/graph` |
| 提交 (总 / 近 30 天) | 875 / **405** | DEV-0247 为最新 |

### 2.2 生产数据 (只读盘点)

**HOT 库** `backend/hotspot.db` (101 MB)：

| 表 | 行数 | 解读 |
|----|------|------|
| `hotspots` | **31,907** | 采集侧丰产 |
| `wiki_items_fts` | 7,848 | FTS 条目 |
| `v1_evidence_receipts` | 51 | 唯一有真实流量的 v1 表 |
| `v1_outbox` | 192 | 事件外发队列 |
| `v1_materials` | **14** | 24 天累计 |
| `v1_signals` | **13** | 24 天累计 |
| `v1_cases` | 5 | |
| `v1_judgments` / `v1_actions` / `v1_knowledge` | **1 / 1 / 1** | |
| `v1_runs` / `v1_artifacts` | **0 / 0** | **主干从未跑通一次** |
| v1 表总数 | 19 | 生产占用总量 < 100 行 |

**WARM 库** `backend/hotspot-warm.db` (199 MB)：`knowledge_items` **4,348** 行。

**md 真源** `llm-wiki-2.0/`：`items/` **4,348** 个 `.md`，`concepts/` 165 个。

**最刺眼的一组对比**：

```
采集侧产出       31,907 条 hotspots
主干侧承接           13 条 v1_signals      → 转化率 0.041%
执行侧产出            0 条 v1_runs / v1_artifacts
```

**v1_signals 的时间分布** (按天)：

```
09-08: 3   09-11: 1   09-13: 1   09-14: 1   09-16: 1   09-17: 1
09-19: 1   09-23: 1   09-26: 1   09-29: 1   09-30: 1
```

近似"每天恰好 1 条"，且 v1_ingest_bridge 自 **2026-09-08** 就在运行（`git log --diff-filter=A` 确认）。这条曲线不是"偶发断流"，是一条**结构性的涓流**（节流成因需单独定位，见 §7 待裁决项）。

### 2.3 生产日志分类 (当前 `app.log`，51,601 行 / 44 MB)

| 级别 | 次数 |
|------|------|
| INFO | 45,288 |
| WARNING | **6,295 (12.2%)** |
| ERROR | 3 |

**Top 消息类 (归一化后)**：

| 消息 | 次数 | 性质 |
|------|------|------|
| `auto_extract_job: extracted 20 hotspots` | 4,864 | INFO 噪声 |
| `alert_evaluator_job: evaluated 50 hotspots` | 4,864 | INFO 噪声 |
| `collect_start` | 4,839 | INFO 噪声 |
| `kl_trigger_t1_job: candidates=0 advanced=0 ... failed=0` | 4,793 | **空转** |
| `kl_trigger_t2_job: candidates=0 ...` | 2,395 | **空转** |
| `no sources configured, returning []` | 1,961 | **配置盲区** |
| `ai gate-detect failed (sensenova): ReadTimeout` | **1,006** | **静默降级** |
| `all 1 sources failed, returning []` | 939 | 采集失败 |
| `_write_fingerprints failed: no such table: warm.hotspots` | **439** | **写库失败** |
| `kl_trigger_t3_job: candidates=0 ...` | 455 | **空转** |
| `write quality log failed: no such table: quality_check_logs` | 多批 | **门禁审计落库失败** |
| `kl_trigger_t1_job crashed: no such table: warm.knowledge_items` | 见日志 | **job 崩溃** |

**kl 管线空转合计**: `candidates=0` 共 **7,643 次**。

**日志存储**: `backend/logs/` = **293 MB**，`rotation=50MB` / `retention=5`，全量 JSON 序列化，级别默认 INFO。

### 2.4 关键单点证据 (每条均在本次审计中直接核对源码)

| # | 事实 | 位置 | 影响 |
|---|------|------|------|
| **E1** | router 返回 `(provider, model)`，`_try_order` **只取 `routed[0]`**，`_resolve_model` 改读 `cfg.models.*` | `ai_hub/gateway.py:181-184`、`:844-857` | `task_overrides` 的 model 全部失效；deep_read 实际跑 `sensenova-6.8-flash-lite` 而非 `deepseek-v4-pro` |
| **E2** | `check_credential_egress` 仅在 2 处调用；`image_service` 直接拼 `Bearer <key>` | `ai_hub/gateway.py:671,767` vs `image_service.py:88,182` | 5 条带凭据路径中 3 条无出站门禁 |
| **E3** | `score` 解析失败回落 `DEFAULT_SCORE 5.0` 并缓存、记 `ok=True` | `ai_hub/prompts.py:71-77`、`gateway.py:270-278` | 模型拒绝/超时被记成"评分 5.0 成功" |
| **E4** | APScheduler 3.11.3 `misfire_grace_time` 默认 **1 秒**，58 个 job 只 3 个覆盖 | 实测 `apscheduler/schedulers/base.py::_configure`；`scheduler.py:70-74,378,396,405` | 55 个 job（含 `collect_all`）错过即静默丢弃，无补跑无记录 |
| **E5** | 58 个 job 中仅 8 个有 `@instrument_job`，`job_runs` 表**无任何 API 读取** | `scheduler/jobs/maintenance.py:91-581` | 调度层整体不可观测 |
| **E6** | `_bulk_syncing` 无 `try/finally`，异常后永久为 True，`_log_wiki_event` 静默返回 | `services/knowledge_sync.py:342-351`、`:77-78` | wiki↔DB 事件桥可静默死亡 |
| **E7** | 孤儿清理无条件删除 md 中不存在的 `knowledge_items` 行 | `services/knowledge_sync.py:352-357` | DB-only 写入的行会被静默删除 |
| **E8** | `knowledge_items` 26 列，`upsert_item` 只写 16 列，`write_item_to_md` 省略 `entities`/`compiled`/`body`/`attention_score` | `repository/knowledge_repo.py:41-60`、`knowledge_sync.py:275-294` | **投影不可从 md 完整重建**，违背 wiki-first |
| **E9** | `api/event_types_api.py:58` 使用未导入的 `ConflictException` | 同文件 `:22` 只导入 2 个异常 | 409 路径实际抛 `NameError`（ruff `F821` 已捕获但未阻断） |
| **E10** | `/judge` 与 `/judge/graph` 各声明两次，扁平 redirect 先匹配胜出 | `routes/index.tsx:112,114` vs `:121,122` | `SentinelJudgePage` 563 行不可达；3 个页面仍链接过去 |
| **E11** | `CORE_ROUTERS` 44 项中 7 项实为 feature-flag 注册，24 个无条件注册模块未登记；断言只查重叠不查完整性 | `core/routers.py:10,32`、`api/_registry.py` | 白名单纪律形同虚设，漂移不可检测 |
| **E12** | 前端无状态库，86 个组件文件直发 223 次 API 调用；32 个端点被多文件重复拉取 | 前端取证 | 无缓存/去重/失效图；24/65 个 fetch effect 有竞态 |
| **E13** | 门禁双错误策略：pipeline fail-closed (-15 分) vs `BaseGate._wrap_exception` fail-open (passed=True) | `quality/pipeline.py:142-154` vs `quality/base.py:76-81` | 同一个门禁异常，结论相反 |
| **E14** | 拒绝日志无 `item_id`，`raw_data` 从不写入 | `migrations/055:130-138`、`quality_hook.py:253-266` | **误拒不可复现、不可回放** |
| **E15** | `quality_check_logs` / `warm.hotspots` 表在生产日志中被报告"no such table" | 生产日志 | 门禁审计与指纹去重两处写路径实际失效 |
| **E16** | `TokenAuthMiddleware` 对 `not path.startswith("/api/")` 直接 `call_next`；`/mcp/sse` 默认开启且暴露 19 个工具（含写） | `api/middleware.py:184`、`api/mcp_config.py:122`、`config/__init__.py:117` | 设 token 也锁不住写入口 |
| **E17** | 迁移器把 `duplicate column` 视为"迁移已应用"，写入版本后 `continue`（跳过该文件剩余语句） | `repository/db.py:326-337` | 迁移可静默半应用且永久标记完成 |
| **E18** | `apply_bundle` 无 `BEGIN`，随后把整包记为 merge base | `sync_bundle.py:687-760` + `sync_service.py:377-379` | 崩溃即永久静默丢失远端记录 |
| **E19** | `warm.knowledge_items`(4,348 行) 无索引；索引建在空表 `main.knowledge_items` 上（迁移 063 裸 `CREATE INDEX` 解析到 main） | `EXPLAIN QUERY PLAN` 实测 `SCAN` | 每个管线 tick 全表扫描 |

---

## 3. 诊断：十九条证据，收敛为六个根因

### 3.1 R1 —— 主干是旁路，不是干道

**现象**：系统有两条流量曲线，量级差 3 个数量级。

```
支路（空转）:  kl T1/T2/T3 空转 7,643 次  |  auto_extract 4,864 次  |  alert_evaluator 4,864 次
主干（真实）:  v1_signals 13 条  |  v1_cases 5 个  |  v1_runs 0 次  |  v1_artifacts 0 个
```

**机理**：系统把"维持自身运转"（提取标签、评估告警、推进管线阶段、重建投影、扫描服务网格）当成了主业，把"用户真正要完成的安全工作"当成了副产品。每一次采集周期结束，11 个后置 job 依次运行，其中大部分结果是 `candidates=0`，但都成功返回。**系统在为自己的仪表盘生产数据。**

**第一性原理违反**：`L1 溯源律` + `L4 删除律`。用户的工作主线（把一条资讯变成一份可交付的判断）没有形成流量，而支撑主线的支路被无节制地保留和调度。

**判定**：这是**产品缺口**，不是性能问题。增加采集源、加更多门禁、加更多 skill 都不能修复它——因为下游根本没有承接能力（`v1_runs` 无执行体）。

---

### 3.2 R2 —— 失败即沉默，成功即幻觉

这是本次审计中**证据最密集**的一条。系统的失败处理模式是"降级并继续，不留痕"：

| 失败类型 | 实际处理 | 用户看到 |
|---------|---------|---------|
| AI 门禁超时 (1,006 次) | fail-open 放行 | "语义门禁已启用" |
| 写入 `warm.hotspots` 失败 (439 次) | WARNING | 无 —— 指纹去重静默失效 |
| 门禁审计落库失败 | WARNING | 门禁统计页照常显示 |
| 模型拒绝/超时 | 回落到 `DEFAULT_SCORE 5.0` + `ok=True` | "评分 5.0" |
| job 错过触发 (55/58 个 job) | APScheduler 静默丢弃 | `next_run_time` 照常推进 |
| fetch 抛异常 | `return_exceptions=True` + `continue`，不追加 `SourceResult` | 源健康度**不计失败** |
| 全源失败 | 提前 return，`last_source_results` 保留上一轮 | `crawler_runs` 记录**上一轮的成功** |
| `_bulk_syncing` 卡死 | 永久 True，事件桥静默停止 | 无 |

**关键洞察**：这不是"错误处理写得不够好"。这是**系统缺少一个失败分类器**。全仓 1,019 处宽泛 `except Exception`，其中 **133 处完全不打日志**（`services` 72、`repository` 48）。

**第一性原理违反**：`L2 可证伪律` + 判据 `C3 失败显式` + `C4 可观测`。

**产品后果 (最严重)**：正因为失败不可见，"主干没跑通"这件事被隐藏了 24 天。`v1_runs` 为 0 行这件事，如果有一个诚实的失败面板，第一天就会暴露。

---

### 3.3 R3 —— 控制面是散文，不是代码

系统有大量**声明**与**实现**脱钩，且脱钩不可检测：

| 声明 (出处) | 实现真相 |
|------------|---------|
| "yaml-only 改动 → deep_read 路由自动生效" (`config/llm.yaml:136-137`) | router 的 model 被丢弃 (E1)，改 yaml 无效 |
| `task_overrides.*.max_tokens` / `temperature` | 完全未被消费 (`route_model` 返回 2-tuple，4 个循环都不传) |
| "ai_hub 唯一入口，禁绕过" (`AGENTS.md`) | SDK 层成立（0 处 `import openai`），但 HTTP 层 3/5 路径绕过 (E2) |
| `CORE_ROUTERS` = "永远注册"白名单 | 7 假 / 24 漏 (E11) |
| "wiki-first: md 是真源，SQLite 是投影" | 投影不可完整重建 (E8)，且会静默删除 (E7) |
| `dsh` 降级链 `not_configured→mock→ai_hub` | `DshRuntime.execute_with_fallback` **零生产调用方** |
| 文档 `ARCHITECTURE.md` 描述 6 个子系统（含 CRM） | CRM 已随 migration 116 删除；该文档头部状态为 2026-08-28 |
| `scheduler.py:21` 注释 "default 300s" | 实际 `collect_interval_seconds=1800` |
| `ai_classify` gate **声明开启** + 扩展登记 + 43 行测试全绿 | 唯一消费点 `classify_item_with_ai` **零生产调用方** —— 自 2026-09-19 开闸以来从未执行（详见 AI Native 补充卷 §2.5） |
| `feature_gates.toml:22-24` 称 agent_loop / playbook_engine / skill_eval "无 router/job/API 消费点" | 对 `playbook_engine` **已过期**（经 CodeGarden 接线）；对 `agent_loop` **不精确**（经 skill_runner 传递可达） |

**第一性原理违反**：判据 `C1 单一真相源` + `C5 契约可验证`。

**为什么这条最危险**：它让**文档成为负资产**。72,495 行文档里，读者无法判断哪一句是真的。这会直接导致下一个接手者（或下一次 AI 辅助开发）基于错误前提做决策——本次审计中就有多处"文档说已修，代码说没有"。

**比文档过期更坏的一种形态：三元一致的假象。** `ai_classify` 同时满足三个可信信号 —— gate 声明为 `true`、扩展登记存在、测试全绿 —— 却因为缺一个调用方而从未运行。**任何单独一项检查都发现不了它，只有"声明 → 消费点可达性"的端到端验证能发现。** 这是 `C5 契约可验证` 缺失的直接后果，已立项为 `AIN-16`（声明即验证 CI 门禁）。

---

### 3.4 R4 —— 一个概念三套本体、三种门禁、两个配置真源

```
                    ┌─ hotspots (31,907 行)  ← 采集侧
同一批资讯 ─────────┼─ v1_materials (14 行)   ← 主干侧
                    └─ llm-wiki-2.0 md (4,348) ← 知识侧
```

三者之间**没有共享 ID**。`v1_ingest_bridge` 和 `auto_recall_for_case` 只是局部桥接，且 `auto_recall_for_case` 只搜 `v1_knowledge`（1 行），不搜 wiki 全文也不搜 hotspots。

配套的重复结构：

| 维度 | 重复 |
|------|------|
| 门禁系统 | 扩展 gate (`feature_gates.toml`, 16) × 每功能 `config.feature_*` 标志 |
| 配置真源 | `config/llm.yaml` × `settings.kv` × env（四级链） + 两套 provider 解析 (`_try_order` / `_resolve_provider`) |
| 领域对象 | v1 九对象 × wiki `knowledge_items` × `hotspots` |
| 前端 `secnews` 与 `sentinel` | 20 个组件域并存，`secnews/` 测试覆盖 19% |
| 时间工具 | `_now_iso` 在 22 个文件里各写一遍 |
| CodeGarden CRUD | `create_service` / `create_resource` / `list_projects` / `list_services` / `list_resources` AST 体相同 |

**第一性原理违反**：`C1 单一真相源` + `C2 单向依赖`（35 个 API 文件直接 import repository）。

---

### 3.5 R5 —— 只做加法，无删除纪律

| 证据 | 规模 |
|------|------|
| 不可达页面 `SentinelJudgePage` + 其测试 | 563 + 353 行 |
| 无运行期引用的 `codegarden_scanner_service.py` | 619 行 |
| 无调用方的 `cost_monitor.py` / `feedback_analyzer.py` | — |
| 只在测试/脚本中被引用的 `pi_adapter.py` | — |
| `Skill*` 家族包 (registry/builder/eval/runner/trigger_gate/triggers/playbook/agent_loop/agent_memory) | **9 个包 / 10,843 行** |
| 平台自检类 skill 占比 | 26 个 skill 中 14 个 (54%) 是系统自我体检 |
| 文档中已 superseded 但仍在仓 | 12+ 份 |
| 日志存储 | 293 MB / 月 |

**第一性原理违反**：`L4 删除律`。**不能被删除的东西不能被信任** —— 因为无法判断它是否还在被依赖，于是所有人都选择保留，复杂度单调递增。

**注意 Skill* 家族**：9 个包共 10,843 行，本质上是一个**内建 agent 平台**。而它的用户只有一个人，且主干（`v1_runs`）从未跑通。按 §5.4 的删除判据，这是最优先的收敛对象。

---

### 3.6 R6 —— 安全边界是"可选启用"，写入路径不原子

安全侧的真实强项需要先如实记录（避免误判为全面失守）：SSRF 门禁 `utils/url_safety.py`（DNS 钉扎 + 内网 IP 阻断）已用于采集器/告警通道/探测；dsh 命令 argv 白名单化；wiki 读写路径经正则 + realpath 双重守卫；全仓无 `pickle` / `eval` / `yaml.load`（仅 `safe_load`）；SQL 全参数化（f-string 只插内部表名常量）；PBKDF2-HMAC-SHA256 600k → Fernet，密钥学原语正确；`.env` 为 0600。

但边界**以"可选"方式实现**，并在三处出现真正的破口：

| 严重度 | 缺陷 | 位置 |
|--------|------|------|
| **HIGH** | `/mcp/sse` 绕过唯一鉴权（非 `/api/` 前缀直接放行），默认开启，19 工具含写入 | `middleware.py:184`、`mcp_config.py:122` |
| **HIGH** | 正文抓取无 URL 校验 + `ssl=False`；其前置校验门 `URLValidityGate` 已从管线移除 → 可读回内网响应（SSRF + TLS MITM） | `quality/url_content_gate.py:40-46`、`quality/pipeline.py:101-104` |
| **HIGH** | 迁移器把 `duplicate column` 当作"迁移已应用"并 `continue`，跳过文件剩余语句且永久记录版本 | `repository/db.py:326-337` |
| MEDIUM | sync 应用无事务，却把整包记为 merge base → 崩溃即永久静默丢数据 | `sync_bundle.py:687-760`、`sync_service.py:377-379` |
| MEDIUM | 生产 `warm.knowledge_items`（4,348 行）**无任何索引**（索引建在空表 `main.knowledge_items` 上）→ 每个管线 tick 全表扫描 | `EXPLAIN QUERY PLAN` 实测 `SCAN` + `TEMP B-TREE` |
| MEDIUM | 库文件与备份 0644 / 目录 0755，含 `llm_secrets` 密文与全量 wiki 正文；WebDAV 远端推送**除密钥外全部明文** | `backup_service.py:93-137` |
| MEDIUM | `HOTSPOT_DB_PATH` 为相对路径而 warm/cold 为绝对 → 换 CWD 启动会打开一个**全新空库**却 ATTACH 真实 warm 库（磁盘上已有 0 字节 `data/hotspot.db` 为证） | `config/__init__.py:41-50` |
| MEDIUM | `restore_from_backup`（覆盖线上库 + 解压知识包）**无测试、无 CI、演练仅为人工 runbook**；而 DB 损坏时 `init_db` 直接 raise，无自动回退到最新快照 | `backup_service.py:224-249`、`db.py:466-480` |

**第一性原理违反**：`L2 可证伪律`（迁移器与 sync 都制造"失败但记录成功"）+ `C1 单一真相源`（索引建错库、相对/绝对路径混用）。

**结论**：安全不是"加一个中间件"的问题，而是**边界必须在唯一的、默认关闭的入口上强制**，且**任何声称成功的写入必须先原子提交**。

---

## 4. 目标架构 (to-be)

### 4.0 一句话

> 从"**记录型平台**"改为"**证据账本 (evidence ledger) + 一条可验证工作循环**"：
> 每个工作单元都产生一条 run record；每个结论都带证据引用；每个失败都显式且可归因；每个概念只有一个身份。

### 4.1 分层重定义 (替换现有五子系统叙事)

```
L0  Source Layer     采集与准入        产出: Source + Signal        (已有，需收敛)
L1  Ledger Layer     证据账本与工作单元 产出: Case + Claim + Run      (需重建为主干)
L2  Substrate Layer  知识基质          产出: Knowledge (md 真源)     (已有，需修投影契约)
L3  Control Plane    声明式控制面      产出: manifest → 路由/门禁/job/UI  (需新建)
L4  Presentation     四菜单表现层      产出: 用户可见状态            (已有，需收敛)
```

**关键改动**：把 **Run 从 Action 的附属表提升为贯穿 L1 的执行账本**。

```
Case ──1:N── Claim ──1:N── Run ──1:N── Artifact ──1:N── Knowledge
                │           │
                └─ evidence_receipts (引用 Source/Signal 的最小单元)
```

每一个 Run 记录必须包含：`{actor, input_ref, plan_ref, policy_version, started_at, ended_at, outcome ∈ {done,failed,cancelled,timeout,needs_human}, reason, cost, artifacts[]}`。

**禁止**：`outcome` 允许"成功但没产物"这种状态存在。

### 4.2 控制面：单一声明式 manifest (治 R3、R4)

把所有"哪些模块存在、归哪个 gate、对应哪个 job、暴露给哪个菜单"收敛到**一张表**：

```toml
# backend/config/manifest.toml  (示意)
[[domain]]
name = "v1_evidence"
gate = "core"                    # core | <extension gate name>
routers = ["case_api", "judgment_api", "action_api", "run_api", "artifact_api", "knowledge_api"]
jobs = ["v1_signal_intake_tick"]
ui = { menu = "action", surface = "CaseQueuePanel" }
jobs_policy = { misfire_grace_time = 900, coalesce = true, max_instances = 1 }
```

由它**生成**三样东西：
1. `register_all()` 的路由注册（含门禁条件）；
2. `CORE_ROUTERS` / `EXTENSION_ROUTERS`（消除 E11 漂移）；
3. 前端菜单归属表（消除 E10 类遮蔽与 `menuOf()` 矛盾）。

**CN 门禁**（新增 CI 步骤，`--check` 模式）：
- manifest 与 `_registry.py` 实际注册模块双向一致；
- 每个 job 必须在 manifest 声明 `misfire_grace_time`（消 E4）；
- 每个 router 模块名、每个 gate 名必须在 manifest 出现，无孤儿。

### 4.3 契约优先 (治 R3、R4)

| 契约 | 现状 | 目标 |
|------|------|------|
| 前后端接口 | 无生成、无 CI 校验 | FastAPI `openapi.json` 导出为前端类型；CI 比对（`check_v1_endpoint_parity.py` 已有雏形但**不在 CI**） |
| 数据 schema | 启动期逐条跑 127 SQL，无版本快照 | 生成 `schema_snapshot.sql` 入仓，CI 比对；迁移编号连续性强校验 |
| 状态机 | 散落在各 service | 每个域对象显式状态机 (单文件)，状态转移集中定义 |
| 配置 | yaml 散文 | 配置项有 schema + 消费点登记表；CI 检查"声明即被消费" |

### 4.4 AI 层：单出口 + 不宣称成功 (治 R2、R3)

```
                   ┌──────────────────────────────────────┐
   所有 LLM 调用 ─→│  gateway (唯一出口, 唯一记账点)        │
                   │  1. policy snapshot (审批时冻结)      │
                   │  2. egress guard (100% 覆盖)          │
                   │  3. model 解析 (单点, 含 task_overrides)│
                   │  4. 输出 schema 校验 + 拒绝检测        │
                   │  5. run record (含 token/cost/latency) │
                   └──────────────────────────────────────┘
```

五条硬规则：
1. **只有 gateway 能带凭据出站** —— 删除 `AIService._call_sensenova_*` 的自建 httpx 路径，`image_service` 改走 gateway；加 AST 门禁禁止新增裸 httpx 带 key 调用。
2. **模型永不宣称成功**：任何解析失败、拒绝、截断、超时 → `outcome=failed`，**不缓存、不回落默认值**。`DEFAULT_SCORE 5.0` 必须删除，改为显式 `verdict=unknown`。
3. **prompt 即代码**：prompt 版本号入 `llm_usage_log`，可追溯"这条判断是哪个 prompt 产出的"。
4. **不可信内容隔离**：采集来的正文在 prompt 中用明确分隔符包裹并加层级声明；AI 输出必须经 schema 校验后才允许落库。
5. **成本真实**：token 用 provider 返回的 usage，不用 `len/4` 估算；`cost_alert` 从只读变阻断。

### 4.5 数据层：一个概念一个身份 (治 R4)

| 层 | 库/位置 | 内容 | 语义 |
|----|---------|------|------|
| **HOT** | `hotspot.db` | 工作台当前态：sources/signals/cases/claims/runs/artifacts | 唯一可写业务库 |
| **WARM** | `hotspot-warm.db` | 档案：历史 raw_items / 归档 / 大表 | **只读**，禁裸写（现有 `warm.hotspots` 写失败即是违反） |
| **COLD** | `hotspot-cold.db` | 审计与归档 | 只读 |
| **MD** | `llm-wiki-2.0/` | 知识正文真源 | 唯一真源 |

**三条不可违反的规则**：
1. **禁止裸表名跨库引用**：所有跨库访问必须走 `knowledge_items_table()` 这类 accessor（已有先例，需强制）；`warm.X` 字面量出现即 CI 失败。
2. **投影必须可重建**：`md → SQLite` 的投影必须无损覆盖所有"可由正文推导"的列。`entities`/`compiled`/`body`/`attention_score` 要么写进 md frontmatter，要么明确标注为"派生缓存，可丢"（E8）。
3. **删除必须显式且可审计**：孤儿清理改为 `dry-run + 计数上限 + 审计日志`，禁止无条件删除（E7）。

### 4.6 观测层：一个 job = 一条 run record (治 R2)

用**统一的 run record** 替换当前"每个 job 各自打日志"的模式：

- 每个 job 自动记 `{job_id, started_at, duration_ms, outcome, reason, counts}`；
- `misfire_grace_time` 与 `max_instances` 必须显式声明（manifest 强制）；
- 新增 `GET /api/ops/runs`（分页 + 过滤 + 失败优先）；
- **健康面板以失败为中心**：默认视图是"过去 24h 有什么失败了/降级了/静默了"，而不是"服务在运行"。

**日志降噪**（治噪声）：把"成功且无异常"的例行 job 降为 DEBUG，只保留状态变化与异常；`rotation=50MB` 保留但级别收敛后预计降一个数量级。

### 4.7 前端：一个状态层、一条路由表 (治 R4、R5)

| 现状 | 目标 |
|------|------|
| 86 文件 / 223 次直接 API 调用 | 统一 server-state 层（TanStack Query 或等价 150 行实现） |
| 4 套 realtime（含 1 处裸 EventSource + 1 处模块级单例） | 1 套，全站唯一 |
| 63 路由声明 / 47 可达 / 2 遮蔽 | 1 path 1 声明，路由表驱动 `menuOf`，CI 断言可达性 |
| 195 CSS 变量 / 104 个在多文件重复定义 | 变量单点定义 + CI 检测重复 |
| 1,692 处硬编码中文 / 19 处 i18n 使用 | 二选一：要么真做 i18n，要么移除 i18n 层（不要半吊子） |
| 5 个 700+ 行"上帝页" | 每页 < 300 行 + 逻辑抽到 hook/lib |

---

## 5. 业务流重设计

### 5.1 主干流 (替代现有三条互不连通的流)

```
① 采集 ──→ Source (含 hash/时间/来源)
              │
② 门禁 ──→ Signal  ✅ 门禁结论 = 可审计记录 (含拒绝原因 + item_id, 可回放)
              │
③ 承接 ──→ Case    ⚠️ 必须人工确认 (L3 人主律); AI 只产出"草案 + 推荐理由"
              │
④ 研判 ──→ Claim   (Judgment: 带 evidence_receipt 引用)
              │
⑤ 行动 ──→ Run     (Action 经审批 → 执行计划冻结 policy_version → 执行)
              │
⑥ 产出 ──→ Artifact (含 hash + 验收状态; 不可验证则不能算完成)
              │
⑦ 沉淀 ──→ Knowledge (带适用条件 + review_at + 采用回执)
              │
⑧ 复利 ──→ 下一次 ③ 自动浮现 + 采用回执 ⇄ 更快的 ①
```

**每一环的退出条件 (可验证, 不可宣称)**：

| 环 | 退出条件 | 当前状态 |
|----|---------|---------|
| ① 采集 | 一个真实源端到端可追溯，失败/陈旧/部分成功可辨别 | ⚠️ 939 次全源失败、358 次 partial |
| ② 门禁 | 误收/误拒均可追踪与回放 | ❌ 无 `item_id`，不可回放 (E14) |
| ③ 承接 | 一条资讯经人工确认成为 Case | ⚠️ 13 signals → 5 cases |
| ④ 研判 | 一条 Judgment 在 UI 内带证据发布 | ⚠️ 1 条 |
| ⑤ 行动 | 一条 Action 走完审批→执行→产物 | ❌ **0** |
| ⑥ 产出 | 一个 Artifact 可验证并被验收 | ❌ **0** |
| ⑦ 沉淀 | 一个 Case 产出带条件 Knowledge | ⚠️ 1 条 |
| ⑧ 复利 | 第二个同类 Case 自动浮现 + 采用回执 | ⚠️ 1 条 adoption |

### 5.2 异常流 (与主干同等重要)

**这是当前系统缺失最严重的一环**。异常流必须是一等公民：

| 异常 | 必须产生的状态 | 当前行为 |
|------|--------------|---------|
| 采集失败 | `source` 健康度降级 + 原因 + 下次重试时间 | 不计失败 (E2/B2) |
| 全源失败 | `run` 记录 `outcome=failed`，**不得**沿用上轮结果 | 沿用上轮 (B1) |
| 门禁异常 | 显式 `gate_error`（不 fail-open 冒充通过） | fail-open (E13) |
| AI 超时/拒绝 | `outcome=failed`，UI 显示降级原因 | 回落 5.0 + `ok=True` (E3) |
| 执行越界/超时 | `outcome=timeout/needs_human` + 审计 | 无执行体 |
| 数据投影漂移 | 对账告警 + 冻结删除 | 无条件删除 (E7) |
| 定时任务错过 | 补跑或显式记录 `missed` | 静默丢弃 (E4) |

**原则**：**任何异常都必须留下"我失败了，因为 X"的记录**，绝不静默降级。

### 5.3 操作流

| 节奏 | 用户动作 | 系统动作 |
|------|---------|---------|
| 每日 | 看"今日待处理"（非"今日资讯"） | 采集 + 门禁 + 生成事项草案 |
| 事件驱动 | 确认草案 → 处理 → 验收 | 冻结 policy 快照 → 执行 → 登记产物 |
| 周期 | 看"未完成/阻塞/待复核" + 失败面板 | 复查提醒 + 逾期检查 + 备份 + 对账 |
| 配置 | 定义自定义事项类型 | 校验不可关闭安全底线 + 生成策略版本 |

### 5.4 保留 / 降级 / 删除判据 (治 R5)

任何功能必须通过以下**四问**才能保留；答不上来的进入降级或删除候选：

| 问 | 判据 | 不通过的含义 |
|----|------|-------------|
| **Q1 用户任务** | 它服务于"发现 / 证明 / 行动 / 复用"中的哪一个？ | 服务于"系统自我体检" → 只能作为运维工具，不得占用用户菜单 |
| **Q2 真实流量** | 近 30 天有真实使用记录吗（非测试、非空转）？ | 无流量 → 冻结，不得继续投入 |
| **Q3 可验证产出** | 它的产出能被验证吗（有 run record / 产物 / 回执）？ | 无 → 先补观测，否则等于不存在 |
| **Q4 删除成本** | 删除它会破坏什么？ | 答不清 → 说明依赖未被理解，正是 `L4` 要治理的对象 |

**立即适用 (按 §2 证据)**：

| 对象 | 规模 | 判定 |
|------|------|------|
| `SentinelJudgePage` + 测试 | 916 行 | **删除**（不可达，Q2 无流量） |
| `codegarden_scanner_service.py` | 619 行 | **删除**（无运行期引用） |
| Skill* 9 包 (registry/builder/eval/runner/trigger_gate/triggers/playbook/agent_loop/agent_memory) | 10,843 行 | **收敛**（需 Q1/Q2 举证，默认合并为 1–2 包） |
| `secnews/*` 组件域 | 26 组件 / 测试覆盖 19% | **收敛**（与 sentinel 域重叠，二选一） |
| `cost_monitor` / `feedback_analyzer` | — | **删除或接线**（二选一，不得悬空） |
| 平台自检类 skill (14/26) | — | **降级**为运维面板，移出用户菜单 |

---

## 6. 分期路线图与验收

> **原则**：先立主干与可见性，再谈能力扩展。**任何一期不得跳过前一期的验收。**

### F0 —— 止血与可见 (最高优先级，1–2 周)

| # | 任务 | 治 | 验收 (可验证) |
|---|------|-----|-------------|
| F0-1 | 修 `quality_check_logs` / `warm.hotspots` 两处写失败 | R2 | 生产日志 24h 内该消息为 0 |
| F0-2 | 全部 job 显式声明 `misfire_grace_time` (≥900s) | R2 | 58/58 job 已声明；CI 门禁阻断新增未声明 job |
| F0-3 | 统一 run record + `GET /api/ops/runs` + 失败优先面板 | R2 | 任一 job 失败可在 UI 查到 |
| F0-4 | 删除 `DEFAULT_SCORE` 假成功；AI 失败 → `outcome=failed` | R2 | 构造超时用例，断言 `failed` 而非 5.0 |
| F0-5 | **修 E1 (router model 被丢弃)** 或显式删除 `task_overrides.model` 声明 | R3 | 二者选一，且 yaml 注释与实际一致 |
| F0-6 | 日志降噪 + 级别收敛 | R2 | `backend/logs/` 日增量降 ≥80% |
| F0-7 | 修 `/judge` 双声明；删 `SentinelJudgePage` 或使其可达 | R5 | 路由表 1 path 1 声明；可达性 CI 断言 |
| F0-8 | 修 `ConflictException` 未导入 (E9) | R2 | ruff F821 = 0 |
| **F0-9** | **鉴权覆盖全入口**：`/mcp/sse`、`/docs`、`/openapi.json` 纳入 TokenAuth（或显式豁免 + 文档声明） | **R6** | 新增测试断言未带 token 时 `/mcp/sse` 拒绝 |
| **F0-10** | **修迁移器 `duplicate column` 语义**：改为"该语句幂等跳过、继续执行文件剩余语句"，不得整体标记完成 | **R6** | 构造"已存在列 + 后续语句"用例，断言后续语句生效 |
| **F0-11** | **正文抓取恢复 URL 校验 + 移除 `ssl=False`** | **R6** | SSRF 用例（`http://127.0.0.1`）被阻断 |
| **F0-12** | 修 `HOTSPOT_DB_PATH` 相对/绝对不一致；库与备份文件 chmod 0600 | **R6** | 换 CWD 启动仍打开同一库 |

**F0 退出条件**: 系统能**诚实地说出自己失败了什么**，且**写入口默认是锁住的**。这是所有后续工作的前提。

### F1 —— 立主干 (2–3 周)

| # | 任务 | 治 | 验收 |
|---|------|-----|------|
| F1-1 | Run 提升为执行账本；`v1_runs` 加 `plan_json`/`policy_version`/`outcome`/`reason` | R1 | 表结构落地 + 单测 |
| F1-2 | 动作→执行最小闭环：审批 → 冻结 snapshot → 执行 → Artifact 登记 | R1 | **一条 Action 在 UI 内走完审批→执行→产物** |
| F1-3 | 门禁拒绝可回放：拒收日志加 `item_id` + `raw_data` | R2 | 任取一条拒绝，可在 UI 看到原文与原因 |
| F1-4 | 异常流状态位全部落库并在 UI 呈现 | R2 | 7 类异常各有可见状态 |
| F1-5 | 定位 `v1_signals` 涓流成因 (节流/去重/准入) | R1 | 给出量化归因 + 目标转化率 |
| F1-6 | sync `apply_bundle` 事务化：全成功才写 merge base | R6 | 注入中途失败，断言 base 未被推进且数据未半写 |
| F1-7 | `warm.knowledge_items` 补建索引（并对齐 `main` 空表） | R6 | `EXPLAIN QUERY PLAN` 由 `SCAN` 变 `SEARCH` |

**F1 退出条件**: 一条真实资讯 → 一个真实 Case → 一个真实 Artifact，**全程有 run record**。

### F2 —— 立控制面 (2–3 周)

| # | 任务 | 治 | 验收 |
|---|------|-----|------|
| F2-1 | 单一声明式 manifest 驱动路由/gate/job/UI | R3/R4 | `--check` 通过；漂移注入测试能红 |
| F2-2 | OpenAPI → 前端类型生成 + CI 比对 | R3/R4 | 契约漂移 CI 阻断 |
| F2-3 | Schema 快照入仓 + 迁移编号连续性校验 | R4 | 快照 CI 比对 |
| F2-4 | `warm.X` 裸引用全清 + CI 门禁 | R4 | grep 为 0 |
| F2-5 | 前端统一 server-state 层 + 单一 realtime | R4/R5 | 直接 API 调用数下降 ≥80% |

### F3 —— 收敛与删除 (2–3 周)

| # | 任务 | 治 | 验收 |
|---|------|-----|------|
| F3-1 | 删除死代码 (`codegarden_scanner_service` 等)，`vulture`/自定义检测入 CI | R5 | 未引用模块 = 0 |
| F3-2 | Skill* 9 包 10,843 行裁决：保留 / 合并 / 删除 | R5 | 决策文档 + 落地 |
| F3-3 | 三套本体合一：hotspots / v1_materials / wiki 共享稳定 ID | R4 | 同一资讯三处同 ID |
| F3-4 | wiki-first 契约兑现：投影无损可重建 | R4 | 删 warm 库 → 从 md 完整重建 → 行数与列值一致 |
| F3-5 | 22 处 `_now_iso` 等重复 helper 收敛到 `utils/` | R5 | 重复 AST 体 = 0 |

### F4 —— 可靠性与安全加固 (2 周)

| # | 任务 | 治 | 验收 |
|---|------|-----|------|
| F4-1 | egress guard 100% 覆盖 + AST 门禁 | R2/R3 | 带凭据出站路径 5/5 有门禁 |
| F4-2 | 执行体沙箱 + 资源上限 + 越界告警 | — | 越界用例被阻断并审计 |
| F4-3 | 备份**恢复演练**进 CI：`restore_from_backup` 加测试 + 隔离环境恢复 | R6 | CI 内完成一次备份→恢复→行数一致 |
| F4-4 | 1,019 处宽泛 except 分级：133 处静默加日志 | R2 | 静默吞异常 = 0 |
| F4-5 | 密钥分离：vault key ≠ sync bundle key；轮换后旧包可解 | R6 | 轮换→恢复旧包用例通过 |
| F4-6 | DB 损坏自动回退最新快照（而非直接拒绝启动） | R6 | 破坏主库后仍能启动并告警 |
| F4-7 | 供应链收紧：`npm ci`、action SHA 固定、`permissions:` 块、dev/optional 依赖纳入 pip-audit | R6 | CI 配置项全部到位 |

### FA —— AI Native 专项轨 (与 F0–F4 并行，详见补充卷)

> 完整设计见 [AI_NATIVE_DESIGN_2026-10-02.md](AI_NATIVE_DESIGN_2026-10-02.md)。此处只列与主干期的咬合点。

| 期 | AI Native 任务 | 验收 |
|----|--------------|------|
| **FA0** (并入 F0) | 删除 `DEFAULT_SCORE` 假成功；AI 失败显式化；降级上抛 UI；`prompt_id + version` 入 `llm_usage_log` | 超时/拒绝用例断言 `failed`；日志含 prompt 版本 |
| **FA1** (并入 F1) | **Proposal 账本**（迁移 + service + API）+ Context Compiler MVP + 判断/行动/经验三类提案端到端 | 一条真实资讯 → AI 判断提案 → 人审采纳 → 事实表出现 1 行且证据哈希可校验 |
| **FA2** (并入 F2) | 提案溯源 UI + 降级可见 + 成本阻断 + Tool Contract 统一 | 任一提案可见模型/prompt/成本/上下文快照 |
| **FA3** (并入 F3) | 反证搜索 / 观察循环 / 语义召回 / 证据缺口检测 | 各自黄金样本通过 |
| **FA4** (并入 F4) | Eval Harness + 反馈闭环（采纳/拒绝/修改 diff） | prompt 或模型变更触发自动回归；采纳率可测 |

**核心不变量 (贯穿全部期)**：

> **AI 只能写 `proposal` 表；`accept` 是唯一事实化入口；`reject` 必须带理由。**
> 违反即违反 `L3 人主律`，且会使 AI 层永远无法改进（无负样本）。


---

## 7. 风险、反证条件与待裁决项

### 7.1 本方案可能错在哪里 (反证条件)

| # | 我的判断 | 什么证据会证明我错了 |
|---|---------|-------------------|
| 1 | 主干流量 0.041% 是产品缺口，不是数据未成熟 | 若 `v1_runs` 在近期有非零历史，或涓流是刻意的"人工节奏"设计 |
| 2 | 应优先立主干而非扩能力 | 若 owner 的真实痛点是"资讯不够多/不够准"而非"转化不了" |
| 3 | Skill* 9 包应大幅收敛 | 若这 9 包是 owner 日常实际使用的核心能力（需使用日志证明） |
| 4 | 三套本体应合一 | 若三套的差异是刻意保留（服务于不同生命周期），应有成文理由 |

### 7.2 待裁决项 (需 owner 决定，不在本方案内自动成立)

| # | 议题 | 选项 |
|---|------|------|
| D1 | 产品身份 | (a) 安全从业者 AI 工作台 (主干优先) / (b) 安全资讯平台 (采集优先) / (c) 两者并存但明确主次 |
| D2 | 主干深度 | (a) 只做"资讯→Case→判断"（研究型闭环） / (b) 做到执行+产物（含 pi 执行体） |
| D3 | 收敛力度 | (a) 激进 (Skill* 家族 + secnews 域大幅删除) / (b) 保守 (只冻结不加) |
| D4 | i18n | (a) 真做（补齐 1,692 处） / (b) 移除 i18n 层 |
| D5 | 前端状态层 | (a) 引 TanStack Query / (b) 自建轻量层 / (c) 维持现状只修竞态 |
| D6 | 单用户 vs 多用户 | 是否长期保持单用户（决定 auth 与隔离投入） |
| D7 | 鉴权模型 | (a) 默认强制 token（首启生成并打印）/ (b) 保持可选但覆盖全入口含 `/mcp/sse` / (c) 仅回环 + 显式 LAN 白名单 |

---

## 8. 附录：证据复现命令

```bash
# 规模
find backend -name '*.py' -not -path '*/tests/*' -not -path '*__pycache__*' | wc -l
find backend -name '*.py' -not -path '*/tests/*' -exec cat {} + | wc -l

# 架构数字门禁 (权威计数)
.venv/bin/python3 scripts/generate_meta.py --check

# 主干流量 (生产库只读)
sqlite3 "file:backend/hotspot.db?mode=ro" \
  "SELECT 'hotspots',count(*) FROM hotspots UNION ALL
   SELECT 'v1_signals',count(*) FROM v1_signals UNION ALL
   SELECT 'v1_cases',count(*) FROM v1_cases UNION ALL
   SELECT 'v1_runs',count(*) FROM v1_runs UNION ALL
   SELECT 'v1_artifacts',count(*) FROM v1_artifacts;"

# 失败分类
grep -o '"message": "[^"]*"' backend/logs/app.log | sed 's/"message": "//;s/"$//' \
  | sed 's/[0-9]\{3,\}/N/g' | sort | uniq -c | sort -rn | head -25

# APScheduler misfire 默认值 (E4 复现)
.venv/bin/python3 -c "
import inspect,apscheduler.version,re
from apscheduler.schedulers.base import BaseScheduler
print(apscheduler.version)
print([m.group(0) for m in re.finditer(r'.*misfire.*', inspect.getsource(BaseScheduler._configure))])"

# 路由遮蔽 (E10 复现)
grep -n '"/judge' frontend/src/routes/index.tsx
```

---

## 9. 与既有文档的关系

| 文档 | 关系 |
|------|------|
| `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md` | **产品定义权威**，本方案不取代；本方案为其提供诊断与架构建议 |
| `docs/v0.8.5/V0.8.5_PLAN.md` | **spec 权威**，本方案不影响其效力 |
| `docs/FIRST_PRINCIPLES_ANALYSIS_2026-09-11.md` | 已被 PRD 标注废止；本方案在其 19 项发现基础上，用 2026-10-02 实测数据重新推导 |
| `docs/CRITICAL_REVIEW_2026-09-03.md` | 历史 finding 台账，本方案 §2.4 补充了 15 条新证据 |
| `docs/ARCHITECTURE.md` | 现状严重过期（仍描述已删除的 CRM 与 6 子系统），建议按 §4.1 重构或标注废止 |

> **回写纪律**：本方案经 owner 裁决后，(a) 架构部分回写 `docs/ARCHITECTURE.md`；(b) 产品/分期部分回写单一权威 PRD；(c) 本文档作为审计留痕保留。
