---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.095518+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.866719+00:00"
params:
  item_ids: ['02ce1b4f4fac', 'bd7a3e5e18a7', 'd7ec2476850a', '5eef51028bd2', '6f18dc9e465e', 'd5d0543f8164', 'bff17130fafa', '5721b0e15006', 'd3f3e9a934dd', 'd0408f219f4f']
---

# 编译任务

请对以下知识条目执行编译：

- [[02ce1b4f4fac]]
- [[bd7a3e5e18a7]]
- [[d7ec2476850a]]
- [[5eef51028bd2]]
- [[6f18dc9e465e]]
- [[d5d0543f8164]]
- [[bff17130fafa]]
- [[5721b0e15006]]
- [[d3f3e9a934dd]]
- [[d0408f219f4f]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
