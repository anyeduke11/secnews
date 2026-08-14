---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.178016+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.790923+00:00"
params:
  item_ids: ['623a1b81c364', '247dddf679f2', 'adaba04e9426', 'ed14fdfeedc4', '27fcac200ad1', 'f2ae78479ba5', '47d991039f26', 'd92f2b3030bc', '4c6bc5b324f0', '616fc477f61e']
---

# 编译任务

请对以下知识条目执行编译：

- [[623a1b81c364]]
- [[247dddf679f2]]
- [[adaba04e9426]]
- [[ed14fdfeedc4]]
- [[27fcac200ad1]]
- [[f2ae78479ba5]]
- [[47d991039f26]]
- [[d92f2b3030bc]]
- [[4c6bc5b324f0]]
- [[616fc477f61e]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
