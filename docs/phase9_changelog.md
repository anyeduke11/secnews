# Phase 9 — 资讯抓取流程标准化 变更日志

> **版本**: v1.9
> **日期**: 2026-07-25
> **spec**: `.trae/specs/phase9-crawl-standardize/`
> **前置**: Phase 8 catchup 完成 (commit b402856)
> **状态**: ✅ 已完成

## 新增功能

### 1. 断点续传 (catchup_checkpoints)
- **migration 042**: 新增 `catchup_checkpoints` 表，per-source 粒度的断点记录
- **CatchupCheckpointRepository**: 7 个 CRUD 方法（upsert / get / list_by_run / mark_done / mark_failed / mark_skipped / list_recent_done）
- **续传策略**: 同一 (category, source_name) 在 24h 内 `status='done'` → 本 run 跳过，避免重复抓取
- **force 模式**: 支持跳过续传检查强制重抓（用于源失效后的恢复场景）

### 2. 数据完整性验证 (collect_validations)
- **migration 042**: 新增 `collect_validations` 表，4 类验证结果持久化
- **CollectionValidator**: 4 类验证规则
  - `source_regression`: 历史 yield > 0 但本次退化 → warn/error
  - `time_coverage_gap`: 1h 连续 ≥ 3 个空 bin → warn；单个空 → info
  - `category_anomaly`: 分类级总量突增/骤降 → info/warn/error
  - `cross_source`: 跨源转载比异常 → info
- 验证不阻塞终态：即使 `validate_and_persist` crash，run 仍能 finish

### 3. 结构化事件日志 (collection_logger)
- **CollectionLogger**: 统一 schema 的 6 种事件类型
  - `collect_start` / `source_done` / `source_failed` / `source_skipped` / `collect_done` / `validate_done`
- 统一字段：event / timestamp / run_id / category / source / duration_ms / items_count / error
- 支持 `log_validation` 输出验证日志

### 4. Catchup Service 集成
- per-source checkpoint 记录（开始 upsert pending，完成 mark_done/failed）
- 结构化日志集成（collect_start → source_done/failed → collect_done）
- collect_validator 集成（run 完成后调 validate_and_persist）
- 异常隔离：单源失败不阻塞整轮，整轮崩溃标 failed
- mode=auto 与 mode=manual 解耦（auto 不阻塞 manual）

### 5. API 扩展
- `GET /api/catchup/status` — 返回 validation 摘要
- `GET /api/catchup/runs/{run_id}/checkpoints` — per-source 进度
- `GET /api/catchup/runs/{run_id}/validations` — 验证结果

### 6. 启动钩子
- `main.py` lifespan 中添加启动后自动追抓钩子
- 时间窗口：`current_week_start() (Asia/Shanghai) → now`
- 5 分钟防抖避免 watchdog/重启风暴重复 enqueue

### 7. 调度器 Job (3 个)
- **catchup_watchdog** (60s): 检测孤儿 run（>10min 未完成）
- **source_revival_check** (每日 03:00): 检测死源复活
- **collect_validations_cleanup** (每日 04:00): 归档 7 天前的旧验证

## 数据库变更

| 迁移文件 | 操作 | 新增表 | 索引 |
|---------|------|--------|------|
| `042_v1.9_catchup_checkpoints.sql` | 新增 | `catchup_checkpoints` / `collect_validations` | 6 个 |

## 新增文件

| 文件 | 职责 |
|------|------|
| `backend/repository/catchup_checkpoint_repo.py` | catchup_checkpoints CRUD |
| `backend/repository/migrations/042_v1.9_catchup_checkpoints.sql` | 新表 schema |
| `backend/services/collection_logger.py` | 结构化事件日志 |
| `backend/services/collect_validator.py` | 4 类数据完整性验证 |

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/services/catchup_service.py` | 集成 checkpoint + 日志 + 验证 |
| `backend/api/catchup.py` | 扩展 checkpoint/validation 端点 |
| `backend/main.py` | lifespan 启动钩子 |
| `backend/scheduler/jobs.py` | 新增 3 个 job |
| `backend/scheduler/scheduler.py` | 注册 3 个 job |

## 测试覆盖

| 测试文件 | 用例数 | 状态 |
|---------|--------|------|
| `test_catchup_checkpoint_repo.py` | 13 | ✅ 全部通过 |
| `test_collection_logger.py` | 8 | ✅ 全部通过 |
| `test_collect_validator.py` | 11 | ✅ 全部通过 |
| `test_catchup_phase9.py` | 8 | ✅ 全部通过 |
| `test_catchup_api.py` | 7 | ✅ 全部通过 |
| `test_catchup_service.py` | 集成 | ✅ 全部通过 |
| `test_catchup_watchdog.py` | 集成 | ✅ 全部通过 |

**总计**: 60+ 用例全部通过

## 关键决策

1. checkpoint 表与 collect_validations 表分离：进度 vs 观测
2. 续传窗口 24h：不短不长
3. 失败源本 run 内不重试，下次 run 重新尝试
4. 验证不阻塞终态
5. 跳过死源（>24h）复用 source_stats 表
6. mode=auto 与 mode=manual 解耦