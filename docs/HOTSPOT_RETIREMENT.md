# HOTSPOT_RETIREMENT.md — Python 后端退役清单

> **Spec**: `SecNews_dsh_全栈整合_task-d12.md` Phase 7
> **状态**: ⏳ 待执行 (Phase 7b 文档已就绪, 等 dsh 端 secnews.db 行数对账完成)
> **目标**: hotspot Python 后端 (:8000) 停止运行, `backend/` 归档为 `hotspot-archived/`, 文档/AGENTS.md 同步收口

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

# 1. 导出 hotspot.db 行数 (基准, 不可变)
python -c "
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

# 2. wiki 文件数
find knowledge/items knowledge/concepts -name '*.md' | wc -l
# 期望: 4245 (4149 items + 96 concepts)

# 3. dsh 端 secnews.db 同样跑一遍, 必须数字完全一致
# 任何 ±1 差异都需 dsh 端补迁或 hotspot 端排除
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

Refs: SecNews_dsh_全栈整合_task-d12.md Phase 7"

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
- [ ] hotspot 端 :8000 端口空闲 (`lsof -i :8000` 无输出)
- [ ] hotspot 端 `backend/` 已 git mv 为 `hotspot-archived/`
- [ ] hotspot 端 `data/export/` 留底且备份至外置盘
- [ ] hotspot 端 AGENTS.md / README.md 标注 RETIRED
- [ ] hotspot 端 git tag `v0.5.0-retired` 已推送
- [ ] 应急回滚命令备齐且在 30 天内可执行

## 相关文档

- `scripts/export_for_dsh.py` — hotspot.db → JSON 旁路导出器 (本仓库)
- `docs/CodeGarden_PRD_v1.7.md` — hotspot v0.3-0.4 详细设计 (本仓库)
- dsh 端 `packages/store/src/migrate-from-hotspot.ts` — TS 端迁入脚本 (dsh-SecNews 仓库)
- dsh 端 `web/` — React SPA 取代 hotspot frontend/ (dsh-SecNews 仓库)
