---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.098711+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.876209+00:00"
params:
  item_ids: ['e779fc1c4fd8', '882b780cd7d5', '19822f51a9d5', '793f7c34a7f5', 'b81beaad203f', '6acb6e037473', '2b1a4d69f3dc', 'bf494ca6ead7', '7fe199e97790', 'fdbf5986ac57']
---

# 编译任务

请对以下知识条目执行编译：

- [[e779fc1c4fd8]]
- [[882b780cd7d5]]
- [[19822f51a9d5]]
- [[793f7c34a7f5]]
- [[b81beaad203f]]
- [[6acb6e037473]]
- [[2b1a4d69f3dc]]
- [[bf494ca6ead7]]
- [[7fe199e97790]]
- [[fdbf5986ac57]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
