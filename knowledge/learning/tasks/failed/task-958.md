---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.094415+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.864142+00:00"
params:
  item_ids: ['2f3aa354c033', 'f85fb2adbbd0', 'c403e4b981c7', '30cb90614493', 'c787d744bbd4', 'c931fda214ef', '41c678282db8', 'dd5d2d016805', '0139fcdd14f5', 'a5122256dcef']
---

# 编译任务

请对以下知识条目执行编译：

- [[2f3aa354c033]]
- [[f85fb2adbbd0]]
- [[c403e4b981c7]]
- [[30cb90614493]]
- [[c787d744bbd4]]
- [[c931fda214ef]]
- [[41c678282db8]]
- [[dd5d2d016805]]
- [[0139fcdd14f5]]
- [[a5122256dcef]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
