# Hotspot v1.0 真实基线 (T00 交付)

> 日期: 2026-09-05; 基线 HEAD: `943a31d17a4ec63b6616925b6c2a36d6e8a5b37d` (v0.8.2)。
> 方法边界: 本基线为**只读盘点** — 未运行任何 backend 测试、未出网、未写任何数据库/Wiki;
> 数据库数字来自 Python sqlite `mode=ro` + `PRAGMA query_only=ON` 单次快照, 非跨库原子快照。
> 旧 v0.8.3 审查 (F01-F15) 与 v0.8.2 收尾审查 (F1-F7) 的数值只作历史线索, 有效性见 §7/§8。

## 1. 版本与启动

| 项 | 事实 | 证据 |
|---|---|---|
| 软件版本 | **0.8.2** (`backend/version.py` APP_VERSION 单一真源) | `python -c "from backend.version import APP_VERSION"` |
| 产品版本显示 | 前端 AboutSettings 走 `GET /api/health` (后端 APP_VERSION); `frontend/package.json` 的 `0.7.0` **不用于产品显示** (滞后字段, T00 不改) | `AboutSettings.tsx:22` |
| 启动入口 | `run.py` → `uvicorn backend.main:app --host 127.0.0.1 --port 8000` (WORKERS=1, 无认证仅回环; `HOTSPOT_ALLOW_LAN=1` 才可绑非回环) | run.py docstring |
| 前端 | React 18 + Vite, dev :8898; 生产 vite build | 命令见 EXECUTION_GUIDE §6 |
| 当前运行状态 | **后端/前端均未运行** (8000/8898 无监听, 无 uvicorn/vite 进程) — 盘点时无活跃写入者 | `lsof -nP -iTCP:8000 -iTCP:8898` 空 |
| v0.8.3 | **未实现** — 仅 3 份未跟踪方案文档; 版本源零痕迹 | `git log 943a31d --not 382a578` 14 commits 全部为 v0.8.2 收尾 |

## 2. 数据根与写入者 (T00 核心交付)

| 根 | 路径 | 实况 | 权威写入者 (代码落点) |
|---|---|---|---|
| **HOT 库** | `backend/hotspot.db` (28MB, 最后写入 09-05 19:39) | 7223 hotspots / 53 trigger_tickets (全部 pending) / 58 skill_runs / 321 agent_runs / llm_secrets 1 / encryption_keys 1 / audit_log 93 | `repository/db.py get_connection` 单一连接源; 写入方: collection_service / catchup / observability_records (audit) / skill_runner (runs) / agent_bridge (agent_runs) / trigger_gate (tickets) / settings repo / secrets_service |
| **WARM 库** | `backend/hotspot-warm.db` (**818MB**, 09-04 17:13) | 数据量主体 (feed/事件等历史) | 经 ATTACH 后 `warm.` alias 写; T16 迁移的主要搬运对象 |
| **COLD 库** | `backend/hotspot-cold.db` (28KB) | 接近空 | Phase 7 后基本冻结 |
| **备份** | `backend/backups/` | 最近 full `hotspot-20260829_200000.db` + knowledge.zip; `incremental/` 目录; 3 个 INTEGRITY_OK 标记 | `services/backup_service.py` (04:30 增量 / 周日 full) + backup_verify (周一 02:00, v0.8.2 A4)。⚠️ full 已 7 天旧 — 新鲜度缺口已录已知问题 F6 |
| **Wiki 单根** | `llm-wiki-2.0/` (content/ concepts/ digest/ inbox/ graph.json _MAP.md) | `HOTSPOT_WIKI_ROOT` env 未设, 走默认解析 | `wiki_fs/paths.py wiki_root()` 单一源; 写入方: knowledge_watcher (双向同步) / skill_runner C/D 管线 (wiki_path) / obsidian 工具链 |
| **知识目录别名** | `KNOWLEDGE_DIR = wiki_root()` (P4 双根合并后同 Wiki 单根) | 无独立目录 | `services/knowledge_sync.py:46` |
| **日志** | `backend/logs/` (app.log 按 log_max_bytes 轮转; 另有历史 run_c4b.out 等手工输出) | | `logging_config.py` (loguru; stdlib logging 全仓不可见 — 红线) |
| **data/ 旧产物** | `data/`: **hotspot.db 0 字节 (08-25, 诱饵勿用)**; compliance/ export/ dsh/ stix/ migrations/(08-24 旧产物) retirement_baseline.json | 非当前写路径 (Phase 7 时代遗留) | 无活跃写入者 |
| **dsh runtime** | settings KV: `dsh.command/endpoint/autostart` (HOT settings 表); 会话工作区 `codegarden/<project>/` | 当前未运行 | `services/dsh/supervisor.py` + `runtime.py resolve_mode` 三态 (not_configured→mock→subprocess) |
| **pi** | 外部 CLI `~/.pi/` (0.84.4, 底层 provider 走用户配置); bridge 走 `agent_bridge.py` 子进程协议 | 未常驻 | `services/agent_bridge.py` (run_agent_task) |
| **密钥材料** | HOT 库 `llm_secrets`(1 行)/`encryption_keys`(1 行) + macOS Keychain `hotspot-*` 前缀条目 | **本 T00 未读取任何密钥内容** | `services/secrets_service.py` (keyring 后缀隔离 + Fernet) |

写入者全局约束: SQLite 连接线程亲和 (asyncio.to_thread 内构造) / stdlib logging 不可见 (一律 loguru) — 均为既有红线。

## 3. 架构与功能清单 (引用单一真源)

- 计数 (2026-09-05 实测, `generate_meta --check` 4/4): **73 routers** (core 45 白名单 + 扩展域 28) / **108 services** / **52 jobs** / **14 collectors**。
  注意: `jobs/__init__.py __all__` 仅 34 个 re-export 名, 其余 job 经模块直连注册 — 以 scheduler.py `add_job` AST 计数 52 为准 (test_feature_gates 锁定)。
- **13 feature gates**: 12 开 (codegarden / codegarden_phase2b / sync / tech_stack / security_graph / secnews / crm / dsh / info_filter / skill_registry / trigger_gate / user_skills), 1 关 (mcp — 只管 /api/mcp/* 调试路由; server 本体 `config.feature_mcp=True` 独立开关)。路由/job 注册是启动期快照, 动态读数 5s TTL 热重载 (v0.8.2 A2)。
- **20 内置 Skill**: 注册表 `skill_registry.BUILTIN` len=20, 实测吻合; 完整 ID 与 v1.0 去向 = EXECUTION_GUIDE §5 迁移责任表 (20/20), 本基线不重复罗列。
- 运行时弹性 (v0.8.1): CircuitBreaker + ProviderHealth + 场景权重 + `/api/observability/llm/health`; 全局限流 `utils/concurrency.py` (v0.8.2 A1)。
- 功能保留/适配/后置裁定: 以 DEVELOPMENT_PLAN §2.1 冲突裁决表为准; 20 Skill 逐项去向见 EXECUTION_GUIDE §5 — 本基线不复制、不改动。

## 4. 已知断链与风险 (基线必须诚实记录的部分)

1. **触发队列无生产消费泵** (旧审查 F01, 已复核属实): TriggerWorker 生产零实例化, `POST /api/skill-registry/{id}/run` 仅入队; **53 条 pending 票据无任何进程消费** — v1.0 T09 的核心对象, 迁移时必须 `legacy_hold` 不得自动执行。
2. **pi 解析残余假阳性** (F05, 已复核属实): `_parse_jsonl_events` 的 `last_json_text` 兜底 + 中间文本不回滚 — session-only 流 / 中间文本后 error 终态仍判成功 (T10 修复对象)。
3. **测试曾写真实 HOT 库** (F13, 实锤): agent_runs id=315..321 为模拟记录 (09-05 11:39 UTC), 混在 321 条历史中; T01 隔离修复前**不得扩大测试**; 旧记录保留不删。
4. **单源抓取持久化失败语义** (F02, 待核验): 旧审查指控本 T00 未重放验证。
5. v0.8.2 收尾审查 F1-F7 (饱和排队尾延迟 / CI 从未真跑 / core-only 漂移 / restore 无测试 / A1×A2 交互 / 备份新鲜度 / Cache-Control 体感) — 见 PROJECT.md 已知问题, 其中 F4/F6 与 T02 直接相关。
6. WARM 818MB 是 T02 备份演练与 T16 迁移的体量基准; COLD 接近空 — 三库"混用"现状以实际 alias 写路径核对为准 (T03/T16)。

## 5. 固定样本漏洞工作故事 (第一条要做的真实工作)

> 样本数据将造入 T01 隔离环境 (临时库/Wiki), **不进真实库**; 编号为示例, 非真实 CVE。

**样本**: 虚构 CVE-2026-31337「某 SSL VPN 网关任意文件读取 (认证前)」, 官方公告 + 2 家转载 + 1 篇分析文。

1. 导入授权虚拟资产快照 A (CSV: 3 台网关, 其中 1 台版本在受影响区间)。
2. 抓取公告原文存 evidence (hash 可溯源) → 情报区显示"收录理由"; 点击研判 → 建事项 Case-A (目标: 判定客户资产是否受影响)。
3. 判断: 命中资产 1 台受影响、1 台版本未知 → **必须显示 unknown**, 不许"缺版本→不受影响"; dsh 产出带原文引用的 claim。
4. 行动: pi 按授权核对资料生成排查材料 (影响矩阵 + 检查清单 hash) → "材料已生成" ≠ "排查已完成"; 用户上传实际排查结果 → 独立验收。
5. 验收通过 → 发布经验 K1 (前提: 版本区间/认证前/该产品线), 绑定复查时间。
6. 事项 B: 同公告、不同版本资产 → 召回 K1 并**指出条件差异**, 不照抄结论; 若 K1 被反证推翻 → disputed + 提醒活跃事项。

完成条件 (与 PRD AC 对齐): 每个关键结论可打开原文出处; unknown 显式呈现; 材料生成与业务验收分离; 第二次任务复用带条件判断。这就是 v1.0 第一条要做的真实工作 — 首条完整路径 = SK-02/SK-03 (T05-T13)。

## 6. T00 通过证据自查

- [x] APP_VERSION (0.8.2) 与实际启动入口 (run.py→uvicorn:8000) 明确
- [x] 每个数据根及写入者可定位 (§2 表, 含诱饵文件与遗留目录说明)
- [x] 未把 v0.8.3 标已实现 (§1: 仅未跟踪文档, 版本源零痕迹)
- [x] 第一条真实工作及完成条件可指出 (§5 样本故事)
- [x] 全程只读: 未跑测试、未出网、未写库/Wiki、未读密钥内容
