# Phase 3: 源级调度 + 健康管理 Spec

## Why

当前采集系统使用全局 `collect_all_job`（每300s）统一调度所有源，缺乏源级粒度控制：
- 死源和活源共享调度槽，活源延迟
- 健康状态无法自动流转（`active→stale→dead→grace→active`）
- 失败退避依赖手动干预，`cooldown_until` 字段未使用
- 无源级告警机制

Phase 3 实现源级调度器 + 健康状态机 + 告警规则，使系统能自动管理 40+ 源的调度生命周期。

## What Changes

### Backend 新增

| 文件 | 用途 |
|------|------|
| `backend/services/source_scheduler_service.py` | 源级调度器：优先级队列 + 并发控制 + 周期调度 |
| `backend/services/source_health_machine.py` | 健康状态机：5 状态自动流转 + 失败退避 |
| `backend/services/source_alerter.py` | 告警规则引擎：阈值触发 + 告警记录 |
| `backend/services/source_prober.py` | 死源探活：HEAD/GET 探测 + 恢复入 grace |
| `backend/repository/source_scheduler_repo.py` | 调度器仓储：待调度源查询 + 锁管理 |
| `backend/repository/source_alert_repo.py` | 告警记录仓储：写入/查询/聚合 |

### Backend 修改

| 文件 | 变更 |
|------|------|
| `backend/scheduler/jobs.py` | 新增 3 个 job：`source_scheduler_tick_job`、`source_probe_job`、`source_alert_eval_job` |
| `backend/scheduler/scheduler.py` | 注册 3 个新 job |
| `backend/collectors/base.py` | 旁路写入 `crawler_runs` 统计到 `source_scheduler_service` 的健康反馈 |
| `backend/services/collection_service.py` | 收集完成后触发健康状态检查 |

### 数据库

| 变更 | 说明 |
|------|------|
| `057_crawler_v2_phase3.sql` | 新增 `source_alerts` 表 + `crawler_sources` 补充字段 |

## Impact

- Affected specs: `phase2-quality-gate-upgrade` (依赖其 rejection_log 作为告警输入)
- Affected code: `scheduler/`, `services/`, `collectors/`, `repository/`
- **BREAKING**: 无（所有新增均旁路，不改变现有采集逻辑）

## ADDED Requirements

### Requirement 3.1: 源级调度器

源级调度器 `SourceSchedulerService` 以独立 APScheduler job 运行，每 60s tick 一次。

#### Scenario: 每 tick 查询待调度源
- **WHEN** `source_scheduler_tick_job` 触发
- **THEN** 查询 `crawler_sources` 中 `enabled=1 AND status!='dead' AND status!='disabled' AND (cooldown_until IS NULL OR cooldown_until < datetime('now'))` 的源
- **THEN** 按 `priority DESC` 排序，取并发度上限（默认 3）的源出队执行
- **THEN** 对每个选中源调用 `CollectionService.run_one(source_id)` 执行单源采集

#### Scenario: 单源采集反馈
- **WHEN** 单源采集完成
- **THEN** 写 `crawler_runs` 记录（`fetched_count`, `accepted_count`, `duration_ms`, `status`）
- **THEN** 调用 `SourceHealthMachine.apply_run_result(source_id, run_result)` 更新健康状态

#### Scenario: 失败退避
- **WHEN** 源连续失败 3 次
- **THEN** 状态流转 `active → stale`
- **WHEN** 源连续失败 5 次
- **THEN** 状态流转 `stale → dead`
- **THEN** 设置 `cooldown_until = now + 2^min(consecutive_failures-5, 6) * 300s`（指数退避，上限 2^6 * 300s = 5.33h）
- **WHEN** 源单轮产出 > 0
- **THEN** 重置 `consecutive_failures = 0`，如状态为 `stale` 则回 `active`

#### Scenario: 优先级抢占
- **WHEN** 高优先级源（`priority > 80`）等待调度
- **THEN** 当前并发槽被低优先级源占用时，不抢占（等待下一 tick）
- **THEN** 每 tick 重新按优先级排序，确保高优先级源优先获得空闲槽

#### Scenario: 并发控制
- **WHEN** 待调度源数量 > 并发上限
- **THEN** 按优先级排序，取前 N 个执行
- **THEN** 剩余源等待下一 tick（60s 后）
- **CONFIGURATION**: 并发度通过 `config.py` 的 `SOURCE_SCHEDULER_CONCURRENCY` 控制，默认 3

### Requirement 3.2: 健康状态机

健康状态机 `SourceHealthMachine` 管理 `crawler_sources.status` 的自动流转。

#### 状态流转图

```
active ──(连续失败3次)──→ stale ──(连续失败5次)──→ dead ──(探活成功)──→ grace ──(连续3轮有产出)──→ active
  │                        │                                                    │
  └──(单轮产出>0)──重置失败计数┘                                                    └──(正常周期调度)
```

#### Scenario: active → stale 下沉
- **WHEN** `apply_run_result` 收到连续第 3 次失败
- **THEN** `status = 'stale'`, `consecutive_failures = 3`
- **THEN** 写 log.warning
- **THEN** 源仍被调度（但处于"需关注"状态）

#### Scenario: stale → dead 下沉
- **WHEN** `apply_run_result` 收到连续第 5 次失败（累计 5）
- **THEN** `status = 'dead'`, `consecutive_failures = 5`, 设置 `cooldown_until`
- **THEN** 源停止调度，释放调度槽
- **THEN** 写 log.error

#### Scenario: stale → active 恢复
- **WHEN** `apply_run_result` 收到单轮产出 > 0
- **THEN** `consecutive_failures = 0`, `status = 'active'`
- **THEN** 写 log.info

#### Scenario: dead → grace 探活恢复
- **WHEN** `source_probe_job` 对 dead 源 HEAD/GET 成功（2xx/3xx）
- **THEN** `status = 'grace'`, `consecutive_failures = 0`
- **THEN** 源重新进入调度队列

#### Scenario: grace → active 验证
- **WHEN** `apply_run_result` 收到连续第 3 轮产出 > 0
- **THEN** `status = 'active'`
- **THEN** 源计入"活跃源"统计

#### Scenario: grace → dead 回退
- **WHEN** `apply_run_result` 在 grace 期间收到任何失败
- **THEN** `consecutive_failures` 重置计数，但 `status` 保持 `grace`
- **WHEN** grace 期间连续失败 3 次
- **THEN** `status = 'dead'`, 回退到 dead 状态

### Requirement 3.3: 死源探活

死源探活 `SourceProber` 每天固定时间（默认 03:30 Asia/Shanghai）对 dead 源执行 HEAD/GET 探测。

#### Scenario: 每日探活
- **WHEN** `source_probe_job` 触发（每日 03:30 Asia/Shanghai）
- **THEN** 查询 `crawler_sources WHERE status='dead' AND enabled=1`
- **THEN** 对每个 dead 源执行 HEAD 请求（超时 10s）
- **THEN** HEAD 405/501 时 fallback 到 GET
- **THEN** 2xx/3xx → `status = 'grace'`, `consecutive_failures = 0`
- **THEN** 4xx/5xx → 保留 `dead`, 更新 `last_error` + `last_yield_at`

#### Scenario: 手动探活
- **WHEN** 用户通过 API 触发单源探活
- **THEN** 执行相同逻辑，返回探测结果

### Requirement 3.4: 源级告警

源级告警 `SourceAlerter` 基于阈值触发告警，写入 `source_alerts` 表。

#### 告警规则表

| 告警 | 条件 | 级别 | 频率限制 |
|------|------|------|---------|
| 连续失败 | `consecutive_failures >= 5` | P1 | 每源每 24h 一次 |
| 拒绝率异常 | 单轮 `rejection_rate > 30%` | P2 | 每源每 24h 一次 |
| HTTP 状态异常 | 单轮 HTTP 4xx/5xx | P2 | 每源每 24h 一次 |
| 耗时异常 | 单轮 `duration_ms > 30000` | P2 | 每源每 24h 一次 |
| URL 校验通过率低 | `url_check_pass_rate < 80%` | P2 | 每源每 24h 一次 |
| 核心 P0 源死亡 | `status='dead' AND priority >= 80` | P1 | 每源每 24h 一次 |

#### Scenario: 告警触发
- **WHEN** `source_alert_eval_job` 触发（每 300s）
- **THEN** 查询最近 24h 的 `crawler_runs` 聚合数据
- **THEN** 对每条活跃源检查告警规则
- **THEN** 命中规则 → 写入 `source_alerts`，避免 24h 内重复告警
- **THEN** 写 log.warning

#### Scenario: 告警查询
- **WHEN** 用户请求 `GET /api/sources/alerts`
- **THEN** 返回 `source_alerts` 表分页结果（`created_at DESC`）
- **THEN** 支持 `source_id`、`level`、`since` 筛选

### Requirement 3.5: 健康状态 API 端点

#### Scenario: 查询源健康状态
- **WHEN** 用户请求 `GET /api/sources/health`
- **THEN** 返回所有源的 `id`, `name`, `status`, `health_score`, `consecutive_failures`, `last_success_at`, `last_yield_at`, `last_error`, `cooldown_until`

#### Scenario: 查询源统计
- **WHEN** 用户请求 `GET /api/sources/stats`
- **THEN** 返回聚合统计：`total`, `active`, `grace`, `stale`, `dead`, `disabled`, `active_rate`

#### Scenario: 手动触发探活
- **WHEN** 用户请求 `POST /api/sources/{source_id}/probe`
- **THEN** 执行单源探活，返回结果

## ADDED Requirements: Seed Data

### Requirement 3.6: 现有 collector 映射到 crawler_sources

将现有 14 个 collector 的源配置映射到 `crawler_sources` 表（seed 数据已在 Phase 0 完成，Phase 3 使用这些数据驱动调度）。

---

## Technical Decisions

### 1. 调度粒度：独立 tick 而非每个源一个 APScheduler job
- **选择**: 单个 `source_scheduler_tick_job` 每 60s tick 一次，内部查询待调度源
- **理由**: 40+ 源各注册一个 APScheduler job 会导致调度器 job 表膨胀，且 APScheduler 的 IntervalTrigger 不支持动态调整（如失败退避后的 `cooldown_until`）
- **权衡**: 60s 的 tick 间隔意味着非紧急源最多延迟 60s 被调度，可接受

### 2. 健康状态机与 `source_health_check_job` 的关系
- **选择**: 新建 `SourceHealthMachine` 替代现有的 `source_health_check_job`（保留后者作为兼容层）
- **理由**: 现有 `source_health_check_job` 只做简单的健康检查，不具备状态流转能力
- **迁移**: 保留 `source_health_check_job` 注册，其内部委托新 `SourceHealthMachine` 执行

### 3. 告警去重
- **选择**: 每源每告警类型 24h 内最多一次
- **理由**: 避免连续失败触发告警风暴
- **实现**: 通过 `source_alerts` 表查询 `alert_type + source_id + created_at > now - 24h` 去重

### 4. 源级调度 vs 现有 collect_all_job
- **选择**: 并行运行。`collect_all_job` 继续作为"全量采集"兜底（每 300s），`source_scheduler_tick_job` 作为"源级精准调度"（每 60s）
- **理由**: 迁移过渡期需要双轨运行，确保无遗漏
- **后续**: Phase 4（旧系统下线）时移除 `collect_all_job` 的 collector 遍历逻辑