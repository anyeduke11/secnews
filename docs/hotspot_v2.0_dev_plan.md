# hotspot v2.0 开发计划

> 基于 `hotspot_v2.0_PRD.md`（4087 行）制定
> 版本: 2026-07-28 · 总周期: ~46 天 · 4 个里程碑 · 9 个 Phase · 24 条需求
> 状态: Phase 8 已完成，当前 Phase: 9

---

## 目录

1. [概述与关键数字](#1-概述与关键数字)
2. [里程碑总览（M1-M4）](#2-里程碑总览m1-m4)
3. [Phase 详细任务分解](#3-phase-详细任务分解)
   - [Phase 8：复利基础设施 + 资讯收藏聚合](#phase-8复利基础设施--资讯收藏聚合6-天)
   - [Phase 9：T1/T2 触发器实施](#phase-9t1t2-触发器实施4-天)
   - [Phase 10：抓取层现代化](#phase-10抓取层现代化5-天)
   - [Phase 11：T3/T4/T5 触发器 + 告警系统](#phase-11t3t4t5-触发器--告警系统6-天)
   - [Phase 12：复利可视化 + 4/6 模式 + 规划引导](#phase-12复利可视化--46-模式--规划引导4-天)
   - [Phase 13：子系统联动](#phase-13子系统联动3-天)
   - [Phase 14：清理 + 文档 + 迁移](#phase-14清理--文档--迁移5-天)
   - [Phase 15：Hybrid AI](#phase-15hybrid-aicrawl4ai--本地-llm--外部-agent-并存6-天)
   - [Phase 16：Chunks + Attention Heatmap + 6 模式完整](#phase-16chunks--attention-heatmap--6-模式完整7-天)
4. [依赖关系与关键路径](#4-依赖关系与关键路径)
5. [验收标准速查](#5-验收标准速查)
6. [迁移策略](#6-迁移策略)
7. [风险与对策](#7-风险与对策)
8. [优先级排序逻辑](#8-优先级排序逻辑)

---

## 1. 概述与关键数字

| 维度 | 值 |
|------|-----|
| 总周期 | ~46 天（6+4+5+6+4+3+5+6+7）|
| 里程碑数 | 4（M1~M4）|
| Phase 数 | 9（Phase 8~16）|
| 需求总数 | 24（P0×8 + P1×9 + P2×7）|
| M1 硬承诺 | P0 全部交付 + 首轮可发布 |
| 新增数据表 | 6 张（4 核心 + 2 扩展）|
| 新增 MCP tool | 4 个（score_item / enrich_concept / link_items / trigger_codegarden_drift）|
| 删除 MCP tool | 4 个（trigger_extract_tags / mark_digest_read / create_alert_rule / trigger_cubox_sync）|
| 新增调度器 job | 9 个（T1~T5 / dead_letter / daily_digest / compounding / attention / planning）|
| 新增 collector | 6 个（hn / reddit / openbb / telegram / gdelt / ossinsight）|
| 核心路径 | 4 表 → 去重/评分 → T1 → T2 → 日增量 → T3/T4/T5 → 联动 → Hybrid AI → 体验项 |

---

## 2. 里程碑总览（M1-M4）

| 里程碑 | 时间窗 | 主题 | 关键交付 | 需求编号 | 负责人倾向 |
|--------|--------|------|---------|---------|-----------|
| **M1** | D1–18 | 复利基础设施 + 闭环核心 | simhash 去重、4 新表、评分 MCP、T1/T2、日增量起始、可读 ID、遗留清理、收藏聚合视图 | P0-1~P0-8 + P1-3 | 全栈/后端主导 |
| **M2** | D19–28 | 闭环尾部 + 可视化 + 规划引导 | T3/T4/T5、3 类告警、日增量收尾、复利仪表盘、4 模式 UI、规划引导 | P1-1~P1-6 | 前端/全栈主导 |
| **M3** | D29–34 | 抓取现代化 + 子系统联动 | 6 新 collector、tech_stack_drift、cve_sync 联动 | P1-8, P1-9 | 抓取层主导 |
| **M4** | D35–46 | Hybrid AI + 体验闭环 | LLMService + Crawl4ai、注意力热图、SM-2 整理/复习、chunks 字段 | P1-7 + P2-1~P2-3 | 全栈 |

### M1 详细排期（D1–18）

| 子阶段 | 天数 | 任务 | 关联需求 |
|--------|------|------|---------|
| D1–3 | 3 | Data migration 043: 4 张新表 + 索引 | P0-2 |
| D1–3 | 3 | simhash 实现 (`services/simhash.py`) | P0-1 |
| D4–5 | 2 | 去重集成 (collection_service.py 中) | P0-1 |
| D4–6 | 3 | migration 046: lifecycle 5 阶段迁移 | P0-3 前置 |
| D5–6 | 2 | 4 个新 MCP tool (score_item/enrich_concept/link_items/drift) | P0-5 |
| D7–9 | 3 | 资讯收藏聚合后端 (imported_aggregator + API) | P1-3 |
| D7–8 | 2 | 资讯收藏聚合前端 (KnowledgeFavoritesView) | P1-3 |
| D9 | 1 | 资讯收藏聚合 e2e 验证 | P1-3 |
| D10–11 | 2 | 状态机引擎 (kl_state_machine.py) | P0-3, P0-4 |
| D10–12 | 3 | T1 触发器 (t1_raw_to_refine.py) + 调度器注册 | P0-3 |
| D12–14 | 3 | T2 触发器 (t2_refine_to_link.py) + 调度器注册 | P0-4 |
| D13–14 | 2 | 重试策略 + 死信队列 (retry_policy.py) | P0-3, P0-4 |
| D15 | 1 | Prometheus 指标 (kl_metrics.py) | P0-3, P0-4 |
| D15–16 | 2 | 可读 ID 规范化 (id_factory.py) | P0-7 |
| D16–17 | 2 | 遗留清理 (kv_cache、/api/agent、4 MCP tool) | P0-8 |
| D17–18 | 2 | 迁移指南 + 测试 + 灰度发布 | P0-8 |

### M2 详细排期（D19–28）

| 子阶段 | 天数 | 任务 | 关联需求 |
|--------|------|------|---------|
| D19–20 | 2 | T3 触发器 (t3_link_to_structure.py) | P1-1 |
| D21–22 | 2 | T4 触发器 (t4_structure_to_publish.py) | P1-1 |
| D23 | 1 | T5 触发器 (t5_publish_to_refine.py) | P1-1 |
| D23–24 | 2 | 告警规则引擎 (alert_engine.py) + 3 类规则 | P1-2 |
| D24 | 1 | 告警 UI (AlertCenter.tsx) | P1-2 |
| D25 | 1 | 复利仪表盘 (KnowledgeCompoundingDashboard.tsx) | P1-4 |
| D25–26 | 2 | 简报模式 + 扫描模式 UI | P1-5 |
| D26–27 | 2 | 深度阅读模式 + 告警模式 UI | P1-5 |
| D27 | 1 | 触发器状态可视化 (5 阶段进度条) | P1-5 |
| D27–28 | 2 | KnowledgePlanningPanel + planning_action_check job | P1-6 |
| D28 | 1 | daily_digest job + 测试 | P0-6 收尾 |

### M3 详细排期（D29–34）

| 子阶段 | 天数 | 任务 | 关联需求 |
|--------|------|------|---------|
| D29–30 | 2 | BackendSession 实现 (session.py) | P1-8 |
| D30–31 | 2 | trafilatura 集成 (trafilatura_parser.py) | P1-8 |
| D31–32 | 2 | 6 个新 collector (hn/reddit/openbb/telegram/gdelt/ossinsight) | P1-8 |
| D33 | 1 | JSON pipeline_config | P1-8 |
| D33–34 | 2 | tech_stack_drift 任务 | P1-9 |
| D34 | 1 | CVE 双向同步 + 跨域 entity 命名空间 | P1-9 |

### M4 详细排期（D35–46）

| 子阶段 | 天数 | 任务 | 关联需求 |
|--------|------|------|---------|
| D35–36 | 2 | LLM 配置文件 schema + LLMService 实现 | P1-7 |
| D37 | 1 | 评分任务迁移 T1 (llm_service.score) | P1-7 |
| D38 | 1 | 摘要任务迁移 T3 (llm_service.summarize) | P1-7 |
| D39–40 | 2 | Crawl4ai 集成 (crawl4ai_parser.py + 4 源迁移) | P1-7 |
| D40 | 1 | 配置降级矩阵 + 5 场景集成测试 | P1-7 |
| D41 | 1 | 成本监控 + Hybrid AI 测试 | P1-7 |
| D42 | 1 | chunks 字段迁移 + knowledge_chunks 表 | P2-3 |
| D42–43 | 2 | chunk 级 FTS5 + chunk 级 UI | P2-3 |
| D43 | 1 | attention_score 计算 + 事件采集 | P2-1 |
| D44 | 1 | attention 聚合 job + AttentionHeatmap 组件 | P2-1 |
| D44–45 | 2 | 整理模式 (OutboxMode) + 复习模式 (ReviewMode SM-2) | P2-2 |
| D45–46 | 2 | 4 模式 UI 完善 (chunk 高亮、attention 显示) + 收尾测试 | P2-1~P2-3 |

---

## 3. Phase 详细任务分解

### Phase 8：复利基础设施 + 资讯收藏聚合（~6 天）✅ 已完成 (2026-07-28)

**目标**: 打通复利闭环的数据底座，交付 simhash 去重、4 张新表、4 个 MCP tool、资讯收藏聚合视图。

| 任务 | 产出 | 前置依赖 | 估算 |
|------|------|---------|------|
| **8.1 数据迁移** | `migration 043_v2.0_fingerprints_scores.sql`：content_fingerprints / ai_scores / item_entities / knowledge_links 4 表 + 6 索引 | 无 | 0.5d |
| **8.2 simhash 实现** | `backend/services/simhash.py`：64-bit simhash + Hamming distance + URL canonicalize | 无 | 0.5d |
| **8.3 去重集成** | `backend/services/collection_service.py`：collect() 后立即去重 | 8.2 | 0.5d |
| **8.4 AI 评分 MCP tool** | `backend/api/mcp_phase8.py`：score_item / enrich_concept / link_items / trigger_codegarden_drift | 8.1 | 1d |
| **8.5 背景补全 MCP tool** | enrich_concept(concept_name, content, source) → 写 concepts/{name}.md | 8.1 | 0.5d |
| **8.6 知识关联 MCP tool** | link_items(from_id, to_id, link_type, confidence) → 写 knowledge_links | 8.1 | 0.5d |
| **8.7 codegarden drift MCP tool** | trigger_codegarden_drift(project_id) → tech_stack 评估 | 8.1 | 0.5d |
| **8.8 测试** | test_simhash / test_mcp_phase8 / test_fingerprint | 8.1~8.7 | 0.5d |
| **8.9 资讯收藏聚合后端** | `backend/services/imported_aggregator.py` + `backend/api/knowledge_imported.py` + 扩展 | 无 | 1d |
| **8.10 资讯收藏聚合前端** | `KnowledgeFavoritesView.tsx` + `useImported.ts` + 5th action card + 路由 | 8.9 | 1.5d |
| **8.11 资讯收藏聚合 e2e** | 全流程验证（5 类型筛选 + 搜索 + 时间 + 分页）| 8.10 | 0.5d |

**Phase 8 门禁**:
- simhash 跨源去重率 ≥ 95%
- 13 MCP tool 通过外部 Agent 调通
- 4 新表 CRUD 全过
- 资讯收藏聚合视图 e2e 8 用例通过

---

### Phase 9：T1/T2 触发器实施（~4 天）

**目标**: 实现 5 阶段状态机引擎 + T1/T2 自动化触发器，知识库日增量开始 >0。

| 任务 | 产出 | 前置依赖 | 估算 |
|------|------|---------|------|
| **9.1 状态机引擎** | `backend/services/kl_state_machine.py`：KLStateMachine 类 + 不变量检查 | 无 | 0.5d |
| **9.2 T1 实施** | `backend/services/triggers/t1_raw_to_refine.py`：60s 调度 + simhash 去重 + 评分 + tag 提取 | 9.1, Phase 8 | 1d |
| **9.3 T2 实施** | `backend/services/triggers/t2_refine_to_link.py`：120s 调度 + entity 查找 + MCP link_items 触发 | 9.1, Phase 8 | 1d |
| **9.4 调度器注册** | `backend/scheduler/jobs.py` 注册 kl_trigger_t1 / kl_trigger_t2 | 9.2, 9.3 | 0.5d |
| **9.5 重试 + 死信** | `backend/services/retry_policy.py`：指数退避 + 死信队列 | 9.2, 9.3 | 0.5d |
| **9.6 Prometheus 指标** | `backend/metrics/kl_metrics.py`：6 个指标 + 仪表盘 JSON | 9.2, 9.3 | 0.5d |
| **9.7 测试** | test_t1_trigger / test_t2_trigger / test_state_machine | 全部 | 0.5d |

**T1 验证**: 100 条样本中 95%+ 成功从 raw 推进到 refine
**T2 验证**: 80% 找到至少 1 个关联 concept

---

### Phase 10：抓取层现代化（~5 天）

**目标**: BackendSession 统一注入、可读 ID 规范化、trafilatura 可选集成、6 个新 collector。

| 任务 | 产出 | 估算 |
|------|------|------|
| **10.1 BackendSession** | `backend/collectors/session.py`：httpx + proxy + retry + rate-limit | 1d |
| **10.2 可读 ID 规范化** | `backend/collectors/id_factory.py`：`{source}:{subtype}:{native_id}` 工厂 | 1d |
| **10.3 trafilatura 集成** | `backend/parsers/trafilatura_parser.py`：作为 optional extractor | 0.5d |
| **10.4 6 个新 collector** | hn / reddit / openbb / telegram / gdelt / ossinsight 各 5 用例 | 2d |
| **10.5 JSON pipeline_config** | `config/pipeline.json`：4 源示例 + 阈值 + 输出 | 0.5d |
| **10.6 测试** | 6 collector × 5 用例 + BackendSession 注入测试 | 0.5d |

---

### Phase 11：T3/T4/T5 触发器 + 告警系统（~6 天）

**目标**: 完成 5 阶段状态机全部触发器，交付 3 类基础告警规则。

| 任务 | 产出 | 估算 |
|------|------|------|
| **11.1 T3 实施** | `backend/services/triggers/t3_link_to_structure.py`：600s 调度 + 关联数检查 + 摘要生成 | 1d |
| **11.2 T4 实施** | `backend/services/triggers/t4_structure_to_publish.py`：1800s 调度 + 阈值 + 24h 稳定 + .md 写入 | 1d |
| **11.3 T5 实施** | `backend/services/triggers/t5_publish_to_refine.py`：用户主动 + 备份 + stale 标记 | 0.5d |
| **11.4 调度器扩展** | 注册 kl_trigger_t3 / t4（T5 走用户主动调用）| 0.5d |
| **11.5 告警规则引擎** | `backend/services/alert_engine.py`：3 类基础规则 | 1d |
| **11.6 告警规则 1** | tech_stack 影响：新 CVE 命中 cg_projects.tech_stack | 0.5d |
| **11.7 告警规则 2** | 关键 CVE：NVD CVSS ≥ 9.0 | 0.5d |
| **11.8 告警规则 3** | 标讯命中：标讯关键词命中 tech_stack | 0.5d |
| **11.9 告警 UI** | `frontend/src/components/AlertCenter.tsx`：Inbox + 红色横幅 | 1d |
| **11.10 测试** | test_t3/t4/t5 + test_alert_engine | 0.5d |

**T3 验证**: 关联数 ≥ 3 的 items 100% 推进到 structure
**T4 验证**: score ≥ 8 的 items 100% 自动发布
**T5 验证**: 用户回滚 100% 不丢用户编辑

---

### Phase 12：复利可视化 + 4/6 模式 + 规划引导（~4 天）

**目标**: 交付复利仪表盘、4 种核心认知模式 UI、KnowledgePlanningPanel 规划引导。

| 任务 | 产出 | 估算 |
|------|------|------|
| **12.1 复利仪表盘** | `KnowledgeCompoundingDashboard.tsx`：日/周/月趋势 + top concepts + 断点告警 | 1d |
| **12.2 简报模式 UI** | `BriefingMode.tsx`：每日首次打开 + 一句话摘要 + 3 篇关键文章 + 数据源状态 | 0.5d |
| **12.3 快速扫描 UI** | `ScanMode.tsx`（即当前首页）：分类 + 标签 + 时间筛选列表 | 0.5d |
| **12.4 深度阅读 UI** | `DeepReadMode.tsx`：文章全屏 + 右侧栏（推荐/笔记/影响/触发器状态）| 0.5d |
| **12.5 告警模式 UI** | `AlertMode.tsx`：红色横幅 + 告警中心 Inbox | 0.5d |
| **12.6 触发器状态可视化** | knowledge_items 详情页显示 5 阶段进度条 | 0.5d |
| **12.7 KnowledgePlanningPanel** | 基于 reading_states + lifecycle + KL 状态生成个性化规划动作 | 1d |
| **12.8 planning_action_check job** | 注册 planning_action_check 每 10min（见 B.9.7）| 0.5d |
| **12.9 测试** | 4 模式组件 + dashboard + planning panel 渲染测试 | 0.5d |

> 注：6 种认知模式中的「整理模式（Outbox）」和「复习模式（SM-2）」由 Phase 16 实施，因依赖 chunks + attention_score + sm2_reviews 等基础设施。

---

### Phase 13：子系统联动（~3 天）

**目标**: 打通 Knowledge ↔ Codegarden ↔ Security 三子系统联动。

| 任务 | 产出 | 估算 |
|------|------|------|
| **13.1 tech_stack_drift 任务** | `backend/services/codegarden_drift.py`：knowledge 新 tech → codegarden 评估 | 1d |
| **13.2 CVE 双向同步** | `backend/services/cve_knowledge_sync.py`：双向去重 + sync retry + 死信 | 1d |
| **13.3 跨域 entity 命名空间** | entity_type 统一：concept/tool/vendor/person/cve/technique/standard/event | 0.5d |
| **13.4 Security Graph 引用 Knowledge** | security.cve_nodes.cve_id → knowledge.item_entities[entity_name] | 0.5d |
| **13.5 测试** | 联动场景测试 15+ 用例 | 0.5d |

---

### Phase 14：清理 + 文档 + 迁移（~5 天）

**目标**: 删除遗留代码和路由，编写迁移指南和用户文档。

| 任务 | 产出 | 估算 |
|------|------|------|
| **14.1 删 kv_cache** | `migration 045_v2.0_drop_kv_cache.sql` | 0.5d |
| **14.2 删 /api/agent/* 路由** | 移除 deprecated 路由 | 0.5d |
| **14.3 删 4 个 MCP tool** | trigger_extract_tags / mark_digest_read / create_alert_rule / trigger_cubox_sync | 1d |
| **14.4 写 v2.0 迁移指南** | `docs/v1_to_v2_migration.md`：5 阶段映射 + 触发器启用步骤 | 1d |
| **14.5 写 v2.0 用户文档** | `docs/hotspot_v2_user_guide.md`：5 触发器说明 + 4 模式使用 | 1d |
| **14.6 更新 CHANGELOG** | `docs/CHANGELOG.md`：v2.0 新增功能 + 破坏性变更 | 0.5d |
| **14.7 更新 README** | 同步到 v2.0 状态（5 子系统、13 MCP tool、5 阶段）| 0.5d |

---

### Phase 15：Hybrid AI（Crawl4ai + 本地 LLM + 外部 Agent 并存）（~6 天）

**目标**: 引入可选本地 LLM 能力，Crawl4ai 高阶抓取，T1/T3 延迟大幅降低。

| 任务 | 产出 | 前置依赖 | 估算 |
|------|------|---------|------|
| **15.1 LLM 配置文件 schema** | `config/llm.yaml` + 校验 + 文档 | 无 | 0.5d |
| **15.2 LLMService 实现** | `backend/services/llm_service.py`：多 provider + 降级 + 缓存 | 无 | 1d |
| **15.3 评分任务迁移 T1** | T1 评分从 MCP `score_item` 改 `llm_service.score()` | 15.2 | 1d |
| **15.4 摘要任务迁移 T3** | T3 摘要从 MCP `enrich_concept` 改 `llm_service.summarize()` | 15.2 | 1d |
| **15.6 Crawl4ai 集成** | `backend/parsers/crawl4ai_parser.py` + 4 源迁移 | 无 | 1.5d |
| **15.7 配置降级矩阵** | 5 种缺失配置场景的降级行为 | 15.2 | 0.5d |
| **15.8 成本监控** | cost_alert 触发 + 日/月 USD 限额 | 15.2 | 0.5d |
| **15.9 测试** | test_llm_service / test_crawl4ai / test_hybrid_ai | 全部 | 1d |

**关键验收**:
- LLMService 多 provider 工作（Ollama + Qwen + OpenAI）
- Crawl4ai 4 源抓取成功率 ≥ 80%
- T1 评分延迟降低 ≥ 60%
- T3 摘要延迟降低 ≥ 40%
- 5 种降级场景全通过

---

### Phase 16：Chunks + Attention Heatmap + 6 模式完整（~7 天）

**目标**: v2.0 收尾 Phase，完成 chunks 段落级引用、attention_score 注意力热图、6 种认知模式全部实施。

| 任务 | 产出 | 估算 |
|------|------|------|
| **16.1 chunks 字段迁移** | `migration 046_v2.0_chunks.sql` + `knowledge_chunks` 表 | 0.5d |
| **16.4 chunk 级 FTS5** | search_knowledge 支持 chunk_index 返回 | 1d |
| **16.5 chunk 级 UI** | 深度阅读模式高亮 chunk，点击跳转原文 | 1d |
| **16.6 attention_score 计算** | `backend/services/attention_scorer.py`：5 维度加权 | 0.5d |
| **16.7 attention 事件采集** | 前端埋点：view/dwell/scroll/favorite/annotation | 0.5d |
| **16.8 attention 聚合 job** | attention_aggregate 每 30 分钟跑一次 | 0.5d |
| **16.9 AttentionHeatmap 组件** | `AttentionHeatmap.tsx`：30 天 × 时间段热图 | 1d |
| **16.10 整理模式（Outbox）UI** | `OutboxMode.tsx`：清单视图 + attention_score 排序 | 1d |
| **16.11 复习模式（SM-2）** | `ReviewMode.tsx` + SM-2 算法 + sm2_reviews 表 | 1.5d |
| **16.12 4 模式 UI 完善** | chunk 高亮、attention 显示 | 1d |
| **16.13 测试** | test_chunks / test_attention / test_6_modes | 0.5d |

**验收**: 6 种认知模式全部在 UI 可用；知识库每条 items 含 chunks + attention_score；用户可在简报模式看到 30 天热图。

---

## 4. 依赖关系与关键路径

### 关键路径（串行链）

```
P0-2 四张表 → P0-1 去重/P0-5 评分 → P0-3 T1 → P0-4 T2
→ P0-6 日增量(Phase 9–11) → P1-1 T3/T4/T5 → P1-9 联动
→ P1-7 Hybrid AI → P2 体验项
```

### 强前置

| 前置 | 后续 | 原因 |
|------|------|------|
| P0-2 4 张新表 | P0-5 评分 MCP、P0-1 去重、实体链接 | 表结构是底座 |
| Phase 8 全部 | Phase 9 T1/T2 | T1 依赖 simhash + 评分 |
| T1/T2 (P0-3/4) | T3/T4/T5 (P1-1) | 状态机链式推进 |
| T1/T2 (P0-3/4) | P0-6 日增量 | 没有触发器日增量 = 0 |
| Phase 11 | Phase 12 可视化 | 仪表盘需要触发器数据 |
| Phase 15 Hybrid AI | Phase 16 | LLMService 是 chunk 摘要前置 |

### 弱依赖/可并行

| 任务 | 不阻塞主链 | 建议并行时段 |
|------|-----------|-------------|
| P1-3 收藏聚合视图 | ✅ | Phase 8 早期并行 |
| P1-8 6 新 collector | ✅ | Phase 10 早期并行 |
| P0-8 遗留清理 | ✅（独立于新功能）| M1 末灰度 |
| Phase 14 文档 | ✅ | 任意时段 |

---

## 5. 验收标准速查

### 北极星指标

| 指标 | 目标 | 验收方式 |
|------|------|---------|
| 知识库日增量 | ≥ 10 items/天 | 30 天平均值 |
| 新信息复用率 | ≥ 30% | item_entities 关联到已有 concept 比例 |
| MCP tool 调用 P95 | < 500ms | Phase 8 性能测试 |
| 跨源去重准确率 | ≥ 95% | simhash + URL canonicalize 联合测试 |
| 评分后入库延迟 | < 5 min | 评分完成到 knowledge_items 创建 |
| 收藏聚合视图响应 | < 300ms P95 | `/api/knowledge/imported` 性能测试 |

### Phase 门禁速查

| Phase | 关键门禁 |
|-------|---------|
| 8 | 去重率 ≥ 95%；13 tool 调通；4 表 CRUD；收藏视图 e2e 8 用例 |
| 9 | T1 推进 95%+；T2 关联发现率 ≥ 80%；调度器 30 job 全部启动 |
| 10 | 6 collector × 5 用例；可读 ID 100% 映射；trafilatura fallback |
| 11 | T3/T4/T5 工作；3 类告警规则触发；4 模式 UI 渲染 |
| 12 | 仪表盘渲染；daily_digest 自动生成；planning panel 动作建议 |
| 13 | drift 触发评估；cve 双向同步；跨域 entity 命名空间 |
| 14 | kv_cache 删；/api/agent 删；4 tool 移；迁移指南完整 |
| 15 | LLMService 多 provider；Crawl4ai 4 源 ≥ 80%；延迟降 60%+ |
| 16 | 6 模式全可用；chunks + attention_score；热图渲染；SM-2 卡片翻转 |

---

## 6. 迁移策略

### 6.1 数据迁移（migration 043-046）

| 迁移 | 阶段 | 内容 |
|------|------|------|
| 043 | Phase 8 | 新增 4 表：content_fingerprints / ai_scores / item_entities / knowledge_links |
| 044 | Phase 9 | KL 重命名：signal→kl:raw, amplify:tagged→kl:refine, generate→kl:structure |
| 045 | Phase 14 | DROP kv_cache 表 |
| 046 | Phase 8 | lifecycle 5 阶段迁移（旧 3 阶段→新 5 阶段）|

### 6.2 可读 ID 迁移（双写策略）

| 阶段 | hotspot.id | 兼容 |
|------|------------|------|
| v2.0 启动 | 旧 hash ID 保留 | 直接读 |
| v2.0 写入 | 新 hotspot 双写：旧 hash + 新可读 | 1 个月内切 |
| v2.0.1 | 旧 hash ID 标 deprecated | 警告 |
| v2.1 | 完全切到可读 ID | 旧 hash 失效 |

### 6.3 MCP tool 迁移

| v1.7.6 tool | v2.0 状态 |
|-------------|-----------|
| trigger_extract_tags | 删除 → T1 触发器自动 |
| trigger_cubox_sync | 删除 → 本地 cron job |
| create_alert_rule | 推迟 v2.1 |
| mark_digest_read | 删除 → reading_states 自动追踪 |
| 5 读 tool | 保持 |
| 4 保留写 tool | 保持 |
| 4 新增 v2.0 tool | 新增 |

### 6.4 部署步骤

1. 停止 hotspot 服务
2. 备份数据库：`cp hotspot.db hotspot.db.v1.7.backup`
3. 执行 migration 043-046（自动）
4. 替换 backend 二进制
5. 替换 frontend dist
6. 启动 hotspot 服务
7. 运行 5 触发器 1 次：`python -m backend.scheduler.manual_run --trigger all`
8. 验证仪表盘：日增量 ≥ 10 items/天
9. 保留 v1.7 数据 30 天（兜底回滚）

### 6.5 回滚策略

| 触发条件 | 回滚动作 |
|---------|---------|
| 5 触发器导致数据异常 | 关闭触发器 job，仅保留 catchup |
| 知识库日增量 < 1 item | 检查阈值配置 + 触发器日志 |
| MCP tool 调用失败率 > 10% | 降级为 v1.7.6 模式（保留 9 读 + 4 保留写）|
| 严重 bug | 用 `hotspot.db.v1.7.backup` 还原 |

---

## 7. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 | 阶段 |
|---|------|------|------|------|------|
| 1 | 单人 46 天密集交付压力 | 高 | 高 | M1 硬承诺，M2-M4 渐进缓冲；P2 可延期至 v2.1 | 全部 |
| 2 | simhash 误判（不同新闻被合并）| 中 | 中 | 阈值 5 起步，先 false positive 监控 | Phase 8 |
| 3 | AI 评分波动（同一新闻两次评分差大）| 高 | 中 | 存多版本评分；v2.0 不自动应用，v2.1 引入置信度 | Phase 8 |
| 4 | 自动入库导致知识库噪声 | 中 | 中 | 阈值 ≥ 7 才入；v2.0 不自动应用 knowledge_links | Phase 9 |
| 5 | 6 个新 collector 反爬失败 | 中 | 低 | 先实现 3 个（hn/rss/openbb），其余 3 个 v2.1 | Phase 10 |
| 6 | 可读 ID 迁移复杂 | 中 | 中 | 保留 hash ID 作为 alias；v2.0 双写，v2.1 切读路径 | Phase 10 |
| 7 | 外部 AI Agent 不支持 score_item | 中 | 高 | 保留 manual add_favorite 路径；评分先存后用 | Phase 8 |
| 8 | 本地 LLM 硬件门槛 | 中 | 高 | 提供云端降级/可选路径，不将本地 LLM 设为闭环硬依赖 | Phase 15 |
| 9 | 知识库日增量 < 10 items | 中 | 高 | 监控告警；分析原因（评分太严？源失效？）；调阈值或源 | Phase 9→11 |
| 10 | 5 触发器互相等待死锁 | 低 | 高 | T2/T4 加 hard timeout + 自动 fallback；kl_dead_letter_retry 兜底 | Phase 11 |
| 11 | 删 /api/agent 路由破坏旧 agent | 低 | 中 | v2.0 保留 deprecated 1 个 minor 版本，v2.1 完全删 | Phase 14 |
| 12 | attention_score 数据稀疏 | 高 | 中 | v2.0 启动时 backfill 从 SQLite history 推断初始 score | Phase 16 |

---

## 8. 优先级排序逻辑

### P0（must）— 复利闭环核心，M1 硬交付

| 编号 | 需求 | 所属 Phase | 理由 |
|------|------|-----------|------|
| P0-1 | simhash 跨源去重 | Phase 8 | 去重是数据质量地基 |
| P0-2 | 新增 4 张数据表 | Phase 8 | 所有扩展功能的数据底座 |
| P0-3 | T1 触发器 raw→refine | Phase 9 | 状态机链起点 |
| P0-4 | T2 触发器 refine→link | Phase 9 | 状态机链第二环 |
| P0-5 | AI 评分 MCP tool | Phase 8 | T1 的前置条件 |
| P0-6 | 知识库自动入库（日增量） | Phase 9–11 | 复利北极星指标 |
| P0-7 | 可读 ID 规范化 | Phase 10 | 数据资产长期可维护性 |
| P0-8 | 遗留清理 | Phase 14 | 发布门禁 |

### P1（should）— 渐进交付，顺序可调

| 编号 | 需求 | 所属 Phase | 优先级排序理由 |
|------|------|-----------|---------------|
| P1-1 | T3/T4/T5 触发器 | Phase 11 | 闭环尾部，强 should |
| P1-2 | 3 类基础告警 | Phase 11 | 闭环尾部，强 should |
| P1-3 | 资讯收藏聚合视图 | Phase 8 | 可随 Phase 8 并行 |
| P1-4 | 复利仪表盘 | Phase 12 | 可见价值 |
| P1-5 | 4 模式 UI | Phase 12 | 可见价值 |
| P1-6 | KnowledgePlanningPanel | Phase 12 | 规划引导 |
| P1-7 | Hybrid AI | Phase 15 | 性能提升，依赖 Phase 8-11 |
| P1-8 | 6 新 collector | Phase 10 | 扩展性补充 |
| P1-9 | 子系统联动 | Phase 13 | 扩展性补充 |

### P2（could）— 严格后置或放弃

| P2-1 | 注意力热图 | Phase 16 | M4 末 |
| P2-2 | 整理/复习（SM-2）模式 | Phase 16 | M4 末 |
| P2-3 | chunks 字段 | Phase 16 | M4 末 |
| P2-4 | Twitter/X 抓取 | v2.1 | 推迟 |
| P2-5 | Email/Webhook 输出 | v2.1 | 推迟 |
| P2-6 | Quick Capture 插件 | v2.2 | 推迟 |
| P2-7 | 向量化语义搜索 | 不做 | 永久移除 |

---

## 附录：文件清单

### 新增后端文件

```
backend/services/simhash.py                    # Phase 8: 64-bit simhash
backend/api/mcp_phase8.py                      # Phase 8: 4 new MCP tools
backend/services/imported_aggregator.py         # Phase 8: 资讯收藏聚合
backend/api/knowledge_imported.py               # Phase 8: 聚合 API
backend/services/kl_state_machine.py            # Phase 9: 状态机引擎
backend/services/triggers/t1_raw_to_refine.py   # Phase 9: T1 触发器
backend/services/triggers/t2_refine_to_link.py  # Phase 9: T2 触发器
backend/services/retry_policy.py                # Phase 9: 重试策略
backend/metrics/kl_metrics.py                   # Phase 9: Prometheus 指标
backend/collectors/session.py                   # Phase 10: BackendSession
backend/collectors/id_factory.py                # Phase 10: 可读 ID
backend/parsers/trafilatura_parser.py           # Phase 10: trafilatura
backend/collectors/hn_collector.py              # Phase 10: HackerNews
backend/collectors/reddit_collector.py          # Phase 10: Reddit
backend/collectors/openbb_collector.py          # Phase 10: OpenBB
backend/collectors/telegram_collector.py        # Phase 10: Telegram
backend/collectors/gdelt_collector.py           # Phase 10: GDELT
backend/collectors/ossinsight_collector.py      # Phase 10: OSS Insight
backend/services/triggers/t3_link_to_structure.py  # Phase 11: T3
backend/services/triggers/t4_structure_to_publish.py  # Phase 11: T4
backend/services/triggers/t5_publish_to_refine.py    # Phase 11: T5
backend/services/alert_engine.py                # Phase 11: 告警引擎
backend/services/codegarden_drift.py            # Phase 13: drift 联动
backend/services/cve_knowledge_sync.py          # Phase 13: CVE 同步
backend/services/llm_service.py                 # Phase 15: LLMService
backend/parsers/crawl4ai_parser.py              # Phase 15: Crawl4ai
backend/services/attention_scorer.py            # Phase 16: attention 计算
config/llm.yaml                                 # Phase 15: LLM 配置
config/pipeline.json                            # Phase 10: Pipeline 配置
config/kl_thresholds.json                       # Phase 9: 阈值配置
```

### 新增前端文件

```
frontend/src/components/knowledge/KnowledgeFavoritesView.tsx    # Phase 8
frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx  # Phase 12
frontend/src/components/knowledge/BriefingMode.tsx              # Phase 12
frontend/src/components/knowledge/ScanMode.tsx                  # Phase 12
frontend/src/components/knowledge/DeepReadMode.tsx              # Phase 12
frontend/src/components/knowledge/AlertMode.tsx                 # Phase 12
frontend/src/components/knowledge/KnowledgePlanningPanel.tsx    # Phase 12
frontend/src/components/AlertCenter.tsx                         # Phase 11
frontend/src/components/knowledge/AttentionHeatmap.tsx          # Phase 16
frontend/src/components/knowledge/OutboxMode.tsx                # Phase 16
frontend/src/components/knowledge/ReviewMode.tsx                # Phase 16
frontend/src/hooks/useImported.ts                               # Phase 8
```

### 新增数据库迁移

```
backend/repository/migrations/043_v2.0_fingerprints_scores.sql  # Phase 8
backend/repository/migrations/044_v2.0_kl_rename.sql            # Phase 9
backend/repository/migrations/045_v2.0_drop_kv_cache.sql        # Phase 14
backend/repository/migrations/046_v2.0_chunks.sql               # Phase 16
```

### 新增文档

```
docs/v1_to_v2_migration.md          # Phase 14
docs/hotspot_v2_user_guide.md       # Phase 14
```