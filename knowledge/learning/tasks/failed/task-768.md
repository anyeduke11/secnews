---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.190001+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.810121+00:00"
params:
  item_ids: ['bcc52fc79708', 'fa55d745baae', 'fb82b677273d', '5b3cb2b8f36d', 'e04e7b412b73', '3a71c4f4cbcd', '8953ac4ce1cb', '2c91d10a9c8b', '85085f364a64', 'e69706d9183a']
---

# 编译任务

请对以下知识条目执行编译：

- [[bcc52fc79708]]
- [[fa55d745baae]]
- [[fb82b677273d]]
- [[5b3cb2b8f36d]]
- [[e04e7b412b73]]
- [[3a71c4f4cbcd]]
- [[8953ac4ce1cb]]
- [[2c91d10a9c8b]]
- [[85085f364a64]]
- [[e69706d9183a]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
