# PROGRESS.md — 执行进度台账（仅活跃段）

> **当前阶段 (2026-09-10)**: v0.8.5 已合入 main 打本地 tag；审查修复批 F1-F11 + 全仓整洁批（`fix/v085-review-p0`）、**信源节奏/存活修正批**与**代理内置批（DEV-0163/0164）**完成待评审合入（分支 `fix/source-cadence-health`）。生产后端已按新代码重启（30 分钟节奏 / 招标 6 小时 / 31 源退役 / 存活与有用分离 / 代理默认内置开启 + 失效自动切直连）。开放项: 15 个观察源 per-source 排查 / B1 信号观察窗调优 / 生产 warm 库 853 行迁移（待授权+备份前置）/ B0-B7 业务闭环整改。
> 接手顺序: 根 `AGENTS.md` → `PROJECT.md` → 本文件活跃段。历史完整段见 `docs/progress-archive/`，docs/ 全景见 `docs/README.md`。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [v0.5-baseline.md](docs/progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [v0.5-execution.md](docs/progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 |
| **v0.6 records** | 2026-08-24/26 | [v0.6-records.md](docs/progress-archive/v0.6-records.md) (856 行) | 里程碑验收 + Phase 7 数据迁移 + P0-P3 治理全记录 |
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [v0.7-records.md](docs/progress-archive/v0.7-records.md) | SettingsHub V2 + 观测批次 ①-⑨ + v0.6.3 性能/双根合并 |
| **v1.0 轨道** | 2026-09-03 ~ 09-08 | [v1.0-track-records.md](docs/progress-archive/v1.0-track-records.md) (1320 行) | T00-T19 / C01-C14 / v1.0.1 融合方案（路线已被 v0.8.5 反向收敛取代）+ REVIEW 20 项阻断 B0-B7 整改路径 |

> 原 v0.5 时代的「规格与文档 / 5 文件用法」小节随 v0.5 spec 一并归档（`docs/archived/2026-09-09-sweep/v0.5_refactor_plan/`），不再维护。

## 当前活跃段 (2026-09-03 起)

### 2026-09-13 七项决策落地: 收缩批全清 + CRM 删除 + 三份设计稿 — DEV-0204~0212

- **裁决** (owner, 7 项): ①P1-0 = dsh 设计边界控制 + pi 执行 (设计稿待复议) ②继续收缩解耦 ③前缀化走 accessor 模式 ④CodeGarden 转型安全实践域 (行动侧, 开源工具实践, 选题提取自资讯流) + **CRM 整体删除** ⑤prompts 命名不改 ⑥mitre 数据做知识梳理 (场景讨论稿) ⑦push 维持禁令 (已做本地 bundle)。
- **收缩批交付** (全部守卫验证): **R2** v1_admission 四表 + collection 四表补 repo (豁免 50→**42**); **R3** knowledge_api/case_api/sources/secrets 四大文件拆 ≤150 聚合层 (豁免 36→**32**, URL 等价性程序化证明 50 路由 AST 全等); **R4** skill_registry⇄skill_runner 环解开 (execute 改 runner 必填注入, 生产调用方实为 0), **环白名单归零** — 全 services import 图零环; **accessor** knowledge_items 裸读 43 处/21 文件→**0** (含 maintenance 参数化/wiki_stats 模块常量运行时化/t5 PRAGMA schema 化); **SSE** sentinel 4 页迁 realtime.ts (节流窗口逐字对照, DEV-0167 纪律 cadence 套件验证), useSSE 直调仅剩底座。
- **删除批**: CRM 全域 (后端 10 文件+前端 9 文件+gate+settings 入口+security-cockpit 设计稿 2497 行, -5040 行), 迁移 116 幂等 drop 三表; 实际构成以 grep 引用图谱为准 (crm 组件实为 7 文件)。
- **设计稿** (待复议): `docs/DESIGN_P10_EXECUTOR_2026-09-13.md` (dsh 生成 ExecutionPlan→人审批默认拒→代码 enforce 四层防线→pi 边界内执行, 分期 0a 人工回执止血→0d 加固) / `docs/DESIGN_CODEGARDEN_PRACTICE_2026-09-13.md` (信号提取→四阶段立项→产物沉淀闭环, 复用 from-knowledge 桥, phase2b 列删除候选) / `docs/DISCUSSION_MITRE_KNOWLEDGE_2026-09-13.md` (M1 图谱点火推荐首发, 复活 D18 死视图; M5 与 CodeGarden 实践域合流)。各含 4 个开放问题待 owner 确认。
- **验证** (实现与验证分离): 全量 pytest **4589/9sk/0** (-21 为 CRM 测试删除) / vitest **496** / tsc 0 / build OK / meta --check 0 MISMATCH (**83 routers / 141 services / 116 migrations**) / 审计 **P0=0 P1=0** P2×6 记录性 (报告 .ua/tmp/shrink-batch-code-audit-report.md; R3 AST 全量 50 路由全等、R2 逐字比对、CRM 残留 grep 0 独立复核)。
- **遗留**: 设计稿三项待复议后实施 (P1-0a 止血可先行); R2 豁免 42 条剩余 (maintenance 动态 SQL/trigger_gate/skill_runner 等随触碰收缩); R3 豁免 32 随手收缩; scripts/db_diet.py 参数化 DELETE 在守卫外 (retention 台账路径); 文档历史 CRM/旧数字引用留 spec 修订批。

### 2026-09-13 解耦工程 P0-0 + 五批全落地: 止血/API 收口/repo 收敛/解环拆上帝服务/前端域客户端 — DEV-0191~0203

- **执行** (6 commits `a45e22c..184b592` on main, 未 push, 方案 `docs/FEATURE_DECOMPOSITION_2026-09-12.md` 最终版): **P0-0** (`60acba0`) 止血十项 — dsh 命令白名单三层 enforce + token 鉴权(默认关) + 回环 guard 共用 + vite host 127.0.0.1 + kl 路径穿越封堵 + **备份链根治** (WAL 帧累积 checksum/v2 格式/三库全量/原子恢复, 生产端到端 checker 27/27 integrity ok) + 证据收据三类 entity_type 白名单 (恒 pending→committed) + crypto 参数修正 + 明文 key 清扫(迁移 115) + 错误契约 8 码扁平 envelope (前端 10 组件同步)。**Batch 2** (`7a2b8fa`) api/knowledge.py 711→39 + api 层 52 处直连 SQL 清零 + R3 守卫。**Batch 3** (`756e569`) v1 五表补 repo + R2 守卫 (54 表豁免冻结增量) + knowledge_items_table() 单一真相源。**Batch 4** (`e257baa`) action⇄run 解环 (run_orchestrator) + R4 守卫 (Tarjan) + knowledge_service 974→150 / collection_service 1071→296 facade 拆分。**Batch 5** (`184b592`) 5 前端域客户端 + ~85 组件/hook 迁移 (**裸 fetch 280→11, 网络调用归零**) + SSE 失效统一 (realtime.ts, v1 迁移/sentinel 登记保留)。
- **守卫族** (4 个新机器断言, 规则机器化): R1 分层 (禁 services→api) / R3 api 零 SQL+行数豁免 36 / R2 写路径唯一 (表豁免 54 收缩制) / R4 零环 (白名单 1: skill_registry⇄skill_runner)。架构数字 85→86 routers / 127→141 services。
- **验证** (每批双独立 agent, 实现与验证分离): 全量 pytest **4600/9sk/0 失败** (基线 4466→+134 用例) / vitest **509** / tsc 0 / build OK / meta --check OK / 每批 code-reviewer 审计 **P0=0** (P1 累计 8 条全修: 备份 checksum 撕裂帧/恢复原子性/守卫绕过面×2/前端信封同步等); 报告 `.ua/tmp/{p0,batch2..5}-code-audit-report.md`。
- **遗留** (豁免收缩路线, 非阻断, 见方案 §4): R3 行数豁免 36 文件 (knowledge_api/case_api/sources/secrets 为目标) / R2 表豁免 54 条 (maintenance 动态 SQL 文件级/v1_admission 四表) / ai_hub write_back 外移待授权 / 裸读 knowledge_items ~20 文件 / sentinel SSE 5 处迁移 / P1-0 执行器 (产品决策待 owner)。

### 2026-09-12 解耦 Batch 1: SSE 事件总线下沉 + 分层守卫上线 — DEV-0191

- **背景**: owner 指令"熟悉仓库 + 功能拆解 + 关键功能独立 API + 解耦 (高内聚低耦合)"。盘点结论: 85 router 已按功能分文件 (`api/_registry.py`), "独立 API"骨架已在; 真正的债是四类耦合 — 反向依赖 8 处 / 层穿透 (api 直连 SQL 50 + services 绕 repo 239) / 上帝模块 (`api/knowledge.py` 711 行、`collection_service` 1071 行等) / `action↔run` 环。完整方案 = `docs/FEATURE_DECOMPOSITION_2026-09-12.md` (13 域拆解总表 + R1~R6 机械规则 + 五批路线图, Batch 2~5 待裁决)。
- **交付** (Batch 1, 零行为变更): 事件总线 `publish_event` 自 `api/events.py` 下沉 `backend/core/events.py`, **8 处 services/scheduler→api 反向依赖清零**; `api/events.py` 只留 SSE 端点 (C11 R18 outbox 重放不变); 新增 `backend/tests/test_layering_guard.py` AST 守卫 (services/scheduler/collectors/repository 四层禁 import backend.api — 分层规则首次机器化)。
- **验证**: 定向 51 passed; 全量 **4468/9sk/0 失败** (main 基线 4466 + 守卫 2; 与上条 4488 差 = fix/source-cadence-health 分支 +31 用例未合 main); meta --check OK (85/127/57/13 不变); ruff 触碰 11 文件 0; `import backend.main` 冒烟 OK。
- **遗留**: Batch 2 (api/knowledge.py 拆分 + api 直连 SQL 清零) ~ Batch 5 (前端域客户端收敛) 待 owner 排期; 与第一性原理 P0-0 止血批建议 P0-0 先行 (方案 §5); ai_hub write_back 外移属红线需显式授权。

### 2026-09-12 工作台聚焦 P0 交付: 标讯剔除 + 内容相关性门禁/实践域兴趣体系 — DEV-0174~0176f

- **裁决** (owner, 方案文档 `docs/WORKBENCH_FOCUS_PRD_v1.0.md` §0): ①否决「安全研究/标讯跟踪双视角切换」②**剔除工作台标讯功能** (取代初版 R2"维持现状": `/bid-alert` 路由+组件+壳菜单+Feed bid 档全删, 资讯流默认 `exclude_category=bid`; 后端 bid_alert API 与采集器暂保留, 停采待裁决) ③立项内容相关性门禁/实践域兴趣体系。**悬置裁决关闭**: v1.0 T00 "标注集 60-80" = 60 本地 admission (不入仓) + 20 入仓评测语料 (`backend/tests/fixtures/practice_domain_eval.json`)。
- **交付** (7+1 commits `1546dfe..a31d31d`+收尾): T0.0 标讯剔除 / T0.1 实践域词表 8 域 (`auto_classifier` 二级打标, 纯规则零 schema) / T0.2 评测语料 20 条+回归护栏脚本 / T0.3 `GET/PATCH /api/settings/interests` (kv+audit) + 设置页"我的方向"卡片 / T0.4 资讯流即时打标+兴趣域页内置顶 (降权不删, 游标时序保护) + 首页/FeedCard 命中徽标 / T0.5 SK-01 聚合分区 (后端; 前端渲染随 P1 动线, SK-01 无活消费面)。
- **验证** (实现与验证分离): 全量 pytest **4488/9skipped 0 失败** (+31 新用例) / vitest **495** / tsc 0 / build OK / meta --check OK / ruff 触碰文件 0。**独立双门**: 功能验收隔离库真实后端走查 **A1-A10 全 PASS** (真实三库 0 句柄零写入); code-reviewer 审计 **P0=0 / P1=4 已修** (画像读取防御 / 卡片 i18n / 两处 PRD 口径如实化待 owner 追认) / P2=11 已认领去向。报告: `.ua/tmp/p0-{acceptance,code-audit}-report.md`。
- **遗留**: ①`/api/secnews/feed` (报纸风页) 打标与 SK-01 前端摘要卡随 **P1 动线批** ②词表无偏人评属 **P1 运营机制** (同源护栏 100% ≠ 真实准确率) ③预存漂移 (非本批): SK-01 admission 查询列与 097 schema 不符静默降级、全仓 4 个预存 ruff error、bid 采集仍在跑 (停采待裁决)。

### 2026-09-10 首页刷新自激循环根治 (同分支, dev server HMR 已生效) — DEV-0167

- **起因**: owner 报首页刷新频率过高、多次页面刷新与抓取, 要求前后端节奏一致 (选 30 分钟就 30 分钟, 手动刷新除外)。生产日志实测: 页面未打开时调度器严格 30 分钟一轮; **首页打开的 44 分钟里采集启动 88 次、前端 `POST /api/refresh` 172 次** (峰值单分钟 9 轮)。DEV-0163 改对了后端节奏, 但前端 SSE 回调对**任意**事件都在 3s 后调 `refresh()` = `POST /api/refresh` (同步跑完整采集) → 一轮结束发 `job_done`+`collect_done` → 再 POST → 无限自激。
- **落地** (4 文件, 后端零改动, 不碰并行会话在改的 `SentinelShell.tsx`): ①`useSSE` 新增 `types` 过滤 (lastId 仍对全部事件推进) ②`useHotspotData` 分离只读 `refetch()` 与触发采集的 `refresh()` ③首页只订阅 `collect_done`, SSE 路径改只读重拉 + 右栏 10s 节流, 错误重试/URL 导入也改只读, 「立即采集」是唯一手动采集入口, 页脚/空态「每 5 分钟」改读 `GET /api/settings/refresh-interval` ④判断页同样过滤 + 30s 节流。
- **验证**: 新增 7 回归; 全量 vitest 487/487 (基线 480+7); tsc 本批 0 错; build 通过。**活体**: IAB 打开新代码首页挂 fetch 探针 → curl 手动采集 → `collect_done` 后页面只做 1 次 `GET /api/hotspots` + 右栏 1 次, **`POST /api/refresh` 0 次**, 后端无新增轮次; 页脚实测"每 30 分钟自动采集"。
- **遗留**: ①既有 bug — 首页/判断页 `usePipeReloadOnSse()` 在 Provider 外调用拿到空 reload, 心跳条采集后不刷新 (修法要动 SentinelShell, 待并行会话收口后做) ②手动 POST 走 `run_once()` 直调不发 `job_done` 不写 `job_runs`, 观测面板少算手动轮 ③owner 已打开的旧标签页需手动刷新一次脱离旧回调。

### 2026-09-10 国际/国内源归属 + 代理优先 + 死代码清理 (同分支, 已上线生产) — DEV-0165

- **归属落库**: migration 110 `crawler_sources.network_zone` (人工核定 6 国际主机: github.com / news.ycombinator.com / hnrss.org / thehackernews.com / hackread.com / schneier.com; 其余含 Cloudflare 托管的 4hou.com 均 domestic)。`prefer_proxy()` 以注册表为单一事实源 (enabled=1, DB 异常安全降级直连优先, 60s TTL)。
- **代理优先接线**: fetchers aiohttp 步 + github collector 第 1 步 — 国际源第一跳直接走 ProxySession (代理失败自动切直连), **实测耗时 GitHub Trending 34.9s→2.1s / TheHackerNews 30s 超时→2.1s (34 条) / Star History 31.8s→1.4s**; 国内源路径零变化。`/health/v2` 逐源暴露 `network_zone`; 新脚本 `scripts/audit_network_paths.py` 输出 全源×zone×renderer×cadence×路径 清单 (国际 4 / 国内 52) + 采集器级路径注记。prefer_proxy 归属缓存 TTL **5s** (原 60s 因 owner 反馈改 zone 延迟过长下调; 表仅 ~101 行单查微秒级; 需即时的写路径调 `invalidate_international_hosts()`)。
- **死代码清理**: 删 `services/proxy_pool.py` (零调用) 及 crawl4ai_parser 兼容钩子; `data_cleaning.validate_url` 死代理分支 (引用不存在的 config.proxy_mode) — **修正误判**: bookmark_sync 多行导入在用 (grep 漏检), 恢复为薄委托 proxy_probe.is_reachable_sync (代理感知+SSRF 门); 删 USER_GUIDE 幽灵 job `proxy-health-probe`; services 127→126 (ARCHITECTURE + 3 份 AGENTS, generate_meta 写模式不落盘需手改)。
- **验证**: 新增 9 后端测试; ruff/generate_meta 全绿; 待全量套件确认 (本条落笔时在跑)。

### 2026-09-10 网络代理内置批 (同分支 `fix/source-cadence-health`, 已上线生产) — DEV-0164

- **起因**: DEV-0163 观察组里 TheHackerNews / GitHub Trending / Star History 经 A/B 实测为纯网络问题 (直连 15s 黑洞, 7897 代理 200/秒回)。owner 裁决: 代理做成**内置可选项、默认开启、代理失效能切回原始直连**。探索发现代理子系统**三重死亡**: mode=off + `backend.proxy_session` 裸导入不可用 (`base.ProxySession` 永远 None, 兜底层不存在) + ProxySession 无失败处理; 另 3 个预存坏点 (`/api/proxy/test` 必 500、PUT 静默无效、前端设置页契约错位 UI 不可用)。
- **落地**: ①`proxy_config.py` 新增 `builtin` 默认模式 (127.0.0.1:7897 + 内置国内绕行清单 `*.cn`+25 主站), env `HOTSPOT_PROXY_*` 真正接线 (env > json > 默认), mtime 缓存 + 原子写, **进程级熔断器** (连败 3 次 → 300s 全直连 → 半开探测, `HOTSPOT_PROXY_FAIL_THRESHOLD/OPEN_SECONDS` 可调) ②`proxy_session.py` 修导入 + `_ProxyAwareRequest` 请求级回退 (代理链路失败立刻摘 proxy 直连重试 + 回写熔断) + SSRF 门 ③`BackendSession` 代理失败同轮直连重试 (不再同代理打死) ④RSS 接代理通道 (`_fetch_rss_bytes` 走 ProxySession, feedparser 只解析字节) ⑤GitHub Trending 新版 markup 解析修复 (repo 锚点不再在 h1/h2 内) ⑥`api/proxy.py` 重写 (修 /test 必 500、PUT 合并语义、直连 vs 代理逐站对照、熔断快照与重置; load/save 改模块属性调用 — 按值导入曾使 test_api 的文件保护失灵, 全量套件每跑一次把生产配置写回 off, 实测踩坑已修) ⑦前端设置页重写 (契约对齐 + 内置模式 + 熔断态 + 闭合按钮 + 直连/代理并列表)。
- **验证**: 新增 36 后端测试 + 4 前端测试; ruff/tsc/vitest 480/480/vite build/generate_meta 全绿; 生产实测: 死代理演练每轮秒切直连且第 3 败熔断、`/api/proxy/test` 经代理 5/5 vs 直连 3/5、**生产抓取链 GitHub Trending 13 条 / TheHackerNews 32 条 / Star History 1 条恢复** (国内千里马不受影响)。后端 pid 84021。
- **待办**: 被墙源仍先烧直连超时 (代理优先名单留作增强); crawl4ai/Playwright 不走代理; 误熔断半开自愈; `services/proxy_pool.py` 死代码 + migration 053 `proxy_health_log` 与 `data_cleaning.py:114` 硬编码清理工单。

### 2026-09-10 信源存活率 + 刷新节奏修正批 (分支 `fix/source-cadence-health` off `fix/v085-review-p0`, 已上线生产, 待评审合入) — DEV-0163

- **起因**: 心跳 "18 存活 / 69 离线" (实况 87 启用 = 14 active + 73 离线, 62 个为招标源); 5 分钟全量轮询 87 源 7 天 3 万 run 里 2 万 failed/partial; owner 裁决: 准确/稳定优先时效拉到 30 分钟, 先诊断抓不到的原因、能修则修、修不好激进退役, "不是能抓到多少而是多少有用"。
- **第一性根因 (实测, 按影响排序)**: ①存活与有用混成一个数字 — 健康机只看过滤后 `item_count`, 招标源首页 40 条锚点 / 0 条安全相关被判死 (含当时"存活"的采招网) ②`crawl4ai_parser` 把 markdown 当 HTML 交给锚点解析器 → bid 链 crawl4ai 一旦成功必然 0 条 (存量 bug) ③GB2312 声明 + GBK 扩展字让 `resp.text()` 抛异常被吞成 "all failed" (全仓 4 处) ④RSS feedparser 机器人 UA 被 Cloudflare 拦 + 无超时 ⑤`main.py` 硬编码 300 压过 env、`cadence_seconds`/`last_fetch_at` 死列、死源不退出轮转与每日复活形成抖动 ⑥failure_rate 口径错配永远 green / revival 与 probe 各自为政 / census 词汇漂移。**否定的假设**: SSRF 连接器 IPv6 乱序拖死直连 (aiohttp 3.14 happy-eyeballs, 未改 `url_safety`)。
- **落地**: T1 节奏 (config 1800 + 持久化 GET/POST + 启动回读; cadence 单一闸口 loader/`get_schedulable`; migration 109 全部 1800 / bid 21600; `url_full_check` 900) · T2 抓取链四修 + `SourceResult.raw_count` 存活/有用分离 (健康机/crawler_runs.fetched/source_stats.produced 走存活口径, accepted/total_items 走有用口径) · T2.3 退役 31 (备份 manifest `_drill/20260910_060238`, 改前状态 `reports/retired_sources_*.json` 可 `--revert`), enabled 87→56, 28 源经生产链实测已恢复 (电力招标网当场出 2 条安全招标), 15 源观察 · T3 failure_rate 双口径 + revival→Phase 3 grace 桥接 + `_check_url` 委托 prober SSRF 门 + census 词汇 · T4 `audit_source_value.py` 有用性排行 (133 源 / 18 有产出 / 37 低价值)。
- **新脚本**: `scripts/audit_dead_source_triage.py` (四层探测, 只读) / `scripts/check_source_fetch.py` (生产链实测, 只读) / `scripts/cleanup_retire_unfixable_sources.py` (dry-run 默认, 备份前置, 可 revert) / `scripts/audit_source_value.py`; 产物在 `reports/` (已 gitignore)。
- **验证**: pytest **4382 passed / 9 skipped / 0 failed** (+50 新测试 0 回归) · ruff 触碰文件 0 错 · generate_meta --check OK (58/14/85/127 不变) · 生产链复测 74 离线源 zero 67→46 / alive 6→27 · 后端重启 pid 59585 `/api/health collect_interval_seconds=1800`, 日志 `collect_all every 1800s`。
- **待办**: 15 观察源 per-source (SPA 薄页 / HackRead 换 feed / 安全内参改 RSS URL / TheHackerNews 慢 feed / 36氪 WAF / GitHub 抖动); Phase 3 仍 dead 的 5 个已恢复 bid 源走 03:30 probe 漏斗; 上游 crawl4ai `_crawl_web line 778` 重定向链 bug; 预存 `_write_fingerprints: no such table warm.hotspots` 单独工单; 前端设置页接 GET refresh-interval。**编号说明**: 下条 v0.8.5 记录引用的 `DEV-0162` 在 DEV_LOG 中不存在 (悬空), 本批按 max+1 使用 DEV-0163。

### 2026-09-09 审查修复批 F1-F11 + 全仓整洁批 (分支 `fix/v085-review-p0`, 待评审合入)

- **卡顿六因修复** (根因=采集管线稳态资源, 非 v0.8.5 前端): F4 门禁前 URL 预去重 (重复 item 不再每轮重付全量门禁) / F2 crawl4ai 连续超时指数退避 (300s×2^(n-1) 封顶 1800s) / F3 日志降噪 (实测 90s 窗口 2.2 万条) / F1 pipeline_stats 同步查询入 to_thread / F5 `HOTSPOT_DISABLE_SCHEDULER=1` dev 并行禁调度 / F6 compounding 30s TTL 缓存。
- **预存回归修复** (v1.0.1 融合带入, main 树复现): F11 unified_search 默认 sources 契约 + warm 限定名自适应 — **上条 D4 记录的 32 个 search/fts "pre-existing 基线" 已清零** (4285+32 → 4329 全绿) / F10 job 计数测试回写 55→58。
- **一致性漂移修正** (F7-F9): spec 路由算术双计 (85+11=96 → 85 总量含 v1 前缀 7 模块) + services 126→127 + ACCEPTANCE V1Prototype 措辞 + .gitignore runtime/upstreams 整目录。
- **整洁批**: docs 49 项归档 `archived/2026-09-09-sweep/` (git mv 全 100% rename) + 活跃指针修正 10 文件 + 新增 `docs/README.md` 导读; 磁盘垃圾 272MB (backend/logs / 杂散 DB / archify 截图); AGENTS.md 19.1→13.6KB; PROGRESS 本番规整 (v1.0 轨道 1315 行切出归档, 本条为新活跃头)。
- 验证: pytest 4329/0 · ruff 触碰文件 0 错 · generate_meta --check 过。
- **Mimosa 首次密封深扫贯通** (scan `scan-2026-09-09T14-26-59.592Z-434b9a445258`, seal sha256:3755…0e33, coverage=partial/inconclusive): 378 findings (HIGH 246 其中 250 条属 vendored dsh 上游)。生产路径响应批 `1797b47`+`a62acb5`+`63adec7`: ①真阳性 skill_runner wiki 写任意路径 → wiki root 包含性收口 ②假阳性源头措辞修正 (playbook ast 解释器自述/webdav 示例占位) ③dump_schema PRAGMA 拼接保持原状 (标识符来自自家 DB 自省; 两轮参数化重写被写入门误拦, 记人工验证接受风险) ④依赖通告 2 包命中但包名未随密封产物序列化, 待有 Semgrep 的复扫定位。

### 2026-09-08 v0.8.5 — 反向收敛: 三层 Sentinel 唯一壳 + v1.0 能力区块 (demo 评审通过, tag v0.8.5)

- [x] 用户裁决: v1.0.1 (C09-C13) 删三层路由换 v1 四入口的路线方向错误; **恢复 v0.8 Sentinel 为唯一壳**, v1.0 九对象/三类 receipt 降级为嵌入三层的能力区块。第一性依据: 复利的前提是日活, 日活的前提是顺手。上一条 v1.0.1 融合记录的方向正确、粒度不足, 其执行入口角色由 [v0.8.5 方案](docs/v0.8.5/V0.8.5_PLAN.md) 接续 (该文档已挂 superseded 横幅)。
- [x] 阶段一 spec: 路由表 §5 / 三层接口消费表 §6 / 实现验证分离 (五类独立 agent) / 方向固化机制 / 飞轮一等验收 (点火 D1 + 自动召回 D3)。
- [x] 阶段二 demo (分支 `feat/v0.8.5-demo` 10 commits, merge `a92effe`): 三层路由恢复 (SentinelLayout) + v1 四入口重定向透传 query + `/cases/:caseId` 深链 + `/knowledge/v1` + SignalPanel/CaseQueuePanel/ExecOverviewPanel 三区块 + CaseDetail 提取 + 守卫反转 `v085_route_shell.test.tsx` + 版本 0.8.5 + `V1SentinelShell` 物理删除。
- [x] 独立验证四门: FactCheck 9/9 · G1 codegen 0 drift · G2 端点 parity 74/74 · G3 黄金走查 13 PASS/1 DEGRADED/0 FAIL · code-review APPROVE · 视觉走查三层/深链/390 (judge 工具章程不含 web UI, 由主会话执行)。**独立验证战果: 抓到 `/api/skill-registry/v1` 被 legacy 参数路由运行时遮蔽 404 (openapi 静态门测不出, main 即坏), 已修。**
- [x] 收尾: tag `v0.8.5` (本地) + CHANGELOG 段 + 本条留痕。已知边界 (spec §9 明示 demo 不主张): 真实源信号供给 (B1) / dsh 真实出稿 (B2) — 分别是 D1/D2 的验收项; **B0-B7 前置阻断仍有效**, 排入 D1-D4 对应批次。
- [ ] **D1 (已开工, 开发项全部落地, 仅剩观察窗)**: **点火已贯通** — `v1_ingest_bridge.py` 编排 T06/T07/T05 (RSS→SourcePipeline→准入→v1_materials+v1_signals), job `v1_signal_intake_tick` 300s (默认 security:SecWiki), 实弹 10→10→0 失败 (`7c8f990`/`92042f4`)。**D1.2 立项携带证据**: migration 108 `v1_case_materials` + create_case 自动绑定 + aggregate `evidence_materials` + CaseDetail 证据区块 (`4217cd2`)。**D1.3 Subject 抽屉**: signals API +subject_id 过滤 + SignalPanel 抽屉下钻 (`4217cd2`)。仅剩: 准入规则观察窗 (job 自动积累 admission_log, 数日后调优, 无代码)。
- [ ] **D2 (已完成, `ee2228c`)**: 端口固定 (`npm run dev:demo`=8898→8000 固定对; 修 dev_environment.sh 代理 env 变量 bug); R09 artifact API 级 CAS (verify/accept/reject +expected_revision, 不符 409); CaseDetail 真实出稿按钮 (生成判断 SK-02 需证据+CVE 解析 / draft 发布 / 生成行动 SK-03 需 published 判断 §10.1, 失败如实报错); P2 修复 (aggregate 竞态守卫 + V1Prototype 死代码清理 698→330 行)。R05/R07 已在 C07 修好。
- [ ] **D3 (已完成, `d4664d9`)**: SK-05 自动召回 — `auto_recall_for_case` 已发布知识 × case 文本读时匹配 (CVE +5 / 关键词 +1 需 ≥2 分, 非 published 不参与, 候选带 reasons 诚实可解释); aggregate +recall_candidates; CaseDetail 召回区块 + 采用免手填 (case 页发起自动带 case_id)。**一等验收实弹**: 第二个同类 Case (无手动关联) 自动浮现 FastGate 处置手册, API 采用 → 回执 id=3 (total=3, adopted=3)。
- [ ] **D4 (已完成, `410c2e4`)**: 路由对账 (ROUTE_REGISTRY v0.8.5 重写); 复利卡诚实计数 (aggregate `reuse_summary`, adoption 真实回执, 不做无基线估算); **验收矩阵 `docs/v0.8.5/ACCEPTANCE.md`** (一致性门/§13/D1-D3 逐条对真实证据); legacy 对账 (dev mapping=0, 生产 853 行迁移需授权+备份前置)。后端全量回归 4285 passed (32 failed=pre-existing search/fts 基线)。
- **关联记录**: DEV-0162。方向固化: 改方向必须显式重写 `v085_route_shell.test.tsx` + 撤 spec 横幅, 不允许静默漂移。
