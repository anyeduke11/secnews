---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.176197+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.788294+00:00"
params:
  item_ids: ['5f26f75d5582', 'fe61ab0f7f2c', 'd0aea44fd4f4', '96bdfc23a5db', 'cf6d406395ac', 'b6058eda2e08', '7bd3c0b77401', '845e8bbe575a', '72cb69889de3', 'e688afdc111d']
---

# 编译任务

请对以下知识条目执行编译：

- [[5f26f75d5582]]
- [[fe61ab0f7f2c]]
- [[d0aea44fd4f4]]
- [[96bdfc23a5db]]
- [[cf6d406395ac]]
- [[b6058eda2e08]]
- [[7bd3c0b77401]]
- [[845e8bbe575a]]
- [[72cb69889de3]]
- [[e688afdc111d]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
