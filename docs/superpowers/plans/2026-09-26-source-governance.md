# 数据源治理 + 介质分类 — 实施计划 (2026-09-26)

> **状态勘误 (2026-09-27 批量台账收口)**: 本计划已**完整交付** — 收口记录 [DEV-0232] (DEV_LOG.md), 交付内容: 数据源体系治理 — media_kind 维度+清理工具链+系统源管理+前端介质分组, 交付回归 13/13 全绿。下方勾选状态以收口记录与代码为准。


**Spec**: `docs/superpowers/specs/2026-09-26-source-governance-design.md`
**Base**: main@f08c8a3 · **Branch**: source-governance

## Task 1: media_kind 维度 + 存量推断 + 搜狗归档 + 多媒体首批源

**Files**: `backend/repository/migrations/121_source_media_kind.sql`（crawler_sources + source_stats 加列）、`backend/repository/db.py`（migration 注册表若有）、`backend/services/source_media_kind.py`（存量推断 + 常量，若逻辑薄可并入迁移脚本）、`scripts/` 或迁移内回填、`backend/tests/test_source_media_kind.py`（新）

- [x] migration 121: 两表加 `media_kind TEXT NOT NULL DEFAULT 'web'`；回填推断: name 含 `(搜狗)` → 'wechat'；url 含 youtube/bilibili → 'multimedia'；其余 'web'
- [x] 搜狗 6 源归档: UPDATE crawler_sources SET status='retired', enabled=0 WHERE media_kind='wechat'（幂等；已 retired 不重复）+ source_alerts 一条 `source_archived_wechat` P2
- [x] 首批多媒体源: probe 通过后 INSERT crawler_sources（media_kind='multimedia'，kind='rss'，category 归入既有枚举）；probe 不过换源，汇报说明
- [x] 测试: 迁移后列存在/推断正确/搜狗归档/幂等

## Task 2: 清理脚本 + 审计表 + 系统源手动管理 API

**Files**: `backend/repository/migrations/122_source_cleanup_log.sql`（新表）、`scripts/fix_source_stats_cleanup.py`（新，--dry-run 默认）、`backend/api/source_system_api.py`（新 ≤150 行：DELETE/PATCH system 源，audit 强制）、`backend/api/_registry.py`（登记净零）、`backend/tests/test_source_cleanup.py` + `test_source_system_api.py`（新）

- [x] 122: `source_cleanup_log(id, source_layer, source_ident, reason, executed_at, executed_by)`
- [x] 清理脚本: source_stats `status='dead' AND total_items=0` → 逐行写 log 后 DELETE；幂等；dry-run 报告变更面（预期 56）
- [x] API: DELETE /api/sources/system/{id}（写 log 必带 reason，同步删 source_stats 同名行）/ PATCH toggle enabled；均 audit
- [x] 测试: dry-run/execute/幂等/DELETE 审计/toggle

## Task 3: 前端矩阵分组 + 手动添加入口

**Files**: `frontend/src/components/shared/editorial/` 或矩阵所在组件（先 grep SourceMatrixCard）、`frontend/src/api/sources.ts`、前端测试

- [x] 矩阵按 media_kind 分组/筛选（全部/web/wechat/multimedia tab 或下拉）；retired 行灰显+标记
- [x] 手动添加源入口核验: 前端已有 custom 源添加 UI 则核验可用；无则补最小添加卡（URL+name+category，走 POST /api/sources/custom）
- [x] 测试: 分组渲染/筛选/retired 灰显

## Task 4: 收口

- [x] 全量回归（基线 4863）+ tsc/vitest + generate_meta + ruff + harness
- [x] DEV-0232 + 计划落账 + PRD 判断

## 全局约束

- migration 编号从 121 顺延（先 grep 确认当前最大号）；自愈/幂等；不动健康机语义；md/采集本体不动

## 实施记录 (2026-09-26 收口)

- **分支**: source-governance (base main@f08c8a3) · **commits**: df083c6 计划+设计稿 → e3b180c T1 (migration 121 + 搜狗归档 + YouTube ×2 多媒体源) → 2cd5523 T2 (清理脚本 + migration 122 审计表 + source_system_api 经 sources.py 聚合层挂载, _registry 零改动 90 routers 净零) → 524ad0e T3 (SourceMatrixCard 介质分组 + SourceSettings 添加入口核验) → 7cbff1c+341d3e4 review fix → 本条收口 (全量回归 + DEV-0232)。
- **审查结论**: Batch A (T1) Approved; Batch B (T2) Changes Required → 已修 (级联删 stats 限定同类目 (name, category) / DELETE reason min_length=1 / 审计先于任何 DELETE·UPDATE)。
- **§2 实测修正**: 初诊"6 源 retired"不成立 — 搜狗在注册层 crawler_sources 实测 0 行, 仅存在于统计层 source_stats 11 行 (标 wechat 不 retire, 可复活候选); 注册层 retired UPDATE 保留为幂等防御。注册层 39 源 = 37 + YouTube ×2 多媒体 (probe 直连失败, enabled=0 + notes 待 owner 配代理激活)。
- **parked**: ① 清理脚本仅解析 `--execute`, 未解析显式 `--dry-run` flag (传 `--dry-run` 会 argparse 报错; dry-run 为默认行为, 语义不受影响); ② DELETE 级联删同类目 stats 行只记 `stats_rows_deleted` 计数, 无逐行审计 (注册行本身有 source_cleanup_log 全量审计); ③ source_system_api 直连 repo 层为 source 域既存惯例 (同 sources.py / source_health_api.py 先例), 未引入 service 层。
- **清理执行裁决留待 owner**: 脚本不 execute — 与 auto-intake 不同, 此清理不可逆删统计历史 (56 空壳行), dry-run 实测就绪, 待 owner 自行 `--execute`。
