---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.132850+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.723634+00:00"
params:
  item_ids: ['d5655d429d38', 'd720c9939094', 'cdf71ffe75d2', 'daaef62abf66', 'f5b6a4235592', 'a1b63d5af4a6', '3e6a518cb5e4', 'cf18367a69ee', '6600f71c661f', '05ab02481123']
---

# 编译任务

请对以下知识条目执行编译：

- [[d5655d429d38]]
- [[d720c9939094]]
- [[cdf71ffe75d2]]
- [[daaef62abf66]]
- [[f5b6a4235592]]
- [[a1b63d5af4a6]]
- [[3e6a518cb5e4]]
- [[cf18367a69ee]]
- [[6600f71c661f]]
- [[05ab02481123]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
