---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.129133+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.716138+00:00"
params:
  item_ids: ['48f1c21fd118', '1eb4bc470682', '250caddccd6e', '2ce25a6ebbd1', '773fbf537f11', '8baea4044903', '91e20cea7f57', '2c5f8ac95648', '0761a057c347', 'c23fe3e18e0b']
---

# 编译任务

请对以下知识条目执行编译：

- [[48f1c21fd118]]
- [[1eb4bc470682]]
- [[250caddccd6e]]
- [[2ce25a6ebbd1]]
- [[773fbf537f11]]
- [[8baea4044903]]
- [[91e20cea7f57]]
- [[2c5f8ac95648]]
- [[0761a057c347]]
- [[c23fe3e18e0b]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
