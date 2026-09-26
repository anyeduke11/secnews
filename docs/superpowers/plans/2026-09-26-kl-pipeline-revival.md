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

- [ ] ghost-item 死信溯源: 找到反复入队的写点 (grep "ghost-item" 全仓), 删除/门禁; kl_queue 已空则只做防再犯。
- [ ] structure 阶段 "list indices must be integers or slices, not str" 修复: 按 kl_error payload 中的 item 定位触发数据形态 (graph.json 结构变化?), 修 stages/structure.py 的索引假设; 回归测试。
- [ ] kl_error 治理后计数应归零; 测试先行。

## Task 2: 值域收敛

- [ ] lifecycle 旧值迁移: generate→kl:publish (或按语义判定), signal→kl:publish; 引号不一致统一; scripts/fix_lifecycle_values.py (--dry-run 默认)。52 个文件。
- [ ] wiki_fs/contract.get_lifecycle 读路径同步兼容旧值 (或迁移后无需)。
- [ ] unknown=1 的 utf-8 解码失败 md 定位与修复或归档。

## Task 3: 漏斗改吞吐视图

- [ ] 后端 /api/kl/pipeline/stats 增吞吐字段: 近 7d 各阶段 transition 到达量 (wiki_events, payload JSON stage 键) + 阶段间转化率; 存量快照保留 (改名 inventory)。
- [ ] 前端 FunnelBar 改吞吐主视图: 各阶段"近7天转化量"条形 + 转化率百分比; 存量作次级展示。PipelineView/SentinelShell 心跳条两处消费点适配。
- [ ] 测试: stats 信封 + 前端渲染。

## Task 4: 入口复活 (owner 重点)

- [ ] 审视 hotspot→knowledge 入管路径: 找到"新知识不再入管"的断点 (T1 触发链? kickoff job 停? agent_write 直灌旁路?)——先诊断再修。
- [ ] 修复后端到端验证: 造一条测试 hotspot → 观察其流经 raw→refine→link→structure→publish 全阶段落 md → 漏斗吞吐视图可见。
- [ ] 防再犯: 入口断供时 (>7d 无 raw) 在漏斗视图标红提示。

## Task 5: 收口

- [ ] 全量回归 (基线 4815 passed) + 前端 tsc/vitest + generate_meta + ruff + harness。
- [ ] DEV_LOG DEV-0230 + 计划落账。

## 全局约束

- 不动 ai_hub; md 真源哲学不变 (SQLite 仅投影); 破坏性脚本 --dry-run 默认。
- kl_queue 当前 0 行——任何队列 schema 变更须兼容空表。
