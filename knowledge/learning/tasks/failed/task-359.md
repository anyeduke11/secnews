---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.178636+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.700270+00:00"
params:
  item_ids: ['cf769bb738df', 'c63c43f7d375', 'd1ed3cb64f40', '0288290e4b72', '0188a8580de5', '5fa7b6ca38fe', 'f4840f52d675', 'da6de50a8504', '0cba0a10b800', 'a287d2d83ab0']
---

# 编译任务

请对以下知识条目执行编译：

- [[cf769bb738df]]
- [[c63c43f7d375]]
- [[d1ed3cb64f40]]
- [[0288290e4b72]]
- [[0188a8580de5]]
- [[5fa7b6ca38fe]]
- [[f4840f52d675]]
- [[da6de50a8504]]
- [[0cba0a10b800]]
- [[a287d2d83ab0]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
