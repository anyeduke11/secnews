# 采集密度门禁限制 — 实施计划 (2026-09-24)

**Spec**: `docs/superpowers/specs/2026-09-24-density-gating-design.md` (owner 三裁决已录 §2)
**Base**: main@70d5d5b · **Branch**: density-gating

## Task 1: 信号层 (数据查询扩展)

**Files**: `backend/repository/hotspot_repo.py`、`backend/repository/quality_rejection_repo.py` (若无 source 维聚合方法则扩展)、`backend/tests/test_density_signals.py` (新)

- [ ] `get_recent_quality_stats` 扩展: 增可选参数 `practice_domains: list[str] | None` → 每源返回 `{avg_quality, count, hit_count}` (hit = practice_domain IN 关注域); 不传则 hit_count=None (向后兼容 T4 既有调用与测试)。
- [ ] 拒收聚合: 近 50 次尝试口径 = 该源 hotspots 入库 count + quality_rejection_log 拒收 count (窗口: 拒收日志近 7d, 入库近 7d, 口径注释写清)。先读 quality_rejection_log 表结构定 source 维聚合可行性: 有 source 列直接 GROUP BY; 无则按 source_name 近似 (url 域名) — 实现时定, 汇报说明。
- [ ] 测试: hit_ratio 计算 (命中/不命中/关注域为空) / 拒收率聚合 / 向后兼容。

## Task 2: 乘子层 (三信号复合)

**Files**: `backend/services/source_scheduler_service.py`、`backend/tests/test_source_quality_cadence.py` (扩展)

- [ ] 常量区: M_r 阈值 (0.3/0.6 → 1.0/1.3/1.8, 样本<10→1.0)、M_i 阈值 (h≥0.5→0.7 / 0<h<0.5→1.0 / h=0 且 count≥10→1.4 / 未配置或不足→1.0)。
- [ ] 纯函数: `rejection_cadence_multiplier(rejection_rate, attempts)`、`interest_cadence_multiplier(hit_ratio, count, configured)`。
- [ ] `build_cadence_overrides` 复合改造: 签名增 rejection_stats 与 interest 信号入参; 倍率 = M_q × M_r × M_i 后夹取 [max(600, base×0.25), base×4] (夹取不变)。
- [ ] tick 接线: source_scheduler_service tick 拉三信号 (关注域从 settings_service 读 `interest.practice_domains`, 空列表 = 未配置)。
- [ ] 测试: 三乘子矩阵 / 零命中×高质量豁免 (1.4×0.5=0.7 仍加密) / 夹取 / 样本不足各路径 / 未配置域 M_i=1.0 / 既有 T4 用例不回归。

## Task 3: AI 推荐 advisor (interest_domain_advisor)

**Files**: `backend/services/interest_domain_advisor.py` (新)、`backend/api/settings.py` 或独立 `backend/api/interest_advisor_api.py` (行数门内从简)、`backend/services/ai_hub/prompts.py` (advisor prompt)、`frontend/src/components/settings/PracticeDomainsCard.tsx` + test、`backend/tests/test_interest_domain_advisor.py` (新)

- [ ] 服务: 组装输入 (近 7d 域分布 + interest_signals 近 30d 行为聚合 + 当前勾选) → ai_hub llm_service.generate(task="interest_advisor") → 解析 JSON {recommended≤5, reasons}; 域枚举校验 (auto_classifier PRACTICE_DOMAIN_LABELS 键集, 越界丢弃); 解析失败返缓存/空不抛错; 结果写 settings.kv `interest.advisor_cache` (24h TTL)。
- [ ] API: GET /api/interest/domains/recommendations (读缓存或按需刷新, 失败 200+空列表+note); 采纳走既有 settings PATCH interest.practice_domains (前端合并, 不新做 PUT 端点)。feature gate: interest_engine 关闭时 404 (is_extension_enabled 先例)。
- [ ] prompt: build_interest_advisor_prompt — 输入为聚合统计 (无原始 URL/标题), 输出契约 JSON, 严格域枚举约束写入 prompt。
- [ ] 前端: PracticeDomainsCard 增「AI 推荐域」区 (chips + 一句话理由 + 采纳按钮=合并进勾选); 测试: 渲染/采纳/空态。
- [ ] 测试: 枚举校验/解析失败兜底/缓存 TTL/gate 关闭 404/LLM mock。

## Task 4: 收口

- [ ] 全量回归 `.venv/bin/python3 -m pytest backend/tests/ -q` (基线 4773 passed) + 前端 `npx tsc --noEmit && npx vitest run`。
- [ ] generate_meta --check (新增 service 148→149 若 advisor 算 service; api 若新文件注意 _registry 净零与行数门) + harness_analyze + 触碰文件 ruff。
- [ ] DEV_LOG DEV-0229 + 计划勾选落账 + PRD 是否需补 (设置页能力无新分区, advisor 属采集配置增强 — 判断后写)。

## 全局约束

- 红线: 不动 ai_hub 调用链内部 (advisor 经 llm_service.generate 单出口调用属正常消费); 不动 13 collector 本体; 不改 gate 权重。
- M_i 消费只读用户勾选域; advisor 推荐不自动生效 (设计稿 §4.3)。
- 行数门: settings.py 291 只减; _registry 271 净零; 新 api 文件 ≤150。
- api 层新端点走 R3 (经 service, 不直连 repo)。
