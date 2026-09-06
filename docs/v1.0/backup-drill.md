# v1.0 T02 — 备份、恢复与开发副本演练报告

> **日期**: 2026-09-06 | **状态**: verified | **DEV-0138**
> **EXECUTION_GUIDE §4 T02**: 备份 manifest + 恢复报告 + 开发环境配置模板, 拟定的迁移工具必须默认 dry-run

## 1. 设计原则

| 原则 | 实现 | 验证 |
|---|---|---|
| 不清生产 backup 链 | T02 写到 `<backup_dir>/_drill/<ts>/`, 不动 `BACKUP_RETENTION=1` 链 | 08-29 全量备份仍存 |
| 不动生产 db_path / wiki_root | 恢复写到 `/tmp/hotspot-restore/<ts>/` (仓库外) | restore 目录树 |
| 默认 dry-run | 两个脚本都 `--dry-run` 默认 (execute 需显式) | dry-run 输出 0 IO |
| 不推送远程 | `HOTSPOT_REMOTE_BACKUP=""` 默认空, 演练脚本不调 `_maybe_remote_push` | 无 WebDAV 调用 |
| 不打印密钥 | 脚本无任何 print/secrets 字段, 只 sha256 摘要 | grep 0 hit |

## 2. 备份演练 (`scripts/t02_backup_drill.py`)

### 2.1 命令
```bash
# dry-run 计划
.venv/bin/python scripts/t02_backup_drill.py --dry-run

# 真演练 (写 _drill 目录)
.venv/bin/python scripts/t02_backup_drill.py --execute
```

### 2.2 实测 (2026-09-06 00:07:07)

| 资产 | 大小 | 耗时 | 吞吐 | 方法 |
|---|---:|---:|---:|---|
| HOT db | 28.1 MB | 0.045s | 629 MB/s | `Connection.backup()` (WAL 一致性快照) |
| WARM db | 818.4 MB | 0.433s | 1889 MB/s | `shutil.copy2` (同盘 CoW) |
| COLD db | 28.7 KB | 0.001s | — | `shutil.copy2` |
| Wiki | 6486 files (3.9 MB) | 1.047s | — | zip deflate (排除 .conflicts/__pycache__/.DS_Store) |
| **总演练** | 826 MB | **1.76s** | — | — |

### 2.3 integrity_check

```
integrity_check: ok
quick_check: ok
table_count: 106
view_count: (verified 1)
```

### 2.4 真实库未污染

演练后 `backend/hotspot.db` mtime = `Sep 5 19:39:58` (与 T01 锁定时一致), `agent_runs=321` 不变。

### 2.5 产物

`backend/backups/_drill/20260906_000707/`
- `hotspot.db` (28.1 MB) — sha256 `e4a3ed141f5e7517083bfb263eebeb6254953f4ab92b14df13054811bc906ad5`
- `hotspot-warm.db` (818.4 MB) — sha256 `31ac753a4bdb5939ecc4f11f70f38402bbd6eede82fff45c7097a0dd37f4be45`
- `hotspot-cold.db` (28.7 KB) — sha256 `57bff2dac5e3a8872bb04e495ab1834d5d81b358144968f5947822d65570ab1b`
- `llm-wiki-2.0.zip` (3.9 MB) — sha256 `22f214d14969bc510764982d169c5c6155a8f883e21d3ddcf8da810941f80e85`
- `manifest.json` — 含 RPO/RTO 演练值 + 源路径 + 4 sha256 + non_goals 清单

## 3. 恢复演练 (`scripts/t02_restore_drill.py`)

### 3.1 命令
```bash
.venv/bin/python scripts/t02_restore_drill.py \
    --drill-dir backend/backups/_drill/20260906_000707 \
    --execute
```

### 3.2 5 项验收 (PASS/FAIL)

| # | 验收项 | 阈值 | 2026-09-06 结果 |
|---|---|---|---|
| 1 | db integrity_check | `ok` | **ok** |
| 2 | db sha256 一致 | 与 manifest hot digest 比 | **match** |
| 3 | db 计数对照 | hotspots=7223, favorites=6, agent_runs=321 | **7223 / 6 / 321 一致** |
| 4 | favorite → hotspot 回查 | url 应能命中 hotspots 行 | 4 次随机抽 1 中 3 失 (历史 url 漂移) |
| 5 | wiki md 抽查 | 随机 1 个 md 可读 + frontmatter 完整 | **PASS** (450 字节, frontmatter 完整) |

**#4 数据观察**: favorites 表存在历史 url 漂移 (favorites.url 不在 hotspots.url) — 这是产品/数据问题, **不是恢复 bug**。脚本以 NOTE 形式记录, 不阻塞 PASS。

### 3.3 实测 RTO (3 轮稳定性)

| Run | 抽中 fav | 抽中 hotspot 回查 | RTO 演练 |
|---|---|---|---:|
| 1 | id=10 (DeepTutor) | miss (历史 url) | 0.498s |
| 2 | id=8 (alibaba/zvec) | miss (历史 url) | 0.521s |
| 3 | id=11 (AGI Hunt) | miss (历史 url) | 0.467s |
| 补充 | id=15 (FreeBuf 498793) | **hit** (id=security_FreeBuf_d237b3d976a9) | 0.511s |

**RTO 演练均值: 0.50s** (拷 db 0.005s + 解 wiki 0.4s + 5 项 verify 0.1s)。

### 3.4 真 RPO / RTO 结论

- **RPO 演练值** = 演练自身耗时, 不等于真 RPO
- **真 RPO** = 距上次 `daily_db_backup` job 的窗口 (默认 04:30, 失败兜底 24h)
- **真 RTO** = 灾难恢复演练总耗时 = 本地 ~ 2.3s, 异机 (含网络传输 + db 校验) 经验值 +10-30s
- 当前 daily_db_backup 走 backup_service.backup_incremental (BACKUP_RETENTION=1), 周日 weekly_maintenance 触发 backup_full 重置链

## 4. 开发副本 (`scripts/dev_environment.sh`)

### 4.1 设计

| 维度 | 生产 | dev | 错开方式 |
|---|---|---|---|
| 后端端口 | 8000 | **8766** | env HOTSPOT_PORT |
| 前端端口 | 8898 | **8899** | vite --port |
| 数据根 | `backend/hotspot.db` | `dev_data/db/hotspot.db` | HOTSPOT_DB_PATH 等 6 个 env |
| Wiki 根 | `llm-wiki-2.0/` | `dev_data/llm-wiki-2.0/` | HOTSPOT_WIKI_ROOT |
| 日志 | `backend/logs/` | `dev_data/logs/` | HOTSPOT_LOG_DIR |
| 备份 | `backend/backups/` | `dev_data/backups/` | HOTSPOT_BACKUP_DIR |
| 启动追抓 | catchup_on_startup=True | **0** | dev.env 关 |
| WebDAV 推送 | 默认关 | 默认关 | HOTSPOT_REMOTE_BACKUP="" |

### 4.2 命令
```bash
# 计划 (dry-run)
bash scripts/dev_environment.sh plan

# 创建数据根 + dev.env 模板 + .gitignore 增量
bash scripts/dev_environment.sh init --execute

# 启动 dev 后端 (source dev.env 后)
bash scripts/dev_environment.sh start-backend

# 查端口/进程
bash scripts/dev_environment.sh status

# 停 dev 服务
bash scripts/dev_environment.sh stop
```

### 4.3 试跑验证 (2026-09-06 00:11:30)

```text
started backend pid=78394
08:11:30 | logging initialized
08:11:30 | db connection opened
08:11:30 | migration numbering gap: files cover 1..95 but missing 066, 067, 068, 069
08:11:30 | applying migration (× N)
08:11:30 | db initialized
08:11:30 | scheduler started, 52 jobs
08:11:30 | keyring master_key verification failed, clearing stale entry (dev 正常)
08:11:30 | startup_complete
08:11:32 | /api/health → 200, version=0.8.2, status=down (hotspots=0 因新库)
08:11:32 | graceful drain done: drained=0
08:11:32 | wal_checkpoint: truncated
08:11:32 | scheduler stopped
```

| 项 | 值 |
|---|---|
| dev db 落盘 | 1.7 MB (空, migrations 1-95 应用) |
| dev log 落盘 | 100 KB (app.log) |
| 生产 db mtime | `Sep 5 19:39:58` (与 T01 锁定一致, **未变**) |
| 端口冲突 | 8766 / 8899 / 8000 / 8898 全部独立 |

### 4.4 dev 数据根清理 (T03+ 用前)

```bash
rm -rf dev_data/   # 全清 (不会进 git, 已 gitignore)
```

## 5. 剩余问题 (待 T03+ 解决)

1. **favorites 表历史 url 漂移** (4 次随机 3 次 miss) — 数据完整性问题, 需清理脚本或 ETL
2. **真 RPO/RTO 异机演练未做** — 当前只测了本机演练, 异机网络传输 + db 校验待 V1.0 末期 (T17 全量故障演练) 补
3. **WARM 818MB 演练是同盘 copy** — 真异机传输吞吐会降到 100-500 MB/s (受网络限制), 时间翻 4-20 倍
4. **dev 环境 watchdog 因空 wiki 不启动** — T03+ 写入测试数据后可激活 (设计预期)

## 6. 提交

`feat(v1.0 T02): 备份演练 + 恢复演练 + 开发副本 (DEV-0138)` — 单 commit, 显式 pathspec

变更文件:
- `scripts/t02_backup_drill.py` (新, 240 行)
- `scripts/t02_restore_drill.py` (新, 280 行)
- `scripts/dev_environment.sh` (新, 145 行)
- `docs/v1.0/backup-drill.md` (本文件)
- `docs/v1.0/task-status.md` (T02 状态更新)
- `PROGRESS.md` (T02 段)
- `DEV_LOG.md` (DEV-0138 记录)
- `.gitignore` (dev_data/ 增量)

## 7. 引用

- `backend/services/backup_service.py` — 复用的 online backup API + 增量 WAL 逻辑
- `backend/wiki_fs/root.py` — wiki 根解析 (HOTSPOT_WIKI_ROOT env 优先)
- `backend/config/__init__.py` — 6 个路径 env + port/host
- [[hotspot-v1.0-baseline-t00]] — T00 锁定基线 (WARM 818MB / 106 表 / 53 pending)
- [[hotspot-v1.0-t01-isolation]] — T01 隔离 4 层 + F13 闭合 (ac45f89)
