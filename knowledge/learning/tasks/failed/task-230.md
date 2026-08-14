---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.143103+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.666571+00:00"
params:
  item_ids: ['28ad1a754a6d', '976d8fcb14a6', '81e279140a95', '064dec97bc33', '54aa69ae4d40', '167d615a1244', 'a0b5d12ca0dd', '3baf145ff20c', 'e4c80bd8ec28', 'fbdf82df689f']
---

# 编译任务

请对以下知识条目执行编译：

- [[28ad1a754a6d]]
- [[976d8fcb14a6]]
- [[81e279140a95]]
- [[064dec97bc33]]
- [[54aa69ae4d40]]
- [[167d615a1244]]
- [[a0b5d12ca0dd]]
- [[3baf145ff20c]]
- [[e4c80bd8ec28]]
- [[fbdf82df689f]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
