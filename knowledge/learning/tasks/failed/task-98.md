---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.123479+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.632520+00:00"
params:
  item_ids: ['4f5bb7842f62', '17d7815bd3d9', 'b8a3e9cf42c2', 'be30a1064049', '042e1141ad07', '2dc0497fb034', '429344b25a2e', 'fa7256245899', '546efdb89f8f', '76b8ae2ddb12']
---

# 编译任务

请对以下知识条目执行编译：

- [[4f5bb7842f62]]
- [[17d7815bd3d9]]
- [[b8a3e9cf42c2]]
- [[be30a1064049]]
- [[042e1141ad07]]
- [[2dc0497fb034]]
- [[429344b25a2e]]
- [[fa7256245899]]
- [[546efdb89f8f]]
- [[76b8ae2ddb12]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
