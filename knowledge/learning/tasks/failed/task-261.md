---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.150037+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.674648+00:00"
params:
  item_ids: ['ad7b6f1b33bb', 'eb29d1693cbe', 'eadc3cd4cd5e', '2036408c8f2b', 'be28097c7f8a', '6a3b2699fe33', 'ee48b5689289', '5152636384ee', '004932c2270f', '553b8729becf']
---

# 编译任务

请对以下知识条目执行编译：

- [[ad7b6f1b33bb]]
- [[eb29d1693cbe]]
- [[eadc3cd4cd5e]]
- [[2036408c8f2b]]
- [[be28097c7f8a]]
- [[6a3b2699fe33]]
- [[ee48b5689289]]
- [[5152636384ee]]
- [[004932c2270f]]
- [[553b8729becf]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
