---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.178762+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.700450+00:00"
params:
  item_ids: ['eaf83f510cf2', '45f109cb3b03', '60222f10b1ae', '2f2516a2d008', 'a828afe01489', 'd34e4722ecdf', 'b1bac992db96', '14723c29ee55', '135919db3131', '7aa22be9fb91']
---

# 编译任务

请对以下知识条目执行编译：

- [[eaf83f510cf2]]
- [[45f109cb3b03]]
- [[60222f10b1ae]]
- [[2f2516a2d008]]
- [[a828afe01489]]
- [[d34e4722ecdf]]
- [[b1bac992db96]]
- [[14723c29ee55]]
- [[135919db3131]]
- [[7aa22be9fb91]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
