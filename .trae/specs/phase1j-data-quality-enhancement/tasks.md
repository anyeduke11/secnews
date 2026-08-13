# Phase 1j 任务分解

## Group X — 快速修复 (Task 10.1-10.3) ✅ commit 6a3a0d3

### Task 10.1: 7 条 domain=null 自动分类 (P2)
- [x] 10.1.1: Grep 找出 7 个 domain:null 文件 ID
- [x] 10.1.2: 调用 `POST /api/knowledge/classify/batch` 或直接调 `auto_classifier.classify_item()`
- [x] 10.1.3: 验证 7 条 domain 不再为 null
- [x] 10.1.4: `full_sync_items_to_db()` 同步到 SQLite

### Task 10.2: ingested_at 时区格式统一 (P2)
- [x] 10.2.1: 编写脚本扫描 knowledge/items/*.md，解析 ingested_at
- [x] 10.2.2: 将 `+0800`/`+00:00` 格式转为 UTC `Z` 后缀
- [x] 10.2.3: 批量更新 frontmatter
- [x] 10.2.4: 验证 0 条非 Z 后缀（抽样）
- [x] 10.2.5: 直接 SQL UPDATE SQLite 409 条（upsert_item 不更新 ingested_at）

### Task 10.3: SOUL.md 编译流程触发 (P2)
- [x] 10.3.1: 在 `knowledge_watcher.py` 新增 `_maybe_regenerate_soul(event)`
- [x] 10.3.2: 当检测到 `tasks/done/` 新增 compile 类型任务时，调用 `soul_service.create_soul_task()` 触发重生成
- [x] 10.3.3: 添加 debounce（5 秒）避免连续触发
- [x] 10.3.4: 验证 compile done 后 SOUL 重生成任务被创建
- [x] 10.3.5: Bug 修复（Group W）：`regenerate_soul` import → `create_soul_task`

---

## Group Y — 数据质量 (Task 10.4-10.5) ✅ commit 3eedb2d

### Task 10.4: 批量编译 PoC 50 条 (P0)
- [x] 10.4.1: 查询 50 条未编译 items（compiled=false，按 ingested_at DESC，排除已编译）
- [x] 10.4.2: 读取每条 .md 标题 + 前 300 字正文
- [x] 10.4.3: LLM 判断分类（domain/topic/type/difficulty + tags + concepts）
- [x] 10.4.4: 更新 frontmatter（compiled=true + 分类字段 + concepts）
- [x] 10.4.5: 新概念落盘 concepts/{slug}.md（domain 动态化）
- [x] 10.4.6: 同步到 SQLite + 重建 graph.json + 更新 _MAP.md
- [x] 10.4.7: 验证 compiled 比例 17.1%（70/409，超过 15% 目标）

### Task 10.5: 18 个空模板概念补定义 (P1)
- [x] 10.5.1: Grep 找出 18 个 `待补充——自动创建` 概念文件
- [x] 10.5.2: LLM 为每个概念生成 20-50 字定义 + 3 个关键要点
- [x] 10.5.3: 更新概念 .md body
- [x] 10.5.4: 验证 0 个空模板

---

## Group Z — 功能增强 (Task 10.6-10.7) ✅ commit pending

### Task 10.6: 联邦搜索前端 UI (P1)
- [x] 10.6.1: 新建 `frontend/src/components/KnowledgeSearchBar.tsx`
- [x] 10.6.2: 调用 `GET /api/knowledge/search?q=&limit=20`
- [x] 10.6.3: 结果列表区分 hotspot/local 来源（颜色/标签）
- [x] 10.6.4: 集成到 KnowledgePage.tsx 顶部工具栏
- [x] 10.6.5: `npm run build` 验证 0 错误

### Task 10.7: 127 pending 任务清理 (P1)
- [x] 10.7.1: 扫描 pending/ 任务文件，解析 task_type
- [x] 10.7.2: 统计各类型分布（124 compile + 2 learning_plan + 1 soul）
- [x] 10.7.3: 过期任务（created_at > 7 天）移到 failed/（无，所有任务 < 2 天）
- [x] 10.7.4: 重复 compile 任务去重（保留最新 10 个，114 条移到 failed/）
- [x] 10.7.5: 验证 pending/ = 13 条（< 20）

---

## Group W — 设计对齐 (Task 10.8) ✅ commit pending

### Task 10.8: summaries/ 周回顾生成 (P2)
- [x] 10.8.1: 新建 `backend/services/summary_service.py`（255 行）
- [x] 10.8.2: `generate_weekly_summary(year_week: str)` 函数
  - 聚合当周新增 items（按 ingested_at 过滤）
  - 聚合当周活跃 concepts（按 updated_at 近似，表无 created_at）
  - 聚合当前 learning progress 快照（无时间字段）
  - 生成 `knowledge/summaries/weekly-{year_week}.md`
- [x] 10.8.3: 新增 `POST /api/knowledge/summaries/weekly` API
- [x] 10.8.4: 注册 cron job（Sun 06:00 Asia/Shanghai，job 14，与 SOUL cron 链式）
- [x] 10.8.5: 手动生成本周回顾验证（weekly-2026-W29.md，26 items + 96 concepts）
- [x] 10.8.6: 验证 summaries/ 至少 1 个文件
- [x] 10.8.7: 新增 `GET /api/knowledge/summaries` 列表 API
- [x] 10.8.8: Bug 修复：knowledge_watcher.py 中 `regenerate_soul` import → `create_soul_task`
