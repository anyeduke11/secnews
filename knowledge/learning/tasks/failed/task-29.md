---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.114318+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.614454+00:00"
params:
  item_ids: ['4d00b8ca48d2', '59fee0233b60', '5de012bcd268', '7a3d5db64028', '6a92fff7377d', 'cd4d3742c449', '432f97f0697c', '4ebaaeb804ae', 'e00861602668', '190373efac6a']
---

# 编译任务

请对以下知识条目执行编译：

- [[4d00b8ca48d2]]
- [[59fee0233b60]]
- [[5de012bcd268]]
- [[7a3d5db64028]]
- [[6a92fff7377d]]
- [[cd4d3742c449]]
- [[432f97f0697c]]
- [[4ebaaeb804ae]]
- [[e00861602668]]
- [[190373efac6a]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
