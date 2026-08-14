---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.130289+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.718517+00:00"
params:
  item_ids: ['bb76664f7c58', '3298dfc38d1f', 'fe458bb5b0a7', 'be59c41db9d3', '0d179ff5cdd4', 'd951465e71db', '6112ffbb785e', '8601cfa5474e', 'a69857aa5072', 'f7111836f3e9']
---

# 编译任务

请对以下知识条目执行编译：

- [[bb76664f7c58]]
- [[3298dfc38d1f]]
- [[fe458bb5b0a7]]
- [[be59c41db9d3]]
- [[0d179ff5cdd4]]
- [[d951465e71db]]
- [[6112ffbb785e]]
- [[8601cfa5474e]]
- [[a69857aa5072]]
- [[f7111836f3e9]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
