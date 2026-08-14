---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.085122+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.839647+00:00"
params:
  item_ids: ['1ae7712cdcdc', 'e594f36f8192', 'e40a85b8a99f', '8fc3790ea09f', '2de6fd1e1750', 'e13b7722e190', '38ef6bb31746', 'd30f8ec7dca2', '9507682d90d1', 'fc8744833119']
---

# 编译任务

请对以下知识条目执行编译：

- [[1ae7712cdcdc]]
- [[e594f36f8192]]
- [[e40a85b8a99f]]
- [[8fc3790ea09f]]
- [[2de6fd1e1750]]
- [[e13b7722e190]]
- [[38ef6bb31746]]
- [[d30f8ec7dca2]]
- [[9507682d90d1]]
- [[fc8744833119]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
