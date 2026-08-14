---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.082518+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.834544+00:00"
params:
  item_ids: ['a10920125c96', 'ec79dbe69814', '2239582057a4', 'a92ee2ce710e', 'e18cec63e191', 'e70c38c4987c', '69a733c988b4', '2df0950ef4cc', '6bb0cb922903', 'a388ef00431e']
---

# 编译任务

请对以下知识条目执行编译：

- [[a10920125c96]]
- [[ec79dbe69814]]
- [[2239582057a4]]
- [[a92ee2ce710e]]
- [[e18cec63e191]]
- [[e70c38c4987c]]
- [[69a733c988b4]]
- [[2df0950ef4cc]]
- [[6bb0cb922903]]
- [[a388ef00431e]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
