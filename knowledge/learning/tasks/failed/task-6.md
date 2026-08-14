---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.111194+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.606927+00:00"
params:
  item_ids: ['3edb3c126755', 'aec7896e95f0', '6f9dbfa31f8c', '83169cef13cf', 'a9505c729cbf', 'a955e02c3c6f', '4dc3a769398c', '6800bdec0d46', 'cd43785a2bc9', '8eaf41bbf961']
---

# 编译任务

请对以下知识条目执行编译：

- [[3edb3c126755]]
- [[aec7896e95f0]]
- [[6f9dbfa31f8c]]
- [[83169cef13cf]]
- [[a9505c729cbf]]
- [[a955e02c3c6f]]
- [[4dc3a769398c]]
- [[6800bdec0d46]]
- [[cd43785a2bc9]]
- [[8eaf41bbf961]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
