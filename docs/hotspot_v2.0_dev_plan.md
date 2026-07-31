# hotspot v2.0 开发计划

> 基于 `hotspot_v2.0_PRD.md`（4087 行）制定
> 版本: 2026-07-29 · 总周期: ~46 天 · 4 个里程碑 · 10 个 Phase · 24 条需求
> 状态: Phase 8 (v2.0)、Phase 9 (v1.9)、Phase 10 (v2.0 T1/T2) 已完成，**当前 Phase: 11 (抓取层现代化)**
>
> > **Phase 编号说明**: 本计划中 Phase 9 为 v1.9 资讯抓取流程标准化（catchup_checkpoints + collect_validations + 结构化日志），Phase 10 为 v2.0 T1/T2 触发器实施。后续 Phase 11–17 对应 PRD B.10 章节中的 Phase 11–17。

---

## 目录

1. [概述与关键数字](#1-概述与关键数字)
2. [里程碑总览（M1-M4）](#2-里程碑总览m1-m4)
3. [Phase 详细任务分解](#3-phase-详细任务分解)
   - Phase 8-10：已完成（详见下方摘要）
   - [Phase 11：抓取层现代化](#phase-11抓取层现代化5-天)
   - [Phase 12：T3/T4/T5 触发器 + 告警系统](#phase-12t3t4t5-触发器--告警系统6-天)
   - [Phase 13：复利可视化 + 4 模式 + 规划引导](#phase-13复利可视化--4-模式--规划引导4-天)
   - [Phase 14：子系统联动](#phase-14子系统联动3-天)
   - [Phase 15：清理 + 文档 + 迁移](#phase-15清理--文档--迁移5-天)
   - [Phase 16：Hybrid AI](#phase-16hybrid-aicrawl4ai--本地-llm--外部-agent-并存6-天)
   - [Phase 17：Chunks + Attention Heatmap + 6 模式完整](#phase-17chunks--attention-heatmap--6-模式完整7-天)
4. [依赖关系与关键路径](#4-依赖关系与关键路径)
5. [验收标准速查](#5-验收标准速查)
6. [迁移策略](#6-迁移策略)
7. [风险与对策](#7-风险与对策)
8. [优先级排序逻辑](#8-优先级排序逻辑)

---

## 1. 概述与关键数字

| 维度 | 值 |
|------|-----|
| 总周期 | ~46 天（6+0+4+5+6+4+3+5+6+7） |
| 已完成 | 16 天（Phase 8/9/10） |
| 剩余 | ~30 天（Phase 11~17） |
| 里程碑数 | 4（M1 已完成，M2~M4 待执行） |
| Phase 数 | 10（Phase 8~17，7 个待完成） |
| 需求总数 | 24（P0×8 + P1×9 + P2×7） |
| M1 已完成 | P0 全部交付 + 首轮可发布 |
| 新增数据表 | 6 张（4 核心 + 1 扩展 + 1 chunks） |
| 新增 MCP tool | 4 个（已交付：score_item / enrich_concept / link_items / trigger_codegarden_drift） |
| 待删除 MCP tool | 4 个（trigger_extract_tags / mark_digest_read / create_alert_rule / trigger_cubox_sync） |
| 当前调度器 job | 22 个（已注册并运行） |
| 目标调度器 job | 30 个（新增 8 个：T3/T4/T5/T½/T¾/alert/planning/attention） |
| 新增 collector | 6 个（hn / reddit / openbb / telegram / gdelt / ossinsight）|
| 核心路径 | 4 表 → 去重/评分 → T1 → T2 → 日增量 → T3/T4/T5 → 联动 → Hybrid AI → 体验项 |

---

## 2. 里程碑总览（M1-M4）

| 里程碑 | Phase | 天数 | 状态 | 关键交付物 |
|--------|-------|------|------|-----------|
| **M1：复利底座 + 闭环核心** | Phase 8→10 | ~18d | ✅ **已完成** | simhash/4 表/4 MCP tool/收藏聚合/状态机/T1/T2/dead_letter/指标 |
| **M2：抓取 + 状态机完整** | Phase 11→12 | ~11d | ⏳ **当前** | BackendSession/6 collector/可读ID/T3/T4/T5/告警引擎/AlertCenter |
| **M3：可视化 + 联动** | Phase 13→14 | ~7d | ⏳ **待进行** | 复利仪表盘/4 模式 UI/PlanningPanel/tech_stack_drift/CVE 同步 |
| **M4：AI + 体验闭环** | Phase 15→17 | ~18d | ⏳ **待进行** | LLMService/Crawl4ai/chunks/attention/6 模式完整 |

---

## 3. Phase 详细任务分解

### Phase 8：复利基础设施 + 资讯收藏聚合（6 天）✅ 已完成

**交付日期**: 2026-07-22 ~ 2026-07-27

**产出文件**:
- `backend/services/simhash.py` — 64-bit simhash 去重
- `backend/api/mcp_phase8.py` — 4 个新 MCP tool（score_item / enrich_concept / link_items / trigger_codegarden_drift）
- `backend/services/imported_aggregator.py` — 资讯收藏聚合
- `backend/api/knowledge_imported.py` — 聚合 API
- `frontend/src/components/knowledge/KnowledgeFavoritesView.tsx` — 收藏视图
- `frontend/src/hooks/useImported.ts` — 聚合 hook
- `backend/repository/migrations/043_v2.0_fingerprints_scores.sql` — 4 张新表

**Phase 8 门禁**:
- 去重率 ≥ 95%（simhash + URL canonicalize 联合测试）
- 13 个 MCP tool 全部调通
- 4 张新表 CRUD 正常
- 收藏聚合视图 e2e 8 用例通过
- 详细变更日志见 [docs/phase8_changelog.md](phase8_changelog.md)

---

### Phase 9 (v1.9)：资讯抓取流程标准化（4 天）✅ 已完成

**交付日期**: 2026-07-22 ~ 2026-07-25

**产出文件**:
- `backend/repository/migrations/042_v2.0_catchup_validations.sql` — catchup_checkpoints + collect_validations 表
- 抓取流程结构化日志 / 断点续传 / 4 类验证（完整性/一致性/时效性/异常检测）
- 详细变更日志见 [docs/phase9_changelog.md](phase9_changelog.md)

---

### Phase 10：T1/T2 触发器实施（4 天）✅ 已完成

**交付日期**: 2026-07-28

**产出文件**:
- `backend/services/kl_state_machine.py` — 5 阶段状态机引擎
- `backend/services/triggers/t1_raw_to_refine.py` — T1 触发器（60s 调度）
- `backend/services/triggers/t2_refine_to_link.py` — T2 触发器（120s 调度）
- `backend/services/retry_policy.py` — 重试策略 + 死信队列
- `backend/metrics/kl_metrics.py` — Prometheus 指标
- `backend/repository/migrations/044_v2.0_kl_dead_letters.sql` — kl_dead_letters 表
- `backend/repository/migrations/045_v2.0_kl_trigger_created_by.sql` — trigger_created_by 字段
- 调度器新增 3 个 job: kl_trigger_t1 / kl_trigger_t2 / kl_dead_letter_retry
- API: `/api/kl/metrics` (6 counters + by_stage_count gauge + 2 histograms)

**Phase 10 门禁**:
- 5 阶段状态机转换合法性 (50/50 单测)
- T1 触发器 (12/12) + T2 触发器 (10/10) 全通过
- 重试 + 死信 (11/11) + 指标 (15/15) + 集成 (6/6) 全通过
- 调度器 job 注册并运行
- 详细变更日志见 [docs/phase10_changelog.md](phase10_changelog.md)

> **✅ 前置操作已完成**: `046_lifecycle_v2.sql` 迁移已于 2026-07-29 执行。75 条旧 3 阶段值已迁移（`generate`→`kl:structure` 74 条, `signal`→`kl:raw` 1 条），残留 0 条。

---

### Phase 11：抓取层现代化（~5 天）

**目标**: BackendSession 统一注入、可读 ID 规范化、trafilatura 可选集成、6 个新 collector。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **11.2 BackendSession** | `backend/collectors/session.py`：httpx + proxy + retry + rate-limit | 无 | 1d |
| **11.3 可读 ID 规范化** | `backend/collectors/id_factory.py`：`{source}:{subtype}:{native_id}` 工厂 | 11.2 | 1d |
| **11.4 trafilatura 集成** | `backend/parsers/trafilatura_parser.py`：作为 optional extractor | 无 | 0.5d |
| **11.5 6 个新 collector** | hn / reddit / openbb / telegram / gdelt / ossinsight 各 5 用例 | 11.2 | 2d |
| **11.6 JSON pipeline_config** | `config/pipeline.json`：4 源示例 + 阈值 + 输出 | 无 | 0.5d |
| **11.7 测试** | 6 collector × 5 用例 + BackendSession 注入测试 + trafilatura | 全部 | 0.5d |

**Phase 11 门禁**:
- 6 collector × 5 用例全部通过
- 可读 ID 100% 映射（无 None / 空 ID）
- trafilatura fallback 正常
- BackendSession 注入 + retry + rate-limit 验证通过

---

### Phase 12：T3/T4/T5 触发器 + 告警系统（~6 天）

**目标**: 完成 5 阶段状态机全部触发器，交付 3 类基础告警规则。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **12.1 T3 实施** | `backend/services/triggers/t3_link_to_structure.py`：600s 调度 + 关联数检查 + 摘要生成 | Phase 10 | 1d |
| **12.2 T4 实施** | `backend/services/triggers/t4_structure_to_publish.py`：1800s 调度 + 阈值 + 24h 稳定 + .md 写入 | Phase 10 | 1d |
| **12.3 T5 实施** | `backend/services/triggers/t5_publish_to_refine.py`：用户主动 + 备份 + stale 标记 | Phase 10 | 0.5d |
| **12.4 调度器扩展** | 注册 kl_trigger_t3 / t4（T5 走用户主动调用）| 12.1/12.2 | 0.5d |
| **12.5 告警规则引擎** | `backend/services/alert_engine.py`：3 类基础规则 + 规则存储 | 无 | 1d |
| **12.6 告警规则 1** | tech_stack 影响：新 CVE 命中 cg_projects.tech_stack | 12.5 | 0.5d |
| **12.7 告警规则 2** | 关键 CVE：NVD CVSS ≥ 9.0 | 12.5 | 0.5d |
| **12.8 告警规则 3** | 标讯命中：标讯关键词命中 tech_stack | 12.5 | 0.5d |
| **12.9 告警 UI** | `frontend/src/components/AlertCenter.tsx`：Inbox + 红色横幅 | 12.5 | 1d |
| **12.10 测试** | test_t3/t4/t5 + test_alert_engine | 全部 | 0.5d |

**T3 验证**: 关联数 ≥ 3 的 items 100% 推进到 structure
**T4 验证**: score ≥ 8 的 items 100% 自动发布
**T5 验证**: 用户回滚 100% 不丢用户编辑

---

### Phase 13：复利可视化 + 4 模式 + 规划引导（~4 天）

**目标**: 交付复利仪表盘、4 种核心认知模式 UI、KnowledgePlanningPanel 规划引导。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **13.1 复利仪表盘** | `KnowledgeCompoundingDashboard.tsx`：日/周/月趋势 + top concepts + 断点告警 | Phase 11/12 | 1d |
| **13.2 简报模式 UI** | `BriefingMode.tsx`：每日首次打开 + 一句话摘要 + 3 篇关键文章 + 数据源状态 | 无 | 0.5d |
| **13.3 快速扫描 UI** | `ScanMode.tsx`（即当前首页）：分类 + 标签 + 时间筛选列表 | 无 | 0.5d |
| **13.4 深度阅读 UI** | `DeepReadMode.tsx`：文章全屏 + 右侧栏（推荐/笔记/影响/触发器状态）| 无 | 0.5d |
| **13.5 告警模式 UI** | `AlertMode.tsx`：红色横幅 + 告警中心 Inbox | Phase 12 | 0.5d |
| **13.6 触发器状态可视化** | knowledge_items 详情页显示 5 阶段进度条 | Phase 12 | 0.5d |
| **13.7 KnowledgePlanningPanel** | 基于 reading_states + lifecycle + KL 状态生成个性化规划动作 | 无 | 1d |
| **13.8 planning_action_check job** | 注册 planning_action_check 每 10min | 无 | 0.5d |
| **13.9 测试** | 4 模式组件 + dashboard + planning panel 渲染测试 | 全部 | 0.5d |

> 注：6 种认知模式中的「整理模式（Outbox）」和「复习模式（SM-2）」由 Phase 17 实施，因依赖 chunks + attention_score + sm2_reviews 等基础设施。

---

### Phase 14：子系统联动（~3 天）

**目标**: 打通 Knowledge ↔ Codegarden ↔ Security 三子系统联动。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **14.1 tech_stack_drift 任务** | `backend/services/codegarden_drift.py`：knowledge 新 tech → codegarden 评估 | 无 | 1d |
| **14.2 CVE 双向同步** | `backend/services/cve_knowledge_sync.py`：双向去重 + sync retry + 死信 | 无 | 1d |
| **14.3 跨域 entity 命名空间** | entity_type 统一：concept/tool/vendor/person/cve/technique/standard/event | 无 | 0.5d |
| **14.4 Security Graph 引用 Knowledge** | security.cve_nodes.cve_id → knowledge.item_entities[entity_name] | 14.2 | 0.5d |
| **14.5 测试** | 联动场景测试 15+ 用例 | 全部 | 0.5d |

---

### Phase 15：清理 + 文档 + 迁移（~5 天）

**目标**: 删除遗留代码和路由，编写迁移指南和用户文档。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **15.1 删 kv_cache** | `migration 047_v2.0_drop_kv_cache.sql` | 无 | 0.5d |
| **15.2 删 /api/agent/* 路由** | 移除 deprecated 路由 | 无 | 0.5d |
| **15.3 删 4 个 MCP tool** | trigger_extract_tags / mark_digest_read / create_alert_rule / trigger_cubox_sync | 无 | 1d |
| **15.4 写 v2.0 迁移指南** | `docs/v1_to_v2_migration.md`：5 阶段映射 + 触发器启用步骤 | 无 | 1d |
| **15.5 写 v2.0 用户文档** | `docs/hotspot_v2_user_guide.md`：5 触发器说明 + 4 模式使用 | 无 | 1d |
| **15.6 更新 CHANGELOG** | `docs/CHANGELOG.md`：v2.0 新增功能 + 破坏性变更 | 无 | 0.5d |
| **15.7 更新 README** | 同步到 v2.0 状态（5 子系统、13 MCP tool、5 阶段） | 无 | 0.5d |

---

### Phase 16：Hybrid AI（Crawl4ai + 本地 LLM + 外部 Agent 并存）（~6 天）

**目标**: 引入可选本地 LLM 能力，Crawl4ai 高阶抓取，T1/T3 延迟大幅降低。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **16.1 LLM 配置文件 schema** | `config/llm.yaml` + 校验 + 文档 | 无 | 0.5d |
| **16.2 LLMService 实现** | `backend/services/llm_service.py`：多 provider + 降级 + 缓存 | 无 | 1d |
| **16.3 评分任务迁移 T1** | T1 评分从 MCP `score_item` 改 `llm_service.score()` | 16.2 | 1d |
| **16.4 摘要任务迁移 T3** | T3 摘要从 MCP `enrich_concept` 改 `llm_service.summarize()` | 16.2 | 1d |
| **16.5 Crawl4ai 集成** | `backend/parsers/crawl4ai_parser.py` + 4 源迁移 | 无 | 1.5d |
| **16.6 配置降级矩阵** | 5 种缺失配置场景的降级行为 | 16.2 | 0.5d |
| **16.7 成本监控** | cost_alert 触发 + 日/月 USD 限额 | 16.2 | 0.5d |
| **16.8 测试** | test_llm_service / test_crawl4ai / test_hybrid_ai | 全部 | 1d |

**关键验收**:
- LLMService 多 provider 工作（Ollama + Qwen + OpenAI）
- Crawl4ai 4 源抓取成功率 ≥ 80%
- T1 评分延迟降低 ≥ 60%
- T3 摘要延迟降低 ≥ 40%
- 5 种降级场景全通过

---

### Phase 17：Chunks + Attention Heatmap + 6 模式完整（~7 天）

**目标**: v2.0 收尾 Phase，完成 chunks 段落级引用、attention_score 注意力热图、6 种认知模式全部实施。

| 任务 | 产出 | 前置 | 估算 |
|------|------|------|------|
| **17.1 chunks 字段迁移** | `migration 048_v2.0_chunks.sql` + `knowledge_chunks` 表 | 无 | 0.5d |
| **17.2 chunk 级 FTS5** | search_knowledge 支持 chunk_index 返回 | 17.1 | 1d |
| **17.3 chunk 级 UI** | 深度阅读模式高亮 chunk，点击跳转原文 | 17.1 | 1d |
| **17.4 attention_score 计算** | `backend/services/attention_scorer.py`：5 维度加权 | 无 | 0.5d |
| **17.5 attention 事件采集** | 前端埋点：view/dwell/scroll/favorite/annotation | 17.4 | 0.5d |
| **17.6 attention 聚合 job** | attention_aggregate 每 30 分钟跑一次 | 17.5 | 0.5d |
| **17.7 AttentionHeatmap 组件** | `AttentionHeatmap.tsx`：30 天 × 时间段热图 | 17.6 | 1d |
| **17.8 整理模式（Outbox）UI** | `OutboxMode.tsx`：清单视图 + attention_score 排序 | 17.4 | 1d |
| **17.9 复习模式（SM-2）** | `ReviewMode.tsx` + SM-2 算法 + sm2_reviews 表 | 无 | 1.5d |
| **17.10 4 模式 UI 完善** | chunk 高亮、attention 显示 | 17.3/17.7 | 1d |
| **17.11 测试** | test_chunks / test_attention / test_6_modes | 全部 | 0.5d |

**验收**: 6 种认知模式全部在 UI 可用；知识库每条 items 含 chunks + attention_score；用户可在简报模式看到 30 天热图。

---

## 4. 依赖关系与关键路径

### 关键路径（串行链）

```
P0-2 四张表 → P0-1 去重/P0-5 评分 → P0-3 T1 → P0-4 T2
→ P0-6 日增量(Phase 10–12) → P1-1 T3/T4/T5 → P1-9 联动
→ P1-7 Hybrid AI → P2 体验项
```

**已完成**: P0-1~P0-6 全部交付（Phase 8 + Phase 10）
**当前**: P0-7 可读 ID 规范化（Phase 11）、P0-6 完整日增量（Phase 11/12）

### 强前置

| 前置 | 后续 | 原因 |
|------|------|------|
| Phase 8 全部 | Phase 10 T1/T2 | T1 依赖 simhash + 评分 |
| T1/T2 (P0-3/4) | T3/T4/T5 (P1-1) | 状态机链式推进 |
| T1/T2 (P0-3/4) | P0-6 日增量 | 没有触发器日增量 = 0 |
| Phase 11 | Phase 12 可视化 | 仪表盘需要触发器数据 + 6 collector 数据 |
| Phase 12 | Phase 13 告警模式 UI | AlertCenter 需要告警引擎 |
| 046 迁移 | Phase 11 | lifecycle 旧 3 阶段 → kl:* 5 阶段 |
| Phase 16 Hybrid AI | Phase 17 | LLMService 是 chunk 摘要前置 |

### 弱依赖/可并行

| 任务 | 不阻塞主链 | 建议并行时段 |
|------|-----------|-------------|
| P1-8 6 新 collector | ✅ | Phase 11 早期并行 |
| P0-8 遗留清理 | ✅（独立于新功能）| M2 末灰度 |
| Phase 14 文档 | ✅ | 任意时段 |
| Phase 14 子系统联动 | ✅ | Phase 12 后任意时段 |

---

## 5. 验收标准速查

### 北极星指标

| 指标 | 目标 | 当前值 | 验收方式 |
|------|------|--------|---------|
| 知识库日增量 | ≥ 10 items/天 | — | 30 天平均值 |
| 新信息复用率 | ≥ 30% | — | item_entities 关联到已有 concept 比例 |
| MCP tool 调用 P95 | < 500ms | — | Phase 8 性能测试 |
| 跨源去重准确率 | ≥ 95% | ✅ 已验收 | simhash + URL canonicalize 联合测试 |
| 评分后入库延迟 | < 5 min | ✅ 已验收 | 评分完成到 knowledge_items 创建 |
| 收藏聚合视图响应 | < 300ms P95 | ✅ 已验收 | `/api/knowledge/imported` 性能测试 |

### Phase 门禁速查

| Phase | 关键门禁 |
|-------|---------|
| 8 | ✅ 去重率 ≥ 95%；13 tool 调通；4 表 CRUD；收藏视图 e2e 8 用例 |
| 9 | ✅ 抓取标准化 + 断点续传 + 4 类验证 |
| 10 | ✅ T1 推进 95%+；T2 关联发现率 ≥ 80%；指标全 |
| 11 | 6 collector × 5 用例；可读 ID 100% 映射；trafilatura fallback |
| 12 | T3/T4/T5 工作；3 类告警规则触发；AlertCenter 渲染 |
| 13 | 仪表盘渲染；daily_digest 自动生成；planning panel 动作建议 |
| 14 | drift 触发评估；cve 双向同步；跨域 entity 命名空间 |
| 15 | kv_cache 删；/api/agent 删；4 tool 移；迁移指南完整 |
| 16 | LLMService 多 provider；Crawl4ai 4 源 ≥ 80%；延迟降 60%+ |
| 17 | 6 模式全可用；chunks + attention_score；热图渲染；SM-2 卡片翻转 |

---

## 6. 迁移策略

### 6.1 数据迁移（migration 042-048）

| 迁移 | 阶段 | 内容 | 状态 |
|------|------|------|------|
| 042 | Phase 9 | catchup_checkpoints + collect_validations 表 | ✅ 已执行 |
| 043 | Phase 8 | content_fingerprints / ai_scores / item_entities / knowledge_links | ✅ 已执行 |
| 044 | Phase 10 | kl_dead_letters 表 | ✅ 已执行 |
| 045 | Phase 10 | kl_trigger_created_by 字段 | ✅ 已执行 |
| 046 | Phase 11 | lifecycle 旧 3 阶段 → kl:* 5 阶段前缀 | ✅ 已执行（2026-07-29） |
| 047 | Phase 15 | DROP kv_cache 表 | ⏳ 待创建 |
| 048 | Phase 17 | knowledge_chunks 表 + chunk 级 FTS5 | ⏳ 待创建 |

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
| trigger_extract_tags | 计划删除 → T1 触发器自动 |
| trigger_cubox_sync | 计划删除 → 本地 cron job |
| create_alert_rule | 推迟 v2.1 |
| mark_digest_read | 计划删除 → reading_states 自动追踪 |
| 5 读 tool | 保持 |
| 4 保留写 tool | 保持 |
| 4 新增 v2.0 tool | ✅ 已新增 |

### 6.4 部署步骤（Phase 17 完成后）

1. 停止 hotspot 服务
2. 备份数据库：`cp hotspot.db hotspot.db.v2.0.backup`
3. 执行 migration 046-048（顺序执行）
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
| 严重 bug | 用 `hotspot.db.v2.0.backup` 还原 |

---

## 7. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 | 阶段 |
|---|------|------|------|------|------|
| 1 | 单人 30 天密集交付压力 | 高 | 高 | M2 硬承诺，M3-M4 渐进缓冲；P2 可延期至 v2.1 | 全部 |
| 2 | simhash 误判（不同新闻被合并） | 中 | 中 | ✅ 阈值 5 起步，已上线监控 | Phase 8 |
| 3 | AI 评分波动（同一新闻两次评分差大） | 高 | 中 | ✅ 存多版本评分；v2.0 不自动应用，v2.1 引入置信度 | Phase 8 |
| 4 | 自动入库导致知识库噪声 | 中 | 中 | ✅ 阈值 ≥ 7 才入；v2.0 不自动应用 knowledge_links | Phase 10 |
| 5 | 6 个新 collector 反爬失败 | 中 | 低 | 先实现 3 个（hn/rss/openbb），其余 3 个 v2.1 | Phase 11 |
| 6 | 可读 ID 迁移复杂 | 中 | 中 | 保留 hash ID 作为 alias；v2.0 双写，v2.1 切读路径 | Phase 11 |
| 7 | 外部 AI Agent 不支持 score_item | 中 | 高 | ✅ 保留 manual add_favorite 路径；评分先存后用 | Phase 8 |
| 8 | 本地 LLM 硬件门槛 | 中 | 高 | 提供云端降级/可选路径，不将本地 LLM 设为闭环硬依赖 | Phase 16 |
| 9 | 知识库日增量 < 10 items | 中 | 高 | 监控告警；分析原因（评分太严？源失效？）；调阈值或源 | Phase 11→12 |
| 10 | 5 触发器互相等待死锁 | 低 | 高 | T2/T4 加 hard timeout + 自动 fallback；kl_dead_letter_retry 兜底 | Phase 12 |
| 11 | 删 /api/agent 路由破坏旧 agent | 低 | 中 | v2.0 保留 deprecated 1 个 minor 版本，v2.1 完全删 | Phase 15 |
| 12 | attention_score 数据稀疏 | 高 | 中 | v2.0 启动时 backfill 从 SQLite history 推断初始 score | Phase 17 |

---

## 8. 优先级排序逻辑

### P0（must）— 复利闭环核心，M1 硬交付 ✅ 已完成

| 编号 | 需求 | 所属 Phase | 状态 |
|------|------|-----------|------|
| P0-1 | simhash 跨源去重 | Phase 8 | ✅ |
| P0-2 | 新增 4 张数据表 | Phase 8 | ✅ |
| P0-3 | T1 触发器 raw→refine | Phase 10 | ✅ |
| P0-4 | T2 触发器 refine→link | Phase 10 | ✅ |
| P0-5 | AI 评分 MCP tool | Phase 8 | ✅ |
| P0-6 | 知识库自动入库（日增量） | Phase 10–12 | ✅ 部分 |
| P0-7 | 可读 ID 规范化 | Phase 11 | ⏳ |
| P0-8 | 遗留清理 | Phase 15 | ⏳ |

### P1（should）— 渐进交付，顺序可调

| 编号 | 需求 | 所属 Phase | 优先级排序理由 |
|------|------|-----------|---------------|
| P1-1 | T3/T4/T5 触发器 | Phase 12 | 闭环尾部，强 should |
| P1-2 | 3 类基础告警 | Phase 12 | 闭环尾部，强 should |
| P1-3 | 复利仪表盘 | Phase 13 | 可见价值 |
| P1-4 | 4 模式 UI | Phase 13 | 可见价值 |
| P1-5 | KnowledgePlanningPanel | Phase 13 | 规划引导 |
| P1-6 | Hybrid AI | Phase 16 | 性能提升，依赖 Phase 8-11 |
| P1-7 | 6 新 collector | Phase 11 | 扩展性补充 |
| P1-8 | 子系统联动 | Phase 14 | 扩展性补充 |
| P1-9 | 迁移指南 + 用户文档 | Phase 15 | 发布门禁 |

### P2（could）— 严格后置或放弃

| 编号 | 需求 | 所属 Phase | 备注 |
|------|------|-----------|------|
| P2-1 | 注意力热图 | Phase 17 | M4 末 |
| P2-2 | 整理/复习（SM-2）模式 | Phase 17 | M4 末 |
| P2-3 | chunks 字段 | Phase 17 | M4 末 |
| P2-4 | Twitter/X 抓取 | v2.1 | 推迟 |
| P2-5 | Email/Webhook 输出 | v2.1 | 推迟 |
| P2-6 | Quick Capture 插件 | v2.2 | 推迟 |
| P2-7 | 向量化语义搜索 | 不做 | 永久移除 |

---

## 附录：文件清单

### 新增后端文件（已交付）

```
backend/services/simhash.py                    # Phase 8: 64-bit simhash
backend/api/mcp_phase8.py                      # Phase 8: 4 new MCP tools
backend/services/imported_aggregator.py         # Phase 8: 资讯收藏聚合
backend/api/knowledge_imported.py               # Phase 8: 聚合 API
backend/services/kl_state_machine.py            # Phase 10: 状态机引擎
backend/services/triggers/t1_raw_to_refine.py   # Phase 10: T1 触发器
backend/services/triggers/t2_refine_to_link.py  # Phase 10: T2 触发器
backend/services/retry_policy.py                # Phase 10: 重试策略
backend/metrics/kl_metrics.py                   # Phase 10: Prometheus 指标
```

### 新增后端文件（待开发）

```
backend/collectors/session.py                   # Phase 11: BackendSession
backend/collectors/id_factory.py                # Phase 11: 可读 ID
backend/parsers/trafilatura_parser.py           # Phase 11: trafilatura
backend/collectors/hn_collector.py              # Phase 11: HackerNews
backend/collectors/reddit_collector.py          # Phase 11: Reddit
backend/collectors/openbb_collector.py          # Phase 11: OpenBB
backend/collectors/telegram_collector.py        # Phase 11: Telegram
backend/collectors/gdelt_collector.py           # Phase 11: GDELT
backend/collectors/ossinsight_collector.py      # Phase 11: OSS Insight
backend/services/triggers/t3_link_to_structure.py   # Phase 12: T3
backend/services/triggers/t4_structure_to_publish.py  # Phase 12: T4
backend/services/triggers/t5_publish_to_refine.py     # Phase 12: T5
backend/services/alert_engine.py                # Phase 12: 告警引擎
backend/services/codegarden_drift.py            # Phase 14: drift 联动
backend/services/cve_knowledge_sync.py          # Phase 14: CVE 同步
backend/services/llm_service.py                 # Phase 16: LLMService
backend/parsers/crawl4ai_parser.py              # Phase 16: Crawl4ai
backend/services/attention_scorer.py            # Phase 17: attention 计算
config/llm.yaml                                 # Phase 16: LLM 配置
config/pipeline.json                            # Phase 11: Pipeline 配置
config/kl_thresholds.json                       # Phase 11: 阈值配置
```

### 新增前端文件（已交付）

```
frontend/src/components/knowledge/KnowledgeFavoritesView.tsx    # Phase 8
frontend/src/hooks/useImported.ts                               # Phase 8
```

### 新增前端文件（待开发）

```
frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx  # Phase 13
frontend/src/components/knowledge/BriefingMode.tsx              # Phase 13
frontend/src/components/knowledge/ScanMode.tsx                  # Phase 13
frontend/src/components/knowledge/DeepReadMode.tsx              # Phase 13
frontend/src/components/knowledge/AlertMode.tsx                 # Phase 13
frontend/src/components/knowledge/KnowledgePlanningPanel.tsx    # Phase 13
frontend/src/components/AlertCenter.tsx                         # Phase 12
frontend/src/components/knowledge/AttentionHeatmap.tsx          # Phase 17
frontend/src/components/knowledge/OutboxMode.tsx                # Phase 17
frontend/src/components/knowledge/ReviewMode.tsx                # Phase 17
```

### 新增数据库迁移

```
backend/repository/migrations/043_v2.0_fingerprints_scores.sql  # Phase 8 ✅
backend/repository/migrations/044_v2.0_kl_dead_letters.sql      # Phase 10 ✅
backend/repository/migrations/045_v2.0_kl_trigger_created_by.sql # Phase 10 ✅
backend/repository/migrations/046_lifecycle_v2.sql               # Phase 11 ✅ 已执行
backend/repository/migrations/047_v2.0_drop_kv_cache.sql        # Phase 15 ⏳
backend/repository/migrations/048_v2.0_chunks.sql               # Phase 17 ⏳
```

### 新增文档

```
docs/v1_to_v2_migration.md          # Phase 15
docs/hotspot_v2_user_guide.md       # Phase 15
```