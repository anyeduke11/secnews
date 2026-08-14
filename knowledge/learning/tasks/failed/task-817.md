---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.075108+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.822647+00:00"
params:
  item_ids: ['484c3bc29cd4', '1f5c6f4ad90d', '668f84b56555', 'd2486fbbdcf1', '6a5c5a1629b8', '13eab737ab3e', '17cae6708ab2', 'd2183c181a7d', '784a3e45b38a', 'e0878d909235']
---

# 编译任务

请对以下知识条目执行编译：

- [[484c3bc29cd4]]
- [[1f5c6f4ad90d]]
- [[668f84b56555]]
- [[d2486fbbdcf1]]
- [[6a5c5a1629b8]]
- [[13eab737ab3e]]
- [[17cae6708ab2]]
- [[d2183c181a7d]]
- [[784a3e45b38a]]
- [[e0878d909235]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
