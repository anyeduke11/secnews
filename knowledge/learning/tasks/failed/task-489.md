---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.149398+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.736615+00:00"
params:
  item_ids: ['cda19880ce39', '6bfadd78980a', '5813ac43973e', '5a334a2effad', '8c21eec8fc75', 'ada4b0bc462c', '33865dad2d96', '07f52c8ff9f7', 'd2d3f51223ff', '6106c67e2249']
---

# 编译任务

请对以下知识条目执行编译：

- [[cda19880ce39]]
- [[6bfadd78980a]]
- [[5813ac43973e]]
- [[5a334a2effad]]
- [[8c21eec8fc75]]
- [[ada4b0bc462c]]
- [[33865dad2d96]]
- [[07f52c8ff9f7]]
- [[d2d3f51223ff]]
- [[6106c67e2249]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
