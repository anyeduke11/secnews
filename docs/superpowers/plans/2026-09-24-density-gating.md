# 采集密度门禁限制 — 实施计划 (2026-09-24)

**Spec**: `docs/superpowers/specs/2026-09-24-density-gating-design.md` (owner 三裁决已录 §2)
**Base**: main@70d5d5b · **Branch**: density-gating

## Task 1: 信号层 (数据查询扩展)

**Files**: `backend/repository/hotspot_repo.py`、`backend/repository/quality_rejection_repo.py` (若无 source 维聚合方法则扩展)、`backend/tests/test_density_signals.py` (新)

- [x] `get_recent_quality_stats` 扩展: 增可选参数 `practice_domains: list[str] | None` → 每源返回 `{avg_quality, count, hit_count}` (hit = practice_domain IN 关注域); 不传则 hit_count=None (向后兼容 T4 既有调用与测试)。
- [x] 拒收聚合: 近 50 次尝试口径 = 该源 hotspots 入库 count + quality_rejection_log 拒收 count (窗口: 拒收日志近 7d, 入库近 7d, 口径注释写清)。先读 quality_rejection_log 表结构定 source 维聚合可行性: 有 source 列直接 GROUP BY; 无则按 source_name 近似 (url 域名) — 实现时定, 汇报说明。
- [x] 测试: hit_ratio 计算 (命中/不命中/关注域为空) / 拒收率聚合 / 向后兼容。

## Task 2: 乘子层 (三信号复合)

**Files**: `backend/services/source_scheduler_service.py`、`backend/tests/test_source_quality_cadence.py` (扩展)

- [x] 常量区: M_r 阈值 (0.3/0.6 → 1.0/1.3/1.8, 样本<10→1.0)、M_i 阈值 (h≥0.5→0.7 / 0<h<0.5→1.0 / h=0 且 count≥10→1.4 / 未配置或不足→1.0)。
- [x] 纯函数: `rejection_cadence_multiplier(rejection_rate, attempts)`、`interest_cadence_multiplier(hit_ratio, count, configured)`。
- [x] `build_cadence_overrides` 复合改造: 签名增 rejection_stats 与 interest 信号入参; 倍率 = M_q × M_r × M_i 后夹取 [max(600, base×0.25), base×4] (夹取不变)。
- [x] tick 接线: source_scheduler_service tick 拉三信号 (关注域从 settings_service 读 `interest.practice_domains`, 空列表 = 未配置)。
- [x] 测试: 三乘子矩阵 / 零命中×高质量豁免 (1.4×0.5=0.7 仍加密) / 夹取 / 样本不足各路径 / 未配置域 M_i=1.0 / 既有 T4 用例不回归。

## Task 3: AI 推荐 advisor (interest_domain_advisor)

**Files**: `backend/services/interest_domain_advisor.py` (新)、`backend/api/settings.py` 或独立 `backend/api/interest_advisor_api.py` (行数门内从简)、`backend/services/ai_hub/prompts.py` (advisor prompt)、`frontend/src/components/settings/PracticeDomainsCard.tsx` + test、`backend/tests/test_interest_domain_advisor.py` (新)

- [x] 服务: 组装输入 (近 7d 域分布 + interest_signals 近 30d 行为聚合 + 当前勾选) → ai_hub llm_service.generate(task="interest_advisor") → 解析 JSON {recommended≤5, reasons}; 域枚举校验 (auto_classifier PRACTICE_DOMAIN_LABELS 键集, 越界丢弃); 解析失败返缓存/空不抛错; 结果写 settings.kv `interest.advisor_cache` (24h TTL)。
- [x] API: GET /api/interest/domains/recommendations (读缓存或按需刷新, 失败 200+空列表+note); 采纳走既有 settings PATCH interest.practice_domains (前端合并, 不新做 PUT 端点)。feature gate: interest_engine 关闭时 404 (is_extension_enabled 先例)。
- [x] prompt: build_interest_advisor_prompt — 输入为聚合统计 (无原始 URL/标题), 输出契约 JSON, 严格域枚举约束写入 prompt。
- [x] 前端: PracticeDomainsCard 增「AI 推荐域」区 (chips + 一句话理由 + 采纳按钮=合并进勾选); 测试: 渲染/采纳/空态。
- [x] 测试: 枚举校验/解析失败兜底/缓存 TTL/gate 关闭 404/LLM mock。

## Task 4: 收口

- [x] 全量回归 `.venv/bin/python3 -m pytest backend/tests/ -q` (基线 4773 passed) + 前端 `npx tsc --noEmit && npx vitest run`。
- [x] generate_meta --check (新增 service 148→149 若 advisor 算 service; api 若新文件注意 _registry 净零与行数门) + harness_analyze + 触碰文件 ruff。
- [x] DEV_LOG DEV-0229 + 计划勾选落账 + PRD 是否需补 (设置页能力无新分区, advisor 属采集配置增强 — 判断后写)。

## 全局约束

- 红线: 不动 ai_hub 调用链内部 (advisor 经 llm_service.generate 单出口调用属正常消费); 不动 13 collector 本体; 不改 gate 权重。
- M_i 消费只读用户勾选域; advisor 推荐不自动生效 (设计稿 §4.3)。
- 行数门: settings.py 291 只减; _registry 271 净零; 新 api 文件 ≤150。
- api 层新端点走 R3 (经 service, 不直连 repo)。

## 实施记录

- **分支**: `density-gating` (base main@70d5d5b)
- **Commits**: 17a00aa (设计稿+计划) → 0f9eba6 (T1 信号层) → 570b1ea (T2 三信号乘子) → f7caac6 (T1 docstring 修正) → b5d7a63 (T3 advisor 全栈, services 148→149 同步) → 584dd97 (推荐区手动刷新入口) → 收口 commit (本 commit: 全量回归 + DEV-0229 + 首例 repo→service 依赖裁决落账 + R4 惰性环解环)
- **审查**: Batch A (T1/T2) **Approved**; Batch B (T3) **Approved** (minor: 手动刷新入口已由 584dd97 收敛)
- **收口验证**: 后端全量 pytest **4815 passed / 9 skipped / 0 failed** (基线 4773 + 42 新例; 首跑 2 failed 为本分支引入的 `ai_hub ⇄ auto_classifier` 惰性环, 已解环 — `build_interest_advisor_prompt` 域枚举改参数注入, 白名单零条目不扩张, 复跑零失败); 前端 `tsc --noEmit` 0 错 / `vitest run` 85 文件 **627 passed**; `generate_meta --check` OK (89 routers / 149 services); `harness_analyze --check` 0 errors; ruff 触碰文件 0 告警
- **Parked**:
  - 每日 job 兜底缓存 — controller 裁决边际价值低 (手动 `?force=1` 已覆盖; 设计稿 §4.2 已注记)
  - fence 正则病态嵌套无害 (取首个闭合, 输入为受控 LLM JSON)
  - M_i 超集打标口径 — hit = 勾选域直接命中, 不含子域超集 (hotspot_repo docstring 已标)
