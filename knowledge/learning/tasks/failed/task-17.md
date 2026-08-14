---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.112884+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.610957+00:00"
params:
  item_ids: ['9bba7343e977', 'bd4a5d361419', 'd6e9ba49b2e6', '0cc56c7ffe67', '2787be296429', '9de96d50fc7e', '484c3bc29cd4', '1f5c6f4ad90d', '668f84b56555', 'd2486fbbdcf1']
---

# 编译任务

请对以下知识条目执行编译：

- [[9bba7343e977]]
- [[bd4a5d361419]]
- [[d6e9ba49b2e6]]
- [[0cc56c7ffe67]]
- [[2787be296429]]
- [[9de96d50fc7e]]
- [[484c3bc29cd4]]
- [[1f5c6f4ad90d]]
- [[668f84b56555]]
- [[d2486fbbdcf1]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
