# Phase 8 — Catchup 验收清单

> 配套 spec.md + tasks.md；逐项打勾。
> 状态：✅ done / ⚠️ partial / ❌ not done / 🚫 skipped

## 0. 文档

- [ ] spec.md 存在且包含 15 个章节
- [ ] tasks.md 存在且分组完整 (A-I)
- [ ] checklist.md 存在（本文件）
- [ ] docs/phase8_changelog.md 存在
- [ ] docs/RUNBOOK.md 含 "如何手动追抓" 段落
- [ ] README.md 在 Phase 路线图加 v1.8

## 1. 数据模型

- [ ] A1. migration 040 创建
- [ ] A2. `catchup_runs` 表 schema 完整（11 字段 + 2 索引）
- [ ] A3. `mode` CHECK 约束 (auto/manual)
- [ ] A4. `status` CHECK 约束 (running/success/partial/failed/aborted)
- [ ] A5. `since_window` 非空，`until_window` 可空
- [ ] A6. `categories` JSON 数组 (TEXT)
- [ ] A7. `started_at` 非空
- [ ] A8. migration 跑通 `python backend/repository/db.py migrate`
- [ ] A9. 旧数据兼容（无破坏性）

## 2. Repository (`backend/repository/catchup_repo.py`)

- [ ] CRUD: create / get / list_recent / update_progress / finish
- [ ] 状态机校验：running → {success, partial, failed, aborted}
- [ ] 不允许从 terminal 状态回 running
- [ ] 单测：CRUD 路径全覆盖
- [ ] 单测：并发更新不丢字段

## 3. Watchdog (`catchup_watchdog_job`)

- [ ] 60s 一次 IntervalTrigger
- [ ] 扫 `collection_runs` 找 started_at < now-600s AND finished_at IS NULL
- [ ] 标 `status='failed', error_msg='watchdog: timeout after 600s'`
- [ ] enqueue 一次 auto catchup (since=最早孤儿时刻, until=now)
- [ ] enqueue 失败仅 log，不抛
- [ ] watchdog 自身有 timeout 保护（≤ 30s 内完成）
- [ ] 单测：8 用例全 PASS

## 4. Catchup Service

- [ ] 独立 `asyncio.Lock`（与 `collect_all` 隔离）
- [ ] `run()` 主流程覆盖：选源 → 抓取 → 写库 → 触发 trend_rebuild
- [ ] 跳过 `source_stats.status='dead' AND updated_at < now-24h` 的源
- [ ] `max_per_source` 截断每源抓取数
- [ ] 源失败不中断整轮（标 partial）
- [ ] abort 中断支持（asyncio.CancelledError → status='aborted'）
- [ ] auto 与 manual 不互斥（auto 优先级低，让 manual 先跑）
- [ ] 单测：12 用例全 PASS

## 5. API 端点

- [ ] `POST /api/catchup/run` 返回 202 + run_id
- [ ] `POST /api/catchup/run` 重复返回 409 + active_run_id
- [ ] `POST /api/catchup/run` 参数校验 (since > until → 400)
- [ ] `POST /api/catchup/run` 大窗口 (>30d) 拒绝
- [ ] `GET /api/catchup/status` 返回 current + recent (≤7)
- [ ] `POST /api/catchup/abort` 成功
- [ ] `POST /api/catchup/abort` 无 in-flight 返回 404
- [ ] 路由注册到 `backend/api/__init__.py`
- [ ] 单测：10 用例全 PASS

## 6. 调度器

- [ ] job 28 `catchup_watchdog` 注册 (60s)
- [ ] job 29 `source_revival_check` 注册 (daily 03:00)
- [ ] `/api/health` 暴露 `last_orphan_recovery_at`
- [ ] `last_orphan_recovery_at` 在 watchdog 触发时更新
- [ ] health 端点 JSON 包含 catchup 状态段

## 7. 源复活

- [ ] `source_revival_service.py` 存在
- [ ] 选 dead ≥ 7d 源
- [ ] HEAD 请求单源（不抓内容）
- [ ] 复活 → source_stats.status='stale' (走后续 health check 验证)
- [ ] 仍死 → source_stats.status='dead' + updated_at=now
- [ ] 单测：5 用例全 PASS

## 8. 前端组件

- [ ] `<CatchupButton />` 存在
- [ ] 状态机：idle / stale / running / success / failed
- [ ] stale 检测：now - last_ingested_at > 30min
- [ ] 弹窗：时间范围 / 分类多选 / max_per_source
- [ ] SSE 订阅 `/api/events/stream` 拿进度
- [ ] abort 按钮（仅 running 状态可见）
- [ ] 成功 toast 3s
- [ ] 失败 toast 5s + retry
- [ ] 嵌入首页 "本周资讯" 区块顶部
- [ ] 主题切换：dark/light 兼容
- [ ] 单测：8 用例全 PASS

## 9. 端到端验收

- [ ] 演练 1：人为制造孤儿 (kill -STOP) → watchdog 10min 内恢复
- [ ] 演练 2：UI 手动追抓 → 5min 内 100+ 条入库
- [ ] 演练 3：追抓跳过 64 bid 源（节省时间）
- [ ] 演练 4：abort 立即生效，status='aborted'
- [ ] 演练 5：trend 重建后 `/api/trends?hours=24` 立即有数据
- [ ] 演练 6：watchdog + manual catchup 并发互不阻塞

## 10. 测试覆盖

- [ ] 后端：4 个测试文件 (watchdog, service, api, e2e)
- [ ] 后端：35 用例全 PASS
- [ ] 前端：1 个测试文件 (CatchupButton)
- [ ] 前端：8 用例全 PASS
- [ ] TypeScript: `npx tsc --noEmit` 0 error
- [ ] 回归：现有 67+ 后端测试无回归
- [ ] 回归：现有 240+ 前端测试无回归

## 11. 性能

- [ ] 追抓期间 CPU 峰值 +10% (vs 正常 collect_all)
- [ ] 追抓 24h 窗口 ≤ 5min (含 5 分类 × 平均 6 源)
- [ ] 追抓 7d 窗口 ≤ 30min (含 6 分类 × 平均 6 源)
- [ ] 不会因为 catchup 阻塞 `collect_all` 主循环

## 12. 安全

- [ ] `/api/catchup/*` 端点仅监听 127.0.0.1（不在 0.0.0.0 暴露）
- [ ] 鉴权：仅本地 loopback 可调（防 CSRF）
- [ ] 速率限制：同一 IP 5min 内最多 1 次 manual catchup
- [ ] 输入校验：since/until 必须是 ISO 8601
- [ ] 输入校验：categories 必须是 6 大分类之一
- [ ] 输入校验：max_per_source 1-100

## 13. 可观测性

- [ ] 每次 catchup 写日志 (start / end / 每源结果)
- [ ] catchup 失败时 log error 等级
- [ ] 暴露 `last_orphan_recovery_at` 到 `/api/health`
- [ ] 暴露 `catchup.last_run` 到 `/api/health`
- [ ] SSE 事件 `catchup.progress` 含百分比 + 源计数

## 14. 兼容性

- [ ] 不破坏现有 `collect_all` 行为
- [ ] 不破坏现有 `collection_runs` 表结构
- [ ] 不破坏现有 `/api/health` 输出（仅追加字段）
- [ ] 不引入新依赖（除 fastapi 已有）
- [ ] 旧 hotspot.db 无 catchup_runs 表 → migration 自动创建

## 15. 文档完整性

- [ ] docs/phase8_changelog.md 包含：新增 / 修改 / 删除清单
- [ ] docs/RUNBOOK.md "如何手动追抓" 含 curl 示例
- [ ] README.md Phase 路线图加 v1.8
- [ ] spec.md 链接挂在 docs/INDEX.md（如有）
- [ ] API 端点 OpenAPI 自动文档正确

## 16. 回滚预案

- [ ] 步骤 1：停止后端
- [ ] 步骤 2：`DELETE FROM catchup_runs;` 不影响主表
- [ ] 步骤 3：从 `backend/scheduler/scheduler.py` 删 2 个 job
- [ ] 步骤 4：从 `backend/api/__init__.py` 删 catchup router
- [ ] 步骤 5：从 `frontend/src/components/` 删 `<CatchupButton />`
- [ ] 步骤 6：migration 040 可保留（不影响主表）
- [ ] 步骤 7：重启后端验证 collect_all 仍正常

## 17. 签字

- [ ] 实施者：________________
- [ ] 验收者：________________
- [ ] 日期：________________

## 18. 备注

- 本 spec 基于 2026-07-25 的 22h 假死事故复盘
- 根因：`collection_service.py:78-79` asyncio.Lock 跨进程失效
- 不在范围：修复根因（独立 PR，Phase 8 之后）
- 22h 漏抓估算：~500-800 条（按 collect_all 5min/次 × 260 次 × 平均 3 条 = 780）
- 恢复证明：2026-07-25 09:25-09:30 冷启动后 5min 入 109 条
