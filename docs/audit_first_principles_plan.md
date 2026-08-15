# hotspot 代码仓库审计与改进方案

> 基于第一性原理的完备性分析 + 批判性审计 + 业务/操作流清晰度审查
> 审计日期：2026-08-15 · 审计方式：源码逐行核对 + 线上库 `backend/hotspot.db` 直查 + 文档对照
> 结论：**本方案只输出分析与改进计划，不修改任何代码**

---

## 0. 执行摘要

hotspot 是一个"信息 → 知识 → 行动"的单人本地工作站，代码规模庞大（后端 55 个 API 文件 / 310+ 路由、81 个 service、36 个调度 job、59 个迁移；前端 200+ 组件；知识库 4,143 个条目），工程完备度不低。但用第一性原理审视**实际数据流动**后发现：

**系统"造了很多管子，但水只流了前四分之一"。**

核心证据（全部为数据库实测）：

| 价值链环节 | 数据现状 |
|---|---|
| 采集（SecNews） | ✅ 953 hotspots，最近每天 200+ 条，质量门禁 3,687,968 条日志在跑 |
| 收藏 → 知识条目 | ⚠️ favorites 仅 **4 条**；knowledge_items 中来自 secnews 的仅 **17 条**（89% 来自 bookmark 批量导入） |
| 知识分类/提炼 | ⚠️ 81–94% 条目的 domain/topic/type/difficulty/concepts 为 null |
| KL 生命周期推进 | ⚠️ 3,925 条（96%）卡在 `kl:link`，**`kl:publish` 恒为 0** |
| 内化（复习/注意力/笔记） | ❌ sm2_reviews=0、reading_states=0、attention_events=0、annotations=0 |
| 内容输出（日历/草稿/发布） | ❌ content_calendar=0、drafts=1、发布任务曾因 draft 缺失而失败 |
| 复利反馈（仪表盘/学习进度） | ❌ 4236 条规划动作全 pending；progress 全 0；仪表盘读进程内存计数器 |

**关键结论**：
1. **知识闭环在第 4 环（关联）之后整体断流**，第 5–7 环是"代码完备、数据从未流动"的死功能；
2. **KL 五阶段状态机是"字段推进器"而非"数据流转器"**——推进结果会被真相源（.md 文件）抹除，且 T4 因评分表为空而永久死锁；
3. **跨设备同步已实质停机 26 天**（master_key 未解锁），且知识库本身不在同步范围内；
4. **前端存在两套导航体系并存**（死代码 Sidebar vs 三层 LayerNav），多个页面（/skills /secrets /sync /knowledge）在主导航中不可达；
5. **CodeGarden 服务网格被 1,347 条自动发现噪音污染**（lsof 全量抓取，type=http/status=running 占 99.9%），拓扑图不可信。

### 0.1 最严重的 15 个问题（四份审计汇总排名）

| # | 问题 | 严重性 | 证据 |
|---|---|---|---|
| 1 | **跨轮去重系统性失效**：content_fingerprints FK 使新条目指纹首插必失败（实测）+ 去重窗口收缩为"本周" → 重复数据保证反复入库 | 🔴 架构 | collection_service.py:614-634 + migrations/043 |
| 2 | **KL 状态机被真相源抹除**：md 无 kl 字段，full_sync 批量重置 DB 状态；T4 死锁 → kl:publish 恒 0 | 🔴 架构 | knowledge_sync.py:141-143 + t4_structure_to_publish.py:9-10 |
| 3 | **`run_one_source` 名不副实**：单源调度实际采集整个分类 → 源级调度与健康归因全部失真；且绕过锁与缓存失效 | 🔴 架构 | collection_service.py:344-393 |
| 4 | **闭环第 5–7 环全是死代码**：sm2_reviews/reading_states/attention_events/annotations/chunks 5 张表 0 行 | 🔴 产品 | DB 实测 |
| 5 | **同步 26 天实质停机 + 知识库不在同步范围 + base 不跨端共享** | 🔴 数据 | sync_history 实测 + sync_service.py:254 |
| 6 | **Security Graph 富化管道 100% 失效**：job 查 hotspots 不存在的列每轮必崩；item_entities 无写入方（0 行）；858 节点 0 边 | 🔴 功能 | jobs.py:633-660 + DB 实测 |
| 7 | **任务队列死胡同 + 事件无 handler**：Playbook/事件/重启/上游同步全只插 knowledge_tasks，唯一消费者只处理 compile 类型；18 条 event_handler 永远 pending；cg_event_process_job 直接 mark_processed 无处理逻辑；Playbook 无沙箱无审计 | 🔴 安全/功能 | compiler.py + jobs.py:555-557 + knowledge_tasks 实测 |
| 8 | **前端断链 4 处**：深度阅读入口空白、/report?type= 被忽略、XLSX 导出 404、复利仪表盘仅测试引用 | 🟠 产品 | KnowledgeTabs.tsx:95 / ReportPage.tsx:25 / ExportSettings.tsx:29 |
| 9 | **导航分裂 + 死 Sidebar**：/skills /secrets /sync /knowledge 主导航不可达；死组件 6 个、死路由 4 条、死 hooks 5 个 | 🟠 产品 | App.tsx vs Sidebar.tsx（0 引用） |
| 10 | **服务网格 1,347 条噪音**：进程名当服务名，type=http+running 占 99.9% | 🟠 数据 | cg_services 实测 |
| 11 | **absence-as-deletion 误删面广**：单表读取异常→空 bundle→清空本地表；无"失败即中止"保护 | 🟠 数据 | sync_bundle.py:45-56 |
| 12 | **master_key 无恢复/轮换**：丢失=全部密文永久不可解；密钥明文持久化 + 启动自动解锁 | 🟠 安全 | crypto.py 全文件 |
| 13 | **Hard 门禁在 loose 模式也拒收 + 门禁崩溃=免检**：语义与文档矛盾 | 🟠 质量 | pipeline.py:150-194 |
| 14 | **瞬时网络失败永久隐藏条目**：unreachable 无复检路径 | 🟠 质量 | quality/jobs.py:63-72 |
| 15 | **配置/文档漂移**：7 项死配置；6 个 collector 未接线；quality_gates.md 说 9 道实际 11 道；settings 不持久化 | 🟡 债务 | config/__init__.py + collectors/__init__.py |

---

## 1. 第一性原理：系统的本质与最小必要价值链

### 1.1 系统本质（从 PRD 与代码提炼）

hotspot 的定位是"从信息到知识，再到知识复利的关键中转系统"（PRD A.5.1）。其最小必要价值链是：

```
信息进入 → 分类 → 提炼概念 → 关联 → 内化(复习/注意力) → 输出(摘要/内容/发布) → 复利反馈
   (采集)   (规则+LLM)  (concept)  (links)   (SM-2/行为)     (日历/草稿)      (仪表盘/SOUL)
```

### 1.2 五大子系统各自的完备性

| 子系统 | 价值链 | 完备度 | 一句话结论 |
|---|---|---|---|
| **SecNews 采集** | 源发现→抓取→解析→质量门禁→去重→入库→索引→推送 | ✅ ~90% | 最成熟的部分；但源健康（77/120 dead）与标讯产出（18 条/40 天）是硬伤 |
| **Knowledge** | 进入→分类→概念→关联→内化→输出→复利 | ⚠️ 前 4 环 60%，后 3 环 0% | 见 §2.1 逐环节表 |
| **CodeGarden** | 项目创建→规格→开发→部署→运维→复盘 | ⚠️ 骨架完整，数据污染 | 服务扫描产生 1,347 条垃圾数据；资源/依赖/事件全 0 |
| **Security Graph** | MITRE/CVE 同步→实体抽取→图谱→查询→合规 | ⚠️ 结构完整，联动缺失 | 858 实体存在，但与 knowledge 概念层不互通 |
| **MCP Server** | 工具暴露→外部 Agent 调用→副作用回写 | ⚠️ 9 工具注册，副作用链断 | add_annotation/update_knowledge_item 对应数据表为空 |

---

## 2. 第一性原理完备性逐环节分析

### 2.1 Knowledge 知识闭环（最核心，问题最集中）

| # | 环节 | 状态 | 证据 |
|---|---|---|---|
| ① | 信息进入（bookmark/cubox/archive → items/*.md） | ✅ 唯一完整链路 | `bookmark_sync.py:182`、`cubox_sync.py:140`、`history.py:132`；4,143 个 .md |
| ② | 分类（domain/topic/type/difficulty） | ⚠️ 代码在、数据没跑完 | `auto_classifier.py:306` 仅 API 手动 + 每日 02:30 消费（配额 100/天）；实测 81–94% 为 null |
| ③ | 提炼 concept | ⚠️ 只有占位概念 | `concept_linker.py:196` 按 tag 建占位 .md（正文"待补充"）；92% items concepts=[] |
| ④ | 关联（knowledge_links） | ⚠️ 数量有、质量存疑 | T2 写 24,354 条 links，但 concepts 空时按 tags 回退匹配（`t2_refine_to_link.py:154-164`），与 PRD"Agent 确认关联"语义相悖 |
| ⑤ | 内化（SM-2 复习/注意力） | ❌ 死代码 | sm2_reviews=0 / reading_states=0 / attention_events=0 / annotations=0；`create_review` 无任何调用点 |
| ⑥ | 输出（摘要/日历/发布） | ⚠️ weekly 摘要活着，其余死 | summaries/ 有 W29–W32；content_calendar=0、drafts=1；发布任务历史上因 draft 不存在失败（failed/error.md task-8） |
| ⑦ | 复利反馈（仪表盘/进度/SOUL） | ❌ 空转 | 复利仪表盘 avg_score=AVG(mastery) 全 0、trigger_health 读进程内存（重启清零）、top_concepts 空 |

### 2.2 KL 五阶段状态机专项（架构级问题）

**结论：KL 状态机是"字段 + 触发器"，但没有驱动任何数据流转，且会被真相源抹除。**

证据链：
1. **状态只存在于 DB 列，.md 真相源没有该字段**：`knowledge_sync.py:141-143` 的 md→DB 映射无 kl 字段，lifecycle 靠 fallback（compiled→generate / 否则 signal）；实测 500 样本 .md 中 **0 个含 kl: 字段**，DB 却显示 3,925 条 kl:link → 状态在 md 中无痕迹；
2. **full_sync 抹除状态机**：watchdog 对任何 .md 变更触发全目录 `full_sync_items_to_db`（`knowledge_watcher.py:208-228`），逐文件 upsert 时 `lifecycle=excluded.lifecycle`（`knowledge_repo.py:51`）→ md 无 lifecycle → 回退 signal/generate → DB 的 kl:link 被批量重置，T1/T2 再花数小时推回 → **状态机在"推进↔被抹除"间震荡**；
3. **T4 死锁**：`t4_structure_to_publish.py:9-10` 要求 ai_scores.score ≥ 8.0，而 **ai_scores 表 0 行**（评分依赖 llm_service，llm_secrets=0 → LLM 不可用 → 从不写分）→ **kl:publish 恒 0**；
4. **推进无副作用**：T1–T4 只 UPDATE lifecycle 列，不写 md、不生成内容、不触发摘要/发布——阶段变化不驱动任何业务动作，纯标签；
5. **规划动作与状态机脱钩**：planning_service 生成 4,236 条动作全 pending，动作完成不推进 lifecycle——两套空转系统。

### 2.3 SecNews 采集管道

| 环节 | 状态 | 证据 |
|---|---|---|
| 源发现/注册 | ⚠️ crawler-v2 strangler 进行中 | crawler_sources 130 条全 status='unknown'；采集仍由 8 个 collector 驱动 |
| 抓取 | ✅ 工作 | 19,535 次成功 collection_runs |
| 质量门禁 | ✅ 工作 | 13 门禁、3.7M 日志、478/953 条 quality_score<50（近半低质） |
| 去重 | ⚠️ 跨轮失效 | 单轮内 simhash 分桶可用，但跨轮指纹持久化因 FK 失败（见 G2），去重窗口收缩为"本周" → 系统性重复入库 |
| 源健康 | ⚠️ 严重 | DEV_LOG 自述 120 源中 77 dead；标讯 40 天仅 18 条；三套健康体系互不同步 |
| URL 校验 | ⚠️ 疑未生效 | crawl_url_checks=0 行（url_full_check_job 每 5min 跑但无产出记录） |

### 2.4 CodeGarden

| 环节 | 状态 | 证据 |
|---|---|---|
| 项目管理（创建/规格/阶段） | ⚠️ 骨架可用 | cg_projects=11、activities=34 |
| 服务网格 M2 | ❌ 数据污染 | **cg_services=1,347，其中 type=http + status=running 占 1,346**；名称如 "com.docke"/"Video\x20"/"python3.1"——lsof 进程名被当作服务名，无去噪/去重 |
| 资源中枢 M3 | ❌ 空 | cg_resources=0（含端口保护/加密模板等 8 端点全部闲置） |
| 联动引擎 M4 | ❌ 空 | cg_dependencies=0、cg_events=0；Playbook 无数据 |
| 技术栈漂移 | ⚠️ 空转 | cg_drift_assessments 有 job，但无上游数据 |

### 2.5 Security Graph

| 环节 | 状态 | 证据 |
|---|---|---|
| MITRE/CVE 同步 | ⚠️ 结构在 | security_entities=858 |
| 实体抽取 | ⚠️ 弱 | 主要靠 enricher 规则 |
| 图谱查询/可视化 | ✅ 有 UI | SecurityGraph.tsx / SecurityTimeline.tsx |
| 与 knowledge 互通 | ❌ 缺失 | PRD A.3.2 明确要求统一 entity 命名空间，security 节点引用 knowledge concepts——未落地 |

### 2.6 MCP Server

- 9 个工具注册（search/get/list/add/remove/update + profile），PRD 宣称 13 个（4 个 agent 工具 score_item/enrich_concept/link_items/trigger_codegarden_drift 为 REST 适配端点，未入 MCP registry）；
- 写副作用链断裂：add_annotation → annotations 表 0 行；update_knowledge_item → 见 KL 状态机问题。

---

## 3. 批判性审计：缺失清单（按严重度分级）

### 3.1 🔴 架构级（先修）

| # | 缺失/问题 | 证据 |
|---|---|---|
| A1 | **KL 状态机被真相源抹除**：md 无 kl/lifecycle 字段，任何 full_sync 把 DB 重置回 signal/generate | knowledge_sync.py:141-143 + knowledge_repo.py:51 + 实测 0 个 md 含 kl 字段 |
| A2 | **T4 死锁 → kl:publish 恒 0**：ai_scores=0 行，评分依赖未配置的 LLM（llm_secrets=0） | t4_structure_to_publish.py:9-10 + DB 实测 |
| A3 | **闭环第 5–7 环全是死代码**：5 张核心表 0 行，前端对应模式打开即空 | sm2_reviews/reading_states/attention_events/annotations/chunks 全 0 |
| A4 | **双生命周期系统并存**：sag_service（signal/amplify/generate）与 kl_state_machine（kl:raw..publish）写同一 lifecycle 列，语义互不兼容 | sag_service.py:_STATE_ORDER vs kl_state_machine.py:TRANSITIONS + DB 混合值 |
| A5 | **watchdog 全目录 full_sync + 孤儿删除**：单文件改动触发 4,143 文件重扫，目录扫描期文件被删会误删 DB 行 | knowledge_watcher.py:208-228 |
| A6 | **导航体系分裂**：Sidebar（9 项，含 /skills /secrets /sync /knowledge）是**死代码**（无任何 import）；现行三层 LayerNav 中这些页面无入口 | grep 全前端：Sidebar 无引用；Header 只有设置齿轮 |
| A7 | **前端页面与后端 flag 脱钩**：ReviewMode 调 /api/reviews/due，但 feature_reviews 默认 False → 路由不注册 → 404 | config/__init__.py:81 + ReviewMode.tsx:101 |
| A8 | **服务网格扫描噪音**：lsof 全量进程名入库为服务，1,346/1,347 为 running+http | codegarden_service_service.py:204 默认 running + cg_services 实测 |

### 3.2 后端数据管道系统性缺陷（审计复核）

| # | 问题 | 证据 |
|---|---|---|
| G1 | **`run_one_source` 名不副实：单源调度实际采集整个分类**：方法只用 source_id 查分类后调 collector.collect()，而 collect() 内 `_load_sources_from_registry` 把 self.sources 重置为该分类全部源 → 源级调度器（60s tick）每轮重复抓全部分类，健康状态机把整类产出归因到单个源 | collection_service.py:344-393 + base.py:376-378 |
| G2 | **跨轮去重系统性失效（严重，已实测）**：`content_fingerprints.hotspot_id` 有 FK REFERENCES hotspots(id)（migrations/043），`_dedup_items` 在 upsert 之前插指纹 → 新条目 hotspot 行不存在 → INSERT OR IGNORE 抛 FK 错误被吞 → 指纹丢失；叠加去重窗口 D7 已改为"本周一 00:00 起"+limit 200 → **系统性跨周重复入库** | collection_service.py:614-634 + domain/enums.py:109-111 |
| G3 | **并发写无统一锁**：run_once 有 asyncio.Lock，但 run_one/run_one_source/catchup/源级调度 tick 全都不持锁；collector 对象是共享可变状态（self.sources 互相覆盖）；catchup `_lock` 从不 acquire | collection_service.py:107/115/278/344；catchup_service.py:60/131 |
| G4 | **Hard 门禁在 loose 模式下也拒绝**（与文档"loose=打 flag 仍入库"矛盾）+ **门禁崩溃=免检**（gate.check 抛异常转 passed=True） | pipeline.py:172-194 vs 文档；pipeline.py:150-160 |
| G5 | **catchup "追抓"窗口未实现**：since/until 只用于校验与日志，抓取仍是普通重采 → "回填历史资讯"是空头承诺 | catchup_service.py:260-266/387-399 |
| G6 | **瞬时网络失败永久隐藏条目**：url_check_status='unreachable' 被查询层过滤且无复检路径（unreachable 不在候选集合）→ 一次抖动=一条资讯永久消失 | quality/jobs.py:63-72 + hotspot_repo.py:263 |
| G7 | **三套源健康体系并存互不同步**：source_stats（3/6 阈值）、source_health_service（green/yellow/red）、crawler_sources 5 态机（3/5 阈值），同一源三处状态不一致且只升不降；collect_all 从不跳过 dead 源 | source_stats_repo.py:135-147 vs source_health_machine.py:20-21 |
| G8 | **位置化 ID + 全列覆盖 upsert**：id 由枚举下标生成，源顺序变化→同 URL 变新 ID 重复入库；内容漂移→同 ID 被不同 URL 覆盖（收藏/标签/注释按 id 关联指向被替换内容） | item_builder.py:137 + hotspot_repo.py:178-193 |
| G9 | **6 个 collector 未接线**：HN/Reddit/OpenBB/Telegram/GDELT/OSSInsight 完整实现但不在 CollectionService.collectors（仅 8 个注册）→ 周期采集永不执行 | collectors/__init__.py:3-8 vs collection_service.py:92-101 |
| G10 | **富化内容绕过质量门禁**：run_once 在门禁后 batch_enrich 改写 summary，不再过 ContentQualityGate；upsert 失败仅 logger.error 却记 SUCCESS 并 SSE 推"成功" | collection_service.py:152-168 |
| G11 | **7 项死配置**：collect_timeout_seconds / collect_single_source_timeout / quality_url_check_enabled / quality_url_check_interval_seconds / quality_reputation_interval_seconds / cache_ttl_seconds / cache_maxsize 定义零使用（cache.py 硬编码）；采集间隔设置不持久化（重启还原 300s） | config/__init__.py:39-64；api/settings.py:20-56 |
| G12 | **文档漂移**：quality_gates.md 声称 9 道门禁，实际 pipeline 11 道；quality/__init__.py 说 8 道；URL 校验抽样语义（10%→全量）漂移 | quality_gates.md vs pipeline.py:91-107 |

### 3.3 🟠 数据安全级（必须修）

| # | 缺失/问题 | 证据 |
|---|---|---|
| B1 | **自动同步 26 天停机**：sync_history 实测 7/20、8/3、8/10 连续 "master_key 未解锁" 失败，最后成功 7/24 | sync_history 表 + jobs.py:329-365 |
| B2 | **3-way merge 的 base 不跨端共享**：sync_states 是各机本地表，共同祖先前提不成立 → 双机分叉时 merge 不可预期 | sync_service.py:254, 377-388 |
| B3 | **absence-as-deletion 误删面广**：单表查询异常返回空表时，同轮 apply 清空本地 favorites/todos/skills/custom_sources/annotations；无"查询失败即中止"保护 | sync_bundle.py:45-56, 578-641 |
| B4 | **master_key 无恢复/轮换**：丢失=secrets+webdav 密码+远端 bundle 永久不可解密；crypto.py 无 rewrap/rotate API | crypto.py 全文件 |
| B5 | **冲突裁决是死功能**：POST /api/sync/conflicts/resolve 写 `_conflict_resolved`，sync_merge 从不读取 → 用户裁决无效 | sync.py:368 vs sync_merge.py 全文件 |
| B6 | **secrets 密文参与 merge 产生伪冲突**：Fernet 随机 IV 使同明文不同密文，全字段比较必然不等 → 每次同步 secrets 全冲突 | sync_bundle.py:40-42 vs sync_merge.py:207-239 |
| B7 | **sm2_reviews merge 语义反了**：due_at 早者胜会保留旧记录、覆盖新复习成果（幸而表空） | sync_merge.py:365-425 |

### 3.4 🟡 功能失效级（应当修）

| # | 缺失/问题 | 证据 |
|---|---|---|
| C1 | **复利仪表盘展示空转数据**：avg_score=AVG(mastery) 全 0、trigger_health 读进程内存（重启清零）、top_concepts 空 | kl_compounding_api.py:46-111 + kl_metrics.py:93 |
| C2 | **分类层断裂**：81–94% items 分类字段 null；规则消费速率（100/天）远低于摄入；compiled/lifecycle 双口径并存 | DB 实测 + compiler.py:309-327 |
| C3 | **学习任务队列 1976 failed / 12 done**：Agent 时代积压被批量判死；规则消费者按此速率需 41 天消化 | failed/task-1979.md reason="superseded" |
| C4 | **URL 全量校验无产出**：crawl_url_checks=0 行 | url_full_check_job + DB 实测 |
| C5 | **MCP 写副作用链断裂**：add_annotation 无数据、update_knowledge_item 受 A1 影响 | annotations=0 |
| C6 | **knowledge 与 security 图谱隔离**：同一概念在两套库重复，无互引 | security_entities=858 vs knowledge_concepts=96 |
| C7 | **.conflicts/ 35 个冲突文件无人处理**：只有列出 API，无 resolve 流程 | obsidian_service.py:29 |
| C8 | **8 个"running"孤儿 collection_runs**：watchdog 未清理（或刚产生） | collection_runs 实测 |
| C9 | **规划动作 4,236 条全 pending，无执行者** | planning_actions 实测 |
| C10 | **服务网格 API 暴露重启/日志/指标**：对本地任意进程有操作能力，无确认/无审计 | codegarden_ops.py M2 端点 |

### 3.5 任务队列死胡同（CodeGarden 联动层核心断裂）

**CodeGarden 的 Playbook 执行 / 事件处理 / 服务重启 / 上游同步，全部只是"往 `knowledge_tasks` 插一行"；全系统唯一消费者 `compiler.py` 只处理 `compile` 类型** → 实库 18 条 `event_handler` 类型任务永远 pending。

| # | 问题 | 证据 |
|---|---|---|
| D1 | **任务队列单消费者、单类型**：除 compile 外无任何消费者 | compiler.py 全文件 + knowledge_tasks 实测（event_handler 18 条 pending） |
| D2 | **Playbook 是"带 sudo 的任意 shell 蓝图"**：零执行、零沙箱、零审计、无确认——为将来预留 RCE 通道 | codegarden_ops.py playbooks 端点 + codegarden_orchestration_service.py |
| D3 | **Security Graph 富化管道 100% 失效**：`security_enrichment_job` 查询 hotspots 不存在的列，每轮必崩 | scheduler/jobs.py:633-660 + 实库报错 |
| D4 | **item_entities 表全库无写入方（0 行）** → cg_drift_assess / cve_sync 两个 job 永远空转 | item_entities 实测 + jobs.py:1259/1276 |
| D5 | **858 个 security 节点 0 条边**：图谱无连接 | security_entities=858、security_edges=0 实测 |
| D6 | **master_key 明文持久化 + 启动自动解锁**；导出接口把主密钥放 URL；30min TTL 名存实亡 | secrets_service.py:92-121,185-198；api/secrets.py:324 |
| D7 | **可观测性打点字段被日志格式丢弃**：`log_event` 的 extra 全丢，叠加无指标无告警 → 关键失败全部无声 | observability.py + logging_config.py:19-25 |
| D8 | **事件处理无 handler**：`cg_event_process_job` 把事件直接 `mark_processed(success=True)`（无任何处理逻辑），cg_events 实库 0 行、无自动事件源 | jobs.py:555-557 |
| D9 | **cost_monitor 全死**：`cost_monitor.py:183-197` 写 cg_events 坏列（与迁移 021 列定义不符必抛错被吞）+ 全库无调用方 | cost_monitor.py + migration 021 |
| D10 | **MCP agent 工具路径穿越**：`mcp_agent_tools.py:97` 的 concept_name 未校验可路径穿越写任意文件 | mcp_agent_tools.py:93-110 |
| D11 | **备份不完整 + 无恢复流程**：backup_service.py:35-43 仅 DB 快照，knowledge/ 源文件只靠 git；全库无 restore 流程 | backup_service.py + grep |
| D12 | **校验不一致 + 文档错误**：api/secrets.py:45 密码 min 8 vs crypto.py:35 min 12；RUNBOOK.md:57 查不存在的 apscheduler_jobs 表；migration 059 暴露 attention_score 从未进迁移 | api/secrets.py + RUNBOOK.md |
| D13 | **宣传与行为落差**：CodeGarden_PRD_v1.7.md:1616-1617 里程碑表承认 M5/M7-M12"待启动"，但 AGENTS.md 宣称 Phase 2b 全量实现 | PRD vs AGENTS.md |

### 3.6 前端功能失效清单（审计复核）

| # | 问题 | 证据 |
|---|---|---|
| E1 | **复利仪表盘 / KL 触发器 / KL 规划动作整套功能无 UI**：`KnowledgeCompoundingDashboard`（535 行）、`KnowledgePlanningPanel`（393 行）只被测试文件引用；文档承诺的入口 /knowledge 落空 | 组件仅 .test 引用；App.tsx:253 |
| E2 | **"深度阅读"入口双坏**：知识页 tab 指向无 :id 的 `/knowledge/deep-read`（路由要求 `deep-read/:id`）→ 内容区空白；判断层入口指向 `/knowledge/briefing` | KnowledgeTabs.tsx:95 vs App.tsx:261；JudgeLayerPage.tsx:27 |
| E3 | **4 条不可达死路由**：`/brief`、`/deep/:type/:id`、`/reviews` 及其背后的 useDigest/useAnnotations/useReviews/useRecommendations/NoteEditor 全部失效 → "标注"功能在实际 UI 中不存在 | App.tsx:269-271；ReviewPage/DeepReadView/BriefModeView 0 活引用 |
| E4 | **XLSX 导出按钮 404**：前端 window.open('/api/export/download')，后端 export.py 无该端点 | ExportSettings.tsx:29 |
| E5 | **`/report?type=weekly|monthly` 被忽略**：ReportPage 固定 useState('daily')，行动层报告入口全部落到日报 | ActionLayerPage.tsx:43-45 vs ReportPage.tsx:25 |
| E6 | **ScanMode lifecycle 筛选静默失效**：后端 list_items 不支持 lifecycle 参数且无客户端兜底 → 用户选择后列表不变；OutboxMode 排序参数被忽略 + limit=50 漏数据 | ScanMode.tsx:101；backend/api/knowledge.py:20-42 |
| E7 | **错误反馈体系分裂**：统一 Toast 仅 CatchupButton 消费；17+ 处 window.alert（SecretsPage 9 处）；ErrorBoundary 从未挂载 | Toast.tsx；ItemDetailDialog.tsx:149-156 |
| E8 | **主题状态双轨 + 首屏暗色闪烁（FOUC）**：SettingsPage 自建 localStorage 事件无人监听；index.css 默认暗色 vs App.tsx 默认亮色 | SettingsPage.tsx:36-51；index.css:46 |
| E9 | **三层 pipeline 数字造假**：各层计数硬编码 0（非本层数据），行动层"待复习/待整理"硬编码 0 → 跨层流转无真实数据支撑 | DataLayerPage.tsx:64-68；ActionLayerPage.tsx:381-382 |
| E10 | **hooks 竞态**：useHotspotData 翻页 >1 不 abort、useSearch 无 AbortController → 旧响应覆盖新结果 | useHotspotData.ts:84-121；useSearch.ts:54-83 |
| E11 | **组件腐化**：11 个组件超 300 行（OutboxMode 659/ReviewMode 657）；6 个死组件（TopBar/Sidebar/ErrorBoundary/WeeklyReportPage/AlertBadge/TagSelector）；77 处硬编码色 | 文件行数实测 + grep |
| E12 | **后端有 API 无 UI**：/api/codegarden/drift、/api/cve/sync、/api/llm/status、/api/kl/metrics 前端 0 引用 | grep 实证 |
| E13 | **热点无站内详情**：卡片仅外链新标签（AgihuntCard.tsx:96-108）；`/api/hotspots/{id}` 详情接口只被不可达的 DeepReadView 使用 → 热点详情、标注入口缺失 | AgihuntCard.tsx + hotspots.py:57 |
| E14 | **收藏→知识库是两跳流程**：收藏 → /data/history → import-from-history（HistoryPage.tsx:54），无单步入口；DataFavoritesPage 声称复用 FavoriteToolbar/FavoriteList 却内联重写（DataFavoritesPage.tsx:166-231） | HistoryPage.tsx:54 + DataFavoritesPage.tsx |

### 3.7 死代码/死组件清单

| 位置 | 说明 |
|---|---|
| `frontend/src/components/Sidebar.tsx` | 全仓库无 import（死组件） |
| `frontend/src/components/TopBar.tsx` | 全仓库无 import（死组件） |
| `SidebarRoute` 中 /skills /secrets /sync /knowledge | 路由存在，主导航无入口 |
| `/brief`、`/deep/:type/:id`、`/reviews` 路由 | 死路由，连带 useDigest/useAnnotations/useReviews/NoteEditor 失效 |
| `knowledge_chunks_api.py` | chunks=0 行，无生成器 |
| `reading_states_repo.py:43-80` record_open/record_dwell | 无任何调用点 |
| `review_service.create_review` | 只有 API 端点，无自动创建 |
| `sync.py 冲突裁决` | 写标记无人读 |
| `knowledge_repo.upsert_progress` | 无调用点，progress 全 0 |
| `KnowledgeCompoundingDashboard` / `KnowledgePlanningPanel` | 仅测试引用（复利/规划 UI 实际不存在） |

---

## 4. 业务流/操作流不清晰点（使用者视角）

| # | 场景 | 不清晰之处 | 影响 |
|---|---|---|---|
| F1 | 用户收藏一篇热点 | **收藏之后发生了什么？** favorites 与 knowledge_items 靠 source_url JOIN，无明确"何时/如何变成知识条目"链路；archive 与 bookmark 两套入口并存 | 用户无法预期；favorites 仅 4 条 |
| F2 | 知识任务队列 | **pending→done 谁在推进？** compile 靠每日 02:30 规则消费者；generate_learning_plan/generate_soul 依赖外部 Agent 主动扫描，Agent 不跑队列永远 pending | 计划停在 W30、SOUL 13 天未更 |
| F3 | 学习计划生成 | **如何触发？** generate_plan_direct 规则版无 scheduler 调用 | 周计划只有 7/23 手动生成一次 |
| F4 | 内容日历/发布 | **日历→草稿→发布→回写 stats 整条链路无自动化、无触发点**；历史上发布因 draft 缺失失败 | content_calendar=0 |
| F5 | 复利仪表盘 | **数据从哪来？** avg_score 全 0、trigger_health 是进程内存——用户看到的"复利"是空转数字且无法分辨 | 产品诚信问题 |
| F6 | 6 认知模式 | Outbox 依赖 reading_states（空）、Review 依赖 sm2（空）→ **这两个模式打开即空页面**，用户不知道为什么 | 空态无解释 |
| F7 | 跨设备同步 | **没有 UI 说明"仅同步配置/收藏/任务，不同步知识库本身"**；sync_history 失败无醒目提示 | 用户误以为 4,143 条目已跨端 |
| F8 | 主导航 | /skills /secrets /sync /knowledge 在 LayerNav 中不可达；质量门禁页在 /judge 子导航有链接但知识管理的 6 模式与 4 领域需先进入 /knowledge | 新用户找不到功能 |
| F9 | CodeGarden 服务网格 | 1,347 条噪音服务，拓扑图不可信；资源中枢/联动引擎无数据 | 功能展示失真 |
| F10 | 源健康 | 77/120 源 dead，无用户可见的健康总览（source_health 有 job 但无 UI 汇总） | 采集断层不可见 |
| F11 | 深度阅读 | 知识页 tab 指向无 :id 的 `/knowledge/deep-read` → 空白；判断层入口打开的是简报 | 用户点"深度阅读"进错页/白屏 |
| F12 | 周报 | 行动层跳 `/report?type=weekly` 被忽略，永远显示日报 | 报告类型不可达 |
| F13 | XLSX 导出 | 前端 window.open('/api/export/download') → 404 | 导出功能不可用 |
| F14 | 手动刷新 | 失败静默（upsert 失败仍记 SUCCESS 并 SSE 推"成功"）；"新增 X 条"是采集总条数而非净新增 | 用户被假成功误导 |
| F15 | 采集失败可见性 | per-source 失败、门禁拒绝原因、url_check_status 隐藏原因，前端全部不可见 | 条目"消失"无解释 |
| F16 | 追抓历史 | catchup since/until 窗口不作用于抓取（仍是普通重采）→ "回填历史"是空头承诺 | 承诺未兑现 |
| F17 | 告警 | v2 评估无 rules 配置入口（规则在设置深处的 v1 体系）；无 SSE 实时（仅 30s 轮询） | 告警模式缺规则配置 |
| F18 | 技能管理 | /skills 无活入口（唯一导航在死组件 Sidebar） | 新用户找不到技能管理 |
| F19 | 复利/规划 | KnowledgeCompoundingDashboard / KnowledgePlanningPanel 仅测试引用 → 文档承诺的复利入口落空 | 功能不存在于 UI |
| F20 | 主题切换 | 设置页切主题后首页状态不一致（双轨）；首屏暗色闪烁 | 界面状态不一致 |

---

## 5. 改进方案（分阶段实施计划）

> 原则：先修"数据流动断裂"，再修"功能死代码"，最后做"导航与体验统一"。
> 每阶段给出验收标准（可量化）。
> **实施状态 (2026-08-16): Phase 0–6 已全部落地, 版本升级为 0.4.0 (v0.4.0)。
> 各 Phase 的完成标注见下方表格 (✅ = 已实现, 🔶 = 部分/后续增强)。**

### Phase 0 — 止血与事实对齐（1–2 天）✅ 完成

| # | 动作 | 验收标准 | 状态 |
|---|---|---|---|
| P0-1 | 修复同步停机：master_key 未解锁根因（keychain 恢复链路）+ 失败告警 | sync_history 连续 3 次成功；失败时前端显式提示 | ✅ sync_job 自动恢复持久化密钥 |
| P0-2 | 服务网格扫描加白名单/去噪（仅扫描 cg_projects 关联目录 + 去重 + 排除系统进程） | cg_services 从 1,347 收敛到 <100 且名称可读 | ✅ 1,347 → 47 (黑名单+泛运行时+系统二进制+自动清理) |
| P0-3 | 停用被 flag 关闭但仍注册的前端路由（ReviewMode 等）或开启 feature_reviews | 前端不出现 404 页面 | ✅ feature_reviews/alerts/recommendations 默认开启 |
| P0-4 | 修复 Sidebar/TopBar 死代码：删除或接入主导航 | grep 无死引用；/skills /secrets /sync 可达 | ✅ 死组件删除 + Header"更多"菜单 |
| P0-5 | **修复跨轮去重 FK 失效**：content_fingerprints 指纹插入改为"入库后补写" | 新条目指纹首轮落库；同 URL 二次采集被拒 | ✅ _write_fingerprints 入库后补写 |
| P0-6 | **修复 security_enrichment_job 列名错误** | job 不再每轮崩溃；enrichment 有真实产出 | ✅ 改查 knowledge_items + JSON 安全合并 |
| P0-7 | **修复前端 4 个断链**：深度阅读路由、/report?type= 透传、XLSX 导出端点、复利仪表盘挂载 | 上述页面可用或显式下线 | ✅ /api/export/xlsx + report type + deep-read 重定向 |

### Phase 1 — 知识闭环数据流修复 ✅ 完成

| # | 动作 | 验收标准 |
|---|---|---|
| P1-1 | **KL 状态落真相源**：write_item_to_md / sync_item_to_db 增加 lifecycle(+kl) 字段映射；full_sync 不重置已推进状态 | 500 样本 md 含 kl 字段 ≥95%；full_sync 后 DB 状态不回落 |
| P1-2 | **T4 死锁解除**：ai_scores 空时提供可配置 fallback 评分（或从 quality_score 映射）；或允许"无评分但满足其他条件"的发布 | kl:publish > 0；发布动作有日志 |
| P1-3 | **统一生命周期模型**：sag_service 与 kl_state_machine 收敛为一套（推荐 kl 五阶段，sag 改为适配层） | lifecycle 取值只剩 5 种 kl:*；无 signal/amplify/generate 新写入 |
| P1-4 | **watchdog 增量同步**：改为按文件 mtime 增量扫描 + 单文件级冲突检测 | 单文件改动不触发全目录重扫；扫描耗时 <5s |
| P1-5 | 分类消费提速：auto_classifier 并入采集 post-ingest 链（或配额从 100/天提到 1000/天） | 一周内 domain/topic null 比例降到 <30% |

### Phase 2 — 采集管道修复 ✅ 完成

| # | 动作 | 验收标准 |
|---|---|---|
| P2-0 | **`run_one_source` 修复为真正单源采集**（按 source_id 过滤源列表而非整分类）；源级调度与健康归因恢复可信 | 源级调度只抓目标源；健康状态与产出一致 |
| P2-1 | **统一并发锁**：run_one/run_one_source/catchup 共用 run_once 的 asyncio.Lock；collector 不再共享可变状态（每次 collect 新建或加锁） | 并发压测无 self.sources 覆盖；无重复采集 |
| P2-2 | **去重窗口修复**：D7 语义改回"滚动 7 天"或去重查询改用滚动窗口 + 指纹表补写 | 上周条目本周不再重复入库 |
| P2-3 | **catchup 追抓窗口真正生效**：since/until 传入 collector 增量抓取；或明确下线"追抓"承诺 | 追抓返回历史区间数据；UI 说明真实能力 |
| P2-4 | **unreachable 复检路径**：unreachable 条目进入周期性复检队列（而非永久隐藏） | 抖动源条目 24h 内恢复可见 |
| P2-5 | **门禁语义对齐**：Hard 门禁在 loose 模式降为 flag+扣分（与文档一致）或文档改为"hard 一律拒收"；gate 崩溃改为 fail-closed | 文档与代码一致；gate 异常不再免检 |
| P2-6 | **6 个未接线 collector 决策**：注册或显式移除（HN/Reddit/OpenBB/Telegram/GDELT/OSSInsight） | 无"已实现但永不执行"的 collector |
| P2-7 | **upsert 语义修复**：位置化 ID 改为内容哈希 ID；ingested_at 不被重采刷新；富化后摘要复检 | 同 URL 不重复；列表无"浮顶"假象 |
| P2-8 | **失败可见性**：采集失败/upsert 失败不再记 SUCCESS；SSE 增加 per-source 失败事件；前端卡片显示 quality 标识与隐藏原因 | 用户可区分"成功/失败/被拒/被隐藏" |

### Phase 3 — 内化/输出环节落地 ✅ 完成

| # | 动作 | 验收标准 |
|---|---|---|
| P3-1 | 复习功能接线：读数据源（DeepRead 停留/Outbox 整理）自动创建 sm2 记录 + 每日 due job | sm2_reviews > 0；ReviewMode 有真实队列 |
| P3-2 | 注意力事件前端埋点：DeepRead/Outbox/收藏/标注 POST /api/attention/events | attention_events > 0；热力图有数据 |
| P3-3 | 标注入口：ItemDetailDialog/DeepRead 加标注 UI（或经 MCP add_annotation）；热点详情站内弹窗（复用 /api/hotspots/{id}） | annotations > 0；热点可站内查看详情 |
| P3-4 | 内容链路最小闭环：draft 生成（从 kl:publish 条目）→ 日历排期 → 发布状态回写 | content_calendar > 0；drafts > 1 |
| P3-5 | 复利仪表盘改读真实数据：用 kl 阶段分布/links/attention 替代 AVG(mastery) 与进程内存；挂载到 /knowledge/compound | 仪表盘数字随 DB 变化，重启不归零 |

### Phase 4 — 同步与安全加固 ✅ 完成

| # | 动作 | 验收标准 |
|---|---|---|
| P4-1 | bundle 构建失败即中止（任何单表读取异常 → 整轮同步失败，不清空本地） | 注入单表故障测试：本地表不被清空 |
| P4-2 | secrets merge 排除密文字段（用明文指纹字段比较） | 无 LLM 配置时同步 secrets 不产生伪冲突 |
| P4-3 | 冲突裁决生效：merge 读取 _conflict_resolved | resolve API 后再同步，裁决生效 |
| P4-4 | sm2_reviews merge 语义修正（due_at 晚者胜） | 单测覆盖 |
| P4-5 | master_key 恢复/轮换流程：re-wrap 所有加密字段 + 文档化 | 改 master_key 后 secrets/webdav 仍可解密 |
| P4-6 | 知识库纳入同步范围（或 UI 明示不同步） | 用户知情；同步失败告警 |
| P4-7 | Playbook 执行加沙箱/确认/审计（或显式禁用执行端点）；cg_event_process_job 补真实 handler 或显式下线 | 无未确认的命令执行面；事件不再"假成功" |
| P4-8 | **备份完整性 + 恢复流程**：备份纳入 knowledge/ 源文件（或至少文档化 git 恢复路径）；提供 restore 脚本 + 演练 | 备份含源文件；restore 有文档可执行 |
| P4-9 | 安全小项：MCP concept_name 路径穿越校验；secrets 密码长度校验统一（8 vs 12）；RUNBOOK.md 表名修正 | 无路径穿越；校验一致；文档可执行 |

### Phase 5 — 导航与操作流统一 ✅ 完成

| # | 动作 | 验收标准 |
|---|---|---|
| P5-1 | 主导航统一：LayerNav 增加"知识/技能/密钥/同步"入口或恢复 Sidebar 并删除 LayerNav 冗余 | 全页面从主导航可达；无二套导航 |
| P5-2 | 空态治理：6 模式空数据时显示"数据从哪来/如何产生"引导文案 | Outbox/Review 空页面有引导 |
| P5-3 | 源健康总览 UI（dead 源列表 + 最近产出 + 恢复建议，合并三套口径） | 用户可见 77 dead 源及处理建议 |
| P5-4 | CodeGarden 拓扑显示校验状态（auto/confirmed/manual），噪音数据可一键清理 | 拓扑图节点可信 |
| P5-5 | 错误反馈统一：window.alert → Toast；ErrorBoundary 挂载到路由层 | 无 window.alert 残留 |
| P5-6 | 主题状态统一：SettingsPage 的 localStorage 事件并入 ThemeContext；消除 FOUC | 切主题全站一致 |
| P5-7 | 收藏→知识库单步入口（收藏面板加"导入知识库"）；DataFavoritesPage 真复用 favorites/ 组件 | 一键导入；无重复组件 |

### Phase 6 — 质量与债务 ✅ 完成 (v0.4.0 版本升级)

| # | 动作 |
|---|---|
| P6-1 | 文档对账：ARCHITECTURE.md / CLAUDE.md / _SCHEMA.md / quality_gates.md 与代码实测对齐（chunks/attention/review 的"已实现"表述需修正；9 vs 11 门禁） |
| P6-2 | 死代码清理：Sidebar/TopBar/chunks API/conflict resolve 标记/未接线 collector/死配置（7 项） |
| P6-3 | security ↔ knowledge 实体统一命名空间（PRD A.3.2 遗留） |
| P6-4 | 为上述每个修复补回归测试（当前 2288 后端 + 278 前端测试不覆盖这些断裂；新增 FK 去重、run_one_source、merge 语义、门禁语义测试） |

---

## 6. 附录：关键证据索引

- 文件真相层：`knowledge/_SCHEMA.md`（schema 与代码漂移：仍写 compiled，代码已用 lifecycle）、`knowledge/SOUL.md`、"暂无创作记录"、`knowledge/learning/progress.json`（全 0）
- 同步核心：`backend/services/knowledge_sync.py:119-151, 176-233, 267-316`、`knowledge_watcher.py:53-57, 111-228`
- 状态机：`kl_state_machine.py:63-91`（纯 validator）、`triggers/t1~t4`（只 UPDATE lifecycle）、`t4_structure_to_publish.py:9-10`
- 死功能：`review_service.py:95-116`、`attention_scorer.py:94-187`、`reading_states_repo.py:43-80`、`knowledge_chunks_api.py`
- 同步：`sync_service.py:101-123, 254, 377-388, 467-476`、`sync_merge.py:161-250, 365-425`、`sync_bundle.py:29-30, 472-545, 578-641`、`sync.py:331-374`
- 加密：`crypto.py:116-132`
- 前端导航：`frontend/src/App.tsx`（路由）、`Header.tsx`（LayerNav 主导航）、`Sidebar.tsx`（死代码）、`layout/LayerHeader.tsx`（子导航）
- 前端断链：`KnowledgeTabs.tsx:95`（deep-read 无 :id）、`ReportPage.tsx:25`（type 被忽略）、`ExportSettings.tsx:29`（导出 404）、`KnowledgeCompoundingDashboard.tsx`（仅测试引用）
- 采集管道：`collection_service.py:344-393`（run_one_source 整分类）、`614-634`（FK 去重失效）、`item_builder.py:137`（位置化 ID）、`quality/pipeline.py:150-194`（门禁语义）、`quality/jobs.py:63-72`（unreachable 永久隐藏）
- 服务网格：`backend/services/codegarden_service_service.py:116-285`、cg_services 表实测（1,346/1,347 噪音）
- CodeGarden 联动：`codegarden_orchestration_service.py:138,242`（任务只写不读）、`compiler.py:616`（唯一消费者只认 compile）、`jobs.py:555-557`（事件假成功）、`cost_monitor.py:183-197`（写坏列）、`backup_service.py:35-43`（仅 DB 备份无 restore）
- 安全：`mcp_agent_tools.py:97`（路径穿越）、`api/secrets.py:324`（主密钥进 URL）、`crypto.py:35` vs `api/secrets.py:45`（校验不一致）
- 文档对照：`docs/hotspot_v1.7_PRD.md` B.6/B.8、`docs/ARCHITECTURE.md` §四/§五、`docs/quality_gates.md`（9 vs 11 门禁，均与实测不符）、`CodeGarden_PRD_v1.7.md:1616-1617`（M5/M7-M12 承认待启动 vs AGENTS.md 宣称全量实现）
