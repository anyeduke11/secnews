# Hotspot v0.5 重构方案（SPEC）

> **版本:** 0.5 ｜ **日期:** 2026-08-21 ｜ **状态:** 历史存档
> **入口 README:** [README.md](README.md)
> **执行细节:** [EXEC.md](EXEC.md)

---

## 3. 第一性原理约束（不可违反）

- **P1 单人本地工作站**：SQLite 本地、无外部底座；性能是体验基线不是可选项。
- **P2 摄入量 ≫ 人工处理量**：14 采集器昼夜进料；任何 Require-LLM 路径必须限频
  （现 60s/6 次）→「先规则后 LLM」是硬约束，不是工程偏好。
- **P3 长期私有知识资产是核心**：llm-wiki-2.0(md 真源)+SQLite 是资产本体；工具可替换，
  资产不动。「dsh 会话 = 短期上下文，写回 llm-wiki-2.0 = 资产沉淀」即 P3 的执行细则。
- **P4 多程序入口 = 薄合同**：Web(editorial)/MCP(外部 AI)/CLI(脚本)/SSE(实时)/dsh(acp)
  都是入口层，不是业务载体。改造成本集中在契约，不碰业务逻辑。
- **P5 终态可读可改**：md 真源支持 git diff 友好、人可直读直改；SQLite 只做索引/index，
  任何"事实"必须在 md 里有落点。

---

## 4. 现状基线（实测，同步 PROGRESS.md）

| 指标 | 基线 | 目标 |
|---|---|---|
| 后端测试收集数 | 2547（0 error） | ≥2547，skipped 不增 |
| 冷路径 p95 | 待服务启动后测 | <150ms |
| 查询计划 | `idx_hotspot_region`+TEMP B-TREE | 出 `idx_list_visible` 无 TEMP SORT |
| 主 chunk | 1,144,684 B (1.14MB) | <300KB |
| DB 体积 | 1.0GB（质量审计日志 73% 体积，热点数据 <50MB） | <300MB（清理后）→ M2-T6 终态 HOT<80MB |
| LLM 出口 | 双入口（llm_service + ai_service） | 单契约（M4）+ 无绕过 |
| 前端 | 老版式 ~30 路由 + editorial 6 view（假数据） | 唯一 editorial 6+1 view 全真 |

勘误：迁移 061 已占用 → 从 064 起编；真膨胀源 quality_check_logs 系；hotspots 仅 2952 行。

---

## 5. 界面与数据层目标架构

```
┌────────────────────────────────────────────────────────────┐
│  统一前端 = editorial 版式（唯一 UI）                          │
│  front | judge | action | read | settings | flow |  AI ✨新增 │
└──────────────┬───────────────────────────────────────────────┘
               │  REST + SSE（前端只连 FastAPI，不直连 dsh）
┌──────────────▼───────────────────────────────────────────────┐
│  FastAPI（单 HTTP 入口）                                        │
│  ├ 51 routers + SSE 事件总线                                   │
│  ├ NEW /api/agent/* 代理（token → dsh acp）                   │
│  └ acp 子进程管理器（spawn/保活/重启/降级）                    │
└──────────────┬───────────────────────────────────────────────┘
               │  stdio JSON-RPC（dsh 规范，不暴露网络）
┌──────────────▼───────────────────────────────────────────────┐
│  DeepSeek Harness acp 后端进程                                 │
│  ctx.sessions/agents/tools(MCP→hotspot)/llm（认知层）          │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 三份契约（合同优先，先于能力）

### 6.1 CLI 契约（M2-Task5 首刀）

批处理子命令（不进 MCP）：`collect_all` `map_rebuild` `sm2_daily_push` `db_diet`
`knowledge_classify` `manual_collect` `extract` `verify_health`。
统一输出 `--json`：

```json
{ "ok": true, "code": 0, "duration_ms": 123, "data": {} }
```

子进程调用 = 确定性命令，**不经过模型轮次**。

### 6.2 SSE 事件契约（M2-Task5 首刀）

| 事件 | 新增/现有 | payload |
|---|---|---|
| `collect_done` | 现有 | `{source,count,errors,duration_ms}` |
| `alert` | 现有 | 不变 |
| `review_due` | 现有 | 不变 |
| `extract_done` | 新增 | `{item_id,tags:[],lifecycle}` |
| `job_done` | 新增 | `{type,id,duration_ms,ok}` |
| `task_done` | 新增 | `{task_id,action,result}` |

### 6.3 MCP 工具面（M4）

- **交互式（<2s，进 MCP）**：现有 9 + `read_events` + `run_extract` + `submit_review` + `create_action`（写回 hotspot todos），总计 ≤13。
- **批处理（≥2s，不进 MCP，走 CLI）**：collect_all / map_rebuild / db_diet 等。

### 6.4 /api/agent/* 契约（M4）

```
POST /api/agent/session            # 创建/复用 agent 会话
POST /api/agent/session/{id}/send  # 发消息（文本/图片）
GET  /api/agent/session/{id}/events# SSE 流（dsh turn/step/chunk 事件）
```

前端只依赖这三个端点；dsh 版本升级 = 后端代理内部改，前端零改动。

---

## 7. 里程碑与退出门禁

| 里程碑 | 退出门禁 |
|---|---|
| M1 | p95<150ms；主 chunk<300KB；缓存采样测试绿 |
| M2 | db<300MB；台账每表有 job；SSE/CLI 契约测试绿；分类存储 HOT<80MB/WARM<80MB/COLD<500MB；增量备份 backups/≤1GB；COLD Fernet 加密；CI integrity 全 ok |
| M3 | editorial 无假数据/占位；每 view 真实 API；老版式可回跳；summary<150ms |
| M3.5 | 归档 100 条→md 数对得上；retention 衰减曲线验证;v0.4 数据双轨零回归 |
| M4 | /ai 意图→工具→结果闭环；对话调 hotspot 工具；dsh 崩溃降级不 500 |
| M5 | LLM 单出口 grep 验证；版本 0.5.0；meta check；全站唯一路由入口 |

**全局结束门禁**：
1. 三份硬证据：冷路径压测报告、EXPLAIN 输出、db 体积。
2. 反向验证：删 llm.yaml 降级、dsh 离线降级不崩(由 dsh-SecNews 侧处理)、SSE 断线重连、保留知识(4152 items)零丢失。
3. 无 TODO/TBD 残留；ruff 零告警。
4. `ARCHITECTURE.md` 更新至 v0.5 现状。
5. git 历史：一任务一提交、无 force push。

**全程法**：测试基线不可退、启动迁移禁大表 UPDATE、不引外部底座、凭据只走 env、
禁 force push、dsh 改造通过 MCP 14 tools 桥接（hotspot 不嵌入 dsh 进程）。

---

## 8. 风险与反制

| 风险 | 概率 | 影响 | 反制 |
|---|---|---|---|
| dsh 是 0.1.0-rc，有破坏性变更 | 高 | 高 | 插件只依赖薄接口；契约三端点隔离，前端零改动 |
| editorial 对齐面大（14 缺 + 4 假/占位） | 高 | 高 | M3 按优先级分批；每批独立验收；老版式 M5 前可回跳 |
| llm-wiki-2.0 迁移 4152 items 风险 | 中 | 高 | v0.4 双轨共跑；SCHEMA deprecated 标兼容；M5 一次性迁移前 md 快照校验 |
| dsh 离线下 AI view 不可用 | 中 | 中 | 降级链 off/acp；离线显示 agent 离线，非 agent 页面常驻 |
| LLM 成本随 agent 引入上升 | 中 | 中 | 门禁/评分留 Python 限频；agent 只处理灰区/提炼/建议；预算配额每任务级 |
| 双记忆（dsh 会话 vs llm-wiki）撞车 | 中 | 高 | 记忆单源裁决：llm-wiki-2.0 可真源，agent 持久产物强制经 ai_hub 写回 |
| 性能四板斧与前端收缩互相干扰 | 中 | 中 | M1 前端拆包与 M3 editorial 收编先做基准，两者独立门禁 |

---

## 13.4 记忆单源裁决（M4-T18 核心）

```
dsh 会话层 (短时上下文)        llm-wiki-2.0 + SQLite (长时资产)
        │                              ▲
        │ 持久产物                      │
        │ (提炼/建议/flag)             │
        └────► ai_hub.py ─────────────┘
                ▲
                │ 唯一写路径
                │
        编辑前/后端自动保存钩子
```

**强约束**：
- dsh 内部 ctx/sessions/agents 只保留当前 turn 上下文
- 任何"我想保存这个" / "flag 这个条目" / "提炼 X" — 必须经 ai_hub 写回 llm-wiki-2.0 + SQLite
- ai_hub.py 是 LLM 唯一写路径（M5 合并后 grep 验证）

---

## 15. 元规则（与 §7 全程法并列，2026-08-21 增补）

- **每个里程碑收尾前必查**：CI 全绿 + 2547 tests collected + ruff 干净 + 一任务一提交
- **M3-T6 开工前必先**：拆 EditorialView.tsx (1067 行) → 6 view 组件 (front/judge/action/read/settings/flow)
- **M4-T15 开工前必先**：vendor/dsh 部署 + HarnessClient 冒烟
- **M5-T19 开工前必先**：test_llm_service 2547 baseline + mcp_agent_tools 4 tool 现状
- **PROGRESS.md 每 commit 必更新**：当前在哪个 Task、下一 commit 计划

---

## 18. 存储哲学反转：llm-wiki-2.0 主存储（2026-08-22 增补，Duke 拍板）

> **触发**: M2-T6 温度分层完成后主库仍有 1.04GB。实测发现臃肿根源不是业务数据
> （hotspots 仅 4891 行，全部业务表 <20MB），而是运营遥测
> （quality_check_logs_archive 265 万行 / warm qcl 121 万 / crawler_runs 16 万 /
> raw_items 13.8 万）+ 1.27GB 旧备份残留。
> 结论：**数据库不该承载知识资产的全量存储**。

### 18.1 参照模型：SAG（Zleap-AI/SAG）

SAG 的核心思想：**Agent 不查"原始数据湖"，而是查"结构化知识层"**。
原版用 RAG 向量库做知识层；hotspot 的等价物是 llm-wiki-2.0（文件系统知识库，
人和 agent 都可读写）。替换关系：

| SAG 组件 | hotspot v0.5 等价 | 说明 |
|---|---|---|
| 原始数据源 | collectors 抓取流 | 不变 |
| RAG 向量库 + chunk 检索 | **llm-wiki-2.0** items/concepts .md 文件 | 文件优先，grep/glob 可导航，agent 直接读写 |
| Embedding pipeline | knowledge_sync.py frontmatter 解析 | md → SQLite 只读索引 |
| Agent 工具面 retrieve() | MCP `wiki_*` 工具族 | 见 18.4 |

### 18.2 职责重划（v0.5 生效裁决）

```
┌──────────────────────────────────────────────────────┐
│  llm-wiki-2.0/  ← 知识真源（人 + agent 共同读写）      │
│  ├ items/     知识条目 (frontmatter + 正文)            │
│  ├ concepts/  概念抽取 + graph.json                   │
│  ├ learning/  学习计划 / 任务队列                      │
│  ├ content/   内容创作                                │
│  └ summaries/ 周报 / 复盘                             │
├──────────────────────────────────────────────────────┤
│  SQLite  ← 运营层（不再是知识存储）                    │
│  ├ HOT: hotspots 流水 (滚动窗口, 保留 90d)             │
│  ├ WARM: 遥测 (qcl/crawler_runs/raw_items, 保留 7d)    │
│  ├ COLD: 归档快照 (季度打包, Fernet)                   │
│  └ wiki_index: wiki 只读索引 (FTS5, 可随时重建)        │
├──────────────────────────────────────────────────────┤
│  事件对应表 (NEW) ← 两世界的唯一桥梁                   │
│  └ wiki_events(id, ts, kind, wiki_path,               │
│                db_table, db_row_id, agent, payload)   │
└──────────────────────────────────────────────────────┘
```

**三条强约束**：
1. **知识写入只有一条路**：collector/agent 产出 → ai_hub.py → 写 `.md` 文件 → watcher 同步索引。禁止直接 INSERT 业务知识进 SQLite
2. **SQLite 表必须能声明自己的命运**：retention.json 每张表标注 `source: telemetry|index|event`；telemetry 表自动滚动删除，index 表可 DROP+重建
3. **体积红线**：HOT+WARM+COLD 合计 <500MB（CI 门禁，`check_backup_chain.py` 已有骨架可扩展）

### 18.3 遥测瘦身落地记录（2026-08-22 已执行）

| 动作 | 删除行数 | 效果 |
|---|---|---|
| 删 1.27GB bak-dedup-20260820 残留 | — | 磁盘 -1.27GB |
| qcl_archive >7d 清理 + VACUUM | 81.8 万 | 主库 1.04GB → **330MB** |
| warm crawler_runs/raw_items >7d 清理 | 6.5 万 + 9.0 万 | warm 320MB → **241MB** |

剩余 qcl（archive 183 万 + warm 121 万）时间戳集中在 8/15 之后，属 7 天窗口内活跃数据，
由既有调度 job 滚动清理，无需手工再删。**下一步**：把「7 天遥测窗口」固化为
scheduler job（现依赖手工脚本），并给 retention.json 补 `source` 字段。

### 18.4 新增 MCP 工具族（M3.5 交付物）

dsh/外部 agent 通过这些工具消费知识库（替代传统 RAG retrieve）：

| 工具 | 语义 | 实现 |
|---|---|---|
| `wiki_search(query)` | FTS5 全文搜 items/concepts | wiki_index 表（已有 knowledge_chunks_api 骨架） |
| `wiki_read(path)` | 读单个 .md 全文 | 直读文件 |
| `wiki_graph(concept)` | 概念邻接（graph.json BFS k=1） | concepts/graph.json |
| `wiki_write(path, fm, body)` | agent 持久产物写回 | 经 ai_hub 单一写路径 |
| `db_trace(wiki_path)` | 反查事件对应（哪些采集产生了这条知识） | wiki_events 表 |

### 18.5 与既有里程碑的关系

- **M2-T6**（已完成）：温度分层保留，但定位从"全站存储"降级为"运营层管理"
- **M3.5**（llm-wiki-2.0 迁移）：升级为 v0.5 主线——新增 wiki_events 表、wiki_* MCP 工具族、retention source 字段
- **M5**（合并）：验收标准增加「DB 体积 <500MB」+「grep 无绕过 ai_hub 的知识写入」
