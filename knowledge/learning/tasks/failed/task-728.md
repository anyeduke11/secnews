---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.184307+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.800329+00:00"
params:
  item_ids: ['101a06b6f130', '3b883b87cb7f', '47f8f6cdca02', 'e687dbcea55a', 'f8dee5b1ded2', 'de03c80d0090', '679f8482a8a1', '2b0016bd17b6', '9415d3f419ee', 'c1fab950d89b']
---

# 编译任务

请对以下知识条目执行编译：

- [[101a06b6f130]]
- [[3b883b87cb7f]]
- [[47f8f6cdca02]]
- [[e687dbcea55a]]
- [[f8dee5b1ded2]]
- [[de03c80d0090]]
- [[679f8482a8a1]]
- [[2b0016bd17b6]]
- [[9415d3f419ee]]
- [[c1fab950d89b]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
