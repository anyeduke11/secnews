# 已废止

> 本文档已被单一权威 PRD 取代: [`docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md) (DEV-0179 收敛纪律)。以下内容仅作历史分析参考。

# hotspot 第一性原理分析与优化方案

- 日期：2026-09-11
- 状态：**分析方案（待裁决）** — 本文不替代 `docs/v0.8.5/V0.8.5_PLAN.md`（唯一实现 spec）；本文的定位是**在 spec 之上回答"方向对不对、哪些是大结构问题"**
- 方法：全部结论来自对**代码与生产库的实测**（命令与结果见附录 A），文档声明与实测冲突处以实测为准
- 边界：本文**不改**三层壳、导航、视觉语言（owner 已在 v0.8.5 §0.4 裁定"顺手"优先）；所有建议都在壳**背后**发生

---

## 0. 摘要（一屏）

> ⚠️ **先读 §0.1**：本系统当前存在一条**在局域网内可被远程利用的未鉴权任意命令执行（RCE）链路**，已实测复现。它优先于本文其余全部内容。

**一句话诊断**：系统把 90% 的工程量投在了"资讯怎么进来"，而它自称的价值是"判断怎么沉淀"；这两件事今天**在数据上根本没有接上**。

三个最硬的实测数字：

| 事实 | 数字 | 含义 |
|---|---|---|
| 采集入库 vs 人工交互 | **9,872 条 : 14 次**（收藏 6 / 待办 6 / 标注 2 / 注意力事件 0） | 交互率 0.14%，看板没有承担看板职责 |
| 机器日志 vs 人的结论 | **5,584,559 行质量日志 : 1 条 v1_knowledge**（且状态 = `retracted`） | 存储被"我们怎么过滤的"占满，"我们得出了什么"几乎为零 |
| AI 是否在环内 | `ai_scores` **0 行**；判读层主数据源是 `/api/hotspots` | AI 的贡献在采集侧，不在判断侧 |
| **语料是不是安全的** | **security 仅 802 / 9,872 = 8%**（ai 5,563 + tech 2,869）；`crawler_sources` **64 / 101 是招投标源**，安全源仅 16 个（active 3 / dead 5 / disabled 8） | **这个看板的主体不是安全** |
| **"行动层"能不能产出** | `v1_runs` **0** / `v1_artifacts` **0**；`run_service.py:155` 写死"永远 queued"，无执行体 | 不是"没数据"，是**代码级死锁** |
| **备份存不存在** | `backend/backups/` **无任何 `.db` 全量快照**；增量 `.bin` **三个全是 0 字节** | 每天跑、每天报成功、每天产出空 |

**根因（一个）**：**双本体论**。同一批资讯在库里同时存在三套身份（`hotspots` / `llm-wiki-2.0` md + `warm.knowledge_items` / `v1_materials`），互不相认。三层壳是**视觉分层**，底下是**两个不通的数据世界**。人在界面上做的每一次判断（收藏、标注、LLM 评估）都写进旁路表或**不落库**，从不进入证据引擎。

**第二个根因（能力方向反了）**：20 个内置 skill 里 **14 个（70%）是系统自我体检**（信源巡检 / 采集器健康 / API 路由健康 / 迁移一致性…），只有 2 个构成真正的安全分析动作。因果链是：系统没有资产、SLA、incident、暴露面这些对象 → agent 无对象可编排 → 只能去看自己的管道。**补技能不会解决它，补对象才会。**

**第三个问题（不可恢复的那一类）**：数据层**没有 schema 真相源**（唯一真相是启动期逐条跑 106 个 SQL）、**写路由是隐式的**（显式 `warm.` 写入全仓 0 处，靠未限定表名解析）、而 **WAL 模式下跨库事务不原子**；再叠加 §0.1 P0-C（warm 库 899 MB 零策略备份、主库 12 天无备份）——**三者叠在一起意味着：一旦损坏，既没有 schema 可重建，也没有备份可恢复**（D12）。

**方案（一句话）**：不改壳，把底下收敛成**单一决策账本（Single Decision Ledger）**——一条资讯只有一条身份、一条状态机；**人的每一次判断都是一等写入**。

**最大的单点收益（1–2 天可落地）**：让 `/api/llm/evaluate` 的结论落库。它今天把结果返回给前端就丢了（`ai_scores` = 0 行），而这正是"AI 看板"里 AI 唯一应当负责的环节。

---

## 0.1 立刻处理：七个 P0（已实测复现，优先级高于本文其余全部内容）

> 本节由三个独立审计发现，**主会话逐条独立复现确认**。它与"架构优化"无关，属于**当下就在漏的口子**。
> 前两条各自独立足以构成"当天必须处理"：**一条是此刻可被局域网远程利用的任意命令执行；一条是备份链每天报成功、每天产出 0 字节**。

| # | P0 | 一句话 | 性质 |
|---|---|---|---|
| **A** | 未鉴权任意命令执行（RCE） | `PUT /api/dsh/control/config` 自由命令 → `Popen`，全站零鉴权 | **此刻可被局域网远程利用** |
| **B** | 前端 dev server 绑 `0.0.0.0` | `:8898` 的 `/api` 反代绕过后端回环门，把 A 放大到整个局域网 | **此刻在漏** |
| **C** | **备份链产出为空且报成功** | 每日 job 正常跑、按 design 打成功日志，**产物是 0 字节**；且无任何全量快照 | **静默地丢全部数据** |
| **D** | 行动层代码级死锁 | `v1_runs` 永远 `queued`，无执行体；Artifact 造不出；**Case 在数学上无法关闭** | 整个"行动层"不可能产出 |
| **E** | 证据收据永久 pending | judgment/action/knowledge 用 `entity_type="judgment"` 调 `create_intent`，而该函数只认 4 种类型 → 必抛 → 被吞 | "可辩护"律结构性失效 |
| **F** | kl items 路径穿越（读+写） | 裸 `item_id` 拼路径，`%2e%2e%2f` 绕过归一化 → 任意 `.md` 读写 | 本机文件完整性 |
| **G** | 明文密钥 ×3 份库 + 假加密 | `settings.quality.llm_api_key` 明文；codegarden 加解密**参数写反** → 明文落库且绕过"未解锁显示 `******`"红线 | 凭据泄露 |

### P0-A 未鉴权任意命令执行（RCE），链路完整可用

| 环节 | 位置 | 事实 |
|---|---|---|
| 入口 | `backend/api/dsh_control_api.py:30,64` | `PUT /api/dsh/control/config` 接受**自由格式** `command: str`，仅 `max_length=2000`，**无白名单** |
| 持久化 | `backend/services/dsh/supervisor.py:72-73` | `set_dsh_config()` 原样写进 `settings` KV（`dsh.command`） |
| 解析 | `backend/services/dsh/supervisor.py:35-43` | `_parse_command()` **只做 `shlex.split`**，无任何命令校验 |
| 沉淀 | `backend/services/process_supervisor.py:101-102` | `subprocess.Popen(command, ...)` |
| 触发 | `backend/api/dsh_control_api.py:40` | `POST /api/dsh/control/start` |
| 鉴权 | 全仓 | `grep -rnE "HTTPBearer\|APIKeyHeader\|get_current_user" backend/` → **0 命中**，无任何认证 |

`Popen` 未用 `shell=True`（所以不是 shell 注入），但只需 `argv = ["/bin/sh","-c","<任意命令>"]`，等价于**任意命令执行**。审计与我的复核均确认：**代码中不存在危险命令黑名单**（`grep danger|blacklist|黑名单|allowlist` 于 `process_supervisor.py` / `dsh/*.py` → 0 命中）——尽管项目红线第 8 条声称"playbook/用户命令走危险命令黑名单"。

### P0-B 前端 dev server 监听 `0.0.0.0`，把 P0-A 从"仅本机"放大成"整个局域网"

```
frontend/vite.config.ts:14      host: '0.0.0.0'
frontend/vite.config.ts:18-23   proxy: { '/api': { target: 'http://127.0.0.1:8000' } }
frontend/package.json:7         "dev": "vite --port 8898 --strictPort --host 0.0.0.0"
```

后端自己是有防护的（`run.py:39-45`：非回环绑定被强制改回 `127.0.0.1`，除非显式 `HOTSPOT_ALLOW_LAN=1`）。
**但这个防护被前端代理完全绕过**——经 8898 进来的请求，源地址是 `127.0.0.1`，后端认定为本机。

**实测（此刻）**：

```
lsof -nP -iTCP:8898 -sTCP:LISTEN
  node 15572 duke  IPv4 ... TCP *:8898 (LISTEN)      ← 绑定 0.0.0.0
curl http://127.0.0.1:8898/api/health              → HTTP 200（拿到完整后端 JSON）
curl http://127.0.0.1:8898/api/dsh/control/status  → HTTP 200
```

即：`http://<本机局域网 IP>:8898/api/dsh/control/config` + `/start` 就是完整的远端 RCE。
**生产后端本身绑在 `127.0.0.1:8000`（已核，正确）——漏的是前端这一侧。**

> 次级问题：`backend/main.py:305-312` 的 `__main__` 分支**没有** `run.py` 的那个回环 guard，直接 `python -m backend.main` 会沿用 `config.host` 原值绑定。需与 `run.py` 统一。

### P0-C **备份链产出为空且报成功**（原判"12 天未产出"是低估）

| 事实 | 证据 |
|---|---|
| 备份只覆盖主库 | `backend/services/backup_service.py:169` `src = Path(config.db_path)`；`grep -n "warm\|cold" backup_service.py` → **0 命中** |
| 保留策略 | `backup_service.py:40` `BACKUP_RETENTION = 1`；`:189-197` 仅按 glob `hotspot-*.db` 清理 |
| 最新正式备份 | `backups/hotspot-20260829_200000_stray.db`，**16 MB / mtime 2026-08-30 04:00**（当前主库 34 MB，即该备份只有 47%） |
| 距今 | 2026-09-11 − 2026-08-30 ≈ **12 天无新备份** |
| warm 唯一副本 | `backups/hotspot-warm.db.bak-esc-20260829_235118`（463 MB，**一次性手工快照**，不在保留策略 glob 管辖内，不会被轮转更新） |
| 当前 warm 体积 | **899 MB**（我在 §3.2 实测 857 MB，仍在增长），**零策略性备份** |

**后果**：主库 12 天的数据（含 v1 全部账本、9,872 条 hotspots、16,489 wiki_events）没有可用恢复点；一旦 warm 库损坏（899 MB 单文件），**不可恢复**。

> ⚠️ **2026-09-11 深度复核更正**：上面的"12 天无新备份"是**低估**。真实情况更严重——
> - `backend/backups/` 里**没有任何 `.db` 全量快照**（只有 `hotspot-20260829_200000.db-shm` 32 KB、一个 0 字节的 `-wal`、和一个 8/30 的 knowledge.zip）。
> - `backend/backups/incremental/` 有 **三个 0 字节的 `.bin`**（9/7、9/8、9/10），`chain.meta` 每天 04:30 被更新——**job 每天正常跑、每天记一条"空 payload 的 sha256"，每天产出 0 字节**。
> - 根因是**可复现的代码 bug**：`backend/services/backup_service.py:243` 硬编码 WAL magic `b"\x37\x7f\x06\x15"`，而本机实测 WAL 头是 `37 7f 06 82`（第 4 字节是 checksum 字节序标志）→ **判断恒假，函数立即 `return` 空列表**。同函数 `:248` 还把 offset 12 的 **4 字节大端** checkpoint_seq 按 8 字节小端读。
> - 恢复侧同样是假的：`backup_service.py:380-387` 的 `restore_from_incremental_chain()` 只做 `applied_pages += len(pages)`，**函数体内零个写操作**，却返回 `{"ok": True, "applied_pages": N}`。
> - 校验侧也是假的：`scripts/check_backup_chain.py:114-121` 对增量内容是空校验（自述"简化"），**永远 PASS**。
>
> 即：**备份 → 恢复 → 校验三层全是空壳，且全部报成功。** 这不再是一个"保留策略"问题，而是"灾难发生当天才会发现的、不可逆的数据全损"问题。它与 P0-A 并列为本方案的两位最高优先级。

### P0-D 行动层是**代码级死锁**，不是"还没数据"

这一条推翻了我在 §4-D6 的初判。原来我写的是"AI 不在环内、v1 引擎没有燃料"；真相比"没数据"严重：**这条链在数学上不可能产出任何东西。**

```
ActionService.start()  → RunService.create_or_replay()
    run_service.py:155   "status": "queued",  # v1.0 C07 R05 修复: 永远 queued (mock 协议已从生产移除)
    ↑ 全仓唯一写 v1_runs 的地方，写死的终态是"永不终态"

全仓无 v1_runs 执行体：
    repository/run_repo.py:89  update_status()  ── 零调用方（主会话已复核 grep）
    api/run_api.py             只有 GET "" 与 GET /{run_id}
    jobs/worker_pump.py:44     注释自述"与 run_service 的 create_or_replay 解耦 — worker_pump 不写 v1_runs"

于是：
    artifact_service.py:93   raise ArtifactValidationError("run_id required")
        → run 无终态 ⇒ Artifact 永远造不出
    case_service.py:426      close_case 守卫 (b)「任何 active v1_runs 不得存在」
    case_service.py:427      close_case 守卫 (c)「至少 1 个 verified/accepted artifact(经 v1_runs 关联)」
        → (b) 与 (c) 互斥 ⇒ Case 永远关不掉
```

实测吻合：生产 `v1_runs` **0 行**、`v1_artifacts` **0 行**。dev 库有 10 条 run（**全部 `queued`、`finished_at=NULL`**）和 6 条 `accepted` artifact——那些 artifact 是 `scripts/t12/t13_*.py` 绕过执行链直写/直调造出来的。

**这意味着**：v0.8.5 的"审批 → 运行 → 验收"交互在 UI 上可以点，但**点完什么也不会发生，且 Case 从此永久卡死**。§5.4 那张"人的动作写到哪里"的表，下半截（Action / Run / Artifact）**必须连同执行器一起重建**，不是"接线"问题。

### P0-E 证据收据永久 pending——"可辩护"律在代码里失效

```
judgment_service.py:322-325   create_intent(entity_type="judgment", ...)
action_service.py:239-245     create_intent(entity_type="action",   ...)
knowledge_service.py:288-294  create_intent(entity_type="knowledge",...)

而 v1_evidence_service.py:198-225 只认 subject / material / signal / case 四种
    → commit_intent 必抛 ValueError("unsupported entity_type")
    → judgment_service.py:326-328 的 try/except 把它吞成一条 warning
```

**后果**：judgment / action / knowledge 的 evidence receipt **永远是 `pending`，永不 `committed`**（dev 库实测 5 judgment + 5 action + 1 knowledge 全 pending，0 committed）。而 `reap_expired_intents()`（`v1_evidence_service.py:426`）**零调用者**，连回收都不会发生。

这是 L3（可辩护律）在代码层的直接违反：系统承诺给每个结论一条证据链，而这条链对**除 signal 之外的每一种对象**都断在第一步。

### P0-F kl items 路径穿越（读 + 写）

```
api/kl_pipeline_api.py:218   GET /api/kl/items/{item_id} → wiki_fs.read_item(item_id)
api/kl_pipeline_api.py:228   PUT /api/kl/items/{item_id} → wiki_fs.write_item(item_id, doc)
wiki_fs/store.py:49,82       path = self._items_dir / f"{item_id}.md"    ← 无过滤 / 无白名单 / 无 realpath 校验
```

浏览器会归一化字面 `..`，但 **URL 编码可绕过**（`%2e%2e%2f` 解码后是 `../`）。即可读任意 `.md`，并覆写任意**已存在**的 `.md`（存在性检查是唯一收敛条件）。

同仓 `wiki_tools.py:114-124` 的同类端点有 `_PATH_RE` 白名单 + `realpath` 前缀校验——**对照表明 kl 侧是漏做，不是设计取舍**。

### P0-G 明文密钥 ×3 份库 + codegarden"假加密"

- `settings.quality.llm_api_key` 在 `backend/hotspot.db` 中**明文**（前 3 字符 `sk`、长度 37），与 `.env` 的生产 key 同值；同样明文存在于两份 `_drill/` 备份库里。
- `codegarden_resource_service.py:222` `encrypt_api_key(str(v), ek_row.id)` —— **参数写反**：把明文当 Fernet 密钥、把密钥行 id 当明文。`Fernet(<任意明文>)` 必抛 → 被 `except` 吞 → **明文落库**。`:258` 的 `decrypt_api_key` 同样写反 → 解密永远失败。
- **二次伤害**：`:249` 未解锁分支对非 dict 值直接返回原值 → 因值实为明文字符串，`GET /api/codegarden/resources/env-templates/{id}`（**不要求 master_key**）会把明文密钥原样吐出，直接击穿规格「未解锁显示 `******`」的红线。（`cg_resources` 当前 0 行，属**潜伏**缺陷。）

### 处置建议（按"当天 / 本周"两档）

**当天（每一项都是小改动，收益极大）**

1. **`frontend/vite.config.ts:14` → `host: '127.0.0.1'`**，同步 `package.json:7,8` 的 `--host 0.0.0.0`；重启 dev server。（**一行**，立即消除局域网面）
2. **`backup_service.py:243` 的 WAL magic 改为不校验具体字节**（或接受 `header[:3] == b"\x37\x7f\x06"` + 校验 `header[4:8]` 版本），并修 `:248` 的 checkpoint_seq 读取（4 字节大端）。**然后立刻手工跑一次全量备份并验证文件非空**——因为现在**一份可用备份都没有**。
3. **`command` 不再从 HTTP 自由写入**：`set_dsh_config` 加 argv 白名单，或把该字段从 API 面移除。
4. **`kl_pipeline_api.py` 的 `item_id` 走 `wiki_tools.py` 同款白名单 + realpath 校验。**
5. **`main.py:305-312` 的 `__main__` 分支与 `run.py:39-45` 共用同一个回环 guard。**

**本周**

6. **备份覆盖三库 + 保留 ≥3 + 恢复侧真写页**：把 `scripts/t02_backup_drill.py:75-113`（已验证三库 `Connection.backup()` + manifest + sha256）接进 `daily_db_backup_job`；修 `restore_from_incremental_chain` 的假成功；修 `check_backup_chain.py` 的空校验；`BACKUP_RETENTION` 1 → ≥3。
7. **修 `create_intent` 的 entity_type 白名单**（加 judgment/action/knowledge），并给 `reap_expired_intents` 挂上调度。这一步**零风险、几十行**，直接让"证据链"从假变真。
8. **`BACKUP_RETENTION` 之外，加一个"备份产物非空"的断言**（0 字节即告警）——这类"静默成功"必须由机器发现，不能靠人查。
9. **`crypto` 参数顺序**：`encrypt_api_key(fernet_key, api_key)` 的两个调用点改回正确顺序；补一个清扫迁移删除 `settings.quality.llm_api_key` 明文；加一条测试锁死"未解锁必须返回 `******`"。
10. **加最小鉴权**：即使回到仅本机，也建议加一个本地 token（红线第 8 条已有错误契约可复用）。

> **P0-D 不在此列**——它不是"修"，是"补上半场"（写一个真正的 Run 执行器）。我把它放在路线图的 P1-0，因为它的形状取决于 owner 想让"执行"到底是什么（派 dsh？派 pi？还是只做人工回执？）。这是一个产品决策，不是 bug 修复。

> 以上十条与本文其余部分是**正交**的：架构可以慢慢谈，这些不能。建议作为独立的 **P0-0 止血批**，先于路线图全部批次。

---

## 1. 方法：第一性原理在这里怎么用

第一性原理不是"从零重写"，是**先确定这个系统不可能被违反的守恒量，再用它去裁判现状**。步骤：

1. 从"安全从业者一天在干什么"反推**不可约的产出物**；
2. 从产出物推出**守恒律**（violate 就一定会亏）；
3. 把守恒律翻译成**可判定的架构判据**；
4. 拿判据逐条扫现状，每一条给出**实测证据**；
5. 只对**违反判据**的部分出方案——不违反的不动（避免重蹈 v1.0 四入口覆辙）。

---

## 2. 推导：四条守恒律与五条架构判据

### 2.1 不可约产出物

安全从业者的产出**不是**"读了多少资讯"，而是：

> **在某个时刻，对某件事做出一个可以对外解释、能被追责、能被复用的判断。**

判断的成本 = 收集证据 + 交叉验证 + 形成结论 + 写下来。
判断的价值 = 它避免的损失 × 它被复用的次数。

于是系统的不可约目标：

> **把"一个安全判断"的边际成本压到最低，并让这个判断以可检索、可复用、可追责的形式留存。**

### 2.2 四条守恒律

| 律 | 陈述 | 违反的代价 |
|---|---|---|
| **L1 单位律** | 系统的原子单位必须是**判断**，不是**条目** | 界面被条目占据 → 人自己做筛选 → L2 破产 |
| **L2 注意力守恒律** | 人的注意力是唯一不可扩展的资源；系统每多产出一条需要人看的东西，成本 +1，除非自动降到 ~0 | 看板退化为"需要人自己维护的管道" |
| **L3 可辩护律** | 判断只有在能回答"凭什么 / 来源 / 何时 / 置信度 / 反证 / 怎么撤回"时才成立 | 结论不可对外 → 无法交付 → 无价值 |
| **L4 复利律** | 资讯价值随时间**衰减**，判断价值随时间**递增**（方向相反） | 存储与索引投在负债上；复利不发生 |

### 2.3 五条架构判据

| 判据 | 内容 | 违反的典型症状 |
|---|---|---|
| **C1 单位正确** | 判断对象是一等公民，且是界面的**默认主线** | 首页/判读页的主体是信息流 |
| **C2 注意力守恒** | 人工交互次数 ≈ 判断次数；不允许人工参与管道维护 | 人要点"刷新"、要滚过 200 条找 3 条 |
| **C3 证据完备** | 每个结论可追溯证据 + 有置信度 + 有反证字段 + 可撤回 | 结论只是文本，没有 refs |
| **C4 时间方向正确** | 资讯可丢/可降采样；判断必须备份、必须可检索 | 日志库比知识库大 3 个数量级 |
| **C5 单一真相** | 一个概念只有一个表示 | 同一篇文章三种 id |

---

## 3. 事实基线（实测，2026-09-11）

### 3.1 代码规模

| 项 | 数字 | 来源 |
|---|---|---|
| 后端 | 822 个 `.py` / **186,115 行** | `find backend -name '*.py'` |
| 前端 | 305 个 `.ts(x)` / **56,602 行** | `find frontend/src` |
| routers / services / jobs / collectors | **85 / 126 / 58 / 14** | `generate_meta.py --check`（CI 门，OK） |
| repository 文件 / SQL 迁移 | 52 / **110** | `ls backend/repository/migrations` |
| 主库表数 | **129** | `sqlite3 hotspot.db .tables` |
| 测试文件 | 324（pytest 4382 passed，PROGRESS 2026-09-10） | — |

### 3.2 数据规模与分布

| 库 | 大小 | 设计目标 | 主要占用 |
|---|---|---|---|
| HOT `hotspot.db` | 34 MB | <80 MB ✅ | hotspots 9,872 / wiki_events 16,489 / security_entities 889 |
| WARM `hotspot-warm.db` | **857 MB** | <80 MB ❌ **超 10 倍** | `quality_check_logs` **4,745,555** + archive 836,004 |
| COLD `hotspot-cold.db` | 28 KB | <500 MB | 仅 `audit_log` / `retention_state` — **分层名存实亡** |

WARM 其余大头：`crawler_runs` 227,688 / `quality_rejection_log` 224,942 / `raw_items` 84,423 / `collection_runs` 49,245 / `coverage_runs` 45,922 / `catchup_checkpoints` 27,635 / `knowledge_links` 24,472 / `planning_actions` 9,424。

### 3.3 人机交互数据（最关键的一组）

| 表 | 行数 |
|---|---|
| `hotspots`（采集入库） | **9,872** |
| `favorites` | **6** |
| `todos` | **6** |
| `annotations` | **2** |
| `attention_events` | **0** |

**人工主动交互合计 14 次 / 9,872 条 = 0.14%。**

对照机器自产：`knowledge_links` 24,472 / `planning_actions` 9,424 / `crawler_runs` 227,688。

### 3.4 v1 证据引擎（"九对象 + 三类 receipt"）实际占用

| 表 | 行数 |
|---|---|
| `v1_materials` | 4 |
| `v1_signals` | 3 |
| `v1_cases` | 4 |
| `v1_judgments` | 1 |
| `v1_actions` | 1 |
| `v1_runs` | **0** |
| `v1_artifacts` | **0** |
| `v1_knowledge` | **1（`status = retracted`）** |
| `v1_knowledge_adoptions` | 1 |
| `admission_log` | 3 |

"点火"源：`backend/services/v1_ingest_bridge.py` → `_DEFAULT_SOURCES = "security:SecWiki"` —— **单一 RSS 源**。

### 3.5 AI 是否在环内

- `ai_scores`（LLM 文章评分表）**0 行**。
- `POST /api/llm/evaluate`（判读层核心动作）**无落库路径**：`backend/api/llm_status.py:86-136` 调 `ai_hub.tasks.evaluate_article` 后直接 `return result`。
- `ai_scores` 的写入点只有两处：`services/triggers/t1_raw_to_refine.py:289` 与 MCP tool `score_item`。
- kl_pipeline 的发布门在 `ai_scores` 为空时用常量兜底：`t4_structure_to_publish.py:65 DEFAULT_SCORE = 5.0`，注释明说"LLM 未配置 → ai_scores 恒空 → kl:publish 死锁"。
- LLM 凭据存在 1 条；`agent_runs` 321；`deep_reads` 14。

### 3.6 健壮性与运维

| 项 | 实测 |
|---|---|
| 宽泛 `except Exception`（后端非测试） | **954** 处；services 层 **402** 处（2026-09-05 审计为 320，**6 天 +82**） |
| 端口暴露 | 后端 `127.0.0.1:8000` ✅；前端 dev server `host: '0.0.0.0'` :8898 且 `/api` 反代到后端 ⚠️ |
| 仓库磁盘 | **5.3 GB**（backups 887 MB / dev_data 215 MB / runtime 175 MB / node_modules）；**入仓仅 1,686 文件** |
| 备份 | `backups/` 9 份，最老 `2026-08-22`（20 天），无保留策略生效迹象 |
| 运行时 | 生产后端 pid 15548 在跑；vite 在跑 |

### 3.7 前端界面复杂度

`frontend/src/components/sentinel/` 六个页面单文件体积：`SentinelActionPage.tsx` 35 KB / `SentinelGraphPage.tsx` 33 KB / `SentinelHomePage.tsx` 32 KB / `SentinelSettingsPage.tsx` 31 KB / `SentinelGardenPage.tsx` 29 KB / `SentinelJudgePage.tsx` 26 KB。数据层为裸 `fetch` + `setInterval`，无统一缓存/失效层。

---

## 4. 诊断：十九项对判据的偏差

### D1【P0 · 违反 C5 单一真相】双本体论：同一概念两套表示，且互不连通

| 概念 | v0 表示 | v1 表示 |
|---|---|---|
| 原始材料 | `hotspots` (9,872) | `v1_materials` (4) |
| 知识条目 | `warm.knowledge_items` (3,800) + `llm-wiki-2.0/*.md` | `v1_knowledge` (1) |
| 判断 | `ai_scores`(0) / `annotations`(2) / `deep_reads`(14) | `v1_judgments` (1) |
| 行动 | `planning_actions`(9,424) / `todos`(6) | `v1_actions` (1) |
| 执行 | — | `v1_runs` (0) |
| 产物 | — | `v1_artifacts` (0) |
| 关注对象 | `security_entities` (889) | `v1_subjects` |
| 生命周期 | kl_pipeline 五阶段 | `v1_knowledge` 4 态机 |

**三条并行的采集路径**，产出三种身份：

1. 经典 collector 链 → `hotspots`（`scheduler/jobs/collect.py`）
2. kl_pipeline → `llm-wiki-2.0/*.md` → `wiki_events`
3. `SourcePipeline` → `v1_materials`/`v1_signals`（`v1_ingest_bridge.py:81` 明确注释"信号/Material 只入库, 不落 wiki"）

项目**自己知道**这件事：`migrations/107_v10_legacy_mapping.sql` 专门建了 `v1_legacy_mapping` 做旧→新 ID 映射，`legacy_source` 枚举就是 `dev_seed | warm.knowledge_items | wiki_items`。**建了映射表，而没有归一。**

**后果**：界面不可能自洽。壳是三个工作阶段，数据是两个不通的世界。

### D2【P0 · 违反 C1】人的判断从不进入证据引擎

- `POST /api/favorites`（人的主要互动，6 次）**没有任何 v1 写入**（grep 确认：`favorites.py` 不引用 `v1_*`）。
- 判读层主内容不是 judgment，而是 `/api/hotspots?...limit=15`（`SentinelJudgePage.tsx:202`）。
- 判读动作 `POST /api/llm/evaluate` 结果**不落库**。

**后果**：**用户在界面上做的一切判断都蒸发了。** 飞轮从未被人喂过，只被机器喂过——而机器喂进去的是 24,472 条 knowledge_links 这类自动产物。

### D3【P0 · 违反 C1】三层是视觉分层，不是数据分层

| 层 | 路由 | 主数据源 |
|---|---|---|
| 资料层 | `/` | `/api/hotspots` |
| 判断层 | `/judge` | `/api/hotspots`（**同一个源**，limit 15） |
| 行动层 | `/action` | `/api/todos` + `/api/kl/planning-actions` + `/api/reviews/due` |

三层共用 v0 资讯世界；v1 九对象只是嵌进去的区块（SignalPanel / CaseQueuePanel / ExecOverviewPanel）。
**"资料 / 判断 / 行动"目前是同一个 feed 的三种排版。**

### D4【P0 · 违反 C2】注意力经济失衡：9,872 : 14

0.14% 的交互率意味着看板没有在承担看板职责——它是一个"需要人自己筛"的漏斗出口。
按 L2，正确形态是**有限、可清零的队列（收件箱语义）**，而非无界时间流。

### D5【P1 · 违反 C4】资源投入方向反了：负债 ≫ 资产

5,584,559 行质量日志 vs 9,872 条资讯 vs 1 条知识。每一步过滤都逐条落库，这是 `O(候选数 × 门数)` 的写放大；而真正有价值的结论是 `O(1)`。
COLD 层只有 28 KB，"审计/历史下沉"没有兑现；WARM 超设计目标 10 倍。

### D6【P1 · 违反 L3】AI 不在环内

`ai_scores = 0` 且流水线用常量 `5.0` 兜底 → AI 评分环节从未真实生效，**但它决定了知识能否发布**。
即：AI 看板里 AI 的主要贡献在**采集与分类**（机器侧），不在**判断辅助**（人侧）。

### D7【P1 · 违反 L3】健壮性债

- 954 处宽泛 `except Exception`（6 天 +82）→ 失败静默。系统无法自证"今天我跑成功了什么"，这与 L3（可辩护）直接冲突。
- dev server `0.0.0.0` + `/api` 反代 + 后端零鉴权 → **同局域网任何设备可完整访问后端能力**（读全库、调子进程、发起出站抓取）。
- 备份 887 MB / 9 份 / 最老 20 天，保留策略未生效。
- 5.3 GB 本地磁盘中入仓仅 1,686 文件——大量不可复现的本地状态。

### D8【P1】界面复杂度来自页面，不是来自数据（前端审计量化版）

**页面即瓶颈**：全站 32 个组件超过 300 行，最大的 12 个里有 7 个是三层页面本身——`v1/CaseDetail` 788 / `SentinelActionPage` 734 / `SentinelGraphPage` 706 / `SentinelHomePage` 672 / `SentinelGardenPage` 643 / `SentinelSettingsPage` 589 / `SentinelJudgePage` 575。

**数据层事实上是缺失的**：

| 指标 | 实测 |
|---|---|
| 裸 `fetch(` | **275 次 / 104 文件**（非测试） |
| 统一封装 `lib/api.ts` 的采用 | 仅 **14 文件 / 133 引用**（且它自己只含 1 个 fetch） |
| `api/v1.ts` 覆盖面 | 只有 `/api/v1/*`；其余 190+ 端点全是手写 |
| 字面端点总数 / 其中被 ≥2 文件重复调用 | **193 / 36** |
| `/api/hotspots` 调用方 | **5 个文件**（Garden / Graph / Judge / Shell / useHotspotData） |
| 缓存/失效层 | **0**（无 react-query / SWR / QueryClient）；唯一去重是 `useFavorites.ts:52` 手写单飞 |
| 数据轮询 `setInterval` | 14 个文件；真 SSE 只有 2 处 |

DEV-0167（首页刷新自激：44 分钟 88 次采集、172 次 `POST /api/refresh`）的根因不是回调写错，**是缺数据层**——没有缓存、没有失效、没有"只读重拉 vs 触发采集"的类型区分。同源缺陷还有一处实锤：`hooks/useRefreshInterval.ts:28` 每个实例各自 `useState` 读 localStorage，**无 storage 监听、无单例** → GeneralSettings / SourceSettings / SentinelHomePage 三份独立副本，改一处另两处不刷新。（`grep "addEventListener('storage'"` = 0 命中。）

**规格的 8 态语义没有落地**：`loading` 374 / `error` 725 处，而 `unavailable` 仅 **19**、`isStale`/`isPartial` **0**。只有 v1 三个区块做到了"unavailable ≠ empty ≠ 0"（`SignalPanel.tsx:57,130` / `ExecOverviewPanel.tsx:37,69`），三个三层主页面（Home / Judge / Action）零实现——`SentinelActionPage.tsx` 全文无 `unavailable` 渲染路径。

**"唯一壳"在壳层成立、在导航层不成立**：壳组件确实只有一个（`SentinelShell.tsx:237`，45 条内容路由无一绕过），但 `PageLayout` 组内嵌了 `secnews/layout/SecNewsShell.tsx:39` 的 tab 导航与 `knowledge/KnowledgeLayout.tsx:82` 的 KnowledgeTabs → **单个路由渲染 2 层导航**，违背 `frontend/src/AGENTS.md`"禁止新一级入口/页内主导航"的硬规则。守卫测试 `v085_route_shell.test.tsx` 只做字符串断言，**测不到这件事**。

**体积虚胖**：`dist` 2.4 MB，其中 `vendor-echarts` **1.14 MB raw / 384 KB gzip = JS 总体积 51%**，而 echarts 全站只被 **3 个低频组件**使用（KnowledgeCompoundingDashboard / KnowledgeGraph / MasteryGauge）。（顺带修正一处历史表述：规格提到的"echarts + recharts 双图表库"不成立——**recharts 根本没安装**，`src` 里只有 3 条提及它的注释。真问题是**单库全量引入，未按需注册 `echarts/core`**。）

**可控的债**：真死文件只有 1 个（`LocaleToggle.tsx` 24 行）；但 `SkillCard`（两份 196/157）、`ComplianceMatrix`（两份 69/117）、`StatusBar`（两份）、`DeepReadMode`/`DeepReadPage`、`ReviewMode`/`ReviewPage` 合计约 **1,500 行冗余**。i18n 覆盖仅 **10.2%**（20/196 文件），其余 3,645 条硬编码中文。

### D9【P2】组织熵与权威链分裂

- 顶层 `secnews-dashboard/`、`security-cockpit/` 是 2026-07 的**设计稿产物**（0 个 `.py`，被 `backend/` 代码引用 **0 次**；`security-cockpit` 即 CRM 座舱方案 C 的设计稿，与 `feature_gates.toml:81` 注释对应）。
- `agent/` 是**未跟踪的废弃产物**（`.gitignore:108`，`git ls-files agent` = 0；内容是一个 README 美化 skill 包，与后端业务零交集）。
- `playbook_engine/`、`skill_eval/` 是被后端读取的数据目录，但用的是 **CWD 相对路径**（见 D15）。
- `knowledge/` 176 个 md 是已声明废弃的**第二 wiki 根**。
- `PROJECT.md` 顶部堆了 5 个互相 supersede 的"当前入口"横幅；docs 700+ 文件，CRITICAL_REVIEW 已到第二版。
- **文档权威链本身在多处分裂——与 D1 同源：一个项目两套真相。**

### D10【P2】五个子系统里只有一个是目标本身

SecNews（资讯）/ Knowledge（知识）/ Security Graph（安全图谱）/ CodeGarden（项目生命周期）/ CRM（业绩座舱）。
后两者与"安全从业者的 AI 看板"无因果关联，却各占 router、service、页面、迁移、测试配额。复杂度预算被内部广度花掉，而不是被用户的决策吞吐量花掉。

### D11【P0 · 违反 C1】"技能商店"是一个自我体检工具箱，不是安全从业者的能力箱

`backend/services/skill_registry/builtin.py` 的 20 个内置 skill，按实际目标模块统计：

| 类别 | 数量 | 明细 |
|---|---|---|
| **系统自我体检** | **14 / 20（70%）** | 信源质量巡检 / 信源失败率趋势 / 采集器健康自检 / 采集器失败分析 / 源生命周期趋势 / gateway 错误码分布 / dsh·pi 任务审计 / TODO 跨期跟踪 / Secrets 轮换状态 / Feature Gate 矩阵 / API 路由健康 / 迁移一致性校验 / MCP tools 可用性 / wiki 根合规 |
| 安全业务 | 6 / 20（30%） | 本周 top5 安全事件 / 今日漏洞情报聚合 / 关键词 30d 趋势 / CVE 提及网络 / 日报 / 周报 |

其中 3 个（日报 / 周报 / 本周 top5）本质是"把资讯聚合一下"，1 个是关键词计数；**真正构成安全分析动作的只有 `daily-vuln-intel` 和 `cve-mention-network` 两个**。

**这是一条因果链，不是一个巧合**：skill 的 step 类型只有三种——`service`（反射调内部 Python 方法，10 处）/ `llm`（7 处）/ `wiki`（7 处），目标模块里 12/15 是 `source_scheduler_repo`、`source_census_service`、`search_service`、`todo_repo`、`db`、`extensions` 这类系统自身组件。

> **Agent 的能力上限 = 它被暴露的对象集合。**
> 系统没有资产、没有 SLA、没有 incident、没有暴露面——**所以 agent 只能去看管道。** D11 不是"skill 选错了"，是 §5.5 那四项领域能力缺失的必然投影。

**后果**：v0.8 的全部"AI Agent"投入（trigger_gate / agent_loop / agent_memory / skill_eval）产出的能力，对这个人的安全工作是**净零**。

### D12【P0 · 违反 C5】数据层没有 schema 真相源，且 WAL 下跨库写入不原子

这是本文**唯一与 §0.1 同级的非安全类 P0**——因为它是**不可恢复**的那一类风险。

| 事实 | 证据 |
|---|---|
| 三库靠 ATTACH，但**写入是隐式的** | `repository/db.py:90-114` ATTACH `warm`/`cold`；**显式 `INSERT/UPDATE/DELETE` 到 `warm.`/`cold.` 全仓 = 0 处**（我已复核）；写操作靠 SQLite "未限定表名解析"落到 warm |
| schema 真相源不存在 | 唯一真相是启动期 `init_db()` 逐条 `executescript` 106 个 `.sql`；无 dump-schema 快照 |
| 迁移副本已腐化 | `data/migrations/` 67 个 `.sql`，与 `backend/repository/migrations/` diff 出 **40 个文件只在后者存在**（副本停在 070） |
| 编号有洞且不阻断 | 空洞 4 个（066-069），`db.py:198-229` **只 warning 不阻断启动** |
| 跨库事务非原子 | SQLite 语义：多附加库事务原子性要求 `journal_mode ≠ WAL`；而 `db.py:76` **强制 WAL** → 任何跨 hot/warm/cold 的写，崩溃时原子性无保证 |
| 运行时探测表名 | `services/search_service.py:43-49` `return "warm.knowledge_items" if "warm" in attached else "knowledge_items"` —— "路由靠环境"的显式自证 |
| 三库路径两份真相 | `scripts/migrate_temp_layers.py:63-66` 硬编码三库路径，与 `backend/config/__init__.py:47-49` 不一致 |

**同类历史补丁**：`db.py:137-160` 启动期主动 `DROP` 引用缺失表的 view——注释自承是因为"hot.db 旧 `unified_search` view 引用了分库前的 `knowledge_items`"。这条补丁本身就是"分库没有单一真相"的负债证明。

**后果**：一旦 warm 库损坏，**没有 schema 可重建、没有备份可恢复（见 §0.1 P0-C）、跨库写入的原子性无保证**。三件事叠在一起，是全场最高风险组合。

### D13【P1 · 违反 L3】观测面有洞：88 个文件的生产日志静默丢失

| 事实 | 证据 |
|---|---|
| 无 InterceptHandler | `grep -rn "InterceptHandler\|basicConfig\|addHandler" backend` → **唯一命中是一句注释**（`utils/shutdown.py:32`） |
| 日志库分裂 | stdlib `logging.getLogger(`：**88 个非测试文件**；loguru re-export：155 个文件；两者混用 3 个 |
| 后果 | 这 88 个文件的日志**不落 app.log**，只靠 `logging.lastResort` 把 WARNING+ 打到 stderr |
| **连异常处理器自己中招** | `backend/exceptions.py:8,15` 用 stdlib logging → **全局异常处理器的日志也不落盘** |
| 项目自己已记录 | `utils/shutdown.py:31-32` 注释：「stdlib logging 无 InterceptHandler → 输出不可见。新代码一律用 loguru」；`docs/CHANGELOG.md:289` 同样自述 |

**叠加效应**：`except Exception` **954 处**（services 402 / api 160 / repository 118 / scheduler 111），其中 **145 处紧跟 `pass`**（静默吞）。**失败既不抛、也不落盘**——系统无法自证"今天我跑成功了什么"。

**再加一层**：**两套互不兼容的错误响应体**。`exceptions.py:108-138` 只注册了 `HotspotException` + `Exception`，**没有 `HTTPException` handler**（我已复核）→ 自定义异常走扁平 `{code,message,trace_id,version}`，而 `HTTPException` 走 FastAPI 默认的嵌套 `{detail:{...}}`（无 trace_id、无 version）。契约定义 **8 个错误码，实装 4 个**（缺 `E_AUTH`/`E_FORBIDDEN`/`E_RATE_LIMIT`/`E_GATE_CLOSED`）；契约文档里的 `E_CASE_CONFLICT` 在代码中出现 **0 次**。

### D14【P1】分层名存实亡：router 超限 43%，且直连 SQL

| 指标 | 实测 |
|---|---|
| router 文件 >150 行（规格上限） | **36 / 83 ≈ 43%**；最大 `api/knowledge.py` **711 行 / 46 个 handler**（超限 4.7 倍） |
| **api 层自己 `get_connection()`** | **50 次 / 21 文件**；`conn.execute(` 60 次 —— router 直接持有 SQL |
| service 层绕过 repository | **240 次 `get_connection()` / 74 文件**（占 services 的 37%） |
| 反向依赖 `services → api` | **8 处**，根因单一：SSE 的 `publish_event` 物理上住在 API 层（`compiler.py:545`、`collection_service.py:293`、`outbox_dispatcher.py:56`、`alert_service.py:189` + 4 处 scheduler） |
| 上帝模块 | `collection_service.py` 1113 行 / 9 个子包依赖；`ai_hub/gateway.py` 887 行 / 30 个公开方法；`jobs/maintenance.py` 724 行 / 20 个不相关 job；`knowledge_repo.py` 853 行 / **47 个公开方法** |

**这条与 D12 同源**：router 直连 SQL 意味着"数据访问只有 repository 一层"的规格在代码里不成立，所以"schema 单一真相"在架构上也无从建立。

### D15【P1】调度与配置：19% 死代码，53 个 job 不受门控，配置有三处真相

| 事实 | 证据 |
|---|---|
| 死 job | `jobs/*.py` 定义 71 个 `*_job`，注册 58 个 → **11 个纯死代码**（`trend_rebuild_job` / `fts_rebuild_job` / `db_diet_job` / `security_enrichment_job` / `url_content_check_job` …） |
| job 状态不持久 | `create_scheduler()` 未配 jobstores → `MemoryJobStore`，**重启丢状态、无补跑** |
| 门控覆盖不足 | `EXTENSION_JOBS` 只登记 **8 个** job → **约 50 个 job 完全不受 feature gate 控制** |
| **备份与校验相隔最多 6 天** | `daily_db_backup_job` 每日 04:30 vs `backup_verify_job` **周一 02:00** → 备份坏掉最久 6 天后才知道（与 §0.1 P0-C 叠加） |
| 配置三处真相 | `collect_interval_seconds`：pydantic 默认（`config/__init__.py:61` = 1800）/ env / **DB settings.kv**；`main.py:47-63` 启动期用 DB 覆盖代码默认 → **运行时可写、文件不可见** |
| 绕过 config 直读 env | **136 处**（`os.environ` 122 + `os.getenv` 14）→ pydantic schema 不是配置的完整清单 |
| 路径两份真相 | `playbook_engine/loader.py:23` 与 `skill_eval/dataset.py:35` 用 **CWD 相对路径**（`Path("playbook_engine/examples")`），换工作目录即失效 |

### D16【P0 · 违反 C1/L3】"行动层"是死锁，证据收据是死信

见 §0.1 P0-D 与 P0-E（完整链路与文件行号在那里）。归纳成判据语言：

- **L1 单位律**：系统承诺的原子单位是"判断 + 行动 + 回执"，但**行动永远停在 `queued`**、**回执永远停在 `pending`**。承诺的对象有一半在代码里不可能到达终态。
- **L3 可辩护律**：证据链对 judgment / action / knowledge **三种对象全部断在第一步**（`create_intent` 白名单不含它们，异常被吞）。这意味着系统即使在将来产生了结论，也**无法为结论生成证据收据**。
- **连带**：`close_case` 的 (b)(c) 守卫互斥，**Case 永远关不掉**——而"结案"是"沉淀"的前置。飞轮的最后两个环节被同一个 bug 同时焊死。

> 我在此更正初判：D6 写的"AI 不在环内"**方向对但归因错**。真正的问题不是我原先说的"没有燃料"，而是**发动机本身没有曲轴**——即使灌满燃料也不会转。

### D17【P0 · 违反 L1】语料重心与产品定位错位：这是一个 AI 资讯站，套了安全外壳

| 切片 | 数量 | 占比 |
|---|---|---|
| `ai` | 5,563 | 56% |
| `tech` | 2,869 | 29% |
| **`security`** | **802** | **8%** |
| `ai_security` | 9 | 0.09% |

源注册表同样错位：`crawler_sources` 101 个里 **64 个是招投标源**；安全源仅 16 个（active 3 / dead 5 / disabled 8）。
而招投标方向投入巨大（`bid_collector.py` 887 行 + `sogou_search.py` 667 行），产出是 **24 条** hotspots。

**后果**：即使把架构、闭环、数据层全部修好，**喂给安全从业者的仍然是 AI 资讯**。这是产品定位问题，不是工程问题——但它会让所有工程投入的边际收益趋近于零。

### D18【P1】安全知识图谱是"死种子"，且图没有边

| 事实 | 证据 |
|---|---|
| 图**没有边** | `security_edges` **0 行**；`security/graph.py:132` 的 `_load_compliance_edges()` 直接 `return []`（硬编码空） |
| ATT&CK 映射表全空 | `attack_techniques` **0**、`attack_cwe_map` **0**；`attack_loader.py:30` 的 `load_attack_data()` **无任何启动调用方**，唯一入口是手动 `POST /api/cve/attack-data/load` |
| tactic 数据被污染 | `security_entities` 里 `entity_type='tactic'` 只有 1 行：`id='x', name='test'`（14 个 tactic 一个都没同步成功） |
| 合规种子从未落库 | `COMPLIANCE_BUILTIN` 8 条定义完整，`security/compliance.py:89` 的 `iter_builtin()` **零调用方** → compliance 实体 **0 行** → 合规视图恒显示"暂无合规数据" |
| **CVE 不是来自 NVD** | 全仓**无 NVD/CNVD 客户端**；30 条 CVE 是 `security_enrichment_job` 用**正则从新闻标题抽**出来的（`knowledge_items` 3,800 行中仅 34 行有 `cve_ids` = **0.9%**），**年份停在 2020（无 2021+）** |
| 术语表 | `security_terms` **3 行，全是测试数据** |
| 图谱不参与研判 | 唯一消费方是内置 skill `cve-mention-network`（**默认关闭**）；`judgment_service` / `case_service` 对图谱**零引用**；19 个 MCP tool 里**零个**安全域工具 |

**后果**：`/knowledge/process`、`/secnews/analytics` 的 ATT&CK / 合规 / CVE 三个视图**永远空**。安全域"看起来很重"的那部分，是离线种子 + 静态查表 + 正则提取。

### D19【P1】大面积空壳能力：注册了、有 UI，但零数据流过

实测为 **0 行**的表所对应的能力：

| 能力 | 表 | 行数 |
|---|---|---|
| 告警引擎（3 规则 + 5 通道） | `alerts` / `alert_events` / `alert_rules` / `alert_deliveries` | 全 **0** |
| 技术栈影响分析 | `tech_stack` | **0** |
| CRM 业绩座舱（13 端点 + 1 页） | `crm_customers` / `crm_opportunities` | **0** |
| CodeGarden 服务网格 / 资源中枢 / 漂移 | `cg_resources` / `cg_dependencies` / `cg_events` / `cg_drift_assessments` | 全 **0** |
| playbook 引擎 | `playbook_runs` / `playbook_schedules` | **0**（`examples/*.yml` 零消费方） |
| skill_eval 评测框架 | — | 全仓**零消费方** |
| 注意力热图 | `attention_events` | **0**（无任何写入方） |
| 用户自建 skill | `user_skills` | **0** |
| 触发队列 | `trigger_tickets` | 53 行，**全来自 2026-09-04 测试，且全部停在 `running`** |

**再加一条最刺眼的**：26 个 skill 的 `default_enabled` **全为 False**、settings 表**没有任何 `skill.*` kv** → `is_skill_enabled()` 恒 False。而 `skill_runs` 的 58 行**全部来自 pytest**（result 里的 wiki 路径是 `/private/var/folders/.../pytest-of-duke/pytest-48/...`）——**生产从未运行过一次 skill**。

**另有 spec 违反**：`scripts/t085_seed_review_fixtures.py` 造的评审 fixture 落在了**生产库**（`v1_cases('C11 live verify 2')` / `v1_judgments('JJJJ…')` / `v1_knowledge('K1')`），与 `V0.8.5_PLAN.md` §9「生产库零写入」直接冲突。

---

## 5. 优化方案

### 5.1 目标态（一句话）

> 从"资讯管道 + 两套本体"，收敛为**单一决策账本（Single Decision Ledger）**：
> **一条资讯只有一条身份、一条状态机；人的每一次判断都是一等写入。**

### 5.2 目标架构（四层，一套对象）

```
① 采集与准入层（无人值守，产"材料"）
   Source → Fetch → Normalize → Admit  ⇒  【Material】唯一身份 = content_hash
   质量门日志聚合为"轮次统计"，不逐条落库；三条采集路径合并为一条

② 决策账本层（唯一真相）
   Subject（持续关注对象：厂商 / CVE / 资产 / 攻击组织 / 法规）
     └─ Signal（值得注意的变化，必须挂在 Subject 上）
          └─ Case（一次需要结论的工作）
               ├─ Judgment（claim + evidence[] + confidence + counter + unknown + revision）
               ├─ Action（决定做什么）→ Run（执行回执）→ Artifact（可交付产物）
               └─ Knowledge（条件化经验：适用条件 + 失效条件 + 复查时间）
   ★ 人的每次交互（收藏 / 标注 / 评估 / 采纳）都写成账本的一行，不是旁路表

③ 视图层（三层壳不动，语义按账本重排）
   资料层 /       = Subject 监控盘 + 待立项 Signal（有限集合，非无限流）
   判断层 /judge  = 待判断 Case 队列（默认视图）+ 上下文装配（证据/反证/历史同类）
   行动层 /action = 待批准 Action + 待验收 Artifact + 到期复查 Knowledge
   工具页          = 保持现状（/secnews /skill-store /knowledge /settings ...）

④ 输出层（今天几乎不存在，却是 L3 的兑现处）
   报告 / 简报 / 工单 / 复盘 = 账本的可追溯投影（每条结论带 evidence 链 + revision）
```

**硬约束**：不引入新框架（保持 FastAPI + SQLite 单进程）；**不改壳、不改导航、不改视觉 token**；所有变化在壳背后。

### 5.3 数据层：Single Decision Ledger（六步，可按顺序独立交付）

| # | 步骤 | 内容 | 风险 |
|---|---|---|---|
| S1 | **身份归一** | 以 `content_hash` 为全系统材料主键；`hotspots` / wiki item / `v1_materials` 统一为它的**投影视图** | 中（需迁移） |
| S2 | **判断落库** | 收藏 / 标注 / `POST /api/llm/evaluate` **一律写 `judgments`**（新增 `kind` 区分 `ai_draft` / `human`，记 `actor`） | **低（不改 AI，只加写入）** |
| S3 | **生命周期合并** | kl_pipeline 五阶段 + `v1_knowledge` 四态机 → 一个状态字段 + 一张迁移表 | 中 |
| S4 | **路径合并** | 三条采集路径 → 一条；`hotspots` 保留为兼容视图（老 API 不改，前端零回归） | 中 |
| S5 | **日志降级** | `quality_check_logs` 逐条 → **轮次聚合**（一轮一行：候选数 / 各门淘汰数 / 入库数 / 耗时） | 低，**存储立即降 3 个数量级且不丢决策信息** |
| S6 | **冷层兑现** | 审计/观测真正下沉 COLD 并加密；WARM 一次性归档 + `VACUUM INTO` 回到 <80 MB 目标 | 低 |

> 关键洞察：质量门要的是**聚合决策信息**（这一轮淘汰了多少、为什么），不是**逐条流水**。今天的 5.58M 行里，99.9% 的信息量可以用几万行表达。

### 5.4 业务流：把"人机交互点"变成一等生产者

| 今天人的动作 | 今天写到哪里 | 目标写到账本哪里 |
|---|---|---|
| 收藏一条热点 | `favorites` 表（旁路） | Judgment(`kind=human`, `claim=关注`) + Evidence 指向 material |
| 标注 | `annotations` 表（旁路） | Judgment 的 `evidence` / `counter` 字段 |
| 点"AI 评估" | **不落库** | Judgment(`kind=ai_draft`) + 人确认/推翻 → 修订历史 |
| 建待办 | `todos` 表 | Action（带 `case_id`、`plan_hash`、approvable） |
| 复习打分 | `reviews` 表 | Knowledge 的 `review_at` / `outcome` 回填 |
| 导出报告 | 生成的 xlsx/报告文件 | Artifact（带 evidence 链与 revision，可追溯） |

**这条表是整个方案的心脏**：不改任何界面控件，只把它们的写入目标换掉，飞轮就通电了。

> ⚠️ **但下半截必须先补发动机**：表里的 Action / Run / Artifact 三行今天**写进去也没有出口**（§0.1 P0-D）。所以在做这张表之前，必须先回答一个产品问题：**"执行"到底是什么**——派 dsh？派 pi？还是只做"人工回执"（人做了事，回来登记一下）？三种答案对应的执行器完全不同。见路线图 P1-0。

### 5.5 功能设计：安全看板应有的 5 个视图（替代 6 个域）

| # | 视图 | 回答的问题 | 今天的状态 |
|---|---|---|---|
| V1 | **今日队列 Today** | "现在需要我处理什么"（有限、可清零、按 风险×暴露×时效 排序） | ❌ 无（只有无界流） |
| V2 | **对象档案 Subject 360** | "关于这个 CVE / 厂商 / 资产，我知道什么、判断过什么" | ◐ 有 `security_entities` 889 条，但是静态种子，未与判断关联 |
| V3 | **判断工作台 Case** | "这件事我该怎么判"（上下文自动装配 + 结论结构化 + 一键成稿） | ◐ 有 CaseDetail，但零真实数据 |
| V4 | **交付物 Deliverables** | "我怎么把结论交出去" | ❌ 无（report/weekly_report 是资讯聚合，不带证据链） |
| V5 | **系统状态 System** | "管道/源/AI 健康吗" | ✅ 已有（心跳条 + observability），保持只读、不占主导航 |

**必须补的四项领域能力（今天缺，且是"安全"这个词的实质）**：

1. **暴露面/资产视角** —— 今天只有 889 条静态 `security_entities`，没有"我有什么"。没有资产，任何风险判断都没有分母。
2. **SLA / 时效承诺** —— CVE 从发布到处置的计时对象完全不存在。安全工作的一半是"在时限内"。
3. **事件响应时间线** —— 没有 incident 对象，没有 告警→分析→处置→复盘 的容器。
4. **合规举证** —— 有 compliance 种子数据，但没有"这条要求 ↔ 我当前的证据是什么"的映射与缺口视图。

> **为什么这四项比"再加一个 skill"重要**：D11 已经证明，skill/agent 层的能力上限等于它被暴露的对象集合。补一个内部 service 只会多一个自我体检 skill；补一个**资产对象**才会解锁"这个 CVE 影响我哪些资产""这台机器该修哪几个漏洞""这件事超 SLA 了吗"这一整类能力。**先补对象，能力自然生长；先补技能，只会长出自省。**

### 5.6 技术架构：边界与规则（防再次漂移）

| 规则 | 内容 | 检查方式 |
|---|---|---|
| R1 | **单一写入路径**：任何"概念"只有一个 writer 模块 | grep 断言 |
| R2 | **单一身份**：材料主键 = `content_hash`，其余 id 皆为别名 | 迁移测试 |
| R3 | **人的输入必须落账本**：前端不存在"只读不写"的判断控件 | 契约测试 |
| R4 | **失败必须可知**：新代码禁止裸 `except Exception`；全局 handler + 失败面板 | ruff 规则 + CI |
| R5 | **日志不是数据**：观测表必须有聚合与保留策略，禁止逐条无界增长 | 表体积门 |
| R6 | **默认视图是队列**：任何列表页首屏默认排序 = 待处理优先，不是时间倒序 | 路由守卫测试 |

### 5.7 健壮性加固包（低风险高收益，可并行）

> 本节按"收益/成本比"排序。前四项是**个位数到几十行**的改动，却各自消灭一整类故障——应立刻做。

| 项 | 动作 | 成本 | 收益 |
|---|---|---|---|
| **日志回收** | 加一个 `InterceptHandler`（loguru 拦截 stdlib logging） | **个位数行** | 88 个文件 + 异常处理器自身的生产日志**全量回收**（D13） |
| **错误契约统一** | 补 `HTTPException` handler，统一扁平 envelope | **几十行** | 消灭两套响应体；客户端可按 code 分支（D13） |
| **显式库前缀** | 全仓写语句显式加 `warm.` / `cold.` 前缀 | 机械替换 | 写路由不再依赖隐式解析（D12） |
| **schema 快照** | `dump_schema.py` 产物入仓 + CI `--check` | 半天 | 出现 schema 真相源；迁移漂移可被机器发现（D12） |
| 网络暴露 | dev server `host` 收 `127.0.0.1`（§0.1 P0-B） | 1 行 | 消除局域网 RCE 可达面 |
| 命令白名单 | `dsh.command` 不再从 HTTP 自由写入（§0.1 P0-A） | 半天 | 切断 RCE 入口 |
| 备份覆盖 | `backup_service` 扩到 warm/cold + 保留 ≥3 + 校验收紧（§0.1 P0-C、D15） | 1 天 | 消除 899 MB 零备份 |
| SSE 下沉 | `publish_event` 从 `api/events.py` 下沉到 core/service | 半天 | 一次性清掉 8 处反向依赖（D14），规格变可机械校验 |
| 死码清理 | 删 11 个死 job + 修 `data/migrations/` 腐化副本 | 半天 | 治理 19% 调度噪声（D15） |
| 磁盘止血 | 清 5.3 GB 本地垃圾 + 备份保留策略生效 | 半天 | 立即可回收数 GB |
| 写入放大 | 见 S5 | 1 天 | WARM 857 MB → 目标 <100 MB |
| 数据层 | 统一客户端（SWR 语义）+ SSE 作失效源；**先立规则"同一端点唯一 hook owner"** | 1 周 | 根治 DEV-0167 类 bug（275 裸 fetch → 收敛） |
| 状态语义 | 抽 `useAsyncState` 联合类型 + 统一渲染器，补三层主页面的 unavailable/stale | 2–3 天 | 让 spec 的 8 态真正落地 |
| 壳守卫 | 守卫测试升级为"遍历路由表 + 断言每页仅 1 个 nav landmark" | 20 分钟 | 防第二级导航复发 |
| 体积 | echarts 改 `echarts/core` 按需注册 | 1 天 | 省 ~1 MB raw / 384 KB gzip（JS 体积的 51%） |
| 状态真相 | `useRefreshInterval` 改单例（对齐 favorites 的既有修法） | 1 小时 | 消除"同一状态三处真相" |
| 配置真相 | `collect_interval_seconds` 单一来源；`playbook_engine`/`skill_eval` 路径改绝对锚定 | 半天 | 消除 DB 隐形配置层与 CWD 依赖（D15） |

### 5.8 减法清单（比加法重要）

| 删/冻结 | 对象 | 理由 |
|---|---|---|
| 删 | `secnews-dashboard/`、`security-cockpit/` | 2026-07 静态 mockup，220 KB 熵 |
| 删 | `knowledge/` 第二 wiki 根 | 已声明废弃，176 个 md 制造双根歧义 |
| 冻结 | CodeGarden / CRM 移出核心动线 | 与目标无因果关联，占 router/service/迁移配额 |
| 合并 | 三条采集路径 → 一条 | D1 的直接来源 |
| 收敛 | 文档权威链：一份"当前真相" + 一份"历史" | PROJECT.md 五个 supersede 横幅 |

---

## 6. 分批路线图

| 批 | 内容 | 退出条件 | 工作量 |
|---|---|---|---|
| **P0-0 止血**（先于全部） | §0.1 的十条：vite host + 备份 WAL magic/覆盖三库/真写页 + dsh command 白名单 + kl 路径校验 + main.py guard + 证据白名单 + 密钥清扫 + 最小 token | 局域网不可达 `/api/*`；**存在一份非空且可恢复的当日备份**；`v1_evidence_receipts` 出现 committed；`GET env-templates` 返回 `******` | **当天–1 周** |
| **P1-0 补上半场：执行器**（形状取决于产品决策） | `run_service` 加 claim → execute → finish；`run_repo.update_status` 接线；三种可选语义（派 dsh / 派 pi / 人工回执）；解开 `close_case` 的 (b)(c) 互斥 | 一条 action 能从 `queued` 走到终态并产出 artifact；Case 能真正关闭 | 3–5 天 |
| **P0-1 判断不再蒸发** | S2：收藏/标注/evaluate 落 `judgments` + 一个只读"今日判断"区块 | `judgments` 行数随日活增长；`ai_scores` 不再恒 0；**零界面控件改动** | 1–2 天 |
| **P0-2 磁盘与写放大止血** | S5 + S6 + 11 个死 job 清理 + `data/migrations/` 腐化副本 + 清生产库评审 fixture | WARM < 300 MB（先止血）；死 job 归零；生产库无 fixture | 1–2 天 |
| **P0-3 身份归一** | S1 + S4：`content_hash` 主键 + 三路径合并 + `hotspots` 兼容视图 | 同一 URL 在全库只有一个 material id；老 API 零回归 | 3–5 天 |
| **P1-1 三层语义重排** | 判断层默认视图 = Case 队列（不是 hotspots）；资料层加"待立项 Signal"有限集合 | 首屏默认排序 = 待处理优先（R6） | 3–5 天 |
| **P1-2 队列化与 Today 视图** | V1 Today + SLA 对象 + 通知 | 一个人早上打开能看到"今天 8 件事"且能清零 | 1 周 |
| **P1-3 数据层与页面拆分** | 统一客户端 + "同一端点唯一 hook owner" + 七个巨型页面拆分 + 壳守卫升级 + SSE 下沉 | `POST /api/refresh` 不再被 SSE 触发；每路由仅 1 个 nav；8 处反向依赖归零 | 1 周 |
| **P1-4 交付物与证据链** | V4 + Artifact + 报告带 evidence refs + 安全报告模板（漏洞/复盘/合规举证） | 导出一份报告，每条结论可点回原始证据；`ops/`、`analysis/` 有真实交付物 | 1 周 |
| **P1-5 语料重心校正**（D17，产品侧） | 重排源注册表：招投标源 64 → 按需；补安全源（NVD/CNVD/CISA KEV/厂商公告/安全社区）；调分类器让 security 成为主体 | security 切片 > 40%；CVE 数据有 2021+ 且来自权威源 | 1–2 周 |
| **P2-1 减法与权威链** | 5.8 清单 + 1,500 行重复组件合并 + echarts 按需 + `useRefreshInterval` 单例 + 配置单一来源 | 入仓文件数下降；JS 体积降 ~1 MB；文档只有一个当前入口 | 2–3 天 |
| **P2-2 让安全图谱活起来** | 接 NVD/CNVD/CISA KEV 增量；修 `security_edges` FK 与实体插入范围让 ATT&CK 有边；`load_attack_data()` / `iter_builtin()` 接启动；图谱进研判 | `security_edges` > 0；compliance 实体 > 0；CVE 有 2021+ | 1 周 |
| **P2-3 领域能力补齐** | 资产台账 / 事件响应时间线 / 合规举证链 / 威胁建模 | 安全工作的五个实质问题有容器 | 按需 |

> **排序原则**：P0-0 是止血；**P1-0 是"补发动机"**（今天所有下游都是死的，不做它后面全是空转）；P0-1 → P0-3 是"让数据可信"；P1-1 → P1-5 是"让界面服务判断 + 校正语料"；P2 是"减熵与让安全域活起来"。
> **不要先做 P2-2/P2-3**：在没有资产对象之前补 skill 只会再多一个自我体检（D11）；在没有执行器之前补图谱只会多一个空视图。
> **D14（分层名存实亡：router 直连 SQL 50 次 / service 绕过 repository 240 次）刻意排在最后**——它是最大但最贵的重构，收益是"分层可断言"，应在数据层真相源（D12）之后再做。

**每批的验证方式沿用项目既有规则**：实现与验证分离，实现侧不得自评 PASS；每批先写反例测试；涉及注册代码跑 `generate_meta.py --check`。

---

## 7. 风险、反例与我不确定的地方

**我可能错在哪**

1. **如果 owner 的真实目标是"资讯获取效率"而不是"判断吞吐"**，那么"队列化"会降低体验。→ 缓解：P1-2 的 Today 视图做成**可逆开关**，资料层的流式体验保留（只把默认排序换成"待处理优先"）。
2. **v0.8.5 §0.4 已裁定"顺手 > 完备"**。本方案**不动壳与动线**，只在壳背后换数据源与默认排序。若某一步需要动动线，必须停下来找 owner 裁决——这是 v1.0 四入口翻车的教训。
3. **"合并本体"可能引爆大重构**。→ 缓解：S1/S4 走**视图兼容**（老 API 与老表保持可用），而不是一次性迁移；先做 S2（1–2 天，零风险）拿到收益再决定是否继续。
4. **单机单用户的复杂度预算本来就小**。本方案的方向是**减对象、减路径、减日志**，不是加服务；若某一步在增加抽象层，说明走偏了。

**我不确定的（需要 owner 裁决）**

- **【最重要】"执行"是什么？** 这决定 P1-0 执行器的形状，也决定整个"行动层"是否有意义。三个选项：
  (a) **派 dsh/pi** —— 真让 AI 去跑命令、改仓库、出报告（能力最强，风险最高，需要沙箱）；
  (b) **派人工** —— Action 只产生"该做什么"的结构化任务，人做完回来登记回执（最轻，最可控，最贴合单人工作站）；
  (c) **只做回执** —— 不产生执行，Action 只是判断的延伸，产物由人上传登记。
  **我的倾向是 (b)**：单机单用户场景下，把 AI 派去执行系统级动作的收益远低于风险，而"把人做过的事结构化登记下来"正好补上 L3（可辩护）缺的那一半。
- **语料重心（D17）是不是要动？** 如果 owner 的真实使用场景确实是"AI + 安全"（而不是纯安全），那么 8% security 可能是有意为之，我在 D17 的判断就需要撤回。**这一条请 owner 直接确认**，因为它会让 P1-5 从"1–2 周"变成"不做"。
- `hotspots` 保留为视图 vs 直接迁移到 `materials`：前者零回归但长期留两套 id，后者干净但有回归风险。
- CodeGarden / CRM 是"冻结"还是"移出仓库"：取决于 owner 是否仍用它们（两者当前**全 0 行**，实际上已在休眠）。
- 生产 warm 库 853 行迁移（PROGRESS 已列为待授权项）与本方案的 S5/S6 有重叠，需要合并执行而非两次停机。
- **`dsh.command` 白名单 vs 移除该字段**：白名单保留"用户自配 dsh 启动命令"的能力，移除则最安全但会砍掉一个已交付功能。倾向白名单 + 首次配置需本机确认。
- **`publish_event` 下沉的位置**：`core/`（更接近"基础设施"语义）还是 `services/`（与消费方同层）。取决于是否希望 scheduler 也能发布事件而不依赖 services。
- **D14 是否值得做**：240 次 service 直连 + 50 次 router 直连分散在 95 个文件，收益是"分层可机械断言"。如果 owner 更看重功能推进，可以只冻结（新代码必须走 repository，老代码不动）而不做全量重构。**我倾向冻结而非重构。**

---

## 8. 验收（硬数字，可客观判定）

| 指标 | 今天 | 目标 |
|---|---|---|
| 局域网可达 `/api/*` | **可达**（实测 200） | **不可达** |
| `PUT /api/dsh/control/config` 接受任意命令 | **是** | **否**（白名单或移除） |
| **备份产物** | **0 字节 / 无全量快照** | 当日**非空**且通过恢复演练（三库全覆盖） |
| 备份恢复演练 | 假成功（不写页返回 ok） | 真恢复 + 行数/hash 对账通过 |
| `v1_runs` 终态 / `v1_artifacts` | 0 / 0（永远 queued） | 一条 action 走到终态并产出可验收 artifact |
| `v1_evidence_receipts` committed | 0（除 signal 外全 pending） | judgment/action/knowledge 均有 committed |
| Case 可关闭 | **数学上不可能** | 至少一个真实 case 走完 close |
| `PUT /api/kl/items/%2e%2e%2f...` | **可穿越** | 400 拒绝 |
| `GET env-templates`（未解锁） | **返回明文** | 返回 `******` |
| 明文 API key 落库 | 3 份库 | **0** |
| **security 语料占比** | **8%**（802 / 9,872） | **> 40%**，且 CVE 数据含 2021+ 且来自权威源 |
| `security_edges` / compliance 实体 | 0 / 0 | > 0（图谱有边、合规有实体） |
| 零数据能力域（alerts/tech_stack/crm/cg_*/playbook…） | 9 个域全 0 | 要么有数据，要么下线（不留空壳） |
| 显式 `warm.`/`cold.` 写语句 | **0** | 全部写语句带前缀 |
| schema 真相源 | 无 | `dump_schema` 产物入仓 + CI `--check` 0 drift |
| stdlib-only 日志文件 | **88** | **0**（InterceptHandler 后） |
| 错误响应体种类 | 2 套 | **1 套**（扁平 envelope） |
| 错误码实装率 | 4 / 8 = 50% | 8 / 8 |
| `judgments` 行数（含 human） | 1 | 与日活匹配（≥ 每日 3–5 条） |
| `ai_scores` 行数 | 0 | > 0 且持续增长 |
| 人工交互率（交互 / 入库） | 0.14% | **> 20%**（靠"入库量下降 + 队列化"两头夹） |
| WARM 库大小 | 857 MB | **< 100 MB** |
| 后端宽泛 `except Exception` | 954 | 单调下降（新代码为 0） |
| 死 job | 11 | 0 |
| 裸 `fetch(` / 重复调用端点 | 275 / 104 文件 / 36 端点 | 单调下降；"同一端点唯一 hook owner" |
| 每路由 nav 层数 | 部分 2 层 | **恒为 1** |
| 一条真实 CVE 端到端 | 无法走通 | 采集→取证→判断→行动→产物，全链可追溯，带 evidence 链与 revision |
| 复利可见 | 无法验证 | 第二次同类出现时，上次结论自动浮现且被"采用" |

**软指标（一句话）**：一个人早上打开看板，看到的是**"今天 8 件事 + 其中 3 件我已经有历史判断可以复用"**，而不是"今天 200 条新资讯"。

---

## 附录 A：证据索引（命令与实测结果，2026-09-11）

| 论点 | 命令 | 结果 |
|---|---|---|
| 架构数字 | `python3 scripts/generate_meta.py --check` | `{"jobs": 58, "collectors": 14, "routers": 85, "services": 126}` OK |
| 代码规模 | `find backend -name '*.py' \| wc -l` / `cat \| wc -l` | 822 / 186,115 |
| 表数 | `sqlite3 backend/hotspot.db ".tables"` | 129 |
| WARM 体积 | `ls -lh backend/*.db` | warm **857M** / hot 34M / cold 28K |
| 质量日志 | `SELECT COUNT(*) FROM quality_check_logs`（warm） | **4,745,555**（+ archive 836,004） |
| 人工交互 | `favorites` 6 / `todos` 6 / `annotations` 2 / `attention_events` 0 | 见 §3.3 |
| v1 占用 | `v1_materials`4 / `v1_signals`3 / `v1_judgments`1 / `v1_runs`0 / `v1_artifacts`0 / `v1_knowledge`1(retracted) | 见 §3.4 |
| 点火单源 | `backend/services/v1_ingest_bridge.py` | `_DEFAULT_SOURCES = "security:SecWiki"` |
| AI 不在环内 | `SELECT COUNT(*) FROM ai_scores` = 0；`api/llm_status.py:86-136` 无写路径 | 见 §3.5 |
| 常量兜底 | `services/triggers/t4_structure_to_publish.py:65` | `DEFAULT_SCORE = 5.0` |
| 判读层主源 | `frontend/src/components/sentinel/SentinelJudgePage.tsx:202` | `fetch('/api/hotspots?...limit=15')` |
| 收藏不写 v1 | `grep -l "v1_" backend/api/favorites.py` | 无命中 |
| 双本体桥 | `backend/repository/migrations/107_v10_legacy_mapping.sql` | `legacy_source ∈ {dev_seed, warm.knowledge_items, wiki_items}` |
| 只入库不落 wiki | `backend/services/v1_ingest_bridge.py:81` | `# D1: 信号/Material 只入库, 不落 wiki` |
| 宽泛 except | `grep -rn "except Exception" backend --include=*.py \| grep -v /tests/ \| wc -l` | **954**（services 内 402） |
| 局域网暴露 | `frontend/vite.config.ts:14,18-23` | `host: '0.0.0.0'` + `/api` → `127.0.0.1:8000` |
| 磁盘 | `du -sh .` / `git ls-files \| wc -l` | 5.3G / 1,686 文件 |
| 顶层 mockup | `ls secnews-dashboard security-cockpit` | `.design` / `colors_and_type.css` / `pages/`（2026-07） |
| 技能自省比例 | `grep -oE 'skill_type="[ABC]"' backend/services/skill_registry/builtin.py \| sort \| uniq -c` | A 12 / C 4 / B 1；目标模块 12/15 为系统自身组件 |
| skill step 种类 | `grep -oE 'kind="[a-z]+"' backend/services/skill_registry/builtin.py \| sort \| uniq -c` | service 10 / llm 7 / wiki 7（**无外部工具/资产类 step**） |

**§0.1 三个 P0（主会话独立复现）**

| 论点 | 命令 / 位置 | 结果 |
|---|---|---|
| RCE：自由命令入参 | `backend/api/dsh_control_api.py:30,64-72` | `command: str \| None (max_length=2000)`，无白名单 → `set_dsh_config()` |
| RCE：无校验解析 | `backend/services/dsh/supervisor.py:35-43` | 仅 `shlex.split` |
| RCE：执行汇 | `backend/services/process_supervisor.py:101-102` | `subprocess.Popen(command, ...)` |
| RCE：触发 | `backend/api/dsh_control_api.py:40` | `POST /api/dsh/control/start` |
| 无鉴权 | `grep -rnE "HTTPBearer\|APIKeyHeader\|get_current_user" backend --include=*.py` | **0 命中** |
| 无命令黑名单 | `grep -n "danger\|blacklist\|黑名单\|allowlist" backend/services/process_supervisor.py backend/services/dsh/*.py` | **0 命中** |
| 8898 绑 0.0.0.0 | `lsof -nP -iTCP:8898 -sTCP:LISTEN` | `node 15572 ... TCP *:8898 (LISTEN)`，命令行含 `--host 0.0.0.0` |
| 8898 反代后端（实测） | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8898/api/dsh/control/status` | **200**（`/api/health` 亦 200，返回完整后端 JSON） |
| 后端自身已防护 | `run.py:39-45` | 非回环绑定强制改回 `127.0.0.1`（除非 `HOTSPOT_ALLOW_LAN=1`） |
| 但 guard 未覆盖 | `backend/main.py:305-312` | `__main__` 分支直接 `uvicorn.run(host=...)`，无 guard |
| 备份只覆盖主库 | `backend/services/backup_service.py:169`；`grep -n "warm\|cold" backup_service.py` | `src = Path(config.db_path)`；**0 命中** |
| 备份保留 1 份 | `backend/services/backup_service.py:40,189-197` | `BACKUP_RETENTION = 1`，glob `hotspot-*.db` |
| 最新正式备份 | `ls -lht backups/` | `hotspot-20260829_200000_stray.db` 16 MB / mtime **2026-08-30 04:00**（≈12 天前；当前主库 34 MB） |
| warm 唯一副本 | `ls -1 backups \| grep -i warm` | `hotspot-warm.db.bak-esc-20260829_235118`（463 MB 手工快照，不受保留策略管辖） |

**前端审计（独立子审计，量化实测）**
| 论点 | 命令 / 位置 | 结果 |
|---|---|---|
| 裸 fetch 规模 | `grep -rn "fetch(" frontend/src --include=*.tsx --include=*.ts` | **275 次 / 104 文件**；`lib/api.ts` 仅 14 文件采用 |
| 端点重复 | 正则抽取字面端点 | 193 个端点，**36 个被 ≥2 文件调用**（`/api/hotspots` 5 文件） |
| 无缓存层 | `grep -rln "react-query\|swr\|QueryClient" frontend/src` | **0** |
| 8 态未落地 | 命中计数 | `loading` 374 / `error` 725 vs `unavailable` **19** / `isStale` **0** |
| 两处真相 | `frontend/src/hooks/useRefreshInterval.ts:28`；`grep "addEventListener('storage'"` | 每实例独立 `useState`；storage 监听 **0** |
| 双导航 | `secnews/layout/SecNewsShell.tsx:39`、`knowledge/KnowledgeLayout.tsx:82` | 单路由渲染 2 层导航，守卫测试测不到 |
| echarts 虚胖 | `du -sh frontend/dist`；chunk 清单 | 2.4 M 总；`vendor-echarts` **1.14 MB raw / 384 KB gz = JS 51%**，仅 3 个低频组件用 |
| recharts 不存在 | `grep -rn recharts frontend/src`；`package.json` | 仅 3 条**注释**，依赖中无此库（修正历史表述） |
| 重复组件 | 同名近似实现比对 | SkillCard ×2 / ComplianceMatrix ×2 / StatusBar ×2 / DeepRead ×2 / Review ×2 ≈ **1,500 行** |
| i18n 覆盖 | `useI18n` 使用文件数 | **20 / 196 = 10.2%**，其余 3,645 条硬编码中文 |
| 大文件 | `find components -name '*.tsx' ! -name '*.test.tsx' \| xargs wc -l \| sort -rn` | >300 行组件 **32** 个；最大 `v1/CaseDetail.tsx` **788** |

**后端审计（独立子审计，量化实测；★ = 主会话已独立复核）**

| 论点 | 命令 / 位置 | 结果 |
|---|---|---|
| ★ 显式跨库写 = 0 | `grep -rnE "(INSERT\|UPDATE\|DELETE)[^;]*\b(warm\|cold)\." backend --include=*.py`（去 tests） | **0**（写路由完全靠未限定表名的隐式解析） |
| 隐式写实例 | `repository/knowledge_repo.py:35` / `services/collection_service.py:860,949,1035` | `INSERT INTO knowledge_items` / `raw_items` / `crawler_runs`（无前缀） |
| 运行时探测表名 | `services/search_service.py:43-49` | `"warm.knowledge_items" if "warm" in attached else "knowledge_items"` |
| ★ 无 `HTTPException` handler | `grep -rn "exception_handler" backend` | 只有 `HotspotException` + `Exception` 两个（`exceptions.py:111,124`） |
| ★ 备份产物为空 | `ls -la backend/backups/ backend/backups/incremental/` | **无任何 `.db` 全量快照**；增量 `.bin` **三个全 0 字节**（9/7、9/8、9/10），`chain.meta` 每日 04:30 仍更新 |
| ★ 备份 WAL magic 恒假 | `backup_service.py:243` vs `od -N16 hotspot.db-wal` | 代码要 `37 7f 06 15`，实际 `37 7f 06 82` → 判断恒假，立即 return 空 |
| ★ 增量恢复不写页 | `backup_service.py:380-387` | 函数体内**零个写操作**，却返回 `{"ok": True, "applied_pages": N}` |
| 备份校验是空校验 | `scripts/check_backup_chain.py:114-121` | 自述"简化"，实际 `pass` → **永远 PASS** |
| ★ run 永停 queued | `run_service.py:155` | `"status": "queued",  # v1.0 C07 R05 修复: 永远 queued` |
| ★ `run_repo.update_status` 零调用 | `grep -rn "update_status" backend --include=*.py` | `run_repo.py:89` 定义后**无任何调用方**（其余 repo 的 update_status* 均有调用） |
| ★ artifact 需 run_id | `artifact_service.py:93` | `raise ArtifactValidationError("run_id required")` |
| ★ case 守卫互斥 | `case_service.py:426,427` | (b) 无 active run **且** (c) 有 verified/accepted artifact → 数学上不可能同时满足 |
| worker 泵不写 v1_runs | `jobs/worker_pump.py:44` | 注释自述"与 run_service 的 create_or_replay 解耦" |
| 证据收据死信 | `judgment_service.py:322-325` → `v1_evidence_service.py:198-225` | `entity_type="judgment"` 不在白名单 → `commit_intent` 必抛 → 被 `:326-328` 吞成 warning |
| 收据回收器零调用 | `v1_evidence_service.py:426` | `reap_expired_intents` 无调度器调用者 |
| kl 路径穿越 | `kl_pipeline_api.py:218,228` → `wiki_fs/store.py:49,82` | 裸 `item_id` 拼路径；对照 `wiki_tools.py:114-124` 有白名单 + realpath |
| 明文 key ×3 库 | `SELECT substr(value,1,3),length(value) FROM settings WHERE key='quality.llm_api_key'` | `'sk' | 37`（明文） |
| codegarden 假加密 | `codegarden_resource_service.py:222,258` vs `crypto.py:116` | 参数写反 → 明文落库；`:249` 未解锁分支直接返回明文 |
| 未守卫出站点 | 出站原语分类统计 | 52 个出站原语，**36 个无守卫**；`safe_aiohttp_connector` 生产调用 **0** |
| WAL 仅主库 | `PRAGMA journal_mode` on 三库 | hot=`wal`，**warm=`delete`、cold=`delete`**（ATTACH 不继承 journal_mode） |
| 僵尸 run | `SELECT COUNT(*) FROM catchup_runs WHERE status='running'` | **112**（2026-07-31 起永久卡住） |
| 安全语料占比 | `SELECT category, COUNT(*) FROM hotspots GROUP BY category` | ai 5,563 / tech 2,869 / **security 802（8%）** / ai_security 9 |
| 源构成错位 | `SELECT COUNT(*) FROM crawler_sources` | 101 源中 **64 个 bid**；安全源 16（active 3 / dead 5 / disabled 8） |
| 图谱无边 | `SELECT COUNT(*) FROM security_edges` / `attack_techniques` | **全 0**；tactic 仅 1 行 `id='x', name='test'` |
| 种子零调用 | `security/compliance.py:89`、`attack_loader.py:30` | `iter_builtin()` / `load_attack_data()` **均无调用方** |
| CVE 来源是正则 | 无 NVD 客户端；`knowledge_items` 中 34/3800 有 `cve_ids` | 覆盖 **0.9%**，年份上限 **2020** |
| 空壳能力矩阵 | 逐表 `COUNT(*)` | alerts×4 / tech_stack / crm×2 / cg_resources×4 / playbook×2 / attention_events / user_skills **全 0** |
| 生产从未跑过 skill | `skill_runs` 58 行的 `result` 内 wiki 路径 | 全部为 `/private/var/folders/.../pytest-of-duke/pytest-48/...` |
| 评审 fixture 入生产库 | `scripts/t085_seed_review_fixtures.py` | `v1_cases('C11 live verify 2')` 等落在 `backend/hotspot.db`，违反 spec §9 |
| ★ 无日志拦截器 | `grep -rn "InterceptHandler\|basicConfig\|addHandler" backend`（去 tests） | 唯一命中是 `utils/shutdown.py:32` 的**注释** |
| ★ 日志库分裂 | `logging.getLogger(` vs `from backend.logging_config import logger` | **88** 文件 vs **155** 文件（混用 3）——88 个文件的日志不落 app.log |
| 异常处理器自用 stdlib | `backend/exceptions.py:8,15` | 全局异常处理器的日志也不落盘 |
| 宽泛 except 分布 | `grep -rn 'except Exception' backend --include='*.py'` | 非测试 **954**（services 402 / api 160 / repository 118 / scheduler 111 / collectors 55）；**145 处紧跟 `pass`** |
| 错误码实装率 | `docs/v1.0/contracts.md:59-68` vs 代码 | 定义 8 个，实装 **4** 个（`E_NOT_FOUND`/`E_CONFLICT`/`E_VALIDATION`/`E_INTERNAL`） |
| router 超限 | `find backend/api -name '*.py' \| xargs wc -l` | **36 / 83 ≈ 43%** >150 行；`api/knowledge.py` **711 行 / 46 handler** |
| router 直连 SQL | `grep -c "get_connection()" backend/api/**` | **50 次 / 21 文件**；`conn.execute(` 60 次 |
| service 绕过 repository | `grep -c "get_connection()" backend/services/**` | **240 次 / 74 文件**（services 的 37%） |
| 反向依赖 `services → api` | `grep -rn "from backend.api" backend/services backend/scheduler` | **8 处**（根因：`publish_event` 住在 API 层） |
| 死 job | `jobs/*.py` 定义 71 个 `*_job` vs 注册 58 | **11 个纯死代码** |
| job 门控覆盖 | `backend/extensions/__init__.py:104-121` | `EXTENSION_JOBS` 仅 8 个 → 约 50 个 job 不受 gate 控制 |
| 备份/校验间隔 | `jobs/maintenance.py:185-238` | backup 每日 04:30 vs verify **周一 02:00**（最坏 6 天才知备份坏） |
| 迁移副本腐化 | `diff data/migrations backend/repository/migrations` | 副本 67 个（停在 070），**40 个文件只在后者存在**；编号空洞 066-069 |
| 配置三处真相 | `config/__init__.py:61` / `api/settings.py:57,83` / `main.py:47-63` | pydantic 默认 / env / **DB settings.kv**（启动期 DB 覆盖代码） |
| 直读 env | `os.environ` + `os.getenv` | **136 处**（73 个不同 env 名） |
| CWD 相对路径 | `playbook_engine/loader.py:23`、`skill_eval/dataset.py:35` | `Path("playbook_engine/examples")` / `Path("skill_eval/fixtures")` |
| `agent/` 未跟踪 | `.gitignore:108`、`git ls-files agent` | **0 个入仓文件**（废弃产物） |
| 设计稿 0 引用 | `security-cockpit` / `secnews-dashboard` | 0 个 `.py`，被 `backend/` 引用 **0 次** |

> 附注：本表所有数字均为本次会话（主会话 + 独立子审计）实测；与本文件结论冲突的历史文档（`ARCHITECTURE.md` §二 的 WARM 目标、`CRITICAL_REVIEW_2026-09-03.md` 的 services 320、`V0.8.5_PLAN.md` 的 "echarts+recharts 双库" 等）以本表为准。
