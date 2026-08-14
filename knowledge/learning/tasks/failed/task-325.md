---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.164702+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.691285+00:00"
params:
  item_ids: ['38ea81fbb86e', 'e65ef104dd0c', '3b29044cd6b6', '65cc0cee7f83', 'ffddfed8e20a', '9315c9b1d9fe', '254ef865ff9d', '23b893911f93', '85d4c246236f', 'bb3af9d01100']
---

# 编译任务

请对以下知识条目执行编译：

- [[38ea81fbb86e]]
- [[e65ef104dd0c]]
- [[3b29044cd6b6]]
- [[65cc0cee7f83]]
- [[ffddfed8e20a]]
- [[9315c9b1d9fe]]
- [[254ef865ff9d]]
- [[23b893911f93]]
- [[85d4c246236f]]
- [[bb3af9d01100]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
