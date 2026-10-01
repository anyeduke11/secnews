# 设计：拒收日志人话化 + 迁设置运维区 (rejection-explain)

- 日期: 2026-10-01
- 状态: 已批准（owner 裁决 2026-10-01: 拒收日志整体迁设置 / 词典+LLM 逐条解释 / 入库后批量生成; 方案 A post-ingest tick 挂点）
- 关联:
  - `docs/superpowers/specs/2026-09-27-four-modes-redefine-design.md`（post-ingest tick 挂点先例: `_news_alert_tick`/`_pick_score_tick`）
  - `backend/collectors/quality_hook.py`（`_write_quality_rejection` 拒收唯一入口）
  - `frontend/src/components/QualityRejectionPage.tsx`（现状: /quality?tab=rejection 表格, reason 列裸 flag 列表）
  - DEV-0235（校对室刷屏根治 — 拒收日志恢复审计价值后的体验延续）
- 起因: owner 在校对室选中 reason td（`['category_mismatch', 'title_summary_inconsistent', 'content_hash_duplicate']`）— 裸 flag 对非开发者不可读; 裁决「原因转成用户可读的解释，日志放在设置里」。

## 1. 现状实测 (2026-10-01)

- reason 列渲染: `QualityRejectionPage.tsx` L118-122 直接输出 `row.reason` 字符串（flag 列表 str 形式）
- 拒因 flag 全集 (7d 生产库 distinct): `content_hash_duplicate` / `category_mismatch` / `title_summary_inconsistent` / `empty_summary` / `author_unknown` / `title_spam_words` / `noise_title` / `empty_title` / `url_duplicate` / `similar_title_duplicate` — 组合 10+ 种
- 拒收量: 百级/天 (DEV-0235 根治去重噪声后为真实拒收); 历史积压 ~5000 行
- 设置页 ops 区现装配: DatabaseMaintenance / ExportActionsCard / DshControlCard
- /quality 页: TABS = 校对总览 + 拒绝样本; `/quality/rejection` 旧深链 redirect 兼容 (DEV-0183 A5)

## 2. 总体架构

```
拒收入库 (quality_hook._write_quality_rejection, explain=NULL)   ← 不动
      ↓ 每轮采集 post-ingest 尾部
_rejection_explain_tick (新, 第 3 个同款 tick)
      ↓
查 explain IS NULL (LIMIT 200/轮) → 合并单次 pi 调用 → UPDATE explain
      
前端: 设置→运维→拒收日志卡
  reason 列 = explain (LLM 人话, 有则显) + 词典映射 flag 标签 (兜底, 恒显小字)
```

双层解释: **词典兜底 (零成本恒可用) + LLM 人话 (结合标题上下文, 延迟 ≤ 一轮)**。

## 3. 词典映射表 (前端常量)

`frontend/src/lib/rejectionReasons.ts`:

```ts
export const REJECTION_FLAG_LABELS: Record<string, string> = {
  content_hash_duplicate: '与已收录内容重复',
  url_duplicate: '链接已收录过',
  similar_title_duplicate: '标题与已有条目高度相似',
  category_mismatch: '内容与分类关键词不匹配',
  title_summary_inconsistent: '标题与摘要对不上',
  empty_summary: '摘要为空',
  empty_title: '标题为空',
  author_unknown: '作者无法验证',
  title_spam_words: '标题含营销/低质词',
  noise_title: '标题属噪音内容(备案/版权/招聘等)',
};
```

- 渲染规则: 从 reason 字符串提取 flag 数组（regex `([a-z_]+)` 提词 + 过滤非 flag 词如 `flags`/`=`/`[`/`]`）→ 逐条映射 → 未知 flag 原样显示
- 多 flag 组合: 全部映射列出, 首个 (主拒因) 加粗
- 词典是纯前端常量 — 不做用户自定义 (非目标)

## 4. LLM 批量解释 (后端)

### 4.1 挂点

`backend/scheduler/jobs/collect.py` post-ingest 链尾部追加 `await _rejection_explain_tick()`（`_pick_score_tick` 之后, 第 3 个同款异常隔离 tick）。

### 4.2 编排服务

`backend/services/rejection_explain_service.py`:

```python
def run_rejection_explain(batch_limit: int = 200) -> dict[str, int]:
    """post-ingest 入口: 为 explain IS NULL 的拒收行批量生成中文解释。

    全程不抛; 返回 {"explained": N}。
    """
    # 1. SELECT id, item_title, reason FROM quality_rejection_log
    #    WHERE explain IS NULL ORDER BY id DESC LIMIT batch_limit
    # 2. 空积压 → {"explained": 0} 零 LLM 调用
    # 3. prompt (ai_hub/prompts.py 新增 build_rejection_explain_prompt):
    #    输入 [{id, title≤100, flags}], 要求输出 JSON 数组
    #    [{id, explain: "一句中文, ≤60字, 说清为什么被拒"}]
    # 4. 单次 llm_service.generate(prompt, task="rejection_explain")
    # 5. 解析失败 / LLM 挂 → 返回 {"explained": 0} (explain 保持 NULL, 下轮重试)
    # 6. 逐行 UPDATE quality_rejection_log SET explain = ? WHERE id = ?
    #    (只更新解析结果中 id 匹配且 explain 非空的行)
```

### 4.3 成本护栏

- 每轮最多 200 行 × 1 次调用; 拒收高峰 (百级/天) 每轮一次调用即追平
- 历史积压 ~5000 行 ≈ 25 轮 (约 12h) 自然消化完, 无需回填脚本
- LLM 失败不写坏数据: explain 保持 NULL, 词典在前端兜底展示
- 防毒化: explain 生成后不重复生成 (IS NULL 过滤天然幂等)

## 5. 迁移与 API

- 迁移 130: `ALTER TABLE quality_rejection_log ADD COLUMN explain TEXT;`（可空; 编号以实施时最大号+1 为准, 当前 129）
- `/api/quality/rejection-log`: 响应**零改动** — service 层 `SELECT *` 自动带新列 (实施时核实 `query_rejection_log` 的列选择是 `SELECT *` 还是显式列清单, 若后者补 explain)
- 零新增端点

## 6. 设置页日志卡 (前端)

- 新组件 `frontend/src/components/settings/RejectionLogCard.tsx`:
  - 复用现 QualityRejectionPage 的数据拉取/筛选 (源/日期) / LayerTable 表格 / 分页结构
  - **reason 列双行渲染**: 首行 explain (LLM 人话, `--text-primary`); 次行词典映射 flag 标签小字 (`--text-muted`, 主拒因加粗)
  - 卡头: 「拒收日志」+ 副标题「采集质量门禁的拒收审计 · 每轮采集后自动生成解释」
- 装配: `SettingsPage.tsx` `case 'ops'` 追加 `<RejectionLogCard />`（运维组第 4 卡）

## 7. /quality 页收缩 + 重定向

- `QualityDashboardPage.tsx`: TABS 删 rejection 项 → 只剩 `校对总览`; 删 tab 切换中 rejection 分支与 `QualityRejectionPage` import
- 路由 (`routes/index.tsx`):
  - `/quality/rejection` redirect 改指向 `/settings?cat=ops`（QueryMergeRedirect 撤, 换 Navigate）
  - `/quality?tab=rejection` 由页面自身逻辑自然归位 overview (tab 参数不再识别 rejection)
- `QualityRejectionPage.tsx` 物理删除 (263 行) + 其测试文件删除; 断言迁移至 RejectionLogCard.test.tsx
- `ROUTE_REGISTRY.md` 同步: /quality/rejection 行改 redirect 目标
- nav4_shell 守卫: 核实 /quality 路由归属断言不受影响 (无路由删除, 仅 redirect 目标变更)

## 8. 测试策略

| 层 | 用例 |
|---|---|
| 词典 (前端) | 10 flag 全映射存在 / 未知 flag 原样 / reason 字符串提取 flag 数组 (含 `flags=['x']` 与裸 `['x','y']` 两种形态) / 多 flag 首项加粗 |
| explain tick (后端) | 空积压零 LLM 调用 / 批量生成回填 correct id / LLM 挂 → explain 保持 NULL 返回 0 / 解析垃圾 → 同左 / LIMIT 截断 / tick 异常隔离不阻塞采集链 |
| prompt | 含 id+title 截断+flags; 要求中文 ≤60 字 |
| API | rejection-log 响应含 explain 列 |
| 前端 | 日志卡 explain 双行渲染 / explain 空时词典兜底行 / 旧深链 redirect → /settings?cat=ops / quality 页无 rejection tab |
| 守卫 | nav4_shell 全绿 / tsc / vitest 全量 |

## 9. 非目标

- 不做拒收记录删除/重放操作
- 不改门禁判定逻辑 (拒因产生侧)
- 词典不做用户自定义
- 不做 explain 的手动重新生成按钮
- 其他日志 (采集/调度/告警运行日志) 不在本期 — 仅拒收日志

## 10. 文档同步义务 (收口时)

- DEV_LOG [DEV-0238]
- PRD: §2.4 或设置页能力段补一句 (拒收日志迁设置 + 人话解释)
- `generate_meta --check`: +1 service (rejection_explain_service) → 153 services, 同批同步五处文档
- ROUTE_REGISTRY.md (§7 已列)

## 11. 自审记录

- 占位符扫描: 无 TBD; 迁移编号 130 标注"以实施时最大号+1 为准"; §5 留一处"实施时核实 SELECT 形态"并给出两分支处理
- 内部一致性: 双层解释 (词典兜底+LLM) 在 §2/§3/§4/§6 一致; explain NULL 语义 (待生成/失败重试) 在 §4.2/§4.3/§6 一致; redirect 目标在 §7 与测试策略一致
- 范围: 单期单计划可承载 (前端词典+卡 / 后端 tick+迁移 / 页面收缩三块强相关一次交付)
- 歧义消除: "主拒因" = flag 数组首项; "一轮" = 采集周期 30min; explain 幂等 = IS NULL 过滤
