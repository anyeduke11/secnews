---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.179600+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.702261+00:00"
params:
  item_ids: ['t5', 't1', '35f3a3bcc3b4', '3dfa47e5456f', '5d3bbedf993f', '8cac7fe16b14', '3b0bf1c387b8', '8e4b1b54a385', '21b8592147af', 'dd79e5b9aced']
---

# 编译任务

请对以下知识条目执行编译：

- [[t5]]
- [[t1]]
- [[35f3a3bcc3b4]]
- [[3dfa47e5456f]]
- [[5d3bbedf993f]]
- [[8cac7fe16b14]]
- [[3b0bf1c387b8]]
- [[8e4b1b54a385]]
- [[21b8592147af]]
- [[dd79e5b9aced]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
