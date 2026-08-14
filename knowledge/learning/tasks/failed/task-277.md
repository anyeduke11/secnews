---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.152873+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.679287+00:00"
params:
  item_ids: ['67dd0100de53', '763b9826043e', '92265656ef4b', '61941b431335', 'd55e5a126ea4', 'cec7000409d0', '818719f9f291', '0dfb737c8967', '9c7195057456', '3d8ae8b8f365']
---

# 编译任务

请对以下知识条目执行编译：

- [[67dd0100de53]]
- [[763b9826043e]]
- [[92265656ef4b]]
- [[61941b431335]]
- [[d55e5a126ea4]]
- [[cec7000409d0]]
- [[818719f9f291]]
- [[0dfb737c8967]]
- [[9c7195057456]]
- [[3d8ae8b8f365]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
