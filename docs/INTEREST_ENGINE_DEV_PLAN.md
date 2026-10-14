# Interest Engine 开发目标与执行计划（GOAL）

- 日期：2026-09-12；状态：**R1 开发中**（裁决三项已收：数据校准 / 独立 gate / 温和发现渐进收敛）
- 产品口径：[`INTEREST_ENGINE_PRD_v1.0.md`](INTEREST_ENGINE_PRD_v1.0.md)

## GOAL 声明

> Feed 的每一条资讯按"我勾选的方向 + 我真实的行为"加权排序，命中可解释、行为可纠偏；
> 无勾选且无行为时，Feed 与现状完全一致。

## R1 任务分解

### T1.1 数据层（migration 113）
`interest_signals`（item_id/domain/signal_type/weight/created_at + 两索引，无 FK）+ `interest_domain_weights`。退出判据：临时库全量应用通过、表结构测试。

### T1.2 InterestEngineService（`backend/services/interest_engine_service.py`）
- `record_signal(item_id, signal_type)`：条目查 title → 域归因 → 无域返 no_domain；同 item+type 30min 去重；写权重按 PRD §1 表。
  - **DEV-0326 修订**：无域**累计型**信号仍返 `no_domain` 丢弃；无域 **reaction**（like/dislike）放行——以哨兵域 `_unattributed` + `weight 0.0` 持久化（对外仍报 `domain: None`），哨兵域不属 10 实践域故不入权重聚合。
- `aggregate()`（5min TTL）：14d 半衰 B(d)、归一化、E 读 settings.kv、β_eff 渐进、S 与乘子 m(d) 落 `interest_domain_weights`；保证 10 域全量返回 + events_30d。
- `get_boost_map()` → `{domain: m}`；`reset()` 清信号与行为分。
- 退出判据：service 单测覆盖（归因/去重/衰减数学/β 渐进/无数据恒等/reset）。

### T1.3 API + gate（`backend/api/interest_api.py`）
3 端点；gate `interest_engine` 登记（TOML 默认 true + `_EXTENSION_NAMES` + `EXTENSION_ROUTERS` + `_registry` 条件注册 + settings features 报告 + reset 写 audit_log）。退出判据：API 测试（201/202/去重/GET 形状/reset+audit）；gate 关闭 404。

### T1.4 排序融合（hotspots 链）
gate 开 → router 取乘子表传入 service；页内 (m desc, 原序) 稳定重排，游标取重排前；缓存键含乘子指纹。gate 关 → 既有显式二值分区不动。退出判据：引擎路径排序测试 + 既有 boost 兼容测试不回归 + 无信号时与现状同序。

### T1.5 前端
`lib/interest.ts`（sendBeacon/fetch keepalive）；埋点：HotspotCard 外链 view、DeepReadChip read、StarButton favorite、深读停留 dwell；"我的方向"卡升级（权重条 + 重置 + i18n）。退出判据：lib 单测 + 卡片测试 + tsc/vitest。

### T1.5b 数字与文档同步
services 126→127 / routers 84→85 / gates 13→14 → ARCHITECTURE.md + 根 AGENTS.md + backend/api/AGENTS.md + scripts/AGENTS.md 同步；`generate_meta.py --check` 过。

## 收尾流程
全量门禁（pytest/vitest/tsc/build/meta --check/ruff）→ 独立 agent 功能验收（隔离库真实后端走查）+ code-reviewer 审计 → 修复 → DEV_LOG/PROGRESS 落账 + 显式 pathspec 提交。

## 两周后重校判据（裁决①尾巴）
真实信号 ≥100 条后：用分布重算 view/read/dwell/deep_read 权重与 C 常数（脚本化，进周审计 RUNBOOK）；词表周审计同周期执行。

## 风险
- 乘子重排改变首页观感（有兼容断言与 gate 断路器双保险）
- sendBeacon Content-Type 兼容（Blob type=application/json，FastAPI 可解析；fetch keepalive 兜底）
- signals 表膨胀（90d purge 挂 maintenance job，量级单人可忽略）
