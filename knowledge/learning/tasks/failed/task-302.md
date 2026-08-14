---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.157931+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.685230+00:00"
params:
  item_ids: ['119d10406525', 'fc4a1ff59694', 'a1cf3b936810', 'e85e004a275c', 'dc28f8fc9d65', 'b58d29b4437f', '8834be75e69c', '5b0ce0d9e7c2', 'd0428fae6e46', '53b6891700d5']
---

# 编译任务

请对以下知识条目执行编译：

- [[119d10406525]]
- [[fc4a1ff59694]]
- [[a1cf3b936810]]
- [[e85e004a275c]]
- [[dc28f8fc9d65]]
- [[b58d29b4437f]]
- [[8834be75e69c]]
- [[5b0ce0d9e7c2]]
- [[d0428fae6e46]]
- [[53b6891700d5]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
