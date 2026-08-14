---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.188283+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.807141+00:00"
params:
  item_ids: ['16354bab5bdd', '5301b8f7a98e', 'ed4f2f7179c5', 'fc263a3ae50f', '9a45c4b4a74e', '58087eb4b4cc', '292b5172fc5a', '98bf2ad9124a', '5918a9eb7469', '78c342fb5b86']
---

# 编译任务

请对以下知识条目执行编译：

- [[16354bab5bdd]]
- [[5301b8f7a98e]]
- [[ed4f2f7179c5]]
- [[fc263a3ae50f]]
- [[9a45c4b4a74e]]
- [[58087eb4b4cc]]
- [[292b5172fc5a]]
- [[98bf2ad9124a]]
- [[5918a9eb7469]]
- [[78c342fb5b86]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
