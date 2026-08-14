---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.132675+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.648864+00:00"
params:
  item_ids: ['7e29a474af87', 'cb2b1b3e8db5', '5d78fa95c98c', 'a18524397783', '0e9cdf515260', '9dac8f4b68a5', '34bf6e5c9328', '4dcf316b68ab', '89e9a9d2a102', 'ef138c822536']
---

# 编译任务

请对以下知识条目执行编译：

- [[7e29a474af87]]
- [[cb2b1b3e8db5]]
- [[5d78fa95c98c]]
- [[a18524397783]]
- [[0e9cdf515260]]
- [[9dac8f4b68a5]]
- [[34bf6e5c9328]]
- [[4dcf316b68ab]]
- [[89e9a9d2a102]]
- [[ef138c822536]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
