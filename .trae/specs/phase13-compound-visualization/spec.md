# Phase 13 — 复利可视化 + 4 模式 + 规划引导

> **版本**: v2.0 (Phase 13)
> **日期**: 2026-07-31
> **周期**: ~4 天
> **spec 路径**: `.trae/specs/phase13-compound-visualization/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.10.6 + B.8
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md` Phase 13
> **前置**: Phase 12 (T3/T4/T5 触发器 + 告警系统) ✅
> **Group 划分**: A(dashboard) → B(4-modes) → C(trigger-vis) → D(planning-panel) → E(scheduler) → F(tests)

---

## 1. 背景与目标

### 1.1 背景

Phase 10-12 完成了 5 阶段知识生命周期状态机的完整闭环（T1-T5）和告警系统。目前 knowledge 子系统已有：
- 完整的数据采集管道（Phase 11）
- 5 阶段 lifecycle 状态机 + 触发器（Phase 10 + 12）
- 告警规则引擎（Phase 12）

但用户侧缺乏**可视化反馈**：看不到知识的复利增长趋势、无法快速切换阅读模式、没有规划引导。Phase 13 解决"用户看得见、用得上"的问题。

### 1.2 目标

1. **复利仪表盘**：日/周/月趋势图 + top concepts 排名 + 断点告警（触发器中累计失败）
2. **4 种认知模式 UI**：简报（每日摘要）、快速扫描（分类列表）、深度阅读（全屏+侧栏）、告警（红色横幅+Inbox）
3. **触发器状态可视化**：knowledge_items 详情页 5 阶段进度条
4. **KnowledgePlanningPanel**：基于 reading_states + lifecycle 生成个性化规划动作
5. **planning_action_check job**：每 10 分钟检查一次，生成规划动作
6. **数据库迁移 049**：创建 `planning_actions` + `planning_action_log` 表

### 1.3 不在范围内

- ❌ 整理模式（Outbox）— Phase 17
- ❌ 复习模式（SM-2）— Phase 17
- ❌ chunks + attention heatmap — Phase 17
- ❌ 子系统联动（tech_stack_drift / CVE 同步）— Phase 14
- ❌ 清理 + 文档 — Phase 15
- ❌ Hybrid AI — Phase 16

---

## 2. 范围

### 2.1 必做

**复利仪表盘（Task A）**
- `frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx`
- 日/周/月趋势折线图（使用 recharts 或 echarts）
- Top concepts 排名（按 link 数或 score 排序）
- 断点告警（显示 T1-T4 触发器中累计失败数 + 死信量）
- 集成到 /knowledge/compound 路由

**简报模式 UI（Task B1）**
- `frontend/src/components/knowledge/BriefingMode.tsx`
- 每日首次打开：一句话摘要 + 3 篇关键文章 + 数据源状态
- 从 `knowledge_items` 取当天 `kl:publish` 的 items
- 数据源健康度显示（从 `source_stats` 或 `source_health` 取）

**快速扫描 UI（Task B2）**
- `frontend/src/components/knowledge/ScanMode.tsx`
- 即当前首页的增强版：分类 + 标签 + 时间筛选列表
- 复用现有 `HotspotGrid` 组件逻辑
- 支持 lifecycle 阶段筛选

**深度阅读 UI（Task B3）**
- `frontend/src/components/knowledge/DeepReadMode.tsx`
- 文章全屏阅读 + 右侧栏（推荐/笔记/影响/触发器状态）
- 右侧栏包含：触发器状态进度条、关联概念、相关推荐

**告警模式 UI（Task B4）**
- `frontend/src/components/knowledge/AlertMode.tsx`
- 红色横幅 + 告警中心 Inbox
- 复用 AlertCenter 组件
- 在导航栏显示未读告警数

**触发器状态可视化（Task C）**
- 在 knowledge_items 详情页显示 5 阶段进度条
- 每个阶段显示状态（已完成/当前/待进行）
- 进度条颜色：raw=gray, refine=blue, link=purple, structure=orange, publish=green

**KnowledgePlanningPanel（Task D）**
- `frontend/src/components/knowledge/KnowledgePlanningPanel.tsx`
- 基于 reading_states + lifecycle 状态生成个性化动作建议
- 动作类型：阅读、复习、关联、整理、发布
- 可作为 dashboard 顶部嵌入或在侧边栏展示

**planning_action_check job（Task E）**
- `backend/scheduler/jobs.py` 新增 `planning_action_check_job`
- `backend/scheduler/scheduler.py` 注册 job 36（IntervalTrigger, 600s）
- 扫描 `knowledge_items` 表，检查 lifecycle 状态 + reading_states
- 生成 `planning_actions` 记录

**测试（Task F）**
- 4 模式组件渲染测试
- 复利仪表盘渲染测试
- KnowledgePlanningPanel 渲染测试
- planning_action 数据库测试
- 总计 25+ 用例

### 2.2 明确不做

- ❌ 不实现整理模式（Phase 17）
- ❌ 不实现复习模式（Phase 17）
- ❌ 不实现 chunks 段落级引用（Phase 17）
- ❌ 不实现 attention heatmap（Phase 17）
- ❌ 不修改现有 collection_service 主流程
- ❌ 不修改 T1-T5 触发器实现
- ❌ 不修改告警引擎

---

## 3. 数据模型

### 3.1 新表 `planning_actions`（migration 049）

```sql
-- backend/repository/migrations/049_v2.0_planning_actions.sql
-- 目的: 规划动作表（KnowledgePlanningPanel 数据源）

CREATE TABLE IF NOT EXISTS planning_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL CHECK(action_type IN (
                        'read', 'review', 'link', 'refine', 'publish'
                    )),
    priority        INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),
    title           TEXT NOT NULL,
    description     TEXT,
    current_stage   TEXT,
    target_stage    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                        'pending', 'in_progress', 'completed', 'dismissed'
                    )),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    dismissed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_planning_actions_status ON planning_actions(status);
CREATE INDEX IF NOT EXISTS idx_planning_actions_item ON planning_actions(item_id);
CREATE INDEX IF NOT EXISTS idx_planning_actions_created ON planning_actions(created_at);
```

### 3.2 新表 `planning_action_log`（migration 049）

```sql
-- backend/repository/migrations/049_v2.0_planning_action_log.sql
-- 目的: 规划动作执行日志

CREATE TABLE IF NOT EXISTS planning_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER REFERENCES planning_actions(id),
    action_type     TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    event           TEXT NOT NULL CHECK(event IN (
                        'created', 'started', 'completed', 'dismissed', 'failed'
                    )),
    detail          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_planning_action_log_action ON planning_action_log(action_id);
```

### 3.3 现有字段复用

- `knowledge_items.lifecycle` — 5 阶段状态，用于进度条和规划生成
- `knowledge_items.score` — 用于复利仪表盘趋势
- `reading_states` — 用于规划生成（已读/未读状态）
- `knowledge_links` — 用于 top concepts 排名
- `source_stats` — 用于数据源健康度

---

## 4. 复利仪表盘设计

### 4.1 KnowledgeCompoundingDashboard 组件

```tsx
// frontend/src/components/knowledge/KnowledgeCompoundingDashboard.tsx

interface CompoundingMetrics {
  daily_trend: { date: string; count: number; score: number }[];
  weekly_trend: { week: string; count: number; score: number }[];
  monthly_trend: { month: string; count: number; score: number }[];
  top_concepts: { name: string; link_count: number; score: number }[];
  trigger_health: {
    t1_failed: number;
    t2_failed: number;
    t3_failed: number;
    t4_failed: number;
    dead_letter_count: number;
  };
  stage_distribution: Record<string, number>;
}
```

### 4.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kl/metrics` | 已存在 — 返回 T1-T4 指标 + by_stage_count |
| GET | `/api/kl/compounding` | 新增 — 返回日/周/月趋势 + top concepts + trigger_health |

---

## 5. 4 种认知模式 UI

### 5.1 路由设计

| 模式 | 路由 | 组件 | 说明 |
|------|------|------|------|
| 简报 | `/knowledge/briefing` | `BriefingMode` | 每日摘要 |
| 快速扫描 | `/knowledge/scan` | `ScanMode` | 分类列表（当前首页） |
| 深度阅读 | `/knowledge/deep-read/:id` | `DeepReadMode` | 全屏+侧栏 |
| 告警 | `/knowledge/alert` | `AlertMode` | 告警 Inbox |

### 5.2 导航整合

在 `KnowledgeTabs` 中新增"模式切换"入口，或在知识库页面顶部添加模式选择器。

### 5.3 4 模式数据获取

- **简报模式**: GET `/api/kl/briefing` — 今日发布的 items + 数据源状态
- **快速扫描**: 复用现有 `/api/hotspots` — 分类/标签/时间筛选
- **深度阅读**: GET `/api/knowledge/items/{id}` — 文章详情 + 关联信息
- **告警模式**: 复用 `/api/alerts/v2` — 告警列表

---

## 6. 触发器状态可视化

### 6.1 5 阶段进度条组件

```tsx
// frontend/src/components/knowledge/LifecycleProgress.tsx

interface LifecycleProgressProps {
  currentStage: string;  // e.g., 'kl:link'
  stages?: string[];     // default: ALL_STAGES
}
```

渲染为水平进度条，每个阶段显示：
- 已完成（绿色勾）→ 当前阶段（蓝色高亮）→ 待进行（灰色虚线）
- 各阶段颜色：raw=#6b7280, refine=#3b82f6, link=#8b5cf6, structure=#f97316, publish=#22c55e

### 6.2 集成位置

- `DeepReadMode` 右侧栏
- `KnowledgeItem` 详情页
- 可作为独立组件在其他页面嵌入

---

## 7. KnowledgePlanningPanel

### 7.1 组件设计

```tsx
// frontend/src/components/knowledge/KnowledgePlanningPanel.tsx

interface PlanningAction {
  id: number;
  item_id: string;
  action_type: 'read' | 'review' | 'link' | 'refine' | 'publish';
  priority: number;
  title: string;
  description: string;
  current_stage: string;
  target_stage: string;
  status: string;
  created_at: string;
}
```

### 7.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kl/planning-actions` | 获取规划动作列表（支持 status 过滤） |
| PUT | `/api/kl/planning-actions/{id}/status` | 更新动作状态（完成/忽略） |

### 7.3 规划生成逻辑（planning_action_check job）

```
对每个 lifecycle='kl:raw' 且未读的 item → 动作: read
对每个 lifecycle='kl:refine' 且 link_count < 3 的 item → 动作: link
对每个 lifecycle='kl:link' 且 score < 8.0 的 item → 动作: refine
对每个 lifecycle='kl:structure' 且稳定 > 24h 的 item → 动作: publish
对每个 lifecycle='kl:publish' 且 7 天未复习的 item → 动作: review
```

---

## 8. 调度器扩展

### 8.1 新增 1 个 job

| Job ID | 名称 | 触发器 | 间隔 |
|--------|------|--------|------|
| `planning_action_check` | 规划动作检查 | IntervalTrigger | 600s |

### 8.2 jobs.py 新增

```python
async def planning_action_check_job() -> None:
    """Phase 13: 每 600s 生成规划动作."""
    from backend.services.planning_service import PlanningService
    try:
        service = PlanningService()
        report = await asyncio.to_thread(service.generate_actions)
        logger.info(f"planning_action_check_job: {report}")
    except Exception as e:
        logger.error(f"planning_action_check_job crashed: {e}")
```

### 8.3 scheduler.py 新增

```python
# Phase 13: job 36 — 规划动作检查（每 600s）
self.scheduler.add_job(
    jobs.planning_action_check_job,
    trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
    id="planning_action_check",
    name="planning action check (every 600s)",
    replace_existing=True,
)
```

---

## 9. 测试计划

### 9.1 4 模式组件测试（12 用例）

| 用例 | 验证 |
|------|------|
| `test_briefing_mode_renders` | 简报模式渲染今日摘要 |
| `test_briefing_mode_empty` | 无今日发布时显示空态 |
| `test_scan_mode_renders` | 扫描模式显示分类列表 |
| `test_scan_mode_filters` | 分类/标签筛选工作 |
| `test_deep_read_mode_renders` | 深度阅读显示文章详情 |
| `test_deep_read_sidebar` | 右侧栏显示关联信息 |
| `test_alert_mode_renders` | 告警模式显示 Inbox |
| `test_alert_mode_badge` | 红色横幅显示未读计数 |
| `test_lifecycle_progress_renders` | 5 阶段进度条渲染 |
| `test_lifecycle_progress_colors` | 各阶段颜色正确 |
| `test_lifecycle_progress_stages` | 完成/当前/待进行状态正确 |
| `test_mode_navigation` | 4 模式切换路由正确 |

### 9.2 复利仪表盘测试（6 用例）

| 用例 | 验证 |
|------|------|
| `test_dashboard_renders` | 仪表盘渲染 |
| `test_dashboard_trend_chart` | 趋势图渲染（日/周/月） |
| `test_dashboard_top_concepts` | Top concepts 列表渲染 |
| `test_dashboard_trigger_health` | 断点告警显示 |
| `test_dashboard_stage_distribution` | 阶段分布图渲染 |
| `test_dashboard_empty` | 无数据时显示空态 |

### 9.3 KnowledgePlanningPanel 测试（5 用例）

| 用例 | 验证 |
|------|------|
| `test_planning_panel_renders` | 规划面板渲染 |
| `test_planning_panel_actions` | 动作列表显示 |
| `test_planning_panel_empty` | 无动作时显示空态 |
| `test_planning_panel_mark_complete` | 标记完成动作 |
| `test_planning_panel_dismiss` | 忽略动作 |

### 9.4 planning_action job 测试（5 用例）

| 用例 | 验证 |
|------|------|
| `test_planning_generate_raw_read` | kl:raw 生成 read 动作 |
| `test_planning_generate_refine_link` | kl:refine + link_count<3 生成 link 动作 |
| `test_planning_generate_link_refine` | kl:link + score<8.0 生成 refine 动作 |
| `test_planning_generate_structure_publish` | kl:structure + stable>24h 生成 publish 动作 |
| `test_planning_no_duplicate` | 相同 item + action_type 不重复生成 |

### 9.5 回归测试

- Phase 12 告警引擎测试 15/15 PASS
- Phase 10 T1/T2 测试 22/22 PASS
- 前端全量测试通过

---

## 10. 验收标准

### 10.1 单元测试门禁

- 4 模式组件测试：12/12 PASS
- 复利仪表盘测试：6/6 PASS
- KnowledgePlanningPanel 测试：5/5 PASS
- planning_action job 测试：5/5 PASS
- **总计**：28 用例全 PASS

### 10.2 行为验收

- 复利仪表盘显示日/周/月趋势 + top concepts + 断点告警
- 4 种认知模式可切换，路由正确
- 5 阶段进度条在详情页和深度阅读模式可见
- KnowledgePlanningPanel 显示个性化规划动作
- planning_action_check job 每 600s 生成规划动作
- 红色横幅显示未读告警数，告警模式展示 Inbox

### 10.3 回归测试

- 所有 Phase 12 测试不退化（46 用例）
- 所有 Phase 10 测试不退化（22 用例）
- 前端全量测试通过

---

## 11. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | 仪表盘性能（大量 items 趋势计算） | 低 | 中 | 后端聚合后返回，前端仅渲染 |
| 2 | 4 模式路由与现有路由冲突 | 中 | 中 | 使用 `/knowledge/*` 命名空间隔离 |
| 3 | planning_action 重复生成 | 中 | 低 | 唯一约束 (item_id + action_type + status='pending') |
| 4 | 进度条与真实 lifecycle 不同步 | 低 | 低 | 直接从 API 返回的 lifecycle 值渲染 |
| 5 | 简报模式无今日发布 | 高 | 低 | 显示空态 + 建议切换到扫描模式 |