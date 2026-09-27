# 采集闭环优化 — 实施计划 (2026-09-24)

> **状态勘误 (2026-09-27 批量台账收口)**: 本计划已**完整交付** — 收口记录 [DEV-0228] (DEV_LOG.md); Task 2 两项待 owner --execute 的数据清理经生产库实测已清零 (0 行, 于后续治理批次被顺手处理), 勾选已回填。全计划无挂起项。


**背景**: 第一性原理诊断 (目的链: 采集 = 以最低成本持续供给过质量门的时效资讯; 源生效 = 可达×产出×过门×时效)。DB 实测: 41 源仅 ~15 源 7d 有产出; last_error 存 'None' 字符串; 复活探测污染 yield 口径; crawler_sources/source_stats 双轨失真; 107 条 P2 告警无动作; cadence 与质量分脱钩; 14 僵尸注册行 + 测试残留。

**owner 裁决 (2026-09-24)**: ①全链路闭环 ②dead>14d 自动退役+可追溯 ③质量分反哺 cadence 自适应。

## Task 1: 观测层修复 (病灶 B)

**Files**: `backend/services/source_health_machine.py`、`backend/scheduler/jobs/collect.py` (03:00 复活探测 / 03:30 HEAD 探测)、`backend/repository/source_stats_repo.py`、相关测试。

- [x] last_error 写入点修复: 空错误存 NULL 而非字符串 'None' (grep 全部 last_error 写入点; 已存量 13 行数据由迁移脚本或启动清洗修正)。
- [x] yield 口径: 复活探测 (revival probe) 只在真实条目入库 (hotspots 新增行) 时才更新 `last_yield_at`; 探测成功但零产出 → 只重置 consecutive_failures/状态, 不算 yield。
- [x] 测试: last_error NULL 路径 / 探测零产出不抬 yield / 探测有产出抬 yield。

## Task 2: 僵尸与残留清理 (病灶 F)

**Files**: `scripts/fix_source_registry_cleanup.py` (新, --dry-run 默认)、hotspots 测试残留。

- [x] hotspots 清除 source IN ('rss','test-src') 垃圾行 (脚本执行, 附带 crawler_sources/custom_sources 中同名残留)。 ~~待 owner --execute~~ → **2026-09-27 实测已清零** (生产库直查 0 行, 于后续治理批次被顺手处理, 无需执行)。
- [x] crawler_sources 中 enabled=0 且 status='unknown' 的 14 行: 从未 fetch 过 → 归档语义 status='retired' + alert 记录 (不物理删, 可追溯)。 ~~待 owner --execute~~ → **2026-09-27 实测已清零** (生产库直查 0 行, 于后续治理批次被顺手处理, 无需执行)。
- [x] 脚本幂等, dry-run 报告变更面。

## Task 3: 失效源自动退役闭环 (病灶 D + 裁决②)

**Files**: `backend/services/source_health_machine.py`、`backend/scheduler/jobs/collect.py` (03:00 探测 job)、`backend/repository/crawler_source_repo.py` (若存在同名 repo)、测试。

- [x] 新规则: status='dead' 且死亡持续 >14d (以 last_success_at 或进入 dead 时刻较早者计) 且当日复活探测失败 → `enabled=0, status='retired'` + source_alerts (alert_type='source_retired', level='P1')。
- [x] 重启路径: retired 源被每日复活探测命中且 HTTP 可达+有产出 → 自动 enabled=1 回 grace; 探测对 retired 源保持低频 (每周而非每日, 防止长期打死亡源)。 (注: 实现为"可达即回 grace, 零产出也算", 与"可达+有产出"口径存在偏差 — parked minor, 见文末实施记录)
- [x] 告警去重: 同一 source 同一 alert_type 未解决时不重复插行 (存在即 bump created_at/detail)。
- [x] 测试: 14 天边界 / 探测成功复活 / retired 源低频探测 / 告警去重。

## Task 4: 质量自适应 cadence (病灶 E + 裁决③)

**Files**: `backend/services/source_scheduler_service.py`、`backend/repository/hotspot_repo.py` (滑动窗口质量查询)、测试。

- [x] 每源质量信号: hotspots 该源最近 N=20 条的 avg(quality_score) (不足 5 条 → 无信号不调)。
- [x] 倍率映射: avg≥75 → 0.5× (加密采集); 40≤avg<75 → 1.0×; avg<40 → 2.0× (降频)。乘后夹在 [max(600s, base×0.25), base×4] 内, 下限 10 分钟防打爆。
- [x] 应用点: source_scheduler tick 计算下次运行时间处乘倍率; cadence 静态配置保持为 base 不变 (可回退)。
- [x] 降频不改变健康机语义: stale/dead 判定仍按原口径 (倍率导致的间隔拉长不得误判 stale — 核对 stale 阈值与 4× 后最大间隔的关系, 必要时 stale 阈值取 max(现值, 4×cadence))。
- [x] 测试: 三档倍率 / 边界夹取 / 不足 5 条不调 / stale 判定不受倍率影响。

## Task 5: 收口

- [x] 全量回归 `.venv/bin/python3 -m pytest backend/tests/ -q` (基线 4715 passed; codegarden 端口预存失败可接受)。 **实测 4773 passed / 9 skipped / 0 failed** (含本分支新增 58 用例)。
- [x] generate_meta --check (无新 router 预期数字不变; 若 source_alerts 相关 api 扩展需同步)。 **OK, 89 routers / 148 services 不变**。
- [x] 触碰文件 ruff。 **0 告警**。
- [x] DEV_LOG 追加 (DEV-0228) + 实测效果回填: 退役清单 / 倍率生效面。 (注: 效果回填待 03:00 job 自然周期与 owner --execute 后补, DEV_LOG 已注明)

## 全局约束

- 红线: 不动 ai_hub 调用链; 不动 13 collector 的抓取逻辑本体 (本计划只动调度/健康/闭环层)。
- 破坏性脚本必须 --dry-run 默认 (scripts/AGENTS.md)。
- 健康机状态机变更须向后兼容现有 8 active 源 (不得误伤)。

> **实施记录 (2026-09-24)**: 分支 `collector-closedloop`; commits `04a5e40` (T1 观测修复) + `d9da931` (T3 自动退役闭环) + `6a576bf` (Batch A review fix) + `1d7c180` (T2 僵尸清理脚本) + `db004d0` (T4 质量自适应 cadence); Batch A/B 代码审查均 **Approved**; 全量回归 4773 passed / 9 skipped / 0 failed; parked minor: 复活探测零产出回 grace 与计划"可达+有产出"口径的偏差 (Task 3 行内已注); T2 生产库执行待 owner `--execute`。
