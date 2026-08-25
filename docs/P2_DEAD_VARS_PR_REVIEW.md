# P2-2: pk_map dead variable PR 评审留档

> **状态**：✅ 已执行方案 A (2026-08-25, 用户指示"继续未完成的重构任务"后落地)
> **文件**：`backend/api/sync.py:352` (`resolve_all_conflicts` 函数)
> **关联**：P0 audit §2.2 表中 pk_map 标 "高风险（业务关键路径）"
> **关联 commit**：`5fe965a7` (P2-1 已 rename 其他 17 个 production F841)
> **日期**：2026-08-25

## 1. 现象

`backend/api/sync.py:352` 中 `pk_map` 被 ruff 报为 F841 dead variable：

```python
# backend/api/sync.py:352-358
pk_map = {
    "favorites": "hotspot_id",
    "todos": "source_id",
    "skills": "name",
    "custom_sources": "url",
    "secrets": "name",
}
count = 0
if isinstance(table_data, list):
    for item in table_data:
        item["_conflict_resolved"] = req.choice
        count += 1
```

`pk_map` 定义后从未被消费。函数 `resolve_all_conflicts` 对所有 item 统一设置 `_conflict_resolved = req.choice`，未使用 pk 列做匹配。

## 2. 同模块另一处 pk_map（对照）

`backend/api/sync.py:307` 在 `resolve_conflict`（单条裁决）函数中也有一个 `pk_map`，**但功能正确**：

```python
# backend/api/sync.py:304-321
if isinstance(table_data, list):
    found = False
    for item in table_data:
        pk_map = {                            # ← 在循环内每次重建 (inefficient)
            "favorites": "hotspot_id",
            "todos": lambda x: f"{x.get('source_type', '')}::{x.get('source_id', '')}",
            "skills": "name",
            "custom_sources": "url",
            "secrets": "name",
        }
        pk_fn = pk_map.get(req.record_type)
        if pk_fn is None:
            break
        key = pk_fn(item) if callable(pk_fn) else item.get(pk_fn)
        if key == req.record_key:
            item["_conflict_resolved"] = req.choice
            found = True
            break
```

L307 的 `pk_map` 在循环内部每次迭代重建（性能小瑕疵），但 `pk_fn = pk_map.get(...)` 和 `key = pk_fn(item)` 真消费了变量。ruff 不报 F841。

## 3. 业务风险评估

### 3.1 当前行为（删除前后行为不变）

`resolve_all_conflicts` 是 v1.3.0 引入的**简化版**批量裁决 API（`@router.post("/conflicts/auto-resolve")`）：

- 客户端调用 `POST /api/sync/conflicts/auto-resolve`，传 `record_type` 和 `choice`
- 服务端对 merged_bundle 中该表的所有 item 统一设置 `_conflict_resolved = req.choice`
- **不区分** record_key，所以不需要 pk_map

**删除 L352 的 pk_map 后**：行为完全不变（原本就未消费）。

### 3.2 未来"逐条裁决"扩展

如果未来要实现"按 record_key 逐条裁决"（即 `resolve_conflict` 的批量版），`pk_map` 必须重新引入，且需要：
1. 提取 `pk_map` 为模块级常量（DRY，L307 和 L352 共享）
2. 在 `resolve_all_conflicts` 中实现 `for item in table_data: key = pk_map[item]; ...`
3. 配套测试 `test_sync.py::test_auto_resolve_respects_pk`

### 3.3 sync 协议业务关键性

sync 协议涉及多端数据合并（local ↔ remote），pk 列是冲突检测和去重的基础。但 `resolve_all_conflicts` 当前实现里 pk 完全不参与——业务关键性体现在 L307 的 `resolve_conflict`，**不在 L352**。

## 4. 删除方案

### 方案 A：直接删除（推荐）

```python
# 删除 backend/api/sync.py:352-358 的 pk_map 块
# 保留：
count = 0
if isinstance(table_data, list):
    for item in table_data:
        item["_conflict_resolved"] = req.choice
        count += 1
```

**优点**：
- ruff F841 → 0（production 全部清理）
- 当前行为零变化
- 未来需要时再重新引入

**缺点**：未来重写 `resolve_all_conflicts` 时需要重新引入 pk_map。

### 方案 B：合并 L307 + L352 的 pk_map 到模块级常量

```python
# backend/api/sync.py 模块顶部
PK_MAP: dict[str, str | Callable] = {
    "favorites": "hotspot_id",
    "todos": lambda x: f"{x.get('source_type', '')}::{x.get('source_id', '')}",
    "skills": "name",
    "custom_sources": "url",
    "secrets": "name",
}
# 同时改造 resolve_all_conflicts 使用 PK_MAP 做真正的逐条裁决
```

**优点**：DRY，未来扩展有现成基础。
**缺点**：本次 commit 范围扩大（涉及功能改进而非纯 dead code 删除），需要更大评审。

### 方案 C：保留 + 加 `del` 占位 + TODO 注释

```python
# PK_MAP 占位 — 当前 resolve_all_conflicts 是简化版批量裁决,
# 不逐条指定 record_key, 故不消费 PK_MAP.
# 待 Phase: 实现真正的逐条裁决时, 引入 PK_MAP 做 key 匹配.
_PK_MAP = {
    "favorites": "hotspot_id",
    "todos": "source_id",
    "skills": "name",
    "custom_sources": "url",
    "secrets": "name",
}
del _PK_MAP  # noqa: F841
```

**优点**：保留意图、IDE 静音警告、调用方不破坏。
**缺点**：dead code 依然存在，仅是命名层面"已治理"。

## 5. 推荐：方案 A

理由：
1. **范围最小**：纯 dead code 删除，1 行 ruff 警告 → 0，不改逻辑
2. **回归测试最稳**：现有 `test_sync_api.py::test_auto_resolve_*` 覆盖 `_conflict_resolved = choice` 路径，删除 pk_map 后行为不变
3. **未来重构独立**：若要做"逐条裁决"，单独开 PR 走方案 B，本次只清 dead code

## 6. 评审检查清单

执行方案 A 前请确认：

- [ ] `backend/tests/test_sync_api.py` 中 `test_auto_resolve_*` 通过
- [ ] `backend/tests/test_sync.py` 全过
- [ ] 手动 e2e：调用 `POST /api/sync/conflicts/auto-resolve` 后，`merged_bundle` 中 `_conflict_resolved` 正确设置
- [ ] 删除 L352-358 后 grep `pk_map` 只剩 L307 一处
- [ ] 同步在 P0_AUDIT.md §2.2 表中 pk_map 行标注 "✅ 已删 (commit XXXX)"

## 7. 关联留档

- P0_AUDIT.md §2.2 表：pk_map 标 "高（注释中"同步方向"）"
- PROGRESS.md L838 记录 P2-2 待 PR 评审
- backend/api/sync.py 注释 v1.3.0 简化实现 — 记录了简化决策的版本

## 8. 实施建议

执行人（agent 或开发者）：

1. **不在本次 P2 commit 删 pk_map**（避免越界 PR 评审）
2. **下次开 PR 时**：附此文档第 1-7 节作为 PR description
3. **PR 标题建议**：`refactor(sync): 删除 resolve_all_conflicts 中 dead pk_map (F841)`
4. **PR 模板**：附 ruff 输出前后对比 + 1 张 e2e 截图 + 1 段方案 A 的 diff

## 9. 决议执行记录 (2026-08-25)

方案 A 落地，**并发现一个比死变量更严重的前置 bug**：

### 9.1 新发现: 两个裁决端点存在 AttributeError → 500 (已修)

`resolve_conflict` 与 `resolve_all_conflicts` 原代码:

```python
state = state_repo.get_by_config(cfg.id)   # 返回 dict(row), 列名 bundle_json
...
merged = json.loads(state.merged_bundle) if isinstance(state.merged_bundle, str) else ...
```

`get_by_config` 返回**普通 dict**, `.merged_bundle` 属性访问必然 `AttributeError`
(且表中根本没有 `merged_bundle` 列, 实际列名为 `bundle_json`)。
即两个端点在"有同步状态"的正常路径上**从未成功返回过 200** — 这也解释了为何
此前不存在任何 auto-resolve 测试 (§5 清单假设的 `test_auto_resolve_*` 并不存在)。

修复: 改为 `state["bundle_json"]`; 状态行为 None 的 404 分支保持不变。

### 9.2 执行清单核验

- [x] 补齐表征测试后再删 (原清单假设的测试不存在, 按 "锁行为不锁实现" 先补):
      `test_conflicts_resolve_marks_matching_key` / `_missing_key_404` /
      `test_conflicts_auto_resolve_marks_all_items` / `_unknown_table_404`
      (`backend/tests/test_sync_api.py`, 4 个新测试全过)
- [x] test_sync_api.py + test_sync.py 全过 (43 passed)
- [x] e2e: TestClient 走真实 API 路径, 断言 merged_bundle 中
      `_conflict_resolved` 正确设置 (单条只标匹配 key; 批量全表标记 + count)
- [x] 删除后 grep `pk_map`: 仅剩 L307 一处 (且移出 for 循环 — 循环不变量,
      §2 提到的性能小瑕疵顺手消除)
- [x] P0_AUDIT.md §2.2 pk_map 行标注 ✅ 已删

### 9.3 结果

- ruff `backend/ --select F401,F841` → **All checks passed** (P2 目标 0/0 首次真正达成)
- 未来若实现"逐条裁决批量版", 按本档 §3.2 方案 B 重引入模块级 PK_MAP
