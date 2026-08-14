---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.151859+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.678134+00:00"
params:
  item_ids: ['3a92a360b158', '6b59d81f6e7d', 'f9629e50fd19', '734aada091aa', 'd98b8158a346', '93fff9021523', 'b8434a8176f4', '1cd764c71d65', 'cd699853e0cd', 'a7b4d48eb70d']
---

# 编译任务

请对以下知识条目执行编译：

- [[3a92a360b158]]
- [[6b59d81f6e7d]]
- [[f9629e50fd19]]
- [[734aada091aa]]
- [[d98b8158a346]]
- [[93fff9021523]]
- [[b8434a8176f4]]
- [[1cd764c71d65]]
- [[cd699853e0cd]]
- [[a7b4d48eb70d]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
