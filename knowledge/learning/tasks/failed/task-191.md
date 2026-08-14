---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.137105+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.656895+00:00"
params:
  item_ids: ['d7098c7d5a04', '4c5998e7237d', '423e63fafcfc', 'd57f09702fb3', '438ede1041ff', 'f093a68591b0', 'f970fa6f821c', '2711856294b3', '84346aab6c05', 'cddbd6a70b7b']
---

# 编译任务

请对以下知识条目执行编译：

- [[d7098c7d5a04]]
- [[4c5998e7237d]]
- [[423e63fafcfc]]
- [[d57f09702fb3]]
- [[438ede1041ff]]
- [[f093a68591b0]]
- [[f970fa6f821c]]
- [[2711856294b3]]
- [[84346aab6c05]]
- [[cddbd6a70b7b]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
