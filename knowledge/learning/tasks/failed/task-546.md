---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.158476+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.758671+00:00"
params:
  item_ids: ['83e936a27b70', '173b8aff8bc4', 'dc51e081deb7', 'bf7c2aaedcf7', '6c2dcb836916', 'a61f0ee011b9', '5c8502bc6ce1', '606240b9de6c', '83319a3629b0', '50d76d53f3e2']
---

# 编译任务

请对以下知识条目执行编译：

- [[83e936a27b70]]
- [[173b8aff8bc4]]
- [[dc51e081deb7]]
- [[bf7c2aaedcf7]]
- [[6c2dcb836916]]
- [[a61f0ee011b9]]
- [[5c8502bc6ce1]]
- [[606240b9de6c]]
- [[83319a3629b0]]
- [[50d76d53f3e2]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
