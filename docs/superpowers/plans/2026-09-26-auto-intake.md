# 自动入管规则引擎 — 实施计划 (2026-09-26)

**Spec**: `docs/superpowers/specs/2026-09-26-auto-intake-design.md`
**Base**: main@3a84da1 · **Branch**: auto-intake

## Task 1: promote 扩展 + auto_intake service

**Files**: `backend/services/sag_service.py`（promote 加 keyword-only 可选参 content/category/source，默认 None 保持收藏 API 兼容）、`backend/services/auto_intake_service.py`（新：评估+游标+每日上限+入管）、`backend/repository/hotspot_repo.py`（候选查询，按 quality_score 排序）、`backend/tests/test_auto_intake.py`（新）

- [x] promote 扩展: keyword-only `content: str | None = None, category: str | None = None, source: str = "secnews"`（None 时不写对应 frontmatter 字段，收藏调用方零破坏）
- [x] auto_intake service: `run_auto_intake()` 按设计稿 §3.2 六步；游标 kv `knowledge.auto_intake.cursor`；计数 kv `knowledge.auto_intake.daily_YYYYMMDD`（或按 ingested_at 实时 COUNT source='secnews_auto' 今日——取实现简者）→ 实现取实时 COUNT（重启安全）
- [x] 配置读取: `get_auto_intake_config()` 默认 enabled=false/min_score=85/limit=20/require_domain=true；写入走既有 settings API
- [x] 测试: 开关关闭不动 / 上限截断 / 质量阈值过滤 / 域命中与未命中 / 游标防重复扫描 / promote 兼容（收藏 API 老调用零变化）

## Task 2: 挂载 + API + 前端

**Files**: `backend/scheduler/jobs/collect.py`（collect_all_job 尾部挂 auto_intake）、`backend/api/settings.py`（GET/PATCH auto-intake，行数门 285 内净零约束）、`frontend/src/components/settings/`（自动入管设置卡，挂 models 或 collection 分区——实现时按信息架构归位，倾向 collection）、`backend/tests/test_auto_intake_api.py`（新）

- [x] collect_all_job 尾部: try-except 包裹（不阻塞采集主流程），日志一行
- [x] API: GET /api/settings/auto-intake（返回配置+今日已入管数）/ PATCH（校验 min_score 0-100、limit 1-100、enabled bool；audit log）
- [x] 前端设置卡: 开关 toggle + 数字输入（阈值/上限）+ 今日已入管展示；状态经 GET 刷新
- [x] 测试: PATCH 校验/audit/auto-intake job 挂载不阻塞采集/前端渲染

## Task 3: 收口

- [x] 全量回归 (基线 4843) + tsc/vitest + generate_meta + ruff + harness
- [x] DEV-0231 + 计划勾选 + PRD 判断（知识管线能力增强，视内容决定是否补 PRD §3.4）

## 全局约束

- 不动 ai_hub；收藏 API 行为不变；不回填历史；gate 不新增（kv enabled）
- 行数门: settings.py 只减不增；新 api 逻辑尽量下沉 service

## 实施记录 (2026-09-26 收口, DEV-0231)

- **分支**: `auto-intake`（base main@3a84da1）
- **Commits**: 34f6d74 计划+设计稿 → eee96c9 T1 评估服务 + promote 扩展 → 1cb21ab T2 挂载 + API + 设置卡 → 1719fe9 Batch A review fix → 收口 commit（本条落账）
- **Batch A 审查**: Changes Required → fix（1719fe9）: PATCH 响应缺 `today_intaken`，前端保存后需二次 GET；修复为响应带 `today_intaken`，契约与 GET 一致
- **实现偏差注记**: 每日计数取"实时 COUNT 今日 secnews_auto"（Task 1 列举的两案中实现简者）；API 落 `backend/api/auto_intake_api.py` 新文件（非 settings.py 内扩张，行数门净零不受影响）
- **量级估算落账**: 近 7 天 hotspots 4989 条中 ≥85 分占 66%、域命中 93% — 两道过滤联手后余量仍大，限流核心为每日上限（20）而非阈值/域命中
- **Parked**: ① 个别测试 docstring 笔误（断言正确，注释错字）；② LIMIT 截断 + 游标推进组合静默放弃同窗低分溢出候选——设计一致（游标语义 = 窗口推进不重扫），调低阈值回捞需手动清游标
- **PRD 判断**: 自动入管属 PRD §3.4 设置页能力（collection 采集与管线分区）增强，已在接口消费段补登记 GET/PATCH `/api/settings/auto-intake` 一句
- **验证**: 后端全量 `pytest backend/tests/ -q` 4863 passed / 9 skipped / 0 failed（8m12s，基线 4843 + 本分支 20）；前端 tsc 0 错 / vitest 87 文件 641 passed；`generate_meta --check` OK（90 routers / 150 services）；ruff 触碰 10 文件 0 告警；`harness_analyze --check` 0 errors
