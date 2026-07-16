---
task_type: "publish"
status: "pending"
created_at: "2026-07-16T02:51:48.841567+00:00"
params:
  draft_id: 4
  platform: "wechat"
  skill_name: "baoyu-post-to-wechat"
  options:
  dry_run: True
---

# 发布任务

## 草稿内容

# 测试

watchdog 自动同步测试。

## 发布参数

- **平台**: wechat
- **Skill**: baoyu-post-to-wechat
- **Draft ID**: 4
- **Options**: {'dry_run': True}

## 执行步骤

1. 读取草稿内容（上方 Markdown 正文）
2. 调用 skill `baoyu-post-to-wechat` 执行发布
3. 发布成功后，将 `published_url` 写入本文件 frontmatter 的 `result.published_url`
4. 移动本文件到 `done/` 目录
5. 如失败，移动到 `failed/` 并记录 error.md
