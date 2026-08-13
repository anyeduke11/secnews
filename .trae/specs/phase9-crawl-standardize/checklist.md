# Phase 9 — 资讯抓取流程标准化 验证清单

> **spec**: `.trae/specs/phase9-crawl-standardize/spec.md`
> **tasks**: `.trae/specs/phase9-crawl-standardize/tasks.md`

## 1. 数据模型

- [x] 1.1 迁移文件 `042_v1.9_catchup_checkpoints.sql` 创建 2 张表（catchup_checkpoints / collect_validations）
- [x] 1.2 catchup_checkpoints 字段完整（run_id / category / source_name / status / items_count / started_at / finished_at / error_msg）
- [x] 1.3 collect_validations 字段完整（run_id / validation_type / severity / payload / detected_at / resolved_at）
- [x] 1.4 约束完整：UNIQUE(run_id, category, source_name)、CHECK(status IN (...))、CHECK(validation_type IN (...))、CHECK(severity IN (...))
- [x] 1.5 6 个索引全部创建（idx_ckpt_run / idx_ckpt_status_run / idx_ckpt_lookup / idx_validation_run / idx_validation_severity / idx_validation_unresolved）
- [x] 1.6 db.py init_db 加载 042 迁移

## 2. Checkpoint Repository

- [x] 2.1 `backend/repository/catchup_checkpoint_repo.py` 实现 7 个 CRUD 方法
- [x] 2.2 upsert 支持插入和更新（ON CONFLICT 逻辑）
- [x] 2.3 list_recent_done 支持 24h 窗口续传查询
- [x] 2.4 test_catchup_checkpoint_repo.py 13 用例全通过

## 3. Collection Logger

- [x] 3.1 `backend/services/collection_logger.py` 实现结构化日志
- [x] 3.2 支持 6 种事件类型（collect_start / source_done / source_failed / source_skipped / collect_done / validate_done）
- [x] 3.3 统一 schema：event / timestamp / run_id / category / source / duration_ms / items_count / error
- [x] 3.4 log_validation 支持验证日志输出
- [x] 3.5 test_collection_logger.py 8 用例全通过

## 4. Collection Validator

- [x] 4.1 `backend/services/collect_validator.py` 实现 4 类验证函数
- [x] 4.2 source_regression：历史 yield > 0 但本次 = 0 → warn；> 70% 退化 → info
- [x] 4.3 time_coverage_gap：1h bins 连续 ≥ 3 个空 → warn；单个空 → info
- [x] 4.4 category_anomaly：本次 > 2x 历史 avg → info；< 30% avg → warn；= 0 且 avg > 0 → error
- [x] 4.5 cross_source：转载比 > 80% → info；< 20% 且 total ≥ 10 → info
- [x] 4.6 validate_and_persist 写入 collect_validations 表
- [x] 4.7 list_recent_validations 支持按 run_id 筛选 + 包含已解决
- [x] 4.8 auto_resolve_old_validations 归档 7 天前的旧验证
- [x] 4.9 test_collect_validator.py 11 用例全通过

## 5. Catchup Service

- [x] 5.1 per-source checkpoint 记录（开始 upsert pending，完成 mark_done/failed）
- [x] 5.2 续传策略：同一 (cat, source) 24h 内 done → 本 run 跳过（skipped）
- [x] 5.3 结构化日志集成：collect_start / source_done / source_failed / source_skipped / collect_done
- [x] 5.4 collect_validator 集成：run 完成后调 validate_and_persist
- [x] 5.5 异常隔离：单源失败不阻塞整轮，整轮崩溃标 failed
- [x] 5.6 mode=auto 与 mode=manual 解耦（auto 不阻塞 manual）
- [x] 5.7 test_catchup_phase9.py 8 用例全通过
- [x] 5.8 test_catchup_service.py 全部通过

## 6. API Layer

- [x] 6.1 `GET /api/catchup/status` 返回 validation 摘要（last_run_validations + validation_summary）
- [x] 6.2 `GET /api/catchup/runs/{run_id}/checkpoints` — per-source 进度
- [x] 6.3 `GET /api/catchup/runs/{run_id}/validations` — 验证结果
- [x] 6.4 test_catchup_api.py 全部通过

## 7. Startup Integration

- [x] 7.1 `main.py` lifespan 中添加启动后自动追抓钩子
- [x] 7.2 5 分钟防抖（should_enqueue_auto + mark_auto_enqueued）
- [x] 7.3 时间窗口：`current_week_start() UTC → now`
- [x] 7.4 异常隔离：失败不阻塞服务启动，只记 warn
- [x] 7.5 catchup_watchdog_job 每 60s 检测孤儿 run
- [x] 7.6 source_revival_check_job 每日 03:00 检测死源复活
- [x] 7.7 collect_validations_cleanup_job 每日 04:00 归档旧 validation
- [x] 7.8 3 个 job 全部注册到 scheduler

## 8. 测试覆盖率

- [x] 8.1 后端总测试用例数 ≥ 60（checkpoint_repo 13 + logger 8 + validator 11 + phase9 8 + api 7 + service + watchdog = 60+）
- [x] 8.2 后端测试全部通过：`.venv/bin/python -m pytest backend/tests/test_catchup_checkpoint_repo.py backend/tests/test_collection_logger.py backend/tests/test_collect_validator.py backend/tests/test_catchup_phase9.py backend/tests/test_catchup_api.py backend/tests/test_catchup_service.py backend/tests/test_catchup_watchdog.py -v`
- [x] 8.3 编译检查通过

## 9. 文档

- [x] 9.1 `docs/phase9_changelog.md` 更新（Phase 9 新增功能说明）
- [x] 9.2 `docs/hotspot_v2.0_dev_plan.md` 标记 Phase 9 状态
- [x] 9.3 `docs/hotspot_v2.0_PRD.md` 中的 Phase 9 相关章节对齐