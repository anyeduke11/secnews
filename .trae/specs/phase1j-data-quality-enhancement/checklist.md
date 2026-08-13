# Phase 1j 验证清单

## Group X — 快速修复 (commit 6a3a0d3)

### Task 10.1: domain=null 分类
- [x] 7 条 items 的 domain 字段不再为 null
- [x] SQLite 同步完成（`SELECT COUNT(*) FROM knowledge_items WHERE domain IS NULL` = 0）
- [x] frontmatter 与 SQLite 一致

### Task 10.2: ingested_at 时区统一
- [x] 抽样 10 条验证：ingested_at 均以 `Z` 结尾
- [x] 无 `+0800` 或 `+00:00` 格式残留（Grep 0 命中）
- [x] 时间值语义正确（UTC 转换无偏差）
- [x] SQLite 直接 SQL UPDATE 409 条（upsert_item 不更新 ingested_at）

### Task 10.3: SOUL 编译触发
- [x] `knowledge_watcher.py` 含 `_maybe_regenerate_soul` 函数
- [x] compile done 任务触发后调用 `create_soul_task()` 生成 SOUL 重生成任务
- [x] debounce 生效（5s 内连续触发只执行一次）
- [x] Bug 修复：`regenerate_soul` import → 改为 `create_soul_task`（Group W commit 修复）

---

## Group Y — 数据质量 (commit 3eedb2d)

### Task 10.4: 批量编译 50 条
- [x] 50 条新 items compiled=true
- [x] compiled 比例 17.1%（70/409，超过 15% 目标）
- [x] graph.json 节点数 96（48 原 + 48 新概念）
- [x] _MAP.md 索引更新
- [x] SQLite 同步完成
- [x] concept domain 动态化（不再硬编码 security）

### Task 10.5: 空概念补定义
- [x] 18 个空模板概念已补定义（DEFINITIONS 字典）
- [x] 每个概念 .md body 含 20-50 字定义 + 3 个关键要点
- [x] 概念覆盖 AI/安全/金融/方法论等领域

---

## Group Z — 功能增强 (commit pending)

### Task 10.6: 联邦搜索前端
- [x] `KnowledgeSearchBar.tsx` 存在（176 行）
- [x] 调用 `GET /api/knowledge/search?q=&limit=20`
- [x] 300ms debounce + 最小 2 字符 + Escape 清除 + click-outside 关闭
- [x] HOTSPOT(蓝)/LOCAL(紫) 来源标签视觉区分
- [x] 集成到 KnowledgePage.tsx 顶部工具栏
- [x] `npm run build` 0 错误

### Task 10.7: pending 任务清理
- [x] pending/ 文件数 13（< 20 目标）
- [x] 114 条 compile 任务移到 failed/（保留最新 10 条）
- [x] failed/ 任务 frontmatter 追加 reason + failed_at 字段
- [x] 保留任务：10 compile + 2 learning_plan + 1 soul

---

## Group W — 设计对齐 (commit pending)

### Task 10.8: summaries 周回顾
- [x] `summary_service.py` 存在（255 行）
- [x] `POST /api/knowledge/summaries/weekly` API 可用
- [x] `GET /api/knowledge/summaries` 列表 API 可用
- [x] `knowledge/summaries/weekly-2026-W29.md` 已生成（26 items + 96 concepts + 35 progress）
- [x] cron job 注册（Sun 06:00 Asia/Shanghai，job 14）
- [x] 链式触发：SOUL(04:00) → migrate(05:00) → summary(06:00)

---

## Fail Loud 检查

- [x] 所有 8 项 Task 全部完成
- [x] 前端 build 0 错误
- [x] 后端 API routes 注册验证通过（/summaries, /summaries/weekly）
- [x] scheduled_summary_job 在 jobs.py 中存在
- [x] project_memory.md 更新
- [x] tasks.md checkbox 全部 [x]
- [x] 未推送 GitHub（用户手动 push）
- [x] Bug 修复：knowledge_watcher.py 中 `regenerate_soul` import → `create_soul_task`
