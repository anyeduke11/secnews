---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.111561+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.607768+00:00"
params:
  item_ids: ['824900d16aea', '9053fcd717b2', '868edf948701', '5748c90352bb', '49d32f7ea736', 'a9f2f7d0efde', 'bfe00170671b', 'ecd5b968ece6', '332c451a881c', '5a5dd3df1e67']
---

# 编译任务

请对以下知识条目执行编译：

- [[824900d16aea]]
- [[9053fcd717b2]]
- [[868edf948701]]
- [[5748c90352bb]]
- [[49d32f7ea736]]
- [[a9f2f7d0efde]]
- [[bfe00170671b]]
- [[ecd5b968ece6]]
- [[332c451a881c]]
- [[5a5dd3df1e67]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
