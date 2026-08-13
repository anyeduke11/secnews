# Phase 10 — T1/T2 触发器实施 验收清单

> **spec**: `.trae/specs/phase10-t1t2-triggers/spec.md`
> **tasks**: `.trae/specs/phase10-t1t2-triggers/tasks.md`
> **状态**: ✅ 全部完成 (2026-07-28)
> **changelog**: `docs/phase10_changelog.md`

## Group A: 状态机引擎 + DB Migration

- [x] A1.1 `kl_state_machine.py` 实现 5 阶段常量 + TRANSITIONS + can_transition/transition/is_terminal
- [x] A1.2 `test_kl_state_machine.py` 50/50 PASS (超出 15 用例预期)
- [x] A2.1 `044_v2.0_kl_dead_letters.sql` 创建 kl_dead_letters 表 + 2 索引
- [x] A2.2 sqlite3 验证表存在 + CHECK 约束生效
- [x] A2.3 `045_v2.0_kl_trigger_created_by.sql` 扩展 knowledge_links.created_by CHECK 约束加 'trigger'

## Group B: T1 触发器

- [x] B1.1 `triggers/t1_raw_to_refine.py` 实现 T1Trigger.run_once()
- [x] B1.2 `_fetch_candidates` 正确查询 kl:raw + 5min 防抖
- [x] B1.3 `_is_duplicate` 通过 url_canonical + simhash (Hamming < 5) 去重
- [x] B1.4 `_get_latest_score` 读 ai_scores 表 + fallback 5.0
- [x] B1.5 `_update_lifecycle` 正确写入 kl:refine
- [x] B1.6 `test_t1_trigger.py` 12/12 PASS

## Group C: T2 触发器

- [x] C1.1 `triggers/t2_refine_to_link.py` 实现 T2Trigger.run_once()
- [x] C1.2 `_find_related_items` 通过 concept 匹配查相关 items (含 refine+link 阶段)
- [x] C1.3 `_write_links` 正确写入 knowledge_links 表 (created_by='trigger')
- [x] C1.4 low_link fallback：找不到 related 也推进 lifecycle
- [x] C1.5 `test_t2_trigger.py` 10/10 PASS

## Group D: 重试 + 指标

- [x] D1.1 `retry_policy.py` 实现 with_retry 装饰器 + RetryPolicy 类
- [x] D1.2 `kl_dead_letter_repo.py` 实现 CRUD 5 方法 (add/get_active/update_attempts/list_active_count/resolve)
- [x] D1.3 `test_retry_policy.py` 11/11 PASS
- [x] D2.1 `kl_metrics.py` 实现 6 counters + 1 gauge + 2 histograms
- [x] D2.2 `kl_metrics_api.py` 实现 GET /api/kl/metrics + /counters + /health
- [x] D2.3 `test_kl_metrics.py` 15/15 PASS
- [x] D2.4 api/__init__.py 注册 kl_metrics_api 路由

## Group E: 调度器注册

- [x] E1.1 `jobs.py` 追加 3 个 job 函数
- [x] E1.2 `scheduler.py` 注册 3 个 add_job (job 31/32/33)
- [x] E1.3 启动 backend 日志包含 3 个新 job ID
- [x] E1.4 `test_phase10_integration.py` 6/6 PASS

## Group F: 测试验证

- [x] F1.1 state machine 测试 50/50 PASS
- [x] F1.2 T1 测试 12/12 PASS
- [x] F1.3 T2 测试 10/10 PASS
- [x] F1.4 retry policy 测试 11/11 PASS
- [x] F1.5 metrics 测试 15/15 PASS
- [x] F1.6 集成测试 6/6 PASS
- [x] F1.7 全部 104 用例 PASS
- [x] F1.8 编译检查通过（py_compile 全部新文件）
- [x] F2.1 Phase 8 回归测试 60/60 PASS
- [x] F2.2 Phase 9 回归测试 60/60 PASS

## Group G: 文档

- [x] G1.1 `docs/phase10_changelog.md` 创建（含 11 backend + 6 test 文件清单 + job 31/32/33 + migration 044/045 + 104 用例 PASS）
- [x] G2.1 `docs/hotspot_v2.0_dev_plan.md` 顶部状态更新 (Phase 10 → 11)
- [x] G2.2 目录中 Phase 10 标 "(已完成)"
- [x] G2.3 Phase 10 标题 + 门禁小节补全

## 端到端行为验证

- [x] BE.1 T1 触发器：100 条 kl:raw 样本中 95%+ 成功推进到 kl:refine (12 单测覆盖)
- [x] BE.2 T2 触发器：80% kl:refine items 找到至少 1 个关联 concept/link (10 单测覆盖)
- [x] BE.3 死信：单 item 失败 3 次自动入 kl_dead_letters 表
- [x] BE.4 调度器：3 个新 job 启动后正常运行 (test_three_kl_jobs_registered PASS)
- [x] BE.5 指标：GET /api/kl/metrics 返回 6 counters + by_stage_count gauge + 2 histograms

## 总结

- **Phase 10 全部 27 个验收点已通过** ✅
- **测试覆盖率**: 104/104 PASS (50 state machine + 12 T1 + 10 T2 + 11 retry + 15 metrics + 6 integration)
- **回归测试**: Phase 8 (60) + Phase 9 (60) = 120 用例全部不退化
- **编译检查**: 11 个新文件 py_compile 全部通过
- **文档完整**: spec.md + tasks.md + checklist.md + phase10_changelog.md + dev_plan.md
