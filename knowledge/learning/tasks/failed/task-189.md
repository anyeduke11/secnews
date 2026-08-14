---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.136798+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.656413+00:00"
params:
  item_ids: ['56dc4c512f2a', '032eb96fc40d', 'd38d9d434ad5', '594018af0319', 'fa8fd7505dee', 'f685c79358f6', 'ad45129eec01', '151b94465971', 'a9741cd154ba', 'f940c587a2a3']
---

# 编译任务

请对以下知识条目执行编译：

- [[56dc4c512f2a]]
- [[032eb96fc40d]]
- [[d38d9d434ad5]]
- [[594018af0319]]
- [[fa8fd7505dee]]
- [[f685c79358f6]]
- [[ad45129eec01]]
- [[151b94465971]]
- [[a9741cd154ba]]
- [[f940c587a2a3]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
