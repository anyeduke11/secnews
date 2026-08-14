---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.140437+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.662441+00:00"
params:
  item_ids: ['16b7fb6fa6d3', '36b437dce60f', 'bd28cb0583c3', '55c037264b95', 'b341f8df56c6', '62a45614cba4', '8e8d4c686493', '9ad9ed3eb7d6', 'c05840919172', 'cf3b34970dd1']
---

# 编译任务

请对以下知识条目执行编译：

- [[16b7fb6fa6d3]]
- [[36b437dce60f]]
- [[bd28cb0583c3]]
- [[55c037264b95]]
- [[b341f8df56c6]]
- [[62a45614cba4]]
- [[8e8d4c686493]]
- [[9ad9ed3eb7d6]]
- [[c05840919172]]
- [[cf3b34970dd1]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
