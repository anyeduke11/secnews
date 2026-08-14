---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.087759+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.845101+00:00"
params:
  item_ids: ['4d8410a498a6', 'b592946d6753', 'c5bf09213ad4', '941b54860d35', 'c403f0c31f86', '90a4bb5596ee', '9b3c342a3c13', '7e96b17af93d', '6207f5531c24', 'e89e0724aaf4']
---

# 编译任务

请对以下知识条目执行编译：

- [[4d8410a498a6]]
- [[b592946d6753]]
- [[c5bf09213ad4]]
- [[941b54860d35]]
- [[c403f0c31f86]]
- [[90a4bb5596ee]]
- [[9b3c342a3c13]]
- [[7e96b17af93d]]
- [[6207f5531c24]]
- [[e89e0724aaf4]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
