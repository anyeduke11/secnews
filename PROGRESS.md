# PROGRESS.md — 执行进度台账（仅活跃段）

> **当前阶段 (2026-11-14)**: **v0.8.8 质量版全阶段交付关闭**（P0~P5，约 31 commit，plan.9 终态对账完毕）——P3 零消费链路退役 + P2.5 数据热冷分层（主库 794→113MB）+ P4 七段埋点/幂等语义 + P4.5 四段指挥台与孤儿清理 + P5 版本收口 0.8.8。**留白待 owner**: `v0.8.8` tag 打点（前置 T8 三主题人工走查 + M-4 裁决，见 `docs/audit/V088_RELEASE_GATE_2026-11-14.md`）。**下一版本**: v0.8.9 立项 = 主干流量专项（pi 执行体 + Case 关闭闭环；依据 v1_runs=0 / v1_artifacts=0），PRD 见 `docs/v0.8.9/V0.8.9_PRD.md`。
> 接手顺序: 根 `AGENTS.md` → `PROJECT.md` → 本文件活跃段。历史完整段见 `docs/progress-archive/`，docs/ 全景见 `docs/README.md`。

## 历史索引

| 阶段 | 时间 | 归档文件 | 内容摘要 |
|---|---|---|---|
| **v0.5 baseline** | 2026-08-20/21 | [v0.5-baseline.md](docs/progress-archive/v0.5-baseline.md) (83 行) | 基线档案（347MB DB / 4.31M 行）+ 任务清单 |
| **v0.5 execution** | 2026-08-23/24 | [v0.5-execution.md](docs/progress-archive/v0.5-execution.md) (348 行) | M3.5 落地 + 整合 dsh 方案定稿 + 三层架构裁决 |
| **v0.6 records** | 2026-08-24/26 | [v0.6-records.md](docs/progress-archive/v0.6-records.md) (856 行) | 里程碑验收 + Phase 7 数据迁移 + P0-P3 治理全记录 |
| **v0.7 时代** | 2026-08-25 ~ 09-02 | [v0.7-records.md](docs/progress-archive/v0.7-records.md) | SettingsHub V2 + 观测批次 ①-⑨ + v0.6.3 性能/双根合并 |
| **v1.0 轨道** | 2026-09-03 ~ 09-08 | [v1.0-track-records.md](docs/progress-archive/v1.0-track-records.md) (1320 行) | T00-T19 / C01-C14 / v1.0.1 融合方案（路线已被 v0.8.5 反向收敛取代）+ REVIEW 20 项阻断 B0-B7 整改路径 |
| **v0.8.6~v0.8.7 时代** | 2026-10-04 ~ 10-12 | [v0.8.6-v0.8.7-era.md](docs/progress-archive/v0.8.6-v0.8.7-era.md) | v0.8.6 P2/P3 收口 + v0.8.7 P3 五工单 + 停机链 R1-R17 + 资讯偏好/清理告警族（DEV-0277~0325） |

> 原 v0.5 时代的「规格与文档 / 5 文件用法」小节随 v0.5 spec 一并归档（`docs/archived/2026-09-09-sweep/v0.5_refactor_plan/`），不再维护。

## 当前活跃段 (2026-09-03 起)
## 当前活跃段 (v0.8.8 时代, 2026-11-10 起)

### 2026-11-14 v0.8.8 全阶段收口 + 计划 plan.9 终态对账 — DEV-0330~0365

- **阶段账**: P0 基线 ✅（四份盘点 520 端点）→ P1 裁决 18/18 ✅ → P2 消融 20 对象 ✅ → P3 移除 ✅（零消费 router 整链下线 + 待办域 410 垫片 + 泳道退役; routers 101→97）→ P2.5 数据热冷分层 ✅（备份链退役 449MB 回收 + 沉降管道生产实跑 37,255+37,317 行 + 重建容差 0 + 日志环截 −75% + 台账两层化 + C2.6 优化批; **主库 794→113MB, R-17-A2 ≤120MB 达标**）→ P4 强化 ✅（R-10 七段埋点 stage_span→audit_log + trace 端点; R-11 envelope error_code/retryable + Case client_request_id + Artifact 幂等去重）→ P4.5 ✅（R-15 四段指挥台 + R-16 孤儿清理 4 service/20 死导出/13 组件; services 161→153 + C5-6 知识→行动转Case 接线）→ P5 ✅（版本 0.8.8 全链对齐 + 发布门 10/13 勾）。
- **计划**: `docs/v0.8.8/V0.8.8_IMPLEMENTATION_PLAN.md` plan.9 = 终态对账（17 处一致性修正），与实况零漂移。
- **收尾动作**: PROGRESS 活跃段归档 v0.8.6~v0.8.7 时代（本文件重组）。
- **门禁终态**: pytest **5,374 passed / 0 failed** · tsc 0 · vitest 703 · build OK · meta/harness 双 check exit 0 · 回滚演练过（抽 C5-5③ revert→tsc→abort）。

### 2026-11-14 P2.5 尾巴 + P3 验收复核 — DEV-0363/0364

- P2.5 最后开口 p2.5.3④ 闭合: retention.json `$warm_boundary` WARM 层边界与保留策略声明（warm.db 36 表零 v1_* 命中; 陈旧副本经恢复+持续写入回归活跃, qcl MAX(checked_at)=当日）。
- P3 验收③首次复核: 两表停写超窗（最新行 11-04/11-08 早于生效日 11-11）+ 端点行为生产活体实测（410 契约体完整 / 404×3 / 回归路由活体 / health 200）。

### v0.8.8 留白清单（owner 侧, 实现侧不得代办）

| # | 项 | 材料 |
|---|---|---|
| 1 | T8 三主题人工走查（light/dark/paper × 四菜单） | `docs/audit/P45_ACCEPTANCE_TAIL_2026-11-14.md` §2 走查入口 |
| 2 | M-4 包体裁决（742,547 B, −1.8% 未达 −3%; 接受或改口径） | 同上 §1 |
| 3 | `v0.8.8` tag 打点授权（前置 = 1+2 闭合; M-9/M-10 观测窗可发布后继续） | `docs/audit/V088_RELEASE_GATE_2026-11-14.md` owner 清单 |

### 下一版本指针

- **v0.8.9 立项（主干流量专项）**: PRD = `docs/v0.8.9/V0.8.9_PRD.md`，实施计划 = `docs/v0.8.9/V0.8.9_IMPLEMENTATION_PLAN.md`。依据: 生产实测 v1_runs=0 / v1_artifacts=0 / v1_cases=6 全 open——「资讯→知识」供给充沛（signals 7,666 / receipts 15,513）而「行动→产物→复利」零流量。
