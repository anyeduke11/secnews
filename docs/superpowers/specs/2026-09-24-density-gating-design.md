# 采集密度门禁限制 — 设计稿 (2026-09-24)

## 1. 目标与第一性原理

采集密度的目标函数 = 让「过得了门 × 用户会消费」的内容以匹配频率到达。

盲区诊断 (实测):
- **白跑看不见**: 拒收条目不入库, T4 的 avg(quality_score) 只反映幸存者; 拒收率 90% 的源照常调度。
- **用户需求不参与**: interest_engine boost 仅作用读时排序, 采集侧零耦合。
- **关注域静态**: 用户勾选后无 AI 辅助, 冷启动与盲区无人补。

## 2. owner 裁决 (2026-09-24)

1. 关注域信号 = **用户显式选择 + AI 推荐** (LLM 分析近期抓取分布+点击行为, 推荐域; 用户可一键采纳; 域枚举限网络信息安全+AI 领域合法集合)。
2. 零命中处置 = **降频 + 高质量豁免** (降抓取频率, 但高质量源经复合乘子仍可加密 — "推送高质量资讯")。
3. 拒收率信号 M_r **本轮纳入**。

## 3. 三信号复合乘子

```
cadence_eff = clip( base × M_q × M_r × M_i , [max(600, base×0.25), base×4] )
```

| 乘子 | 信号 | 映射 | 样本不足 |
|---|---|---|---|
| M_q (已有 T4) | 近 20 条 avg(quality_score) | ≥75→0.5 / 40-75→1.0 / <40→2.0 | <5 条→1.0 |
| M_r 门禁健康 | 近 50 次尝试拒收率 r (quality_rejection_log 按源) | r<0.3→1.0 / 0.3-0.6→1.3 / ≥0.6→1.8 | <10 次→1.0 |
| M_i 关注命中 | 近 20 条入库条目 practice_domain ∈ 关注域比例 h | h≥0.5→0.7 / 0<h<0.5→1.0 / h=0 且≥10 条→1.4 | 未配置域或 <10 条→1.0 |

裁决②体现: 零命中 1.4 × 高质量 0.5 = 0.7 仍加密 — 质量豁免由复合结构自然给出, 不需特判。

护栏: 夹取不变; 健康机 (stale/dead/retired) 语义不变, 密度调节与失效判定解耦; M_i 阈值/常量集中在 scheduler_service 常量区。

## 4. 关注域双通道 (裁决①)

### 4.1 用户显式 (已有, 微调)
settings.kv `interest.practice_domains` 保持唯一真源; PracticeDomainsCard 从 10 域枚举多选 (auto_classifier.PRACTICE_DOMAIN_LABELS)。

### 4.2 AI 推荐 (新: interest_domain_advisor)
- 服务: `backend/services/interest_domain_advisor.py`, 经 ai_hub 单出口调默认 LLM (task=interest_advisor, 走 scenario light 档)。
- 输入 (确定性组装, 不含原始 URL): ①近 7d 各 practice_domain 入库分布 (top N + 占比); ②interest_signals 近 30d 各域行为聚合分 (复用 interest_engine_service 聚合); ③当前勾选域。
- 输出契约: JSON {recommended: [≤5 合法域], reasons: {域: 一句话}} — **域枚举校验**: 推荐域 ∉ 合法集合 → 丢弃该项; 解析失败 → 返回上次缓存/空推荐, 不抛错。
- 触发: 手动为主 (前端"获取推荐"按钮) + 每日 job 兜底缓存 (失败静默)。**推荐不自动生效** — 用户在卡片上一键采纳 (合并进勾选) 后才影响 M_i。
- 缓存: settings.kv `interest.advisor_cache` (含时间戳), 24h 内复用。

### 4.3 M_i 消费的"关注域"
= 用户勾选域 (含已采纳的推荐)。行为聚合 boost 不直接进 M_i (避免 LLM/行为回路直接控制调度 — 用户显式意图是唯一开关, AI 与行为只做推荐输入)。

## 5. 数据流

```
quality_rejection_log ──┐
hotspots (avg + 域命中) ─┼→ build_cadence_overrides (三乘子) → get_schedulable due 计算
settings.kv 关注域 ──────┘
                                    ┌─ 手动/每日 → advisor (LLM) → 推荐 chips → 用户采纳 → kv 更新
interest_signals + 域分布 ──────────┘
```

## 6. 实施任务 (SDD)

- **T1 信号层**: hotspot_repo.get_recent_quality_stats 扩展返回每源 {avg, count, hit_ratio(需传入关注域)}; 新 rejection 聚合查询 (quality_rejection_repo 或 hotspot_repo 内, 近 50 次尝试口径 = 入库 count + 拒收 count)。测试先行。
- **T2 乘子层**: rejection_cadence_multiplier / interest_cadence_multiplier 纯函数 + build_cadence_overrides 复合改造 + 常量区。测试: 三乘子矩阵/夹取/样本不足/零命中×高质量豁免。
- **T3 advisor**: interest_domain_advisor 服务 + GET /api/interest/domains/recommendations + PUT 采纳 (走既有 settings PATCH 或专用端点) + PracticeDomainsCard 推荐区。feature gate: interest_engine 开启时可用。测试: 枚举校验/解析失败兜底/缓存/采纳落 kv。
- **T4 收口**: 全量回归 + DEV_LOG + 计划落账。

## 7. 边界与非目标

- 不改 13 collector 抓取本体; 不改 gate 扣分权重 (统一权重表另行立项)。
- M_i 不用行为分直接驱动 (显式意图唯一开关); advisor 推荐不自动生效。
- 拒收率口径: quality_rejection_log 有 source 维则直接聚合; 无则按 url 前缀归并 (T1 实现时定, 汇报说明)。
