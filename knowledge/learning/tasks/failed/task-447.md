---
task_type: "compile"
status: "failed"
created_at: "2026-08-03T18:00:00.133936+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.725215+00:00"
params:
  item_ids: ['98a23d671645', 'f7abd3f8e1ac', '7b1ef9367eaa', '0db7af6e8e5a', '119c21082b62', '5ec51c001bd7', '2a339fe086cd', 'ff7b3d52afc3', 'da79e22f6547', '15f839a5ec52']
---

# 编译任务

请对以下知识条目执行编译：

- [[98a23d671645]]
- [[f7abd3f8e1ac]]
- [[7b1ef9367eaa]]
- [[0db7af6e8e5a]]
- [[119c21082b62]]
- [[5ec51c001bd7]]
- [[2a339fe086cd]]
- [[ff7b3d52afc3]]
- [[da79e22f6547]]
- [[15f839a5ec52]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
