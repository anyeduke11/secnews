---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.123126+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.631797+00:00"
params:
  item_ids: ['3048db5a897b', '21acc82d14cb', '13d91c765f64', '8910d07d773a', 'f5ac70647eb0', '9f0cd0506cbc', '377b88b89dcc', 'a3204dddd41e', 'caa4a9ba5fac', '55ae5aa116fd']
---

# 编译任务

请对以下知识条目执行编译：

- [[3048db5a897b]]
- [[21acc82d14cb]]
- [[13d91c765f64]]
- [[8910d07d773a]]
- [[f5ac70647eb0]]
- [[9f0cd0506cbc]]
- [[377b88b89dcc]]
- [[a3204dddd41e]]
- [[caa4a9ba5fac]]
- [[55ae5aa116fd]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
