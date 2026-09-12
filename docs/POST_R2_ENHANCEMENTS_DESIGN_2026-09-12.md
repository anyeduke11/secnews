# POST-R2 收尾设计包 — 未实现项与增强项

- 日期: 2026-09-12; 状态: **待裁决** (设计先行, 未动代码)
- 上游: DEV-0184/0185 收尾报告的未实现 + 增强清单; 数据来源为 Mimosa 封存扫描 (scanId `scan-2026-09-12T07-51-35.981Z-b3f23646372d`, seal `sha256:07d5b8…`) 与生产三库只读核查
- 结论先行: 6 项中 **4 项建议做** (T1 triage / T3 重校 / T5 恢复 scrub / T6 RUNBOOK), 1 项等窗口, 1 项建议记录不动 (ai/tech 桶维持现状)

## 0. 总览

| # | 事项 | 优先级 | 工作量 | 需裁决 |
|---|---|---|---|---|
| T1 | Mimosa 270 finding triage 流水线 | P1 | 0.5 天复核 + 1~2 天修复 | 裁决①② |
| T2 | hotspots 死列 DROP (migration 114) | P2 | 0.5 天 | 裁决③ |
| T3 | 信号权重重校脚本 + 触发规则 | P1 | 0.5 天 (等数据) | 无 (规则认可即可) |
| T4 | ai/tech 桶合并口径 | P2 | A=0 / B=1 天 | 裁决④ |
| T5 | 恢复链路 legacy-bid scrub | P1 | 0.5 天 | 裁决⑤ |
| T6 | 漂移阈值并入周审计 RUNBOOK | P1 | 0.25 天 | 无 |

---

## T1. Mimosa triage 流水线 (P1)

### 事实 (封存扫描透视)

| 归属 | 数量 | 构成 | 性质 |
|---|---|---|---|
| vendor (runtime/upstreams dsh/pi) | 147 (54%) | other 92 / cmd-inject 28 / credential 18 / code-inject 5 | **第三方上游源码**, 只读 clone 入仓 (gitignore 隔离), 非本仓维护面 |
| scripts (运维) | 66 | sql 26 / random 26 / ssrf 9 | 一次性工具, 多为多行 SQL 字符串启发式 |
| scripts (chaostest/loadtest) | 18 | path-traversal 12 / ssrf 5 | 故障注入/压测工具, 故意写危险操作 |
| **backend (生产代码)** | **33** | **sql 10 / ssrf 10 / random 8 / 其他 5** | **唯一需要逐条认真 triage 的面** |
| other | 6 | path-traversal 3 / ssrf 3 | 需归类 |

唯一已实锤的修复项: `scripts/spike_gateway_s1_s3.py:77` 硬编码凭据 (spike 脚本按 scripts/AGENTS.md "跑通后必须删除" 约定本应已删)。

### 设计

三层漏斗, 270 → ~33 生产面 → 少量真修复:

- **L0 scope 豁免 (规则化, 一笔处置)**: `runtime/upstreams/**` 与 `scripts/chaostest/**`、`scripts/loadtest/**` 整体豁免 — 前者是第三方上游 (升级时随上游走, 不改一行), 后者是故障注入工具的危险操作是其功能本身。台账记录豁免边界, 不逐条复核。
- **L1 批类复核 (backend 33 条)**:
  - B1 ssrf ×10: 逐条核对出站点是否已走 `backend/utils/url_safety.py` 中央防护 (`validate_url` / `safe_aiohttp_connector` / `safe_urllib_request`) — 已走 = 豁免 (误报), 未走 = 修复 (接入中央 helper)
  - B2 sql ×10: 逐条验证参数化 (占位符 + 绑定参数) — repo 层全参数化, 预期 9/10 为多行 SQL 字符串误报; 真拼接 = 修复
  - B3 random/path/other ×13: random 核对用途 (ULID/幂等键非加密用途 = 豁免); path-traversal 核对输入来源 (固定配置路径 = 豁免)
- **L2 修复批**: L1 判 A 类 (真问题) 的集中修复 + 修复后复跑 scanner 确认 anchor 消失 (实现与验证分离)
- **台账**: `docs/security/MIMOSA_TRIAGE_LEDGER.md` — 每条: anchor sha256 / class / 处置 (A 修复 commit / B 误报依据 / C 接受风险) / 复核日期。机读 JSON 同目录。引用本次 scanId+seal, 下次扫描按 anchor 增量对账。

### 验收

台账覆盖 270/270; backend 33 条逐条有处置结论; spike 脚本凭据项关闭; 复扫新增 findings = 0 未处置。

### 裁决点

- ① vendor + chaostest/loadtest 整体豁免边界是否认可 (影响 165 条的处置)
- ② `scripts/spike_gateway_s1_s3.py` 删除 (推荐, 符合 debug/spike 约定) vs 改 env 读取保留

---

## T2. hotspots 死列 DROP — migration 114 (P2, 销毁型)

### 事实 (生产只读核查 2026-09-12)

- SQLite 3.53.3, 支持 DROP COLUMN (≥3.35)
- `hotspots.region` 被 **`idx_hotspot_region` 索引**引用 → 直接 DROP 会失败, 必须先 `DROP INDEX`
- `hotspots.bid_status` 无索引引用, 可直接 DROP
- `weekly_reports.bid_summary` 在 **warm 库** (7 行历史数据, 列存在) — 有真实历史值, 销毁收益为零, **建议保留** (维持 DEV-0185 注释口径)
- 注意: 单文件连接 PRAGMA 检查会漏 ATTACH 库的表 (weekly_reports 即如此), 迁移演练必须走 `get_connection()` (含 ATTACH) 全链

### 设计

`backend/repository/migrations/114_drop_dead_columns.sql`:

```sql
-- 前置: SQLite ≥3.35; idx_hotspot_region 引用 region, 须先删索引
DROP INDEX IF EXISTS idx_hotspot_region;
ALTER TABLE hotspots DROP COLUMN region;
ALTER TABLE hotspots DROP COLUMN bid_status;
-- weekly_reports.bid_summary (warm 库) 保留: 有历史数据, 不销毁
```

- 前置: 改库前手动 full backup + sha256 manifest (沿用 T02 备份演练链路, 改库前备份是硬规则)
- 演练: 生产三库副本 `init_db()` 全链通过 (含 114) → 再上生产 (同 DEV-0183 hotfix 验证法)
- 风险: DROP COLUMN 不可回滚, 依赖备份链; 两列代码 0 读写 (DEV-0180 已核), 回滚需求≈0

### 验收

生产 `PRAGMA table_info(hotspots)` 无两列; 全量门禁绿; /api/hotspots 正常; 备份 manifest 落档。

### 裁决点

- ③ 是否执行 (纯清理, 不做也不影响任何功能; 做 = 消耗一次销毁型迁移预算)

---

## T3. 信号权重重校脚本 (P1, 触发条件未到)

### 设计

`scripts/audit_interest_recalibration.py` (audit_ 前缀, 严格只读, 零 SQL — 复用 hotspot_repo `interest_audit_*` + 纯函数):

- 输入: interest_signals 30d 按 type 分布 / distinct items / 域归因分布; favorites vs deep_reads 存量比
- 内置判定规则 (代码化, 不靠人记):
  - R1 若 deep_read:favorite 的**实际信号比**偏离校准锚 (14:9) 超 30% → 建议按新比重定 2.0:3.0 锚点
  - R2 若 view 信号占总信号 >60% 且 view 的 distinct-item/总信号比 <0.5 (大量重复 view) → 建议 view 权重 0.5→0.3
  - R3 若满 14 天后 W30 稳定 <10 → 建议 C=30→15 (加速 β 收敛); 若 W30≥30 → 维持
- 输出: 人类可读建议 + **可直接粘贴的常数 diff 块** (指向 `interest_engine_service.py` 常数区)
- 设计决策: 常数**留在代码** (单一真相源), 脚本只建议不改配置 — 单用户不值得引入热配置面; 改动走 commit 可追溯
- 触发 (写进 T6 RUNBOOK): 信号 ≥100 条或 R1 上线满 14 天, 以先到者为准

### 验收

空库 dry-run 跑通 (输出"不满足任何重校条件"); 合成分布单测 3 条规则各覆盖正反例。

---

## T4. ai/tech 桶合并口径 (P2, 产品裁决)

### 事实

- Phase 35 有意合并: `category="ai"` 查询 SQL 层为 `IN ('ai','tech')`; balanced 桶无独立 tech 桶; UI 分类栏"科技/AI"合并展示
- 影响: "all" Feed 中 tech 条目经 AI 桶进入、与 AI 共享配额; `category=tech` 筛选仍可用; 实践域打标与兴趣乘子不受影响 (按 title 归因)

### 选项

| 方案 | 内容 | 代价 | 影响 |
|---|---|---|---|
| A 维持 + ADR 记录 (推荐) | 现行为即设计, 落 docs/decisions/ADR | 0 | 无 |
| B tech 独立桶 | balanced 桶 +1, 前端分类栏拆开 | 1 天 | tech 曝光独立但稀释他类页内配额 |
| C ai 桶内 tech 子配额 | 桶内按子类限比 | 复杂度最高 | 不推荐 |

### 推荐

A — tech(IT 资讯) 对安全从业者属背景信息, 与 AI 合并曝光符合内容定位; Phase 35 已是裁决过的现状, 无回归即无债。若你希望 tech 独立曝光再升 B。

### 裁决点

- ④ A 维持 (推荐) / B 独立桶 (排独立批次)

---

## T5. 恢复链路 legacy-bid scrub (P1, 鲁棒性)

### 事实

- `Category.from_str("bid")` 与 HotspotItem pydantic 校验现拒收 bid (DEV-0185)
- 恢复含 bid 行的历史备份后, 任何触及 bid 行的列表查询会在 repo `_row_to_item` 处 ValidationError → 500 (恢复副本不可用)
- `weekly_reports.bid_summary` (warm) 有列有历史值, 无碍

### 设计

`scripts/t02_restore_drill.py` 恢复流程末尾追加 scrub 步骤 (幂等):

```
① restore 完成后: DELETE FROM hotspots WHERE category='bid' (跨表: 同步删 warm.content_fingerprints 关联行, 复用 migration 112 语义)
② 记录 scrub 计数到恢复 manifest
③ bid 行不存在 = no-op (对 09-12 之后的新备份零影响)
```

- 备份本体**不动** (备份是历史真相, scrub 只作用于恢复出的工作副本)
- 对齐 owner 先例 (migration 112 "不需要有意保留, 直接清理"), 推荐 DELETE 而非归档隔离表

### 验收

构造含 bid 行的备份 → restore+scrub → /api/hotspots、favorites、深读全链 200; 演练脚本输出 scrub 计数。

### 裁决点

- ⑤ scrub 动作: DELETE (推荐) vs 移入隔离表 `legacy_bid_hotspots`

---

## T6. 漂移阈值 + 审计周期化 RUNBOOK (P1, 流程)

### 设计

`docs/RUNBOOK.md` 追加"周期审计"章节, 每周一执行:

| 步骤 | 命令 | 判据 |
|---|---|---|
| 1. 词表回归 | `python scripts/check_practice_domain_lexicon.py --check` | 100% 过, 否则先修词表 |
| 2. 兴趣引擎审计 | `python scripts/audit_interest_hit_rate.py --json > reports/interest_audit_<date>.json` | 人工浏览漂移/覆盖率 |
| 3. 重校触发判断 | 看步骤 2 输出的 W30 饱和度 | 信号 ≥100 或满 14 天 → 跑 T3 脚本 |
| 4. (月度) 无偏人评 | `python scripts/audit_practice_domain_sample.py --sample 40` → 人工标注 → `--grade` | 准确率 <0.8 → 修词表 |

- 漂移阈值 (DRIFT_TOP_N=3 / OVERLAP_MIN=2) 已是模块常数, 与 T3 同窗口调整; 判据变更走 commit
- 不做调度自动化: 审计是"人看"的动作, 自动跑只会生成无人读的 JSON; 单用户人工节奏足够

### 验收

RUNBOOK 章节落地; 首个周一按单执行一遍并留档。

---

## 7. 建议批次顺序

1. **本周内**: T6 (0.25d) + T5 (0.5d) — 都是小而闭环
2. **待裁决后**: T1 L0/L1 (0.5d) → spike 凭据修复 → T1 L2 修复批 (视 triage 结果)
3. **任意窗口**: T2 (0.5d, 若裁决执行) · T4-A (落 ADR 一段话)
4. **等数据**: T3 脚本可先写 (0.5d), 触发判断交给 RUNBOOK

## 8. 裁决清单 (一次回复即可)

| # | 问题 | 推荐 |
|---|---|---|
| ① | vendor + 故障注入工具整体豁免边界 | 认可 |
| ② | spike_gateway_s1_s3.py 处置 | 删除 |
| ③ | migration 114 死列 DROP 是否执行 | 执行 (P2 顺位) |
| ④ | ai/tech 桶 | A 维持 + ADR |
| ⑤ | 恢复 scrub 动作 | DELETE |
