---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.190379+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.810520+00:00"
params:
  item_ids: ['136dbda08c8b', '90519cc3508e', 'a789a4a14d88', '86117b572d0a', '037301e8617b', '1051fb7e288c', '412f9825c9ed', 'd31daef94400', '4fddf0a232ef', 'db8e32164bb3']
---

# 编译任务

请对以下知识条目执行编译：

- [[136dbda08c8b]]
- [[90519cc3508e]]
- [[a789a4a14d88]]
- [[86117b572d0a]]
- [[037301e8617b]]
- [[1051fb7e288c]]
- [[412f9825c9ed]]
- [[d31daef94400]]
- [[4fddf0a232ef]]
- [[db8e32164bb3]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
