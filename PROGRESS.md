# v0.5 重构执行进度（PROGRESS.md）

> 规格文件：`docs/v0.5_refactor_plan.md`（唯一真理）。接手会话先读本文件，不重做已完成任务。
> 止损：基线不符→BLOCKED.md；连败 3 次→停；劣于基线→回滚如实报告。
>
> **2026-08-21 SPEC 更替**：正式 SPEC 已改写为「统一前端 + DeepSeek Harness 认知层」方案
> （取代旧的性能+Workbench+自研 AiHub 版，旧版归档于 `docs/archived/v0.5_refactor_plan_perf_only.md`）。
> M1 性能三任务 / M2 DB 瘦身承接不变；M3 改为 editorial 对齐填空；M4 改为 dsh 认知层。
> T0 已完成项保留。

## 基线档案（2026-08-20/21 实测）

| 指标 | 基线值 | 目标 | 测量命令 |
|------|--------|------|----------|
| 后端测试收集数 | **2547**（0 error，修复后） | ≥2547，skipped 不增 | `.venv/bin/python -m pytest backend/tests/ --collect-only -q \| tail -1` |
| 冷路径 p95 | **待服务启动后测**（后端当前未运行） | <150ms | `.venv/bin/python scripts/quick_perf.py --cold` |
| 查询计划 | `idx_hotspot_region` + **TEMP B-TREE FOR ORDER BY** | 出 `idx_list_visible` 无 TEMP SORT | §12 EXPLAIN 命令 |
| 主 chunk | **1,144,684 B (1.14MB)** `index-DugkVWQY.js` | <300KB | `ls -laS frontend/dist/assets/*.js` |
| DB 体积 | **1.0GB** | <300MB | `du -sh backend/hotspot.db` |
| hotspots 行数 | 2952（ingested_at NULL 仅 1 行） | — | sqlite3 COUNT |
| LLM 出口 | 双入口（llm_service + ai_service） | 单出口 ai_hub.py | §12 grep 命令 |

### 基线勘误（与方案原记载的差异，已同步修订方案文档）
1. 迁移编号 061 已被占用（`061_v0.4_chunk_fts_cjk.sql`），新迁移从 **064** 起编。
2. DB 膨胀源是 `quality_check_logs_archive`(265 万行) / `quality_check_logs`(115 万行) /
   `crawler_runs`(16 万) / `raw_items`(13.8 万)，不是 hotspots（仅 2952 行）。
   Task 4 瘦身重心已按此调整。
3. 现状查询已用 `idx_hotspot_region` 但排序走 TEMP B-TREE；测试基线 2547 取代方案的 2288。

### 存量缺陷修复（T0，不属于任何 Task）
- `backend/tests/test_llm_evaluate.py` 收集错误（ImportError: `_parse_eval_json`）：
  该函数 v4.4 后位于 ai_service，测试仍从 llm_service 导入且 mock 错层（AsyncClient vs 同步 Client）。
  已按实际契约重写，测试意图不变，7 用例全过。

## 任务清单

- [x] T0 基线测量 + PROGRESS.md + quick_perf --cold 模式 + 测试基线修复
- [ ] M1-Task1 列表查询索引化（迁移 064 + 回填脚本 + hotspot_repo 改造）
- [ ] M1-Task2 缓存日志采样 + 真实预热
- [ ] M1-Task3 Vite manualChunks 拆包 + echarts lazy
- [ ] M1 里程碑验收
- [ ] M2-Task4 db_diet.py + 表生命周期台账
- [ ] M2-Task5 /api/workbench/summary
- [ ] M2 里程碑验收
- [ ] M3 Workbench 页面 + AiHub Step1-2
- [ ] M3 里程碑验收
- [ ] M4 AiHub Step3-4（灰区路由/预算/t_extract/t_advice/注入防护/配置页/评测集/校准）
- [ ] M4 里程碑验收
- [ ] M5 删双入口 + 门禁参数配置 + P2 余项
- [ ] M5 版本 0.5.0 + CHANGELOG + generate_meta
- [ ] 全局结束门禁 + 最终 code review

## 里程碑验收记录

（每里程碑结束在此追加：命令 + 输出摘要）

### T0 提交记录
- `fix(test): repair llm_evaluate baseline imports/mock layer`（基线修复）
- `feat(perf): quick_perf --cold 双轨冷路径模式 + PROGRESS.md 基线档案`
