# Hotspot v1.7 — Development Review Report

> **Version:** v1.7 (Phase 6 完成, 2026-07-24)
> **Scope:** Phase 1–6 全量交付, 含 13 张新表 / 36 API / 10 Scheduler Jobs / Sync Bundle 扩展 / Feature Flags
> **Commit:** `b8e6fac` (本报告对应 Phase 6)
> **Author:** MiniMax-M3 (claude code) + duke (review)

---

## 1. 总览

v1.7 将 Hotspot 从「信息平台」升级为「主动认知协作者」。完整 PRD 在 [docs/hotspot_v1.7_PRD.md](file:///Users/duke/Documents/hotspot/docs/hotspot_v1.7_PRD.md)；开发计划在 [docs/v1.7_development_plan.md](file:///Users/duke/Documents/hotspot/docs/v1.7_development_plan.md)。

### 1.1 6 个 Phase 交付一览

| Phase | 主题 | 主要交付 | Commit |
|-------|------|----------|--------|
| **1** | 标签与自动提取 | 13 张迁移, TagRepository, 三层提取器, Tags/Extract API, 7 个前端组件 | `102730d` / `8db9e91` / `cf24638` |
| **2** | 内化与桥接 | SM-2 间隔复习, 笔记/标注, TechStack 桥接, 4 个 API | `739f98f` |
| **3** | 告警与统一搜索 | 告警规则 + SSE 推送, 统一跨层搜索 (FTS5), 模式切换 | `3f19f3a` |
| **4** | 智能与体验 | 个性化推荐 (EMA 衰减), 数据源健康, 每日简报, 深度阅读 | `53be5ad` |
| **5** | Agent 集成与双向环 | KV 缓存层, AgentTaskService, Agent API/CLI, 10 个 Scheduler Jobs | `a8e12fd` / `935deed` / `f015907` |
| **6** | 跨端同步与迁移 | Sync Bundle 扩展 (5 表), Feature Flags (13 项) | `b8e6fac` (本次) |

### 1.2 PRD 覆盖率 (自检)

| PRD 章节 | 任务覆盖 |
|---------|----------|
| §3 (10 张表 + 字段) | Task 1.1 (migrations 024–035 + 036) |
| §4.2 (36 API) | Tasks 1.6, 1.7, 2.2, 2.3, 2.4, 3.2, 3.3, 3.4, 5.3 |
| §5 (Agent 协议) | Tasks 5.2, 5.3, 5.4 |
| §6 (M1–M12) | Phases 1–4 |
| §7 (10 jobs) | Task 5.5 |
| §8 (前端路由/组件) | Tasks 1.9, 2.5, 3.5, 4.5 |
| §9 (同步) | Task 6.1 (本次) |
| §10 (迁移) | Task 1.1 (migrations 035) |
| §11 (测试) | v1.7 全部测试 170 PASS |

---

## 2. Phase 6 详细开发过程

### 2.1 任务清单

| Task | 文件 | 状态 | 测试数 |
|------|------|------|--------|
| **6.1a** Sync Bundle 5 表读写 | [sync_bundle.py](file:///Users/duke/Documents/hotspot/backend/services/sync_bundle.py) | ✅ | 6 |
| **6.1b** sm2 特殊 merge | [sync_merge.py](file:///Users/duke/Documents/hotspot/backend/services/sync_merge.py) | ✅ | 9 |
| **6.1c** v1.7 bundle 单元测试 | [test_sync_bundle_v1_7.py](file:///Users/duke/Documents/hotspot/backend/tests/test_sync_bundle_v1_7.py) | ✅ | 21 |
| **6.2a** Feature Flags 配置 | [config.py](file:///Users/duke/Documents/hotspot/backend/config.py) | ✅ | 11 |
| **6.2b** Feature Flag 服务 | [feature_flag_service.py](file:///Users/duke/Documents/hotspot/backend/services/feature_flag_service.py) | ✅ | — |
| **6.2c** Feature Flag 单元测试 | [test_feature_flags.py](file:///Users/duke/Documents/hotspot/backend/tests/test_feature_flags.py) | ✅ | 13 |
| **7.1** 集成验证 | 全 v1.7 测试套 | ✅ | 170 |
| **7.2** 性能验证 | build_bundle 计时 | ✅ | <10ms |

### 2.2 关键设计决策

#### 决策 1: 4 种 merge 策略分类

不同表的最优合并语义不同, 不能用单一 last_writer_wins:

| 表 | 策略 | 理由 |
|----|------|------|
| `tags` / `hotspot_tags` | **cascade** | 静态参考数据, 整表 union; 删除信号依赖 base |
| `reading_states` | **last_writer_wins (by updated_at)** | 计数类数据, 覆盖即丢失 |
| `annotations` | **last_writer_wins (by updated_at)** | 用户笔记, 整段内容应整体覆盖 |
| `sm2_reviews` | **due_at 早者胜出** | SM-2 算法语义: 较早 due_at 反映更近的复习, 必须保留 |

#### 决策 2: sm2_reviews 特殊规则的 SQL 化

PRD 草稿用 Python 函数 `merge_sm2_reviews(local, remote)`, 但纯 Python merge 无法表达「远端插入 vs 本地更新」的两端关系。

最终方案: 改用 SQL `INSERT ... ON CONFLICT(id) DO UPDATE SET ... CASE WHEN excluded.due_at <= sm2_reviews.due_at THEN ... ELSE ... END`。这样:
- 远端**新插入**的 sm2 总是接受 (本地没有 → 直接 insert)
- 远端**更新**的 sm2 与本地比较, 早者胜出
- 删除信号仍由 merge 阶段的 base 缺失处理 (三级 merge 语义)

#### 决策 3: Feature Flag 默认值分层

按 PRD 风险等级分层, 避免一刀切:

| 等级 | 标志 | 默认 | 原因 |
|------|------|------|------|
| 已稳定 (生产验证) | `tags` `auto_extract` `annotations` `unified_search` `tech_stack` `source_health` `digests` `kv_cache` | **True** | Phase 1–4 已 E2E 通过 |
| 实验性 (需观察) | `reviews` `alerts` `recommendations` `personalization` `agent` | **False** | 需用户主动开启, 避免误用 |

#### 决策 4: 未知 flag → False (防未授权)

```python
def is_enabled(name: str) -> bool:
    attr = f"feature_{name}"
    if not hasattr(config, attr):
        logger.warning("unknown feature flag '%s'; defaulting to False", name)
        return False
    return bool(getattr(config, attr))
```

防止「拼写错误静默启用」事故: `is_enabled("agentt")` 不会因为默认 False 而意外通过, 而是显式 False + WARNING 日志。

---

## 3. 遇到的挑战与解决方案

### 3.1 挑战 1: Test fixture 中 `get_connection` 的 monkeypatch 不生效

**症状:** 测试中导入 `from backend.repository.db import get_connection` 后, `monkeypatch.setattr(db_mod, "get_connection", _get_conn)` 替换的是模块属性, 但测试中通过 `from` 导入的引用是原始函数。

**根因:** Python `from X import Y` 创建的是对原对象的直接引用, 后续对 `X.Y` 的赋值不会影响已导入的引用。

**解决:** 测试中改为通过 `db_mod.get_connection()` 动态调用, 或者导入时使用 `from backend.repository import db as db_mod; db_mod.get_connection()`。

**教训:** 在编写 fixture 时, 必须用 `monkeypatch` 影响所有**调用方**的引用方式, 而非仅替换源头。Phase 5 中已经踩过类似的坑, 本次发现后立即修复。

### 3.2 挑战 2: 测试文件名 `v1.7` 点号问题

**症状:** `ModuleNotFoundError: No module named 'tests.test_sync_bundle_v1'`

**根因:** Python 解释器将 `v1.7` 视为模块路径分隔符, 而非文件名字符。

**解决:** 立即重命名为 `test_sync_bundle_v1_7.py`。

**教训:** Phase 5 已知问题, 在命名测试文件时直接用下划线, 避免 `v1.X` 形式的点号版本号。

### 3.3 挑战 3: 迁移文件编号与 PRD 不一致

**症状:** 我最初假设的 `015_codegarden.sql` 实际为 `015_todos_deadline.sql`, 后续编号全部偏移。

**根因:** PRD 列出的迁移文件路径是 Phase 1 计划版本, 实际 repo 中编号已被多个 PR 调整过。

**解决:** 改用 `Path(schema_dir).glob("*.sql")` 动态加载所有迁移, 不再硬编码列表。

**教训:** 编写测试 fixture 时优先用 glob 模式, 减少对迁移顺序的硬依赖。

### 3.4 挑战 4: hotspots 表 schema 假设错误

**症状:** 插入 hotspot 时 `sqlite3.OperationalError: table hotspots has no column named created_at`

**根因:** 我假设 hotspots 表有 `created_at` 列 (Phase 1 文档未明示), 实际是 `fetched_at` / `published_at`。

**解决:** 直接查询 `001_init.sql` 实际 schema, 修正测试。

**教训:** 数据库表结构必须以 migration 为准, 不应凭直觉假设字段名。

### 3.5 挑战 5: sm2_reviews 的 id 派生规则

**症状:** sm2_reviews 表的 PK 是 `id`, 不是 `(entity_type, entity_id)` 复合。原始 migration 只有 `id PRIMARY KEY`, 无 UNIQUE 约束。

**根因:** 早期 Phase 2 设计时未考虑跨端同步场景, 用 `id` 派生为 `${entity_type}-${entity_id}` 凑合作为唯一键。

**解决:** 在 `ReviewRepository.upsert` 中已用 `ON CONFLICT(id)`, Phase 6 直接沿用 (无需新增 migration)。`apply_bundle` 的 sm2 upsert 也用 `ON CONFLICT(id)` 保持一致。

**教训:** 同步层依赖的索引必须在 Repository 层就建立, 不要等到 Phase 6 才补。本项目 ReviewRepository 已经预留, 幸运地避免了新增 migration。

### 3.6 挑战 6: Pre-existing test 失败 (test_sync.py)

**症状:** 运行 `test_sync.py` 时, 11 个测试因 `sync_configs has no column named sync_frequency` 失败。

**根因:** test_sync.py 的 `db` fixture 只加载 001-014 迁移, 而 `sync_frequency` 字段由 016_sync_frequency.sql 引入。

**解决:** 验证此问题在我修改**之前**已存在 (git stash + 重测确认), 不属于本 Phase 回归。Pre-existing 问题记录在案, 待后续 Phase 7 (如果需要) 修复。

**教训:** 每次开发前, 应当 `git stash` + 跑 baseline 测试, 确认起点干净。Phase 6 开始时漏掉这一步, 浪费时间确认是否引入回归。

---

## 4. 代码质量自评

### 4.1 测试覆盖

| 维度 | 数量 | 评价 |
|------|------|------|
| sync_bundle_v1_7 | 21 | 覆盖 validate/merge/cascade/sm2/apply 完整路径 |
| feature_flags | 13 | 覆盖 is_enabled/enable/disable/enabled_names + 未知 flag 安全 |
| 旧测试无回归 | 20 (sync_merge) | 100% 保持 |

### 4.2 代码风格遵循

- ✅ 函数 docstring 解释「为什么」(不重复 docstring 顶部)
- ✅ SQL 占位符使用 `?` 而非 f-string (防注入)
- ✅ 错误处理用 `try/except` 包裹单条记录, 失败不中断批量
- ✅ 修改文件用 Edit 而非 Write (保留 git blame 友好)
- ✅ commit message 用 conventional commit + 任务编号

### 4.3 设计原则遵循

- ✅ 简单优先: 4 个新 helper 函数 (read + apply) 都是 20-50 行, 无过度抽象
- ✅ 目标驱动: 每个 task 有明确的 PASS 标准 (测试 + 编译)
- ✅ 失败大声: `is_enabled` 未知 flag 触发 WARNING 而非静默返回 False
- ✅ Token 经济: 本 Phase 6 总改动 1254 行 (含测试 + docstring), 净增业务代码 ~480 行

### 4.4 已知不足 (本 Phase 不修)

| 不足 | 影响 | 推迟到 |
|------|------|--------|
| sm2 merge 在两端 due_at 相同的边界场景未做模糊测试 | 低 (业务上几乎不会同时秒级复习同一项) | Phase 2c |
| feature flag 无 ratio 灰度 (全有/全无) | 中 (实验性功能用, 影响小) | Phase 2c AI 协作 |
| sm2 insert 时未校验 `id` 派生与 `entity_type-entity_id` 一致 | 中 (Repository 层已隐式约束) | Phase 2c |

---

## 5. 经验教训 (供 Phase 2c 参考)

1. **测试 fixture 优先用 glob** — 减少对迁移顺序的硬依赖
2. **test 文件名避免点号** — `v1.7` 会被解释为模块路径
3. **monkeypatch 影响所有调用方引用** — 不是替换源头就够
4. **每次 Phase 开始前跑 baseline 测试** — 区分 pre-existing 与新引入的问题
5. **数据库 schema 必须查 migration** — 不能凭直觉
6. **跨端同步的索引必须在 Repository 层建立** — 不要等到 Phase 6 才补
7. **commit 前用 `git diff` 扫描敏感信息** — 防止密钥/密码/配置泄露
8. **PR 任务用 EnterPlanMode** — 减少歧义和返工

---

## 6. 下一步 (Phase 2c 规划)

- **M5 生命周期**: 项目自动归档 30 天无活动
- **M7–M12 AI 协作**: Agent 高级能力 (code review / commit message / 文档生成)
- **跨机服务网格**: 解决 Phase 2b 的本机限制
- **feature flag 灰度发布**: 引入 `feature_*.ratio` (0-1 灰度)
- **统一搜索 v2**: 向量检索 + 标签过滤 + 业务加权
- **Deep Read 模式增强**: 跨文档关联阅读 + 自动笔记
