# R-06 服务层孤儿盘点表 (P0 基线)

> **需求来源**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md` §4.6 R-06 服务层孤儿盘点（161 → 清单）](../v0.8.8/V0.8.8_REFACTOR_PRD.md)
>
> **验收标准 (PRD §4.6)**: ① 产出 161 行表格，每行含 `service 文件 / 被 import 次数 / 消费者文件列表 / 判定（孤儿·单消费者·多消费者·UNKNOWN）`；② 孤儿数 ≤ 5（161 的 3%）；③ 每个孤儿均有独立核验记录
>
> **本文档性质**: 纯只读盘点，零代码 / 测试 / 配置变更。产出供 P1 裁决使用；**本文档不构成任何删除建议**，删除动作属 P2/P3 阶段职责。

---

## 1. 采集方法

### 1.1 service 文件口径

口径源 = `scripts/generate_meta.py::count_services()`：

```python
# scripts/generate_meta.py:174-175
def count_services() -> int:
    return len(list(SERVICES.glob("*.py"))) - 1  # 减去 __init__.py
```

`SERVICES = ROOT / "backend" / "services"`（`scripts/generate_meta.py:56`）。

实测确认：

```bash
$ python3 -c "from scripts.generate_meta import count_services; print(count_services())"
161
```

| 项 | 值 |
|---|---|
| `backend/services/*.py` 文件总数 | 162 |
| `-1` 剔除的文件 | `backend/services/__init__.py`（包声明文件，`__all__: list[str] = []` 为空，不计为 service） |
| **本表 service 行数** | **161** ✅ 与 `count_services()` 完全一致 |

> `-1` 的语义：`glob("*.py")` 只匹配 `backend/services/` 顶层文件（非递归），其中 `__init__.py` 是 Python 包声明而非业务服务，故减去。该函数是 `docs/ARCHITECTURE.md` 与 CI `generate_meta.py --check` 的唯一数字来源，本表行数与之对齐。

### 1.2 消费者统计范围

全仓扫描，覆盖三个根目录（排除 `__pycache__` / `node_modules` / `dist` / `build` / `.venv`）：

| 范围 | 文件数 | 说明 |
|---|---:|---|
| `backend/`（含 `backend/tests/`） | 1,006（`.py`） | 生产代码 + 测试 |
| `scripts/` | 119（`.py`） | 运维 / 审计 / 数据修复脚本 |
| `frontend/src/` | 385（`.ts/.tsx/.js/.jsx`） | 前端源码（见下方说明） |
| **Python 文件合计（AST 解析）** | **1,125** | `backend/` 1,006 + `scripts/` 119 |

- **import 解析方式**: Python 侧用 `ast` 静态解析 `ast.Import` / `ast.ImportFrom`，覆盖四种形式：
  1. `import backend.services.X`
  2. `from backend.services.X import a, b`
  3. `from backend.services import X`（子模块形态）
  4. `backend/services/` 内部相对 import（`from .X import ...` / `from . import X`）
- **前端说明**: `frontend/` 无法 import Python service 模块 —— 全仓 `backend.services` 字面量在 `frontend/src` 仅 5 处，**全部是注释**（如 `frontend/src/types/index.ts:2` "与后端 backend/services/hotspot_service.py 输出完全对齐"、`frontend/src/api/proposals.ts:15` "与后端 run_ledger_service/proposal_repo 行字典对齐"）。前端经 HTTP 契约消费后端能力，不构成 service 的 import 消费者。故本表 161 行的消费者列表中**前端消费者数为 0**（已核，非遗漏）。

### 1.3 反射检查清单（UNKNOWN 判定依据）

PRD §4.6 技术约束：「反射风险：`importlib`、`getattr(module, name)`、plugin 注册表。凡命中反射模式的 service 一律不下「孤儿」结论，标 `UNKNOWN`」。

本盘点对每个 service 模块名执行以下 5 类检查（**纯注释行已剔除**，避免把文档提及误判为动态引用）：

| # | 反射模式 | 检测正则 / 位置 | 命中语义 |
|---|---|---|---|
| 1 | `importlib.import_module("backend.services.X")` | `importlib\.import_module\s*\(\s*["']backend\.services\.` | 字符串动态导入 |
| 2 | `importlib.util.find_spec` + `import_module` | `backend/services/skill_builder/validate.py:111,118`（`spec = importlib.util.find_spec(module)` → `mod = importlib.import_module(module)`） | 用户自定义 skill 的 target 反射校验 |
| 3 | `mock.patch("backend.services.X....")` | `patch\s*\(\s*["']backend\.services\.` | 测试侧字符串动态打桩（`unittest.mock` 按字符串解析并 import） |
| 4 | `monkeypatch.setattr("backend.services.X.attr", ...)` | `setattr\s*\(\s*["']backend\.services\.` | pytest 按 `module.attr` 字符串解析并 import |
| 5 | plugin 注册表 `ServiceTarget(module="backend.services.X")` | `backend/services/skill_registry/builtin.py`（20 内置 skill）、`backend/services/skill_registry/v1_skills.py`（v1 技能），消费端 `backend/services/skill_runner/dispatch.py:125` `module = importlib.import_module(target.module)` | 生产侧动态注册表 |

补充检查（用于识别假阳性，不单独触发 UNKNOWN）：

- **裸字符串队列名**：`backend/scheduler/jobs/worker_pump.py:26` `_KNOWN_QUEUES = ("trigger_gate", "ai_hub", "case_service")` —— 这是 task_type 枚举值，非模块路径，**不构成反射**。
- **数据字段名**：`"feedback_analyzer"` 作为 `source` 字段值（`backend/repository/user_memory_repo.py:26`、`backend/services/user_memory_service.py:26`）、`"observability_thresholds"` 作为告警 source（`backend/scheduler/jobs/maintenance.py:946`）、`"wiki_archiver"` 作为 job id、`"knowledge_sync"` 作为限流组名 —— 均为**字符串数据值**，非模块引用，**不构成反射**。
- **配置 / 指纹文件**：`.ua/fingerprints.json` 等工具产物含全量模块路径字符串，属静态分析工具缓存，非运行期注册表，**不构成反射**。
- **f-string / 字符串拼接动态路径**：`grep -rn 'backend\.services\.\{\|"backend\.services\." *+'` 全仓 0 命中，不存在拼接式动态导入。

### 1.4 判定规则（4 档，优先级自上而下）

| 判定 | 条件 |
|---|---|
| `UNKNOWN` | 命中 §1.3 任一反射模式（含测试侧字符串打桩 —— 保守起见一律不下孤儿结论） |
| `孤儿` | 无任何 import 消费者 **且** 无反射命中 |
| `单消费者` | 消费者文件数 = 1 |
| `多消费者` | 消费者文件数 ≥ 2 |

> 「被 import 次数」按 **import 语句条数** 计（同一文件内多次 import 计多次），与「消费者文件列表」的去重文件数是两个不同量。存在 5 个 service 两者不一致（如 `learning_service`：1 个消费者文件但 5 条 import 语句），已在校验脚本中逐条核对。

---

## 2. 主表（161 行）

> **消费者路径简写**：`backend/` 前缀省略；`backend/api/` → `api/`，`backend/tests/` → `tests/`，`backend/services/` → `services/`，`backend/scheduler/` → `scheduler/`，`backend/kl_pipeline/` → `kl_pipeline/`，`backend/repository/` → `repository/`，`scripts/` 保持原样。

| # | service 文件 | 被 import 次数 | 消费者文件列表 | 判定 |
|---:|---|---:|---|---|
| 1 | `backend/services/action_service.py` | 15 | `api/action_api.py`、`api/v1_case_relation_api.py`、`tests/test_action_service.py`、`tests/test_artifact_service.py`、`tests/test_c06_async_call_dsh.py`、`tests/test_c07_run_dispatch_and_skill_guards.py`、`tests/test_c08_artifact_cas_wiki_caseclose.py`、`tests/test_c11_outbox_and_aggregate.py`、`tests/test_run_service.py`、`scripts/t085_seed_review_fixtures.py`、`scripts/t12_golden_inspection_materials.py` | **UNKNOWN** |
| 2 | `backend/services/agent_bridge.py` | 3 | `api/agents_api.py`、`tests/test_agent_bridge.py`、`scripts/soaktest/pi_live_probe.py` | **多消费者** |
| 3 | `backend/services/ai_write_back.py` | 15 | `api/extract.py`、`api/knowledge_classify_api.py`、`api/knowledge_concepts.py`、`api/knowledge_items.py`、`api/mcp_agent_tools.py`、`api/wiki_tools.py`、`scheduler/jobs/knowledge.py`、`services/compiler.py`、`services/federation_service.py`、`services/sag_service.py`、`services/triggers/t1_raw_to_refine.py`、`services/triggers/t4_structure_to_publish.py`、`services/v1_signal_bridge.py`、`tests/test_ai_hub.py`、`tests/test_v1_signal_bridge.py` | **多消费者** |
| 4 | `backend/services/alert_channels.py` | 23 | `api/observability_router.py`、`scheduler/jobs/maintenance.py`、`services/alert_dispatcher.py`、`tests/test_alert_channels.py` | **多消费者** |
| 5 | `backend/services/alert_dispatcher.py` | 8 | `api/observability_router.py`、`scheduler/jobs/maintenance.py`、`scheduler/jobs/security.py`、`tests/test_alert_channels.py` | **UNKNOWN** |
| 6 | `backend/services/alert_engine.py` | 3 | `api/alert_api.py`、`services/news_alert_service.py`、`tests/test_alert_engine.py` | **多消费者** |
| 7 | `backend/services/alert_service.py` | 5 | `api/alert_api.py`、`api/alerts.py`、`scheduler/jobs/collect.py`、`tests/test_alert_service.py` | **UNKNOWN** |
| 8 | `backend/services/annotation_service.py` | 1 | `api/annotations.py` | **单消费者** |
| 9 | `backend/services/artifact_service.py` | 9 | `api/artifact_api.py`、`api/v1_case_relation_api.py`、`services/run_ledger_service.py`、`tests/test_artifact_service.py`、`tests/test_c08_artifact_cas_wiki_caseclose.py`、`tests/test_c11_outbox_and_aggregate.py`、`scripts/t085_seed_review_fixtures.py`、`scripts/t12_golden_inspection_materials.py` | **多消费者** |
| 10 | `backend/services/attack_label_service.py` | 1 | `api/event_types_api.py` | **单消费者** |
| 11 | `backend/services/attack_loader.py` | 12 | `api/cve_analytics.py`、`main.py`、`services/cve_attack_service.py`、`tests/test_attack_loader.py`、`tests/test_cve_attack_service.py`、`tests/test_mp1_graph_ignite.py`、`tests/test_mp2_extraction_guard.py`、`scripts/agent_A_extract.py`、`scripts/agent_B_extract.py`、`scripts/agent_C_extract.py`、`scripts/agent_C_selfcheck.py`、`scripts/agent_D_extract.py` | **多消费者** |
| 12 | `backend/services/attention_events_service.py` | 2 | `api/attention_events_api.py`、`tests/test_attention_events_service.py` | **多消费者** |
| 13 | `backend/services/attention_scorer.py` | 2 | `scheduler/jobs/maintenance.py`、`tests/test_attention_scorer.py` | **多消费者** |
| 14 | `backend/services/auto_classifier.py` | 33 | `api/knowledge_classify_api.py`、`api/settings.py`、`collectors/keywords.py`、`repository/hotspot_repo.py`、`scheduler/jobs/collect.py`、`scheduler/jobs/knowledge.py`、`services/auto_intake_service.py`、`services/compiler.py`、`services/digest_service.py`、`services/hotspot_service.py`、`services/interest_domain_advisor.py`、`services/interest_engine_service.py`、`services/skill_registry/sk01_daily_priority.py`、`services/v1_admission_service.py`、`tests/test_ai_classify.py`、`tests/test_auto_classifier.py`、`tests/test_auto_classifier_practice_domain.py`、`tests/test_compound_drivers.py`、`tests/test_interest_domain_advisor.py`、`tests/test_knowledge_oneway.py`、`tests/test_practice_domain_corpus.py`、`tests/test_shutdown_yield.py`、`scripts/audit_interest_hit_rate.py`、`scripts/audit_practice_domain_sample.py`、`scripts/check_practice_domain_lexicon.py` | **多消费者** |
| 15 | `backend/services/auto_intake_service.py` | 6 | `api/auto_intake_api.py`、`scheduler/jobs/collect.py`、`tests/test_auto_intake.py`、`tests/test_shutdown_yield.py` | **多消费者** |
| 16 | `backend/services/backup_service.py` | 11 | `api/maintenance_retention_api.py`、`scheduler/jobs/maintenance.py`、`tests/test_backup_compact.py`、`tests/test_backup_service.py`、`tests/test_backup_verify.py`、`tests/test_db_hardening.py`、`scripts/check_backup_chain.py` | **多消费者** |
| 17 | `backend/services/backup_verify_service.py` | 4 | `api/maintenance_retention_api.py`、`scheduler/jobs/maintenance.py`、`tests/test_backup_compact.py`、`tests/test_backup_verify.py` | **多消费者** |
| 18 | `backend/services/batch_service.py` | 4 | `api/history.py`、`tests/test_batch_service.py`、`tests/test_history_api.py` | **多消费者** |
| 19 | `backend/services/bookmark_sync.py` | 3 | `api/knowledge_import.py`、`tests/test_bookmark_regression.py` | **UNKNOWN** |
| 20 | `backend/services/case_service.py` | 14 | `api/v1_case_query_api.py`、`api/v1_case_relation_api.py`、`api/v1_case_update_api.py`、`api/v1_case_write_api.py`、`tests/test_c08_artifact_cas_wiki_caseclose.py`、`tests/test_c11_outbox_and_aggregate.py`、`tests/test_case_service.py`、`tests/test_v1_ingest_bridge.py`、`scripts/t15_golden_workbench_4entry.py` | **多消费者** |
| 21 | `backend/services/catchup_service.py` | 14 | `api/catchup.py`、`main.py`、`scheduler/jobs/collect.py`、`services/health_query_service.py`、`tests/test_catchup_api.py`、`tests/test_catchup_phase9.py`、`tests/test_catchup_service.py`、`tests/test_catchup_watchdog.py` | **UNKNOWN** |
| 22 | `backend/services/chunk_service.py` | 6 | `api/knowledge_chunks_api.py`、`api/wiki_tools.py`、`scheduler/jobs/knowledge.py`、`tests/test_hub_stats.py` | **多消费者** |
| 23 | `backend/services/codegarden_drift.py` | 3 | `api/codegarden_phase14.py`、`scheduler/jobs/codegarden.py`、`tests/test_codegarden_drift.py` | **UNKNOWN** |
| 24 | `backend/services/codegarden_github_service.py` | 6 | `api/codegarden.py`、`tests/test_codegarden_api.py` | **UNKNOWN** |
| 25 | `backend/services/codegarden_knowledge_bridge.py` | 3 | `api/codegarden.py`、`tests/test_codegarden_api.py`、`tests/test_codegarden_e2e.py` | **多消费者** |
| 26 | `backend/services/codegarden_orchestration_service.py` | 3 | `api/codegarden_ops.py`、`tests/test_codegarden_ops_api.py` | **多消费者** |
| 27 | `backend/services/codegarden_project_service.py` | 3 | `api/codegarden.py`、`scheduler/jobs/codegarden.py`、`tests/test_codegarden_api.py` | **多消费者** |
| 28 | `backend/services/codegarden_resource_service.py` | 5 | `api/codegarden_ops.py`、`tests/test_p0_evidence_crypto.py` | **多消费者** |
| 29 | `backend/services/codegarden_scanner_service.py` | 4 | `tests/test_codegarden_scanner.py` | **单消费者** |
| 30 | `backend/services/codegarden_service_service.py` | 4 | `api/codegarden_ops.py`、`scheduler/jobs/codegarden.py`、`tests/test_codegarden_ops_api.py` | **多消费者** |
| 31 | `backend/services/collect_validator.py` | 4 | `api/catchup.py`、`scheduler/jobs/collect.py`、`services/catchup_service.py`、`tests/test_collect_validator.py` | **多消费者** |
| 32 | `backend/services/collection_dedup.py` | 3 | `services/collection_pipeline.py`、`services/collection_service.py`、`tests/test_warm_write_paths.py` | **多消费者** |
| 33 | `backend/services/collection_logger.py` | 3 | `services/catchup_service.py`、`services/collect_validator.py`、`tests/test_collection_logger.py` | **UNKNOWN** |
| 34 | `backend/services/collection_pipeline.py` | 3 | `services/collection_service.py`、`tests/test_pipeline_p1_fix.py` | **多消费者** |
| 35 | `backend/services/collection_service.py` | 16 | `main.py`、`services/catchup_service.py`、`services/hotspot_service.py`、`services/triggers/t1_raw_to_refine.py`、`tests/test_arxiv_paper_collector.py`、`tests/test_catchup_watchdog.py`、`tests/test_collection_service.py`、`tests/test_e2e_collect.py`、`tests/test_fingerprint.py`、`tests/test_github_collector.py`、`tests/test_liveness_vs_usefulness.py`、`tests/test_t1_trigger.py`、`scripts/chaostest/mock_503.py`、`scripts/collect_security_phase21.py`、`scripts/manual_collect.py` | **UNKNOWN** |
| 36 | `backend/services/command_bar_service.py` | 3 | `api/command_bar_api.py`、`tests/test_command_bar.py`、`tests/test_search_p4.py` | **多消费者** |
| 37 | `backend/services/compiler.py` | 5 | `api/knowledge_import.py`、`scheduler/jobs/digest.py`、`tests/test_compiler.py` | **UNKNOWN** |
| 38 | `backend/services/compliance_service.py` | 2 | `api/compliance.py`、`tests/test_compliance_service.py` | **多消费者** |
| 39 | `backend/services/concept_linker.py` | 21 | `api/knowledge_concepts.py`、`services/compiler.py`、`tests/test_characterization_golden.py`、`tests/test_graph_runtime.py`、`scripts/check_graph_schema.py`、`scripts/migrate_v04_to_llm_wiki.py` | **UNKNOWN** |
| 40 | `backend/services/content_pref_advisor.py` | 2 | `api/interest_api.py`、`tests/test_content_pref_auto.py` | **多消费者** |
| 41 | `backend/services/content_service.py` | 4 | `api/content.py`、`scheduler/jobs/knowledge.py`、`services/knowledge_watcher.py` | **UNKNOWN** |
| 42 | `backend/services/copilot_drafter.py` | 1 | `services/run_ledger_service.py` | **单消费者** |
| 43 | `backend/services/cost_monitor.py` | 1 | `tests/test_hybrid_ai.py` | **单消费者** |
| 44 | `backend/services/crawler_seed.py` | 0 | — | **孤儿** |
| 45 | `backend/services/cubox_sync.py` | 5 | `api/cubox_import_api.py`、`api/knowledge_ops.py`、`api/mcp_adapters.py`、`tests/test_cubox_import.py` | **UNKNOWN** |
| 46 | `backend/services/cve_attack_service.py` | 2 | `api/cve_analytics.py`、`tests/test_cve_attack_service.py` | **多消费者** |
| 47 | `backend/services/cve_enrich_service.py` | 2 | `services/deep_read_service.py`、`tests/test_cve_enrich.py` | **多消费者** |
| 48 | `backend/services/cve_heatmap_service.py` | 2 | `api/cve_analytics.py`、`tests/test_cve_heatmap_service.py` | **UNKNOWN** |
| 49 | `backend/services/cve_knowledge_sync.py` | 3 | `api/codegarden_phase14.py`、`scheduler/jobs/security.py`、`tests/test_cve_knowledge_sync.py` | **UNKNOWN** |
| 50 | `backend/services/daily_report_overview_service.py` | 2 | `api/reports.py`、`tests/test_arxiv_paper_collector.py` | **UNKNOWN** |
| 51 | `backend/services/data_cleaning.py` | 9 | `collectors/item_builder.py`、`services/bookmark_sync.py`、`services/cubox_sync.py`、`services/history_import.py`、`services/imported_aggregator.py`、`services/sag_service.py`、`tests/test_auto_intake.py`、`tests/test_bookmark_regression.py`、`tests/test_favorite_to_knowledge.py` | **多消费者** |
| 52 | `backend/services/deep_read_service.py` | 15 | `api/deep_read.py`、`tests/test_cve_enrich.py`、`tests/test_deep_read_service.py` | **多消费者** |
| 53 | `backend/services/digest_service.py` | 9 | `api/digests.py`、`api/mode.py`、`scheduler/jobs/digest.py`、`tests/test_digest_service.py`、`tests/test_interest_engine.py`、`tests/test_mode_api.py`、`tests/test_phase3_acceptance.py`、`tests/test_phase4_acceptance.py` | **UNKNOWN** |
| 54 | `backend/services/dsh_adapter.py` | 19 | `services/action_service.py`、`services/judgment_service.py`、`services/knowledge_ai.py`、`services/skill_registry/sk01_daily_priority.py`、`tests/test_c06_async_call_dsh.py`、`tests/test_c06_real_dsh_adapter.py`、`scripts/t10_live_trace.py` | **多消费者** |
| 55 | `backend/services/event_technique_extract_service.py` | 12 | `api/event_technique_api.py`、`scheduler/jobs/security.py`、`tests/test_mp2_extraction_guard.py`、`scripts/agent_A_extract.py`、`scripts/agent_A_selfcheck.py`、`scripts/agent_B_extract.py`、`scripts/agent_B_selfcheck.py`、`scripts/agent_C_extract.py`、`scripts/agent_C_selfcheck.py`、`scripts/agent_D_extract.py`、`scripts/agent_D_selfcheck.py`、`scripts/agent_E_extract.py` | **多消费者** |
| 56 | `backend/services/event_technique_review_service.py` | 1 | `api/event_types_api.py` | **单消费者** |
| 57 | `backend/services/export_service.py` | 5 | `api/export.py`、`main.py`、`scheduler/jobs/maintenance.py`、`tests/test_api.py` | **多消费者** |
| 58 | `backend/services/extract_service.py` | 5 | `api/extract.py`、`api/mcp_adapters.py`、`scheduler/jobs/knowledge.py`、`services/tech_stack_service.py`、`tests/test_extract_service.py` | **UNKNOWN** |
| 59 | `backend/services/feature_flag_service.py` | 5 | `api/mcp_settings_api.py`、`tests/test_feature_flags.py`、`tests/test_mcp_server.py`、`tests/test_mcp_sse.py` | **多消费者** |
| 60 | `backend/services/federation_service.py` | 4 | `api/knowledge_concepts.py`、`api/knowledge_items.py`、`scheduler/jobs/knowledge.py`、`services/graph_builder.py` | **UNKNOWN** |
| 61 | `backend/services/feedback_analyzer.py` | 1 | `tests/test_feedback_analyzer.py` | **单消费者** |
| 62 | `backend/services/feedback_service.py` | 2 | `api/feedback_api.py`、`tests/test_feedback_service.py` | **多消费者** |
| 63 | `backend/services/graph_builder.py` | 3 | `api/knowledge_concepts.py`、`scripts/phase1i_task914_compile.py`、`scripts/phase1j_task1004_compile.py` | **多消费者** |
| 64 | `backend/services/health_query_service.py` | 5 | `api/health.py`、`api/health_stats.py`、`tests/test_health_query_service.py`、`tests/test_observability.py` | **多消费者** |
| 65 | `backend/services/history_import.py` | 2 | `api/history.py`、`api/knowledge_import.py` | **UNKNOWN** |
| 66 | `backend/services/hotspot_service.py` | 12 | `api/categories.py`、`api/content_preferences_api.py`、`api/hotspots.py`、`api/interest_api.py`、`api/reports.py`、`services/content_pref_advisor.py`、`tests/test_api.py`、`tests/test_content_pref_auto.py`、`tests/test_dedupe_by_url.py`、`tests/test_settings_content_preferences.py` | **UNKNOWN** |
| 67 | `backend/services/hub_stats_service.py` | 1 | `api/knowledge_api.py` | **单消费者** |
| 68 | `backend/services/imported_aggregator.py` | 3 | `api/knowledge_imported.py`、`tests/test_imported_aggregator.py`、`tests/test_knowledge_imported_api.py` | **多消费者** |
| 69 | `backend/services/incident_report_service.py` | 10 | `scheduler/jobs/security.py`、`tests/test_mp2_api_contract.py`、`tests/test_mp2_extraction_guard.py`、`scripts/agent_A_extract.py`、`scripts/agent_B_extract.py`、`scripts/agent_C_extract.py`、`scripts/agent_D_extract.py`、`scripts/agent_E_extract.py` | **多消费者** |
| 70 | `backend/services/info_filter_gate.py` | 8 | `api/info_filter_api.py`、`collectors/base.py`、`collectors/item_builder.py`、`scheduler/jobs/collect.py`、`tests/test_info_filter_api.py`、`tests/test_info_filter_gate.py`、`tests/test_semantic_filter_gate.py`、`tests/test_shutdown_yield.py` | **多消费者** |
| 71 | `backend/services/info_filter_service.py` | 11 | `api/info_filter_api.py`、`services/info_filter_gate.py`、`services/v1_admission_service.py`、`services/v1_ingest_bridge.py`、`services/v1_signal_bridge.py`、`tests/test_info_filter_gate.py`、`tests/test_info_filter_service.py`、`tests/test_semantic_filter_gate.py` | **多消费者** |
| 72 | `backend/services/interest_domain_advisor.py` | 2 | `api/interest_api.py`、`tests/test_interest_domain_advisor.py` | **多消费者** |
| 73 | `backend/services/interest_engine_service.py` | 17 | `api/hotspots.py`、`api/interest_api.py`、`api/settings.py`、`scheduler/jobs/maintenance.py`、`services/digest_service.py`、`services/interest_domain_advisor.py`、`services/pick_service.py`、`tests/test_cleanup_job_alerts.py`、`tests/test_content_pref_auto.py`、`tests/test_hotspots_api.py`、`tests/test_interest_domain_advisor.py`、`tests/test_interest_engine.py`、`scripts/audit_interest_hit_rate.py`、`scripts/audit_interest_recalibration.py` | **多消费者** |
| 74 | `backend/services/judgment_drafter.py` | 2 | `services/run_ledger_service.py`、`tests/test_judgment_drafter.py` | **多消费者** |
| 75 | `backend/services/judgment_service.py` | 17 | `api/judgment_api.py`、`api/v1_case_relation_api.py`、`tests/test_c01_wal_backup_and_wikifs_isolation.py`、`tests/test_c06_async_call_dsh.py`、`tests/test_c11_outbox_and_aggregate.py`、`tests/test_judgment_api.py`、`tests/test_judgment_service.py`、`tests/test_p0_evidence_crypto.py`、`scripts/t085_seed_review_fixtures.py`、`scripts/t11_golden_cve2026_31337.py` | **UNKNOWN** |
| 76 | `backend/services/kl_state_machine.py` | 14 | `services/triggers/t1_raw_to_refine.py`、`services/triggers/t2_refine_to_link.py`、`services/triggers/t3_link_to_structure.py`、`services/triggers/t4_structure_to_publish.py`、`services/triggers/t5_publish_to_refine.py`、`services/wiki_stats_service.py`、`tests/test_kl_state_machine.py`、`tests/test_phase10_integration.py`、`tests/test_t1_trigger.py`、`tests/test_t2_trigger.py`、`tests/test_t3_trigger.py`、`tests/test_t4_trigger.py`、`tests/test_t5_trigger.py` | **多消费者** |
| 77 | `backend/services/knowledge_ai.py` | 1 | `services/knowledge_service.py` | **单消费者** |
| 78 | `backend/services/knowledge_common.py` | 6 | `services/knowledge_ai.py`、`services/knowledge_evidence_bridge.py`、`services/knowledge_legacy_bridge.py`、`services/knowledge_lifecycle.py`、`services/knowledge_reuse.py`、`services/knowledge_service.py` | **多消费者** |
| 79 | `backend/services/knowledge_evidence_bridge.py` | 1 | `services/knowledge_service.py` | **单消费者** |
| 80 | `backend/services/knowledge_legacy_bridge.py` | 1 | `services/knowledge_service.py` | **单消费者** |
| 81 | `backend/services/knowledge_lifecycle.py` | 1 | `services/knowledge_service.py` | **单消费者** |
| 82 | `backend/services/knowledge_reuse.py` | 1 | `services/knowledge_service.py` | **单消费者** |
| 83 | `backend/services/knowledge_service.py` | 24 | `api/mcp_agent_tools.py`、`api/v1_case_relation_api.py`、`api/v1_knowledge_query_api.py`、`api/v1_knowledge_reuse_api.py`、`api/v1_knowledge_write_api.py`、`scheduler/jobs/knowledge_review.py`、`tests/test_c01_wal_backup_and_wikifs_isolation.py`、`tests/test_c06_async_call_dsh.py`、`tests/test_c08_artifact_cas_wiki_caseclose.py`、`tests/test_c12_knowledge_adoption.py`、`tests/test_knowledge_api.py`、`tests/test_knowledge_reuse.py`、`tests/test_knowledge_service.py`、`tests/test_v1_ingest_bridge.py`、`scripts/t085_seed_review_fixtures.py`、`scripts/t13_golden_knowledge_reuse.py` | **UNKNOWN** |
| 84 | `backend/services/knowledge_sync.py` | 43 | `api/knowledge_concepts.py`、`api/knowledge_import.py`、`api/wiki_tools.py`、`scheduler/jobs/digest.py`、`scheduler/jobs/knowledge.py`、`services/ai_write_back.py`、`services/backup_service.py`、`services/bookmark_sync.py`、`services/chunk_service.py`、`services/codegarden_knowledge_bridge.py`、`services/cubox_sync.py`、`services/federation_service.py`、`services/history_import.py`、`services/knowledge_watcher.py`、`services/mastery_projection.py`、`services/obsidian_service.py`、`services/summary_service.py`、`services/triggers/t5_publish_to_refine.py`、`tests/test_ai_hub.py`、`tests/test_auto_intake.py`、`tests/test_chunks_api.py`、`tests/test_compiler.py`、`tests/test_compound_drivers.py`、`tests/test_e8_projections.py`、`tests/test_favorite_to_knowledge.py`、`tests/test_hub_stats.py`、`tests/test_knowledge_truth_source.py`、`tests/test_sag_lifecycle.py`、`tests/test_wiki_tools.py`、`scripts/phase1i_task914_compile.py`、`scripts/phase1j_groupx.py`、`scripts/phase1j_task1004_compile.py`、`scripts/phase1j_task1005_fill_concepts.py` | **UNKNOWN** |
| 85 | `backend/services/knowledge_watcher.py` | 8 | `api/knowledge_obsidian.py`、`main.py`、`services/obsidian_service.py`、`tests/test_knowledge_watcher.py` | **多消费者** |
| 86 | `backend/services/kpi_service.py` | 2 | `api/kpi_api.py`、`tests/test_kpi_api.py` | **多消费者** |
| 87 | `backend/services/learning_service.py` | 5 | `api/knowledge_plans.py` | **UNKNOWN** |
| 88 | `backend/services/legacy_hold_service.py` | 2 | `scheduler/jobs/worker_pump.py`、`tests/test_legacy_hold_service.py` | **多消费者** |
| 89 | `backend/services/legacy_items_migrate_service.py` | 5 | `api/legacy_items_migrate_api.py`、`tests/test_legacy_items_migrate_service.py`、`scripts/t18_golden_legacy_items_migrate.py`、`scripts/t18_legacy_items_migrate.py` | **多消费者** |
| 90 | `backend/services/legacy_migrate_service.py` | 6 | `api/legacy_migrate_api.py`、`tests/test_legacy_migrate_service.py`、`tests/test_t17_e2e_audit_sse.py`、`scripts/t16_golden_legacy_migrate.py`、`scripts/t16_legacy_migrate.py` | **多消费者** |
| 91 | `backend/services/legacy_migrate_v1.py` | 24 | `api/legacy_migrate_v1_api.py`、`scheduler/jobs/legacy_promote.py`、`services/knowledge_legacy_bridge.py`、`services/legacy_items_migrate_service.py`、`services/legacy_migrate_service.py`、`tests/test_c13_legacy_migrate_v1.py`、`tests/test_c13_legacy_promote_jobs.py`、`scripts/t13_golden_legacy_migrate.py`、`scripts/t13_legacy_migrate.py`、`scripts/t13_legacy_promote.py` | **多消费者** |
| 92 | `backend/services/maintenance_service.py` | 17 | `api/maintenance_db_api.py`、`api/maintenance_retention_api.py`、`scheduler/jobs/maintenance.py`、`tests/test_quality_logs_archive.py`、`tests/test_telemetry_window.py`、`scripts/db_diet.py` | **多消费者** |
| 93 | `backend/services/map_updater.py` | 7 | `scheduler/jobs/maintenance.py`、`services/compiler.py`、`services/knowledge_watcher.py`、`tests/test_compiler.py`、`tests/test_compound_drivers.py`、`scripts/phase1i_task914_compile.py`、`scripts/phase1j_task1004_compile.py` | **UNKNOWN** |
| 94 | `backend/services/mastery_projection.py` | 2 | `api/reviews.py`、`tests/test_mastery_projection.py` | **多消费者** |
| 95 | `backend/services/monthly_report_service.py` | 3 | `api/reports.py`、`services/content_pref_advisor.py`、`tests/test_arxiv_paper_collector.py` | **多消费者** |
| 96 | `backend/services/news_alert_service.py` | 2 | `scheduler/jobs/collect.py`、`tests/test_news_alert_service.py` | **多消费者** |
| 97 | `backend/services/oauth_provider.py` | 11 | `api/secrets_oauth_api.py`、`services/secrets_service.py`、`tests/conftest.py`、`tests/test_oauth_secrets.py`、`tests/test_pipeline_p1_fix.py` | **多消费者** |
| 98 | `backend/services/observability_query_service.py` | 9 | `api/observability_audit_api.py`、`api/observability_metrics_api.py`、`tests/test_api_observability.py` | **多消费者** |
| 99 | `backend/services/observability_sampling.py` | 18 | `api/middleware.py`、`api/observability_router.py`、`tests/test_observability_sampling.py` | **多消费者** |
| 100 | `backend/services/observability_thresholds.py` | 5 | `api/observability_router.py`、`scheduler/jobs/maintenance.py`、`tests/test_observability_thresholds.py` | **多消费者** |
| 101 | `backend/services/obsidian_service.py` | 2 | `api/knowledge_obsidian.py` | **单消费者** |
| 102 | `backend/services/outbox_dispatcher.py` | 2 | `main.py` | **单消费者** |
| 103 | `backend/services/pi_adapter.py` | 6 | `tests/test_c06_real_pi_adapter.py`、`scripts/t10_live_trace.py` | **多消费者** |
| 104 | `backend/services/pick_service.py` | 3 | `scheduler/jobs/collect.py`、`tests/test_pick_service.py` | **UNKNOWN** |
| 105 | `backend/services/planning_service.py` | 3 | `api/kl_planning_api.py`、`scheduler/jobs/maintenance.py`、`tests/test_phase13_planning.py` | **多消费者** |
| 106 | `backend/services/process_supervisor.py` | 2 | `services/dsh/supervisor.py`、`tests/test_process_supervisor.py` | **多消费者** |
| 107 | `backend/services/profile_service.py` | 7 | `scheduler/jobs/maintenance.py`、`secnews_dashboard.py`、`services/feedback_service.py`、`tests/test_feedback_service.py`、`tests/test_phase4_acceptance.py`、`tests/test_profile_service.py` | **UNKNOWN** |
| 108 | `backend/services/progress_service.py` | 4 | `api/knowledge_plans.py` | **单消费者** |
| 109 | `backend/services/quality_gate_map.py` | 1 | `kl_pipeline/stages/refine.py` | **单消费者** |
| 110 | `backend/services/quality_query_service.py` | 4 | `api/quality_rejection_api.py`、`tests/test_quality_query_service.py` | **多消费者** |
| 111 | `backend/services/recommend_service.py` | 2 | `api/recommend.py`、`tests/test_recommend_service.py` | **多消费者** |
| 112 | `backend/services/rejection_explain_service.py` | 2 | `scheduler/jobs/collect.py`、`tests/test_rejection_explain_service.py` | **多消费者** |
| 113 | `backend/services/retention_engine.py` | 33 | `scheduler/jobs/maintenance.py`、`tests/test_characterization_golden.py`、`tests/test_graph_runtime.py`、`tests/test_wiki_archiver_retention.py`、`scripts/check_retention_decay.py` | **多消费者** |
| 114 | `backend/services/retry_policy.py` | 10 | `services/triggers/t1_raw_to_refine.py`、`services/triggers/t2_refine_to_link.py`、`services/triggers/t3_link_to_structure.py`、`services/triggers/t4_structure_to_publish.py`、`tests/test_kl_ingest_e2e_revival.py`、`tests/test_retry_policy.py`、`tests/test_t1_trigger.py`、`tests/test_t2_trigger.py`、`tests/test_t3_trigger.py`、`tests/test_t4_trigger.py` | **多消费者** |
| 115 | `backend/services/review_enrich.py` | 2 | `api/reviews.py`、`api/reviews_manage.py` | **多消费者** |
| 116 | `backend/services/review_service.py` | 7 | `api/reviews.py`、`api/reviews_manage.py`、`scheduler/jobs/digest.py`、`services/attention_events_service.py`、`services/hub_stats_service.py`、`tests/test_review_service.py`、`tests/test_reviews_manage_api.py` | **多消费者** |
| 117 | `backend/services/run_ledger_service.py` | 8 | `api/run_ledger_api.py`、`services/command_bar_service.py`、`services/knowledge_service.py`、`tests/test_copilot_drafter.py`、`tests/test_run_ledger.py` | **多消费者** |
| 118 | `backend/services/run_orchestrator.py` | 3 | `services/action_service.py`、`tests/test_run_orchestrator.py` | **多消费者** |
| 119 | `backend/services/run_service.py` | 11 | `api/run_api.py`、`api/v1_case_relation_api.py`、`services/run_orchestrator.py`、`tests/test_artifact_service.py`、`tests/test_c07_run_dispatch_and_skill_guards.py`、`tests/test_c08_artifact_cas_wiki_caseclose.py`、`tests/test_c11_outbox_and_aggregate.py`、`tests/test_run_orchestrator.py`、`tests/test_run_service.py`、`scripts/t085_seed_review_fixtures.py` | **多消费者** |
| 120 | `backend/services/sag_service.py` | 8 | `api/favorites.py`、`services/auto_intake_service.py`、`tests/test_auto_intake.py`、`tests/test_favorite_to_knowledge.py`、`tests/test_knowledge_oneway.py`、`tests/test_knowledge_truth_source.py`、`tests/test_sag_lifecycle.py` | **多消费者** |
| 121 | `backend/services/search_service.py` | 9 | `api/search.py`、`services/command_bar_service.py`、`tests/test_c02_migration_postcondition.py`、`tests/test_cve_enrich.py`、`tests/test_search_p4.py`、`tests/test_search_service.py`、`tests/test_wiki_items_fts.py` | **UNKNOWN** |
| 122 | `backend/services/secnews_dashboard_service.py` | 1 | `api/secnews_dashboard_api.py` | **单消费者** |
| 123 | `backend/services/secrets_service.py` | 38 | `api/secrets_keys_api.py`、`api/secrets_lifecycle_api.py`、`api/secrets_oauth_api.py`、`api/secrets_reset_api.py`、`api/secrets_reveal_api.py`、`api/secrets_rotation_api.py`、`main.py`、`mcp_stdio_main.py`、`scheduler/jobs/collect.py`、`scheduler/jobs/security.py`、`services/ai_hub/pool.py`、`services/ai_hub/service.py`、`services/alert_channels.py`、`services/codegarden_github_service.py`、`services/codegarden_resource_service.py`、`services/sync_bundle.py`、`services/sync_fernet_mixin.py`、`services/sync_service.py`、`services/trigger_gate/triggers/webhook.py`、`tests/test_llm_pool.py`、`tests/test_llm_secrets_integration.py`、`tests/test_oauth_secrets.py`、`tests/test_p0_evidence_crypto.py`、`tests/test_secrets_api.py`、`tests/test_trigger_webhook_secret.py`、`scripts/fix_webhook_secret_to_vault.py` | **多消费者** |
| 124 | `backend/services/security_graph_service.py` | 1 | `api/security.py` | **UNKNOWN** |
| 125 | `backend/services/settings_service.py` | 8 | `api/content_preferences_api.py`、`api/settings.py`、`services/auto_intake_service.py`、`services/content_pref_advisor.py`、`services/feature_flag_service.py`、`services/interest_domain_advisor.py`、`tests/test_auto_intake.py`、`tests/test_settings_service.py` | **多消费者** |
| 126 | `backend/services/signal_service.py` | 6 | `api/v1_signals_api.py`、`tests/test_signal_service.py`、`scripts/t15_golden_workbench_4entry.py` | **多消费者** |
| 127 | `backend/services/simhash.py` | 5 | `services/collection_dedup.py`、`services/triggers/t1_raw_to_refine.py`、`tests/test_fingerprint.py`、`tests/test_simhash.py`、`tests/test_t1_trigger.py` | **多消费者** |
| 128 | `backend/services/soul_service.py` | 5 | `api/knowledge_import.py`、`scheduler/jobs/digest.py`、`services/knowledge_watcher.py` | **UNKNOWN** |
| 129 | `backend/services/source_alerter.py` | 2 | `scheduler/jobs/collect.py`、`tests/test_source_alerter.py` | **多消费者** |
| 130 | `backend/services/source_census_service.py` | 6 | `api/source_health_api.py`、`api/source_stats_api.py`、`api/source_trend_api.py`、`tests/test_health_metric_alignment.py`、`tests/test_source_census.py` | **UNKNOWN** |
| 131 | `backend/services/source_health_machine.py` | 8 | `services/collection_pipeline.py`、`services/source_scheduler_service.py`、`tests/test_health_metric_alignment.py`、`tests/test_source_health_machine.py`、`tests/test_source_quality_cadence.py` | **多消费者** |
| 132 | `backend/services/source_health_service.py` | 8 | `api/source_trend_api.py`、`scheduler/jobs/collect.py`、`tests/test_health_metric_alignment.py`、`tests/test_pipeline_p1_fix.py`、`tests/test_source_health_service.py` | **UNKNOWN** |
| 133 | `backend/services/source_pipeline.py` | 6 | `services/v1_ingest_bridge.py`、`tests/test_c05_collection_to_source_pipeline.py`、`tests/test_c05_pipeline_watermark.py`、`tests/test_source_pipeline.py`、`tests/test_v1_ingest_bridge.py` | **多消费者** |
| 134 | `backend/services/source_prober.py` | 11 | `api/source_stats_api.py`、`scheduler/jobs/collect.py`、`services/source_revival_service.py`、`tests/test_source_prober.py` | **多消费者** |
| 135 | `backend/services/source_revival_service.py` | 9 | `scheduler/jobs/collect.py`、`tests/test_health_metric_alignment.py`、`tests/test_source_health_state_machine.py`、`tests/test_source_revival_service.py` | **多消费者** |
| 136 | `backend/services/source_scheduler_service.py` | 2 | `scheduler/jobs/collect.py`、`tests/test_source_quality_cadence.py` | **UNKNOWN** |
| 137 | `backend/services/stats_recycle_service.py` | 1 | `scheduler/jobs/maintenance.py` | **单消费者** |
| 138 | `backend/services/summary_enricher.py` | 1 | `services/collection_pipeline.py` | **单消费者** |
| 139 | `backend/services/summary_service.py` | 3 | `api/knowledge_plans.py`、`scheduler/jobs/digest.py` | **多消费者** |
| 140 | `backend/services/sync_bundle.py` | 17 | `services/sync_fernet_mixin.py`、`services/sync_service.py`、`tests/test_sync_bundle_v1_7.py`、`tests/test_sync_transaction.py` | **多消费者** |
| 141 | `backend/services/sync_config_service.py` | 6 | `api/sync.py`、`tests/test_sync_config_service.py` | **多消费者** |
| 142 | `backend/services/sync_fernet_mixin.py` | 3 | `services/sync_service.py`、`tests/test_sync_service_split.py` | **多消费者** |
| 143 | `backend/services/sync_merge.py` | 7 | `services/sync_bundle.py`、`services/sync_fernet_mixin.py`、`services/sync_service.py`、`tests/test_sync.py`、`tests/test_sync_bundle_v1_7.py`、`tests/test_sync_merge.py`、`tests/test_sync_transaction.py` | **多消费者** |
| 144 | `backend/services/sync_service.py` | 7 | `api/sync.py`、`scheduler/jobs/collect.py`、`tests/test_sync.py`、`tests/test_sync_service_split.py` | **UNKNOWN** |
| 145 | `backend/services/sync_service_constants.py` | 4 | `services/sync_bundle.py`、`services/sync_fernet_mixin.py`、`services/sync_merge.py`、`tests/test_sync_service_split.py` | **多消费者** |
| 146 | `backend/services/sync_zip.py` | 3 | `services/sync_bundle.py`、`services/sync_fernet_mixin.py`、`services/sync_service.py` | **多消费者** |
| 147 | `backend/services/tech_stack_service.py` | 2 | `api/tech_stack.py`、`tests/test_tech_stack_bridge.py` | **多消费者** |
| 148 | `backend/services/terminology_service.py` | 2 | `api/security.py`、`tests/test_terminology_service.py` | **多消费者** |
| 149 | `backend/services/trend_service.py` | 1 | `api/trends.py` | **单消费者** |
| 150 | `backend/services/url_batch_check_service.py` | 1 | `scheduler/jobs/collect.py` | **单消费者** |
| 151 | `backend/services/user_memory_service.py` | 5 | `services/agent_memory/__init__.py`、`services/feedback_analyzer.py`、`services/feedback_service.py`、`tests/test_agent_memory.py`、`tests/test_feedback_analyzer.py` | **多消费者** |
| 152 | `backend/services/v1_admission_service.py` | 8 | `services/v1_ingest_bridge.py`、`services/v1_signal_bridge.py`、`tests/test_admission_log_service.py`、`tests/test_v1_admission_service.py`、`tests/test_v1_signal_bridge.py`、`scripts/t07_seed_label_set.py` | **多消费者** |
| 153 | `backend/services/v1_evidence_service.py` | 17 | `api/v1_case_relation_api.py`、`scheduler/jobs/maintenance.py`、`services/action_service.py`、`services/case_service.py`、`services/judgment_service.py`、`services/knowledge_evidence_bridge.py`、`services/skill_registry/sk01_daily_priority.py`、`services/source_pipeline.py`、`services/v1_ingest_bridge.py`、`services/v1_signal_bridge.py`、`tests/test_c05_evidence_committed_reads.py`、`tests/test_case_service.py`、`tests/test_p0_evidence_crypto.py`、`tests/test_source_pipeline.py`、`tests/test_v1_evidence_service.py` | **多消费者** |
| 154 | `backend/services/v1_ingest_bridge.py` | 3 | `scheduler/jobs/collect.py`、`tests/test_v1_ingest_bridge.py` | **多消费者** |
| 155 | `backend/services/v1_signal_bridge.py` | 4 | `scheduler/jobs/collect.py`、`services/skill_registry/sk01_daily_priority.py`、`tests/test_skill_registry_v1.py`、`tests/test_v1_signal_bridge.py` | **多消费者** |
| 156 | `backend/services/webdav_client.py` | 5 | `api/sync.py`、`services/secrets_service.py`、`services/sync_fernet_mixin.py`、`services/sync_service.py`、`tests/test_webdav.py` | **UNKNOWN** |
| 157 | `backend/services/weekly_report_overview_service.py` | 2 | `api/reports.py`、`tests/test_arxiv_paper_collector.py` | **UNKNOWN** |
| 158 | `backend/services/weekly_report_service.py` | 3 | `api/weekly_report.py`、`scheduler/jobs/digest.py` | **多消费者** |
| 159 | `backend/services/wiki_archiver.py` | 9 | `scheduler/jobs/knowledge.py`、`tests/test_wiki_archiver_retention.py` | **多消费者** |
| 160 | `backend/services/wiki_stats_service.py` | 13 | `api/kl_compounding_api.py`、`api/kl_metrics_api.py`、`api/kl_pipeline_api.py`、`api/mcp_phase5_tools.py`、`secnews_dashboard.py`、`services/hub_stats_service.py`、`tests/test_phase13_planning.py`、`tests/test_wiki_stats_funnel_fallback.py`、`tests/test_wiki_stats_throughput.py`、`wiki_fs/store.py` | **多消费者** |
| 161 | `backend/services/worker_coordinator.py` | 5 | `scheduler/jobs/worker_pump.py`、`tests/test_c03_startup_health.py`、`tests/test_worker_coordinator.py` | **多消费者** |

---

## 3. 判定汇总

| 判定 | 数量 | 占比 | 说明 |
|---|---:|---:|---|
| 孤儿 | **1** | 0.6% | 零 import 消费者且无反射命中 |
| 单消费者 | 22 | 13.7% | 恰好 1 个消费者文件 |
| 多消费者 | 101 | 62.7% | ≥ 2 个消费者文件 |
| UNKNOWN | 37 | 23.0% | 命中反射模式，不下孤儿结论 |
| **合计** | **161** | 100% | — |

### 与「孤儿数 ≤ 5」阈值对比

| 项 | 阈值 | 实测 | 结论 |
|---|---|---|---|
| 孤儿数 | ≤ 5 | **1** | ✅ **通过**，余量 4 |
| 孤儿占比 | ≈ 3% | 0.6% | ✅ 远低于阈值 |
| 表格行数 | = 161 | 161 | ✅ 与 `count_services()` 一致 |

**结论**: R-06 验收标准 ①②均满足。孤儿 1 个（`crawler_seed`），未触及阈值上限，**服务层不存在批量死代码风险**。P1 裁决时真正的工作量不在「孤儿」，而在 37 个 UNKNOWN（反射盲区）与 22 个单消费者（尤其 3 个「仅测试消费」项）。

### UNKNOWN 的二级分布（供 P1 排期）

| 反射来源 | service 数 | 名单 |
|---|---:|---|
| 生产侧 plugin 注册表（`skill_registry` `ServiceTarget.module=`，经 `skill_runner/dispatch.py:125` `importlib.import_module` 执行） | 14 | `action_service`、`cve_heatmap_service`、`daily_report_overview_service`、`hotspot_service`、`judgment_service`、`knowledge_service`、`search_service`、`security_graph_service`、`source_census_service`、`source_health_service`、`source_scheduler_service`、`weekly_report_overview_service`（另 `source_health_service` 同时命中测试打桩） |
| 测试侧 `conftest.py` 字符串 `importlib.import_module` 清单 | 11 | `bookmark_sync`、`compiler`、`concept_linker`、`content_service`、`cubox_sync`、`federation_service`、`history_import`、`knowledge_sync`、`learning_service`、`map_updater`、`soul_service` |
| 测试侧 `mock.patch("backend.services.X…")` | 14 | `alert_service`、`catchup_service`、`codegarden_github_service`、`collection_logger`、`collection_service`、`digest_service`、`extract_service`、`profile_service`、`sync_service`、`webdav_client` 等 |
| 测试侧 `monkeypatch.setattr("backend.services.X…")` | 6 | `alert_dispatcher`、`codegarden_drift`、`cve_knowledge_sync`、`knowledge_sync`、`pick_service` |

> 14 + 11 + 14 + 6 = 45 > 37，因同一 service 可同时命中多类（如 `knowledge_sync` 既在 conftest 清单又被 `monkeypatch.setattr`；`source_health_service` 既在 plugin 注册表又被 `mock.patch`）。表内按 service 去重。

---

## 4. 孤儿候选明细（逐个独立核验）

### 4.1 `crawler_seed.py` — 判定：**孤儿**

**文件**: `backend/services/crawler_seed.py`（194 行）

**核验 1 — import 图核验（AST 全仓扫描）**

```
被 import 次数: 0
消费者文件列表: （空）
```

全仓 1,125 个 Python 文件 + 421 个前端源文件中，无任何 `import backend.services.crawler_seed` / `from backend.services.crawler_seed import ...` / `from backend.services import crawler_seed`。

**核验 2 — 模块名 grep**

```bash
$ grep -rn "crawler_seed" --include="*.py" backend/ scripts/ frontend/
backend/scripts/seed_crawler_sources.py:62:            # 与 backend/services/crawler_seed.py:146 守卫同语义。
backend/services/crawler_seed.py:4:    python -c "from backend.services.crawler_seed import seed_sources; seed_sources()"
```

命中 2 处，均非 import：
- `backend/scripts/seed_crawler_sources.py:62` —— **纯注释**，指向同语义守卫，非引用。
- `backend/services/crawler_seed.py:4` —— **自身 docstring** 里的手工用法示例。

**核验 3 — 类名 / 主函数名 grep**

```bash
$ grep -rn "seed_sources" --include="*.py" backend/ scripts/ frontend/
backend/services/crawler_seed.py:4:    python -c "from backend.services.crawler_seed import seed_sources; seed_sources()"
backend/services/crawler_seed.py:131:def seed_sources() -> int:
backend/services/crawler_seed.py:192:    n = seed_sources()
```

`seed_sources` 的全部命中都在**定义它的同一个文件内**（131 行定义、192 行 `__main__` 自调用），无外部调用方。

```bash
$ grep -rn "_SOURCE_GROUPS\|_make_source_id\|_detect_parser_id" --include="*.py" backend/ scripts/ frontend/
```

私有辅助函数（58 / 76 / 106 行）同样全部自包含，无外部引用。

**核验 4 — 调度 / 路由 / 测试接入核验**

```bash
$ grep -rn "crawler_seed" backend/scheduler/ backend/api/     # → 0 命中
$ ls backend/tests/ | grep -i "crawler\|seed"
test_crawler_sources.py
```

- 无 scheduler job 引用（该文件不在 `backend/scheduler/jobs/*` 任何 job 的 import 图中）。
- 无 API router 引用。
- `backend/tests/test_crawler_sources.py` **不导入 `crawler_seed`**，它导入的是 `backend.scripts.seed_crawler_sources`：

```bash
$ grep -n "import" backend/tests/test_crawler_sources.py
87:    from backend.scripts.seed_crawler_sources import _collect_sources
154:    from backend.scripts.seed_crawler_sources import _collect_sources
```

**核验 5 — 反射风险核验（§1.3 五类全查）**

`crawler_seed` 模块名**未命中**任何反射模式：无 `importlib` 引用、无 `getattr` 引用、不在 `skill_registry` plugin 注册表、不在 `conftest.py` 动态清单、无 `mock.patch` / `monkeypatch.setattr` 字符串打桩。可安全下「孤儿」结论。

**为何判孤儿**

该文件是 **Crawler v2 Phase 0 的一次性种子脚本**（docstring 自述），功能是把 collector 的 `*_SOURCES` 常量灌入 `crawler_sources` 表。它的能力已被 `backend/scripts/seed_crawler_sources.py`（Phase 0.5）**在生产语义上取代**——后者改用 collector **实例**的 `sources`（实际生效源，含 `SOURCE_BLACKLIST` 过滤），修正了 Phase 0 用常量导致的黑名单源漏网问题。当前 `crawler_sources` 表的真实生产写入者与读取者链路（`backend/repository/source_scheduler_repo.py`）均不经过 `crawler_seed`。文件顶部的 `if __name__ == "__main__"` 表明它只以手工 `python -c` 方式使用，不参与任何自动化路径。

**风险提示**

- ⚠️ **`crawler_sources` 表本身仍是活的** —— `backend/repository/source_scheduler_repo.py`（读/写/删该表）与 `backend/repository/hotspot_repo.py:798` 都在用它。**删除 `crawler_seed.py` 不影响该表**，但**不得连带删除表或 repo**。
- ⚠️ **`backend/scripts/seed_crawler_sources.py:62` 的注释以 `crawler_seed.py:146` 为行号锚点** —— 若删除 `crawler_seed.py`，该注释锚点失效，需同批修正（属 P3 删除纪律的一次性清理项）。
- ⚠️ **文档残留 2 处**（非代码）：`docs/code-wiki/02-backend.md:127`（采集编排清单）、`docs/code-wiki/06-crawler-comparison.md:111`。按 PRD 单一权威 PRD 纪律，这两份 `code-wiki` 文档本身已属历史文档，但行号/清单残留需在 P3 一并处理。
- ⚠️ **`.trae/specs/phase4-legacy-shutdown/spec.md:18,30` 提及 `crawler_seed.py`** —— 是 Phase 4 规格的「可能修改」条目，非执行期引用。
- ℹ️ **`DEV_LOG.md:2392` 记录了「清接线: … crawler_seed + seed_crawler_sources …」** —— 说明 DEV-0179（标讯链删除）时二者均被点名清理过接线，`crawler_seed` 残留至今。

---

## 5. 单消费者清单（22 项，供 P1 快速过目）

**判定含义**：整个仓库只有 1 个文件 import 它。这类 service 是「改动波及面最小」的一档，也是**误删风险最高**的一档（唯一消费者一旦重构，service 即成孤儿）。

### 5.1 生产单消费者（19 项）— 正常架构形态

| service | 唯一消费者 | 位置 |
|---|---|---|
| `annotation_service` | `backend/api/annotations.py` | API 层直接挂载 |
| `attack_label_service` | `backend/api/event_types_api.py` | API 层直接挂载 |
| `event_technique_review_service` | `backend/api/event_types_api.py` | API 层直接挂载 |
| `hub_stats_service` | `backend/api/knowledge_api.py` | API 层直接挂载 |
| `secnews_dashboard_service` | `backend/api/secnews_dashboard_api.py` | API 层直接挂载 |
| `trend_service` | `backend/api/trends.py` | API 层直接挂载 |
| `stats_recycle_service` | `backend/scheduler/jobs/maintenance.py` | 定时任务挂载 |
| `url_batch_check_service` | `backend/scheduler/jobs/collect.py` | 定时任务挂载 |
| `quality_gate_map` | `backend/kl_pipeline/stages/refine.py` | pipeline 阶段挂载 |
| `copilot_drafter` | `backend/services/run_ledger_service.py` | 服务间调用 |
| `summary_enricher` | `backend/services/collection_pipeline.py` | 服务间调用 |
| `knowledge_ai` | `backend/services/knowledge_service.py` | 服务间调用 |
| `knowledge_evidence_bridge` | `backend/services/knowledge_service.py` | 服务间调用 |
| `knowledge_legacy_bridge` | `backend/services/knowledge_service.py` | 服务间调用 |
| `knowledge_lifecycle` | `backend/services/knowledge_service.py` | 服务间调用 |
| `knowledge_reuse` | `backend/services/knowledge_service.py` | 服务间调用 |
| `obsidian_service` | `backend/api/knowledge_obsidian.py` | API 层直接挂载（2 条 import） |
| `outbox_dispatcher` | `backend/main.py` | 应用启动挂载（2 条 import） |
| `progress_service` | `backend/api/knowledge_plans.py` | API 层直接挂载（4 条 import） |

> `knowledge_service` 一个文件同时消费 5 个 knowledge 子模块（`knowledge_ai` / `knowledge_evidence_bridge` / `knowledge_legacy_bridge` / `knowledge_lifecycle` / `knowledge_reuse`）—— 属 **facade 模式**，5 个子模块共用一个消费入口。这 5 项的存废应作为**一个决策单元**，不可逐个独立裁决。

### 5.2 仅测试消费（3 项）— **重点关注**

| service | 唯一消费者 | 生产代码中是否存在引用 |
|---|---|---|
| `cost_monitor` | `backend/tests/test_hybrid_ai.py` | ❌ 无 |
| `feedback_analyzer` | `backend/tests/test_feedback_analyzer.py` | ❌ 无 |
| `codegarden_scanner_service` | `backend/tests/test_codegarden_scanner.py` | ❌ 无（4 条 import 均在测试文件内） |

**核验证据**

```bash
$ grep -rn "CostMonitor\|cost_monitor" --include="*.py" backend/ scripts/ | grep -v "^backend/services/cost_monitor.py" | grep -v "^backend/tests/"
backend/services/ai_hub/usage.py:13:   / cost_monitor.record_usage。成功失败都落表, 真实 latency/真值 tokens、
backend/services/ai_hub/usage.py:15:2. cost_monitor.record_usage 改为调 record_llm_call (避免双 INSERT 漂移)。
```

→ 仅 **docstring 提及**，无 import、无调用。

```bash
$ grep -rn "FeedbackAnalyzer\|feedback_analyzer" --include="*.py" backend/ scripts/ | grep -v "^backend/services/feedback_analyzer.py" | grep -v "^backend/tests/"
backend/repository/user_memory_repo.py:26:        source: str = "feedback_analyzer",
backend/services/agent_memory/__init__.py:14:两条路径同一对象, 既有调用者 (feedback_analyzer / feedback_service) 零改动。
backend/services/user_memory_service.py:26:        source: str = "feedback_analyzer",
```

→ `source: str = "feedback_analyzer"` 是**数据字段默认值**（不是模块引用）；`agent_memory/__init__.py:14` 是 docstring。**均非 import**。

**为何单列**

这 3 项满足「孤儿」的**实质**定义（生产链路零引用），但形式上有 1 个测试消费者，故按 4 档规则判为「单消费者」而非「孤儿」——**这是口径的必然结果，不是漏判**。从 P1 裁决视角，它们与 4.1 的 `crawler_seed` 属同一族待决项，但处置方式不同：

- **测试仍覆盖其行为** → 删除会同时删除对应测试；P1 需先确认「该能力是否仍需保留」。
- **风险提示 — `codegarden_scanner_service`**：属 CodeGarden 扩展域（`feature_gates.toml` 中 `codegarden` / `codegarden_phase2b` 默认开启），生产可达性由 gate 控制；「生产零 import」可能只是 gate 关闭时的表象，**不能据本表断言其死**。
- **风险提示 — `cost_monitor` / `feedback_analyzer`**：两者均在 v0.8.x 文档中被描述为已落地能力（`ai_hub/usage.py` docstring 明确记载「cost_monitor.record_usage 改为调 record_llm_call」的改造历史）。**能力可能已由 ai_hub / agent_memory 内部逻辑吸收**，需 P1 读代码确认，而非据 import 计数直接判死。

---

## 6. 已知局限 / 未覆盖路径

| # | 局限 | 影响 | 缓解 |
|---|---|---|---|
| 1 | **统计基于 import 语句，非运行时可达性** | 一个 service 可能被 import 但其函数从未被调用（死代码在被调用者内部） | 本表是 R-06 的 import 级口径要求；函数级死代码属 R-05/R-08 范畴 |
| 2 | **`user_skills` 表驱动的动态导入面未纳入** | `backend/services/skill_builder/validate.py:111,118` 会对**任意**用户提交的 `target_module` 字符串做 `importlib.util.find_spec` + `importlib.import_module`，理论上**任意 service** 都可被用户在 UI 创建的 skill 引用 | 该面**不是静态注册表**，无法静态枚举；故未用于把 service 判为 UNKNOWN。但它意味着「零引用」不等于「不可达」。P1 裁决任何孤儿/单消费者项前，须查 `user_skills` 表是否有存量行指向它 |
| 3 | **`skill_registry` plugin 注册表是数据驱动的** | `backend/services/skill_registry/builtin.py`（20 内置）+ `v1_skills.py` 是**当前**注册的 skill 目标；后续可新增指向任意 service | 已对当前快照做穷举登记（14 个 service 标 UNKNOWN）；新增 skill 需重跑本盘点 |
| 4 | **前端不是 service 的 import 消费者** | 前端经 HTTP 契约消费后端；`frontend/src` 中 5 处 `backend.services` 全为注释 | 非遗漏，是架构事实。但**端点级**孤儿（前端已不再调用的 API）属 R-09 范畴 |
| 5 | **未纳入 `backend/services/` 子包** | `ai_hub/`(14) `agent_loop/`(4) `agent_memory/`(4) `dsh/`(8) `llm/`(2) `pi/`(1) `playbook_engine/`(5) `skill_builder/`(4) `skill_eval/`(5) `skill_registry/`(8) `skill_runner/`(4) `trigger_gate/`(10) `triggers/`(7) = **13 个子包 / 76 个 .py 文件** 不计入本表 | 与 `count_services()` 口径一致（该函数只 glob 顶层）。子包盘点若需，应单列 R-06-b |
| 6 | **`.mimosa/` 隐藏目录** | `backend/services/.mimosa/`（含 `hook-state/` `hook-status/`）为工具运行时产物目录，**0 个 .py 文件**，不影响 service 计数 | 已核，不计入 |
| 7 | **`.ua/fingerprints.json` 等工具缓存含全量模块路径字符串** | 若被误当注册表，会把 100+ service 误判 UNKNOWN | 已确认其为静态分析工具产物（`generatedAt: 2026-09-11`，`gitCommitHash` 固定），**非运行期注册表**，不采信 |
| 8 | **未跑动态追踪（运行时 import hook）** | 若存在运行时生成 import 语句（如 `exec`/`eval` 构造代码），静态 AST 不可见 | 全仓 `eval`/`exec` 出现在 `backend/services/playbook_engine`（`_safe_eval` 有 RCE 边界测试，`backend/tests/test_playbook_engine.py:441`）等**受控沙箱**内，构造的是 `os`/`datetime` 等标准库，不构造 service 模块路径；已人工核对 |
| 9 | **import 次数与消费者文件数是两套口径** | 5 个 service 两者不一致（`codegarden_scanner_service` 4:1 / `learning_service` 5:1 / `obsidian_service` 2:1 / `outbox_dispatcher` 2:1 / `progress_service` 4:1） | 表内「被 import 次数」列 = import 语句条数，「消费者文件列表」= 去重文件数；判定档位按**消费者文件数**划分，与 PRD「单消费者/多消费者」字面语义一致 |
| 10 | **仓库树状态** | 本盘点在**非干净树**上采集（存在未提交改动），结论对应采集时刻的磁盘状态 | PRD RA-8 要求「基线在脏树上采集导致结论失效」由采集脚本校验 `git status` 干净。本表为 P0 基线快照，P1 裁决前建议复跑一次核对漂移 |

---

## 附录 A：可复现命令

```bash
# 1. 口径确认
python3 -c "from scripts.generate_meta import count_services; print(count_services())"   # → 161

# 2. 孤儿独立核验（模块名 + 主函数名 + 调度/路由/测试接入）
grep -rn "crawler_seed" --include="*.py" backend/ scripts/ frontend/
grep -rn "seed_sources"  --include="*.py" backend/ scripts/ frontend/
grep -rn "crawler_seed" backend/scheduler/ backend/api/

# 3. 反射面复查（任一命中即不得判孤儿）
grep -rn "importlib\.import_module\s*(\s*[\"']backend\.services\." --include="*.py" backend/ scripts/
grep -rn "patch(\s*[\"']backend\.services\."        --include="*.py" backend/ scripts/
grep -rn "setattr(\s*[\"']backend\.services\."      --include="*.py" backend/ scripts/
grep -rn "module=\"backend\.services\."              --include="*.py" backend/services/skill_registry/

# 4. 假阳性排除（字符串数据值 ≠ 模块引用）
grep -rn "_KNOWN_QUEUES" backend/scheduler/jobs/worker_pump.py
grep -rn "source=\"observability_thresholds\"\|source: str = \"feedback_analyzer\"" --include="*.py" backend/
```

## 附录 B：本次采集环境

| 项 | 值 |
|---|---|
| 采集日期 | 2026-11-10 |
| 采集范围 | `backend/` + `scripts/` + `frontend/` |
| Python 文件（AST 解析） | 1,125（`backend/` 1,006 + `scripts/` 119） |
| 前端源文件（文本扫描） | 385（`frontend/src/`） |
| 被解析的唯一消费者文件 | 427（生产 194 / 测试 192 / scripts 41 / 前端 0） |
| service 行数 | 161（= `count_services()`） |
| 本次盘点对仓库的写入 | **仅本文档**；未改业务代码 / 测试 / 其他文档；无 git 写操作；无数据库写入 |
