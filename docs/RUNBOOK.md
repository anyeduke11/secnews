# 运维手册 (Runbook)

## 常驻运维（Phase 8 Addendum）

### 启动

```powershell
cd c:\Users\Noped\Documents\lingxi-claw\20260704-15-04-55-413\hotspot-map
.\scripts\service\start.ps1
```

启动后端 + APScheduler 采集服务，WORKERS=4，端口 8000。
- 日志：`scripts/logs/service.out.log` 和 `service.out.log.err`
- PID：`scripts/logs/service.pid`

### 状态查询

```powershell
.\scripts\service\status.ps1
```

输出：pid / uptime / status / scheduler jobs / collect_interval / db size / cache hit rate

### 优雅停止

```powershell
.\scripts\service\stop.ps1
```

10s 内退出，rc=0（Phase 8 Task 1.1 容错 stop()）。

### 故障排查

| 症状 | 排查 |
|------|------|
| 端口 8000 占用 | `netstat -ano \| findstr :8000` → 找 PID → `Stop-Process -Force` |
| 启动后 status=down | `tail scripts/logs/service.out.log` 看 traceback |
| scheduler.ok=false | 检查 `collect_interval_seconds` 环境变量 |
| DB 损坏 | `python scripts/chaostest/db_corrupt.py` 走演练 |
| /api/health 慢 | PRAGMA integrity_check 60s TTL 缓存已生效 |
| 22h 假死 (本周资讯空) | 见下面「如何手动追抓资讯」 |

### 日志路径

- 应用：`scripts/logs/service.out.log` / `.err`
- 业务：项目根 `backend/logs/hotspot.log`
- 压测：`scripts/logs/perf_*.log`
- 故障演练：`scripts/logs/chaos_*.log` / `chaos_*_backend_*.log`

### 验证服务常驻

跑 30 分钟，监控：
- `status.ps1` 每 5min 跑一次
- `cache.hit_rate.list > 0.5` 表示 list cache 在工作
- `scheduler.jobs` 包含 collect_all + trend_rebuild + url_content_check + source_reputation_rebuild + export_rebuild

---

## 如何手动追抓资讯（Phase 8 新增）

`collection_service.py` 的 `asyncio.Lock` 跨进程不释放的根因**未修**（独立 PR），
但 Phase 8 加了「被动保护 + 主动补救」双保险：

### A. 被动保护：watchdog

每 60s 跑一次 `catchup_watchdog_job`，扫 `collection_runs` 找
`started_at < now-600s AND finished_at IS NULL` 的孤儿行：

1. 标 `status='failed', error_msg='watchdog: timeout after 600s'`
2. 防抖 5min 后自动 enqueue 一次 auto catchup
3. 写 `last_orphan_recovery_at` 时间戳到 `catchup_service` 模块级变量

健康检查暴露：

```bash
curl http://127.0.0.1:8000/api/health | jq '.components.collectors'
# 看 last_orphan_recovery_at — 最近一次 watchdog 触发时间
```

### B. 主动补救：API + UI

**API 调用**（无 UI 时直接调）：

```bash
# 1) 触发 24h 内追抓 (max_per_source=20 避免冲源)
curl -X POST http://127.0.0.1:8000/api/catchup/run \
  -H "Content-Type: application/json" \
  -d '{"since":"'$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)'","max_per_source":20}'
# → 202 {"run_id": N, "status": "running", "mode": "manual"}

# 2) 看进度
curl http://127.0.0.1:8000/api/catchup/status?limit=5
# → { current_running: {...}, recent: [...], last_orphan_recovery_at: "..." }

# 3) 中止 (如果跑太久)
curl -X POST http://127.0.0.1:8000/api/catchup/abort \
  -H "Content-Type: application/json" -d '{}'
# → 200 {"ok": true, "aborted_run_id": N}
```

**UI 操作**（推荐）：

1. 打开首页 → Header 右侧 🔄 「追抓资讯」按钮
2. 点击 → 默认追 24h 内全分类 (max_per_source=20)
3. running 时按钮变「追抓中…」，旁边出现 ⏹ 中止按钮 + 实时进度 `run #N: 5/12 源, 28 条`
4. 终态后 toast 提示成功/部分/失败
5. 已有 manual 在跑时点击会弹 toast「已有 manual 追抓在跑」

### C. 紧急止血：冷启动

如果 22h+ 假死、watchdog 也没救回来：

```bash
# 1) 找后端 PID
ps aux | grep "uvicorn\|python run.py" | grep -v grep

# 2) 杀进程
kill <pid>

# 3) 重启 (冷启动重置 asyncio.Lock 残影)
python run.py

# 4) 冷启动后会立即跑一次 collect_all (collect_all_job 启动触发),
#    并在 1 分钟内被 watchdog 检测 → 自动 enqueue auto catchup
```

### D. 死源复活

每天 03:00 (Asia/Shanghai) `source_revival_check_job` 跑一次，
对 `status='dead' AND last_checked_at < now-7d` 的源做 HEAD 探测：

- 2xx/3xx → 复活 (`status='active', zero_yield_runs=0`)
- 4xx/5xx/timeout → 保持 dead, 更新 `last_checked_at`

复活后**不主动**跑全量 collect — 下一个 `collect_all_job` (每 5min) 会自然带它。

### E. 追抓跳过的源

`source_stats.status='dead' AND last_checked_at < now-24h` 的源视为已知死,
不进入追抓配额。如果发现"追抓跑了 0 条"：

```bash
sqlite3 backend/data/hotspot.db \
  "SELECT category, source_name, status, last_checked_at, last_error
   FROM source_stats WHERE status='dead' ORDER BY last_checked_at DESC LIMIT 20;"
```

修复路径:
1. 配代理: `backend/proxy_config.json` 加 `http://127.0.0.1:7897`
2. 等次日 03:00 复活 job
3. 手动复跑: `python -c "from backend.services.source_revival_service import revive_all_dead; print(revive_all_dead())"`

