# Phase 1j — 数据质量 + 增强

**状态**: 待批准
**日期**: 2026-07-16
**前置**: Phase 1i 完成（41 commits, compiled 4.9%）
**Token 预算**: ~25,000 / 30,000 session budget

## 目标

Phase 1i 闭环了 14 项 P1 偏差，基础设施（API + 前端组件）基本齐全。Phase 1j 聚焦：
1. **数据质量**：批量编译 PoC 50 条 + 18 空概念补定义 + 7 条 domain=null 分类 + 时区统一
2. **功能补齐**：联邦搜索前端 UI 集成
3. **设计对齐**：summaries/ 周回顾生成 + SOUL 编译触发 hook
4. **运维**：127 pending 任务清理

## 范围

| Task | 优先级 | 类型 | 描述 |
|------|--------|------|------|
| 10.1 | P2 | 数据质量 | 7 条 domain=null 自动分类 |
| 10.2 | P2 | 数据规范 | ingested_at 时区格式统一为 UTC Z |
| 10.3 | P2 | 设计对齐 | SOUL.md 由编译流程触发（watchdog hook） |
| 10.4 | P0 | 数据质量 | 批量编译 PoC 50 条（累计 70 条, ~17%） |
| 10.5 | P1 | 数据质量 | 18 个空模板概念补定义 |
| 10.6 | P1 | 功能补齐 | 联邦搜索前端 UI 集成 |
| 10.7 | P1 | 运维 | 127 pending 任务清理（归类/执行/失败） |
| 10.8 | P2 | 设计对齐 | summaries/ 周回顾 service + cron |

## 分组与依赖

```
Group X (快速修复) → Group Y (数据质量) → Group Z (功能增强) → Group W (设计对齐)
```

- **Group X** (Task 10.1-10.3): 独立小修复，无依赖
- **Group Y** (Task 10.4-10.5): 编译 50 条 + 空概念补定义（10.5 可与 10.4 合并执行）
- **Group Z** (Task 10.6-10.7): 前端 UI + 任务清理（独立）
- **Group W** (Task 10.8): summaries service（依赖编译数据更丰富后生成）

## 成功标准

1. compiled 比例 ≥ 15%（70/410+）
2. 18 个空概念全部有定义内容
3. 0 条 domain=null
4. 联邦搜索前端可用（输入 → 结果列表）
5. summaries/ 至少 1 个周回顾文件
6. SOUL.md 在编译任务完成后自动触发
7. pending/ 任务数 < 20（127 → 清理）
8. 前端 build 0 错误

## 关键决策

- **批量编译 50 条**：LLM 判断分类 + 概念提取，写入 scripts/phase1j_task1004_compile.py
- **空概念补定义**：LLM 为 18 个空模板生成定义内容（20-50 字）
- **ingested_at 统一**：Python 脚本批量将 +0800/+00:00 转为 UTC Z 后缀
- **SOUL 编译触发**：在 knowledge_watcher.py 的 `_maybe_update_map()` 旁新增 `_maybe_regenerate_soul()`
- **summaries 周回顾**：新增 summary_service.py，按周聚合 items/concepts/progress 生成 weekly-YYYY-Www.md
- **pending 任务清理**：扫描 pending/ 任务文件，按 task_type 分类，过期的移到 failed/
