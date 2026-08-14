---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.136714+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.656151+00:00"
params:
  item_ids: ['4869c49323b5', 'a1c74bdd7fb2', 'f19342b79ba2', '70a41f17ec00', 'ef5b9d4318da', '9442e6a83b36', '03fd82ba57a4', 'bcfff57b797c', '24c861a54be3', '9fa6457bbe09']
---

# 编译任务

请对以下知识条目执行编译：

- [[4869c49323b5]]
- [[a1c74bdd7fb2]]
- [[f19342b79ba2]]
- [[70a41f17ec00]]
- [[ef5b9d4318da]]
- [[9442e6a83b36]]
- [[03fd82ba57a4]]
- [[bcfff57b797c]]
- [[24c861a54be3]]
- [[9fa6457bbe09]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
