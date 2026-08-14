---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.158210+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.758087+00:00"
params:
  item_ids: ['5fa1277e7ff9', '7642ca8e31b3', 'dfb5a5286d54', '901216a78f97', '9f248da8e24c', '90aab4d1c7db', '05a090038da4', '44772db2ae2d', 'd868d40e0db2', 'febdab5470bf']
---

# 编译任务

请对以下知识条目执行编译：

- [[5fa1277e7ff9]]
- [[7642ca8e31b3]]
- [[dfb5a5286d54]]
- [[901216a78f97]]
- [[9f248da8e24c]]
- [[90aab4d1c7db]]
- [[05a090038da4]]
- [[44772db2ae2d]]
- [[d868d40e0db2]]
- [[febdab5470bf]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
