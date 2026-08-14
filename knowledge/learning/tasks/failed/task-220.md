---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.141576+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.664338+00:00"
params:
  item_ids: ['214ca4c2e87d', 'feee7dd3f071', 'a74a8ccd21e0', '83e28e0b9a87', '9807ce39c280', '3344e10bb45c', '96c175356e53', 'c2d786fb6b27', 'fb5138834dea', '013fab478493']
---

# 编译任务

请对以下知识条目执行编译：

- [[214ca4c2e87d]]
- [[feee7dd3f071]]
- [[a74a8ccd21e0]]
- [[83e28e0b9a87]]
- [[9807ce39c280]]
- [[3344e10bb45c]]
- [[96c175356e53]]
- [[c2d786fb6b27]]
- [[fb5138834dea]]
- [[013fab478493]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
