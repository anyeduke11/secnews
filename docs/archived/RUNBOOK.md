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
