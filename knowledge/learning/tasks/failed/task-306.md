---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.158839+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.686532+00:00"
params:
  item_ids: ['62e66c77642e', 'd48aa642da11', '6fe669556052', '1de05fd4fb5f', '43c17f04733e', '5ff1d09d87ba', '6c3ae666490e', 'd44c2263afe6', 'ebf452067ffc', 'a43aeba29fcc']
---

# 编译任务

请对以下知识条目执行编译：

- [[62e66c77642e]]
- [[d48aa642da11]]
- [[6fe669556052]]
- [[1de05fd4fb5f]]
- [[43c17f04733e]]
- [[5ff1d09d87ba]]
- [[6c3ae666490e]]
- [[d44c2263afe6]]
- [[ebf452067ffc]]
- [[a43aeba29fcc]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
