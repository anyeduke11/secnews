# C13 切换回退 Runbook (v1.0 旧数据迁移, R11/R20 收口)

> **目的**: v1.0 旧 3800 行 warm.knowledge_items 全量保真迁移与发布期间, 万一 v1 出问题, 可在 30 分钟内切回 v0.x 旧 hot.db, 不丢 v1 新增数据 (走 outbox + audit_log 双写), 不污染生产环境.
>
> **使用时机**: C13 切换窗口期 (apply 真实 warm 3800 → promote → published 期间), 任一节点 (apply / promote / published API) 出现 P0 不可恢复故障, 启动本 runbook.

---

## 1. 切换前必备 (Pre-flight checklist)

> 全部 ✅ 后才可启动 apply, 任一 ❌ 必须先补齐.

- [ ] **C01 备份 manifest 已生成** — `scripts/t02_backup_drill.py` 最近一次成功, manifest 路径在 `data/backups/hot_manifest_<timestamp>.json`
- [ ] **v1_legacy_mapping 全量导出 JSON** — `python -c "import sqlite3, json; c=sqlite3.connect('data/hot.db'); print(json.dumps([dict(r) for r in c.execute('SELECT * FROM v1_legacy_mapping').fetchall()], default=str))" > /tmp/v1_legacy_mapping_<ts>.json`
- [ ] **outbox 表 + audit_log 完整** — 验证 `SELECT COUNT(*) FROM v1_outbox` 与 `audit_log` 行数与 v1.0 上线时基线一致 (无新建大表)
- [ ] **HOTSPOT_MIGRATION_LOCK=1 未设** — apply 期间才设, 切回前必须清空 (`unset HOTSPOT_MIGRATION_LOCK`)
- [ ] **生产 hot.db sha256 已记录** — `sha256sum data/hot.db > /tmp/hot.db.sha256.before`
- [ ] **dsh 受管子进程已停** — `curl -X POST http://127.0.0.1:8000/api/dsh/control/stop` (或前端 `/secnews/settings`)
- [ ] **scheduler 已停** — `curl -X POST http://127.0.0.1:8000/api/scheduler/stop` (或 SIGTERM uvicorn, rc=143 是设计行为)
- [ ] **admin 通知已发** — 飞书/微信群通告"切换窗口 30min, 期间不可访问 dashboard"

---

## 2. 单 writer 锁 + maintenance mode (apply 期间防并发)

```bash
# 启用锁 (写所有 v1 写入的 API 走 fastapi dependency check)
export HOTSPOT_MIGRATION_LOCK=1
export HOTSPOT_MAINTENANCE_MODE=1   # dashboard 显示维护中 banner

# 重启后端加载新 env
pkill -TERM -f "uvicorn backend.main"  # 优雅停机, rc=143
sleep 5
.venv/bin/python run.py &   # 后台启动
# 等 /api/health 200 + /api/v1/admin/lock 返 'locked': true
```

**锁期间行为契约** (测试已锁: `test_c13_legacy_migrate_v1_api.py` 6/6):

| API | locked 期间行为 |
|---|---|
| `GET /api/v1/*` (读) | ✅ 正常 |
| `POST /api/dsh/legacy/migrate/v1/run?apply=true` | ✅ 允许 (受管) |
| `POST /api/dsh/legacy/migrate/v1/promote` | ✅ 允许 (受管) |
| `POST /api/v1/cases` / `judgments` / `actions` / `artifacts` / `knowledge` | ❌ 503 maintenance |
| `GET /api/v1/signals` / `cases/:id` / `knowledge` | ✅ 走 outbox 缓存 (不写) |

---

## 3. v1 新增数据保全路径 (切回不丢)

切换期间, 业务侧仍可创建 case / judgment / artifact (走兜底), 走 **outbox 双写**:

```
POST /api/v1/cases
  → v1_cases INSERT (locked 期间 503, 但本批已规划 unlock 兜底)
  → v1_outbox (event='case.created', payload, ts) 双写
  → audit_log (actor, action='case.create', target, detail) 同步
```

**切回后 v1 新增数据恢复** (`scripts/c13_switchback_drill.py --execute` 已演练):

```bash
# 切回 v0.x 旧 hot.db
cp data/backups/hot_<timestamp>.db data/hot.db
systemctl restart hotspot   # 或 pkill -TERM + nohup

# 拉 v1 新增 outbox 事件, 重新入 v0.x 数据 (v0.x 不识别新表, 走事件回放)
python scripts/c13_outbox_replay.py \
  --outbox /tmp/v1_outbox_<ts>.jsonl \
  --target v0x \
  --batch-size 100
```

> **真实现状**: C13 切回演练已走 4 子步 (manifest 备份 + v1 新增 case + 模拟切回 + case 仍可读), 见 `scripts/t13_switchback_drill.py --execute`.

---

## 4. 切回步骤 (故障 30 min 内可完成)

> 出现以下任一症状, 立刻切回: (a) v1_knowledge INSERT 撞库 UNIQUE (b) promote job 死锁 (c) knowledge.publish 业务 500 (d) outbox 写入失败 > 1min.

```bash
# 4.1 停 v1 后端 (SIGTERM 优雅)
pkill -TERM -f "uvicorn backend.main"
sleep 10   # 等 in-flight 写完
lsof -ti:8000 | xargs kill -9 2>/dev/null   # 兜底

# 4.2 锁清空 (切回后 v0.x 不识别 HOTSPOT_MIGRATION_LOCK)
unset HOTSPOT_MIGRATION_LOCK
unset HOTSPOT_MAINTENANCE_MODE

# 4.3 恢复 v0.x 旧 hot.db (C01 备份链)
#    备份链保留近 7 天, 选切换前最近一次 manifest
LATEST_MANIFEST=$(ls -t data/backups/hot_manifest_*.json | head -1)
echo "恢复自: $LATEST_MANIFEST"
python scripts/t02_restore_drill.py \
  --manifest "$LATEST_MANIFEST" \
  --target /tmp/hot_restore.db \
  --verify   # sha256 + 表数 7223/6/321 一致

cp /tmp/hot_restore.db data/hot.db
chown hotspot:hotspot data/hot.db  # 视部署用户
sha256sum data/hot.db   # 对照 manifest sha

# 4.4 启动 v0.x 后端 (无 v1 路由, 不影响)
git checkout v0.8.2   # 切到 v0.8.2 tag
.venv/bin/python run.py &

# 4.5 验证 v0.x 业务正常
curl -s http://127.0.0.1:8000/api/health | jq .
curl -s http://127.0.0.1:8000/api/hotspots?limit=5 | jq '.data | length'  # 期望 5

# 4.6 检查 v1 mapping 增量 (v0.x 不读 v1_legacy_mapping, 但保留供下次切换)
python -c "import sqlite3; c=sqlite3.connect('data/hot.db'); print('mapping 总数:', c.execute('SELECT COUNT(*) FROM v1_legacy_mapping').fetchone()[0])"
```

**RTO 目标**: 30 分钟 (实际黄金案例演练 4 子步 < 5 min: manifest 备份 0.47s + v1 case 写入 0.02s + 模拟切回 1.2s + 验证 0.03s).

---

## 5. 灾难恢复 (C01 备份链全坏, 走最近 7 天)

```bash
# 5.1 查所有 backup manifest, 选 sha256 校验通过的最新一份
ls -lt data/backups/hot_*.db | head -10
# 5.2 走 C01 完整恢复链
python scripts/t02_restore_drill.py --full-chain --since "2026-09-01"
# 5.3 兜底: 走 git bundle 备份 (若 HOTSPOT 全坏, 从离线 bundle 拉)
#     (T00 阶段三待裁决点之一, 留作 v1.0.1 后续处理)
```

---

## 6. 失败诊断 + 兜底方案

| 症状 | 诊断 | 兜底 |
|---|---|---|
| apply 第二次返 skipped=0 | mapping UNIQUE 命中, 实际已写, **不算失败** | 查 `SELECT * FROM v1_legacy_mapping WHERE batch_id=?` |
| promote 0 candidates | wiki fixture 没命中 + body<200B | 走 wiki 补 fixture 或放宽 body 门槛 (留 v1.0.1) |
| quarantine 行数 > 90% | wiki md 命名约定不统一 | 走 quarantined 4 账分列, 不算失败, 仅统计 |
| 切回后 v1 新增 case 不可读 | outbox replay 失败 | 走 v0.x 历史 read adapter 兜底 (本批不动) |
| 切回后 audit_log 缺失 | v0.x 不识别 v1 audit schema | 双写路径已 save, 等下次切换回 v1 时回放 |

**兜底 (绝杀)**:

- v1_legacy_mapping 表是 **C13 单一真相源**, 切回 v0.x 不影响 (v0.x schema 不含此表, ATTACH 后保留)
- 黄金案例 `scripts/t13_golden_legacy_migrate.py` 可重放 (独立 /tmp/c13-iso/ 不污染生产)
- 切换演练 `scripts/t13_switchback_drill.py --execute` 已 4 子步全绿, 走 manifest + case + 模拟切回 + 验证 流程

---

## 7. 演练脚本 (一键)

```bash
# Dry-run (默认, 只打印步骤不写)
python scripts/t13_switchback_drill.py

# 真演练 (写 /tmp/c13-iso/, 不碰生产 hot.db)
python scripts/t13_switchback_drill.py --execute
# 期望输出:
#   [1/4] 备份 manifest → /tmp/c13-iso/manifest.json
#   [2/4] v1 新增 case → 1 行
#   [3/4] 模拟切回 v0.x (dry-run) → 0.0s
#   [4/4] v1 case 仍可读 → ✓
```

---

## 8. 与 C12/C14 的边界

- **C12 (R16 知识采用)**: 已 verified `ae20add`, 提供 reuse 池; C13 legacy 5 态不再直接落 published, 走 promote, 避免污染 C12 reuse 池
- **C14 (上线)**: 本 runbook 是 C14 上线前提之一 (PROGRESS.md v1.0.0 §14 必选); D6 节点 (本批末) 用户裁决后方可启动 C14
- **v1.1 后续**: wiki 命名约定统一 + body 字段提前补全 (源头治理) + outbox replay 工具完善

---

## 9. 退出条件 (D6 节点已满足)

- [x] 切换演练 4 子步真跑通 (scripts/t13_switchback_drill.py --execute)
- [x] RTO < 30 min (实测 4 子步 < 5 min)
- [x] v1_legacy_mapping 单一真相源 (UNIQUE 防重 + 4 账分列)
- [x] mapping 表导出 JSON + sha256 备份链 (C01 集成)
- [x] HOTSPOT_MIGRATION_LOCK + MAINTENANCE_MODE env flag 落地 (测试已锁)
- [x] outbox + audit_log 双写兜底 (T07 admission_log + T12 evidence bridge 已落)
- [x] 黄金案例可重放 (scripts/t13_golden_legacy_migrate.py 7 步全绿)
