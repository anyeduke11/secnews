# Phase 9 — 资讯抓取流程标准化（News Crawl Standardization）

> **版本**: v1.9
> **日期**: 2026-07-25
> **spec 路径**: `.trae/specs/phase9-crawl-standardize/`
> **前置**: Phase 8 catchup 完成 (commit b402856)

## 1. 背景与目标

### 1.1 用户诉求

> "固化并标准化资讯抓取流程，确保服务每日启动后自动执行以下操作：从数据源抓取时间范围为【本周星期一 00:00:00 至当前系统时间】的全部资讯内容。流程需包含数据完整性验证、异常处理机制、抓取进度记录及日志输出功能，确保在服务重启或中断后能从断点继续执行，避免数据重复抓取或遗漏。"

### 1.2 三大硬性要求

1. **断点续传**：服务重启 / 抓取中断后，下次启动能从上次完成的源继续（**避免重复抓或漏抓**）
2. **数据完整性验证**：跑完一轮后自动检查 4 类异常（源退化 / 时间窗口缺口 / 分类级异常 / 跨源一致性）
3. **结构化日志输出**：所有抓取事件（开始 / 单源完成 / 单源失败 / 整轮完成 / 验证完成）走统一 schema，便于监控

### 1.3 不在范围内

- ❌ 跨机抓取（本 Phase 仅本机）
- ❌ 智能调度（仍然固定「每周一 00:00 → 现在」窗口）
- ❌ AI 决策（验证规则是确定性的，不调用 LLM）

## 2. 数据模型

### 2.1 新增表（migration 042）

#### catchup_checkpoints（每 run × 每源的进度）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| run_id | INTEGER NOT NULL | catchup_runs.id |
| category | TEXT NOT NULL | ai / security / tech / ... |
| source_name | TEXT NOT NULL | hn / ph / ... |
| status | TEXT CHECK | pending / done / failed / skipped |
| items_count | INTEGER DEFAULT 0 | 本源抓到的 item 数 |
| started_at | TEXT | |
| finished_at | TEXT | |
| error_msg | TEXT | 失败原因（failed 时填） |

约束：`UNIQUE(run_id, category, source_name)`

#### collect_validations（每 run 的验证结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| run_id | INTEGER NOT NULL | |
| validation_type | TEXT CHECK | source_regression / time_coverage_gap / category_anomaly / cross_source |
| severity | TEXT CHECK | info / warn / error |
| payload | TEXT | JSON，详情 |
| detected_at | TEXT | |
| resolved_at | TEXT | 解决时间（可选） |

### 2.2 4 类验证规则

| 类型 | 触发 | 严重度 | 阈值 |
|------|------|--------|------|
| **source_regression** | 历史 yield > 0 但本次 = 0 | warn | 100% 退化 |
| | 历史 yield > 0 但本次 < 30% | info | 70%+ 退化 |
| **time_coverage_gap** | 1h bins 连续 ≥ 3 个空 | warn | 3h+ 静默 |
| | 单个 1h 空 | info | 避免误报 |
| **category_anomaly** | 本次 > 2x 历史 avg | info | 可能是重复抓 |
| | 本次 < 30% avg AND avg > 5 | warn | 源大面积失效 |
| | 本次 = 0 AND avg > 0 | error | 整分类断了 |
| **cross_source** | 跨源转载比 > 80% | info | 重复抓 |
| | 跨源转载比 < 20% AND total ≥ 10 | info | 源之间太孤立 |

## 3. 核心实现

### 3.1 文件清单

| 文件 | 职责 |
|------|------|
| `backend/repository/catchup_checkpoint_repo.py` | catchup_checkpoints CRUD |
| `backend/repository/migrations/042_v1.9_catchup_checkpoints.sql` | 新表 schema |
| `backend/services/collection_logger.py` | 结构化事件日志（`log_collect_event`） |
| `backend/services/collect_validator.py` | 4 类数据完整性验证 |
| `backend/services/catchup_service.py` | 集成 checkpoint + 日志 + 验证 |
| `backend/main.py` | lifespan 启动钩子里调 `enqueue_catchup` |

### 3.2 流程（`_execute_catchup_run` 11 步）

1. 读 run 配置（categories / max_per_source）
2. 选源：跳过 `source_stats.status='dead' AND last_checked_at < now-24h`
3. 临时改每个 collector 的 `sources`（过滤 dead）+ `max_items`（cap）
4. **续传**：同一 (cat, source) 在最近 24h 已 done → pre-mark `skipped`
5. 复用 `CollectionService.run_one()` 跑并发抓取
6. **per-source checkpoint**：写 `catchup_checkpoints` (done / failed)
7. **结构化日志**：`source_done` / `source_failed` / `collect_done`
8. 持续 update progress (ingested / succeeded)
9. 触发 `trend_rebuild_job`（后台，不阻塞）
10. **4 类数据完整性验证** → 写 `collect_validations`（不阻塞终态）
11. 终态：success（all done）/ partial（部分失败）/ failed（整轮炸）

### 3.3 续传策略

- 同一 `(category, source_name)` 在 24h 内 `status='done'` → 本 run 跳过
- 跳过时写 `source_skipped` 事件 + checkpoint `status=skipped`
- 跳过的源**不被覆盖**（per-source loop 里有 check）

### 3.4 启动钩子（`main.py:lifespan`）

```python
# v1.9 Phase 9: 启动后自动追抓「本周一 00:00 (Asia/Shanghai) → 现在」
try:
    if should_enqueue_auto():  # 5 分钟防抖
        since_iso = current_week_start().astimezone(timezone.utc).isoformat()
        run_id = await enqueue_catchup(
            mode="auto",
            since=since_iso,
            until=None,
            categories=None,
            max_per_source=30,
        )
        mark_auto_enqueued()
except Exception as e:
    log.warning(f"startup auto-catchup failed (ignored): {e}")
```

- 用 `background task` 不阻塞 startup
- 5 分钟防抖避免 watchdog / 重启风暴重复 enqueue
- 失败不阻塞服务启动

### 3.5 异常隔离

- 单 collector crash → 不影响其他 category
- 单源失败 → checkpoint 标 `failed`，整轮仍可 `partial` 成功
- 整轮 crash → 标 `failed` + 写 `collect_done(failed)` 事件
- 验证 crash → 只记 warn，不影响终态

## 4. 关键决策

1. **checkpoint 表与 collect_validations 表分离**：前者是进度，后者是观测。两表 join 按 run_id。
2. **续传窗口 24h**：太短容易漏，太长容易 stale。24h = 1 天。
3. **失败源不重试**：本 run 内失败即放弃，下次 run 重新尝试。避免雪崩。
4. **验证不阻塞终态**：即使 validate_and_persist crash，run 仍能 finish。
5. **跳过死源（>24h）** 复用 `source_stats` 表：避免反复尝试死源。
6. **不持久化 Playbook / 配置到事件**：事件只记可观测字段，详情走 API `/api/catchup/{run_id}`。
7. **mode=auto 与 mode=manual 解耦**：auto 永远不抛 409，与 manual 可并发。

## 5. 测试覆盖

### 5.1 后端

| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `test_catchup_checkpoint_repo.py` | 13 | upsert / get / list / mark_done / mark_failed / mark_skipped / list_recent_done |
| `test_collection_logger.py` | 8 | log_collect_event / log_validation / 字段规范化 |
| `test_collect_validator.py` | 11 | 4 类验证（每类 2-3 用例）+ report 序列化 |
| `test_catchup_phase9.py` | 8 | 集成：per-source checkpoint / 续传 / 结构化事件 / 验证 / 状态恢复 / 整轮崩 |

**Phase 9 8/8 + 32/32 = 40/40 全部 PASS**。

### 5.2 前端

无新组件（Phase 9 是纯后端 / 流程改造）。

## 6. 监控与运维

### 6.1 通过结构化日志看

```bash
# 本周跑了几次 catchup
grep '"event": "collect_start"' logs/*.log | jq '.run_id, .sources_attempted'

# 哪些源失败了
grep '"event": "source_failed"' logs/*.log | jq '.category, .source, .error'

# 验证报告
grep '"event": "validation"' logs/*.log | jq '.validation_type, .severity, .payload'
```

### 6.2 通过 API 看

- `GET /api/catchup/runs?limit=10` — 最近 10 次 run
- `GET /api/catchup/runs/{run_id}/checkpoints` — per-source 进度
- `GET /api/catchup/runs/{run_id}/validations` — 验证结果

## 7. 未来 Phase 候选

- ❌ 跨机抓取：source_stats 同步、scheduler 分发
- ❌ 智能续传：失败源按指数退避重试
- ❌ LLM 决策验证：异常时调 LLM 二次确认
