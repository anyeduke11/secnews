# v0.8.9 发布门核验（C7-2 预审）— 逐项状态

> **日期**: 2026-11-17
> **性质**: 实现侧核验记录（实现侧不得自评 PASS；⏸ 项需 owner / 观测窗 / 人工）
> **结论**: **发布门未全勾 — `v0.8.9` tag 打点留待 owner**（C7-1 版本与文档已在 main 收口；本文件为 C7-2 打点前的逐项预审）

## G1~G5 目标达成情况（30 天观测窗 t0 = 2026-11-14 → 2026-12-14）

| # | 目标 | 状态 | 证据 |
|---|---|---|---|
| 1 | **G1 主干流量**：runs ≥10 / artifacts ≥5 | ◐ **观测中，未达** | 活体 `backend/hotspot.db` 实测 `v1_runs=4` / `v1_artifacts=3`（2026-11-17）；窗口仅过 3 天，计数随流量继续累计。**不宣称达标** |
| 2 | **G2 Case 关闭**：首个运营型 case 真实关闭（守卫全过，非绕过） | ✅ | 演练① 首个 closed case + 演练⑤ 运营型全链（case→judgment(published)→action→run→artifact(accepted)→close）；四守卫 N1~N4 **反向取证**各自拦截（`docs/audit/V089_PILOT_DRILL_2026-11-14.md`） |
| 3 | **G3 执行体**：direct 人工回执全链 + pi 边界内执行 ≥1 条真实 Action | ✅ | 演练① direct 全链（run `run_4QMMNC767QOXWEC4TAS3OK5CQL`）；演练② pi 边界内执行产出 artifact `MMFHXG3JS4MUVE55DDRC37AGEJ`，落盘 sha256 **==** content_hash；`v1_runs` 中 executor='pi' 3 行 |
| 4 | **G4 安全演练**：越界命令被 L4 拦截 | ✅ | 演练③ `curl` → `E_ARGV_NOT_ALLOWED` 在 **spawn 前**拦截（`agent_runs` 无 curl 行 / 无 artifact）；演练④ 越界告警 2 条（写越界 / 读凭据）+ SIGXCPU + 出网 NET-BLOCKED；熔断**未触发** |
| 5 | **G5 观测可信**：口径修复 + run 事件入 outbox → 七段 p95 与 artifact 产出率可测 | ◐ **部分** | 口径已修（分母 `outcome='done'`），活体 yield_ratio=**1.0**；`v1_outbox` `event_type='v1_run'` 12 条；**但 M-9（七段 p95）/ M-10（埋点开销）需满窗数据**（t0=2026-11-14 → 2026-12-14） |

## 发布门逐项核验

| # | 发布门项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 全量 pytest 0 failed | ✅ | `pytest backend/tests/` → **5,463 passed / 7 skipped / 0 failed**（1052.79s）；前端 tsc 0 / vitest 713 / build OK |
| 2 | ruff 全仓 0 错 | ✅ | `ruff check backend/ scripts/drill_v089_c6.py` → All checks passed |
| 3 | 架构双 check | ✅ | `generate_meta.py --check` exit 0（56 jobs / 19 collectors / 99 routers / **155 services** / 67 core_routers；AGENTS 数字 7/7 + 版本一致性 7/7）；`harness_analyze.py --check` exit 0 |
| 4 | 版本单一真源全链一致 | ✅ | `backend/version.py::APP_VERSION` = **0.8.9**；AGENTS.md 头部版本门 + CLAUDE.md + PROJECT.md + README.md 中英版本表 + `frontend/package.json` + `assets/readme/*.svg` + CHANGELOG 全部对齐 |
| 5 | 试点演练①~⑥ 留档 | ✅ | `docs/audit/V089_PILOT_DRILL_2026-11-14.md`（六段齐全，含首跑失败留痕） |
| 6 | services 域零依赖环 | ✅ | `test_service_cycle_guard.py` 7 passed（白名单仍为空集；新增定向哨兵锁 `run_ledger_service` 不得引 knowledge facade） |
| 7 | 权威 PRD + 实施计划 + DEV_LOG + PROGRESS 同步 | ✅ | 权威 PRD 追加 2026-11-17 P7 条目（含 G1~G5 分档）；实施计划 §8/§11 + §0 状态行回写；DEV_LOG DEV-0389；PROGRESS 收口段 |
| 8 | **30 天观测窗满窗判定（M-9 / M-10）** | ⏸ | t0 = 2026-11-14 → **2026-12-14** 满窗后判定，本轮不满窗 |
| 9 | **G1 计数达标**（runs ≥10 / artifacts ≥5） | ⏸ | 当前 4 / 3，随流量继续累计 |
| 10 | v0.8.8 遗留项（M-4 包体 / T8 三主题人工走查） | 🔶 **M-4 ✅ 已修** / **T8 ⏸ 仍待人工** | **M-4**: 2026-11-17 v0.8.9 修复 —— 745,356 → **577,813 B**（−23.6% vs 基线 756,187 B），根因 = echarts 整包进 vendor chunk（gzip 384KB = 52%），改 tree-shaking 入口解决，未动业务能力面 → `docs/audit/V089_M4_BUNDLE_FIX_2026-11-17.md`；**T8 三主题人工走查仍待 owner 目视** |

## tag 授权前置（owner 清单）

1. **观测窗满窗判定**（门 8）— 2026-12-14 后出 M-9 七段 p95 / M-10 埋点开销
2. **G1 计数达标**（门 9）— runs ≥10 / artifacts ≥5
3. **v0.8.8 遗留裁决**（门 10）— ~~M-4 接受现状或改口径~~ **已修**（v0.8.9 echarts tree-shaking，577,813 B 达标）；**T8 三主题人工走查归档**仍待 owner
4. **owner 授权打 tag** — `git tag -a v0.8.9 -m "..."` + 远端推送（远端推送另需明令）

以上 1/3 闭合即可打 `v0.8.9` tag；在此之前本版在 main 收口，README / CHANGELOG 如实标「tag 待 owner 打点」。
