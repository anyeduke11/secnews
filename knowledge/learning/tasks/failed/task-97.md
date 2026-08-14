---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.123340+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.632348+00:00"
params:
  item_ids: ['67c4a9172b0d', 'd8555aedcd59', '78636312c3d0', 'c9929ecf85a7', '3f339fc67c29', 'cf682da26b0f', '83bc8ae1f2ec', 'a7a3b64f6fef', '7e955f1d53a8', '20b73a1d07eb']
---

# 编译任务

请对以下知识条目执行编译：

- [[67c4a9172b0d]]
- [[d8555aedcd59]]
- [[78636312c3d0]]
- [[c9929ecf85a7]]
- [[3f339fc67c29]]
- [[cf682da26b0f]]
- [[83bc8ae1f2ec]]
- [[a7a3b64f6fef]]
- [[7e955f1d53a8]]
- [[20b73a1d07eb]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
