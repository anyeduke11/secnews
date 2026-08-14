---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.186061+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.803736+00:00"
params:
  item_ids: ['ae180ecf0756', '356bb34b3b80', '617762326d13', 'db843805ec42', '114937dadfd6', 'd6ec347787f7', 'e07bf77bdc1b', '26d10b6251a2', 'f854896a929e', '0b4a13e78a16']
---

# 编译任务

请对以下知识条目执行编译：

- [[ae180ecf0756]]
- [[356bb34b3b80]]
- [[617762326d13]]
- [[db843805ec42]]
- [[114937dadfd6]]
- [[d6ec347787f7]]
- [[e07bf77bdc1b]]
- [[26d10b6251a2]]
- [[f854896a929e]]
- [[0b4a13e78a16]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
