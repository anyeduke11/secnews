---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.118743+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.622396+00:00"
params:
  item_ids: ['2bb344e53ce0', '64480b51b2cd', 'cf863a108bc7', '940fa787e021', '0591d0508d01', '349d7c7e6227', '838548db6e88', '352d746ba4aa', '534ab4511205', '8a8ea407ddac']
---

# 编译任务

请对以下知识条目执行编译：

- [[2bb344e53ce0]]
- [[64480b51b2cd]]
- [[cf863a108bc7]]
- [[940fa787e021]]
- [[0591d0508d01]]
- [[349d7c7e6227]]
- [[838548db6e88]]
- [[352d746ba4aa]]
- [[534ab4511205]]
- [[8a8ea407ddac]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
