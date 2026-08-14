---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.176458+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.788686+00:00"
params:
  item_ids: ['d17af3e5cb98', '6b9da15e1ef1', '782a611e24bf', 'ee6f96d56331', 'd00ae7e955d8', 'e6c002065825', 'e65196cbe044', '1b6235880bda', '613e2495317b', '6cac303cf8fa']
---

# 编译任务

请对以下知识条目执行编译：

- [[d17af3e5cb98]]
- [[6b9da15e1ef1]]
- [[782a611e24bf]]
- [[ee6f96d56331]]
- [[d00ae7e955d8]]
- [[e6c002065825]]
- [[e65196cbe044]]
- [[1b6235880bda]]
- [[613e2495317b]]
- [[6cac303cf8fa]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
