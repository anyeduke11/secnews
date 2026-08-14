---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.138942+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.734030+00:00"
params:
  item_ids: ['0cca542afe2a', 'd6d4b7700280', '31bc13cc9241', '532a43898b2a', '917d7cf36902', '8b97b1951e64', 'c53b5df2c89a', '2fb27a055a48', 'c51b1b68dddc', '1114cc1bb5cb']
---

# 编译任务

请对以下知识条目执行编译：

- [[0cca542afe2a]]
- [[d6d4b7700280]]
- [[31bc13cc9241]]
- [[532a43898b2a]]
- [[917d7cf36902]]
- [[8b97b1951e64]]
- [[c53b5df2c89a]]
- [[2fb27a055a48]]
- [[c51b1b68dddc]]
- [[1114cc1bb5cb]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
