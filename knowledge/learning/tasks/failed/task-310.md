---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.159575+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.687405+00:00"
params:
  item_ids: ['aece3d3c2914', 'd2d6e5e509f1', '7fbe86e1c685', '0aa80881a0a6', '7e0f137310d9', '66df3937eafc', '5a907503e5da', '63063743b439', 'e30b2c8f89a3', '2c7b12ce31bf']
---

# 编译任务

请对以下知识条目执行编译：

- [[aece3d3c2914]]
- [[d2d6e5e509f1]]
- [[7fbe86e1c685]]
- [[0aa80881a0a6]]
- [[7e0f137310d9]]
- [[66df3937eafc]]
- [[5a907503e5da]]
- [[63063743b439]]
- [[e30b2c8f89a3]]
- [[2c7b12ce31bf]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
