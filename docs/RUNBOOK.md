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
ls -lh backend/hotspot.db

# 查看调度器已注册 job (P4-9: apscheduler 未持久化到 SQLite, 改查健康接口)
curl http://127.0.0.1:8000/api/health | jq '.components.scheduler'
```

## 故障排查

| 症状 | 排查 |
|------|------|
| 端口 8000 占用 | `scripts/restart_backend.sh --stop-only`（TERM 整组→有界等→逃逸 KILL, R5 SOP）；手工兜底 `lsof -i :8000` → 找 PID → `kill <pid>` |
| 端口 8898 占用 | `lsof -i :8898` → 8898 是受保护端口（CodeGarden 资源中枢），禁止释放 |
| 启动后端报错 | 检查 `.venv` 是否激活，`pip install -r backend/requirements.txt` |
| 前端启动报错 | `cd frontend && npm install` 重新安装依赖 |
| 采集无数据 | 检查 `backend/proxy_config.json` 代理配置 |
| 数据库损坏 | `sqlite3 backend/hotspot.db "PRAGMA integrity_check;"` |
| 22h 假死 (本周资讯空) | 见下面「如何手动追抓资讯」 |
| webhook 签名校验疑似未生效 | fail-open 语义（设计如此）: 已配 secret 但 vault 未解锁时与未配置不可区分, 均放行签名校验并落 warning; 仅 secret 存在且解锁时才 fail-closed 拒绝。排查: 检查 llm_secrets 中 `webhook.secret` 是否已解锁 |

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

**标准动作（DEV-0303 R5 SOP 脚本, 推荐）**：

```bash
scripts/restart_backend.sh
# TERM 整组 → 有界等端口释放 (默认 20s) → 超时逃逸 KILL → 前台启动
# 只停不起: scripts/restart_backend.sh --stop-only
# 自定义等待: HOTSPOT_STOP_WAIT=30 scripts/restart_backend.sh
```

停机现在是有界且快的（DEV-0301/0302/0303）：SSE 停机哨兵让长连接 1s 内终结、
退出尾闸保证进程必死不挂、残留进程组由启动闸自动收割（R4）。
典型停机 ~2s, 上界 ~20s（HOTSPOT_STOP_WAIT 可调）。

**手工兜底**（脚本不可用时）：

```bash
# 1) 找后端 PID
ps aux | grep "uvicorn\|python run.py" | grep -v grep

# 2) 杀进程 (优先整组, 含 uvicorn 子进程/dsh 等同组子进程)
kill <pid>          # 或: kill -TERM -- -<pgid>

# 3) 重启 (冷启动重置 asyncio.Lock 残影; 残留进程组会被启动闸自动收割)
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
sqlite3 backend/hotspot.db \
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
sqlite3 backend/hotspot.db "VACUUM;"

# 完整性检查
sqlite3 backend/hotspot.db "PRAGMA integrity_check;"

# 查看各表大小
sqlite3 backend/hotspot.db "
SELECT name, SUM(pgsize) as size_bytes
FROM dbstat GROUP BY name ORDER BY size_bytes DESC LIMIT 20;"

# 备份
cp backend/hotspot.db backend/hotspot.db.backup
```

## 实践域词表周审计 (Workbench Focus P1, DEV-0179)

每周一次（建议周一早上），对词表打标做人工抽检，防漂移:

```bash
# 1. 采样近一周资讯 40 条, 词表预打标, 生成待标注报告 (DB 只读)
python scripts/audit_practice_domain_sample.py --sample 40 --window 7d
#    → reports/practice_domain_review_<时间戳>.md

# 2. 人工把报告里 truth 列填上真值 (8 域 id 或 none)

# 3. 回读计算真实准确率 (门槛 80%)
python scripts/audit_practice_domain_sample.py --grade reports/practice_domain_review_<时间戳>.md
```

- 低于 80%: 按 PRD 修订 `TAG_PRACTICE_MAP`/`TITLE_PRACTICE_RULES` 词表，改完必须跑
  `python scripts/check_practice_domain_lexicon.py --check`（同源回归护栏，须保持 100%）。
- 同时抽查 `GET /api/observability/audit` 与 info_filter 拒绝样本（Settings → 资讯筛选门禁），
  防止关键词误杀关键信息。

## 兴趣引擎周审计 (Interest PRD R2, DEV-0184/0187)

与词表周审计同周期执行; 四步全部 DB 只读:

| 步骤 | 命令 | 判据 |
|---|---|---|
| 1. 词表回归 | `python scripts/check_practice_domain_lexicon.py --check` | 100% 过, 否则先修词表 |
| 2. 引擎健康 | `python scripts/audit_interest_hit_rate.py --json > reports/interest_audit_<日期>.json` | 人工浏览信号分布 / 漂移状态 / Feed 覆盖率 |
| 3. 重校触发判断 | 看步骤 2 输出的 W30 饱和度 | 信号 ≥100 条或上线满 14 天 → 跑步骤 4 |
| 4. 权重重校判定 | `python scripts/audit_interest_recalibration.py` | 有建议项 → owner 裁决后手改 `interest_engine_service.py` 常数并 commit |

- 漂移提示阈值 (`DRIFT_TOP_N=3` / `DRIFT_OVERLAP_MIN=2`) 与步骤 4 同窗口调整, 变更走 commit。
- 审计是"人看"的动作, 不做调度自动化; 机器只产只读报告。
- 月度附加: 跑一次无偏人评采样 (`audit_practice_domain_sample.py --sample 40`),
  准确率 <80% 时优先修词表再动引擎。

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