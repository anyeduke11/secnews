---
task_id: 6
task_type: generate_learning_plan
status: pending
created_at: "2026-07-15T13:44:13.845877+00:00"
params:
  domains: ['security']
  week: "2026-W29"
---

# 任务：生成学习计划

请使用 knowledge-master skill 为本周（2026-W29）生成学习计划。

## 参数
- 周次: 2026-W29
- 领域: security

## 步骤
1. 扫描 knowledge/items/ 和 knowledge/concepts/ 了解当前知识状态
2. 根据 SOUL.md 和知识覆盖度，生成本周学习目标（3-5 个）
3. 选择 5-10 个知识条目作为本周学习任务
4. 写入 knowledge_plans 表（通过 API 或直接操作）
