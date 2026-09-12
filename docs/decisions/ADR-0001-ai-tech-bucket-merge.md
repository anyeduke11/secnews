# ADR-0001: Feed 均衡查询中 tech 维持并入 ai 桶

- 日期: 2026-09-12; 状态: **采纳 (方案 A — 设计包推荐项; owner 指示"按设计包完成开发")**
- 上游: `docs/POST_R2_ENHANCEMENTS_DESIGN_2026-09-12.md` T4

## 背景

`hotspot_repo.query` 对 `category="ai"` 的过滤在 SQL 层为 `category IN ('ai', 'tech')`
(Phase 35 引入), 且 `HotspotService._query_balanced` 的均衡桶元组不含 `Category.TECH` —
即 tech (IT/科技资讯) 没有独立曝光桶, 经由 AI 桶进入 "all" Feed 并与 AI 共享页内配额。
UI 分类栏 "科技/AI" 合并展示, `category=tech` 精确筛选仍可用 (走 `= 'tech'` 分支? 不 —
tech 精确筛选同样命中合并口径, 这是 Phase 35 的既定设计)。

DEV-0185 bid 清扫后该口径被重新审视: 是否应给 tech 独立桶。

## 决定

**维持现状 (方案 A)**, 本 ADR 即为该既定事实的正式记录:

1. 均衡查询桶保持 6 元组 (ai / ai_security / security / finance / startup / github),
   不为 tech 增加独立桶。
2. `category="ai"` 的 SQL 层 `IN ('ai','tech')` 合并口径保持不变。
3. 测试与注释须引用本 ADR (tech 排除类测试选 security 而非 tech, 因 ai 桶含 tech)。

## 理由

- Phase 35 已是裁决过的现状, UI 与查询口径对齐, 无回归即无债。
- 内容定位: tech(IT 资讯) 对安全从业者属背景信息, 与 AI 合并曝光合理;
  独立桶会稀释 security/ai_security 等核心域的页内配额。
- 实践域打标 (`classify_practice_domain`) 与兴趣引擎乘子按 **title** 归因,
  不依赖类目口径 — tech 条目在兴趣层不受本决定影响。

## 后果

- 若未来 tech 内容权重上升需独立曝光, 走方案 B (独立桶 + 前端分类栏拆分, 约 1 天),
  需重新裁决并更新本 ADR。
- 影响范围备注: `HotspotService._query_balanced` / `hotspot_repo.query` /
  `count_unique_urls_in_range` 三处的合并口径是同一决定的三个投影, 改动须同步。
