---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.142024+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.665003+00:00"
params:
  item_ids: ['8ab77ec7cf47', '771ef2ae76f4', 'b664174371a9', 'b63ad4ae2439', '94d1d55d6395', 'c8fb63ba0b38', '1f1c88e35666', 'aff0b148d6bf', '1384adaf989e', '6b1c70121365']
---

# 编译任务

请对以下知识条目执行编译：

- [[8ab77ec7cf47]]
- [[771ef2ae76f4]]
- [[b664174371a9]]
- [[b63ad4ae2439]]
- [[94d1d55d6395]]
- [[c8fb63ba0b38]]
- [[1f1c88e35666]]
- [[aff0b148d6bf]]
- [[1384adaf989e]]
- [[6b1c70121365]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
