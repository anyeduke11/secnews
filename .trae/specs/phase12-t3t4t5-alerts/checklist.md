# Checklist — Phase 12: T3/T4/T5 触发器 + 告警系统

## T3 触发器
- [x] T3Trigger 类实现 `run_once()` 方法
- [x] `_fetch_candidates()` 查询 lifecycle='kl:link' 的 items
- [x] `_count_links(item_id)` 查询 knowledge_links 关联数
- [x] 关联数 ≥ 3 的 items 推进到 structure
- [x] 关联数 < 3 的 items 也推进（标 low_link）
- [x] `_generate_summary(item)` 从 content 提取前 200 字
- [x] 异常时入死信队列
- [x] KLMetrics 指标正确递增

## T4 触发器
- [x] T4Trigger 类实现 `run_once()` 方法
- [x] `_fetch_candidates()` 查询 lifecycle='kl:structure' 的 items
- [x] `_get_latest_score(item_id)` 从 ai_scores 取分
- [x] score ≥ 8.0 推进到 publish
- [x] score < 8.0 跳过
- [x] 24h 稳定窗口检查（updated_at < now - 24h）
- [x] `_write_to_md(item)` 调用 `write_item_to_md()`
- [x] .md 文件写入 knowledge/items/{id}.md

## T5 触发器
- [x] T5Trigger 类实现 `rollback(item_id)` 方法
- [x] 备份 .md 文件到 knowledge/backups/
- [x] 标记 stale_at 时间戳
- [x] lifecycle 更新为 kl:refine
- [x] 非 publish 状态拒绝回滚
- [x] API 端点 `POST /api/kl/rollback/{item_id}`
- [x] 备份目录自动创建

## 调度器
- [x] jobs.py 新增 `kl_trigger_t3_job`（600s）
- [x] jobs.py 新增 `kl_trigger_t4_job`（1800s）
- [x] scheduler.py job 34 — `kl_trigger_t3`
- [x] scheduler.py job 35 — `kl_trigger_t4`

## 告警规则引擎
- [x] migration 048 创建 `alert_rules` 表
- [x] migration 048 创建 `alert_events` 表
- [x] 3 条种子数据（tech_stack_cve, critical_cve, bid_match）
- [x] AlertEngine 类 `evaluate_all()` 方法
- [x] 规则 1：tech_stack CVE 影响触发告警
- [x] 规则 2：关键 CVE (CVSS ≥ 9.0) 触发告警
- [x] 规则 3：标讯命中触发告警
- [x] GET /api/alerts/v2 返回告警列表
- [x] GET /api/alerts/v2/unread-count 返回未读数
- [x] PUT /api/alerts/v2/{id}/read 标记已读
- [x] PUT /api/alerts/v2/read-all 全部已读
- [x] POST /api/alerts/v2/evaluate 手动触发评估

## 告警 UI
- [x] AlertCenter.tsx 渲染 Inbox 列表
- [x] 红色横幅显示未读告警数
- [x] severity 颜色区分
- [x] 标记已读/全部已读功能

## 测试
- [x] test_t3_trigger.py 10/10 PASS
- [x] test_t4_trigger.py 10/10 PASS
- [x] test_t5_trigger.py 11/11 PASS
- [x] test_alert_engine.py 15/15 PASS
- [x] Phase 10 T1/T2 回归测试 22/22 PASS 无退化
- [x] Phase 11 回归测试 138 passed 无退化
- [x] 全量回归测试通过