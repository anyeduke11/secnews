# PRD 能力/需求清单

> **生成日期**: 2026-11-17
> **来源文档**（均已在本次通读/skim 范围内）:
> - 【主】`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`（唯一权威 PRD，631 行，含 v0.8.6 九章历史版与变更记录）
> - 【86】`docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md`（v0.8.6 AI Native 主干，主 PRD 引用的版本族文档）
> - 【89】`docs/v0.8.9/V0.8.9_PRD.md`（v0.8.9 主干流量专项，主 PRD 引用的版本族文档）
>
> **方法与口径**: 逐条忠实于 PRD 原文，未作代码核对；「实现状态」仅转述 PRD 自身标注（✅/⚠️/❌、已落地/已交付/待落地/待裁决等），PRD 未标注处如实写「PRD 未标注」。「UI 表面」仅采信 PRD 文本可推断的页面路径/区块名，推断处注明；无法推断写「PRD 未标注」。章节号以各文档自身章节为准；「变更记录」指主 PRD 文末变更记录条目（DEV-xxxx 编号）。
> **状态词表**: 已上线（PRD 标注已落地/已交付/✅）｜部分（⚠️ 部分/部分接通/部分落地）｜规划中（待落地/待裁决/候选/待验收）｜未实现（❌ 未启动/Stub/未标注交付且属明确缺口）｜观测中（30 天窗内待判定）｜纪律生效（机制/纪律性约束，持续有效）。

---

## 一、资讯域（data，`/` 资讯菜单）

| # | ① 需求描述 | ② PRD 出处 | ③ 实现状态（PRD 标注） | ④ UI 表面 |
|---|---|---|---|---|
| DATA-1 | 资讯经质量门禁→内容门禁→规则筛选入管，门禁结果可解释、误收误拒可追踪 | 【主】九章版 §3.2 功能清单（P0）、§5.1；§1.3 成功指标 | 管线运行中；gate-detect 失败 446/446 显式 outcome（变更记录 DEV-0286「失败必可见」成立） | `/` feed；拒收入口见 DATA-11/12 |
| DATA-2 | 首页四阅读模式各有后端语义：全量（当轮全部）/ 精选（pick_score Top-30）/ 深度（精读候选+收藏自选）/ 告警（需读者执行动作） | 【主】§2.4「2026-09-27 首页四阅读模式重定义」（DEV-0236/0237） | 已上线（实弹验收：pi 复核拒绝 4 条误中候选） | `/` 首页四按钮 |
| DATA-3 | 精选评分 pick_score = quality_score + 关注域 boost×25 + 收藏源 +10 + 时效衰减，每轮采集后落库并按分排序返回 | 【主】§2.4 同上条（迁移 129、`GET /api/hotspots/picked`） | 已上线（7d 回看 evaluated=1000/picked=30） | `/` 精选模式 |
| DATA-4 | 告警收窄为「需用户执行动作」资讯：4 规则词表筛 → pi 复核 action_hint（patch/investigate/monitor/respond）→ `alert_events` 落库；fail-open：LLM 失败时 ≥2 强信号候选放行 | 【主】§2.4 同上条（`/api/alerts/v2` 加过滤零新增端点；假告警撤除） | 已上线 | `/` 告警列表 4 分类 tab + 未读徽标 + 已读/解决 |
| DATA-5 | 资讯卡片赞/踩 reaction：状态型信号（互斥切换+可取消）、对全部条目（含非安全领域）持久化，无域条目以哨兵域 `_unattributed` 落库、不回滚乐观态 | 【主】变更记录 DEV-0311/0313/0314/0326 | 已上线 | `/` 资讯卡片（头条/次级/快讯三挂载点）赞/踩按钮 |
| DATA-6 | 兴趣引擎域归因三层化：hotspot tags → 标题关键词 → category 兜底；累计型信号无域仍丢弃 | 【主】变更记录 DEV-0313 | 已上线 | `/` feed 排序（无独立 UI） |
| DATA-7 | 内容偏好三层：统计自动学习（近 30d 行为按类目/来源聚合，零配置默认生效）+ LLM 优化建议（采纳才写入，人主律）+ 手动设置折叠为高级选项；三级偏好加强/默认/减弱，只升降不删 | 【主】变更记录 DEV-0315/0316（`GET/PATCH /api/settings/content-preferences`） | 已上线 | `/settings?cat=general` 内容偏好卡 + `/` feed 排序第二轴 |
| DATA-8 | 非安全内容偏好通道（三案候选设计） | 【主】变更记录 DEV-0314 第三批 | 未实现（留档待裁决） | PRD 未标注 |
| DATA-9 | SK-01 daily-priority-intel：每日优先情报摘要，后端/API/首页接线，渲染兴趣分区 | 【主】§2.4 AI 能力表、§3.2 | 部分：已接线；摘要缺少原文/事项动作且未展示响应 mode | `/` PriorityDigestCard |
| DATA-10 | 首页摘要降级可见性：组件应显示 mode/降级原因 | 【主】§3.4 结论、§7 R5 | 未实现（PRD 定性「实际体验缺口」） | `/` PriorityDigestCard |
| DATA-11 | 拒收日志人话化：前端词典 10 flag 中文兜底 + 后端 LLM 批量 explain 回填（IS NULL 幂等）；日志迁设置运维区 | 【主】§2.4「2026-10-01」（DEV-0238，迁移 130） | 已上线 | `/settings?cat=ops` RejectionLogCard（第 4 卡）；`/quality/rejection` 重定向兼容 |
| DATA-12 | 拒收回放：strict 拒绝标记行 JOIN raw_items 原文（item_id+raw_data），raw 缺失诚实「未留存」 | 【86】§3.1 范围、P1-5（DEV-0273 已交付） | 已上线 | RejectionReplay 区块挂 ObservabilityTab（零新路由） |
| DATA-13 | 语义门禁 semantic_filter：规则 neutral 时 LLM verdict-only 判别，失败 fail-open 保留；后改 post-ingest 化（热路径零 LLM，tick 尾补偿，reject→隐藏+flag 可回溯） | 【主】§2.4「2026-09-18 方案 B」+ 变更记录 DEV-0289-F | 已上线（gate 2026-09-19 开闸） | 采集管线（结果见拒收日志） |
| DATA-14 | 智能分类 ai_classify：纯规则 miss 时 LLM 补 domain，词表严格校验；后主流量化（批级预算 20） | 【主】§2.4 同上；【86】P1-2（DEV-0270 已交付） | 已上线 | 采集管线 |
| DATA-15 | NER 实体抽取：t1 打分成功后实体落 `knowledge_items.entities`（gate `pipeline_ner`，迁移 119） | 【主】§2.4 同上 | 已上线 | 采集管线（实体入知识条目） |
| DATA-16 | MP-1 图谱点火：attack_techniques 244 条 + attack_cwe_map 714 条 + security_edges 17,616 条 | 【主】§2.5 | 已上线（✅ 已落地） | PRD 未标注直接表面 |
| DATA-17 | MP-2 事件类型：11 类词表 + 5 表 + 4 service + 6 API + 25 语料；候选生产（mp2_extract_job 03:30 全 11 类）→ 候选池 pending → owner 人工审定 | 【主】§2.5 + 变更记录 DEV-0328（四段断裂修复、契约测试 8 用例）；【主】§7 R4 | 部分：基础设施已落地；候选池待 owner 人审（金融三类递进进行中） | `/action/events` 通稿审核页（MP-2 真实端点全接入，DEV-0183） |
| DATA-18 | 类型识别：漏洞/情报/技术/开源/合规/管理分类；AI 推荐和预填资讯→事项草案 | 【主】九章版 §3.2 功能清单（P0）、§5.1 | PRD 未标注（九章版为历史产品定义，语义保留） | 事项建项入口（见 ACT-13/14） |
| DATA-19 | 采集真实供给验收：已注册 SourcePipeline 的持续供给、新鲜度与错误状态呈现 | 【主】§2.7 R02、§4 F0-5 | 规划中（代码已接线、桥测试通过；持续真实供给未验收） | PRD 未标注 |

## 二、知识域（knowledge，`/knowledge` 菜单）

| # | ① 需求描述 | ② PRD 出处 | ③ 实现状态（PRD 标注） | ④ UI 表面 |
|---|---|---|---|---|
| KNOW-1 | Wiki-first 存储：知识正文 Markdown 真源（`llm-wiki-2.0/`），FTS 索引嵌入 HOT 库（7,734 条） | 【主】§2.3、§6.3；九章版 §4.2 | 已上线 | `/knowledge` 相关页 |
| KNOW-2 | Knowledge 域对象：迁移 102、7 端点，可发布/复查/采用 | 【主】§2.2 | 已上线（1 行数据） | `/knowledge` |
| KNOW-3 | SK-05 reuse-experience：`auto_recall_for_case` 按 Case 标题/问题匹配已发布知识，自动召回 | 【主】§2.4、§3.2 | 已上线（✅，已产生 adoption 回执） | CaseDetail 召回区块 |
| KNOW-4 | SK-06 knowledge-review-due：Daily 04:00 Shanghai 复查到期 job + case blocker 机制 | 【主】§2.4、§3.2 | 已上线（✅ job 55 运行） | `/knowledge` 复查提醒 |
| KNOW-5 | SK-04 复盘知识回流：case 关闭事件直连（D8）→ 复盘提案起草（人主律）→ 人批准 → `v1_knowledge` draft（默认 playbook，review_at=+90d）→ 既有 publish（CAS+wiki-first）→ 同类召回 | 【89】§4.5 R-5；【主】§2.4 SK-04 行 + 变更记录 DEV-0283（提案化收编）、DEV-0388（事件直连，演练⑥ PASS） | 已上线（SK-04 前端接线缺口已由提案化+事件直连闭合） | `/action` 审批收件箱/CopilotCards + `/knowledge` |
| KNOW-6 | 知识适用条件/限制与真实复用验证：第二个同类 Case 自动浮现知识 + 1 条真实采用回执 + 实际结果记录 | 【主】§1.2 G4、§4 F5、§2.7 R16 | 规划中（召回/采用已有基础；适用条件与真实重复使用验证待做） | `/knowledge` |
| KNOW-7 | 资料库前厅 `/knowledge/khub`（hub-stats 聚合） | 【主】变更记录 DEV-0183/0185 | 部分：页面已上线；hub-stats 聚合端点未实现（DEV-0185 定性「真实后端缺口仅剩一项」，登记 UNIMPLEMENTED 台账；前端不展示伪造数据） | `/knowledge/khub` |
| KNOW-8 | 编目室 `/knowledge/library`（复用既有 `GET /api/knowledge/items`，不建新表） | 【主】变更记录 DEV-0183/0185 | 已上线 | `/knowledge/library` |
| KNOW-9 | 无限画布：共享 InfiniteCanvas（拖拽平移/光标锚定缩放/双击重置/点阵网格）；canvas 双模式（DOM 默认 + ECharts demo 降级）、graph 画布开关（SVG 直排默认降级） | 【主】变更记录 DEV-0184 | 已上线（纯前端，零新路由） | `/knowledge/canvas`、`/knowledge/graph` |
| KNOW-10 | 清样深读 `/reader/:id`：wiki 阅读 + 批注 | 【主】变更记录 DEV-0183/0185 | 部分：页面已上线；批注为前端占位，复用既有 annotations 表（migration 027）仅缺薄 API、不写 wiki md | `/reader/:id` |
| KNOW-11 | Cubox「导入目录」支持本地化 .md：顶层 `*.json` + 递归 `*.md`，frontmatter 解析（source_url/title/tags/created），响应透传 imported 报数 | 【主】变更记录 DEV-0327 | 已上线 | `/knowledge` 导入页 |
| KNOW-12 | 真源缺列补齐（E8）：entities/compiled 进 frontmatter，attention_score 标注派生缓存可丢；md→SQLite roundtrip 测试锁定 | 【86】P2-2（DEV-0278 已交付） | 已上线 | `llm-wiki-2.0/` md 真源 |
| KNOW-13 | 旧库 3800 行 knowledge_items 迁移（T16 遗留） | 【主】§7 R9 | 未实现（待授权 + 备份前置） | PRD 未标注 |
| KNOW-14 | AI 副驾知识摘要卡/关联证据卡（/knowledge 条目详情增量区块，走提案通道） | 【86】§6.1 信息结构、P1-3 | 部分：P1-3 实现裁决将四卡统一挂 `/action`（CopilotCards，DEV-0271）；§6.1 规划的 /knowledge 落位与实现存在差异 | `/knowledge`（规划）/ `/action`（实际落位，DEV-0271） |

## 三、行动域（action，`/action` 菜单）

| # | ① 需求描述 | ② PRD 出处 | ③ 实现状态（PRD 标注） | ④ UI 表面 |
|---|---|---|---|---|
| ACT-1 | v1.0 九对象账本：Subject/Material/Signal/Case/Judgment/Action/Run/Artifact/Knowledge（+3 receipt）；Signal 只读无写端点 | 【主】§2.2、九章版 §7 数据模型 | 已上线（Run/Artifact 由 0 行到 v0.8.9 有真实流量，见 ACT-6/ACT-9；Signal 无写端点为 PRD 标注现状） | `/action` CaseQueuePanel 等 |
| ACT-2 | 审批收件箱：proposal 卡必显类型/发起方/证据数/case/prompt 版本/正文预览；写操作橙标；批准两步内联确认；修订=受控展开 JSON；驳回原因必填 ≤200；failed 卡显示 error_msg + 重试=新生成提案 | 【86】§6.2、用例 A（P1-1 切片3，DEV-0265 已交付） | 已上线 | `/action` ApprovalInbox（ExecOverviewPanel 之前） |
| ACT-3 | AI 起草研判：Case 页发起 → ai_hub HEAVY 档（task=report）→ proposal 落库（evidence_ids_json + prompt 版本 judgment-draft@v1）→ 批准生成双签 Run → md 落盘 sha256 登记成功才 succeeded/done；无绑定证据 400；旧直写端点退役 410 | 【86】用例 A（DEV-0264/0265/0267 已交付） | 已上线 | CaseDetail「AI 起草研判」按钮 + `/action` 收件箱 |
| ACT-4 | 全界面 AI 副驾四卡：研判建议/知识摘要/证据召回/SK-04 复盘，全部走提案通道（人审后生效），各产出 ≥1 artifact | 【86】§3.3 M3、P1-3（DEV-0271 已交付，四卡挂 `/action`） | 已上线 | `/action` CopilotCards 区块 |
| ACT-5 | 四段执行指挥台（R-15）：执行流程四段化指挥 | 【主】头部 v0.8.8 P4.5；【89】R-1「四段指挥台 Run 段接线操作按钮」 | 已上线 | `/action` ExecOverviewPanel / ActionCommandConsole |
| ACT-6 | Run 人工回执通道（direct 执行体）：`POST /api/v1/runs/{id}/claim|start|finish|cancel`（CAS 状态迁移、finish 必填 outcome∈{done,failed,cancelled,timeout,needs_human}+error 原因码；重复 finish 409；finish 发 `v1_run` outbox 事件）；人登记=人担保（落 audit_log）；禁止绕过守卫直接 succeeded | 【89】§4.1 R-1（D4 裁决）；【主】变更记录 DEV-0384（P1，演练① 首个 closed case） | 已上线 | `/action` 四段指挥台 Run 段 |
| ACT-7 | Action 收口端点：`POST /api/v1/actions/{id}/finish`（running→succeeded/failed，校验关联 run 终态） | 【89】§4.1 R-1 | 已上线 | CaseDetail/指挥台 |
| ACT-8 | ExecutionPlan 边界协议：schema v1（commands[]/writable_paths[]/readable_paths[]/network[] 默认全禁/timeout_sec/output_artifact）；ai_hub 起草建议 plan（不碰红线）+ 人工手写兜底；审批 `approve|reject` 默认拒绝、approve 即冻结（快照+boundary_hash 落 run 行，migration 136 三列，D2）；试点只读类模板（D5） | 【89】§4.2 R-2、§5、§9 D2/D5；【主】变更记录 DEV-0385（P3） | 已上线（不变式：默认拒绝 + approve 即冻结 + 仅 queued/claimed 可操作） | `/action` 四段指挥台 plan 审批区块 |
| ACT-9 | pi 边界内执行：enforce 编译器（workspace 锁定 + argv 白名单∩plan 子集 + 网络隔离 + timeout）+ 确定性 argv 执行体（D3 改判：逐条 subprocess，越界即 fail）+ 终态回写 Run + Artifact 自动登记（body_hash）；开关 `pi_executor_enabled` 默认关，生产开启须 owner 授权 | 【89】§4.3 R-3、§9 D3；【主】变更记录 DEV-0386（P4，演练②③过） | 已上线（默认关） | `/action` Run 段事件流 |
| ACT-10 | L3 系统层加固：macOS sandbox-exec per-plan profile（文件读写隔离+凭据禁读+出网全禁）+ ulimit（CPU/文件大小/文件数）| 【89】§4.4 R-4、§6；【主】变更记录 DEV-0387（P5，演练④ 6 步全达成） | 已上线（已知边界：仅 macOS；非 macOS 降级仅 ulimit 并留痕；RLIMIT_AS 内存上限未实现） | 无独立 UI（audit_log 留痕） |
| ACT-11 | L4 审计与越界告警：逐命令 argv 落 agent_runs（`agent='pi-executor'`/`protocol='argv'`，stdout 尾 500 字）+ 越界事件入 `observability_alerts`（executor.boundary_violation，critical，按 run 去重；普通非零退出不告警） | 【89】§6 安全模型；【主】变更记录 DEV-0387 | 已上线（演练④：越界 spawn 前被拦 `E_ARGV_NOT_ALLOWED`） | `/settings?cat=ops` 失败/告警面板 |
| ACT-12 | Case 关闭闭环：四守卫不改语义只供弹药——研究型经 published judgment 旁路关闭、运营型经完整 run/artifact 链关闭（守卫 (d) 保留，D6）；关闭事件四守卫反证演练 | 【89】§4.5 R-5；【主】变更记录 DEV-0384/0388（演练⑤ N1~N4 全过，首个运营型 case 真实关闭） | 已上线 | CaseDetail 关闭流程 |
| ACT-13 | 五类标准事项模板：漏洞治理/研究实践/情报响应/合规整改/管理决策模板（用户确认→Case/Action） | 【主】九章版 §3.2 功能清单（P0） | PRD 未标注（九章版为历史产品定义，语义保留；事项建立必须用户确认已为人主律纪律） | `/action` 建项入口 |
| ACT-14 | 自定义事项类型：字段/状态/步骤/规则/审批/输出模板/提醒可配置，AI 提供结构/字段/步骤/门禁/审批/输出模板建议；不得绕过系统安全底线 | 【主】§1.0 v0.8.6 产品裁决增量、九章版 §3.2（P0）/§6.3 配置流 | PRD 未标注（产品语义保留） | PRD 未标注 |
| ACT-15 | CodeGarden 安全实践域：CP-1 S1 开源信号提取（9,872 条）+候选池端点；CP-2 S2 立项四阶段+行动侧入口；CP-3 S3 产物沉淀+知识联动；CP-4 S4 工具台账+phase2b 删除裁决 | 【主】§5.2、§2.6 | 部分：practice_domain 分类已落；`cg_projects.practice_domain` 列 + S1 开源信号提取未落地；CP-1~CP-4 未落地 | PRD 未标注 |
| ACT-16 | P1-0 执行器四期（P1-0a 止血人工回执+b 列扩展 / P1-0b 边界协议 / P1-0c pi 执行 / P1-0d 加固；不做 shell=True、workspace 外写、交互式输入、凭据传递） | 【主】§5.1、§2.6 | 已由 v0.8.9 R-1~R-4 对应落地（【89】§9 D1 确认继承 P10 设计）；主 PRD §2.6 当时标注「真实消费/终态执行未落」 | 同 ACT-6~10 |
| ACT-17 | 完整事项队列可达性：CaseQueuePanel 只在被重定向遮蔽的旧页面挂载；行动页总览仅前 8 个 open/in_progress、不含 blocked，不能替代完整队列 | 【主】§2.1「当前关键不一致」、§4 F0-3 | 未实现（PRD 标注动线缺口，F0-3 P0 任务；新排序待裁决） | `/action` 总览（现状仅 8 条） |
| ACT-18 | 观测收口（R-6）：artifact_yield 口径修复（分母改 `outcome='done'`，D7 定性 bug 修复）+ run 全生命周期事件入 v1_outbox（带 trace_id）+ run 端到端时延 P50/P90 + M-9（七段 p95）/M-10（埋点开销）观测窗判定 | 【89】§4.6 R-6、§9 D7；【主】变更记录 DEV-0384（P2，活体 yield_ratio=1.0） | 部分：口径修复+run 事件已上线；M-9/M-10 观测中（t0=2026-11-14 → 2026-12-14 待满窗判定） | `GET /api/ops/kpi` + `/settings?cat=ops` |
| ACT-19 | 30 天主干流量目标与发布门：runs ≥10 / artifacts ≥5 / 首个运营型 case 关闭 / 越界演练通过；tag `v0.8.9` 发布 | 【89】§1.4 G1~G5、§8 P7；【主】变更记录 DEV-0389（P7） | 观测中（G2/G3/G4 ✅；G1 ◐ 活体 runs=4/artifacts=3 未达标不宣称；tag 待 owner 授权） | PRD 未标注 |

## 四、设置域（settings，`/settings` 菜单）

| # | ① 需求描述 | ② PRD 出处 | ③ 实现状态（PRD 标注） | ④ UI 表面 |
|---|---|---|---|---|
| SET-1 | 设置页 IA：7 cat / 5 组——overview 总览 / general 通用（主题/模式/刷新/兴趣画像/能力开关）/ models 模型配置唯一入口 / collection 采集与管线 / network 代理 / connectivity 同步·MCP·密钥状态 / ops 维护·导出·dsh 启停；纯配置心智（只读监控/数据浏览/一次性动作不混入） | 【主】九章版 §3.4（DEV-0227 落账） | 已上线 | `/settings?cat=*` |
| SET-2 | Feature gates 单源：16 gate（开 15/关 1 mcp）；`GET /api/settings/features`、`GET/PUT /api/settings/feature-gates*`（TOML 写入+audit，env 覆盖 409）；`HOTSPOT_FEATURE_GATES` env 优先于 TOML；gate 化须随消费点同时登记 | 【主】九章版 §3.4；头部「开关源」节 | 已上线 | `/settings?cat=general` 能力开关 |
| SET-3 | 模型配置唯一入口：Provider/密钥/模型池/三场景（models cat）；模型池内置国产 9 平台 + 密钥保险箱 + /models 探测；llm.yaml 档位路由分权（task_overrides 三档锚点） | 【主】九章版 §3.4；【86】§1.6 名词解释（DEV-0244/0245 已落） | 已上线 | `/settings?cat=models` |
| SET-4 | MCP 设置：`GET/PUT /api/settings/mcp/*`（ungated 开关 + 配置）；MCP server 23 工具（16 读 + 7 写，含 v0.8.7 只读导出 ×4：list_proposals/runs/artifacts/cases，operation_id 防漂移守卫）；gate 关零暴露双锁 | 【主】九章版 §3.4、§6.1；变更记录 DEV-0289-B | 已上线 | `/settings?cat=connectivity`（server 供外部 agent） |
| SET-5 | WebDAV 同步：同步能力 + 出站范围须与本地优先定位对齐；跨端 sync bundle 仅打包 config namespace（`settings_sync_allowed` 白名单）；`webhook.secret` 加密存储不入明文 KV | 【主】九章版 §3.4、§6.3 | 已上线（能力存在；出站边界 PRD 提示与本地优先定位对齐） | `/settings?cat=connectivity` |
| SET-6 | 自动入管配置：`GET/PATCH /api/settings/auto-intake`（自动入管配置 + 今日已入管数） | 【主】九章版 §3.4（DEV-0231） | 已上线 | `/settings?cat=collection` 设置卡 |
| SET-7 | 失败面板：`/api/ops/runs` + 运维区失败优先视图；默认视图=过去 24h failed/missed/needs_human；按严重度排序、每行时间/对象/原因/重试按钮；空态文案区分真空态与加载失败 | 【86】§3.3 M5、§6.1/§6.2（P0-5 最小版） | 已上线（任一 job 失败 UI 可查；面板自身 run record+心跳条兜底） | `/settings?cat=ops` OpsRunsPanel |
| SET-8 | /maint 维护页：健康卡（size_mb/freelist/fragmentation_pct 按权威契约 fail-loud）+ 清理卡（`/cleanup-quality-logs`，三档滚动模型 21 天台账）+ 索引卡（`/api/maintenance/index-health`，vacuum 后复检闭环）+ 备份卡（盘点端点 + compact 滚动保留「1 全量+≤3 增量」） | 【主】变更记录 DEV-0178、DEV-0317~0324 | 已上线（想象契约四处全部修正为按后端权威契约呈现） | `/maint`（复用 maintenance API） |
| SET-9 | 设置治理四件套：AI 提供商、数据分级、出站策略、策略版本、审计（配置→生效策略；策略快照与版本追溯） | 【主】九章版 §3.2 功能清单（P0 设置治理） | 部分：审计/策略快照随执行链落地（ACT-8/11/12）；数据分级与出站策略主 PRD 明示「不能视为已实现承诺」（§1.1） | `/settings?cat=*` |
| SET-10 | 鉴权全入口（S1）：TokenAuth 覆盖 `/mcp/sse`、`/docs`、`/openapi.json`（或显式豁免+文档）；纯回环 MEDIUM / LAN 暴露 HIGH | 【86】§9.4、P0-3 | PRD 未标注单条交付（属 AI Native P0 止血批次） | `/mcp/sse`、`/docs`、`/openapi.json` |
| SET-11 | 出站与路径加固（F0-11/12）：正文抓取恢复 URL 校验（SSRF 阻断内网）+ 移除 `ssl=False`；库/备份文件 0600；`HOTSPOT_DB_PATH` 绝对路径化 | 【86】§9.4、P0-9 | PRD 未标注单条交付（P0 批次） | 无（后端） |
| SET-12 | run.py 单实例守卫：pgid 锁 + 端口探活双检启动闸 | 【主】头部 v0.8.6 段；变更记录 DEV-0293/0294（拓扑定案 dev 即生产：8000 后端 + 8898 vite） | 已上线 | 无（启动闸） |
| SET-13 | 备份与热冷分层：SQLite backup API + manifest + sha256（R12）→ v0.8.8 备份链退役（449MB 回收、语义改「可重建」）+ hotspots 沉降 wiki 冷层 + 日志环截 −75% + 台账两层化（主库 794→111MB） | 【主】§2.3、§2.7 R12；头部 v0.8.8 P2.5；【89】§3.3 C6（恢复演练进 CI 作废） | 已上线（代码修复定向测试通过；早期「生产恢复演练」要求随备份链退役作废） | `/maint` 备份卡 |
| SET-14 | dsh 启停（ops cat）与 :3210 降级链 `not_configured→mock→ai_hub`（dsh 为受管子进程，勿再写「独立网关」） | 【主】九章版 §3.4；变更记录 DEV-0178 | 已上线 | `/settings?cat=ops` |
| SET-15 | 单用户边界：先支持单用户本地部署；组织协作、租户隔离、跨组织共享不纳入本版本承诺（D6 长期单用户） | 【主】九章版 §2.1；【86】裁决 D6 | 纪律生效（明确不做） | PRD 未标注 |

## 五、跨切面（壳/心跳条/主题/命令栏/质量规则/receipt/幂等/安全/存储/工程纪律）

| # | ① 需求描述 | ② PRD 出处 | ③ 实现状态（PRD 标注） | ④ UI 表面 |
|---|---|---|---|---|
| XF-1 | SentinelShell 四菜单唯一壳（资讯/知识/行动/设置）：唯一壳 + 4-tab；v1.0 九领域对象/三类 receipt 只能以能力区块进入；v1 四入口 `/workbench` `/intel` `/cases` 仅为重定向兼容（透传 query）；禁止新一级入口/新壳 | 【主】头部 v0.8.9 状态段、§2.1；【86】§1.6 壳纪律 | 已上线（壳冻结 C-1 硬约束，v0.8.8 四硬约束之一） | 全站 SentinelShell |
| XF-2 | 管道心跳条全站常驻（4-tab + 心跳条） | 【主】头部 v0.8.9 状态段 | 已上线 | 全站常驻 |
| XF-3 | PageLayout 工具页：53 路由全 lazy，`menuOf(pathname)` 自动归属四菜单；UTILITY_GROUPS 17 项更多菜单物理删除 | 【主】§2.1、§6.2（Routes 53）；变更记录 DEV-0168/0175 | 已上线 | 工具页统一 PageLayout |
| XF-4 | 主题 3 态：light / dark / paper（纸面版暖米黄纸底+衬线字体，最小侵入仅覆写 6 个核心 token） | 【主】§2.1、§6.2；变更记录 DEV-0175 | 已上线（T8 三主题人工走查未闭，见主 PRD 变更记录 P7 遗留） | `/settings?cat=general` 主题 |
| XF-5 | 对话式命令栏：Shell 常驻 masthead（四菜单右侧），固定四类意图模板（查询/建案/出报告/执行），本地规则优先，不做通用 NLU；不可识别显式列出可选动作（不猜）；查询带 Source url；行动类生成 proposal；执行类诚实返回 unsupported；每条命令落 command_log（`GET /api/commands`） | 【86】用例 B、§6.2（P1-4，DEV-0272 已交付） | 已上线 | CommandBar 常驻区块 |
| XF-6 | 质量规则两层模型：11 内置 gate + 专家规则（5 matcher、reject/flag、零 LLM）+ AI 语义规则（NL→聚合 LLM 判别、默认开、fail-open 可见、预算 max_per_batch=10 双闸、dry-run cap 5）；`quality_custom_rules` 单表两用（migration 133）+ 6 端点；gate 级开关 5s TTL | 【主】头部 v0.8.6 段；【86】DEV-0280 | 已上线 | CustomRulesPanel（CRUD+gate 开关+dry-run） |
| XF-7 | 三类 receipt 一等公民：evidence_receipts（证据回执，幂等提交）/ v1_knowledge_revisions（append-only）/ v1_knowledge_adoptions（真实采用回执，不以召回次数冒充复用） | 【主】§2.2、§2.7 R16；【86】§1.6 | 已上线 | Artifact 卡/知识详情/CaseDetail |
| XF-8 | CAS 幂等语义：Run/Artifact 状态迁移用 update_status + revision（重复终态 409）；Artifact revision+old_status 原子比较（R09）；复盘 handler 幂等（exists_for_case） | 【主】§2.7 R09；【89】R-1/R-5 | 已上线 | 全部写路径 |
| XF-9 | 人主律（提案纪律）：Agent 产出提案、人负责审批，未经人审批不得成为事实；事项建立必须用户确认，AI 不得直接创建或授权；一切 AI 动作只能经 proposal 通道生效 | 【主】九章版 §1.3/§9；【86】§1.6/§3.5 | 纪律生效（审批收件箱为其 UI 承载） | `/action` 审批收件箱 |
| XF-10 | 失败三形态收口 + 零静默：gate fail-open / 写库失败 / job misfire 全落显式 outcome（gate_error 不冒充通过；misfire_grace≥900s + max_instances=1，collect 错过补跑一次）；G2 清零确认（gate-detect 446/446） | 【主】头部 v0.8.6 段；【86】§5.2、§10 P0-5/12、DEV-0286 | 已上线（「失败必可见」不变量成立） | `/settings?cat=ops` 失败面板 |
| XF-11 | run record 统一埋点：所有执行（job/命令/审批/管线）统一 run record；G1/G2 指标从 v1_runs/v1_proposals/command_log 聚合，无额外埋点 | 【86】§4.1 架构裁决③、§9.3 | 已上线 | `GET /api/ops/runs`、`GET /api/commands` |
| XF-12 | 安全底线八条 × 四层防线：外部执行授权(L1)/范围限制(L2)/凭据保护(执行环境无 llm_secrets+L3 禁读凭据载体)/出站控制(network 默认全禁)/审计留痕(L4+audit_log)/失败真实性(7 态机显式 outcome)/资源上限(timeout+ulimit；内存 AS 未实现)/审批快照版本追溯(boundary_hash+revision)；不可关闭，自定义规则不得绕过 | 【主】§1.0；【89】§6 | 已上线（L1/L2/L4 全交付；L3 已交付但仅 macOS；内存 AS 上限未实现） | `/action` 指挥台 + 告警面板 |
| XF-13 | ai_hub 红线与 egress 门禁：`gateway._try_order`/`service._resolve_provider` 未裁决勿动；仅 gateway 可带凭据出站（image_service 收编），AST 门禁禁止新增裸凭据路径；管线 LLM 单出口走 gateway | 【主】头部「ai_hub 红线」、§2.4 方案 B；【86】§4.1 硬规则②、P0-11 | 纪律生效（红线持续有效；P0-11 单条交付 PRD 未标注） | 无（后端/CI） |
| XF-14 | pi 主力引擎：`llm.yaml` `default_provider: pi` + fallback_order pi 带头（ollama/sensenova/qwen/openai 降兜底不删除）；实弹验收 score 首链 provider=pi ok=1 + chat 真回复 + fallback 兜住 | 【主】§2.4「2026-09-27 pi 升主力引擎」 | 已上线 | 无（模型路由层） |
| XF-15 | dsh 受管子进程：ProcessSupervisor+bridge；dsh vendor 二进制不在树内（D3 裁决）→ 全链降 ai_hub | 【主】§2.4、变更记录 DEV-0178；【89】§1.1 断点③ | 部分（mock/ai_hub 降级链可用；真 vendor 死路已裁决） | 无 |
| XF-16 | 存储哲学：HOT 唯一可写业务库 / WARM 只读档案（禁裸 `warm.` 引用，CI 门禁 check_warm_refs）/ COLD 审计归档 / wiki-first md 真源 / v0.8.8 热冷分层；WAL 跨 ATTACH 事务不原子为已知限制（v1 域对象尽量在 HOT） | 【主】§2.3、§3.3、§7 R6；【86】§4.3、P1-8（DEV-0276 已交付） | 已上线（跨库不原子为已知风险） | 无（数据层） |
| XF-17 | 迁移器幂等（S2）：duplicate column 跳过但继续执行文件剩余语句，半应用禁止；migration X-6 只加不改（migration 136 三列） | 【86】§9.2、P0-4；【89】§5 | P0-4 单条交付 PRD 未标注（P0 批次）；X-6 规则纪律生效 | 无 |
| XF-18 | sync apply_bundle 事务化：deferred_commit 单事务原子注入，中途失败整体回滚；pull 顺序契约 base 不推进 | 【86】P1-6（DEV-0274 已交付） | 已上线 | 无 |
| XF-19 | 前端 fetch 竞态守卫：useAbortGuard hook，24 个页面/面板级风险文件统一卸载守卫（113 处）；第二批（依赖变更序 requestId 与弹窗类 20 文件）列后续批 | 【86】P1-7（DEV-0275 已交付） | 部分（第一批已上线；第二批未做） | 全站 fetch effect |
| XF-20 | 状态库裁决：先修竞态不引 react-query/swr/TanStack，另议；前端数据层用 `lib/api`/域 API/`realtime.ts` | 【主】§3.4；【86】裁决 D5、§3.1 | 纪律生效（未引入，是否引库由测量决定） | 无 |
| XF-21 | i18n 裁决：维持中文硬编码（D4），移除半吊子 i18n 层另议；现 120+ keys（zh-CN/en-US） | 【主】§6.2；【86】裁决 D4、§3.1 | 纪律生效（维持现状） | 全站 |
| XF-22 | KPI 口径与观测：主指标=signal→case 分诊时延 P50/P90 + artifact 产出率（→1.0），signals/hotspots 比率降级参考；七段链路埋点（stage spans→audit_log+trace 端点）；R-11 envelope error_code/retryable + Case/Artifact 幂等键 | 【主】头部 v0.8.8 P4、变更记录 DEV-0289-C；【86】§1.4 | 已上线（口径切换已落地；主指标基线待观测窗重设） | `GET /api/ops/kpi` |
| XF-23 | 工程纪律组：单一权威 PRD 维护纪律（先改 PRD 再改其他文档/superseded 横幅/spec 漂移禁止/audit 留痕/DEV_LOG 联动）；架构数字门禁（generate_meta.py AST 反推，56 jobs/19 collectors/99 routers/155 services，CI `--check`）；core.include/exclude 分类门槛；agent assets lint（长 skill 必须 references/，error 阻断 CI） | 【主】头部「单一权威 PRD 维护纪律」「架构数字门禁」「core 路径边界」「Agent Assets Lint」各节 | 纪律生效（CI 门禁持续运行） | 无（CI/脚本） |
| XF-24 | SSE 实时失效：统一 realtime 注册 + Case 精准失效；SSE 刷新自激循环已修；生产断网恢复未验收 | 【主】§2.7 R18、§3.4 | 部分（前端已接线、定向测试通过；端到端可靠性验收待做） | 全站实时刷新 |
| XF-25 | egress/出站诚实声明：本地运行≠数据不出域——配置外部模型或 WebDAV 时内容可离开本机；离线模式、资料分级、外部推理限制不得视为已实现承诺 | 【主】§1.1、§4.3 外部依赖 | 未实现（PRD 明示「不能视为已实现承诺」） | `/settings?cat=connectivity`（现状仅能力入口） |

---

## 六、PRD 明确未实现/规划中项（汇总）

### 未实现（PRD 明确标注 ❌/Stub/缺口/未实现承诺）

1. **MP-3 L1 漏洞绑 CVE**（NVD 接入 + CVE→technique 标注 + 资讯继承标签）——【主】§2.5 ❌ 未启动、§5.3。
2. **MP-4 L3 响应 + 双向关联**（`knowledge_technique_ref` 表 + `get_knowledge_for_techniques()`）——【主】§2.5 ⚠️ Stub（返回空列表）、表未建；§5.3。
3. **CodeGarden 安全实践域**——【主】§2.6：practice_domain 分类已落，`cg_projects.practice_domain` 列 + S1 开源信号提取未落地；§5.2 CP-1~CP-4 未落地。
4. **非安全内容偏好通道**——【主】变更记录 DEV-0314：三案候选，未实现，待裁决。
5. **hub-stats 聚合端点**——【主】变更记录 DEV-0185：真实后端缺口仅剩此一项，登记代码 TODO 与 `docs/UNIMPLEMENTED.md`。
6. **/reader/:id 批注薄 API**——【主】变更记录 DEV-0183（批注占位）/DEV-0185（复用 annotations 表仅缺薄 API，不写 wiki md）。
7. **摘要降级可见性**——【主】§2.4（SK-01 摘要未展示响应 mode、缺原文/事项动作）、§3.4、§7 R5。
8. **完整事项队列可达性**——【主】§2.1：CaseQueuePanel 被遮蔽、行动页总览仅前 8 条不含 blocked；§4 F0-3。
9. **出站控制 / 资料分级 / 离线模式 / 外部推理限制**——【主】§1.1 明示「不能视为已实现承诺」；九章版 §8 F5 治理加固未竟。
10. **3800 行旧 knowledge_items 迁移**——【主】§7 R9：待授权 + 备份前置。
11. **RLIMIT_AS 内存上限**——【89】§6 已知边界：macOS 内核拒绝收紧，未实现。
12. **非 macOS L3 沙箱**——【89】§6：降级为仅 ulimit，audit_log 留痕 `sandbox=unavailable`。
13. **pi 执行体生产开启**——【89】R-3：`pi_executor_enabled` 默认关，须 owner 授权。
14. **MCP 执行类工具**（写提案/审批经 MCP）——【89】§3.1 留待后续。
15. **Docker 隔离 / sandbox Docker / 非本机 uid 降权**——【89】§3.1 明确不做/留待后续。
16. **执行计划修订历史表**（plan 存 run 行内）——【89】§3.1 留待后续。
17. **多执行体并发编排 / playbook 化执行**——【89】§3.1 留待后续。
18. **CodeGarden 实践域作为执行下游**——【89】§3.1 留待后续（P10 §7 预留）。
19. **移动端 / 局域网多端**——【89】§3.1、【86】§3.1、【主】九章版 §2.1 不纳入承诺。
20. **0.8.7 候选表 C1~C9**——【86】§3.1（except 分级治理[高]/_bulk_syncing try-finally/密钥分离/供应链收紧/WebDAV 明文/双门禁合一/组件域收敛/helper 收敛）维持候选；C6 恢复演练进 CI 已作废（【89】§3.3，备份链退役语义改「可重建」）。
21. **AI Native 留待后续**——【86】§3.1：manifest 控制面、三本体合一（hotspots/v1_materials/wiki 共享 ID）、OpenAPI→前端类型生成、TanStack 状态库、日志 293MB→归档策略细化；Skill* 9 包大删除冻结（D3 保守）、i18n 层移除另议（D4）。
22. **v0.8.8 两项未闭**——【主】变更记录 P7 段：M-4 包体 −1.8% 未达 −3%、T8 三主题人工走查。

### 规划中 / 待裁决 / 待验收

23. **MP-2 候选池 owner 人审**——【主】§2.5、§7 R4（owner 人审是关键路径瓶颈，金融三类递进进行中）。
24. **F0-F5 分期路线**——【主】§4：新排序待裁决，不直接作为已批准开发清单；九章版 §8 F0–F5 已被 AI Native P0–P2 与 0.8.7 候选表收编（2026-10-02 owner 裁决）。
25. **采集真实供给/新鲜度验收**（R02/F0-5）、**SSE 生产断网恢复**（R18）、**R06 live trace / R10 WikiFs / R15 Skill 契约 / R19 契约一致性 / R20 发布台账复核**——【主】§2.7/§4：代码已接线或部分修复，运行证据未验收/未复核。
26. **Workbench Focus 工作流与效果验收**——【主】§2.6：优先摘要前端分区、兴趣引擎和域词表已落；工作流与效果验收仍须补齐。
27. **30 天观测窗**——【89】§8 P7：t0=2026-11-14 → 2026-12-14，M-9/M-10 待满窗判定；tag `v0.8.9` 待 owner 打点（G1 活体 runs=4/artifacts=3 未达 ≥10/≥5，如实标「观测中」）。
28. **SK-03 执行体回写**——【主】§2.4 标注「执行体 P1-0 待落地」；执行体已由 v0.8.9 交付（ACT-6/9），主 PRD 该行未回写。
29. **dsh 真 vendor**——【主】§7 R2 待排期 →【89】§1.1 已裁决死路（二进制不在树内），全链降 ai_hub。

---

## 尾注

- 本清单为 PRD 文本层的能力盘点，不构成实现核验：PRD 自身声明「真相源 = 当前工作树代码 + 可追溯验证记录」（【主】文首），实现与验证分离、实现侧不得自评 PASS。
- 条目中「PRD 未标注」表示三份 PRD 均未对该项给出交付状态标注，需按【主】§2「实现状态按二次复审核对」口径另行核对代码。
- 涉及 AI Native P0 止血批次（SET-10/SET-11/XF-13/XF-17）的单条交付状态，【86】§10 未逐条标 ✅，仅 P1/P2 各切片有 DEV 编号交付记录。
