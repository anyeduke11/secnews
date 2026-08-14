---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.188699+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.808013+00:00"
params:
  item_ids: ['13da92a0bd1b', 'fec995b78bfe', '988628a63aec', 'agent-inv-1', 'agent-test-1', 'b63a32f1ae1c', 'k-ext-1', 'c250c0180f1e', 'de6f670d8cc2', '0fd65c2fd21a']
---

# 编译任务

请对以下知识条目执行编译：

- [[13da92a0bd1b]]
- [[fec995b78bfe]]
- [[988628a63aec]]
- [[agent-inv-1]]
- [[agent-test-1]]
- [[b63a32f1ae1c]]
- [[k-ext-1]]
- [[c250c0180f1e]]
- [[de6f670d8cc2]]
- [[0fd65c2fd21a]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
