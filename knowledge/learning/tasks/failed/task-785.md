---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.192377+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.813967+00:00"
params:
  item_ids: ['a08ccd54b509', '57d3df0e57e1', '87c9bc3f555c', '44b258197db1', 'c25cf8c13e1e', 'ffaad4116f8c', '538c8bc13b16', 'ef82bf33bf22', 'e161a6c47dd4', 'a34caae4b152']
---

# 编译任务

请对以下知识条目执行编译：

- [[a08ccd54b509]]
- [[57d3df0e57e1]]
- [[87c9bc3f555c]]
- [[44b258197db1]]
- [[c25cf8c13e1e]]
- [[ffaad4116f8c]]
- [[538c8bc13b16]]
- [[ef82bf33bf22]]
- [[e161a6c47dd4]]
- [[a34caae4b152]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
