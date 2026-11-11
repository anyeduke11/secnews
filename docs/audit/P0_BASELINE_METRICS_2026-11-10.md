# P0 基线指标表（v0.8.8 阶段 0）

> **文档类型**: 审计留痕（只读盘点 + 指标基线）
> **版本**: v0.8.8-P0
> **日期**: 2026-11-10
> **依据**: [`docs/v0.8.8/V0.8.8_REFACTOR_PRD.md`](../v0.8.8/V0.8.8_REFACTOR_PRD.md) §5.1（指标定义）/ §5.2（目标与基线）/ §5.3（采集纪律）/ §8.1（P0 阶段）
> **P0 退出条件**: 基线全部落表；无「待测」项 —— 本文用于关闭该条件

---

## 1. 采集环境与口径

| 项 | 值 |
|---|---|
| 采集树 | `/tmp/hotspot-baseline-v087`（git worktree，`git describe` = `v0.8.7-2-g8bb960b`，HEAD = `8bb960b`） |
| 工作树是否干净 | 干净（`git status` 无改动）；符合 §5.3「不得在含未提交改动的树上采」 |
| Python | 主仓 `.venv/bin/python3`（3.14.6），worktree 复用同一虚拟环境 |
| 前端依赖 | worktree `frontend/node_modules` → 主仓软链 |
| 数据 | `llm-wiki-2.0/`（4762 items md） + 三库副本（`hotspot.db` / `hotspot-warm.db` / `hotspot-cold.db`） + `backend/proxy_config.json` |
| 端口 | 基线后端 `8011`；基线前端静态服务 `8897`（主仓 8000 / 8898 未占用冲突） |
| 网络 | 本机外网不通（DNS/连接超时），故 M-3 屏蔽 `fonts.googleapis.com` / `fonts.gstatic.com`；M-7 无法活体采集（见 §4.2） |

### 1.1 基线树选择说明（**发布缺陷**）

`v0.8.7` tag 指向 `5a8057f`，但该提交的 `frontend/src/routes/lazy-imports.ts:177` 引用 `../components/knowledge/KnowledgeLibraryPage`，**该组件文件不存在**，`vite build` 直接失败：

```
Could not resolve "../components/knowledge/KnowledgeLibraryPage" from "src/routes/lazy-imports.ts"
```

该组件在 `8bb960b`（`v0.8.7-2`，即 v0.8.7 公开交付收口的第二个提交）才补齐。因此：

- **前端相关指标（M-3 / M-4）基线只能取自 `8bb960b`**；
- 后端架构数字在 `5a8057f` 与 `8bb960b` 间无差异（jobs 59 / collectors 19 / routers 101 / services 161 / core 69），故 M-1 / M-2 / M-5 / M-6 / M-7 / M-8 口径不受影响。

> **结论**：`v0.8.7` tag 不可构建前端，属已发布版本的已知缺陷；本文件记录在案，不在 P0（只读）范围内修复。

---

## 2. 基线指标主表

| 编号 | 指标 | **基线值** | 样本 / 口径 | 采集方式 |
|---|---|---|---|---|
| M-1 | 后端冷启动耗时 | **5,706 ms** | 3 次：6,420 / 3,633 / **5,706**（中位数） | `python run.py` → 轮询 `GET /api/health` 首次 200 |
| M-2 | 路由注册数 | **101** | `count_routers()` AST 反推（当前树 100，差异见注 ①） | `scripts/generate_meta.py` |
| M-3 | Feed 首屏 P95 | **215.5 ms** | 10 次，1440×900；中位 159.45 ms（P95 = 第 9/10 位） | Playwright + Performance API；首个数据块插入时刻 |
| M-4 | 前端生产包体积 | **756,187 B**（738.5 KiB） | 77 个产物（`.js/.css/.html`）gzip 后总和；raw 2,432,420 B | `vite build` 后对 `dist/` 逐文件 gzip 统计 |
| M-5 | 后端常驻 RSS | **15,280 KB**（14.9 MiB） | 空载 5 分钟后连续 10 次采样（间隔 2 s）中位数 | `lsof -nP -iTCP:8011 -sTCP:LISTEN` 取 PID → `ps` |
| M-6 | 全量 pytest 墙钟 | **1,364.46 s**（22.7 min） | 3 次串行：1,364.46 / 1,898.41 / 979.54（中位数 = 1,364.46）；每轮 5455 passed / 9 skipped / 13 failed（见 §2.1） | `/usr/bin/time -p pytest backend/tests/ --tb=line -q -p no:randomly` |
| M-7 | 单轮采集耗时 | **33,180 ms**（近 60 次中位数） | `job_runs` 历史 n=757（全 ok）；全量均 247,085 ms / p95 688,991 ms / min 2,925 / max 814,283 | 历史账本替代活体（见 §4.2） |
| M-8 | 知识库全量重建耗时 | **3.496 s** | 活体：`full_sync_items_to_db` 4762 items 3.467 s + `full_sync_concepts_to_db` 165 concepts 0.029 s；清理 173 孤儿 item 行 / 2 孤儿 concept 行 | 直跑投影重建函数并计时 |
| M-9 | 链路单段 p95 | **—（依赖 R-10）** | 七段埋点未落地 | P4 阶段（R-10）采集 |
| M-10 | 埋点开销占比 | **—（依赖 R-10）** | 需 M-9 开关对照 | P4 阶段（R-10）采集 |

**注 ①** M-2 基线取 `8bb960b` 的 101；当前工作树为 100（DEV-0332 R-13 退役 `/api/todos` 后 −1）。§5.2 的「≤ 96」目标即相对 101 计。

**注 ②** M-9 / M-10 不属于「待测」：其采集前置（R-10 埋点）在 PRD §8.1 中排期为 **P4**，P0 阶段物理不可测。§5.2 中此两行的「基线」列以「—（P4 采集）」登记，判定条件不变。

### 2.1 M-6 明细

三次串行执行（`-p no:randomly` 关闭随机序，避免顺序抖动影响墙钟），墙钟与用例数落盘于 `/tmp/hotspot-baseline-v087/m6_run{1,2,3}.log`：

| 轮次 | 墙钟（real） | pytest 自报 | 用例结果 |
|---|---|---|---|
| run 1 | 1,364.46 s | 1362.57 s | 5455 passed / 9 skipped / **13 failed** |
| run 2 | 1,898.41 s | 1896.54 s | 同上（失败集完全相同） |
| run 3 | 979.54 s | 977.69 s | 同上（失败集完全相同） |
| **中位数** | **1,364.46 s** | — | — |

**13 个失败用例的归因（三轮完全一致，确定性失败，非随机抖动）**

| 类别 | 数量 | 明细 | 主仓复跑结论 |
|---|---|---|---|
| A. worktree 隔离缺件 | 11 | 5 × `FileNotFoundError: '.venv/bin/python'`（`test_c03_startup_health` 2 / `test_migrate_cli` 3）；4 × `runtime/upstreams/{pi,dsh}` vendor 路径不存在（`test_c06_real_*_adapter`）；2 × `test_t17_e2e_audit_sse` 审计行数断言（依赖已迁移数据） | **全部通过**（主仓 `.venv` 与 `runtime/upstreams/` 存在） |
| B. 数据/环境依赖 | 2 | `test_kpi_api::test_triage_latency_p50`（`assert 0 == 2`）、`test_check_temp_db_sizes::test_hot_violation_when_over_limit`（`FAIL: 1 layer(s) exceed limit`） | **同样失败** → 基线环境既有问题，与本版本改动无关 |

> **口径声明（fail loud）**：§5.1 对 M-6 的定义是「全量 pytest **全绿**耗时」。worktree 基线树上无法达到「全绿」——A 类 11 项是工作树隔离缺件（`.venv` 软链与 `runtime/upstreams/` 未随 worktree 落地），B 类 2 项是主仓同样复现的数据态问题。故 M-6 的实际口径为「**同一失败集（13 项）下的墙钟中位数**」；P6 复测必须使用相同失败集口径，或在主仓（含 `.venv` 与 `runtime/`）重测后同步下修本基线。
>
> **变异度**：三轮 979.54 ~ 1,898.41 s（1.94×），差异来自本机负载与用例内网络超时等待，**不来自用例数**（三轮 5455 passed 恒定）。因此 M-6 只可用于「中位数 ±5% 级的粗粒度不劣化门」，不可用于精细性能比较。

---

## 3. §5.2 目标换算（基线 → 绝对门限）

由 §5.2 的相对目标换算，P6 验收时的绝对门限：

| 编号 | 基线 | 目标公式 | **绝对门限** |
|---|---|---|---|
| M-1 | 5,706 ms | ≤ 基线 × 0.95 | **≤ 5,421 ms** |
| M-2 | 101 | ≤ 96 | **≤ 96**（R-05 全下线则 ≤ 93） |
| M-3 | 215.5 ms | ≤ 基线 × 0.90 | **≤ 194 ms** |
| M-4 | 756,187 B | ≤ 基线 × 0.97 | **≤ 733,501 B** |
| M-5 | 15,280 KB | ≤ 基线 × 0.95 | **≤ 14,516 KB** |
| M-6 | 1,364.46 s | ≤ 基线 × 1.05 | **≤ 1,432.68 s**（23.9 min） |
| M-7 | 33,180 ms | ≤ 基线 × 0.95 | **≤ 31,521 ms** |
| M-8 | 3.496 s | ≤ 基线 × 0.90 | **≤ 3.15 s** |
| M-9 | — | 七段全部可测 | 覆盖硬指标（P4 采集） |
| M-10 | — | ≤ 2% | **≤ 2%**（P4 采集） |

---

## 4. P0 盘点交付物（R-06 ~ R-09）

| 需求 | 交付文档 | 规模 | 关键结论 |
|---|---|---|---|
| R-06 服务层孤儿 | [P0_R06_SERVICE_ORPHANS_2026-11-10.md](P0_R06_SERVICE_ORPHANS_2026-11-10.md) | 161 行主表 | 孤儿 **1**（`crawler_seed.py`，0.6% ≤ 3% 阈值）/ 单消费者 22 / 多消费者 101 / UNKNOWN 37（反射路径）；另有 3 个「仅测试消费」实质等价孤儿 |
| R-07 调度层盘点 | [P0_R07_JOB_INVENTORY_2026-11-10.md](P0_R07_JOB_INVENTORY_2026-11-10.md) | 59 行主表 | 无 gate 归属的 job 数为 0；判「闭环非必需」3 个（`source_revival_check` / `collect_validations_cleanup` / `source_probe`），其中 `source_probe` 与 `source_revival_check` 功能重叠 |
| R-08 采集层盘点 | [P0_R08_COLLECTOR_INVENTORY_2026-11-10.md](P0_R08_COLLECTOR_INVENTORY_2026-11-10.md) | 19 行主表 | 30 日零产出 **4**（`hn` / `hfdailypapers` / `ossinsight` / `telegram`）；同 category 重复抓取 145 条/7 日（P1 首要候选）；`paper` 类 169 条/7 日不进首页 Feed |
| R-09 前端 ↔ API 依赖图 | [P0_R09_FRONTEND_API_MAP_2026-11-10.md](P0_R09_FRONTEND_API_MAP_2026-11-10.md) | 520 端点 | 前端有消费 **276** / 零调用 244（纯零调用 67）；前端调用点 379；router 口径实测 100 |

> R-09 即为 §8.1 P0 行的「依赖图」交付物；R-06~R-08 为「基线数据表」的盘点部分。

### 4.1 已知采集局限（fail loud）

1. **R-08 快照非冻结**：主库 `backend/hotspot.db` 由运行中的采集器持续写入（`collect_all` 1800 s + `source_scheduler_tick` 60 s），条数为 2026-11-10 14:09 UTC 单次快照；7 日总量在 1388–1395 间波动，但「谁零产出 / 谁重复 / 谁被过滤」的结论不受影响。
2. **R-09 method 靠推断**；反射式后端自调用仅做文本命中；MCP gate 默认关闭的 15 个端点静态在册但运行时 404。
3. **R-06 UNKNOWN 37** 中，14 个由 `skill_registry` 以 `ServiceTarget(module="backend.services.X")` 字符串持有（`skill_runner/dispatch.py:125` 的 `importlib.import_module`）；裁决前须查 `user_skills` 表现存行，不可据 import 图判死。

### 4.2 M-7 口径替代说明

本机外网不通，无法执行一次真实完整采集周期（活体采集会全量失败，测得的是超时时间而非采集耗时）。故改用**真实历史账本** `job_runs`：

- 口径：`collect_all` job 的 `started_at → finished_at` 差值；
- 样本：n = 757，全部 `status=ok`；最新一次 2026-11-10T08:00:01Z；
- 取值：**近 60 次中位数 33,180 ms**（全量均值 247,085 ms 受历史长尾与首轮冷缓存影响，p95 688,991 ms；min 2,925 / max 814,283）；
- 取中位数而非均值：与 §5.1「三次取中位数」的抗长尾精神一致，且近 60 次代表当前稳定态。

> **局限**：历史账本包含真实网络采集，其耗时受目标站点响应与外网质量影响，与 P6 复测环境强相关；P6 复测必须在同口径（同一 `job_runs` 查询，取近 60 次中位数）下比较，不得混用活体单次值。

---

## 5. 复现命令

```bash
# 0) 准备干净基线树
git worktree add /tmp/hotspot-baseline-v087 8bb960b
cd /tmp/hotspot-baseline-v087
ln -s /Users/duke/Documents/hotspot/frontend/node_modules frontend/node_modules
# 放入 llm-wiki-2.0/ + backend/hotspot*.db + backend/proxy_config.json

# M-1 冷启动（3 次取中位数）
python measure_coldstart.py            # 三次：6420 / 3633 / 5706 ms

# M-2 路由数
/Users/duke/Documents/hotspot/.venv/bin/python3 /Users/duke/Documents/hotspot/scripts/generate_meta.py --check

# M-3 Feed 首屏 P95（10 次）
python serve_dist.py &                  # 8897 静态服务 + /api 反代 → 8011
python measure_firstpaint.py            # P95 = 215.5 ms

# M-4 生产包体积
cd frontend && npx vite build --logLevel error
find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' \) -exec gzip -c {} \; | wc -c
# → 756187（77 文件）

# M-5 常驻 RSS（空载 5 分钟）
HOTSPOT_DISABLE_SCHEDULER=1 python run.py --port 8011 &
BASELINE_IDLE_SECONDS=300 python measure_rss.py   # → 15280 KB

# M-6 全量 pytest 墙钟（3 次取中位数）
for i in 1 2 3; do { /usr/bin/time -p /Users/duke/Documents/hotspot/.venv/bin/python3 -m pytest \
  backend/tests/ --tb=line -q -p no:randomly; } > m6_run$i.log 2>&1; done
```

---

## 6. P0 关闭结论

| 退出条件（§8.1） | 状态 |
|---|---|
| R-06 产出 161 行表 + 孤儿 ≤ 5 | ✅ 161 行 / 孤儿 1 |
| R-07 产出 59 行表 + 无 gate 归属数为 0 | ✅ 59 行 / 0 |
| R-08 产出 19 行表 + 零产出有裁决建议 | ✅ 19 行 / 4 个死源候选 + 裁决建议 |
| R-09 端点 → 前端调用点数表 | ✅ 520 端点 / 379 调用点 / 3 例误报复盘 |
| M-1 / M-3 ~ M-8 基线落表 | ✅ M-1 / M-3 / M-4 / M-5 / M-6 / M-7 / M-8 全部落表（M-6 = 1,364.46 s，含 13 项确定性失败集说明，见 §2.1） |
| 无「待测」项 | ✅ M-9 / M-10 以「—（P4 采集）」登记（前置 R-10 排期 P4），不属待测遗项 |

**P0 关闭**。遗留（移交后续阶段，不阻断 P0 退出）：

1. M-6 基线口径为「worktree 隔离环境下的同一失败集墙钟」，P6 复测须同口径；如需「主仓全绿口径」，须在主仓（含 `.venv` / `runtime/`）重测并下修本基线。
2. `v0.8.7` tag 前端不可构建（§1.1）——独立缺陷，需在后续版本修复 tag 指向或补发 `v0.8.7.1`。
3. M-7 采用 `job_runs` 历史替代活体（§4.2）——本机外网不通导致，P6 复测须同口径。