# Hotspot v0.5 重构方案（EXEC）

> **版本:** 0.5 ｜ **日期:** 2026-08-21 ｜ **状态:** 历史存档
> **入口 README:** [README.md](README.md)
> **技术规格:** [SPEC.md](SPEC.md)

---

## §11 执行框架（M1→M5）

### 11.1 依赖图

```
              ┌─ T0: 基线+测试修复 ─┐
              │                       │
    T-Fix: 24 collection errors  ─────────┤  (M1 开工前置, 已在 0490470f 修)
              │                       │
        ┌─────────▼─────────┐         ┌────▼──────┐
        │ M1 性能 (P0)       │ ──────► │ M2 契约+瘦身 │
        │ T1 索引/查询       │         │ T4 db_diet │
        │ T2 cache 采样     │         │ T5 SSE+CLI │
        │ T3 vite 拆包      │         └────┬──────┘
        └───────────────────┘              │
                                            ▼
        ┌───────────────────┐         ┌────┴──────┐
        │ M3 editorial 接满  │ ◄──┐    │ M3.5 wiki2  │  (与 M3 并行, 域名不同)
        │ T6 6view 接 API   │    │    │ T10 目录+schema│
        │ T7 14 缺分 4 批   │    │    │ T11 archiver │
        │ T8 /data 退役     │    │    │ T12 retention│
        │ T9 summary API    │    │    │ T13 graph 6边│
        └───────────────────┘    │    │ T14 M5 迁   │
                                 │    └────┬──────┘
        ┌───────────────────┐    │           │
        │ M4 dsh 认知层     │ ◄──┘───────────┘  (依赖 M2 契约 + M3.5 数据)
        │ T15 agent_api     │
        │ T16 acp 管理器    │
        │ T17 AI view       │
        │ T18 记忆单源      │
        └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ M5 收尾+发版      │
        │ T19 ai_hub 合并   │
        │ T20 v0.5.0+meta   │
        └───────────────────┘
```

**并行机会**：
- M3（前端编辑）∥ M3.5（数据底座） — 域名不同
- M1 与 M2-Task4（db_diet）可微并行（M1 改 hotspot_repo 不影响 db_diet 删表）
- M4 必等 M2 契约第一刀（不然 AI view 没用 SSE/CLI 契约）+ M3.5 数据底座

### 11.2 工时估算（粗略，1 d = 1 人日）

| M | 任务 | 估时 | 关键依赖 |
|---|---|---|---|
| T-Fix | 修 24 collection errors | **0.5d** | 0490470f |
| M1 | T1 索引化收尾 | 1d | 064 迁移已写，hotspot_repo 改造已 commit |
| | T2 cache 采样 | 0.5d | T1 完成后 |
| | T3 vite 拆包 | 0.5d | 无 |
| M2 | T4 db_diet + 台账 | 1.5d | T1 完成后（避免 schema 变更撞 db_diet） |
| | T5 SSE/CLI 契约 | 1d | 无 |
| M3 | T6 6view 接 API | 2d | 必先拆 EditorialView (1067 行 → 6 组件) |
| | T7 14 项缺失 (4 批) | 4d | 见 FRONTEND_BACKEND_ALIGNMENT_AUDIT.md |
| | T8 /data 退役提示 | 0.5d | 无 |
| | T9 summary API | 1d | 无 |
| M3.5 | T10 目录+schema | 1d | 无 |
| | T11 archiver | 1d | T10 完成后 |
| | T12 retention engine | 1d | T10 完成后 |
| | T13 graph 6 边 | 1d | T10 完成后 |
| | T14 一次性迁移 4147 items | 0.5d | T11-T13 完成后, M5 前做 |
| M4 | T15-18 dsh 融合 | 3d | dsh 部署 + M2 契约 + M3.5 数据 |
| M5 | T19 ai_hub 合并 | 1.5d | 836 行单 PR 合并, test_llm_service 全绿准入 |
| | T20 v0.5.0+meta+ARCH | 0.5d | 无 |

**总估时**：~21.5 人日（不含 dsh 集成调试 1-2d buffer）

### 11.3 当前进度（截至 0490470f）

- ✅ T0 基线+测试修复（2547 tests collected）
- ✅ M1-Task1 WIP commit（hotspot_repo 改造 + IndentationError 修复）
- 🔲 M1-Task1 收尾：EXPLAIN 验证 idx_list_visible + 回填脚本跑通
- 🔲 其余全部 pending

---

## §13 dsh 融合方案（D1 决策的展开）

> ### ⚠️ 2026-08-23 路线变更（Duke 拍板，本节以下正文部分废止）
>
> **发现平行工程** `~/Documents/dsh-SecNews/SECNEWS-二次开发方案.md`（v1.0, 2026-08-22），
> 已推进到 P2 完成：P0 spike / P1 看板骨架（反代 + 报纸看板接真数据）/
> P2 能力引擎（`POST /api/cap/:id` 模板 turn + SSE + 排队 + 取消，3 个 AI 按钮真实出稿）
> 全部验证通过。其架构与本章原设计**宿主关系相反**：
>
> | | 原 SPEC §13-§17（废止） | dsh-SecNews 方案（生效） |
|---|---|---|
> | 宿主 | hotspot FastAPI spawn dsh acp 子进程 | **dsh web :3210 为宿主** |
> | hotspot 角色 | 认知层宿主 + MCP 工具面 | **确定性骨干被 BFF 反代**（采集/SQLite/KL/SM-2 原样运行） |
> | 前端 | editorial 第 7 view 'AI' 自由对话 | `/secnews` 报纸看板 + **AI 能力按钮**（不做自由对话） |
> | 部署 | vendor/dsh submodule + Python SDK | 上游锁 tag 只读 + 兄弟目录 secnews/ monorepo + `--patch` 插件 |
>
> **裁决**：
> 1. M4 以 dsh-SecNews 方案为准；hotspot 不做 acp 子进程宿主。
>    **T15a/T16/T17 原设计（agent_bridge.py spawn dsh / agent_api.py 三端点 / AIView.tsx）废止。**
> 2. 本章及 §16/§17 中仍然有效的部分：
>    - **MCP 工具面**：dsh mcp-client 连 `python -m backend.mcp_stdio_main`
>      （现 14 tools：基础 9 + wiki 4 + wiki_write），配置写法见 dsh-SecNews 方案 §6；
>    - **记忆单源裁决（§13.4）**：agent 持久产物唯一写路径 = ai_hub → wiki（不变）；
>    - **T15b runner 注册表**：`backend/config/agent_runner_schema.py` + `config/agents.yaml`
>      已落地（2026-08-23），作为 runner 元数据事实源供 dsh 侧读取。
> 3. hotspot 侧后续工作（原 M4 剩余量）：无新代码任务；仅 T18 调整为
>    「dsh agent 产物经 ai_hub 写回」（llm-wiki-2.0 就绪前暂写 knowledge/）。
> 4. **M4 执行以 `~/Documents/dsh-SecNews/SECNEWS-二次开发方案.md` 为唯一真理**，
>    本节以下原文保留作历史参考（标注 ~~废止~~ 的段落不再维护）。

### 13.1 dsh 真实结构（实测自 deepseek-ai/deepseek-harness StudyDocs 2026-08-14 zip）

```
deepseek-harness/
├── apps/         cli + web(:3080, 仅 dev 用, M5 移除)
├── packages/     34 个包 — core/acp/mcp/llm/extensions/...
│   ├── acp/          Agent Client Protocol, JSON-RPC stdio server
│   ├── mcp/mcp-client/  dsh 自己的 MCP client (能连 hotspot MCP server)
│   ├── llm/          LLM 适配层
│   └── ...
├── python/sdk/   Python 同步 stdio JSON-RPC client
│   └── src/deepseek_harness/client.py
│       class HarnessClient:
│           start() → subprocess.Popen spawn dsh 运行时 + stdio JSON-RPC
│           request/notification 队列 + 线程模型
└── python/sdk-runtime/  dsh 运行时 Python 绑定
```

**关键事实**：
- dsh 是 **TypeScript 主体**（pnpm 生态），但提供 **Python SDK**（同步 stdio JSON-RPC client）
- dsh "developer preview" — README 明确：**THERE WILL BE COMPATIBILITY-BREAKING CHANGES**（SPEC §8 已识别的风险）
- `packages/acp/` = ACP server 端；`packages/mcp/mcp-client/` = dsh 作为 MCP client 连外部 server

### 13.2 hotspot ↔ dsh 融合架构

> **~~废止~~**（2026-08-23 路线变更：hotspot 不再 spawn dsh；生效架构见 dsh-SecNews 方案 §1——
> dsh web :3210 宿主 + secnews-api BFF 反代 hotspot :8000）

```
┌─────────────────────────────────────────────────────┐
│  FastAPI lifespan                                  │
│  ├ spawn dsh 进程 (subprocess.Popen)               │
│  ├ stdio JSON-RPC 双向 (HarnessClient 封装)         │
│  ├ heartbeat 5s ping → 失败重启 (max 3 次)         │
│  └ 崩溃 → 降级 HOTSPOT_AGENT_BACKEND=off           │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│  DeepSeek Harness 运行时                            │
│  ├ acp server (协议层, FastAPI 通过 SDK 调)         │
│  ├ mcp-client → 连 hotspot MCP server (stdio)     │
│  └ llm 适配 + ctx.sessions/agents/tools             │
└─────────────────────┬───────────────────────────────┘
                      │  mcp protocol (stdio)
┌─────────────────────▼───────────────────────────────┐
│  hotspot mcp_stdio_main (现有 9 个工具)            │
│  read_hotspots / get_hotspot / search / ...         │
└─────────────────────────────────────────────────────┘
```

### 13.3 关键文件与接口

> **~~废止~~**（agent_bridge.py / agent_api.py / AIView.tsx 三文件不再创建；
> 生效文件清单见 dsh-SecNews 方案 §2 secnews/ monorepo 布局）

| 文件 | 角色 | 备注 |
|---|---|---|
| `vendor/dsh/` (新建) | dsh 源码嵌入 | git submodule 或浅 clone 锁 commit |
| `backend/services/agent_bridge.py` (新建) | HarnessClient 封装 | 启动 dsh 进程 + stdio JSON-RPC + 队列消费 + 心跳 |
| `backend/api/agent_api.py` (新建) | `/api/agent/{session,send,events}` 三端点 | token 鉴权（复用 HOTSPOT_MASTER_KEY 派生）+ SSE 流式回放 |
| `frontend/src/components/editorial/AIView.tsx` (新建) | 第 7 view, 编辑风对话 | 走 `/api/agent/*`, 不 iframe dsh web |
| `backend/services/llm_status.py` (改) | dsh 健康状态端点 | 由 agent_bridge 心跳（list_sessions 轻量 RPC）填充 |
| `backend/mcp_stdio_main.py` (不改) | hotspot MCP server | **dsh 启子进程**调 `python -m backend.mcp_stdio_main`（per dsh mcp-client config） |
| `config/llm.yaml` (不改) | hotspot 自有 LLM 配置 | ai_hub.py 用（M5 合并），与 dsh ctx.llm 并存不冲突 |

### 13.4 记忆单源裁决（M4-T18 核心）

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

### ~~13.5 降级链~~（废止）

> ⚠️ **2026-08-23 废止**：本节描述 hotspot spawn dsh acp 子进程的心跳/重启/降级设计。
> dsh-SecNews 方案中 dsh web (:3210) 是宿主进程，无 acp spawn 关系；dsh 崩溃由其自身 supervisor 处理，
> hotspot 仅作为 BFF 被反代。生效的降级语义见 dsh-SecNews 方案。

| 状态 | 行为 | 触发 |
|---|---|---|
| dsh 健康 | `/ai` 正常对话 | heartbeat OK |
| dsh 崩溃 1-2 次 | 自动重启 | agent_bridge 内 max_restart=3 |
| dsh 崩溃 3+ 次 | 降级显示 "agent 离线", 其余页面照常 | `HOTSPOT_AGENT_BACKEND=off` 等效 |
| dsh 升级破坏接口 | 前端零改动（契约 3 端点隔离） | dsh version 切换时后端代理内部改 |
| 离线首次启动 | AI view 提示 "agent 后端未就绪" | lifespan spawn 失败 |

### ~~13.6 dsh 部署步骤（M4 开工 checklist）~~（废止，被 dsh-SecNews P0 取代）

> ⚠️ **2026-08-23 废止**：vendor submodule / Python SDK / agent_bridge 等步骤不再执行。
> 生效部署方式：dsh-SecNews 方案已完成 P0-P2（`~/Documents/dsh-SecNews/` monorepo，
> `pnpm dsh web` 宿主 :3210 + BFF 反代 hotspot :8000 + MCP 桥接配置）。
> M4 后续工作 = 该方案 P3+（知识·执行按钮组等），见 PROGRESS.md c3/c4。

1. **vendor 嵌入**：`git submodule add https://github.com/deepseek-ai/deepseek-harness vendor/dsh`，锁 commit
2. **冒烟**：`cd vendor/dsh && pnpm install && pnpm run build && pnpm dsh --help`（验证 dsh 进程可启）
3. **Python SDK 安装**：`pip install -e vendor/dsh/python/sdk`（或 `pip install -e vendor/dsh/python/sdk-runtime`）
4. **冒烟 2**：`python -c "from deepseek_harness.client import HarnessClient; HarnessClient().start()"` 验证 stdio JSON-RPC 通
5. **MCP 客户端连 hotspot**：`packages/mcp/mcp-client/` 配置连 `python -m backend.mcp_stdio_main`，9 个工具可见
6. **FastAPI 集成**：实现 `agent_bridge.py` + `agent_api.py`（M4-T15/T16）
7. **前端 AI view**：`AIView.tsx`（M4-T17）
8. **联调 e2e**：意图→工具→结果闭环（M4 验收）

---

## §14 风险登记（2026-08-21 强化版）

| ID | 风险 | 概率 | 影响 | 反制 | 触发条件 | 责任人 |
|---|---|---|---|---|---|---|
| R1 | dsh 0.1.0-rc 破坏性变更 | 高 | 高 | 插件只依赖薄接口 (ctx.llm/tools/schedule/mcp-client)；契约 3 端点隔离 | dsh 升级后 HarnessClient.start() 失败 | M4 owner |
| R2 | editorial 对齐面大 (14 缺 + 4 假/占位) | 高 | 高 | 4 批分批, 每批独立验收; /data 老版式 M5 前可回跳 | T7 任一批超时 1d | M3 owner |
| R3 | llm-wiki-2.0 迁 4147 items 风险 | 中 | 高 | v0.4 双轨共跑; SCHEMA deprecated 标兼容; M5 前 md 快照校验 | 迁移脚本 hash 对账失败 | M3.5 owner |
| R4 | dsh 离线下 AI view 不可用 | 中 | 中 | 降级链 off/acp; 离线显示 agent 离线, 非 agent 页面常驻 | dsh 进程 3 次重启失败 | M4 owner |
| R5 | LLM 成本随 agent 引入上升 | 中 | 中 | 门禁/评分留 Python 限频 (60s/6 次); agent 只处理灰区/提炼/建议; 预算配额每任务级 | 月度 LLM cost > 上月 ×2 | M5 owner |
| R6 | 双记忆 (dsh 会话 vs llm-wiki) 撞车 | 中 | 高 | 记忆单源裁决: llm-wiki-2.0 真源, agent 持久产物经 ai_hub 写回 | dsh 重启后用户期望状态丢失 | M4 + M5 owner |
| R7 | 性能四板斧与前端收缩互相干扰 | 中 | 中 | M1 拆包 + M3 editorial 收编各自独立门禁, 互不阻塞 | p95 或主 chunk 任一反弹 | M1 + M3 owner |
| **R8** | **dsh 嵌入增加 hotspot 仓库体积** | **中** | **中** | **vendor/dsh/ 用 .gitignore 锁 binary + lockfile, CI 只跑 hotspot 单测不跑 dsh 内部测试** | **repo size > 500MB** | **devops** |
| **R9** | **24 errors 类 collection 退化复发** | **中** | **高** | **CI 加 `pytest --collect-only -q \| tail -1` 检查, 数字漂移即 fail** | **任何 PR 引入 import-time 错误** | **CI owner** |
| **R10** | **hotspot_repo 改造 working tree 残留 WIP** | **中** | **中** | **0490470f 已 commit 现状; M1-T1 续做前先跑 EXPLAIN, 一次性补 query 完整路径** | **git diff hotspot_repo 持续 >50 行未提交** | **M1 owner** |

---

## §15 元规则（与 §7 全程法并列）

- **每个里程碑收尾前必查**：CI 全绿 + 2547 tests collected + ruff 干净 + 一任务一提交
- **M3-T6 开工前必先**：拆 EditorialView.tsx (1067 行) → 6 view 组件 (front/judge/action/read/settings/flow)
- **M4-T15 开工前必先**：vendor/dsh 部署 + HarnessClient 冒烟
- **M5-T19 开工前必先**：test_llm_service 2547 baseline + mcp_agent_tools 4 tool 现状
- **PROGRESS.md 每 commit 必更新**：当前在哪个 Task、下一 commit 计划

---

## ~~§16 dsh 融合技术栈详解~~（2026-08-21 补 §13 不足；2026-08-23 废止）

> ⚠️ **2026-08-23 废止**：本节的 acp spawn / stdio JSON-RPC / Python SDK 三线程模型 / agent_bridge
> 契约端点等协议层设计随 §13.2/§13.3 一并废止。生效的集成方式是 **MCP 桥接**
> （dsh mcp-client 连 `python -m backend.mcp_stdio_main`，14 tools 已落地，见 04a69367）。
> 以下原文仅保留作历史参考。

### 16.1 进程层：dsh 运行时 + Python SDK 线程模型

#### 16.1.1 运行时 carrier（两种）

dsh 提供两种运行时 binary，`HarnessClient._default_launch_args()` 选择其一：

| Carrier | 形态 | 触发 | 要求 | 适用 |
|---|---|---|---|---|
| **exe（生产）** | 单文件 Node executable `dsh-jsonrpc-agent-pkg-<platform>-<arch>` | `HarnessConfig.runtime_bin` 显式指定或 wheel 自动选 | 无（自带 Node runtime） | **hotspot 选这个** |
| **node（dev-only）** | `node runtime/node/node_modules/@deepseek-ai/dsh-sdk-jsonrpc-demo/lib/packaged-bin.js` | `DSH_RUNTIME_MODE=node` 显式选 | 目标机 Node >= 22.19 | 开发验证 |

macOS wheel tag: `py3-none-macosx_14_0_arm64`，含 `dsh-jsonrpc-agent-pkg-macos-arm64` + `dsh-jsonrpc-agent-pkg-macos-arm64-spawn-helper`（node-pty 必需）。
Linux tag: `py3-none-manylinux_2_28_x86_64` / `py3-none-manylinux_2_28_aarch64`。

**hotspot 安装命令**（M4-T15 部署步骤 3）：
```bash
pip install deepseek-harness-runtime-bin   # exe carrier wheel, macOS arm64
pip install deepseek-harness-sdk           # Python SDK
```

#### 16.1.2 进程 spawn 与 stdio JSON-RPC

`HarnessClient.start()` 调用 `subprocess.Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)`：

- **行缓冲（bufsize=1）+ JSON Lines**：每行一个 JSON 对象，`\n` 终止
- **stdout** 留给 JSON-RPC 协议帧（response / notification / server-request）
- **stderr** 留给 dsh 日志（被 SDK 收到 deque 保留最近 400 行）
- **stdin** 写 client 发的 request / notification
- **text=True, encoding="utf-8"**：字符串 IO，SDK 内部 `json.dumps(message, separators=(",", ":")) + "\n"` 紧凑序列化

#### 16.1.3 三线程模型

| Thread | Name | 职责 |
|---|---|---|
| main | (caller) | request 发起 + 收 response/notification 队列 |
| daemon | `dsh-runtime-reader` | 从 stdout 逐行读 JSON，按 `id`/`method` 分发到 `_responses` / `_notifications` / `_requests` queue |
| daemon | (stderr) | 从 stderr 收日志行到 deque(maxlen=400) |

消息分类（`_handle_message`）：
```
{"id": ..., "method": "..."}        → IncomingRequest → _requests queue (server→client 调用)
{"id": ..., "result": ...}          → 找对应 waiter, 推 result
{"id": ..., "error": {...}}         → 找对应 waiter, 推 JsonRpcError(code, message, data)
{"method": "...", "params": ...}    → Notification → subscriber 队列或 _notifications
```

#### 16.1.4 关键 API 速查

```python
from deepseek_harness.client import HarnessClient, HarnessConfig
from deepseek_harness.errors import JsonRpcError, TransportClosedError
from deepseek_harness.models import Notification

# 1. 启动
config = HarnessConfig(
    request_timeout_seconds=30.0,
    shutdown_timeout_seconds=1.0,
)
client = HarnessClient(config)
client.start()  # spawn 进程 + 起 reader/stderr thread

# 2. initialize (必传 provider + model)
init = client.initialize(
    cwd="/Users/duke/Documents/hotspot",
    provider="deepseek",
    model="deepseek-chat",
    max_tokens=4096,
)

# 3. 订阅 notification (dsh turn/step/chunk 事件)
sub = client.subscribe_notifications(
    notification_filter=lambda n: n.method.startswith("session/")
)

# 4. 发 prompt (会阻塞直到 dsh 报告 end_turn / cancelled)
def on_chunk(n: Notification) -> None:
    # dsh 发 "session/update" + {"event": {"sessionUpdate": "agent_message_chunk", ...}}
    print(n.payload)

message_id = client.session_prompt(
    session_id="sess_abc123",
    content_blocks=[{"type": "text", "text": "查最近 24h 的 AI 安全热点"}],
    on_notification=on_chunk,
)

# 5. 优雅关闭
client.close()  # 发 shutdown request → stdin.close → terminate → wait → kill
```

### 16.2 工具注入：hotspot 9 tool → dsh ctx.tools 命名

#### 16.2.1 dsh mcp-client 配置（cordis.yml）

dsh 启动时读 `$DSH_CORDIS_CONFIG` 指向的 cordis.yml（plugin 组装清单）。hotspot 在 dsh 配置里加一个 mcp-hotspot 插件实例：

```yaml
# vendor/dsh/runtime/cordis.yml (hotspot 派生版)
plugins:
  # ... 默认 plugin 集 (dsh-sdk-jsonrpc-server / agent core / llm-deepseek / persistence / bash / fs)

  - id: mcp-hotspot
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: hotspot          # 决定 tool 命名空间
      transport: stdio
      command: python
      args: ['-m', 'backend.mcp_stdio_main']
      cwd: '/Users/duke/Documents/hotspot'
      toolCallTimeoutMs: 30000      # 30s (默认 60s, hotspot 9 工具大都在 1s 内)
      failOnStartupError: false     # hotspot MCP 暂时不可用不阻止 dsh 启动
      reconnect:
        enabled: true
        initialDelayMs: 500
        maxDelayMs: 30000
        maxAttempts: 10
```

#### 16.2.2 dsh 看到的 tool 命名

`mcp__<serverName>__<rawName>` —— hotspot 9 tool 在 dsh 视角的命名：

| hotspot MCP tool (raw) | dsh ctx.tools 命名 | 类 |
|---|---|---|
| `search_hotspots` | `mcp__hotspot__search_hotspots` | 读 |
| `get_hotspot` | `mcp__hotspot__get_hotspot` | 读 |
| `list_favorites` | `mcp__hotspot__list_favorites` | 读 |
| `search_knowledge` | `mcp__hotspot__search_knowledge` | 读 |
| `get_personal_profile` | `mcp__hotspot__get_personal_profile` | 读 |
| `add_favorite` | `mcp__hotspot__add_favorite` | 写 |
| `remove_favorite` | `mcp__hotspot__remove_favorite` | 写 |
| `add_annotation` | `mcp__hotspot__add_annotation` | 写 |
| `update_knowledge_item` | `mcp__hotspot__update_knowledge_item` | 写 |

dsh MCP client 启 → `listTools()` → 注册 9 个 tool 到 `ctx.tools` → 注入 system prompt 工具列表。
模型直接 `mcp__hotspot__search_hotspots({"q": "...", "time_range": "D7"})` 调，**dsh 透明转发到 hotspot 进程**。

#### 16.2.3 重连 + 工具集合更新

dsh 监听 `notifications/tools/list_changed`，自动 re-sync：
- 成功 reconnect → 替换 generation（旧 tool 仍注册直到新 generation 完成）
- 失败 reconnect → 旧 tool 仍注册但 `callTool` 会失败；`maxAttempts` 耗尽后**整体 unregister**（hotspot MCP 真的死了，AI view 提示"工具不可用"）

### 16.3 LLM 适配层：hotspot llm.yaml ↔ dsh ctx.llm

#### 16.3.1 双 adapter 模式

dsh `packages/llm/` 提供双 adapter 注册到 `ctx.llm`：

| Adapter | Package | 适用 |
|---|---|---|
| Direct DeepSeek | `llm-deepseek/` | `provider=deepseek, model=deepseek-chat`（**默认**) |
| Multi-provider | `llm-pi-ai/` | `provider=ollama/openai/qwen/anthropic`，**hotspot 既有 llm.yaml 直迁** |

env 变量：
```
DEEPSEEK_API_KEY      # llm-deepseek 必需
DEEPSEEK_BASE_URL     # 可选, 默认官方 endpoint
DSH_SESSION_ROOT      # 持久化 JSONL 根目录
DSH_CWD               # 工作目录（hotspot 仓库根）
```

#### 16.3.2 与 hotspot llm.yaml 的关系

`config/llm.yaml`（hotspot 自有）是 ai_hub.py（M5 合并的 LLM 单出口）专用；**dsh ctx.llm 走自己的 adapter**，两套并存：

```
hotspot llm.yaml  ──→  ai_hub.py  ──→  hotspot 后端逻辑 (评分/摘要/触发)
dsh ctx.llm       ──→  dsh agent  ──→  mcp__hotspot__* 调回 hotspot
```

**无冲突**：
- ai_hub.py 调 LLM 用于"评分/限频/门禁"（60s/6 次限频）—— 走 hotspot 自己的 provider
- dsh ctx.llm 用于"agent 推理" —— 走 dsh 的 provider
- 两者**通过 mcp 工具的最终落点统一**（hotspot 写库只走 ai_hub）

#### 16.3.3 M4 启动时的 provider 决策

默认 `provider=deepseek, model=deepseek-chat`（成本最低 + 中文友好）。
用户可在前端 AI view 设置里覆盖（POST /api/agent/session 的 body 加 `provider`/`model`），透传到 `client.initialize(...)`。

### 16.4 错误处理与降级

#### 16.4.1 三层降级链

| 层 | 触发 | 行为 | 状态码/UI |
|---|---|---|---|
| L1 — dsh 进程 | spawn 失败 / 3 次 restart 失败 | `HOTSPOT_AGENT_BACKEND=off` 等效，AI view 显示 "agent 离线" | HTTP 503 |
| L2 — dsh session | `session/prompt` 超时（30s） / transport 关闭 | 单独 session 失败，不影响 dsh 进程 | HTTP 504，UI 提示重试 |
| L3 — dsh tool call | mcp__hotspot__* 失败（hotspot MCP 死） | 工具不可用，agent 可继续对话或换思路 | tool result 带 `isError: true` |

#### 16.4.2 心跳 / 重启 / 优雅关闭

`agent_bridge.py` 维护：
- 启动：`lifespan startup` 调 `client.start()` + `client.initialize()`
- 心跳：每 5s 调 `client.request("ping", None, response_model=...)` —— **acp 协议不直接支持 ping**，**改用 list_sessions / list_agents 轻量 RPC**（acp 协议要新增方法 or 用空闲时段试探）
- 重启：心跳失败 → `client.close()` → `client.start()` 重建，max 3 次
- 关闭：`lifespan shutdown` 调 `client.close()` 优雅终止（`shutdown` request → stdin.close → terminate → wait 1s → kill）

#### 16.4.3 ACP 协议层的关键限制（影响 AI view 设计）

- **Fresh sessions only** —— 每次 /api/agent/session 必须 `session/new`，不能 resume/fork
- **Baseline prompts only** —— content_blocks 只支持 `text`，无图片/音频/embedded resources
- **Committed answers only** —— dsh 不返回实时 token 流 / 推理 / 工具活动 / 计划 / 标题，**只返回完整 committed message**
- → **AI view 不能做流式打字效果**，只能"等待 → 一次性出结果"。要打字效果必须在 FastAPI 端做 chunking（从 dsh 整段拿到后分片推 SSE）

### 16.5 配置面（HOTSPOT_/DSH_/provider env）

| 变量 | 来源 | 必填 | 用途 |
|---|---|---|---|
| `HOTSPOT_AGENT_BACKEND` | hotspot config.py | 否，默认 `off` | `off` = 不启 dsh；`acp` = 启 dsh 进程 + HarnessClient |
| `HOTSPOT_MASTER_KEY` | hotspot config.py | 已有 | /api/agent/* token 鉴权派生（复用） |
| `DEEPSEEK_API_KEY` | env | M4 启 dsh 时 | dsh ctx.llm (Direct DeepSeek) |
| `DEEPSEEK_BASE_URL` | env | 否 | 代理 endpoint |
| `OPENAI_API_KEY` | env | 否 | dsh ctx.llm (pi-ai 多 provider) |
| `QWEN_API_KEY` | env | 否 | dsh ctx.llm (pi-ai) |
| `ANTHROPIC_API_KEY` | env | 否 | dsh ctx.llm (pi-ai) |
| `OLLAMA_HOST` | env | 否 | dsh ctx.llm (pi-ai, ollama) |
| `DSH_CORDIS_CONFIG` | env | dsh 进程必填 | cordis.yml 路径（hotspot 在启动 dsh 时注入） |
| `DSH_SESSION_ROOT` | env | dsh 进程必填 | JSONL 持久化根（hotspot 设到 `~/.dsh/sessions/`） |
| `DSH_CWD` | env | dsh 进程必填 | hotspot 仓库根 |
| `DSH_RUNTIME_MODE` | env | 否，默认 auto | 强制用 `exe` 或 `node` carrier |

### 16.6 端到端消息流（用户输入 → AI 回复）

```
1. 用户在 editorial AIView 输入 "查 24h AI 安全热点 + 收藏前 3 条"
   ↓
2. 前端 POST /api/agent/session  {"provider": "deepseek", "model": "deepseek-chat"}
   ↓
3. FastAPI agent_api.py:
   a. 鉴权 (HOTSPOT_MASTER_KEY 派生 token)
   b. agent_bridge.create_session() →
      HarnessClient.session_prompt → "session/new" → 返回 sess_xxx
   ↓
4. 前端 POST /api/agent/session/{id}/send  {content_blocks: [{type:"text", text:"..."}]}
   ↓
5. FastAPI:
   a. agent_bridge.send(id, content_blocks) → 启后台 task
   b. 返回 202 Accepted + session_id
   ↓
6. 后台 task:
   HarnessClient.session_prompt(sess_xxx, content_blocks, on_notification=...)
   ├─ dsh 处理: LLM 推理 → 决定调 mcp__hotspot__search_hotspots
   ├─ dsh 调 mcp client → spawn python -m backend.mcp_stdio_main (or 已存在)
   ├─ hotspot MCP server 调 FastAPI 路由 → 查 hotspot.db
   ├─ 返回 tool result 给 dsh
   ├─ dsh LLM 二次推理 → 决定调 mcp__hotspot__add_favorite (3 次)
   └─ dsh 报告 end_turn → 整段 committed message 返回
   ↓
7. 后台 task 拿整段 committed message → agent_bridge.publish_event(sess_xxx, message)
   ↓
8. SSE 推: GET /api/agent/session/{id}/events → "data: {type:'message', content:'...', tool_calls:[...]}"
   ↓
9. AIView EventSource 收到 → 渲染 markdown + tool_call 历史列表
```

**关键延迟点**：
- dsh 整段（端到端）通常 5-30s（多 tool call 时更长）
- hotspot MCP 9 tool 调用大都在 <500ms（SQLite + 索引）
- **SSE 推送粒度**：FastAPI 端从整段 committed message 做 chunking 模拟流式（每 50ms 推 50 字），UI 看起来像打字

### 16.7 端到端最小可验证 demo（M4 收尾 e2e 测试）

```python
# backend/tests/e2e/test_dsh_integration.py
def test_dsh_search_and_favorite_e2e():
    """端到端: 用户问 → dsh 推理 → 调 hotspot 2 个 tool → 收藏成功"""
    with TestClient(app) as client:
        # 1. 创建 session
        r = client.post("/api/agent/session",
                        json={"provider": "deepseek", "model": "deepseek-chat"},
                        headers={"Authorization": f"Bearer {test_token}"})
        assert r.status_code == 201
        sess_id = r.json()["session_id"]

        # 2. 发 prompt
        r = client.post(f"/api/agent/session/{sess_id}/send",
                        json={"content_blocks": [{"type": "text", "text":
                            "查 24h AI 安全热点, 收藏前 3 条"}]},
                        headers={"Authorization": f"Bearer {test_token}"})
        assert r.status_code == 202

        # 3. SSE 流消费 (等 dsh end_turn, 限 60s)
        events = []
        with client.stream("GET", f"/api/agent/session/{sess_id}/events",
                           headers={"Authorization": f"Bearer {test_token}"}) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
                    if any(e.get("type") == "message" for e in events):
                        break

        # 4. 验证
        msg = next(e for e in events if e["type"] == "message")
        assert "AI 安全" in msg["content"]
        tool_names = [tc["name"] for tc in msg.get("tool_calls", [])]
        assert "mcp__hotspot__search_hotspots" in tool_names
        assert "mcp__hotspot__add_favorite" in tool_names

        # 5. 验证 hotspot 真有 3 条新 favorite
        favs = client.get("/api/favorites",
                          headers={"Authorization": f"Bearer {test_token}"}).json()
        assert len(favs["items"]) >= 3
```

**M4 硬指标达成条件**：
- ✅ test_dsh_search_and_favorite_e2e 5 步全过
- ✅ 关闭 dsh 进程后 /api/agent/* 返回 503，AI view 提示离线
- ✅ 重新启 dsh 后端点恢复
- ✅ `grep -r "from llm_service\|from ai_service" backend/` = 0（M5 时验证）

### 16.8 与 §13 关键文件表的差异（接口列补全）

§13.3 关键文件表更新：

| 文件 | 角色 | 关键 API / 协议 |
|---|---|---|
| `vendor/dsh/` (新建) | dsh 源码嵌入 | `cordis.yml` 派生 + `runtime/cordis.yml` 含 mcp-hotspot 插件实例 |
| `backend/services/agent_bridge.py` (新建) | HarnessClient 封装 | `start()` / `initialize(cwd, provider, model)` / `session_prompt()` / `subscribe_notifications()` / `close()` |
| `backend/api/agent_api.py` (新建) | 3 HTTP 端点 | `POST /api/agent/session` / `POST /api/agent/session/{id}/send` / `GET /api/agent/session/{id}/events` (SSE) |
| `frontend/src/components/editorial/AIView.tsx` (新建) | 第 7 view 编辑风对话 | EventSource 订阅 SSE，**不能做流式打字**（acp 限制）；FastAPI 端 chunking 模拟 |
| `backend/services/llm_status.py` (改) | dsh 健康状态端点 | 由 agent_bridge 心跳（list_sessions 轻量 RPC）填充 |
| `backend/mcp_stdio_main.py` (不改) | hotspot MCP server | **dsh 启子进程**调 `python -m backend.mcp_stdio_main`（per dsh mcp-client config） |
| `config/llm.yaml` (不改) | hotspot 自有 LLM 配置 | ai_hub.py 用（M5 合并），与 dsh ctx.llm 并存不冲突 |

### 16.9 §14 R1/R4/R6 反制更新

**R1 dsh 破坏性变更**反制补：
- harness-client 锁版本：`pip install deepseek-harness-sdk==0.1.0`
- 测试覆盖：e2e 用 mock dsh runtime 注入固定 JSON-RPC 响应，验证 FastAPI 代理层解耦
- 升级流程：`vendor/dsh` submodule 升级 → 跑 §16.7 e2e → 通过才允许 commit

**R4 dsh 离线下 AI view 不可用**反制补：
- HTTP 层：/api/agent/* 在 agent_bridge 未就绪时直接返回 503
- UI 层：AIView 启动时 GET /api/llm/agent-status → 若 `available=false` 显示降级 banner
- 数据层：离线时 AIView 仍可读"历史 session"（从 dsh JSONL 持久化解析）

**R6 双记忆撞车**反制补：
- 物理隔离：dsh JSONL session 存 `~/.dsh/sessions/`，hotspot llm-wiki-2.0 存 `<repo>/llm-wiki-2.0/`，**不共享文件系统**
- 逻辑隔离：dsh 任何持久化需求走 mcp__hotspot__* 工具（create_annotation / update_knowledge_item），**禁止直写 SQLite**
- 审计：grep `dsh.*sqlite3.connect` = 0；`sqlite3.connect.*~/.dsh/` = 0

---

## ~~§17 dsh 融合架构图~~（2026-08-21 补 §13 视觉化；2026-08-23 废止）

> ⚠️ **2026-08-23 废止**：3 张 ASCII 图描述的是 hotspot spawn dsh acp 子进程的拓扑，
> 与 dsh-SecNews 方案（dsh web 宿主 + BFF 反代）相反。生效架构图见
> `~/Documents/dsh-SecNews/SECNEWS-二次开发方案.md`。以下原文仅保留作历史参考。

### 17.1 cordis.yml hotspot 派生完整版

**基线**: dsh 默认 cordis.yml (`python/sdk-runtime/src/deepseek_harness_runtime/runtime/cordis.yml`)
+ dsh mcp-client stdio 配置 (`packages/mcp/mcp-client/README.md`)

```yaml
# vendor/dsh/hotspot/cordis.yml
# 启动: DSH_CORDIS_CONFIG=/path/to/this/file.yml

# ═══════════════════════════════════════════════════════════════
# 1. 协议层 — 必须, 不然 dsh 没法跟 FastAPI 通信
# ═══════════════════════════════════════════════════════════════
- id: sdk-jsonrpc-server
  name: '@deepseek-ai/dsh-sdk-jsonrpc-server'    # stdio JSON-RPC 入口

# ═══════════════════════════════════════════════════════════════
# 2. 认知层 — agent 推理 + LLM 适配
# ═══════════════════════════════════════════════════════════════
- id: agent-core
  name: '@deepseek-ai/dsh-agent-spine-demo'
  config:
    workspaceContext:
      maxBytes: 65536

# Direct DeepSeek adapter (默认, 成本最低 + 中文友好)
- id: llm-deepseek
  name: '@deepseek-ai/dsh-llm-deepseek'

# pi-ai 多 provider adapter (与 hotspot llm.yaml 4 provider 对齐)
- id: llm-pi-ai
  name: '@deepseek-ai/dsh-llm-pi-ai'
  config:
    ollama:    !!js { baseUrl: process.env.OLLAMA_HOST ?? 'http://127.0.0.1:11434' }
    openai:    !!js { apiKey: process.env.OPENAI_API_KEY }
    qwen:      !!js { apiKey: process.env.QWEN_API_KEY }
    anthropic: !!js { apiKey: process.env.ANTHROPIC_API_KEY }

# ═══════════════════════════════════════════════════════════════
# 3. 工具层 — hotspot MCP 接入 (dsh 看到 9 tool: mcp__hotspot__*)
# ═══════════════════════════════════════════════════════════════
- id: mcp-hotspot
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: hotspot                         # 决定 tool 命名空间 mcp__hotspot__<raw>
    transport: stdio
    command: python
    args: ['-m', 'backend.mcp_stdio_main']
    cwd: !!js process.env.DSH_CWD ?? '/Users/duke/Documents/hotspot'
    toolCallTimeoutMs: 30000
    failOnStartupError: false                   # MCP 暂时挂不阻止 dsh 启
    reconnect:
      enabled: true
      initialDelayMs: 500
      maxDelayMs: 30000
      maxAttempts: 10

# ═══════════════════════════════════════════════════════════════
# 4. 持久化 — dsh JSONL 短期上下文 (与 hotspot 资产物理隔离)
# ═══════════════════════════════════════════════════════════════
- id: sessions
  name: '@deepseek-ai/dsh-session-persistence-jsonl'
  config:
    root: !!js process.env.DSH_SESSION_ROOT ?? '~/.dsh/sessions'

- id: session-checkpoints
  name: '@deepseek-ai/dsh-session-checkpoint-policy'

# ═══════════════════════════════════════════════════════════════
# 5. 工具执行 — bash + fs (agent 可用)
# ═══════════════════════════════════════════════════════════════
- id: subprocess
  name: '@deepseek-ai/dsh-subprocess-local'

- id: bash
  name: '@deepseek-ai/dsh-bash-local'
  config:
    cwd: !!js process.env.DSH_CWD ?? process.cwd()

- id: fs-local
  name: '@deepseek-ai/dsh-fs-local'
  config:
    cwd: !!js process.env.DSH_CWD ?? process.cwd()
```

**hotspot 改了什么 vs dsh 默认**：

| 区块 | dsh 默认 | hotspot 派生 | 原因 |
|---|---|---|---|
| 协议层 | sdk-jsonrpc-server | **不变** | 必须 |
| 认知层 | llm-deepseek | **+ llm-pi-ai** | hotspot 4 provider 都要用 |
| 工具层 | 无 mcp | **+ mcp-hotspot** | dsh 调回 hotspot 9 tool |
| 持久化 | DSH_SESSION_ROOT | **不变** | 物理隔离 ~/.dsh/ |
| 工具执行 | bash + fs | **不变** | agent 可用 |
| agent-core | workspaceContext | **不变** | 默认 64KB workspace |

### 17.2 dsh 进程状态机（崩溃/重启/降级）

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
                    ▼                                          │
   ┌────────┐  start()   ┌──────────┐  ping OK  ┌──────────┐  │
   │  INIT  │ ─────────▶ │ STARTING │ ────────▶ │ HEALTHY  │  │
   └────────┘  成功     └──────────┘  (5s 间隔) └────┬─────┘  │
       │              start() 失败   │              │        │
       │                  │          │              │ ping 失败│
       │                  ▼          │              ▼        │
       │           ┌──────────────┐  │       ┌────────────┐  │
       │           │DEGRADED_OFFLINE│ │       │ DEGRADED   │  │
       │           └──────────────┘  │       │ (1次失败)  │  │
       │                            │       └─────┬──────┘  │
       │                            │             │ ping 失败│
       │                            │             ▼         │
       │                            │       ┌────────────┐  │
       │                            │       │ RESTARTING │  │
       │                            │       │ (2-3次重启)│  │
       │                            │       └─────┬──────┘  │
       │                            │             │         │
       │                            │       ┌─────┴──────┐  │
       │                            │       │            │  │
       │                            │  成功│            │失败│
       │                            │       ▼            ▼    │
       │                            │  ┌──────────┐  ┌──────────────┐
       │                            │  │ HEALTHY  │  │DEGRADED_OFFLINE│
       │                            │  └──────────┘  └──────┬───────┘
       │                            │                      │
       │                            │                      │ close()
       │                            │                      ▼
       │                            │               ┌──────────────┐
       │                            │               │SHUTTING_DOWN │
       │                            │               └──────┬───────┘
       │                            │                      │ 清理完
       │                            │                      ▼
       │                            │                 ┌─────────┐
       │                            │                 │ STOPPED │
       │                            │                 └─────────┘
       │                            │                      ▲
       │                            └──────────────────────┘
       │                                       FastAPI lifespan
       │                                       shutdown 触发
       │
       └──────────────── DEGRADED_OFFLINE ◀── start() 失败
                                              (env 缺失 / 二进制找不到)
```

**状态转换表**：

| 触发 | 当前状态 | 下一状态 | 动作 |
|---|---|---|---|
| FastAPI lifespan startup | (无) | INIT | spawn dsh 进程 |
| `client.start()` 成功 | INIT | STARTING | 起 reader/stderr thread |
| 首次 ping 返回 | STARTING | HEALTHY | `init.initialize()` |
| `client.start()` 失败 | INIT | DEGRADED_OFFLINE | 写 `/api/llm/agent-status=offline` |
| 5s 内 ping 失败 | HEALTHY | DEGRADED | 记 warn 日志 |
| 5s 内再次 ping 失败 | DEGRADED | RESTARTING | `client.close()` + `start()` 重试 |
| 重启后 ping 成功 | RESTARTING | HEALTHY | 清零 restart counter |
| 累计 3 次失败 | RESTARTING | DEGRADED_OFFLINE | `HOTSPOT_AGENT_BACKEND=off` 等效 |
| FastAPI lifespan shutdown | * | SHUTTING_DOWN | 发 `shutdown` request + `stdin.close()` |
| shutdown 1s 完成 | SHUTTING_DOWN | STOPPED | 进程退出 |
| dsh 二进制丢失 | INIT | DEGRADED_OFFLINE | 永远不重试，提示"agent 未安装" |

**降级行为**：

| 状态 | HTTP 行为 | UI 行为 |
|---|---|---|
| HEALTHY | /api/agent/* 返回 200/202 | AI view 正常 |
| DEGRADED | /api/agent/* 返回 200/202 (单次失败不升级) | UI 静默 |
| RESTARTING | /api/agent/* 返回 503 | UI 提示 "agent 重启中" |
| DEGRADED_OFFLINE | /api/agent/* 返回 503 | AI view 显示 "agent 离线" banner (其余页面照常) |

### 17.3 M4 部署 8 步物理操作时序

```
终端操作                                    验证/产物                        时间
──────────────────────────────────────────────────────────────────────────────────────

[步骤 1] vendor 嵌入 dsh 源码
──────────────────────────────────────────────────────────────────────────────────────
$ cd /Users/duke/Documents/hotspot
$ git submodule add \
    https://github.com/deepseek-ai/deepseek-harness \
    vendor/dsh                              vendor/dsh/.git 文件存在      ~30s
$ git add .gitmodules vendor/dsh            锁 commit hash 写入            ~5s
$ git commit -m "chore: vendor dsh source"

[步骤 2] dsh 进程冒烟 (Node 模式, dev-only)
──────────────────────────────────────────────────────────────────────────────────────
$ cd vendor/dsh
$ pnpm install                             node_modules/ 出现              ~3min
$ pnpm run build                           dist/ 出现                      ~2min
$ pnpm dsh --help                          输出 dsh CLI 帮助              ~10s
                                                              ⬆ 验证: dsh 进程可启
$ cd ../..

[步骤 3] 装 Python SDK + runtime (exe carrier, 生产)
──────────────────────────────────────────────────────────────────────────────────────
$ pip install deepseek-harness-runtime-bin  下载 dsh-jsonrpc-agent-pkg     ~1min
                                            + -spawn-helper (macOS)
$ pip install deepseek-harness-sdk          装 HarnessClient               ~10s
$ python -c "from deepseek_harness.client \
    import HarnessClient; \
    print(HarnessClient().start())"        进程可启 + stdio JSON-RPC 通    ~5s
                                                              ⬆ 验证: SDK OK
$ pip freeze | grep deepseek                锁版本写入 requirements.txt

[步骤 4] 派生 cordis.yml (hotspot 版)
──────────────────────────────────────────────────────────────────────────────────────
$ mkdir -p vendor/dsh/hotspot
$ cp vendor/dsh/python/sdk-runtime/src/\
    deepseek_harness_runtime/runtime/cordis.yml \
    vendor/dsh/hotspot/cordis.yml.bak      备份 dsh 默认版
$ # 按 §17.1 改写: + llm-pi-ai / + mcp-hotspot
$ vim vendor/dsh/hotspot/cordis.yml        编辑为 hotspot 派生版          ~5min
$ DSH_CORDIS_CONFIG=vendor/dsh/hotspot/\
    cordis.yml \
DSH_SESSION_ROOT=~/.dsh/sessions \
DSH_CWD=$PWD \
DEEPSEEK_API_KEY=sk-xxx \
$ pnpm dsh --config $DSH_CORDIS_CONFIG     进程启动 + 加载自定义 config    ~10s
                                              dsh 启动 log 应含
                                              "mcp-hotspot" 加载成功
                                                              ⬆ 验证: dsh 启动 OK
                                              dsh 内部 9 tool 已注册

[步骤 5] agent_bridge.py 封装 HarnessClient
──────────────────────────────────────────────────────────────────────────────────────
$ # 写 backend/services/agent_bridge.py
$ # 类 AgentBridge:
$ #   start()       → HarnessClient().start() + .initialize(provider="deepseek")
$ #   ping()        → request("ping", None)  # 5s 间隔
$ #   create_session() → session/new
$ #   send()        → session/prompt
$ #   subscribe()   → subscribe_notifications
$ #   close()       → close()
$ #   state         → INIT/HEALTHY/DEGRADED/RESTARTING/DEGRADED_OFFLINE
$ # 集成到 main.py lifespan:
$ #   startup  → agent_bridge.start()
$ #   shutdown → agent_bridge.close()
$ pytest backend/tests/test_agent_bridge.py -v
                                              单元测试覆盖 6 状态转换      ~30min
                                                              ⬆ 验证: 状态机正确

[步骤 6] agent_api.py 3 端点
──────────────────────────────────────────────────────────────────────────────────────
$ # 写 backend/api/agent_api.py:
$ #   POST /api/agent/session         → agent_bridge.create_session()
$ #   POST /api/agent/session/{id}/send → agent_bridge.send() (返回 202)
$ #   GET  /api/agent/session/{id}/events → SSE (publish_event 转发)
$ # token 鉴权: HOTSPOT_MASTER_KEY 派生 bearer
$ # 注册到 backend/api/__init__.py: register_routers()
$ pytest backend/tests/test_agent_api.py -v
                                              端点测试 + 鉴权测试 + SSE 测试 ~30min
$ # 手动验证:
$ curl -X POST localhost:8000/api/agent/session \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"provider":"deepseek","model":"deepseek-chat"}'
                                              返回 {"session_id":"sess_..."}  ~5s
                                                              ⬆ 验证: API 通

[步骤 7] 前端 AIView.tsx 第 7 view
──────────────────────────────────────────────────────────────────────────────────────
$ # 写 frontend/src/components/editorial/AIView.tsx (编辑风, ~300 行)
$ # 注册到 App.tsx routes: front/judge/action/read/settings/flow/AI
$ # EventSource("/api/agent/session/{id}/events") + POST /send
$ # 注意: acp 协议 committed only, 不能真流式
$ #         FastAPI 端 chunking 50ms 模拟打字
$ # 提示降级: agent_bridge 状态 = DEGRADED_OFFLINE 时显示 banner
$ cd frontend && npm run dev               启 dev server                  ~10s
$ # 浏览器 localhost:8898 切换到 AI view
$ # 输入 "查 24h AI 安全热点"
                                              AI view 显示 dsh 推理结果    ~30s
                                              + tool_call 历史
                                              (9 tool 中调了 search_hotspots)
                                                              ⬆ 验证: 闭环

[步骤 8] e2e 测试 + 降级验证
──────────────────────────────────────────────────────────────────────────────────────
$ pytest backend/tests/e2e/test_dsh_integration.py -v
                                              跑 §16.7 e2e (5 步)          ~1min
$ # 降级验证 1: 杀 dsh 进程
$ pkill -f dsh-jsonrpc-agent
$ curl -X POST localhost:8000/api/agent/session \
    -H "Authorization: Bearer $TOKEN"       返回 503                      ~3s
$ # 浏览器 AI view 刷新 → 显示 "agent 离线" banner
$ # 其余页面 (front/judge/...) 仍正常
                                                              ⬆ 验证: 降级 OK
$ # 降级验证 2: 重启 dsh
$ pnpm dsh --config $DSH_CORDIS_CONFIG &   dsh 进程恢复
$ # 浏览器 AI view 重连 → 自动恢复
                                                              ⬆ 验证: 恢复 OK
$ # 收尾:
$ git add -A
$ git commit -m "feat(agent): M4 dsh 认知层 (T15-T18 完成)"

总耗时: 约 1-2 人日 (步骤 1-4: 30min, 5-6: 1.5h, 7-8: 1.5h, +调试 buffer)
```

### 17.4 §17 与 §13/§16 关系

- **§13** 给了高层架构 + 关键文件 + 8 步 checklist（**为什么这样做**）
- **§16** 给了协议层 + 工具注入 + LLM 适配 + 错误处理 + 端到端消息流 + e2e demo（**做什么**）
- **§17** 给了 3 张图：cordis.yml 完整版、状态机、部署时序（**长什么样 / 怎么操作**）

三者配合，M4 实施时直接当开发手册。

---

## §18 存储哲学反转：llm-wiki-2.0 主存储（2026-08-22 增补，Duke 拍板）

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

---

## §19 dsh 多智能体编排：通过 dsh 调度外部 CLI agent（2026-08-22 增补）

> **依据**: DeepSeek Harness 开源项目 + 公众号文章《DeepSeek Harness》
> (mp.weixin.qq.com/s/RlgwFWpaLj2sH_pK-EZRAg)。
> dsh 定位 = **通用 agent harness**：统一协议 (ACP JSON-RPC stdio) 封装任意
> coding agent。hotspot 不逐个适配 claude code / codex，而是全部经 dsh。

### 19.1 架构：dsh 作为 agent 网关

```
┌────────────────────────────────────────────────────────┐
│ hotspot FastAPI                                        │
│  /api/agent/*  →  agent_bridge.py  →  dsh 主进程       │
└──────────────────────────┬─────────────────────────────┘
                           │ ACP JSON-RPC (stdio)
┌──────────────────────────▼─────────────────────────────┐
│ dsh (deepseek-harness)                                 │
│  ├ session 管理 / LLM 适配 / MCP-client(hotspot 9工具) │
│  └ sub-agent spawn: 按 task 类型路由到不同 runner       │
│     ├ builtin deepseek runner   (默认, 对话/提炼/评分)  │
│     ├ claude-code adapter       (复杂重构/长任务)       │
│     └ codex adapter             (快速代码生成/补丁)     │
└──────────────────────────┬─────────────────────────────┘
                           │ 各 CLI 自己的原生协议
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         claude 进程   codex 进程    gemini cli...
        (ACP/stdio)   (exec/stdout)   (可选扩展)
```

### 19.2 路由策略（task → agent 映射）

| 任务类型 | 默认 agent | 理由 |
|---|---|---|
| 对话/简报解读/知识提炼/灰区分类 | dsh builtin (DeepSeek) | 成本最低、中文友好、走 hotspot MCP 工具面 |
| 代码重构/跨文件修改（CodeGarden 任务书执行） | claude code | agentic 能力最强，长上下文 |
| 快速补丁/单文件生成/测试脚手架 | codex | 启动快、token 便宜 |
| 用户显式指定 | 用户选择 | AIView 下拉框覆盖默认路由 |

### 19.3 实施要点（并入 M4，T15 扩展为 T15a/T15b）

> ⚠️ **2026-08-23 路线变更**：T15a 标题保留，但执行主体从「hotspot spawn dsh acp」改为
> 「dsh-SecNews 方案 cap engine + runner 注册表」。T15b 已由 `config/agents.yaml`
> + `backend/config/agent_runner_schema.py` 落地（commit a4283c36）。

**T15a — dsh 宿主进程接入**（执行方 = `~/Documents/dsh-SecNews/`，见该方案 §2/§3）

**T15b — 外部 CLI runner 注册**（已落地，见 `backend/config/agent_runner_schema.py` + `config/agents.yaml`）：
1. dsh 配置（cordis.yml `agents` 段）注册两个自定义 runner：
   ```yaml
   agents:
     claude-code:
       command: ["claude", "--print", "--output-format", "stream-json"]
       protocol: stream-json    # 逐行 JSON 解析
       cwd: "{workspace}"       # CodeGarden 项目目录注入
     codex:
       command: ["codex", "exec", "--json"]
       protocol: jsonl
   ```
2. `agent_runner_schema.route(task_type)` — 按 19.2 表选 runner；
   dsh 端消息携带 `preferred_agent` 字段（AIView 由 dsh-SecNews 侧实现，hotspot 不重复）
3. 工作目录安全边界：claude/codex 只允许在 `codegarden/<project>/` 内执行
   （runner `cwd` 锁定 + sandbox flag），禁止触碰 hotspot 根目录与 knowledge/
4. 结果回写：CLI stdout 结构化输出 → dsh session → 持久产物仍经 ai_hub → llm-wiki-2.0
   （复用 §13.4 记忆单源裁决，外部 agent 不产生第二记忆源）

### 19.4 降级与成本控制

| 场景 | 行为 |
|---|---|
| claude/codex CLI 未安装 | 路由回退 builtin DeepSeek，AIView 提示 |
| CLI 超时 (>10min) | kill 进程，session 标记 failed，产物不落库 |
| 成本配额 | 沿用 R5：每任务级预算，月度对账；claude/codex 调用在 cg_events 留痕 |

### 19.5 验收（并入 M4 exit gate）

- [ ] AIView 选择 claude code 发起 CodeGarden 重构任务 → 任务书下发 → diff 回显 → 产物落 wiki
- [ ] 未安装 claude CLI 时同任务自动回退 DeepSeek 且 UI 有提示
- [ ] `wiki_events` 中可见每次外部 agent 调用的 kind=`cli_agent_run` 记录
- [ ] 外部 agent 无法访问 codegarden/<project>/ 以外路径（负向测试）

---

## 附录 A：关键文件变更映射（§13 关键文件表）

| 文件 | 变更类型 | 里程碑 | 说明 |
|---|---|---|---|
| `backend/services/ai_hub.py` | 改（M5 合并） | M5 | llm_service + ai_service 合并为单契约 |
| `backend/services/llm_status.py` | 改 | M4 | dsh 健康状态端点 |
| `backend/api/agent_api.py` | 新建（废止） | M4 | ~~不再创建~~ |
| `backend/services/agent_bridge.py` | 新建（废止） | M4 | ~~不再创建~~ |
| `frontend/src/components/editorial/AIView.tsx` | 新建（废止） | M4 | ~~不再创建~~ |
| `backend/config/agent_runner_schema.py` | 新建（已落地） | M4 | runner 注册表元数据 |
| `config/agents.yaml` | 改（已落地） | M4 | 注册 claude-code / codex runner |
| `backend/mcp_stdio_main.py` | 不改 | M4 | dsh mcp-client 连这个 |
| `vendor/dsh/` | 新建（废止） | M4 | ~~不再 vendor 嵌入~~ |

## 附录 B：废弃决策索引

| 决策 | 废止原因 | 废止日期 | 替代方案 |
|---|---|---|---|
| D1 dsh 部署形态：vendor submodule + Python SDK | dsh-SecNews 平行工程更成熟 | 2026-08-23 | dsh-SecNews 方案 P3+ |
| T15a/T16/T17 原设计 | 宿主关系相反 | 2026-08-23 | dsh web :3210 宿主 + BFF 反代 |
| 四分温度库（HOT/WARM/COLD/FROZEN） | 仍以 SQLite 为真源，治标不治本 | 2026-08-22 | wiki-first 存储哲学 |
| 自研 ai_hub.py 从零写 | 已有雏形，应是收敛而非重写 | 2026-08-21 | 单契约收敛 + dsh 认知层 |

## 附录 C：术语表

| 术语 | 定义 |
|---|---|
| hotspot | 本项目代号（安全新闻知识仪表盘） |
| dsh | DeepSeek Harness，开源 agent harness（TypeScript 主体） |
| llm-wiki-2.0 | 文件系统知识库（md 真源），替代 SQLite 全量存储 |
| ACP | Agent Client Protocol，dsh 使用的 JSON-RPC stdio 协议 |
| MCP | Model Context Protocol，hotspot 向 dsh 暴露工具的协议 |
| SSE | Server-Sent Events，FastAPI 向前端推送实时事件 |
| wiki_index | SQLite FTS5 索引，只读，可随时从 llm-wiki-2.0 重建 |
| retention.json | 表生命周期台账，标注每张表的 source 和保留策略 |
| agent_bridge | ~~HarnessClient 封装层（已废止）~~ |
| BFF | Backend For Frontend，dsh-SecNews 方案中 secnews-api 反代 hotspot |
