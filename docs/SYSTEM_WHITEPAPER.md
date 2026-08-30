# SecNews（hotspot）系统白皮书

> **版本**：v0.4.3 ｜ **日期**：2026-08-22 ｜ **定位**：面向 AI + 安全从业者的单人本地知识工作站
>
> 本文是系统的完整技术白皮书，覆盖产品定位、总体架构、前后端功能全景、业务流程与操作流。
> 架构数字由 `scripts/generate_meta.py` AST 反推维护（43 jobs / 51 routers / 81 services / 14 collectors / 36 repos / 60 migrations）。

---

## 目录

1. [产品定位与设计哲学](#1-产品定位与设计哲学)
2. [总体架构](#2-总体架构)
3. [后端架构详解](#3-后端架构详解)
4. [前端架构详解](#4-前端架构详解)
5. [五大子系统功能全景](#5-五大子系统功能全景)
6. [数据模型与存储体系](#6-数据模型与存储体系)
7. [核心业务流程](#7-核心业务流程)
8. [操作流（用户视角）](#8-操作流用户视角)
9. [AI 能力与 MCP 集成](#9-ai-能力与-mcp-集成)
10. [安全设计](#10-安全设计)
11. [质量保障与测试体系](#11-质量保障与测试体系)
12. [部署运维与扩展机制](#12-部署运维与扩展机制)

---

## 1. 产品定位与设计哲学

### 1.1 一句话定位

SecNews 是一个运行在本地的**单人知识工作站**：把 30+ 信息源的热点资讯自动采集进来，经过 13 道质量门禁过滤，沉淀为结构化知识库，最终驱动报告生成、复习计划与代码项目管理——形成「信息 → 判断 → 行动」的完整闭环。

### 1.2 目标用户

**AI + 安全从业者**。这是产品的差异化根基：

- 安全领域数据源最广（17 源），knowledge 库中安全 + AI 内容合计占 65%
- AI 安全交叉内容（OWASP LLM Top 10、对抗 ML、prompt injection、AI 红队）是区别于纯安全或纯 AI 产品的独特方向
- 金融/创业/招标/科技/GitHub 为辅助领域

### 1.3 设计哲学

| 原则 | 含义 | 落地方式 |
|------|------|----------|
| **单人本地优先** | 无多用户认证、无 Redis/PostgreSQL/Celery/Docker | 单 FastAPI 进程 + SQLite WAL |
| **文件即真相** | .md 文件是知识源头，SQLite 只是读缓存 | knowledge/ 目录 + watchdog 双向同步 |
| **Core/Extension 软分层** | 核心永不消失，扩展可插拔 | feature_gates.toml + 路由/job 条件注册 |
| **LLM 只做判断** | 分类/摘要/提取交给 LLM；路由/重试/确定性变换交给代码 | Hybrid AI：规则优先，LLM 兜底 |
| **复利导向** | 知识要能积累、能被再次消费 | KL 五阶段生命周期 + SM-2 复习 + 复利仪表盘 |

### 1.4 三层心智模型（Second Brain）

v0.4 将全部功能重组为「第二大脑」三层抽象：

```
资料层 · 我有什么        判断层 · 我怎么看         行动层 · 我下一步做什么
─────────────────       ─────────────────        ─────────────────────
资讯流 / 标讯列表        质量门禁 / 趋势分析       报告 / Outbox 整理
收藏夹 / 历史记录        标讯分析 / 注意力热力图    SM-2 复习 / 知识复利
搜索 / 知识导入          知识图谱 / 编译           CodeGarden 项目管理
   ↓ 采集→结构化→筛选      ↓ 分析→决策                ↓ 计划→执行→复盘
```

---

## 2. 总体架构

### 2.1 五大子系统

五个子系统共享同一个 FastAPI 进程与 SQLite 数据库：

```
┌──────────────────────────────────────────────────────────────────┐
│                    SecNews 单进程架构 (127.0.0.1:8000)             │
│                                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │  SecNews   │ │ Knowledge  │ │ Security   │ │  CodeGarden  │  │
│  │  热点聚合   │ │ LLM-Wiki   │ │ Graph      │ │  项目管理     │  │
│  │ 30+源采集   │ │ 文件+DB双写 │ │ ATT&CK/CVE │ │ 服务/资源/事件│  │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └──────┬───────┘  │
│        └──────────────┴──────┬───────┴───────────────┘          │
│                       ┌──────┴──────┐                           │
│                       │ MCP Server  │ ← AI Agent 标准协议接入     │
│                       │ 9 tools     │                           │
│                       └─────────────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈总览

| 层 | 技术 | 说明 |
|----|------|------|
| 后端框架 | Python + FastAPI | 同步 DB 调用，仅 HTTP 异步 |
| 数据库 | SQLite (WAL 模式) | thread-local 连接、autocommit、单 worker |
| 调度 | APScheduler (AsyncIOScheduler) | 43 个 job，max_instances=1 + coalesce=True |
| 前端 | React 18 + Vite 5 + TypeScript | Tailwind CSS、react-router v6、50+ lazy 组件 |
| 图表 | ECharts 6 | echarts-for-react 封装 |
| 测试 | pytest（2286+ 后端）/ Vitest + jsdom（290+ 前端） | CI 全量执行 |
| 加密 | cryptography Fernet | PBKDF2 派生 master key |
| MCP | fastapi-mcp | stdio + SSE 双通道 |

### 2.3 系统上下文

- **输入侧**：30+ 外部数据源（RSS/API/爬虫），经可选代理（`backend/proxy_config.json`）
- **输出侧**：Web UI（8898）、REST API（8000）、MCP 协议（stdio/SSE）、导出文件（CSV/XLSX/Markdown）
- **同步侧**：WebDAV（坚果云）跨设备配置同步，zip + Fernet 信封加密
- **Agent 侧**：Claude/Cursor 等 AI Agent 通过 MCP 或直接读写 `knowledge/` 目录参与知识闭环

---

## 3. 后端架构详解

### 3.1 分层结构

```
backend/
├── main.py              # 入口: lifespan(启动链) + CORS + TraceID 中间件
├── api/                 # REST 层 — 51 routers, register_routers() 聚合注册
├── services/            # 业务逻辑 — 81 services（sync/codegarden_*/kl_*/security_*）
├── repository/          # DAO 层 — 36 repos, db.py(thread-local) + migrations/(60 SQL)
├── collectors/          # 14 collectors extends BaseCollector + support 模块
├── parsers/             # 独立解析器注册表 (base_parser + RawItem)
├── quality/             # 13 质量门禁 + QualityGatePipeline (loose/strict)
├── scheduler/           # APScheduler 封装 — HotspotScheduler + 43 jobs
├── security/            # Security Knowledge Graph (ATT&CK STIX / CVE 提取 / 合规种子)
├── domain/              # Pydantic models (HotspotItem, KnowledgeItem...)
└── config.py / crypto.py / extensions.py   # 配置 / 加密 / 扩展开关
```

**关键模式**：
- `api/__init__.py` 的 `register_routers()` 用 **lazy import** 注册全部 router，避免循环依赖
- 每个 repo 导出 **singleton 实例**；`get_connection()` 为 thread-local + autocommit
- 启动 lifespan 顺序：日志 → init_db → cache warmup → export 预构建 → MCP seeding → scheduler → auto-unlock → knowledge watchdog → startup catchup → 打点 `startup_complete`

### 3.2 API 面（51 routers）

核心分组（节选，均挂 `/api/*` 前缀）：

| 域 | Routers | 说明 |
|----|---------|------|
| 资讯 | hotspots, trends, categories, sources, favorites, history, refresh | 热点查询/趋势/收藏/手动刷新 |
| 知识 | knowledge, knowledge_chunks_api, content, reviews, annotations | 条目 CRUD / FTS5 chunk / 日历草稿 / SM-2 / 笔记 |
| 判断 | quality, security, kl_metrics_api, kl_rollback_api, attention_events_api | 门禁拒绝明细 / 安全图谱 / KL 指标回滚 / 注意力 |
| 行动 | reports, weekly_report, todos, bid_alert, skills | 日报周报 / 待办 / 标书提醒 |
| 系统 | health, settings, maintenance, cache, events(SSE), proxy, llm_status | 健康/设置/VACUUM/缓存/SSE 推送 |
| 扩展（门控） | sync, codegarden, codegarden_ops, codegarden_phase14, mcp*, tech_stack, search, digests, recommend... | 按 `is_extension_enabled()` / `config.feature_*` 条件注册，关闭时 404 |

### 3.3 调度器（43 jobs）

`HotspotScheduler` 基于 AsyncIOScheduler，并发防护三件套：`max_instances=1`（同 job 不重叠）、`coalesce=True`（错峰合并）、`start_date=now`（修复 next_run_time=None 导致的永久停摆 bug）。job 按「节奏」分四类：

| 节奏 | 代表 job | 说明 |
|------|----------|------|
| 高频（60s–5min） | collect_all(300s), cg_event_process(60s), catchup_watchdog(60s), kl_trigger_t1(60s), source_scheduler_tick(60s), url_full_check(300s), auto_extract_alert(60s) | 采集主循环 + 触发器链 |
| 中频（10–30min） | kl_trigger_t2(120s), kl_dead_letter_retry(600s), kl_trigger_t3(600s), security_entity_concept_sync(600s), attention_aggregate(1800s), knowledge_classify(1800s), knowledge_chunk_generation(1800s), cve_sync_to_security(1800s), bid_expiry_check(1800s), source_health_check(900s) | 流水线推进 |
| 低频（小时级） | cg_drift_assess(3600s), kl_trigger_t4(1800s), content_draft_generation(6h), knowledge_stub_backfill(6h) | 深加工 |
| Cron 定时（Asia/Shanghai 为主） | compile_daily(02:00), compile_consumer(02:30), profile_decay(03:00), source_revival_check(03:00), source_probe(03:30), daily_db_backup(04:30), stats_daily(06:00), digest_generator(08:00), sm2_daily_push(08:00), map_rebuild_daily(02:00), weekly_maintenance(周日04:00), quality_logs_cleanup(周日05:00), mitre_sync(周日04:00), sync(周一10:30), cg_upstream_sync(09:00), weekly_report(周一02:00 UTC), daily_snapshot(00:30 UTC) | 维护与产出 |

**job 门控**：`_JOB_EXT_MAP` 把 7 个 job 归属到扩展域（sync / codegarden / codegarden_phase2b / tech_stack / security_graph），扩展关闭时对应 job 不调度。

**collect_all post-ingest 链**：v1.8 重构后，trend_rebuild、url_content_check、export_rebuild、security_enrichment、fts_rebuild 五个原独立 job 收敛进 `collect_all_job` 尾部的 post-ingest 链——有新数据才重建，避免空转。

### 3.4 采集器体系

14 个 BaseCollector 子类 + support 模块，覆盖 7 大领域 30+ 源：

| Collector | 领域 | 典型来源 |
|-----------|------|----------|
| security_collector | 安全 | 安全周刊/RSS 聚合（17 源） |
| ai_security_collector | AI×安全 | OWASP LLM Top 10、对抗 ML |
| ai_collector / hn_collector / reddit_collector | AI/社区 | AIhot / Hacker News / Reddit |
| github_collector / ossinsight_collector | GitHub | Trending / OSSInsight |
| tech_collector | 科技 | 科技媒体 RSS |
| finance_collector / openbb_collector | 金融 | 金十 / CLSD / OpenBB |
| startup_collector | 创业 | 创业媒体 |
| bid_collector | 标讯 | 搜狗搜索 + 状态查询（bid_search/bid_status/sogou_search） |
| telegram_collector / gdelt_collector | 补充 | Telegram / GDELT（延迟源，反爬时返回空） |

support 模块：`parsing.py`/`keywords.py`（从 base.py 提取的解析与关键词）、`fetchers.py`/`session.py`（HTTP 与会话）、`quality_hook.py`（门禁挂钩）、`item_builder.py`/`id_factory.py`（条目构造与 ID）、`aggregator.py`（聚合编排）。

### 3.5 质量门禁流水线

13 道 gate 由 `QualityGatePipeline` 串联，loose/strict 双模式（strict 下任一 fail 即拒绝入库）：

```
schema → duplicate → recency → title_summary → url_validity → final_url
→ url_content → noise_content → category_match → author_verification
→ source_reputation → bid_recency(标讯专用) → content_quality
```

所有检查结果写入 `quality_check_logs`（归档机制：每周日归档保留 7 天 + incremental_vacuum 回收空间）；被拒条目进入拒绝明细页可人工复核。来源信誉分由 `source_reputation_rebuild` 每 6h 重算并反哺门禁。

---

## 4. 前端架构详解

### 4.1 结构

```
frontend/src/
├── App.tsx               # 仅组合: ThemeProvider + AppRoutes
├── routes/
│   ├── index.tsx          # 路由表 = 应用结构图（三层架构路由集中声明）
│   └── lazy-imports.ts    # 50+ React.lazy 集中管理
├── components/            # ~150 组件（含 knowledge/ security/ codegarden/ 子目录）
│   ├── PageLayout.tsx     # 嵌套 Layout（ToastProvider + 容器）
│   ├── Icon.tsx           # 共享 SVG 图标
│   └── ...
├── hooks/                 # useHotspotData / useFavorites / useSSE / useFeatureFlags...
├── contexts/ThemeContext  # 明暗主题
└── types/index.ts         # 共享类型 + CATEGORIES 表
```

### 4.2 路由地图（三层架构）

```
/editorial                     → / （报纸版 EditorialView 已于 2026-08-29 删除，仅保留重定向）

/data                          资料层首页（资讯流）
/data/import /data/favorites   导入 / 收藏
/data/history                  历史（useFavorites 共享 store）
/judge                         判断层首页
/judge/trends /judge/bid-analysis  趋势 / 标讯分析
/action                        行动层首页
/action/report /action/compound    报告 / 知识复利
/action/todos /action/outbox       待办 / 整理
/action/review /action/skills      复习 / 技能
/action/codegarden[/phase2b]       CodeGarden（feature 门控）
/action/bid-alert                  标书提醒

/knowledge/*                   知识管理四大领域 + 六认知模式:
  import / process / compile / compound    信息导入→处理→编译→复利
  briefing / scan / deep-read / alert      简报 / 扫描 / 深读 / 告警
  outbox / review / heatmap                整理 / 复习 / 注意力热力图

/secrets /sync /settings /report   密钥 / 同步(门控) / 设置 / 报告
/deep/:type/:id                    跨实体深读视图
* → /data                          未匹配回落（扩展关闭时旧深链不白屏）
```

前端同样实现 Core/Extension 分层：`useFeatureFlags()` 从后端读取 gates，codegarden/sync 等路由条件渲染，core 路由永远注册。

### 4.3 前后端对齐机制

- SSE（`/api/events`）实时推送采集进度、告警等事件 → `useSSE` hook 消费
- Feature Gates 通过 API 下发，前后端共享同一份开关语义（关闭 = 路由不渲染 + API 404 + job 不调度，三处一致）

---

## 5. 五大子系统功能全景

### 5.1 SecNews 热点聚合

- **多域采集**：7 领域（安全/AI/金融/创业/标讯/科技/GitHub）30+ 源，14 collector 并行抓取
- **追抓（catchup）**：按 per-source checkpoint 追补「本周一以来」缺口；watchdog 每 60s 巡检队列；死源每日复活探测 + 每日探活
- **标讯专线**：搜狗搜索抓取 + 地区筛选 + 过期检查（30min）+ 竞品分析与标书提醒
- **消费界面**：资料层资讯流（领域筛选/排序/搜索）、收藏/历史、导出（CSV/XLSX/MD）
- **趋势与报告**：趋势快照（每日）、日报/周报/月报自动生成（Editorial 风格）

### 5.2 Knowledge LLM-Wiki

文件系统知识库，人类与 AI Agent 双读写：

```
knowledge/
├── items/       L1 条目（~405 个 .md，YAML frontmatter + 正文）
├── concepts/    L2 概念（~35 个 .md + graph.json 知识图谱）
├── learning/    L3 学习计划 + 任务队列（pending/processing/done/failed）
├── content/     L4 创作（drafts + calendar.json 发布日历）
├── summaries/   周期性摘要
├── SOUL.md      用户角色画像（自动生成：身份/深度/兴趣/习惯/盲区）
├── _MAP.md      自动生成的知识地图（每日重建）
└── _SCHEMA.md   数据契约
```

**双向同步**：watchdog（默认开启）监听文件变更 debounce 后回灌 SQLite；DB 写入同时落盘 .md。SQLite 为读缓存，`.md` 文件为 source of truth。

**KL 五阶段生命周期**（自动化触发器链）：

```
kl:raw ──T1(60s)──▶ kl:refine ──T2(120s)──▶ kl:link ──T3(600s)──▶ kl:structure ──T4(1800s)──▶ kl:publish
 原始入库            评分+标签完成        实体关联完成        摘要+结构化完成         已发布
```

配套：死信队列监控（10min 重试）、失败回滚 API（`/api/kl/rollback`）、触发器指标（`/api/kl/metrics`）。

**六种认知模式**：Briefing（每日简报 08:00 自动生成）/ Scan（快速扫描）/ DeepRead（深读 + chunk 原文跳转）/ Alert（规则告警）/ Outbox（收集箱整理）/ Review（SM-2 间隔复习，每日推送到期项）。

**注意力经济**：5 维加权评分（view_count/dwell_time/scroll_depth/is_favorited/annotation_count，0-100），30 分钟聚合 job + 30 天窗口 + 自动清理；热力图可视化注意力分布。

**复利闭环**：编译消费者每日 02:30 消费积压任务；内容草稿每 6h 从已发布条目自动生成；知识地图每日重建；SOUL 画像每周日刷新（soul → migrate → summary 维护链）。

### 5.3 Security Knowledge Graph

- **实体与边**：CVE / 攻击技术 / 威胁组织 / 合规条款构成属性图，`SecurityGraphEngine` 提供图查询
- **MITRE ATT&CK**：STIX 数据每周日同步；CVE 每 30 分钟流入 security 实体
- **术语标准化**：terminology_service 归一化安全术语；实体↔概念统一 job（10min）打通 security 与 knowledge 两套体系
- **前端呈现**：SecurityGraph 力导图、SecurityTimeline 时间线、实体详情、合规矩阵（ComplianceMatrix）、术语标准化工具

### 5.4 CodeGarden 项目管理

个人代码项目全生命周期：

| 模块 | 能力 |
|------|------|
| M1 项目看板 | cg_projects CRUD、上游仓库同步（每日 09:00）、知识条目一键转项目（`from-knowledge`，project_id 双向引用）|
| M2 服务网格 | lsof/docker/pm2 自动发现本机服务（5min 扫描）、拓扑 SVG、日志/指标/重启、8898 端口保护 |
| M3 资源中枢 | cg_resources（port/domain/env_template/volume），Fernet 加密 env，域名端口冲突检测 |
| M4 联动引擎 | cg_dependencies 依赖图 + BFS 影响分析、cg_events 事件总线（60s 处理）、Playbook YAML 编排 |
| Phase 14 | 技术栈漂移评估（每小时）：用 knowledge 条目评估项目技术栈过时风险 |

### 5.5 MCP Server（AI Agent 接入层）

基于 fastapi-mcp，把 9 个 REST 端点 1:1 暴露为 MCP tool：

- **读（5）**：search_hotspots / get_hotspot / list_favorites / search_knowledge / get_personal_profile
- **写（4）**：add_favorite（标记 created_via='mcp'）/ remove_favorite / add_annotation / update_knowledge_item
- **双通道**：stdio（本地单进程，Agent 直接拉起 `backend.mcp_stdio_main`）+ SSE `/mcp/sse`（HTTP 调试/远程）
- **治理**：tool 元数据启动时幂等 seeding 到 mcp_tool_registry 表；绑定 127.0.0.1；feature 关闭时 SSE 404、stdio 打印警告退出；另有 score_item/enrich_concept/link_items 等 Agent 侧写 tool（副作用模式）

---

## 6. 数据模型与存储体系

### 6.1 存储分工

| 存储 | 角色 |
|------|------|
| SQLite（60 migrations） | 全系统唯一关系库：hotspots/knowledge/concepts/security/cg_* 等 36 张 repo 对应表 |
| FTS5 | chunk 级全文检索（段落切分，char_start/end 支持原文跳转） |
| knowledge/*.md | 知识源头文件，watchdog 双向同步 |
| backend/hotspot.db.bak-* | 每日 04:30 在线备份，保留最近 7 份 |
| WebDAV zip 包 | 跨端配置同步载体（Fernet 信封加密） |

### 6.2 Knowledge Item Schema（核心契约）

```yaml
id / title / source(cubox|bookmark|secnews|secnews_archive) / source_url / ingested_at
lifecycle: kl:raw → kl:refine → kl:link → kl:structure → kl:publish   # 五阶段
domain / topic / type(news|analysis|paper|tutorial|tool|opinion|github) / difficulty
tags[] / concepts[] / related_items[]
mastery(0-100) / last_reviewed / review_count          # 学习状态
attention_score                                         # 注意力评分
project_id                                              # CodeGarden 反向引用（无 FK，应用层保证一致）
```

Concept Schema：slug/title/domain/aliases/source_items/local_wiki_ref（联邦语法 `[[wiki:local:...]]` / `[[wiki:hotspot:...]]`）。

### 6.3 同步合并引擎

跨端同步拆三个文件保证可测性：

- `sync_service.py`：push/pull/bidirectional 编排
- `sync_merge.py`：3-way merge——record 级对齐 + field 级 last-write-wins
- `sync_bundle.py`：build_bundle 序列化 + Fernet 加解密（PBKDF2 master key 派生）

---

## 7. 核心业务流程

### 7.1 主数据流：采集 → 门禁 → 存储 → 消费

```
[30+ 外部源]
    │  14 collectors 并行抓取 (fetchers/session/proxy)
    ▼
RawItem (parsers 解析标准化)
    │
    ▼
QualityGatePipeline (13 gates, loose/strict)
    ├─ pass ──▶ hotspots 表 ──▶ post-ingest 链:
    │           trend_rebuild → fts_rebuild → security_enrichment
    │           → url_check → export_rebuild
    │           ──▶ SSE 推送前端实时刷新
    └─ reject ▶ quality_check_logs ──▶ 拒绝明细页（人工复核）
```

### 7.2 知识流水线（KL 生命周期）

```
收藏/导入 (cubox / bookmark / secnews_archive)
    ▼
kl:raw ──T1──▶ 自动打分 + 标签提取 (auto_classifier + extract)
    ▼
kl:refine ──T2──▶ concept_linker 实体关联 (tag→concept 映射)
    ▼
kl:link ──T3──▶ 摘要与结构化 (compile_daily 每日编译兜底)
    ▼
kl:structure ──T4──▶ publish ──▶ 内容草稿生成 / 简报 / 周报消费
    │
    └─ 任一阶段失败 → 死信队列 (10min 重试) → rollback API 可人工回退
```

### 7.3 注意力反馈环

```
前端埋点 (浏览/停留/滚动/收藏/批注)
    ▼
attention_events 实时记录 ──▶ 30min 聚合 job (30 天窗口)
    ▼
attention_score (0-100) 反哺排序与推荐 ──▶ 热力图可视化
```

### 7.4 CodeGarden 联动流

```
knowledge item ──POST /api/codegarden/from-knowledge──▶ cg_projects
    (project_id ↔ source_item_id 应用层双向写入)

技术栈漂移: cg_projects.tech_stack × knowledge 条目
    ──每小时 cg_drift_assess──▶ 漂移报告 (哪些技术该更新了)

服务网格: lsof/docker/pm2 发现 ──▶ cg_services ──▶ 依赖图 + BFS 影响分析
    ──▶ 事件总线 (cg_events) ──▶ Playbook 自动处置
```

### 7.5 跨端同步流

```
本地变更 ──▶ build_bundle (序列化 + 版本 base)
    ▼
3-way merge (base/local/remote, field 级 LWW)
    ▼
Fernet 信封加密 ──▶ zip ──▶ WebDAV (坚果云)
    ▼
其他设备 pull ──▶ 解密 ──▶ merge ──▶ 本地落库
（定时: 每周一 10:30 Asia/Shanghai; cg_services 含加密字段同步,
  resources/dependencies/events 设备本地不同步）
```

---

## 8. 操作流（用户视角）

### 8.1 首次安装

```bash
# 1. 后端
pip install -r backend/requirements.txt
# 2. 自配代理 (安全/GitHub 采集必需): backend/proxy_config.json (见 README)
# 3. 前端
cd frontend && npm install && npm run dev     # http://localhost:8898
python run.py                                  # http://127.0.0.1:8000
```

### 8.2 日常操作路径

| 场景 | 操作路径 |
|------|----------|
| 早间简报 | 打开 `/knowledge/briefing` → 看 08:00 自动生成的每日简报 → 点感兴趣条目进深读 |
| 快速扫热点 | `/data` 资料流 → 领域筛选 → 收藏（进知识管线）或忽略 |
| 沉淀知识 | 收藏条目自动 kl:raw → 触发器链自动推进 → `/knowledge/process` 查看处理进度 |
| 深度学习 | `/knowledge/scan` 扫描模式 → 选条目 DeepRead（chunk 原文跳转）→ Review 模式做 SM-2 复习 |
| 写作输出 | `/knowledge/compound` 复利仪表盘 → 已发布条目自动成草稿 → content/drafts 编辑 → 发布日历排期 |
| 安全研判 | `/judge` → 安全图谱查实体关联 → 时间线看 CVE 演进 → 合规矩阵对标 |
| 项目巡检 | `/action/codegarden/phase2b` → 服务网格拓扑 → 依赖影响分析 → Playbook 处置事件 |
| 标讯跟进 | `/data?category=bid` 地区筛选 → `/action/bid-alert` 设置提醒 → 过期自动检查 |
| 跨端同步 | `/sync` 页手动 push/pull（或等待周一自动同步）→ 冲突由 3-way merge 解决 |
| 密钥管理 | `/secrets` 录入 LLM API Keys → OS keychain 自动解锁（Fernet 加密落库） |

### 8.3 AI Agent 操作流

```
Agent 启动 ──stdio 拉起 hotspot MCP server──▶ 获得 9 tools
    ▼
search_knowledge("零信任最新资料") ──▶ 得到条目列表
    ▼
get_hotspot(id) 详情 ──▶ add_favorite(id) 收藏 ──▶ 进入 KL 管线
    ▼
add_annotation(id, "关注其绕过手法") ──▶ 批注计入注意力评分
    ▼
update_knowledge_item(id, {...}) 修正元数据
    （或直接读写 knowledge/items/*.md — watchdog 自动同步 DB）
```

---

## 9. AI 能力与 MCP 集成

### 9.1 Hybrid AI 原则

**代码能答的不用模型**（Rule 5）：路由/重试/确定性转换全部代码实现；LLM 仅用于分类、摘要、提取、起草等判断型任务。

### 9.2 LLM Provider

- **商汤日日新**（云端）+ **Ollama**（本地）双通道，经统一的 AIService 门面调用
- `llm_status` API 暴露可用性状态；密钥在 `/secrets` 管理（Fernet 加密）
- 详细配置见 `docs/llm_config.md`

### 9.3 LLM 应用点

| 场景 | 实现 |
|------|------|
| 自动分类 | auto_classifier：tag → domain/topic 建议 |
| 标签提取 | extract API + auto_extract_alert job（60s 批处理） |
| 概念链接 | concept_linker：tag → concept 映射，构建知识图谱 |
| SOUL 画像 | soul_service：从统计聚合角色画像（规则为主） |
| 内容草稿 | 从已发布条目生成初稿（每 6h） |
| 编译消费 | compile 消费者对积压任务做规则式分类流转（确定性，不走 LLM） |

---

## 10. 安全设计

| 维度 | 方案 |
|------|------|
| 密钥存储 | Fernet 对称加密落库，master key 经 PBKDF2 派生；OS keychain 自动解锁 unlock 状态 |
| 代理隔离 | 外部抓取统一走 proxy_config.json（gitignore，首次安装自配） |
| MCP 暴露面 | 默认绑定 127.0.0.1，改 0.0.0.0 输出 warning；tool 白名单 include_operations |
| 端口保护 | CodeGarden 资源中枢保护 8898 端口不被占用 |
| CORS 白名单 | 仅 localhost:8898/8899/8000 四个 origin |
| 可观测性 | TraceIDMiddleware 全链路 trace id；结构化日志 log_event；startup_complete 打点 |
| 数据安全 | 每日在线备份保留 7 份；quality_logs 归档 + incremental_vacuum 防 1.35GB 膨胀复发 |
| 同步安全 | WebDAV 传输前 Fernet 信封加密，密钥不出本机 |

---

## 11. 质量保障与测试体系

- **后端**：pytest 2286+ tests，tmp_path + monkeypatch 做 DB 隔离；纯函数测试（test_sync_merge/test_auto_classifier/test_knowledge_watcher）最快验证核心算法
- **前端**：Vitest + jsdom 290+ tests，与组件同目录存放；Playwright 用于 E2E
- **CI**（`.github/workflows/ci.yml`）：Python compile + pytest + tsc --noEmit + vitest + vite build；另有 `generate_meta.py --check` 校验 ARCHITECTURE.md 数字未漂移
- **Feature Gate 矩阵测试**：conftest autouse fixture 测试环境全开 gates，组合矩阵见 test_feature_gates.py
- **命令速查**：

```bash
python -m pytest backend/tests/ -k "merge" -v      # 后端单测
cd frontend && npx tsc --noEmit && npx vitest run  # 前端类型+测试
python scripts/generate_meta.py                    # 同步架构文档数字
```

---

## 12. 部署运维与扩展机制

### 12.1 运维要点

- **单 worker 铁律**：SQLite WAL 下必须 WORKERS=1，避免锁竞争
- **备份恢复**：每日 04:30 online backup → `backend/hotspot.db.bak-*`，直接替换即可恢复
- **维护 API**：maintenance（vacuum/cleanup）、cache（clear/stats）、health（含 scheduler 状态）
- **降级开关**：catchup_on_startup / knowledge_watchdog_enabled / feature_mcp 等均可 env/TOML 关闭，故障时逐个隔离

### 12.2 Feature Gates 与扩展开发

开关源 `backend/config/feature_gates.toml`，五域：codegarden / mcp / sync / tech_stack / security_graph。默认开启 sync，其余默认关闭。env 覆盖优先级最高：

```bash
HOTSPOT_FEATURE_GATES='{"extensions": {"mcp": true}}'   # 临时开启 MCP
```

新增扩展的三处接线（缺一不可）：router 条件注册（api/\_\_init\_\_.py）→ job 门控（scheduler._JOB_EXT_MAP）→ 前端 useFeatureFlags 条件渲染。与 core router 白名单防重叠断言保证 core 永不消失。

### 12.3 版本演进脉络

| 版本 | 里程碑 |
|------|--------|
| v0.3.x | Phase 11-17：HN/Reddit/GDELT/OpenBB 采集、chunk+FTS5、注意力评分、六认知模式 |
| v1.3-v1.5 | SSE 实时推送、OS keychain、CodeGarden MVP（Phase 2a）、服务网格/资源中枢/联动引擎（Phase 2b） |
| v1.7 | 笔记空间、SM-2 复习、告警系统、统一搜索、KL 触发器 T1-T4、MCP Server（Phase 7）、Agent 双向环（Phase 5） |
| v1.8-v1.9 | catchup 追抓、死源复活、job 收敛（R3）、Editorial 报纸版式、日报月报 API |
| v0.4.0 | Second Brain 三层架构重构、KL 五阶段取代 SAG 三阶段 |
| v0.4.3 | Core/Extension 软分层 + Feature Gates、复利驱动器（SM-2 推送/知识地图/编译消费者）、AST 元数据校验 |
| 当前 | Hybrid AI（商汤日日新 + Ollama）、AIService 门面统一 LLM 调用 |

### 12.4 后续方向（摘自 roadmap）

- AI 协作深化（M7-M12）：Agent 深度参与 CodeGarden 开发流程
- 30 天自动归档、跨机网格（多设备服务互联）
- MCP tool 家族扩展与更多 Agent 侧写能力

---

## 附录 A：关键代码入口索引

| 模块 | 路径 |
|------|------|
| 应用入口/lifespan | backend/main.py |
| 路由聚合 | backend/api/\_\_init\_\_.py |
| 调度器 | backend/scheduler/scheduler.py（43 jobs + _JOB_EXT_MAP） |
| 采集基类 | backend/collectors/base.py |
| 质量流水线 | backend/quality/pipeline.py |
| DB 初始化 | backend/repository/db.py + migrations/ |
| 同步引擎 | backend/services/sync_merge.py |
| KL 触发器 | backend/scheduler/jobs.py（kl_trigger_t1~t4） |
| MCP 配置 | backend/api/mcp_config.py |
| 前端路由表 | frontend/src/routes/index.tsx |
| Feature Flags hook | frontend/src/hooks/useFeatureFlags.ts |

## 附录 B：术语表

| 术语 | 含义 |
|------|------|
| KL | Knowledge Lifecycle，知识五阶段生命周期（raw/refine/link/structure/publish） |
| SOUL.md | 自动生成的用户角色画像（身份/知识深度/兴趣/习惯/盲区） |
| Attention Score | 5 维加权的注意力评分（0-100），反哺排序 |
| Feature Gate | 扩展功能开关（TOML + env 覆盖），控制路由/API/job/前端路由四层 |
| 3-way merge | 基于 base/local/remote 的三方合并，field 级 last-write-wins |
| Playbook | CodeGarden 的 YAML 编排脚本，响应事件总线自动处置 |
| Editorial | 报纸排版风格的阅读视图（全屏独立路由） |

---

*本文基于 2026-08-22 的代码库状态撰写；架构数字以 `scripts/generate_meta.py` 输出为准，改动注册代码后需同步运行该脚本。*
