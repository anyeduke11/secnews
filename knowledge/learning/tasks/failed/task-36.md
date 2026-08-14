---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.115429+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.616377+00:00"
params:
  item_ids: ['245ab6f74012', '006d22721b0c', 'cdf8d974eeb4', 'efa267c2d986', '143ee67062d5', '11fb76e74dd3', '9af50b2cca6a', '7d8890d4e8e1', '7a5f93728e43', 'e45fd23cb7e6']
---

# 编译任务

请对以下知识条目执行编译：

- [[245ab6f74012]]
- [[006d22721b0c]]
- [[cdf8d974eeb4]]
- [[efa267c2d986]]
- [[143ee67062d5]]
- [[11fb76e74dd3]]
- [[9af50b2cca6a]]
- [[7d8890d4e8e1]]
- [[7a5f93728e43]]
- [[e45fd23cb7e6]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
