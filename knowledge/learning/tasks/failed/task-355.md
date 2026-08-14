---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.178110+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.699090+00:00"
params:
  item_ids: ['24dca0050941', '9bc77b72f7e3', '6c4994d73bd3', '265f50af3f89', '9f83e55719bc', '9ad2a9d79066', '97d02b440785', 'c1d3f3294060', '7e2d918c84b6', 'fa4aae2fc901']
---

# 编译任务

请对以下知识条目执行编译：

- [[24dca0050941]]
- [[9bc77b72f7e3]]
- [[6c4994d73bd3]]
- [[265f50af3f89]]
- [[9f83e55719bc]]
- [[9ad2a9d79066]]
- [[97d02b440785]]
- [[c1d3f3294060]]
- [[7e2d918c84b6]]
- [[fa4aae2fc901]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
