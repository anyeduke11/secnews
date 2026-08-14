---
task_type: "compile"
status: "failed"
created_at: "2026-08-02T18:00:00.130700+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.644656+00:00"
params:
  item_ids: ['8fb1755d08a3', '404399ba475a', '1603c1306887', 'a9f6afbd2832', '32e81e30b888', '68a7ca7e7aa2', '2e668b278657', 'b09299be792c', '76e18ccffd27', 'ebbc150b6437']
---

# 编译任务

请对以下知识条目执行编译：

- [[8fb1755d08a3]]
- [[404399ba475a]]
- [[1603c1306887]]
- [[a9f6afbd2832]]
- [[32e81e30b888]]
- [[68a7ca7e7aa2]]
- [[2e668b278657]]
- [[b09299be792c]]
- [[76e18ccffd27]]
- [[ebbc150b6437]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
