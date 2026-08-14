---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.150440+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.675171+00:00"
params:
  item_ids: ['78b9b8acf6d5', '8d49b38c7231', 'df0601d3bb36', 'c001903392e5', '0d8330a762a1', '71d9d7c119ed', '1ac830363352', '72f0fa5c715a', '4ef397e79a60', 'e6ae93d51578']
---

# 编译任务

请对以下知识条目执行编译：

- [[78b9b8acf6d5]]
- [[8d49b38c7231]]
- [[df0601d3bb36]]
- [[c001903392e5]]
- [[0d8330a762a1]]
- [[71d9d7c119ed]]
- [[1ac830363352]]
- [[72f0fa5c715a]]
- [[4ef397e79a60]]
- [[e6ae93d51578]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
