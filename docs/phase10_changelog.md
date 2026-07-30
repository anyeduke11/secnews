# Phase 10 — T1/T2 触发器实施 变更日志

> **版本**: v2.0 (Phase 10)
> **日期**: 2026-07-28
> **spec**: `.trae/specs/phase10-t1t2-triggers/`
> **前置**: Phase 8 (复利基础设施) ✅ + Phase 9 (v1.9 抓取标准化) ✅
> **状态**: ✅ 已完成

## 新增功能

### 1. 5 阶段 KL 状态机引擎
- `backend/services/kl_state_machine.py`: 实现 `LIFECYCLE_RAW/REFINE/LINK/STRUCTURE/PUBLISH` 5 阶段常量 + `TRANSITIONS` 单向 DAG + `can_transition/transition/is_terminal` 核心 API
- T5 回滚边：`kl:publish → kl:refine` (回退场景)
- `STAGE_LABELS` 中英双语标签，便于 UI 展示
- 兼容 v1.7.6 旧值：`signal` / `amplify:tagged` / `generate` 通过 046 迁移一次性升级

### 2. T1 触发器 (kl:raw → kl:refine)
- `backend/services/triggers/t1_raw_to_refine.py`: `T1Trigger.run_once()`
- 流程：查询 `lifecycle='kl:raw'` 且 `ingested_at < now - 5min` 的 items → simhash 去重 (Hamming < 5 或 url_canonical 精确匹配) → 取最近 `ai_scores.score` (无则 fallback 5.0) → 提取 tag (从 `concepts` JSON 解析) → 更新 `lifecycle='kl:refine'`
- 防抖：5 分钟内新 ingest 的 item 不处理 (避免 race condition)
- 调度：每 60s

### 3. T2 触发器 (kl:refine → kl:link)
- `backend/services/triggers/t2_refine_to_link.py`: `T2Trigger.run_once()`
- 流程：查询 `lifecycle='kl:refine'` 的 items → 解析 `concepts` (JSON) 找共享 concept 的其他 items → 写 `knowledge_links` (`type='similar'`, `confidence=0.7`, `created_by='trigger'`) → 更新 `lifecycle='kl:link'`
- 双向：a→b 与 b→a 同时建立（同一周期）
- low_link 兜底：找不到 related 也推进 lifecycle（标 low_link 而非 failed）
- 调度：每 120s

### 4. 重试策略 + 死信队列
- `backend/services/retry_policy.py`:
  - `with_retry(fn, max_attempts=3, backoff=(1,5,30))` 装饰器（指数退避）
  - `RetryPolicy.handle_failure(trigger, item_id, error)` 业务级：累计 attempts，3 次失败入死信
- `backend/repository/kl_dead_letter_repo.py`: 5 个 CRUD 方法（add / get_active / update_attempts / list_active_count / resolve）
- `migration 044_v2.0_kl_dead_letters.sql`: 新表 `kl_dead_letters` + 2 索引
- `migration 045_v2.0_kl_trigger_created_by.sql`: 扩展 `knowledge_links.created_by` CHECK 约束允许 `'trigger'` 值

### 5. Prometheus 指标 (KLMetrics)
- `backend/metrics/kl_metrics.py`: 6 counters + 1 stage gauge + 2 histograms
  - counters: `t1_triggered/t1_succeeded/t1_failed/t1_dead_letter` + T2 对称 4 个
  - gauge: `by_stage_count` (5 阶段 items 数)
  - histograms: `t1_latency_ms` / `t2_latency_ms` (ring buffer 100 sample)
  - thread-safe RLock
- `backend/api/kl_metrics_api.py`: `GET /api/kl/metrics` 返回 JSON snapshot
  - `GET /api/kl/metrics/counters`: 仅 counters
  - `GET /api/kl/metrics/health`: 健康检查

### 6. 调度器 Job (3 个新增)
- **kl_trigger_t1** (job 31, 60s): T1 触发器
- **kl_trigger_t2** (job 32, 120s): T2 触发器
- **kl_dead_letter_retry** (job 33, 600s/10min): 死信监控 + 告警 (>50 active 时 warn)

## 数据库变更

| 迁移文件 | 操作 | 新增表 / 约束 | 索引 |
|---------|------|--------|------|
| `044_v2.0_kl_dead_letters.sql` | 新增 | `kl_dead_letters` | 2 (trigger+resolved / item_id) |
| `045_v2.0_kl_trigger_created_by.sql` | 修改 | `knowledge_links.created_by` CHECK 增加 `'trigger'` | 无 |

## 新增文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `backend/services/kl_state_machine.py` | ~190 | 5 阶段状态机 + TRANSITIONS + can_transition/transition/is_terminal |
| `backend/services/triggers/__init__.py` | ~20 | triggers 子包入口 |
| `backend/services/triggers/t1_raw_to_refine.py` | ~270 | T1 触发器 (simhash 去重 + 评分 + tag 提取 + lifecycle 推进) |
| `backend/services/triggers/t2_refine_to_link.py` | ~250 | T2 触发器 (concept 关联 + knowledge_links 写入 + lifecycle 推进) |
| `backend/services/retry_policy.py` | ~180 | with_retry 装饰器 + RetryPolicy 业务类 |
| `backend/repository/kl_dead_letter_repo.py` | ~200 | kl_dead_letters CRUD |
| `backend/metrics/__init__.py` | ~15 | metrics 子包入口 |
| `backend/metrics/kl_metrics.py` | ~180 | 6 counters + 1 gauge + 2 histograms |
| `backend/api/kl_metrics_api.py` | ~60 | GET /api/kl/metrics 端点 |
| `backend/repository/migrations/044_v2.0_kl_dead_letters.sql` | ~16 | kl_dead_letters 表 schema |
| `backend/repository/migrations/045_v2.0_kl_trigger_created_by.sql` | ~50 | knowledge_links.created_by CHECK 约束扩展 |

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/api/__init__.py` | 注册 `kl_metrics_api` 路由 (第 44 行 + 第 105 行) |
| `backend/scheduler/jobs.py` | 追加 `kl_trigger_t1_job` / `kl_trigger_t2_job` / `kl_dead_letter_retry_job` (3 个 async 函数) |
| `backend/scheduler/scheduler.py` | 追加 job 31/32/33 注册 (3 个 add_job 调用) |

## 测试覆盖

| 测试文件 | 用例数 | 状态 |
|---------|--------|------|
| `test_kl_state_machine.py` | 50 | ✅ 全部通过 (5 阶段转换 + 非法转换 + 边界) |
| `test_t1_trigger.py` | 12 | ✅ 全部通过 (candidates + 去重 + 评分 fallback + tag + lifecycle + metrics + retry) |
| `test_t2_trigger.py` | 10 | ✅ 全部通过 (candidates + entity 查找 + link 写入 + lifecycle + low_link + metrics) |
| `test_retry_policy.py` | 11 | ✅ 全部通过 (with_retry 5 + RetryPolicy 6) |
| `test_kl_metrics.py` | 15 | ✅ 全部通过 (counters + stage gauge + histograms + endpoint + singleton) |
| `test_phase10_integration.py` | 6 | ✅ 全部通过 (3 jobs 注册 + T1→T2 链 + 端到端 link 写入 + metrics 端点 + 死信兜底 + 调度器往返) |

**总计**: 104 个 Phase 10 测试用例全部通过

## 回归测试

| 阶段 | 测试文件 | 用例数 | 状态 |
|------|---------|--------|------|
| Phase 8 | test_simhash / test_fingerprint / test_mcp_phase8 / test_imported_aggregator / test_knowledge_imported_api | 60 | ✅ 全部通过 |
| Phase 9 | test_catchup_checkpoint_repo / test_collection_logger / test_collect_validator / test_catchup_phase9 / test_catchup_api / test_catchup_watchdog | 60 | ✅ 全部通过 |

## 关键决策

1. **不引入 prometheus_client**：用纯 Python dict + RLock 实现 6 counters + 1 gauge + 2 histograms，通过 `/api/kl/metrics` 暴露 JSON snapshot。零新依赖，符合"少即是多"原则。
2. **T2 双向 link**：`_find_related_items` 同时包含 refine 和 link 阶段 items，确保 a→b 与 b→a 在同一周期建立。
3. **低 link 兜底**：T2 找不到 related 不算 failed，只标 `low_link++`，仍推进 lifecycle（避免 T2 永远卡住）。
4. **状态机独立于 knowledge_sync**：状态机直接写 SQLite，knowledge_sync 仍走 file-first 双轨制，两者不冲突。
5. **死信表 046 之前创建**：死信表 schema 在 044 已存在，无需 046 即可写。
6. **created_by CHECK 扩展 (045)**：默认 'manual/agent/rule' 不含 'trigger'，必须独立 migration 扩展。
7. **scheduler job 31/32/33 编号沿用 Phase 8/9 续号**：与 PRD §2.2 30 job 总数一致。
8. **T1/T2 都设 RAW_MIN_AGE_SECONDS 防抖**：避免 ingest 后立即推进（5min 内 wait 异步评分写入）。

## 依赖变更
- 新增 Python 依赖：无（纯标准库 + FastAPI + APScheduler 已有）
- 新增前端依赖：无
- 新增 API 端点：1 个 (`GET /api/kl/metrics` + 2 子端点)

## 配置变更
- 无（Phase 10 不引入 feature flag）

## 已知问题 / 待 Phase 11+ 处理

- ❌ T3/T4/T5 触发器未实现（保留接口签名即可，Phase 12 实施）
- ❌ 旧 3 阶段 lifecycle 迁移 SQL `046_lifecycle_v2.sql` 已存在但未执行 — **Phase 10 完成后、Phase 11 启动前**手动执行
- ❌ 死信清理 job 未实现（暂依赖手动 resolve，Phase 12 写 cleanup）
- ❌ ai_scores 大量为空时 T1 评分全 fallback 5.0 — Phase 15 Hybrid AI 后精度提升
- ❌ 暂无 Prometheus 暴露（仅 JSON 端点，需要时引入 prom client）

## API 端点汇总

| 方法 | 路径 | 描述 | 状态码 |
|------|------|------|--------|
| GET | `/api/kl/metrics` | 完整 snapshot (counters + gauges + histograms) | 200 |
| GET | `/api/kl/metrics/counters` | 仅 counters | 200 |
| GET | `/api/kl/metrics/health` | 健康检查 | 200 |

## 端到端行为验证

- ✅ T1 触发器：12 个单测覆盖去重/评分/tag/lifecycle 全链路
- ✅ T2 触发器：10 个单测覆盖 concept 关联/link 写入/lifecycle 推进
- ✅ 死信：3 次失败自动入 `kl_dead_letters` 表 (test_retry_policy::test_third_failure_writes_dead_letter)
- ✅ 调度器：3 个新 job 启动后正常运行（test_phase10_integration::test_three_kl_jobs_registered）
- ✅ 指标：`/api/kl/metrics` 返回 6 counters + by_stage_count gauge + 2 histograms
- ✅ T1→T2 端到端：test_phase10_integration::test_end_to_end_writes_knowledge_link
- ✅ Scheduler 往返：replace_existing 工作（test_phase10_integration::test_scheduler_start_stop_round_trip）
