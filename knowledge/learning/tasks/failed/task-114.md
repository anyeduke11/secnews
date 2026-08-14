---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.125541+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.636659+00:00"
params:
  item_ids: ['1a8333a519c4', 'b0aceed4458e', 'f6281a376695', 'c25008b4317b', '44cb03ed9ba2', 'a78423d62c58', '007773f27c0e', '74ae28638ec6', '5867c269b7bb', 'b6de3a2a17ea']
---

# 编译任务

请对以下知识条目执行编译：

- [[1a8333a519c4]]
- [[b0aceed4458e]]
- [[f6281a376695]]
- [[c25008b4317b]]
- [[44cb03ed9ba2]]
- [[a78423d62c58]]
- [[007773f27c0e]]
- [[74ae28638ec6]]
- [[5867c269b7bb]]
- [[b6de3a2a17ea]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
