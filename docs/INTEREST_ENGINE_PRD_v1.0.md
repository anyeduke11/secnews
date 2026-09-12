# Interest Engine PRD v1.0 — 内容门禁 × 推荐系统

- 日期：2026-09-12；状态：**已裁决立项（R1 开发中）**；开发目标见 [`INTEREST_ENGINE_DEV_PLAN.md`](INTEREST_ENGINE_DEV_PLAN.md)
- 上游：`WORKBENCH_FOCUS_PRD_v1.0.md` P2 行为反馈闭环的展开；上游裁决（2026-09-12）三项：①信号权重从已有数据校准 ②内容门禁与质量门禁分离、新建独立 gate ③温和发现（未勾选 E=0.15）、逐步收敛（行为分随证据量渐进接管）
- 路由/接口一致性仍以 [`v0.8.5/V0.8.5_PLAN.md`](v0.8.5/V0.8.5_PLAN.md) 为唯一权威 spec

## 0. 定位与红线

- **单用户兴趣引擎**：显式勾选（冷启动）+ 隐式行为（演化）→ 域权重 → 排序融合。不做协同过滤/多用户/召回模型（召回沿用 FTS+词表；语义召回另立方案）。
- **四层门禁**：L0 质量（11 道，不动；bid_recency 门已随标讯剔除移除）→ L1/L2 噪音（info_filter，不动）→ **L3 相关性（本引擎，降权不删）**。
- 红线：热路径零 LLM（ai_hub 链不动）；无新一级入口；独立 feature gate `interest_engine`（内容门禁与质量门禁分离，gate 断路器默认开）。

## 1. 信号与权重（裁决①：从已有数据校准）

生产库校准事实（2026-09-12 只读）：favorites=9、deep_reads(hotspot)=14、reading_states/attention_events=0、近 30 天资讯 11388 条。

| 信号 | 触发点 | 权重 | 依据 |
|---|---|---|---|
| view | Feed 卡片点外链 | 0.5 | 锚定（零存量） |
| read | 打开深读入口 | 1.0 | 锚定（零存量） |
| dwell>30s | 深读停留 | 1.5 | 锚定（零存量） |
| deep_read | 深读完成 | **2.0** | **数据推导：3.0×(9/14)≈1.93** |
| favorite | 收藏 | 3.0 | 锚定 |

- view/read/dwell 锚定值：R1 上线两周后用真实分布重校（DEV_PLAN 收尾判据）。
- 去重：同 item 同 type 30 分钟窗口合并；域归因在写入时完成（`classify_practice_domain(title)`），item 后续删除不影响聚合。

## 2. 权重模型（裁决③：温和发现、逐步收敛）

```
B(d)  = Σ w·exp(-ln2·age_days/14)          # 行为分, 14 天半衰
B'(d) = B(d)/max_d B(d)                     # 归一化 [0,1]
E(d)  = 勾选 1.0 / 未勾 0.15               # 温和发现: 未勾不给 0
β_eff = 0.4 · min(1, W30/C),  C=30          # 逐步收敛: 行为证据满 C 才全额接管
S(d)  = 0.6·E(d) + β_eff·B'(d)
排序乘子 m(d) = 0.7 + 0.6·S(d)              # ∈ [0.79, 1.30]
```

- 无勾选且无信号 → m 恒 1.0，Feed 行为与现状一致（兼容断言）。
- β 随 30 天内信号总量 W30 渐进升至 0.4：冷启动由显式勾选主导，行为积累后逐步接管并收敛（C=30 冷启动常数，两周后重校）。

## 3. 数据模型（migration 113）

不复用 attention_events（FK 绑 knowledge_items + 30d 生命周期属知识注意力）：`interest_signals`（item_id 无 FK / domain / signal_type / weight / created_at，保留 90 天，purge 挂现有 maintenance job）+ `interest_domain_weights`（domain PK / explicit_selected / behavioral_score / blended_score / last_event_at / updated_at）。聚合在读时计算（5min TTL），不新增调度 job。

## 4. API（gate `interest_engine` 条件注册）

| 端点 | 语义 |
|---|---|
| `POST /api/interest/signals` `{item_id, signal_type, dwell_seconds?}` | 201 记录；无域条目 202 accepted_no_domain；域归因服务端做 |
| `GET /api/interest/weights` | 10 域三层分 + 各域近 30d 事件数（权重条数据源） |
| `POST /api/interest/weights/reset` | 清行为信号（显式勾选保留）+ audit_log |

排序融合：`/api/hotspots` gate 开启时由引擎提供 `{domain: m(d)}` 乘子表，页内按 (m desc, 原序) 稳定重排（游标仍取重排前时序，沿用既有保护）；gate 关闭时保持显式二值分区现状。

## 5. 前端

- `lib/interest.ts` 统一 `trackInterest()`（sendBeacon 优先，fetch keepalive 兜底）；接入点：卡片外链（view）/ DeepReadChip（read）/ StarButton 收藏（favorite）/ 深读停留（dwell）。
- 设置页"我的方向"卡升级：勾选 + 域权重条（行为贡献可视化）+ 重置按钮；i18n 双语。
- 可解释性：徽标与权重条均可回溯到信号明细（R2："为何推荐" tooltip）。

## 6. 分期

- **R1**：migration 113 + InterestEngineService + 3 端点 + 排序融合 + 前端埋点与权重条 + gate 登记 + 测试。
- **R2**：漂移检测（行为 top3 vs 勾选重合 <2 提示，绝不自动改画像）、摘要按 composite 选 top-N、周审计附命中率代理指标。
- **R3**：语义召回（另立方案）。

## 7. 非目标与验收

非目标：协同过滤、多用户、自动改画像、LLM 热路径。验收：全量 pytest/vitest/tsc/build/meta --check 全绿；无勾选无信号时 Feed 与现状逐序一致；reset 后行为分归零；gate 关闭时引擎端点 404 且排序回退显式二值；实现与验证分离（独立审计）。
