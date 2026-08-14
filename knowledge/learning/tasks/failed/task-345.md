---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.176406+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.696258+00:00"
params:
  item_ids: ['617762326d13', 'db843805ec42', '114937dadfd6', 'd6ec347787f7', 'e07bf77bdc1b', '26d10b6251a2', 'f854896a929e', '0b4a13e78a16', '1fa55eab89cb', 'daae8bc25d00']
---

# 编译任务

请对以下知识条目执行编译：

- [[617762326d13]]
- [[db843805ec42]]
- [[114937dadfd6]]
- [[d6ec347787f7]]
- [[e07bf77bdc1b]]
- [[26d10b6251a2]]
- [[f854896a929e]]
- [[0b4a13e78a16]]
- [[1fa55eab89cb]]
- [[daae8bc25d00]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
