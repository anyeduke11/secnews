---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.096472+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.870387+00:00"
params:
  item_ids: ['8e32becfeda0', '1f2698205f13', '3211d0705d29', 'ad60b4e4cb4b', '860c2707a7fa', 'e963e0e17c62', 'a77e2d1769cc', 'b1ceb98c0462', 'e91714cc5460', 'de4bc74c18df']
---

# 编译任务

请对以下知识条目执行编译：

- [[8e32becfeda0]]
- [[1f2698205f13]]
- [[3211d0705d29]]
- [[ad60b4e4cb4b]]
- [[860c2707a7fa]]
- [[e963e0e17c62]]
- [[a77e2d1769cc]]
- [[b1ceb98c0462]]
- [[e91714cc5460]]
- [[de4bc74c18df]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
