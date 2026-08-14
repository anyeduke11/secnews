---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.141020+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.663434+00:00"
params:
  item_ids: ['bbc3bd637c68', '5c1b71ad6eb9', 'e016a92ec75d', 'ff3eb444be0c', '45003b33c311', '89fdd16bec78', 'd8432b5fac4d', 'b8ebfb42ceb2', 'a34aa938975e', '6a8b51680ff4']
---

# 编译任务

请对以下知识条目执行编译：

- [[bbc3bd637c68]]
- [[5c1b71ad6eb9]]
- [[e016a92ec75d]]
- [[ff3eb444be0c]]
- [[45003b33c311]]
- [[89fdd16bec78]]
- [[d8432b5fac4d]]
- [[b8ebfb42ceb2]]
- [[a34aa938975e]]
- [[6a8b51680ff4]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
