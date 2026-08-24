# HOTSPOT_RETIREMENT.md — Python 后端退役清单

> **状态 (2026-08-25)**: ⏸️ **已冻结** — Phase 7 破坏性步骤 (D+2 停 :8000 / D+3 `git mv` 归档) 按用户裁决 **冻结不执行**; hotspot 仍活跃开发 (`docs/SECNEWS_INTEGRATION_TASKS.md` Phase 0-6)。本文档作为 Phase 7a-7d 已交付工具的参考档案保留。
> **裁决依据**: `PROGRESS.md` §2026-08-24 产品三层架构裁决 §连锁裁决
> **整合 spec**: [`docs/HOTSPOT_SECNEWS_INTEGRATION.md`](HOTSPOT_SECNEWS_INTEGRATION.md) + [`docs/SECNEWS_INTEGRATION_TASKS.md`](SECNEWS_INTEGRATION_TASKS.md)

> **Spec**: `docs/HOTSPOT_SECNEWS_INTEGRATION.md` Phase 7
> **状态**: ⏳ 文档已就绪 (Phase 7a/7b/7c/7d 已交付, D+0/D+1 gated on dsh 端验收)
> **目标**: hotspot Python 后端 (:8000) 停止运行, `backend/` 归档为 `hotspot-archived/`, 文档/AGENTS.md 同步收口

## Phase 7 交付状态 (2026-08-24 锁定)

| Phase | 内容 | commit | 状态 |
|-------|------|--------|------|
| 7a | `export_for_dsh.py` (375 行) + 8 测试 | `b1cd80de` | ✅ 已交付 |
| 7b | `HOTSPOT_RETIREMENT.md` + AGENTS/README 退役 banner | `8ec7db61` + `68234ae6` | ✅ 已交付 |
| 7c | `snapshot_for_retirement.py` (305 行) + `execute_retirement.sh` (309 行) + baseline + 13 测试 | `94d02c49` | ✅ 已交付 |
| 7d | `dump_schema.py` (443 行) + 4 文件 schema dump + 14 测试 | `40632c98` | ✅ 已交付 |
| 7e | `export_migrations_for_dsh.py` (337 行) + 67 migrations/* 导出 + 11 测试 | (本轮) | ✅ 已交付 |
| 7f | `docs/PORT_SPEC.md` (312 行) Python→TS 移植对照表 | (本轮) | ✅ 已交付 |
| 7 D+0/D+1 | dsh 端 secnews.db 行数对账 + wiki 文件数对账 + React SPA 冒烟 | (gated on dsh 仓库) | ⏳ 待 dsh 端推进 |
| 7 D+2/D+3 | hotspot 端 :8000 停 / `git mv` / git tag `v0.5.0-retired` | `execute_retirement.sh --apply` | ⏳ 待 D+0/D+1 完成后用户触发 |

## 退役时间线 (3-5 天)

| Day | 任务 | 验收命令 | Owner |
|-----|------|---------|-------|
| D+0 | dsh 端 migrate-from-hotspot.ts 跑通, secnews.db 行数 == hotspot.db 行数 | `sqlite3 secnews.db "SELECT 'hotspots',COUNT(*) UNION ALL SELECT 'favorites',COUNT(*) ..."` 与 hotspot.db 对账 | dsh 端 |
| D+0 | dsh 端 `cp -r hotspot/knowledge/items dsh/data/wiki/items` 完成 | `find dsh/data/wiki -name '*.md' | wc -l` == `find hotspot/knowledge -name '*.md' | wc -l` | dsh 端 |
| D+1 | dsh 端 React SPA `web/` 全功能冒烟 (5 视图 + API) | `cd dsh/web && npm run build && npm run preview` 手动验证 | dsh 端 |
| D+2 | hotspot 端停止 :8000 进程, 跑 export_for_dsh.py 备份 | `lsof -i :8000` 无输出; `data/export/manifest.json` 存在 | hotspot 端 (本仓库) |
| D+3 | hotspot 端 `backend/` 归档为 `hotspot-archived/` | `git mv backend hotspot-archived` | hotspot 端 |
| D+3 | hotspot 端 AGENTS.md / README.md 标注 RETIRED | grep `RETIRED` AGENTS.md | hotspot 端 |
| D+4 | 30 天观察期, 应急回滚到 hotspot-archived/ | rollback 命令备齐 | 双方 |

## hotspot 端验收命令 (行数对账)

```bash
cd /Users/duke/Documents/hotspot

# 1. 一键锁定 baseline (供 dsh 端对账)
python3 scripts/snapshot_for_retirement.py
# 期望输出:
#   hotspots 3391 / favorites 4 / todos 6 / sm2_reviews 3 / annotations 2 /
#   hotspot_tags 5356 / knowledge_concepts 98 / knowledge_graph 42
#   → total_db_rows: 8902
#   items 4149 / concepts 96 / inbox 0 / quarantine 0
#   → total_wiki_files: 4245
# 实际写入 data/retirement_baseline.json

# 1b. 等价手写版 (若 snapshot 脚本不可用)
python3 -c "
import sqlite3, json
conn = sqlite3.connect('backend/hotspot.db')
tables = ['hotspots','favorites','todos','sm2_reviews','annotations',
          'hotspot_tags','knowledge_concepts','knowledge_graph']
print(json.dumps({t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                  for t in tables}))
"
# 期望 (锁定 2026-08-24):
# {"hotspots": 3391, "favorites": 4, "todos": 6, "sm2_reviews": 3,
#  "annotations": 2, "hotspot_tags": 5356,
#  "knowledge_concepts": 98, "knowledge_graph": 42}

# 2. wiki 文件数 (与 baseline.json 一致)
find knowledge/items knowledge/concepts -name '*.md' | wc -l
# 期望: 4245 (4149 items + 96 concepts)

# 3. dsh 端 secnews.db 同样跑一遍, 必须数字完全一致
# 任何 ±1 差异都需 dsh 端补迁或 hotspot 端排除
# (snapshot 输出的 dsh_verify_hint 给出了 node:sqlite 的对账命令模板)
```

## hotspot 端一键退役脚本

上述 6 步已经打包为可一键执行的脚本 [`scripts/execute_retirement.sh`](../scripts/execute_retirement.sh)。

**设计**:
- **dry-run 默认** (`bash scripts/execute_retirement.sh`): 打印所有会做什么, 不动文件/进程/git
- **真执行** (`bash scripts/execute_retirement.sh --apply`): 跑完 6 步, 含 safety checks
- **可分步** (`--step N --apply`): 单步重跑, 排错用
- **可跳过** (`--skip-kill / --skip-export / --skip-baseline`): 灵活组合
- **错误回滚**: 失败时打印 30 天应急回滚命令

**完整流程**:

```bash
# Dry-run 先看一遍会做什么
bash scripts/execute_retirement.sh

# D+0 dsh 端对账通过后, 真执行
bash scripts/execute_retirement.sh --apply

# 排错时单独跑某步
bash scripts/execute_retirement.sh --step 3 --apply   # 只锁 baseline
```

## hotspot 端退役步骤 (D+2/D+3)

### 步骤 1: 停止 :8000 进程

```bash
# 查 PID
lsof -i :8000 | grep LISTEN

# 优雅停止 (给 uvicorn 处理 in-flight request)
kill -TERM <PID>

# 兜底: 强杀 (10s 后还没退)
kill -KILL <PID>

# 验证: 应无输出
lsof -i :8000
```

### 步骤 2: 跑 export_for_dsh.py 留底

```bash
.venv/bin/python scripts/export_for_dsh.py --out data/export
# 期望: 8 表 8902 行 + 4245 wiki 文件 + manifest.json

# 备份到外置盘 (与 hotspot-archived/ 并列)
rsync -av data/export/ /Volumes/backup/hotspot-export-$(date +%Y%m%d)/
```

### 步骤 2.5: 锁 baseline 快照 (供 dsh 端对账)

```bash
.venv/bin/python scripts/snapshot_for_retirement.py
# 期望: data/retirement_baseline.json 含 schema_version=1 + counts + dsh_verify_hint

# 任意时刻可重新验证 (退出码 0=一致, 1=漂移)
.venv/bin/python scripts/snapshot_for_retirement.py --verify
```

### 步骤 3: 归档 backend/

```bash
# git mv 保留 history (后续可追溯)
git mv backend hotspot-archived

# 顶层脚本调用同步 (run.py / check_render.py 改用 archived)
# 见 §"代码迁移清单"
```

### 步骤 4: 移除前端 SPA

```bash
# frontend/ 已被 dsh 端 web/ 取代
# 但保留作为 archive (前端代码逻辑独立, 不阻塞 hotspot-archived/)
git mv frontend hotspot-archived/frontend
```

### 步骤 5: 标注 AGENTS.md / README.md

```bash
# AGENTS.md 顶部加 RETIRED banner
sed -i '' '1i\
# 🚨 RETIRED (YYYY-MM-DD) — 本仓库已迁入 dsh-SecNews; 见 HOTSPOT_RETIREMENT.md\
# 🚨 Python 后端 (:8000) 已停, 数据已迁至 dsh/SecNews\
\
' AGENTS.md

# README.md 同上
```

### 步骤 6: git tag

```bash
git add -A
git commit -m "chore(retire): Python 后端退役, backend/ → hotspot-archived/

Phase 7b 完成: hotspot → dsh-SecNews 全栈整合闭环。

- backend/ → hotspot-archived/backend/ (git mv 保留 history)
- frontend/ → hotspot-archived/frontend/
- data/export/ 留底 (gitignored, 已同步至外置盘)
- AGENTS.md / README.md 顶部加 RETIRED banner
- 指向 dsh-SecNews 仓库 README

Refs: docs/HOTSPOT_SECNEWS_INTEGRATION.md Phase 7"

git tag -a v0.5.0-retired -m "Python 后端退役标记, 数据已迁入 dsh-SecNews"
git push origin main --follow-tags
```

## 代码迁移清单

| 路径 | 退役前 | 退役后 |
|------|--------|--------|
| `run.py` | `python run.py` → uvicorn :8000 | 改读 `archived-path`, 或直接 rm |
| `check_render.py` | 调 :8000/health | 标记 deprecated, 仅本地 dev 用 |
| `backend/main.py` | FastAPI app 入口 | 移入 `hotspot-archived/` |
| `backend/requirements.txt` | 生产依赖 | 同步进 dsh `pyproject.toml` 或独立 dev 依赖 |
| `.github/workflows/ci.yml` | backend/frontend 矩阵 | 改为只在 archived-tag 触发 (可选) |
| `core.include` / `core.exclude` | 含 `backend/**` | 删, 改 `hotspot-archived/**` |
| `scripts/generate_meta.py` | AST 反推 backend/ | 改为 archived-only, 或归档 |

## 应急回滚 (30 天观察期)

dsh 端发现 bug / 数据缺失, 需要回滚到 hotspot 时:

```bash
# 1. 拉 archived tag (或最新 commit before RETIRED)
git checkout v0.5.0-retired -- hotspot-archived

# 2. 恢复为 backend/
git mv hotspot-archived backend
git mv hotspot-archived/frontend frontend

# 3. 重启 uvicorn
cd backend && uvicorn main:app --host 127.0.0.1 --port 8000

# 4. 同步 dsh (反向导入: dsh → hotspot)
python scripts/migrate_from_dsh.py  # 需事先写好
```

> **回滚 SLA**: D+30 之内响应, 之后 hotspot-archived/ 进入冷冻归档 (磁带/OSS Cold Archive)。

## 不迁移的表 (dsh 端独立管理)

| 表 | 原因 | 退役动作 |
|----|------|---------|
| `schema_version` | dsh 自管 | 直接删 |
| `encryption_keys` | PBKDF2 重新派生 | 清除 Fernet keyfile |
| `settings` | dsh 自管 | 仅导出 quality_rules 子集 |
| `cg_*` | CodeGarden 扩展, dsh 不依赖 | 整库 dump 留底 |
| `llm_*` | LLM 凭据/缓存, 全部本地化 | 清空 llm_api_key |
| `kl_queue` / `kl_dead_letters` | 运行时状态 | 丢弃 |
| `alert_events` / `alert_rules` / `alerts` | dsh 重放或重生成 | 丢弃 |
| `quality_check_logs_archive` | 1.8M 行, 不导入 | 留底 (不迁) |
| FTS5 虚表 (`hotspots_fts*` / `wiki_items_fts*`) | dsh 自行 rebuild | 留底 (不迁) |

详见 `scripts/export_for_dsh.py::SKIP_TABLES`。

## 文档同步清单

| 文件 | 退役前 | 退役后 |
|------|--------|--------|
| `AGENTS.md` | 顶部加 RETIRED banner | 当前文档 |
| `README.md` | 顶部加 RETIRED banner, 指向 dsh 仓库 | 待写 |
| `docs/ARCHITECTURE.md` | 标注 "历史快照" | 待改 |
| `docs/CHANGELOG.md` | 新增 v0.5.0-retired 条目 | 待写 |
| `PROGRESS.md` | 新增 Phase 7b 收尾条目 | 待写 |
| `docs/HOTSPOT_RETIREMENT.md` | 本文档 | 当前 |

## 验收 checklist (D+4 前)

- [ ] dsh 端 secnews.db 行数 == hotspot.db 行数 (8 表逐表对账)
- [ ] dsh 端 wiki 文件数 == 4245
- [ ] dsh 端 React SPA 全功能冒烟通过
- [ ] hotspot 端 baseline.json 锁定 (`data/retirement_baseline.json`)
- [ ] hotspot 端 `--verify` 退出码 0 (`snapshot_for_retirement.py --verify`)
- [ ] hotspot 端 :8000 端口空闲 (`lsof -i :8000` 无输出)
- [ ] hotspot 端 `backend/` 已 git mv 为 `hotspot-archived/`
- [ ] hotspot 端 `data/export/` 留底且备份至外置盘
- [ ] hotspot 端 AGENTS.md / README.md 标注 RETIRED
- [ ] hotspot 端 git tag `v0.5.0-retired` 已推送
- [ ] 应急回滚命令备齐且在 30 天内可执行
- [ ] `bash scripts/execute_retirement.sh --help` 可执行

## 相关文档

- [`scripts/export_for_dsh.py`](../scripts/export_for_dsh.py) — hotspot.db → JSON 旁路导出器 (本仓库)
- [`scripts/snapshot_for_retirement.py`](../scripts/snapshot_for_retirement.py) — 行数基线快照, dsh 端对账用 (本仓库)
- [`scripts/dump_schema.py`](../scripts/dump_schema.py) — 80 表 DDL + 索引 + FTS5 虚表组导出, 给 dsh `packages/store/src/schema.ts` 参考 (本仓库)
- [`scripts/execute_retirement.sh`](../scripts/execute_retirement.sh) — 6 步退役一键脚本 (dry-run 默认, 本仓库)
- [`backend/tests/test_export_for_dsh.py`](../backend/tests/test_export_for_dsh.py) — 8 个 export 契约测试 (本仓库)
- [`backend/tests/test_snapshot_for_retirement.py`](../backend/tests/test_snapshot_for_retirement.py) — 13 个 baseline 契约测试 (本仓库)
- [`backend/tests/test_dump_schema.py`](../backend/tests/test_dump_schema.py) — 14 个 schema dump 契约测试 (本仓库)
- [`docs/CodeGarden_PRD_v1.7.md`](CodeGarden_PRD_v1.7.md) — hotspot v0.3-0.4 详细设计 (本仓库)
- dsh 端 `packages/store/src/migrate-from-hotspot.ts` — TS 端迁入脚本 (dsh-SecNews 仓库)
- dsh 端 `packages/store/src/schema.ts` — TS 端表结构 (dsh-SecNews 仓库, 由 dump_schema.py 提供 DDL 参考)
- dsh 端 `web/` — React SPA 取代 hotspot frontend/ (dsh-SecNews 仓库)
