# v0.8.8 发布门核验（C6-2）— 逐项状态

> **日期**: 2026-11-14
> **性质**: 实现侧核验记录（实现侧不得自评 PASS；⏸ 项需 owner / 观测窗 / 人工）
> **结论**: **发布门未全勾 — `v0.8.8` tag 打点留待 owner 于遗留项闭合后授权**（本地 main 已收口于 C6-1）

## §8.3 发布门逐项核验（PRD 版本族）

| # | 发布门项 | 状态 | 证据 |
|---|---|---|---|
| 1 | M-2 路由数 ≤ 97 | ✅ | `generate_meta --check`: routers **97**（P3 退役后实测） |
| 2 | M-1/M-3~M-8 ≤ 目标 | ◐ | **M-6 复测达标**: 全量 pytest 三轮 625.2s / 618.9s（目标 ≤1,432.68s，大幅优于）；M-1 冷启动 / M-3 Feed P95 / M-5 RSS / M-7 采集 / M-8 重建 **未在本轮复测**（需活体服务/采集窗，留 owner 复测或按 P0 基线口径沿用） |
| 3 | M-9/M-10 达标 | ⏸ | R-10 埋点本版落地（C4-1），M-9 七段 p95 / M-10 开销占比需**运行观测窗**积累 `audit_log` span 数据后判定（PRD §5.2 原登记「P4 采集」） |
| 4 | 六道 CI 门全绿 | ✅(本地) | compileall / pytest 5,374·0 failed / tsc+vitest 703 / build OK / generate_meta / harness_analyze 全 exit 0；⚠️ 远端 CI 从未真跑（PROJECT.md 已知问题，沿用） |
| 5 | 消融矩阵留档 | ✅ | `docs/audit/P2_ABLATION_2026-11-11.md`（20 对象） |
| 6 | 裁决表批准且执行完毕 | ✅ | 18/18（2026-11-11），P3 六项 + R-13 410 垫片均已执行 |
| 7 | 权威 PRD + DEV_LOG + ARCHITECTURE 同步 | ✅ | PRD §6.1 已刷新（97/153/56/19）；DEV_LOG 至 DEV-0362；ARCHITECTURE.md 经 --fix 同步 |
| 8 | 回滚演练（抽 1 删除项 revert 可复原） | ✅ | 2026-11-14 抽 C5-5③（`6b8dfa3`）：`git revert --no-commit` → 文件复原 + `tsc` 干净 → `--abort` 无残留 |
| 9 | `/todos` `/garden` 重定向生效且无白屏 | ✅ | 410 垫片 `main.py:459-461`（test 锁 410+E_GONE 契约）；`/todos` `/garden` QueryRedirect→/action（C3-5/C3-6 交付 + nav4_shell 守卫） |
| 10 | 四段 data-stage 断言 + 三主题走查归档 | ◐ | data-stage ✅（stages.test.tsx）；**T8 三主题人工走查 ⏸ 待 owner**（`docs/audit/P45_ACCEPTANCE_TAIL_2026-11-14.md` §2） |
| 11 | ROUTE_REGISTRY / index.tsx 无 /todos /garden 页面声明 | ✅ | C3-6 收口（重定向除外） |
| 12 | R-17: 备份链 grep 0 + backups 消失 + ≤120MB + 容差 0 + 台账差集 0 | ✅ | 111 MB 实测（2026-11-14）；`diff_total 0`；台账 169 条差集 0；`backend/backups/` 不存在 |
| 13 | M-4 包体 ≤ 基线×0.97 | ✅ **（v0.8.9 已修）** | 原测 742,547 B（−1.8%）未达；**2026-11-17 v0.8.9 修复后 577,813 B（−23.6%）**，根因 = echarts 整包进 vendor chunk（gzip 384KB = 52%），改 tree-shaking 入口解决，未动业务能力面 → 见 `docs/audit/V089_M4_BUNDLE_FIX_2026-11-17.md` |

## tag 授权前置（owner 清单）

1. **T8 三主题人工走查**（门 10 后半）— 目视 light/dark/paper × 四菜单，记录归档
2. ~~**M-4 裁决**（门 13）~~ — **2026-11-17 已由 v0.8.9 修复（577,813 B 达标），无需裁决** → `docs/audit/V089_M4_BUNDLE_FIX_2026-11-17.md`
3. **M-9/M-10 观测窗**（门 3）— R-10 span 落库积累后判定（可发布后观测，不阻塞 tag，PRD §5.2 M-9/M-10 原即为 P4 采集口径）
4. （可选）M-1/M-3/M-5/M-7/M-8 活体复测 — 本轮以 M-6 达标 + P0 基线沿用处理

以上 1 完成即可打 `v0.8.8` tag；3/4 可发布后继续。
