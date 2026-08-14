---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.147960+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.671700+00:00"
params:
  item_ids: ['bcf33a84b320', '54de59f19249', '6f607bf1d40d', '78bfab3b291c', 'ab168d39be76', '2960d1c347fd', 'aacc62f066d9', 'db44461c5e08', 'c8f82e6c4240', 'fa9fb4605c10']
---

# 编译任务

请对以下知识条目执行编译：

- [[bcf33a84b320]]
- [[54de59f19249]]
- [[6f607bf1d40d]]
- [[78bfab3b291c]]
- [[ab168d39be76]]
- [[2960d1c347fd]]
- [[aacc62f066d9]]
- [[db44461c5e08]]
- [[c8f82e6c4240]]
- [[fa9fb4605c10]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
