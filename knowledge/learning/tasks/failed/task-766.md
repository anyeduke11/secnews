---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.189705+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.809673+00:00"
params:
  item_ids: ['4d381575d296', '7a225283bb5a', '732e17525e61', '129ef6ba30ef', 'e22c81844fc0', 'db1f4178a821', 'a41f69cda708', '0ae5275a4c07', 'eb83bf584818', 'c6ce89d6606a']
---

# 编译任务

请对以下知识条目执行编译：

- [[4d381575d296]]
- [[7a225283bb5a]]
- [[732e17525e61]]
- [[129ef6ba30ef]]
- [[e22c81844fc0]]
- [[db1f4178a821]]
- [[a41f69cda708]]
- [[0ae5275a4c07]]
- [[eb83bf584818]]
- [[c6ce89d6606a]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
