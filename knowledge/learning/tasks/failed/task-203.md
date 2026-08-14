---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.139027+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.659949+00:00"
params:
  item_ids: ['046b282facd9', 'f416208501aa', '61bb192257fe', '805f21c06ad4', 'fff585ed82ef', '5d50b95c3cdf', '77a575133f82', '08eb7e40737e', '139673048d32', 'c67ef5de7ddf']
---

# 编译任务

请对以下知识条目执行编译：

- [[046b282facd9]]
- [[f416208501aa]]
- [[61bb192257fe]]
- [[805f21c06ad4]]
- [[fff585ed82ef]]
- [[5d50b95c3cdf]]
- [[77a575133f82]]
- [[08eb7e40737e]]
- [[139673048d32]]
- [[c67ef5de7ddf]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
