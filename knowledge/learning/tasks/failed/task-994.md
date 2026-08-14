---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.098100+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.875075+00:00"
params:
  item_ids: ['84661286acd7', 'e63a6bacb720', 'd1c565d76d55', '53f0bbaa9a2a', '2efa77dd1271', '4578a1a6ecc0', 'cbf9599e275a', '95efe7c0580d', '5814550110a7', '1ead51d0eb1d']
---

# 编译任务

请对以下知识条目执行编译：

- [[84661286acd7]]
- [[e63a6bacb720]]
- [[d1c565d76d55]]
- [[53f0bbaa9a2a]]
- [[2efa77dd1271]]
- [[4578a1a6ecc0]]
- [[cbf9599e275a]]
- [[95efe7c0580d]]
- [[5814550110a7]]
- [[1ead51d0eb1d]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
