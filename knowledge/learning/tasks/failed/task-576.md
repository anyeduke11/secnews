---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.163040+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.766278+00:00"
params:
  item_ids: ['d08483410a34', 'd1ac6a9d7098', '64940540094e', '8f1ee69bb31d', 'b93ad892df81', '0411a639350a', 'e380e70168b8', '33d37ef978c3', '2e4829153c6a', '870ba2b59291']
---

# 编译任务

请对以下知识条目执行编译：

- [[d08483410a34]]
- [[d1ac6a9d7098]]
- [[64940540094e]]
- [[8f1ee69bb31d]]
- [[b93ad892df81]]
- [[0411a639350a]]
- [[e380e70168b8]]
- [[33d37ef978c3]]
- [[2e4829153c6a]]
- [[870ba2b59291]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
