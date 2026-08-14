---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.130801+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.719600+00:00"
params:
  item_ids: ['19cd0d853af8', 'ee220aa85508', '551a671ecb6c', '8910b33ad866', '0bcc22dc8b65', '5c00668e97d9', '086be67ecd04', '2cf7745f8ed7', 'ebc9ec9f8a9e', '2d71b069b126']
---

# 编译任务

请对以下知识条目执行编译：

- [[19cd0d853af8]]
- [[ee220aa85508]]
- [[551a671ecb6c]]
- [[8910b33ad866]]
- [[0bcc22dc8b65]]
- [[5c00668e97d9]]
- [[086be67ecd04]]
- [[2cf7745f8ed7]]
- [[ebc9ec9f8a9e]]
- [[2d71b069b126]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
