# Phase 12 — T3/T4/T5 触发器 + 告警系统

> **版本**: v2.0 (Phase 12)
> **日期**: 2026-07-31
> **周期**: ~6 天
> **spec 路径**: `.trae/specs/phase12-t3t4t5-alerts/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.11.6 + B.10 + M6
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md` Phase 12
> **前置**: Phase 10 (T1/T2 触发器) ✅ + Phase 11 (抓取层现代化) ✅ + 046 迁移 ✅
> **Group 划分**: A(T3) → B(T4) → C(T5) → D(scheduler) → E(alert-engine) → F(alert-rules) → G(alert-ui) → H(tests)

---

## 1. 背景与目标

### 1.1 背景

Phase 10 完成了 5 阶段状态机的前两跳（T1: kl:raw→kl:refine, T2: kl:refine→kl:link），Phase 11 完成了抓取层现代化和 6 个新 collector。目前知识库 lifecycle 可以推进到 `kl:link`，但无法继续到 `kl:structure`（结构化摘要）和 `kl:publish`（发布到 knowledge/items/*.md）。

同时，v1.7 的告警系统 M6 设计了完整规则引擎但从未实施。v2.0 PRD 恢复为 3 类基础规则。

### 1.2 目标

1. **T3 触发器**：每 600s 跑一次，把 `lifecycle='kl:link'` 的 items 推进到 `kl:structure`（关联数检查 + 摘要生成 + 结构化）
2. **T4 触发器**：每 1800s 跑一次，把 `lifecycle='kl:structure'` 的 items 推进到 `kl:publish`（score 阈值 + 24h 稳定窗口 + .md 文件写入）
3. **T5 触发器**：用户主动调用，把 `kl:publish` 回滚到 `kl:refine`（备份 + stale 标记）
4. **告警规则引擎**：`alert_engine.py` 实现 3 类基础规则 + 规则存储
5. **告警规则 1**：tech_stack 影响 — 新 CVE 命中 cg_projects.tech_stack
6. **告警规则 2**：关键 CVE — NVD CVSS ≥ 9.0
7. **告警规则 3**：标讯命中 — 标讯关键词命中 tech_stack
8. **告警 UI**：`AlertCenter.tsx` — Inbox + 红色横幅
9. **调度器注册**：job 34（kl_trigger_t3，600s）+ job 35（kl_trigger_t4，1800s）

### 1.3 不在范围内

- ❌ 复利仪表盘 UI（Phase 13）
- ❌ 4 模式 UI（Phase 13）
- ❌ KnowledgePlanningPanel（Phase 13）
- ❌ T5 的 UI 操作入口（Phase 13 AlertMode 或 DeepReadMode）
- ❌ Hybrid AI 评分（Phase 16）— T3 摘要生成使用现有 `knowledge_sync` 基础设施
- ❌ 告警通知通道（邮件/推送）— v2.1
- ❌ 告警规则自定义 UI — v2.1

---

## 2. 范围

### 2.1 必做

**T3 触发器（Task A）**
- `backend/services/triggers/t3_link_to_structure.py`：`T3Trigger` 类 + `run_once()` 方法
- 流程：查询 `lifecycle='kl:link'` 的 items → 检查关联数（`knowledge_links` 表）→ 生成摘要（使用现有 `write_item_to_md` 的 content 字段）→ 更新 `lifecycle='kl:structure'`
- 关联数 ≥ 3 的 items 100% 推进
- 关联数 < 3 的 items 也推进但标 `low_link_structure` flag
- 调度：每 600s

**T4 触发器（Task B）**
- `backend/services/triggers/t4_structure_to_publish.py`：`T4Trigger` 类 + `run_once()` 方法
- 流程：查询 `lifecycle='kl:structure'` 的 items → 检查 score（`ai_scores` 表，阈值 ≥ 8.0）→ 检查 24h 稳定窗口（`updated_at < now - 24h`）→ 调用 `write_item_to_md()` 写入 .md 文件 → 更新 `lifecycle='kl:publish'`
- score ≥ 8 的 items 100% 自动发布
- score < 8 的 items 跳过，累计 `skipped_low_score` 计数
- 调度：每 1800s

**T5 触发器（Task C）**
- `backend/services/triggers/t5_publish_to_refine.py`：`T5Trigger` 类 + `run_once()` 方法
- T5 是**用户主动调用**（非定时调度）
- 流程：接收 `item_id` → 备份当前 .md 文件到 `knowledge/backups/` → 标记 `stale_at` 时间戳 → 更新 `lifecycle='kl:refine'`
- 提供 `rollback(item_id)` 方法供 API 调用
- 回滚 100% 不丢用户编辑（备份优先）

**调度器扩展（Task D）**
- `backend/scheduler/jobs.py`：新增 `kl_trigger_t3_job` / `kl_trigger_t4_job`
- `backend/scheduler/scheduler.py`：job 34（600s）+ job 35（1800s）
- T5 不注册定时 job，注册 API endpoint `POST /api/kl/rollback/{item_id}`

**告警规则引擎（Task E）**
- `backend/services/alert_engine.py`：`AlertEngine` 类
- 3 类规则存储（SQLite `alert_rules` 表）
- 规则评估 `evaluate()` 方法
- 告警记录 `alert_events` 表（存储已触发的告警）

**告警规则 1（Task F1）**
- tech_stack 影响：新 CVE 命中 `cg_projects.tech_stack`
- 从 `cve_items` 或 `security_items` 检测 CVE → 匹配 `cg_projects.tech_stack` → 触发告警

**告警规则 2（Task F2）**
- 关键 CVE：NVD CVSS ≥ 9.0
- 从 `security_items` 检测 CVSS score → 触发告警

**告警规则 3（Task F3）**
- 标讯命中：标讯关键词命中 `cg_projects.tech_stack`
- 从 `bid_items` 检测关键词匹配 → 触发告警

**告警 UI（Task G）**
- `frontend/src/components/AlertCenter.tsx`
- Inbox 列表：展示告警标题、时间、等级、状态
- 红色横幅：未读告警数显示在导航栏
- 标记已读/全部已读功能

**测试（Task H）**
- `test_t3_trigger.py`：10 用例（关联数检查 + 摘要 + lifecycle 推进）
- `test_t4_trigger.py`：10 用例（score 阈值 + 24h 窗口 + .md 写入）
- `test_t5_trigger.py`：8 用例（备份 + 回滚 + 不丢编辑）
- `test_alert_engine.py`：15 用例（3 类规则 × 5 场景）

### 2.2 明确不做

- ❌ 不实现告警规则自定义 UI（v2.1）
- ❌ 不实现通知通道（邮件/推送/飞书）
- ❌ 不修改现有 T1/T2 触发器实现
- ❌ 不修改 `collection_service.py` 主流程
- ❌ 不修改 simhash 实现
- ❌ 不修改 4 个 MCP tool
- ❌ 不实现 Hybrid AI（Phase 16）

---

## 3. 数据模型

### 3.1 新表 `alert_rules`（migration 048）

```sql
-- backend/repository/migrations/048_v2.0_alert_rules.sql
-- 目的: 告警规则定义

CREATE TABLE IF NOT EXISTS alert_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    rule_type   TEXT NOT NULL CHECK(rule_type IN ('tech_stack_cve', 'critical_cve', 'bid_match')),
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    config      TEXT,  -- JSON 配置（如阈值、匹配模式）
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_rules_type ON alert_rules(rule_type);
```

### 3.2 新表 `alert_events`（migration 048）

```sql
-- backend/repository/migrations/048_v2.0_alert_events.sql
-- 目的: 已触发的告警事件

CREATE TABLE IF NOT EXISTS alert_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     INTEGER REFERENCES alert_rules(id),
    rule_type   TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    severity    TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    source      TEXT,  -- 触发源（如 CVE ID、标讯标题）
    source_url  TEXT,
    item_id     TEXT,  -- 关联的知识库 item ID
    project_id  INTEGER,  -- 关联的 cg_projects ID
    status      TEXT NOT NULL DEFAULT 'unread' CHECK(status IN ('unread', 'read', 'resolved')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status);
CREATE INDEX IF NOT EXISTS idx_alert_events_created ON alert_events(created_at);
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_type ON alert_events(rule_type);
```

### 3.3 lifecycle 5 阶段转换图（完整）

```python
TRANSITIONS = {
    LIFECYCLE_RAW:       {LIFECYCLE_REFINE},       # T1 (Phase 10)
    LIFECYCLE_REFINE:    {LIFECYCLE_LINK},         # T2 (Phase 10)
    LIFECYCLE_LINK:      {LIFECYCLE_STRUCTURE},    # T3 (Phase 12)
    LIFECYCLE_STRUCTURE: {LIFECYCLE_PUBLISH},      # T4 (Phase 12)
    LIFECYCLE_PUBLISH:   {LIFECYCLE_REFINE},       # T5 回滚 (Phase 12)
}
```

### 3.4 现有 `knowledge_items` 表新增字段（无需 migration）

T4 和 T5 使用现有字段：
- `lifecycle` — 5 阶段字符串
- `updated_at` — 用于 T4 24h 稳定窗口判断
- `score` — 用于 T4 阈值判断

T5 新增字段（通过 `046_lifecycle_v2.sql` 已包含或直接在代码中更新）：
- `stale_at` — 回滚时标记的时间戳

---

## 4. T3 触发器设计

### 4.1 T3Trigger 类

```python
# backend/services/triggers/t3_link_to_structure.py

class T3Trigger:
    """T3: kl:link → kl:structure

    流程：
    1. 查询 lifecycle='kl:link' 的 items（无时间限制）
    2. 关联数检查：查询 knowledge_links 表，统计 from_id=item.id 的 link 数
    3. 关联数 ≥ 3 的 items 正常推进；< 3 的也推进但标 low_link_structure
    4. 生成摘要：从现有 content 字段提取前 200 字作为 summary
    5. 更新 lifecycle='kl:structure'
    """

    def run_once(self) -> dict:
        items = self._fetch_candidates()
        advanced = 0
        low_link = 0
        skipped = 0
        failed = 0
        for item in items:
            try:
                link_count = self._count_links(item["id"])
                if link_count < 3:
                    low_link += 1
                summary = self._generate_summary(item)
                self._update_lifecycle(item["id"], LIFECYCLE_STRUCTURE)
                advanced += 1
            except Exception as e:
                self.retry_policy.handle_failure("t3", item["id"], e)
                failed += 1
        return {
            "candidates": len(items),
            "advanced": advanced,
            "low_link": low_link,
            "failed": failed,
        }
```

### 4.2 关联数查询

```python
def _count_links(self, item_id: str) -> int:
    """查询 knowledge_links 表中 from_id=item_id 的 link 数"""
    conn = get_connection()
    cur = conn.execute(
        "SELECT COUNT(*) FROM knowledge_links WHERE from_id = ?",
        (item_id,)
    )
    return cur.fetchone()[0]
```

### 4.3 摘要生成

```python
def _generate_summary(self, item: dict) -> str:
    """从现有 content 提取前 200 字作为摘要"""
    content = item.get("content") or ""
    summary = content[:200]
    return summary
```

---

## 5. T4 触发器设计

### 5.1 T4Trigger 类

```python
# backend/services/triggers/t4_structure_to_publish.py

class T4Trigger:
    """T4: kl:structure → kl:publish

    流程：
    1. 查询 lifecycle='kl:structure' 的 items
    2. score 检查：取最近 ai_scores.score，需 ≥ 8.0
    3. 24h 稳定窗口：updated_at < now - 24h
    4. .md 写入：调用 write_item_to_md()
    5. 更新 lifecycle='kl:publish'
    """

    STABLE_WINDOW_HOURS = 24
    MIN_SCORE = 8.0

    def run_once(self) -> dict:
        items = self._fetch_candidates()
        advanced = 0
        skipped_low_score = 0
        skipped_unstable = 0
        failed = 0
        for item in items:
            try:
                score = self._get_latest_score(item["id"])
                if score < self.MIN_SCORE:
                    skipped_low_score += 1
                    continue
                if not self._is_stable(item):
                    skipped_unstable += 1
                    continue
                self._write_to_md(item)
                self._update_lifecycle(item["id"], LIFECYCLE_PUBLISH)
                advanced += 1
            except Exception as e:
                self.retry_policy.handle_failure("t4", item["id"], e)
                failed += 1
        return {
            "candidates": len(items),
            "advanced": advanced,
            "skipped_low_score": skipped_low_score,
            "skipped_unstable": skipped_unstable,
            "failed": failed,
        }
```

### 5.2 .md 写入

使用 `knowledge_sync.write_item_to_md()` 写入 `knowledge/items/{id}.md`。

---

## 6. T5 触发器设计

### 6.1 T5Trigger 类

```python
# backend/services/triggers/t5_publish_to_refine.py

class T5Trigger:
    """T5: kl:publish → kl:refine（用户主动回滚）

    流程：
    1. 接收 item_id 参数
    2. 备份当前 .md 文件到 knowledge/backups/{id}_{timestamp}.md
    3. 标记 stale_at = now
    4. 更新 lifecycle='kl:refine'
    """

    def rollback(self, item_id: str) -> dict:
        backup_path = self._backup_md(item_id)
        self._mark_stale(item_id)
        self._update_lifecycle(item_id, LIFECYCLE_REFINE)
        return {
            "item_id": item_id,
            "backup_path": str(backup_path),
            "new_lifecycle": LIFECYCLE_REFINE,
        }
```

### 6.2 API 端点

```python
# backend/api/kl_rollback_api.py

@router.post("/api/kl/rollback/{item_id}")
async def rollback_knowledge_item(item_id: str):
    """用户主动回滚 knowledge item 到 refine 阶段"""
    trigger = T5Trigger()
    result = trigger.rollback(item_id)
    return {"status": "ok", "result": result}
```

---

## 7. 告警规则引擎

### 7.1 AlertEngine 类

```python
# backend/services/alert_engine.py

class AlertEngine:
    """告警规则引擎"""

    def __init__(self):
        self.rules = self._load_rules()

    def _load_rules(self) -> list:
        """从 alert_rules 表加载启用的规则"""
        conn = get_connection()
        cur = conn.execute(
            "SELECT * FROM alert_rules WHERE enabled = 1"
        )
        return cur.fetchall()

    def evaluate_all(self) -> dict:
        """评估所有规则，返回触发统计"""
        results = {}
        for rule in self.rules:
            count = self._evaluate_rule(rule)
            results[rule["name"]] = count
        return results

    def _evaluate_rule(self, rule: dict) -> int:
        """评估单条规则"""
        if rule["rule_type"] == "tech_stack_cve":
            return self._evaluate_tech_stack_cve(rule)
        elif rule["rule_type"] == "critical_cve":
            return self._evaluate_critical_cve(rule)
        elif rule["rule_type"] == "bid_match":
            return self._evaluate_bid_match(rule)
        return 0

    def _evaluate_tech_stack_cve(self, rule: dict) -> int:
        """规则1：新 CVE 命中 cg_projects.tech_stack"""
        # 查询最近 24h 的 security_items
        # 提取 CVE ID
        # 匹配 cg_projects.tech_stack
        # 触发 alert_events
        pass

    def _evaluate_critical_cve(self, rule: dict) -> int:
        """规则2：关键 CVE (CVSS ≥ 9.0)"""
        # 查询最近 24h 的 security_items
        # 提取 CVSS score
        # score ≥ 9.0 触发告警
        pass

    def _evaluate_bid_match(self, rule: dict) -> int:
        """规则3：标讯命中 tech_stack"""
        # 查询最近 24h 的 bid_items
        # 关键词匹配 cg_projects.tech_stack
        # 命中触发告警
        pass
```

### 7.2 告警事件存储

```python
def _trigger_alert(self, rule_type: str, title: str, description: str,
                   severity: str, source: str = None, source_url: str = None,
                   item_id: str = None, project_id: int = None) -> int:
    """写入 alert_events 表"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO alert_events
           (rule_type, title, description, severity, source, source_url, item_id, project_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (rule_type, title, description, severity, source, source_url, item_id, project_id)
    )
    return conn.lastrowid
```

### 7.3 3 类规则种子数据（migration 048）

```sql
INSERT INTO alert_rules (name, description, rule_type, config) VALUES
('技术栈 CVE 影响', '新 CVE 命中 cg_projects.tech_stack 时触发', 'tech_stack_cve', '{"window_hours": 24}'),
('关键 CVE 告警', 'NVD CVSS ≥ 9.0 的 CVE 触发', 'critical_cve', '{"min_cvss": 9.0}'),
('标讯技术栈匹配', '标讯关键词命中 tech_stack 时触发', 'bid_match', '{"window_hours": 24}');
```

---

## 8. 告警 UI

### 8.1 AlertCenter 组件

```tsx
// frontend/src/components/AlertCenter.tsx

interface AlertEvent {
  id: number;
  rule_type: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  source: string;
  status: 'unread' | 'read' | 'resolved';
  created_at: string;
}

// 功能：
// 1. GET /api/alerts → 获取告警列表（分页，默认最新 50 条）
// 2. 红色横幅：导航栏显示未读告警数
// 3. 标记已读：PUT /api/alerts/{id}/read
// 4. 全部已读：PUT /api/alerts/read-all
// 5. 按 severity 颜色区分：critical=红, high=橙, medium=黄, low=灰
```

### 8.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alerts` | 获取告警列表（支持 status/severity 过滤） |
| GET | `/api/alerts/unread-count` | 获取未读告警数 |
| PUT | `/api/alerts/{id}/read` | 标记单条已读 |
| PUT | `/api/alerts/read-all` | 全部已读 |
| PUT | `/api/alerts/{id}/resolve` | 标记已解决 |
| POST | `/api/alerts/evaluate` | 手动触发规则评估 |

---

## 9. 测试计划

### 9.1 T3 测试（10 用例）

| 用例 | 验证 |
|------|------|
| `test_t3_returns_candidates` | 查询 lifecycle='kl:link' 的 items |
| `test_t3_advances_high_link_items` | 关联数 ≥ 3 的 items 推进到 structure |
| `test_t3_low_link_also_advances` | 关联数 < 3 的 items 也推进（标 low_link） |
| `test_t3_generates_summary` | 摘要从 content 前 200 字提取 |
| `test_t3_updates_lifecycle` | lifecycle 更新为 kl:structure |
| `test_t3_no_candidates` | 无候选 items 时返回空结果 |
| `test_t3_failure_handling` | 异常时入死信队列 |
| `test_t3_link_count_query` | knowledge_links 表查询正确 |
| `test_t3_metrics_incremented` | 指标正确递增 |
| `test_t3_empty_content` | content 为空时摘要为空字符串 |

### 9.2 T4 测试（10 用例）

| 用例 | 验证 |
|------|------|
| `test_t4_returns_candidates` | 查询 lifecycle='kl:structure' 的 items |
| `test_t4_advances_high_score_items` | score ≥ 8.0 的 items 推进到 publish |
| `test_t4_skips_low_score` | score < 8.0 的 items 跳过 |
| `test_t4_skips_unstable` | updated_at < 24h 的 items 跳过 |
| `test_t4_writes_md_file` | .md 文件写入 knowledge/items/ |
| `test_t4_updates_lifecycle` | lifecycle 更新为 kl:publish |
| `test_t4_no_candidates` | 无候选 items 时返回空结果 |
| `test_t4_failure_handling` | 异常时入死信队列 |
| `test_t4_metrics_incremented` | 指标正确递增 |
| `test_t4_score_fallback` | 无 ai_scores 时使用 item.score 字段 |

### 9.3 T5 测试（8 用例）

| 用例 | 验证 |
|------|------|
| `test_t5_rollback_basic` | 正常回滚，lifecycle 变为 kl:refine |
| `test_t5_backup_created` | .md 备份文件写入 knowledge/backups/ |
| `test_t5_stale_marked` | stale_at 时间戳标记 |
| `test_t5_rollback_nonexistent` | 不存在的 item_id 返回 404 |
| `test_t5_rollback_not_published` | 非 publish 状态的 item 拒绝回滚 |
| `test_t5_backup_preserves_content` | 备份文件内容与原始 .md 一致 |
| `test_t5_api_endpoint` | POST /api/kl/rollback/{id} 返回正确 |
| `test_t5_concurrent_rollback` | 并发回滚同一 item 不冲突 |

### 9.4 告警引擎测试（15 用例）

| 用例 | 验证 |
|------|------|
| `test_alert_engine_load_rules` | 从 alert_rules 表加载启用的规则 |
| `test_tech_stack_cve_trigger` | CVE 命中 tech_stack 触发告警 |
| `test_tech_stack_cve_no_match` | CVE 未命中 tech_stack 不触发 |
| `test_critical_cve_trigger` | CVSS ≥ 9.0 触发告警 |
| `test_critical_cve_below_threshold` | CVSS < 9.0 不触发 |
| `test_bid_match_trigger` | 标讯关键词命中 tech_stack 触发 |
| `test_bid_match_no_match` | 关键词未命中不触发 |
| `test_alert_event_stored` | 告警写入 alert_events 表 |
| `test_alert_event_api_get` | GET /api/alerts 返回告警列表 |
| `test_alert_event_mark_read` | PUT /api/alerts/{id}/read 标记已读 |
| `test_alert_event_read_all` | PUT /api/alerts/read-all 全部已读 |
| `test_alert_unread_count` | GET /api/alerts/unread-count 返回正确 |
| `test_alert_rule_disabled` | 禁用规则不评估 |
| `test_alert_concurrent_triggers` | 重复触发不重复写入 |
| `test_alert_evaluate_all` | evaluate_all 返回正确统计 |

---

## 10. 调度器注册

### 10.1 新增 2 个 job

| Job ID | 名称 | 触发器 | 间隔 |
|--------|------|--------|------|
| `kl_trigger_t3` | T3: kl:link → kl:structure | IntervalTrigger | 600s |
| `kl_trigger_t4` | T4: kl:structure → kl:publish | IntervalTrigger | 1800s |

### 10.2 jobs.py 新增

```python
async def kl_trigger_t3_job() -> None:
    """Phase 12: 每 600s 跑一次 T3 (kl:link → kl:structure)."""
    from backend.services.triggers.t3_link_to_structure import T3Trigger
    try:
        t3 = T3Trigger()
        report = await asyncio.to_thread(t3.run_once)
        logger.info(f"kl_trigger_t3_job: {report}")
    except Exception as e:
        logger.error(f"kl_trigger_t3_job crashed: {e}")


async def kl_trigger_t4_job() -> None:
    """Phase 12: 每 1800s 跑一次 T4 (kl:structure → kl:publish)."""
    from backend.services.triggers.t4_structure_to_publish import T4Trigger
    try:
        t4 = T4Trigger()
        report = await asyncio.to_thread(t4.run_once)
        logger.info(f"kl_trigger_t4_job: {report}")
    except Exception as e:
        logger.error(f"kl_trigger_t4_job crashed: {e}")
```

### 10.3 scheduler.py 新增（2 个 add_job）

```python
# Phase 12: job 34 — T3 触发器（每 600s）
self.scheduler.add_job(
    jobs.kl_trigger_t3_job,
    trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
    id="kl_trigger_t3",
    name="KL T3 trigger: kl:link -> kl:structure (every 600s)",
    replace_existing=True,
)
# Phase 12: job 35 — T4 触发器（每 1800s）
self.scheduler.add_job(
    jobs.kl_trigger_t4_job,
    trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
    id="kl_trigger_t4",
    name="KL T4 trigger: kl:structure -> kl:publish (every 1800s)",
    replace_existing=True,
)
```

---

## 11. 验收标准

### 11.1 单元测试门禁

- `test_t3_trigger.py`：10/10 PASS
- `test_t4_trigger.py`：10/10 PASS
- `test_t5_trigger.py`：8/8 PASS
- `test_alert_engine.py`：15/15 PASS
- **总计**：43 用例全 PASS

### 11.2 行为验收

- T3：关联数 ≥ 3 的 items 100% 推进到 `kl:structure`
- T4：score ≥ 8 的 items 100% 自动发布到 `knowledge/items/*.md`
- T5：用户回滚 100% 不丢用户编辑（备份优先）
- 3 类告警规则可触发，告警事件写入 `alert_events` 表
- AlertCenter 渲染未读告警数、红色横幅、Inbox 列表
- 调度器：2 个新 job 启动后正常运行（日志可见每 600s/1800s 输出）

### 11.3 回归测试

- 所有 Phase 10 测试不退化（56 用例）
- 所有 Phase 11 测试不退化（49 用例）
- 所有现有 collector 测试不退化（21 用例）
- 编译检查：所有新文件通过 `py_compile`

---

## 12. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | T3 关联数检查慢（大量 items） | 低 | 中 | 加 `knowledge_links.from_id` 索引 |
| 2 | T4 .md 写入与 `knowledge_watcher` 冲突 | 中 | 高 | T4 写入后 `knowledge_sync` 自动同步回 DB，不会冲突 |
| 3 | T5 备份目录不存在 | 低 | 低 | `knowledge/backups/` 目录自动创建 |
| 4 | 告警重复触发 | 中 | 中 | `alert_events` 加 `source + item_id` 唯一约束 |
| 5 | 告警表无限增长 | 中 | 低 | 保留 30 天，之后自动清理 |
| 6 | 标讯匹配无 cg_projects 数据 | 高 | 低 | 无项目时不触发，不报错 |
| 7 | T3/T4 与 T1/T2 竞争条件 | 低 | 中 | 状态机转换检查已在 `kl_state_machine.py` 实现 |