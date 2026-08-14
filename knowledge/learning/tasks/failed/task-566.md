---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.161555+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.764192+00:00"
params:
  item_ids: ['95383eba4a7a', '3c351d939d39', 'e78965049364', '083671984c99', '33775093e1aa', '7eaa24caf5e8', 'e46095a62dd6', 'c3a4e1742471', 'b6adc2a78699', '64e2d9d1a65c']
---

# 编译任务

请对以下知识条目执行编译：

- [[95383eba4a7a]]
- [[3c351d939d39]]
- [[e78965049364]]
- [[083671984c99]]
- [[33775093e1aa]]
- [[7eaa24caf5e8]]
- [[e46095a62dd6]]
- [[c3a4e1742471]]
- [[b6adc2a78699]]
- [[64e2d9d1a65c]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
