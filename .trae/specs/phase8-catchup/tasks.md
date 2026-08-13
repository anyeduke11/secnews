# Phase 8 — Catchup 任务清单

> 配套 spec.md；任务分组按"先数据后逻辑再 UI 再测试"。
> 状态：⏳ pending / 🔄 in_progress / ✅ done / ❌ blocked

## A. 数据模型（0.5d）

- [ ] A1. 创建 `040_v1.8_catchup_runs.sql` migration
- [ ] A2. 运行 `python backend/repository/db.py migrate` 验证 schema
- [ ] A3. 在 `_MAP.md` / `docs/_SCHEMA.md` 添加 `catchup_runs` 条目
- [ ] A4. 写 `backend/repository/catchup_repo.py` (CRUD + 状态机)
- [ ] A5. 写 `backend/tests/test_catchup_repo.py` (8 用例)

## B. Watchdog（0.5d）

- [ ] B1. 在 `backend/scheduler/jobs.py` 新增 `catchup_watchdog_job()`
- [ ] B2. 注册到 `backend/scheduler/scheduler.py` (id=28, IntervalTrigger(seconds=60))
- [ ] B3. 写 `backend/tests/test_catchup_watchdog.py` (8 用例)
  - [ ] B3.1 检测孤儿 started_at > 600s 未 finished
  - [ ] B3.2 边界：started_at = now - 600s 视为已孤儿
  - [ ] B3.3 边界：finished_at 已存在不触发
  - [ ] B3.4 多个孤儿 → 标记所有 + enqueue 1 次 catchup
  - [ ] B3.5 auto catchup since=最早孤儿时刻
  - [ ] B3.6 enqueue 失败不抛（仅 log）
  - [ ] B3.7 并发：watchdog 与 run_once 不冲突
  - [ ] B3.8 watchdog 自身的 timeout / 重入保护
- [ ] B4. `/api/health` 暴露 `last_orphan_recovery_at` 字段

## C. Catchup Service（0.5d）

- [ ] C1. 创建 `backend/services/catchup_service.py`
  - [ ] C1.1 `CatchupService` 类 + 独立 `asyncio.Lock`
  - [ ] C1.2 `run(mode, since, until, categories, max_per_source)` 主流程
  - [ ] C1.3 选源逻辑：跳过 `source_stats.status='dead' AND updated_at < now-24h`
  - [ ] C1.4 复用 `collection_service._crawl_one` 走每源抓取
  - [ ] C1.5 写库走 `hotspot_repo.upsert_batch`（自动去重）
  - [ ] C1.6 完成时触发 `trend_rebuild` job (force=True)
- [ ] C2. 并发：与 `collect_all` 互不阻塞（独立 lock）
- [ ] C3. 写 `backend/tests/test_catchup_service.py` (12 用例)
  - [ ] C3.1 锁隔离：两个 manual catchup 不能并发（409）
  - [ ] C3.2 auto catchup 与 manual 并行不互斥
  - [ ] C3.3 跳过 dead 源（mock source_stats）
  - [ ] C3.4 max_per_source 截断
  - [ ] C3.5 完整跑通 (e2e 单源 happy path)
  - [ ] C3.6 源失败 → 标 partial，不中断整轮
  - [ ] C3.7 abort 中断（asyncio.CancelledError）
  - [ ] C3.8 since 早于 earliest known 源不报错
  - [ ] C3.9 until 早于 since → 立即 success items=0
  - [ ] C3.10 触发 trend_rebuild 验证
  - [ ] C3.11 auto mode 优先级低于 manual
  - [ ] C3.12 失败时 DB 行标 status='failed' 含 error_msg

## D. API 端点（0.25d）

- [ ] D1. 创建 `backend/api/catchup.py` (3 端点)
  - [ ] D1.1 `POST /api/catchup/run` (202 accepted)
  - [ ] D1.2 `GET /api/catchup/status` (200 + current + recent 7)
  - [ ] D1.3 `POST /api/catchup/abort` (200)
- [ ] D2. 注册到 `backend/api/__init__.py` `register_routers()`
- [ ] D3. 写 `backend/tests/test_catchup_api.py` (10 用例)
  - [ ] D3.1 POST 成功返回 202 + run_id
  - [ ] D3.2 POST 重复返回 409
  - [ ] D3.3 POST 参数校验 (since > until)
  - [ ] D3.4 GET 无 in-flight 时 current_run=null
  - [ ] D3.5 GET 有 in-flight 时返回实时进度
  - [ ] D3.6 GET recent_runs 限制 7 条
  - [ ] D3.7 POST abort 成功
  - [ ] D3.8 POST abort 无 in-flight 返回 404
  - [ ] D3.9 鉴权：仅 local 127.0.0.1 可调（防 CSRF）
  - [ ] D3.10 大窗口 (since > 30d) 拒绝 → 400

## E. 调度器 + 源复活（0.25d）

- [ ] E1. 注册 job 29 `source_revival_check` (每日 03:00)
- [ ] E2. 写 `backend/services/source_revival_service.py`
  - [ ] E2.1 选 dead ≥ 7d 源
  - [ ] E2.2 对每个源做 1 次轻量 HEAD 请求
  - [ ] E2.3 复活 → source_stats.status='stale' (走后续 health check 验证)
  - [ ] E2.4 仍死 → 继续 'dead' + updated_at=now
- [ ] E3. 写 `backend/tests/test_source_revival.py` (5 用例)

## F. 前端（0.5d）

- [ ] F1. 创建 `frontend/src/components/CatchupButton.tsx`
  - [ ] F1.1 状态机：idle / stale / running / success / failed
  - [ ] F1.2 弹窗：时间范围 / 分类多选 / max_per_source
  - [ ] F1.3 SSE 订阅 `/api/events/stream` 拿进度
  - [ ] F1.4 abort 按钮（仅 running 状态可见）
- [ ] F2. 嵌入首页 "本周资讯" 区块顶部
- [ ] F3. CSS 主题跟随（dark/light）
- [ ] F4. 写 `frontend/src/components/CatchupButton.test.tsx` (8 用例)
  - [ ] F4.1 stale 状态高亮（last_ingested > 30min）
  - [ ] F4.2 idle 状态灰色
  - [ ] F4.3 点击弹窗 → 提交 → 进入 running
  - [ ] F4.4 SSE 进度事件更新数字
  - [ ] F4.5 成功 → green toast 3s
  - [ ] F4.6 失败 → red toast 5s + retry 按钮
  - [ ] F4.7 abort 按钮调 POST /abort
  - [ ] F4.8 SSE 断线 3s 后自动重连

## G. 端到端验收（0.5d）

- [ ] G1. 演练 1：人为制造孤儿
  - [ ] G1.1 `kill -STOP <uvicorn_pid>` 暂停 5min
  - [ ] G1.2 观察 `collection_runs` 出现 stuck 行
  - [ ] G1.3 watchdog 在 600s 内标 failed + 触发 auto catchup
  - [ ] G1.4 `kill -CONT` 恢复进程（catchup 跑完后）
- [ ] G2. 演练 2：UI 手动追抓
  - [ ] G2.1 首页点 "追抓资讯" → 弹窗
  - [ ] G2.2 选 since=now-24h, all categories
  - [ ] G2.3 进度条 5min 内推到 100%
  - [ ] G2.4 toast 显示 "追抓 N 条 / M 分类 / Xs"
  - [ ] G2.5 `/api/trends?hours=24` 立即有数据（验证 trend 重建）
- [ ] G3. 演练 3：bid 源跳过
  - [ ] G3.1 确认 catchup 不尝试 64 个 bid 源（节省时间）
  - [ ] G3.2 catchup_runs.sources_attempted < collection_runs.sources_attempted
- [ ] G4. 演练 4：abort
  - [ ] G4.1 触发长窗口 catchup (since=now-14d)
  - [ ] G4.2 30s 后点 abort
  - [ ] G4.3 catchup_runs.status='aborted', finished_at 已设

## H. 文档（0.25d）

- [ ] H1. 创建 `docs/phase8_changelog.md`
- [ ] H2. 更新 `docs/RUNBOOK.md` 加 "如何手动追抓"
- [ ] H3. 更新 `README.md` 在 Phase 路线图加 v1.8
- [ ] H4. 更新 `.trae/specs/INDEX.md`（如有）

## I. CI / Regression（0.25d）

- [ ] I1. 跑全套后端测试，确认无回归（67+ 文件）
- [ ] I2. 跑全套前端测试，确认无回归（240+ 用例）
- [ ] I3. 跑 `npx tsc --noEmit`
- [ ] I4. 更新 `.github/workflows/ci.yml`（如需要）
- [ ] I5. 创建 PR 描述，按 5-section 模板

## 总计

- 任务数：~50
- 预估工时：**2.5 工作日**
- 依赖：Phase 7 MCP 完成（✅）
- 阻塞：无

## 进度追踪

- 0/50 完成 → 1/50 → ... → 50/50
- 每日更新：早晨开工前 / 晚间收工前
