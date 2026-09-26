# 数据源治理 + 介质分类 — 实施计划 (2026-09-26)

**Spec**: `docs/superpowers/specs/2026-09-26-source-governance-design.md`
**Base**: main@f08c8a3 · **Branch**: source-governance

## Task 1: media_kind 维度 + 存量推断 + 搜狗归档 + 多媒体首批源

**Files**: `backend/repository/migrations/121_source_media_kind.sql`（crawler_sources + source_stats 加列）、`backend/repository/db.py`（migration 注册表若有）、`backend/services/source_media_kind.py`（存量推断 + 常量，若逻辑薄可并入迁移脚本）、`scripts/` 或迁移内回填、`backend/tests/test_source_media_kind.py`（新）

- [ ] migration 121: 两表加 `media_kind TEXT NOT NULL DEFAULT 'web'`；回填推断: name 含 `(搜狗)` → 'wechat'；url 含 youtube/bilibili → 'multimedia'；其余 'web'
- [ ] 搜狗 6 源归档: UPDATE crawler_sources SET status='retired', enabled=0 WHERE media_kind='wechat'（幂等；已 retired 不重复）+ source_alerts 一条 `source_archived_wechat` P2
- [ ] 首批多媒体源: probe 通过后 INSERT crawler_sources（media_kind='multimedia'，kind='rss'，category 归入既有枚举）；probe 不过换源，汇报说明
- [ ] 测试: 迁移后列存在/推断正确/搜狗归档/幂等

## Task 2: 清理脚本 + 审计表 + 系统源手动管理 API

**Files**: `backend/repository/migrations/122_source_cleanup_log.sql`（新表）、`scripts/fix_source_stats_cleanup.py`（新，--dry-run 默认）、`backend/api/source_system_api.py`（新 ≤150 行：DELETE/PATCH system 源，audit 强制）、`backend/api/_registry.py`（登记净零）、`backend/tests/test_source_cleanup.py` + `test_source_system_api.py`（新）

- [ ] 122: `source_cleanup_log(id, source_layer, source_ident, reason, executed_at, executed_by)`
- [ ] 清理脚本: source_stats `status='dead' AND total_items=0` → 逐行写 log 后 DELETE；幂等；dry-run 报告变更面（预期 56）
- [ ] API: DELETE /api/sources/system/{id}（写 log 必带 reason，同步删 source_stats 同名行）/ PATCH toggle enabled；均 audit
- [ ] 测试: dry-run/execute/幂等/DELETE 审计/toggle

## Task 3: 前端矩阵分组 + 手动添加入口

**Files**: `frontend/src/components/shared/editorial/` 或矩阵所在组件（先 grep SourceMatrixCard）、`frontend/src/api/sources.ts`、前端测试

- [ ] 矩阵按 media_kind 分组/筛选（全部/web/wechat/multimedia tab 或下拉）；retired 行灰显+标记
- [ ] 手动添加源入口核验: 前端已有 custom 源添加 UI 则核验可用；无则补最小添加卡（URL+name+category，走 POST /api/sources/custom）
- [ ] 测试: 分组渲染/筛选/retired 灰显

## Task 4: 收口

- [ ] 全量回归（基线 4863）+ tsc/vitest + generate_meta + ruff + harness
- [ ] DEV-0232 + 计划落账 + PRD 判断

## 全局约束

- migration 编号从 121 顺延（先 grep 确认当前最大号）；自愈/幂等；不动健康机语义；md/采集本体不动
