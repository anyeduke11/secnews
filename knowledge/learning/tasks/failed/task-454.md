---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.135021+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.726883+00:00"
params:
  item_ids: ['00260fdb08d4', '79b8be77232e', 'd4f42164ffff', '347fc16d5c16', 'c95a74b704ab', 'b50d742b4430', '2446bb3e67f7', 'cb6c12daea1f', '0e5201c29189', '9c02984bb256']
---

# 编译任务

请对以下知识条目执行编译：

- [[00260fdb08d4]]
- [[79b8be77232e]]
- [[d4f42164ffff]]
- [[347fc16d5c16]]
- [[c95a74b704ab]]
- [[b50d742b4430]]
- [[2446bb3e67f7]]
- [[cb6c12daea1f]]
- [[0e5201c29189]]
- [[9c02984bb256]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
