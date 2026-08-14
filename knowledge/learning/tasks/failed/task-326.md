---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.164841+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.691469+00:00"
params:
  item_ids: ['4643d9e331a3', '5e7f61d30cb6', '047a1c08f4ae', '3c32fcf8dbf5', '6bea6bda18fe', '55b6ff46836c', 'a62969605b5c', '1ad579a14cf3', 'c9dc70635c23', '94eaba688f07']
---

# 编译任务

请对以下知识条目执行编译：

- [[4643d9e331a3]]
- [[5e7f61d30cb6]]
- [[047a1c08f4ae]]
- [[3c32fcf8dbf5]]
- [[6bea6bda18fe]]
- [[55b6ff46836c]]
- [[a62969605b5c]]
- [[1ad579a14cf3]]
- [[c9dc70635c23]]
- [[94eaba688f07]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
