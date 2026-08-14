---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.131792+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.721666+00:00"
params:
  item_ids: ['4aa1f7ddb264', 'ee2cda8a7664', 'aa78272f3be3', 'b71ead6d2e48', 'a81bb2eef5fa', '06137b2e7dab', '4e764cde3b07', '57e5db8aa06c', '3f18b02229e2', '554fea816bb5']
---

# 编译任务

请对以下知识条目执行编译：

- [[4aa1f7ddb264]]
- [[ee2cda8a7664]]
- [[aa78272f3be3]]
- [[b71ead6d2e48]]
- [[a81bb2eef5fa]]
- [[06137b2e7dab]]
- [[4e764cde3b07]]
- [[57e5db8aa06c]]
- [[3f18b02229e2]]
- [[554fea816bb5]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
