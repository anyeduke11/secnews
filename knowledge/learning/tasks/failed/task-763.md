---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.189272+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.808893+00:00"
params:
  item_ids: ['60a9342e850d', '4bcb28d78969', '909b7be7673f', '73b9a5c63b9d', '0898d672bf56', '9762ef330432', '689189c10948', 'a4e80889c971', 'e6c19db03260', '399536c9e809']
---

# 编译任务

请对以下知识条目执行编译：

- [[60a9342e850d]]
- [[4bcb28d78969]]
- [[909b7be7673f]]
- [[73b9a5c63b9d]]
- [[0898d672bf56]]
- [[9762ef330432]]
- [[689189c10948]]
- [[a4e80889c971]]
- [[e6c19db03260]]
- [[399536c9e809]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
