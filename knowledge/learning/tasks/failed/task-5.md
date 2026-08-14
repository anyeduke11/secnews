---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.111082+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.606687+00:00"
params:
  item_ids: ['8982d14169f4', '3b44582e8d70', '37f2d70edadb', '9086b8144854', 'cc67601bb309', '1d4c5cc1f3fc', 'fb85915c910f', 'bec52856f7d8', '0d5b74da5048', 'd3bcd604559e']
---

# 编译任务

请对以下知识条目执行编译：

- [[8982d14169f4]]
- [[3b44582e8d70]]
- [[37f2d70edadb]]
- [[9086b8144854]]
- [[cc67601bb309]]
- [[1d4c5cc1f3fc]]
- [[fb85915c910f]]
- [[bec52856f7d8]]
- [[0d5b74da5048]]
- [[d3bcd604559e]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
