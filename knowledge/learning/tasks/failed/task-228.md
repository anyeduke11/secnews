---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.142737+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.666094+00:00"
params:
  item_ids: ['553e8d75cff4', '98d06bb5e719', '450975ceec03', '470a7640a841', 'f51a465256ce', '35a0e53da665', '7989b7e25bae', 'ce7cd0684e0c', '510c33770130', '72d8855bbaaf']
---

# 编译任务

请对以下知识条目执行编译：

- [[553e8d75cff4]]
- [[98d06bb5e719]]
- [[450975ceec03]]
- [[470a7640a841]]
- [[f51a465256ce]]
- [[35a0e53da665]]
- [[7989b7e25bae]]
- [[ce7cd0684e0c]]
- [[510c33770130]]
- [[72d8855bbaaf]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
