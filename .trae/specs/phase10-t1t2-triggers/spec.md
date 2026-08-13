# Phase 10 — T1/T2 触发器实施 (KL 状态机起点)

> **版本**: v2.0 (Phase 10)
> **日期**: 2026-07-28
> **周期**: ~4 天（D10–14 in M1 详细排期）
> **spec 路径**: `.trae/specs/phase10-t1t2-triggers/`
> **PRD 章节**: `docs/hotspot_v2.0_PRD.md` B.11.6 + B.10
> **前置**: Phase 8 (复利基础设施) ✅ + Phase 9 (v1.9 抓取标准化) ✅
> **开发计划**: `docs/hotspot_v2.0_dev_plan.md` Phase 10
> **Group 划分**: A(state-machine) → B(t1-trigger) → C(t2-trigger) → D(retry+metrics) → E(scheduler) → F(tests)

---

## 1. 背景与目标

### 1.1 背景

hotspot v1.7.6 的知识库 `knowledge_items` 表已存在 5 阶段 lifecycle 字段（`signal` / `amplify:tagged` / `generate`），但**没有任何代码在推进 lifecycle**——所有 items 都停在 `signal` 阶段。Phase 8 完成了 4 张数据表（`content_fingerprints` / `ai_scores` / `item_entities` / `knowledge_links`）+ 4 个 MCP tool + simhash 去重，但 5 触发器（T1~T5）一个都没接进调度器。

v2.0 的核心承诺是**知识库日增量 ≥ 10 items/天**，Phase 10 实施 T1/T2 两个触发器，让 lifecycle 自动从 `kl:raw` → `kl:refine` → `kl:link`。

### 1.2 目标

1. **5 阶段状态机引擎**：`kl_state_machine.py` 实现 5 阶段转换的不变量检查
2. **T1 触发器**：每 60s 跑一次，把 `lifecycle='kl:raw'` 的 items 推进到 `kl:refine`（自动评分 + 提取 tag + simhash 去重）
3. **T2 触发器**：每 120s 跑一次，把 `lifecycle='kl:refine'` 的 items 推进到 `kl:link`（查找 entity 关联 + 写入 knowledge_links）
4. **重试 + 死信**：指数退避（1s/5s/30s），3 次失败后入死信队列
5. **Prometheus 指标**：6 个核心指标（triggered / succeeded / failed / latency / dead_letter / by_stage_count）
6. **调度器注册**：job 31（kl_trigger_t1，60s）+ job 32（kl_trigger_t2，120s）

### 1.3 不在范围内

- ❌ T3/T4/T5 触发器（Phase 12）
- ❌ 6 个新 collector（Phase 11）
- ❌ 可读 ID 规范化（Phase 11）
- ❌ Hybrid AI 评分（Phase 15）— 本 Phase 用 MCP `score_item` 已存评分，Phase 15 切换为 `llm_service.score`
- ❌ lifecycle 5 阶段迁移 SQL（`046_lifecycle_v2.sql` 已存在，Phase 10 完成后执行）
- ❌ 告警系统（Phase 12）
- ❌ 复利仪表盘 UI（Phase 13）

---

## 2. 范围

### 2.1 必做

**状态机引擎（Task A）**
- `backend/services/kl_state_machine.py`：`KLStateMachine` 类 + 5 阶段常量 + 转换函数 + 不变量检查
- 5 阶段：`kl:raw` → `kl:refine` → `kl:link` → `kl:structure` → `kl:publish`
- 转换函数：`can_transition(from, to)` / `transition(item, to_stage, actor)`

**T1 触发器（Task B）**
- `backend/services/triggers/__init__.py`
- `backend/services/triggers/t1_raw_to_refine.py`：`T1Trigger` 类 + `run_once()` 方法
- 流程：查询 `lifecycle='kl:raw'` 且 `ingested_at < now - 5min` 的 items → simhash 去重（仅推进非重复）→ 评分（取最近 `ai_scores.score`，无则 fallback 5.0）→ 提取 tag（来自 `concepts` 或 keyword）→ 更新 `lifecycle='kl:refine'`
- 调度：每 60s

**T2 触发器（Task C）**
- `backend/services/triggers/t2_refine_to_link.py`：`T2Trigger` 类 + `run_once()` 方法
- 流程：查询 `lifecycle='kl:refine'` 的 items → 查找 entity（`item_entities` 表 + 关键词匹配 `concepts`）→ 写 `knowledge_links`（self→related，type='similar'）→ 更新 `lifecycle='kl:link'`
- 调度：每 120s

**重试 + 死信（Task D1）**
- `backend/services/retry_policy.py`：`with_retry(fn, max_attempts=3, backoff=(1, 5, 30))` 装饰器
- `backend/repository/kl_dead_letter_repo.py`：死信队列 CRUD

**Prometheus 指标（Task D2）**
- `backend/metrics/kl_metrics.py`：6 个指标定义（counter / histogram / gauge）
- `backend/api/kl_metrics_api.py`：`GET /api/kl/metrics` 返回 JSON（无需 prom client）

**调度器注册（Task E）**
- `backend/scheduler/jobs.py`：新增 `kl_trigger_t1_job` / `kl_trigger_t2_job` / `kl_dead_letter_retry_job`
- `backend/scheduler/scheduler.py`：job 31（60s）+ job 32（120s）+ job 33（600s 死信重试）

**测试（Task F）**
- `test_kl_state_machine.py`：15 用例（5 阶段转换合法性 + 非法转换拒绝）
- `test_t1_trigger.py`：12 用例（去重 + 评分 fallback + tag 提取 + lifecycle 推进）
- `test_t2_trigger.py`：10 用例（entity 查找 + link 写入 + lifecycle 推进）
- `test_retry_policy.py`：8 用例（指数退避 + 死信写入 + 边界）
- `test_kl_metrics.py`：5 用例（6 指标正确递增）
- `test_phase10_integration.py`：6 用例（端到端：T1→T2 链路 + 调度器启动 + 死信兜底）

### 2.2 明确不做

- ❌ 不实现 T3/T4/T5 触发器（保留接口签名即可）
- ❌ 不改 `collection_service.py` 主流程（Phase 8 已修，Phase 10 只读不写）
- ❌ 不改 simhash 实现（已存在）
- ❌ 不改 4 个 MCP tool（已存在）
- ❌ 不实现 lifecycle 迁移 SQL 执行（仅写文档说明）
- ❌ 不实现 Hybrid AI（Phase 15）— T1 评分直接读 `ai_scores` 表

---

## 3. 数据模型

### 3.1 不修改任何表

Phase 10 只读 + 更新现有 4 张表（`knowledge_items` / `ai_scores` / `item_entities` / `knowledge_links`）+ 1 张新表（`kl_dead_letters`）。

### 3.2 新表 `kl_dead_letters`（migration 044）

```sql
-- backend/repository/migrations/044_v2.0_kl_dead_letters.sql
-- 目的: KL 触发器死信队列（重试 3 次失败后入队）

CREATE TABLE IF NOT EXISTS kl_dead_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_name TEXT NOT NULL CHECK(trigger_name IN ('t1', 't2', 't3', 't4', 't5')),
    item_id     TEXT NOT NULL,                  -- knowledge_items.id
    error_msg   TEXT NOT NULL,                  -- 最后一次错误
    attempts    INTEGER NOT NULL DEFAULT 0,     -- 累计尝试次数
    payload     TEXT,                           -- JSON 序列化上下文
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_retry_at TEXT,
    resolved    INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_dl_trigger_resolved ON kl_dead_letters(trigger_name, resolved);
CREATE INDEX IF NOT EXISTS idx_dl_item_id ON kl_dead_letters(item_id);
```

### 3.3 lifecycle 5 阶段值（字符串常量）

```python
# backend/services/kl_state_machine.py

# v2.0 5 阶段 lifecycle 值
LIFECYCLE_RAW = "kl:raw"            # 原始入库（从 hotspots / 收藏导入）
LIFECYCLE_REFINE = "kl:refine"      # 评分 + tag 完成
LIFECYCLE_LINK = "kl:link"          # 实体关联完成
LIFECYCLE_STRUCTURE = "kl:structure"  # 摘要 + 结构化完成
LIFECYCLE_PUBLISH = "kl:publish"    # 已发布到 knowledge/{item_id}.md

# 阶段转换图（单向 DAG）
TRANSITIONS = {
    LIFECYCLE_RAW:       {LIFECYCLE_REFINE},       # T1
    LIFECYCLE_REFINE:    {LIFECYCLE_LINK},         # T2
    LIFECYCLE_LINK:      {LIFECYCLE_STRUCTURE},    # T3 (Phase 12)
    LIFECYCLE_STRUCTURE: {LIFECYCLE_PUBLISH},      # T4 (Phase 12)
    LIFECYCLE_PUBLISH:   {LIFECYCLE_REFINE},       # T5 回滚 (Phase 12)
}
```

### 3.4 兼容旧 3 阶段值

`046_lifecycle_v2.sql` 已存在但未执行，**Phase 10 完成后、Phase 11 启动前执行**：
```sql
UPDATE knowledge_items
SET lifecycle = CASE lifecycle
    WHEN 'signal'         THEN 'kl:raw'
    WHEN 'amplify:tagged' THEN 'kl:refine'
    WHEN 'generate'       THEN 'kl:structure'
    ELSE lifecycle
END
WHERE lifecycle IN ('signal', 'amplify:tagged', 'generate');
```

---

## 4. 状态机设计

### 4.1 状态机类（Task A1）

```python
# backend/services/kl_state_machine.py

from typing import Optional

# 5 阶段常量（见 §3.3）
LIFECYCLE_RAW = "kl:raw"
LIFECYCLE_REFINE = "kl:refine"
LIFECYCLE_LINK = "kl:link"
LIFECYCLE_STRUCTURE = "kl:structure"
LIFECYCLE_PUBLISH = "kl:publish"

# 合法转换图
TRANSITIONS = {
    LIFECYCLE_RAW:       {LIFECYCLE_REFINE},
    LIFECYCLE_REFINE:    {LIFECYCLE_LINK},
    LIFECYCLE_LINK:      {LIFECYCLE_STRUCTURE},
    LIFECYCLE_STRUCTURE: {LIFECYCLE_PUBLISH},
    LIFECYCLE_PUBLISH:   {LIFECYCLE_REFINE},  # T5 回滚
}


def can_transition(from_stage: str, to_stage: str) -> bool:
    """检查 from_stage → to_stage 是否合法"""
    return to_stage in TRANSITIONS.get(from_stage, set())


def transition(item_lifecycle: str, to_stage: str, actor: str = "trigger") -> str:
    """返回新 lifecycle（不变更数据库）
    
    Raises:
        ValueError: 非法转换
    """
    if not can_transition(item_lifecycle, to_stage):
        raise ValueError(
            f"illegal transition: {item_lifecycle} -> {to_stage} (by {actor})"
        )
    return to_stage


def is_terminal(stage: str) -> bool:
    """是否终态（kl:publish 是终态，但可被 T5 回滚）"""
    return stage == LIFECYCLE_PUBLISH


# 5 阶段中文标签
STAGE_LABELS = {
    LIFECYCLE_RAW:       "原始",
    LIFECYCLE_REFINE:    "精炼",
    LIFECYCLE_LINK:      "关联",
    LIFECYCLE_STRUCTURE: "结构化",
    LIFECYCLE_PUBLISH:   "已发布",
}
```

### 4.2 T1 触发器（Task B1）

```python
# backend/services/triggers/t1_raw_to_refine.py

class T1Trigger:
    """T1: kl:raw → kl:refine
    
    流程：
    1. 查询 lifecycle='kl:raw' 且 ingested_at < now - 5min 的 items
    2. simhash 去重（content_fingerprints 已有完全相同则跳过）
    3. 评分：取最近 ai_scores.score（无则 fallback 5.0）
    4. 提取 tag：来自 item.concepts (JSON 字符串) 或 auto_classifier
    5. 更新 lifecycle='kl:refine'
    """
    
    RAW_MIN_AGE_SECONDS = 300  # 5min 防抖
    
    def run_once(self) -> dict:
        """返回 {'candidates': N, 'advanced': M, 'skipped_duplicate': K, 'failed': F}"""
        items = self._fetch_candidates()
        advanced = 0
        skipped_dup = 0
        failed = 0
        for item in items:
            try:
                if self._is_duplicate(item):
                    skipped_dup += 1
                    continue
                score = self._get_latest_score(item["id"])
                tags = self._extract_tags(item)
                self._update_lifecycle(item["id"], LIFECYCLE_REFINE)
                advanced += 1
                self.metrics.inc("t1_succeeded")
            except Exception as e:
                self.retry_policy.handle_failure("t1", item["id"], e)
                failed += 1
                self.metrics.inc("t1_failed")
        self.metrics.set("t1_candidates", len(items))
        return {
            "candidates": len(items),
            "advanced": advanced,
            "skipped_duplicate": skipped_dup,
            "failed": failed,
        }
```

### 4.3 T2 触发器（Task C1）

```python
# backend/services/triggers/t2_refine_to_link.py

class T2Trigger:
    """T2: kl:refine → kl:link
    
    流程：
    1. 查询 lifecycle='kl:refine' 的 items（无时间限制）
    2. entity 查找：item.concepts 里的每个 concept 名查 knowledge_items
    3. 写 knowledge_links (from=item.id, to=related.id, type='similar', confidence=0.7)
    4. 至少 1 个 link 才推进 lifecycle（找不到 link 也推进，但标 low_link）
    5. 更新 lifecycle='kl:link'
    """
    
    def run_once(self) -> dict:
        items = self._fetch_candidates()
        advanced = 0
        low_link = 0
        failed = 0
        for item in items:
            try:
                related_ids = self._find_related_items(item)
                if related_ids:
                    self._write_links(item["id"], related_ids)
                else:
                    low_link += 1
                self._update_lifecycle(item["id"], LIFECYCLE_LINK)
                advanced += 1
            except Exception as e:
                self.retry_policy.handle_failure("t2", item["id"], e)
                failed += 1
        return {
            "candidates": len(items),
            "advanced": advanced,
            "low_link": low_link,
            "failed": failed,
        }
```

---

## 5. 重试 + 死信（Task D1）

```python
# backend/services/retry_policy.py

import time
import functools
import logging
from typing import Callable, Tuple

logger = logging.getLogger("hotspot.retry")

DEFAULT_BACKOFF = (1, 5, 30)  # 3 次重试：1s / 5s / 30s


def with_retry(fn: Callable, max_attempts: int = 3, backoff: Tuple[int, ...] = DEFAULT_BACKOFF):
    """同步函数重试装饰器（最后一次失败抛异常）"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt < max_attempts - 1:
                    wait_s = backoff[min(attempt, len(backoff) - 1)]
                    logger.warning(
                        f"retry {fn.__name__} attempt={attempt + 1}/{max_attempts} "
                        f"wait={wait_s}s err={e}"
                    )
                    time.sleep(wait_s)
        raise last_exc
    return wrapper


class RetryPolicy:
    """业务级重试 + 死信写入"""
    
    def __init__(self, dead_letter_repo, metrics):
        self.dlq = dead_letter_repo
        self.metrics = metrics
    
    def handle_failure(self, trigger_name: str, item_id: str, error: Exception, payload: dict = None):
        """业务失败：增加 attempts，3 次后入死信"""
        existing = self.dlq.get_active(trigger_name, item_id)
        attempts = (existing.attempts if existing else 0) + 1
        if attempts >= 3:
            self.dlq.add(trigger_name, item_id, str(error), attempts, payload or {})
            self.metrics.inc(f"{trigger_name}_dead_letter")
            logger.error(f"{trigger_name} dead letter: item={item_id} attempts={attempts}")
        else:
            self.dlq.update_attempts(trigger_name, item_id, str(error), attempts)
            logger.warning(f"{trigger_name} retry scheduled: item={item_id} attempts={attempts}")
```

---

## 6. Prometheus 指标（Task D2）

```python
# backend/metrics/kl_metrics.py

class KLMetrics:
    """KL 状态机核心指标（无 prom client，纯 JSON counter/gauge）"""
    
    def __init__(self):
        self._counters = {
            "t1_triggered": 0,    # T1 跑的总轮数
            "t1_succeeded": 0,    # T1 推进成功的 items
            "t1_failed": 0,       # T1 失败的 items
            "t1_dead_letter": 0,  # T1 死信
            "t2_triggered": 0,
            "t2_succeeded": 0,
            "t2_failed": 0,
            "t2_dead_letter": 0,
        }
        self._gauges = {
            "by_stage_count": {  # 当前各阶段 items 数
                "kl:raw": 0, "kl:refine": 0, "kl:link": 0,
                "kl:structure": 0, "kl:publish": 0,
            }
        }
        self._histograms = {
            "t1_latency_ms": [],
            "t2_latency_ms": [],
        }
    
    def inc(self, name: str, n: int = 1):
        if name in self._counters:
            self._counters[name] += n
    
    def set_stage_counts(self, counts: dict):
        self._gauges["by_stage_count"].update(counts)
    
    def observe(self, name: str, value: float):
        if name in self._histograms:
            self._histograms[name].append(value)
            # 仅保留最近 100 个样本
            if len(self._histograms[name]) > 100:
                self._histograms[name] = self._histograms[name][-100:]
    
    def snapshot(self) -> dict:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "avg": sum(v) / len(v) if v else 0,
                    "p50": sorted(v)[len(v) // 2] if v else 0,
                    "p99": sorted(v)[int(len(v) * 0.99)] if v else 0,
                }
                for k, v in self._histograms.items()
            }
        }
```

API: `GET /api/kl/metrics` → 返回上述 snapshot JSON。

---

## 7. 调度器注册（Task E）

### 7.1 新增 3 个 job

| Job ID | 名称 | 触发器 | 间隔 |
|--------|------|--------|------|
| `kl_trigger_t1` | T1: kl:raw → kl:refine | IntervalTrigger | 60s |
| `kl_trigger_t2` | T2: kl:refine → kl:link | IntervalTrigger | 120s |
| `kl_dead_letter_retry` | 死信重试 | IntervalTrigger | 600s（10min）|

### 7.2 jobs.py 新增

```python
# backend/scheduler/jobs.py (追加)

import asyncio

# Phase 10: T1/T2 触发器
async def kl_trigger_t1_job() -> None:
    from backend.services.triggers.t1_raw_to_refine import T1Trigger
    try:
        t1 = T1Trigger()
        report = await asyncio.to_thread(t1.run_once)
        _logger.info(f"kl_trigger_t1_job: {report}")
    except Exception as e:
        _logger.error(f"kl_trigger_t1_job crashed: {e}")


async def kl_trigger_t2_job() -> None:
    from backend.services.triggers.t2_refine_to_link import T2Trigger
    try:
        t2 = T2Trigger()
        report = await asyncio.to_thread(t2.run_once)
        _logger.info(f"kl_trigger_t2_job: {report}")
    except Exception as e:
        _logger.error(f"kl_trigger_t2_job crashed: {e}")


async def kl_dead_letter_retry_job() -> None:
    from backend.services.retry_policy import RetryPolicy
    from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository
    try:
        repo = KLDeadLetterRepository()
        # 简单兜底：每 10min 把超过 1h 未解决的死信记 warn
        count = await asyncio.to_thread(repo.list_active_count)
        if count > 50:
            _logger.warning(f"kl_dead_letter_retry_job: {count} active dead letters (need manual review)")
    except Exception as e:
        _logger.error(f"kl_dead_letter_retry_job crashed: {e}")
```

### 7.3 scheduler.py 新增（3 个 add_job）

```python
# 在 scheduler.py 的 start() 末尾追加

# Phase 10: job 31 — T1 触发器（每 60s）
self.scheduler.add_job(
    jobs.kl_trigger_t1_job,
    trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
    id="kl_trigger_t1",
    name="KL T1 trigger: kl:raw -> kl:refine (every 60s)",
    replace_existing=True,
)
# Phase 10: job 32 — T2 触发器（每 120s）
self.scheduler.add_job(
    jobs.kl_trigger_t2_job,
    trigger=IntervalTrigger(seconds=120, start_date=_now_utc),
    id="kl_trigger_t2",
    name="KL T2 trigger: kl:refine -> kl:link (every 120s)",
    replace_existing=True,
)
# Phase 10: job 33 — 死信监控（每 600s）
self.scheduler.add_job(
    jobs.kl_dead_letter_retry_job,
    trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
    id="kl_dead_letter_retry",
    name="KL dead letter monitor (every 10min)",
    replace_existing=True,
)
```

---

## 8. 验收标准

### 8.1 单元测试门禁

- `test_kl_state_machine.py`：15/15 PASS
- `test_t1_trigger.py`：12/12 PASS
- `test_t2_trigger.py`：10/10 PASS
- `test_retry_policy.py`：8/8 PASS
- `test_kl_metrics.py`：5/5 PASS
- `test_phase10_integration.py`：6/6 PASS
- **总计**：56 用例全 PASS

### 8.2 行为验收

- T1 触发器：100 条 `kl:raw` 样本中 95%+ 成功推进到 `kl:refine`
- T2 触发器：80% `kl:refine` items 找到至少 1 个关联 concept/link
- 死信：单 item 失败 3 次自动入 `kl_dead_letters` 表
- 调度器：3 个新 job 启动后正常运行（日志可见每 60s/120s/600s 输出）
- 指标：`GET /api/kl/metrics` 返回 6 counters + by_stage_count gauge + 2 histograms

### 8.3 回归测试

- 所有 Phase 8 测试不退化（60+ 用例）
- 所有 Phase 9 测试不退化（50+ 用例）
- 编译检查：`backend/services/kl_state_machine.py` + `triggers/*.py` + `retry_policy.py` + `kl_metrics.py` 全部通过 `py_compile`

### 8.4 文档更新

- 创建 `docs/phase10_changelog.md`：记录 Phase 10 新增功能 + 文件清单
- 更新 `docs/hotspot_v2.0_dev_plan.md`：标记 Phase 10 状态为 ✅
- 更新 `docs/hotspot_v2.0_PRD.md`（如需要）：5 触发器实现状态

---

## 9. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | 旧 3 阶段 lifecycle 残留导致 T1 漏跑 | 中 | 中 | Phase 10 完成后执行 046 migration；T1 兼容 2 阶段值 |
| 2 | simhash 误判把不同 item 当重复 | 低 | 中 | T1 仅对 url_canonical 精确匹配做跳过，simhash 阈值 ≥ 5 才跳过 |
| 3 | T2 找不到 entity 关联导致大量 low_link | 高 | 低 | low_link 也推进 lifecycle（标 special_link_count=0），Phase 12 再优化 |
| 4 | ai_scores 表为空导致评分全 fallback 5.0 | 高 | 中 | fallback 5.0 视为正常；Phase 15 Hybrid AI 后评分精度提升 |
| 5 | 死信表无限增长 | 中 | 中 | 保留 30 天；Phase 12 写 dead_letter_cleanup job |
| 6 | 调度器 60s 太频繁导致 CPU 占用高 | 低 | 中 | T1 单轮候选 ≤ 50 个；超过则分批 |
| 7 | 状态机与 knowledge_sync 冲突 | 低 | 高 | 状态机仅直写 SQLite；knowledge_sync 仍走 file-first |
