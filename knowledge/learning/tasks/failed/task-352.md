---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.177629+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.698208+00:00"
params:
  item_ids: ['92b8ec0b1e5f', 'fb6f5b5d5a20', 'be60f282b0a6', 'db38893f7abc', '1296424b047b', '79bb6ebacc96', '588127bdd194', '22c9f1673226', 'a1d85ff52040', 'd5068a6cba2b']
---

# 编译任务

请对以下知识条目执行编译：

- [[92b8ec0b1e5f]]
- [[fb6f5b5d5a20]]
- [[be60f282b0a6]]
- [[db38893f7abc]]
- [[1296424b047b]]
- [[79bb6ebacc96]]
- [[588127bdd194]]
- [[22c9f1673226]]
- [[a1d85ff52040]]
- [[d5068a6cba2b]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
