# 设计：首页四阅读模式重定义 — 全量/精选/深度/告警 (four-modes-redefine)

- 日期: 2026-09-27
- 状态: 已批准（owner 裁决 2026-09-27: 四按钮语义重定义 + 确认分节设计; 判定规则细节/数据流/前端交互逐节过审）
- 关联:
  - `backend/services/alert_engine.py`（既有告警引擎, 本设计扩展其规则集思想但资讯域判定住新服务）
  - `backend/services/interest_engine_service.py`（精选信号源: boost_map）
  - `backend/collectors/quality_hook.py`（语义门禁 fail-open 同构先例, DEV-0235）
  - `docs/superpowers/specs/2026-09-18-pipeline-llm-pi-provider-design.md`（pi LLM 漏斗先例）
- 批次: P1 告警落地 / P2 精选功能（独立交付独立回归）

## 1. 背景与现状实测

首页四阅读模式（`SentinelHomePage.tsx` `ReadMode = 'brief' | 'scan' | 'deep' | 'alert'`）当前是**纯前端模式切换**——同一份快讯列表换渲染分支, 无任何后端语义差异:

- 「简报」= 头条叙事 + 次级 + 快讯流
- 「扫描」/「深度」= 无独立渲染分支（与 brief 同列表）
- 「告警」= **假告警**: 取快讯池中 security 类评分最高的一条展示（`alertItem` useMemo）, 无后端判定

后端有完整告警体系但空转: `alert_engine` 仅 2 条规则（`tech_stack_cve`/`critical_cve`, 判定对象为 security_entities/knowledge_items, 非资讯条目域）, `alert_events` 表 0 行, 与首页零接线。`/api/alerts/v2` 端点齐备（列表/未读数/已读/解决）。

owner 裁决四模式语义重定义:

| 按钮 | 新语义 | 数据源 | 判定 |
|---|---|---|---|
| 全量（原简报） | 当轮收录全部资讯, 时间倒序 | hotspots 现有查询 | 无 |
| 精选（新功能） | 从全量挑选值得细看的资讯 | hotspots + 精选评分 | 多信号合成 |
| 深度（保留） | 需要慢慢精读的资讯 | hotspots 深读标记 | 长文/高密度判定 + 用户自选 |
| 告警（收窄） | **需要用户执行动作**的落地资讯 | alert_events | 4 规则筛 + pi 复核 |

摸底数据（2026-09-27 生产库）: 7d score 均值 77.7/最大 82（区分度不足, 精选必须叠加其他信号）; 收藏 9 条（FreeBuf 4 等, 个性化信号可用）; 严格词筛候选每轮 ~0.5 条（LLM 复核成本可忽略）; 校对室刷屏已根治（DEV-0235, F4 预去重 7d 窗口修复）。

## 2. P1 告警落地 — "需要用户执行动作的资讯"

### 2.1 判定漏斗

```
每轮采集 post-ingest (_news_alert_tick, 与 _auto_intake_tick 同款模式)
  → 窗口内新条目 (fetched_at >= now-40min; 首轮 7d 回看)
  → 4 组词表筛 (title+summary; 每轮候选预计 0~3 条)
  → 去重闸 (hotspot_id 已在 alert_events.item_id → 跳过)
  → pi LLM 复核 (单次 generate, 合并候选, verdict JSON 数组)
  → severity 映射 + max_per_run=5 冷却 → INSERT alert_events
  → SSE publish news_alert 事件
```

### 2.2 四规则与词表（v1, 配置存 alert_rule_definitions.config）

**R1 `critical_vuln` 需打补丁/排查的漏洞** — severity=critical
- 强信号: `在野利用` / `exploited in the wild` / `0day` / `零日` / `PoC` / `概念验证` / `紧急补丁` / `out-of-band`
- CVSS 通道: 标题/摘要含 CVE 编号且（security_entities CVSS ≥ 9.0 或匹配 `满分`/`9.8`/`10.0`）— 复用既有 critical_cve 数据源
- 复核问题: 「是否为已被积极利用/影响面广、需要读者排查自家资产的漏洞？」

**R2 `major_security_event` 需资产排查/响应的安全事件** — severity=high
- 强信号: `遭攻击` / `hacked` / `breach` / `数据泄露` / `勒索攻击` / `供应链攻击` / `关基` / `critical infrastructure` / `APT` / `失陷`
- 门槛: 标题命中 ≥2 信号词, 或 1 信号词 + quality_score ≥ 75
- 复核问题: 「是否需要读者对自家资产做排查/响应（而非纯知情）？」

**R3 `major_ai_security_event` AI 资产需要行动的事件** — severity=high
- 强信号: `AI黑客` / `deepfake` / `深度伪造` / `提示注入` / `prompt injection` / `模型投毒` / `AI 漏洞` / `LLM 漏洞` / `MCP 漏洞` / `越狱`+`大规模`
- 前置限定: title/summary 同时命中 AI 语境词（`AI`/`LLM`/`大模型`/`GPT`/`Claude`/`agent`）+ 安全事件词
- 复核问题: 「AI 资产（模型/MCP/Agent 基建）是否需要行动（升级/排查/配置变更）？」

**R4 `must_know_regulatory` 监管/政策限时执行** — severity=medium
- 强信号: `紧急通报` / `公安部` / `CISA`+`advisory` / `报送` / `等保` + 时限词
- 复核问题: 「是否存在读者需要限时完成的合规动作？」
- 注: 原"其他需关注资讯"兜底语义删除——收窄为纯合规动作类, 纯知情类由 LLM 复核过滤（这是与初版方案的最大语义差, owner 2026-09-27 裁决）

### 2.3 LLM 复核协议

- 候选去重后**合并单次调用**: prompt 输出 `[{id, execute: bool, action_hint: "patch|investigate|monitor|respond", urgency: "now|today|this_week", reason}]`
- 走 ai_hub `generate(task="news_alert_review")` — pi 主力通道 + 既有 fallback 链
- prompt 模板入 `ai_hub/prompts.py`（`_NEWS_ALERT_REVIEW_PROMPT`, 与 `_SEMANTIC_VERDICT_PROMPT` 同款式）
- **fail-open 规则**: LLM 失败/解析失败 → 词表命中 ≥2 强信号的条目直接放行为告警（宁多报不漏报）, 单信号条目丢弃
- action_hint/urgency 存入 alert_events.description 尾部（结构化 `【action:patch|urgency:now】` 标记）, 前端解析展示

### 2.4 去重与冷却

- 条目级: hotspot_id 唯一（查 alert_events.item_id）
- 事件级: 同 CVE 编号 7d 内不重复（复用 `_has_recent_alert`）
- 冷却: 每规则每轮 max 5 条（`config.max_per_run`）

### 2.5 数据契约（零 DDL for alert_events）

`alert_events` 13 列全部够用: rule_type=4 类规则名 / item_id=hotspot_id / source=CVE 编号或源名 / description=reason+摘要截断+action 标记 / status+read_at 既有生命周期。唯一 DDL: `alert_rule_definitions` INSERT 4 行（enabled=1）。

### 2.6 API（零新增端点）

`/api/alerts/v2` 既有端点直接消费; `list_alerts` 加可选 `rule_type` 查询参数（一行）。

## 3. P2 精选功能 — 多信号合成挑选

### 3.1 pick_score 合成（纯规则, 无 LLM）

```
pick_score = quality_score                          (基线 0-100)
           + interest_boost × 10                    (interest_engine 既有 boost_map, 关注域命中)
           + 10 × is_from_favored_source            (favorites GROUP BY source ≥2 篇的源)
           + 时效衰减 (24h 内满权重; 24h~7d 线性衰减至 0)
```

精选线: 全量按 pick_score 排序取 Top-N, N=30/天（settings `quality.pick_top_n` 可调）。

### 3.2 落库

`hotspots` 新迁移（128, 编号以实施时最大号+1）加 `pick_score REAL` 列（可空）。`pick_service.py` 每轮 post-ingest 对窗口内新条目计算并落列（`UPDATE ... SET pick_score`）；Top-N 内打 `pick_score` 高分即选中（视图按列排序, 无需布尔标记）。favorites 变化时无需重算（下一轮自然生效, 个性化信号容忍 30min 延迟）。

### 3.3 触发挂点

post-ingest 链追加 `_pick_score_tick()`（与 _news_alert_tick 并列, 全 try-except）。

## 4. 前端交互（SentinelHomePage）

- **按钮文案**: `简报`→`全量`, `扫描`→`精选`, `深度` 保留, `告警` 保留（`mode-alert-on` 样式类不动）
- **告警视图**（mode==='alert'）: 替换快讯流区域 —
  - 未读徽标: 按钮红点 = `/api/alerts/v2/unread-count`（rule_type IN 4 类, 不混 CodeGarden 项目告警）; SSE `news_alert` 到达即刷新
  - 4 分类 tab: 漏洞/安全事件/AI 安全事件/合规时限 + 全部
  - 列表项: severity 色条（critical 红/high 橙/medium 黄）+ 时间 + 标题 + 来源 + LLM reason
  - 展开卡: 摘要 + action_hint 徽章（`打补丁`/`排查`/`关注`/`响应`）+ urgency + 操作（进入深读/查看原文/收藏, 复用 alert-detail 结构）
  - 列表头: 全部已读 / 解决; 空态: `当前无可执行告警 — 系统每轮采集后自动扫描`
  - 旧"高危"单条假告警区块撤除
- **精选视图**（mode==='scan'）: 现有列表结构按 pick_score DESC 排序 + `精选`徽章 + pick_score 展示; 空态: 首轮未跑 pick 时回退 quality_score 排序
- **全量视图**（mode==='brief'）: 现状快讯流原样
- **深度视图**（mode==='deep'）: 列表 = 深读标记条目 + 自动候选（summary≥200 字 或 标题命中 `分析|详解|深度|指南|research`）, 用户"加入深读"操作优先

## 5. 触发挂点与实时性（后端）

- post-ingest 链尾部追加: `await _news_alert_tick()` + `await _pick_score_tick()`（均全 try-except, 不阻塞采集链, 与 `_auto_intake_tick` 同款）
- SSE: alert_events 写入后 publish `news_alert` 事件（outbox 既有机制）; pick 重算后 publish `pick_refresh`
- 首轮启动: news_alert 做 7d 回看（冷启动有内容）; pick 对 7d 条目补算 pick_score

## 6. 测试策略

| 层 | 用例 |
|---|---|
| 词表筛 | 4 规则命中/不命中; R3 AI 语境限定（普通 AI 新闻不进）; R2 双信号门槛 |
| LLM 复核 | 正常 JSON / 解析失败 fail-open（≥2 信号放行, 单信号丢弃）/ LLM 全挂 |
| 去重冷却 | 同 hotspot 不重复 / 同 CVE 7d 去重 / max_per_run 截断 |
| tick | 窗口计算（40min）/ 首轮 7d 回看 / 空候选零开销 / 异常隔离 |
| pick_score | 合成公式各信号分量 / Top-N 截断 / 时效衰减边界 / favorites 源判定 |
| API | rule_type 过滤 / unread-count 仅 4 类规则 |
| 前端 | 4 视图渲染 / 告警 tab 分组 / 空态 / 未读徽标 / 已读解决操作 / 精选徽章 |

## 7. 非目标

- 不接外部推送（alert_channels/dispatcher 保留但不配 settings, 后续想接即通）
- 不做告警规则的用户自定义 UI（config 走 settings API 即可改）
- 不动 alert_engine 既有 2 条 CVE 规则（判定对象不同域）
- 不做精选的用户反馈闭环（收藏/阅读信号已有 interest_engine 消费, 不重复建设）
- 深度模式不做阅读进度追踪（保持现有收藏/深读跳转）

## 8. 文档同步义务（收口时）

- DEV_LOG [DEV-0236]（P1）/ [DEV-0237]（P2）
- 单权威 PRD: §3.4 设置页/资讯能力段补四模式语义（若该段存在）; SentinelShell 心跳条语义如涉及则同步
- generate_meta --check: 新增 news_alert_service / pick_service → services 数字 +2, 同批同步 ARCHITECTURE.md 与四 AGENTS.md + CLAUDE.md

## 9. 自审记录

- 占位符扫描: 无 TBD; R1 CVSS 通道复用既有 critical_cve 数据源, 迁移编号写明"以实施时最大号+1 为准"
- 内部一致性: 四模式语义矩阵（§1）与规则细节（§2）/精选合成（§3）/前端交互（§4）对齐; alert_events 零 DDL 与 §2.5 契约一致
- 范围: P1/P2 拆分明确, 单期可一份实施计划承载
- 歧义消除: "需要用户执行"的操作化定义 = action_hint 四枚举; 精选"N=30/天"可配置; fail-open 的"强信号"= 词表命中 ≥2
