# Phase 8 变更日志 (v1.8 — 追抓资讯 News Catchup Pipeline)

> **日期**: 2026-07-25
> **范围**: 追抓资讯 (manual + auto) + 死源复活 + collection_runs 状态扩展
> **spec**: [.trae/specs/phase8-catchup/spec.md](../.trae/specs/phase8-catchup/spec.md)
> **兼容性**: 非破坏性变更 (新增表/列，旧 API 全部保留)

## 1. 新增清单

### 1.1 数据库

- **`catchup_runs` 表** (migration 040)
  - 11 字段: `id, mode, since_window, until_window, categories (JSON), max_per_source, started_at, finished_at, status, items_ingested, items_skipped, sources_attempted, sources_succeeded, error_msg, duration_ms`
  - 状态机: `running → {success, partial, failed, aborted}` (CHECK 约束)
  - 模式: `auto` (watchdog 触发) / `manual` (用户触发)
  - 索引: `(status, started_at DESC)` / `(started_at DESC)`
- **`collection_runs.status` CHECK 扩展** (migration 041)
  - 新增 `'running'` 状态允许中间态落库
  - 索引: `(status, started_at DESC)` 供 watchdog 扫描

### 1.2 API 端点 (5 个)

- `POST /api/catchup/run` — 手动触发追抓 (manual)，返回 202 + run_id
- `GET  /api/catchup/status` — 当前 in-flight + 最近 N 条 (默认 7)
- `POST /api/catchup/abort` — 中止当前 manual run (协作式)
- `POST /api/catchup/auto` — 内部 watchdog 入口 (auto mode, 不阻塞 manual)
- `GET  /api/catchup/runs/{id}` — 单条 run 详情 (调试用)
- `GET  /api/health` 扩展 — `collectors.last_orphan_recovery_at` 暴露

### 1.3 后端服务

- `backend/repository/catchup_repo.py` — CRUD + 状态机校验
- `backend/services/catchup_service.py` — 主流程
  - `enqueue_catchup(mode, since, until, categories, max_per_source)` — 接受后异步执行
  - `abort_current()` — 协作式取消
  - `_execute_catchup_run(run_id)` — 跳过 dead 源 / 复用 CollectionService / 触发 trend_rebuild
  - `_lock` 与 `collect_all` 隔离, 互不阻塞
  - `_last_auto_enqueue_at` 5min 防抖
- `backend/services/source_revival_service.py` — 死源复活
  - `list_dead_sources(dead_for_days)` — 列死 N 天以上的源
  - `try_revive_one(cat, name, url)` — 单源 HEAD 探测
  - `revive_all_dead()` — 批量复活, 返回 `RevivalResult[]`
- `backend/scheduler/jobs.py` — 新增 2 job
  - `catchup_watchdog_job` — 每 60s 扫 collection_runs 找孤儿
  - `source_revival_check_job` — 每日 03:00 复活死源

### 1.4 前端

- `frontend/src/components/CatchupButton.tsx` — Header 上的追抓按钮
  - 状态机: idle / running / done
  - 3s 轮询 `/api/catchup/status` 拿进度
  - running 时显示「中止」按钮 + 实时进度
  - 终态后 toast 提示
- 嵌入位置: `Header.tsx` 主题切换和刷新按钮之间

### 1.5 测试 (46 后端 + 8 前端)

- `backend/tests/test_catchup_repo.py` (12) — CRUD + 状态机 + duration 计算
- `backend/tests/test_catchup_service.py` (15) — 锁隔离 / 跳死源 / cap / 异常 / abort / trend_rebuild
- `backend/tests/test_catchup_watchdog.py` (12) — 孤儿检测 / 防抖 / 并发
- `backend/tests/test_catchup_api.py` (11) — POST 触发 / 状态查询 / abort / 参数校验
- `backend/tests/test_source_revival_service.py` (5) — 列死源 / 复活 / 网络错误
- `frontend/src/components/CatchupButton.test.tsx` (8) — 触发 / 进度 / abort / 409 / 终态

### 1.6 文档

- `docs/phase8_changelog.md` (本文件)
- `docs/RUNBOOK.md` — 新增「如何手动追抓资讯」段落
- `README.md` — 路线图加 v1.8 行
- `.trae/specs/phase8-catchup/spec.md` — 完整 spec
- `.trae/specs/phase8-catchup/tasks.md` — 任务清单 (A-I)
- `.trae/specs/phase8-catchup/checklist.md` — 验收清单

## 2. 设计决策 (10 条)

1. **独立 `asyncio.Lock`** — catchup 与 collect_all 互不阻塞, 可并行
2. **manual 一次只允许一个** — `_current_manual_run` 占位, 重复触发返 409
3. **auto 不阻塞 manual** — auto 优先级低, manual 在跑时 auto 让出
4. **协作式 abort** — DB 标 `aborted`, `_execute` 在下一个写库点退出
5. **跳过 dead 源** — `status='dead' AND last_checked_at < now-24h` 视为已知死, 不浪费配额
6. **`max_per_source` cap** — 默认 20 (manual) / 30 (auto), 避免冲垮源站
7. **deadline 600s 触发 watchdog** — `started_at < now-600s AND finished_at IS NULL` 视为孤儿
8. **watchdog 防抖 5min** — `_last_auto_enqueue_at` 避免反复 enqueue
9. **完成时触发 trend_rebuild** — 后台 fire-and-forget, 不阻塞 catchup 终态
10. **source_revival 每日 03:00** — 死 7d+ 的源 HEAD 探测, 不抓内容

## 3. 运维要点

### 3.1 手动追抓

```bash
# 触发 24h 内的全分类追抓
curl -X POST http://127.0.0.1:8000/api/catchup/run \
  -H "Content-Type: application/json" \
  -d '{"since":"2026-07-24T20:00:00Z","max_per_source":20}'

# 看进度
curl http://127.0.0.1:8000/api/catchup/status

# 中止
curl -X POST http://127.0.0.1:8000/api/catchup/abort \
  -H "Content-Type: application/json" -d '{}'
```

### 3.2 健康检查

```bash
curl http://127.0.0.1:8000/api/health | jq '.components.collectors'
# 关注 last_orphan_recovery_at — 反映 watchdog 近期是否触发过
```

### 3.3 故障排查

| 症状 | 排查 |
|------|------|
| 追抓一直 running 不结束 | 看 collection_runs 中最近的 started_at > 600s 行, 等 watchdog 标 failed |
| catchup 跑了 0 条 | 查 `source_stats.status='dead'` 的源 (跳过), 或 `proxy_config.json` 失效 |
| 22h 假死后第一次跑 | 杀 uvicorn 冷启动 → watchdog 自动触发 auto catchup |
| 死源始终不复活 | 查 `quality.revival_dead_for_days` 设置 (默认 7) |

## 4. 不在范围内 (Phase 9+)

- ❌ 修 `collection_service.py` 的 asyncio.Lock 根因 (独立 PR)
- ❌ 给 MCP Server 暴露追抓 tool (Phase 9 集成)
- ❌ 跨机服务网格 + 分布式追抓
- ❌ 自动恢复 22h 全部历史 (默认深度 7d, 防止源站被冲)
- ❌ 替换现有 collect_all (追抓是**额外**能力)

## 5. 验收

- ✅ 46/46 后端 Phase 8 测试 PASS (5 文件)
- ✅ 8/8 前端 CatchupButton 测试 PASS
- ✅ 0 TypeScript 编译错误
- ✅ 0 回归 (Phase 1-7 + Phase 8 全部通过)
- ✅ 调度器 2 个新 job 注册 + 启动正常
- ✅ health endpoint 暴露 `last_orphan_recovery_at`
