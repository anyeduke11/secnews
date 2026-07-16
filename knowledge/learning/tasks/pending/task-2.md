---
task_type: "generate_soul"
status: "pending"
created_at: "2026-07-15T12:41:06.324479+00:00"
params:
  scope: "full"
---

# SOUL 重新生成任务

请扫描 knowledge/items/ 和 knowledge/concepts/，重新生成 SOUL.md 角色画像。

## 参数
- scope: full（全量扫描重建）

## 执行步骤
1. 扫描 knowledge/items/ 所有条目的 domain/topic/tags/concepts
2. 扫描 knowledge/concepts/ 所有概念
3. 按 §3.3 格式生成 SOUL.md（5 节：身份/知识深度/兴趣趋势/学习偏好/内容创作风格）
4. 写入 knowledge/SOUL.md
5. 移动本文件到 done/
