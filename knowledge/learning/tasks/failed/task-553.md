---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.159537+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.760952+00:00"
params:
  item_ids: ['b86080893ca6', 'b77250752f5e', 'a2c4a9085958', 'b69b3c98accd', '01cb91de68a1', '832f00feea74', '86d7c23c1feb', '83b4b400c7b0', 'b620c3b4034e', 'f19875e5dc1d']
---

# 编译任务

请对以下知识条目执行编译：

- [[b86080893ca6]]
- [[b77250752f5e]]
- [[a2c4a9085958]]
- [[b69b3c98accd]]
- [[01cb91de68a1]]
- [[832f00feea74]]
- [[86d7c23c1feb]]
- [[83b4b400c7b0]]
- [[b620c3b4034e]]
- [[f19875e5dc1d]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
