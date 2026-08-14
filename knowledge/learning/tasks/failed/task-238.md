---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.144736+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.669508+00:00"
params:
  item_ids: ['802985b64026', 'bba432388511', '411f107db582', 'd059008a596b', '5c3e927ad22d', '3843ee26a0cc', '442a8fdd873d', 'ac28d55261a1', '8bbe78796cd2', 'be8c19e1ef7b']
---

# 编译任务

请对以下知识条目执行编译：

- [[802985b64026]]
- [[bba432388511]]
- [[411f107db582]]
- [[d059008a596b]]
- [[5c3e927ad22d]]
- [[3843ee26a0cc]]
- [[442a8fdd873d]]
- [[ac28d55261a1]]
- [[8bbe78796cd2]]
- [[be8c19e1ef7b]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
