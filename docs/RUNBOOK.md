# 运维手册 (Runbook)

## 启动与停止

### 后端

```bash
# 启动后端 (FastAPI + APScheduler)
python run.py
# → http://127.0.0.1:8000，自动启动采集调度器

# 指定端口
PORT=8001 python run.py
```

### 前端

```bash
cd frontend && npm run dev
# → http://localhost:8898
```

### 停止

```bash
# 找到后端 PID
lsof -i :8000 | grep LISTEN

# 停止
kill <pid>
# 或直接 Ctrl+C (前台运行)
```

### 生产构建

```bash
cd frontend && npm run build
# → tsc + vite build，输出到 dist/
```

## 状态查询

```bash
# 后端健康检查
curl http://127.0.0.1:8000/api/health | jq '.'

# 调度器状态
curl http://127.0.0.1:8000/api/health | jq '.components.scheduler'

# 采集器状态
curl http://127.0.0.1:8000/api/health | jq '.components.collectors'

# 查看数据库大小
ls -lh backend/data/hotspot.db

# 查看调度器已注册 job
sqlite3 backend/data/hotspot.db "SELECT id, name, trigger, next_run_time FROM apscheduler_jobs;"
```

## 故障排查

| 症状 | 排查 |
|------|------|
| 端口 8000 占用 | `lsof -i :8000` → 找 PID → `kill <pid>` |
| 端口 8898 占用 | `lsof -i :8898` → 8898 是受保护端口（CodeGarden 资源中枢），禁止释放 |
| 启动后端报错 | 检查 `.venv` 是否激活，`pip install -r backend/requirements.txt` |
| 前端启动报错 | `cd frontend && npm install` 重新安装依赖 |
| 采集无数据 | 检查 `backend/proxy_config.json` 代理配置 |
| 数据库损坏 | `sqlite3 backend/data/hotspot.db "PRAGMA integrity_check;"` |
| 22h 假死 (本周资讯空) | 见下面「如何手动追抓资讯」 |

### 日志路径

- 应用日志：`backend/logs/hotspot.log`
- 后端 stdout：终端输出（前端运行时不写文件）

## 如何手动追抓资讯

`collection_service.py` 的 `asyncio.Lock` 跨进程不释放的根因**未修**（独立 PR），
但加了「被动保护 + 主动补救」双保险：

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

## 数据库维护

```bash
# 手动 VACUUM
sqlite3 backend/data/hotspot.db "VACUUM;"

# 完整性检查
sqlite3 backend/data/hotspot.db "PRAGMA integrity_check;"

# 查看各表大小
sqlite3 backend/data/hotspot.db "
SELECT name, SUM(pgsize) as size_bytes
FROM dbstat GROUP BY name ORDER BY size_bytes DESC LIMIT 20;"

# 备份
cp backend/data/hotspot.db backend/data/hotspot.db.backup
```

## 测试

```bash
# 后端全部测试
.venv/bin/python3 -m pytest backend/tests/ -v

# 按类型筛选
.venv/bin/python3 -m pytest backend/tests/ -k "merge" -v
.venv/bin/python3 -m pytest backend/tests/ -m unit -v

# 前端测试
cd frontend && npx vitest run

# 前端类型检查
cd frontend && npx tsc --noEmit
```

## CI

`.github/workflows/ci.yml` — Python compile + pytest + tsc + vitest + vite build。