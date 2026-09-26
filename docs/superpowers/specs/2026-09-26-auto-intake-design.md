# 自动入管规则引擎 — 设计稿 (2026-09-26)

## 1. 目标与第一性原理

知识管线的入口应与采集解耦但不停摆: 让"高价值 + 命中关注"的资讯**自动**进入
raw→refine→...→publish 加工链, 用户从"手动收藏才入管"变为"消费产出 + 抽样纠偏"。

入管判据 (owner 裁决 B 方案): 质量分 ≥ 阈值 **且** 命中关注域 (可选) **且** 每日限量。
收藏通道保持不变 (显式意图永远优先, 收藏的条目不受每日上限约束)。

## 2. 实测依据 (2026-09-26)

- 近 7 天 hotspot 4989 条; quality_score≥85 占 66% (~469/天) → 光质量阈值不缩量
- 抽样 domain 命中率 93% → 域过滤也几乎不缩量 → **限流核心 = 每日上限**
- T1 防重/防风暴天然成立: url 幂等 + 5min debounce + simhash 判重 + 50/轮
- hotspots 无 practice_domain 列 → 域命中用 auto_classifier 规则现算 (无 LLM)

## 3. 规则引擎

### 3.1 配置 (settings kv `knowledge.auto_intake.*`)

| 键 | 默认 | 说明 |
|---|---|---|
| enabled | false | 总开关 (gate 化随消费点登记原则; 首版用 kv 不新增 feature gate) |
| min_quality_score | 85 | 入管质量下限 (hotspots.quality_score) |
| daily_limit | 20 | 每自然日入管上限 (防风暴主闸) |
| require_domain_hit | true | 是否要求命中关注域 (interest.practice_domains) |

API: 沿用 `api/settings.py` 先例, GET `/api/settings/auto-intake` + PATCH (校验 + audit)。

### 3.2 评估流程 (挂 collect_all_job 尾部 post-ingest, 30min 一轮)

```
collect_all_job 尾部 → auto_intake_job():
  1. enabled=false → return
  2. 今日已入管数 ≥ daily_limit → return (计数器 = knowledge_items
     WHERE source='secnews_auto' AND ingested_at ≥ 今日 0 点)
  3. 候选 = hotspots WHERE ingested_at > 上次游标 (kv 游标防重复扫描)
     AND quality_score ≥ min_quality_score AND summary 非空
     ORDER BY quality_score DESC LIMIT (daily_limit - 已入管)
  4. 逐条: require_domain_hit 时 batch_classify(title+summary) 命中
     interest.practice_domains 才入管; 未命中跳过 (不入管也不重扫——游标推进)
  5. 入管 = 复用 promote_favorite_to_knowledge 扩展版:
     +content(summary), +category, +source='secnews_auto' (区分收藏通道)
     幂等 by url; md 先写
  6. 游标推进到本轮 max(ingested_at); metrics: evaluated/intake/skipped
```

### 3.3 与既有机制的关系

- **收藏通道**: 不变, 不占 daily_limit (source='secnews' vs 'secnews_auto' 区分)
- **T1 判重**: 自动入管的低重复风险条目若撞车, simhash 判重落 deduped, 无害
- **密度乘子 M_i**: 自动入管条目同样经管线, quality_score 随管线评分更新,
  与采集密度自适应天然衔接
- **每日上限与管线容量**: T1 50/轮×60s 远大于 20/天, 无挤压

## 4. 可观测性

- 入管数/评估数/跳过数 计入 metrics (与 t1_deduped 同族)
- 漏斗页 (PipelineView) 吞吐视图自然可见自动入管流量 (kl:refine+)
- auto_intake job 日志: 每轮 candidates/intaken/limit_reached 一行

## 5. 实施任务

- **T1** promote 扩展 + auto_intake service (评估+游标+上限) + 配置读写 + 测试
- **T2** collect_all_job 挂载 + settings API GET/PATCH + 前端设置卡 (采集分区:
  自动入管开关/阈值/上限/今日已入管数) + 测试
- **T3** 收口: 全量回归 + DEV-0231 + 计划落账

## 6. 非目标

- 不做 LLM 判断入管 (纯规则; LLM 判断成本与延迟不划算, 规则+每日上限已够)
- 不动收藏 API 行为; 不新增 feature gate (kv enabled 即可, 观察期后再议 gate 化)
- 不回填历史 hotspot (游标从部署时刻起算)
