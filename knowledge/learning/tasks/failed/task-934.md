---
task_type: "compile"
status: "failed"
created_at: "2026-08-08T18:00:00.091856+00:00"
reason: "superseded: 由规则式自动消费者 (consume_compile_tasks) 替代; 存量积压清理"
failed_at: "2026-08-14T12:26:25.852140+00:00"
params:
  item_ids: ['9db8e06d236f', 'ab5d8690b080', 'b630b953c271', '1d92d4f1cdde', 'b103682ff627', 'f7a7c6d5b392', 'b1a7c187d33e', 'df21c42e65ca', '0dc86dec8ce5', '9f034549e94c']
---

# 编译任务

请对以下知识条目执行编译：

- [[9db8e06d236f]]
- [[ab5d8690b080]]
- [[b630b953c271]]
- [[1d92d4f1cdde]]
- [[b103682ff627]]
- [[f7a7c6d5b392]]
- [[b1a7c187d33e]]
- [[df21c42e65ca]]
- [[0dc86dec8ce5]]
- [[9f034549e94c]]

## 编译步骤
1. 分类 + 打标（domain/topic/type/difficulty + tags）
2. 概念提取（写入 concepts/{slug}.md）
3. 概念关联（更新条目 frontmatter.concepts）
4. 标记 compiled=true
