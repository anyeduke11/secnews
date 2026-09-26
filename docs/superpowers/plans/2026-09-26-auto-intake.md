# 自动入管规则引擎 — 实施计划 (2026-09-26)

**Spec**: `docs/superpowers/specs/2026-09-26-auto-intake-design.md`
**Base**: main@3a84da1 · **Branch**: auto-intake

## Task 1: promote 扩展 + auto_intake service

**Files**: `backend/services/sag_service.py`（promote 加 keyword-only 可选参 content/category/source，默认 None 保持收藏 API 兼容）、`backend/services/auto_intake_service.py`（新：评估+游标+每日上限+入管）、`backend/repository/hotspot_repo.py`（候选查询，按 quality_score 排序）、`backend/tests/test_auto_intake.py`（新）

- [ ] promote 扩展: keyword-only `content: str | None = None, category: str | None = None, source: str = "secnews"`（None 时不写对应 frontmatter 字段，收藏调用方零破坏）
- [ ] auto_intake service: `run_auto_intake()` 按设计稿 §3.2 六步；游标 kv `knowledge.auto_intake.cursor`；计数 kv `knowledge.auto_intake.daily_YYYYMMDD`（或按 ingested_at 实时 COUNT source='secnews_auto' 今日——取实现简者）
- [ ] 配置读取: `get_auto_intake_config()` 默认 enabled=false/min_score=85/limit=20/require_domain=true；写入走既有 settings API
- [ ] 测试: 开关关闭不动 / 上限截断 / 质量阈值过滤 / 域命中与未命中 / 游标防重复扫描 / promote 兼容（收藏 API 老调用零变化）

## Task 2: 挂载 + API + 前端

**Files**: `backend/scheduler/jobs/collect.py`（collect_all_job 尾部挂 auto_intake）、`backend/api/settings.py`（GET/PATCH auto-intake，行数门 285 内净零约束）、`frontend/src/components/settings/`（自动入管设置卡，挂 models 或 collection 分区——实现时按信息架构归位，倾向 collection）、`backend/tests/test_auto_intake_api.py`（新）

- [ ] collect_all_job 尾部: try-except 包裹（不阻塞采集主流程），日志一行
- [ ] API: GET /api/settings/auto-intake（返回配置+今日已入管数）/ PATCH（校验 min_score 0-100、limit 1-100、enabled bool；audit log）
- [ ] 前端设置卡: 开关 toggle + 数字输入（阈值/上限）+ 今日已入管展示；状态经 GET 刷新
- [ ] 测试: PATCH 校验/audit/auto-intake job 挂载不阻塞采集/前端渲染

## Task 3: 收口

- [ ] 全量回归 (基线 4843) + tsc/vitest + generate_meta + ruff + harness
- [ ] DEV-0231 + 计划勾选 + PRD 判断（知识管线能力增强，视内容决定是否补 PRD §3.4）

## 全局约束

- 不动 ai_hub；收藏 API 行为不变；不回填历史；gate 不新增（kv enabled）
- 行数门: settings.py 只减不增；新 api 逻辑尽量下沉 service
