---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.117242+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.619236+00:00"
params:
  item_ids: ['02bfeeebf4a2', '4294861a644b', '1ca365b4c19a', '063e7aa6d0cd', '5902a689974c', '520faf324dfa', 'c27d005945ed', 'f3704636312a', '829bdc0998c4', '79095a15427d']
---

# 编译任务

请对以下知识条目执行编译：

- [[02bfeeebf4a2]]
- [[4294861a644b]]
- [[1ca365b4c19a]]
- [[063e7aa6d0cd]]
- [[5902a689974c]]
- [[520faf324dfa]]
- [[c27d005945ed]]
- [[f3704636312a]]
- [[829bdc0998c4]]
- [[79095a15427d]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
