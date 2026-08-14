---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.162451+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.765530+00:00"
params:
  item_ids: ['0d390c162e06', '200a45471640', '8321e0406ae9', 'caf0eaa97e70', 'd3866510d33a', '555b9abf4a8d', '98f59b916538', '4f5d0f07559b', '02ce1b4f4fac', 'bd7a3e5e18a7']
---

# 编译任务

请对以下知识条目执行编译：

- [[0d390c162e06]]
- [[200a45471640]]
- [[8321e0406ae9]]
- [[caf0eaa97e70]]
- [[d3866510d33a]]
- [[555b9abf4a8d]]
- [[98f59b916538]]
- [[4f5d0f07559b]]
- [[02ce1b4f4fac]]
- [[bd7a3e5e18a7]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
