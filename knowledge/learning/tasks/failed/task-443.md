---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.133310+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.724080+00:00"
params:
  item_ids: ['2f54e94a8ad9', '719306291abe', 'b07fc11bfd39', '3f568891a1ec', '9869dfde643c', '24c30276f683', '2288f88de820', 'e7fe11b7ba4b', '4a642fc431d9', 'd7caedef3640']
---

# 编译任务

请对以下知识条目执行编译：

- [[2f54e94a8ad9]]
- [[719306291abe]]
- [[b07fc11bfd39]]
- [[3f568891a1ec]]
- [[9869dfde643c]]
- [[24c30276f683]]
- [[2288f88de820]]
- [[e7fe11b7ba4b]]
- [[4a642fc431d9]]
- [[d7caedef3640]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
