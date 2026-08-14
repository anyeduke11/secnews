---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.134515+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.652052+00:00"
params:
  item_ids: ['fd2dac190df3', 'bd00fd0dd74b', '0874fa68db5b', 'b240678c02ea', 'fdb6a4609b2b', 'a7d78ec983f1', '6d5ec70fe1c8', '62af20701d36', '8d7c33d5f76d', '1f9e0c938c1e']
---

# 编译任务

请对以下知识条目执行编译：

- [[fd2dac190df3]]
- [[bd00fd0dd74b]]
- [[0874fa68db5b]]
- [[b240678c02ea]]
- [[fdb6a4609b2b]]
- [[a7d78ec983f1]]
- [[6d5ec70fe1c8]]
- [[62af20701d36]]
- [[8d7c33d5f76d]]
- [[1f9e0c938c1e]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
