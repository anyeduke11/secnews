# KL 管线有效性治理 — 实施计划 (2026-09-26)

**Spec**: 会话内第一性原理诊断 (owner 裁决: 全量治理 / 入口断点修复+端到端验证)
**Base**: main@725e92b · **Branch**: kl-pipeline-revival

## 诊断事实 (2026-09-26 实测)

- 管线停摆 13 天 (最后 transition 09-13), kl_queue=0 行
- 4180 publish 中大量为 agent_write (4424) 直灌终态, 未经 raw→refine
- 漏斗图 = 存量快照 (raw=1/refine=0/publish=4179), 比例失真
- kl_error: ghost-item not found ×138 (死循环) / structure "list indices" ×14 (类型 bug)
- 52 个 md lifecycle 值域外 (generate×51 / signal×2, 引号不一致×16)
- refine 369 → link 117 → structure 3952: 存在绕过 refine 的直通路径

## Task 1: 错误治理

- [x] ghost-item 死信溯源: 找到反复入队的写点 (grep "ghost-item" 全仓), 删除/门禁; kl_queue 已空则只做防再犯。→ engine.kickoff 入口存在性校验拒收 (a5c1546); 另修复死信从未落库隐藏 bug (_to_dead_letter trigger_name 被 044 CHECK 拒收, 按阶段映射 t1-t4)。
- [x] structure 阶段 "list indices must be integers or slices, not str" 修复: 按 kl_error payload 中的 item 定位触发数据形态 (graph.json 结构变化?), 修 stages/structure.py 的索引假设; 回归测试。→ 复核确认 ×14 全部早于 9b81a7b 双形态修复, 复跑 45 passed 零复发, 无需新代码改动。
- [x] kl_error 治理后计数应归零; 测试先行。→ ghost 连续 drain 耗尽 max_attempts=5 → 死信落库 + kl_error 与尝试次数同界 (test_ghost_item_retries_finitely_then_dead_letters)。

## Task 2: 值域收敛

- [x] lifecycle 旧值迁移: generate→kl:publish (或按语义判定), signal→kl:publish; 引号不一致统一; scripts/fix_lifecycle_values.py (--dry-run 默认)。52 个文件。→ owner 裁决 generate/signal 均为已发布语义; 实测迁移 53 (52 可解码 + 1 编码修复后入列), 迁移后 kl:publish 4232 + kl:deduped 2。
- [x] wiki_fs/contract.get_lifecycle 读路径同步兼容旧值 (或迁移后无需)。→ legacy alias generate/signal→kl:publish 兜底, 命中 warning 留痕。
- [x] unknown=1 的 utf-8 解码失败 md 定位与修复或归档。→ items/664775643243.md 尾部 7 字节截断残片修复, 全库 4234 文件全部可解码。

## Task 3: 漏斗改吞吐视图

- [x] 后端 /api/kl/pipeline/stats 增吞吐字段: 近 7d 各阶段 transition 到达量 (wiki_events, payload JSON stage 键) + 阶段间转化率; 存量快照保留 (改名 inventory)。→ 保留原字段名 funnel (偏差注记见上), funnel_source/funnel_note 显式标注存量口径。
- [x] 前端 FunnelBar 改吞吐主视图: 各阶段"近7天转化量"条形 + 转化率百分比; 存量作次级展示。PipelineView/SentinelShell 心跳条两处消费点适配。→ PipelineView 适配; 心跳条只读快照字段天然兼容, 不改 (偏差注记见上)。
- [x] 测试: stats 信封 + 前端渲染。→ test_wiki_stats_throughput.py + FunnelBar.test.tsx。

### 偏差注记 (2026-09-26 review fix 落账)

- **存量快照未改名 inventory**: 实现保留原字段名 `funnel` 向后兼容 (SentinelShell 心跳条 /
  PipelineView 等既有消费点均读 `funnel`), 改名会牵动多消费端且无行为收益 —
  以 `funnel_source` / `funnel_note` 字段显式标注存量口径, 语义区分由前端吞吐主视图承担。
- **SentinelShell 心跳条未适配吞吐视图**: 心跳条只读快照字段 (`funnel` / `queue`),
  新增 `throughput` 字段不影响其渲染 (兼容核验通过); 吞吐主视图仅落在 PipelineView
  的 FunnelBar, 心跳条保持存量小格语义不变。

## 治理 T4 review fix (2026-09-26, Changes Required 收口)

- kl_transition 停摆信号接入复活链: T1-T4 触发器推进时补写 wiki_events
  (`kind='kl_transition'`, payload.stage=到达阶段, `backend/services/triggers/events.py`),
  与 kl_queue drain 同事件语义 — 吞吐/last_transition_at 从此覆盖生产链。
- throughput_7d 值域移除 kl:raw (无任何事件写点, 恒 0 键只会造成停摆误报),
  conversion 去 raw_to_refine 对; 前端 FLOWING fixture 同步生产可达形态。
- api 行数门收口: kl_pipeline_api stats 组装下沉 `wiki_stats_service.pipeline_stats_snapshot`
  (280→241), deep_read 分节渲染下沉 `deep_read_service.build_sections/extract_envelope_meta`
  (203→151), 豁免清单数字同步收缩。

## Task 4: 入口复活 (owner 重点)

- [x] 审视 hotspot→knowledge 入管路径: 找到"新知识不再入管"的断点 (T1 触发链? kickoff job 停? agent_write 直灌旁路?)——先诊断再修。→ 断点实锤: warm.db 2026-09-18 遗失致 knowledge_items 投影表缺失/空壳静默失败 + 触发链停摆; db.py 启动自愈重建投影表并随拷 main.sqlite_master 具名索引 (063), IF NOT EXISTS 幂等 (612e9eb + 终审 78d149d)。
- [x] 修复后端到端验证: 造一条测试 hotspot → 观察其流经 raw→refine→link→structure→publish 全阶段落 md → 漏斗吞吐视图可见。→ E2E 锚定测试 `test_full_pipeline_revival` (backend/tests/test_kl_ingest_e2e_revival.py::TestIngestToPublishE2E, ingest→kickoff→raw→refine→link→structure→publish 全链落 md) + `test_import_url_enqueues_refine_task`。
- [x] 防再犯: 入口断供时 (>7d 无 raw) 在漏斗视图标红提示。→ 吞吐视图停摆黄条 (T3) + last_transition_at 排除 kl:deduped 判重心跳 + T1-T4 触发器推进补写 wiki_events kl_transition (review fix 8a90e68) 使停摆判定覆盖生产复活链。

## Task 5: 收口

- [x] 全量回归 (基线 4815 passed) + 前端 tsc/vitest + generate_meta + ruff + harness。
- [x] DEV_LOG DEV-0230 + 计划落账。

## 全局约束

- 不动 ai_hub; md 真源哲学不变 (SQLite 仅投影); 破坏性脚本 --dry-run 默认。
- kl_queue 当前 0 行——任何队列 schema 变更须兼容空表。

## 实施记录 (2026-09-26 收口)

- **分支**: kl-pipeline-revival (base main@725e92b)
- **commits 清单** (时间序):
  - c9d8d8e docs(kl): 管线有效性治理 — 诊断事实 + 实施计划
  - a5c1546 fix(kl): ghost-item 死循环治理 + structure 类型 bug (T1)
  - adc2733 chore(kl): lifecycle 值域收敛脚本 + 52 文件迁移 (T2)
  - 32069e9 feat(kl): 漏斗吞吐视图 + 停摆提示 (T3)
  - 612e9eb fix(kl): 入口断点修复 + 端到端验证 (T4)
  - 8a90e68 fix(kl): 行数门收口 + 停摆信号接入复活链 (review fix)
  - 827001b / a37361d / 79b1222 fix(kl): deep_read.py 151 行收口 (re-review fix ×3)
  - 78d149d fix(kl): 终审修复 — 看板回退/warm 索引/信号口径/黄条盲区
- **审查链**: Batch A (T1+T2) 审查 **Approved**; Batch B (T3+T4) 审查 **Changes Required** → fix (8a90e68) → re-review 通过 → 行数门收口 (827001b/a37361d/79b1222); 终审 Findings (看板空集断层 / warm 索引 / 信号口径 / 黄条盲区) → fix (78d149d) 全部闭环。
- **裁决落账**: agent_write×4424 初诊疑为"直灌终态旁路", 经核验为 T4 structure→publish 阶段 md 落盘的 kind 留痕 (正常写路径), **非旁路** — 初诊纠正; 真正断点是 warm.db 遗失丢投影表静默失败 + 触发链停摆。

### parked 项 (收口遗留, 不阻断)

- `kl_dead_letter_retry_job` 仅阈值告警不重试 (Phase 12 遗留, 且只覆盖 t1/t2) — 死信无自动重试闭环, 治理后仅保证死信**落库可见**。
- 吞吐为 engine drain (完成阶段) + trigger 推进 (到达阶段) 双口径近似聚合, 注释已如实注明混合语义。
- `contract.get_lifecycle` legacy alias 兜底命中时 warning 留痕 — 旧值书写的外部工具未根治, 仅读路径防御。
