# UI/UX 重构 Phase 子 PRD 索引

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0
> **范围**: Phase 1B - Phase 7（Phase 1A 已交付，commit `4968c7f`）
> **Goal 模式使用**: agent 按下表顺序拾取子 PRD 执行

---

## 0. 快速导航

| Phase | 目标 | 子 PRD | 预计 commit | 前置 |
|---|---|---|---|---|
| ✅ 1A | 设计系统骨架 | [PRD §3](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) | `4968c7f` (done) | — |
| ⏳ 1B | 拆 6 大文件 | [UIUX_PHASE_1B.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_1B.md) | `refactor(frontend): split 6 large files` | Phase 1A |
| ⏳ 2 | SecNews 4 组件 | [UIUX_PHASE_2.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_2.md) | `refactor(frontend): secnews token migration` | Phase 1A |
| ⏳ 3 | Knowledge 3 组件 | [UIUX_PHASE_3.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_3.md) | `refactor(frontend): knowledge token migration` | Phase 1A |
| ⏳ 4 | CodeGarden 5 组件 | [UIUX_PHASE_4.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_4.md) | `refactor(frontend): codegarden token migration` | Phase 1B |
| ⏳ 5 | 系统页 + 45 组件 | [UIUX_PHASE_5.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_5.md) | `refactor(frontend): system pages + 45 components` | Phase 2-4 |
| ⏳ 6 | 15 测试补强 | [UIUX_PHASE_6.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_6.md) | `test(frontend): 15 high-frequency tests` | Phase 1B-5 |
| ⏳ 7 | 验证 + push | [UIUX_PHASE_7.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_7.md) | `chore: UI/UX refactor complete` | Phase 1A-6 |

## 1. 依赖图

```
Phase 1A (✅ done)
  │
  ├──→ Phase 1B (split 6 large)
  │       │
  │       └──→ Phase 4 (codegarden refactor)
  │
  ├──→ Phase 2 (secnews)
  │
  ├──→ Phase 3 (knowledge)
  │
  └──→ Phase 5 (system + 45 components)  ← needs Phase 2/3/4
            │
            └──→ Phase 6 (15 tests)  ← needs Phase 1B-5
                      │
                      └──→ Phase 7 (verify + push)
```

## 2. Goal 模式拾取顺序（推荐）

| 顺序 | Phase | 原因 |
|---|---|---|
| 1 | Phase 1B | 必须先拆大文件，Phase 4 才能动 codegarden |
| 2 | Phase 2 | 独立子集，可与 Phase 3/4 并行 |
| 3 | Phase 3 | 独立子集 |
| 4 | Phase 4 | 依赖 Phase 1B 拆分 |
| 5 | Phase 5 | 收尾剩余组件 |
| 6 | Phase 6 | 测试补强 |
| 7 | Phase 7 | 收尾 |

**并行提示**: Phase 2 / 3 / 5 可独立并行（不互依赖），但**单 agent 串行执行更安全**（避免 git 状态混乱）。

## 3. 子 PRD 共同结构

每个子 PRD 包含 9 节：

| 节 | 用途 |
|---|---|
| 0. Goal | 一句话目标（goal 模式自动读取） |
| 1. 入口 / 出口 | 前置条件 + 交付物 |
| 2. In Scope | 必须做的具体文件 + 操作 |
| 3. Out of Scope | 明确不做的（避免越界） |
| 4. 改造规则 | 必须遵守的代码规则 |
| 5. 执行步骤 | 顺序的 step 列表 |
| 6. 验证清单 (DoD) | 可执行的验证命令 |
| 7. 风险与缓解 | 已知风险 + 缓解 |
| 8. 决策日志 | 已锁定的决策 |
| 9. 完成后 | 下一步触发 |

## 4. 完成定义（DoD，跨所有 Phase）

```bash
# 全项目 0 硬编码颜色
grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" | grep -v "^\s*//" | wc -l
# 期望: 0

# TypeScript 0 错误
cd frontend && npx tsc --noEmit
# 期望: 0 errors

# vitest 90+ PASS
cd frontend && npx vitest run
# 期望: Tests 90+ passed

# vite build < 12s
cd frontend && npm run build
# 期望: built in < 12s

# 后端 1283 PASS
.venv/bin/python3 -m pytest backend/tests/ -q
# 期望: 1283 passed

# 暗/亮双主题切换无视觉回归
# (浏览器手动验证)
```

## 5. 与 master PRD 的关系

- **master PRD**: 战略层（为什么做 / 范围 / 设计原则 / 决策）
- **子 PRD**: 战术层（怎么做 / 步骤 / 命令 / 风险）
- 任何冲突以 **master PRD 决策日志** 为准
- 子 PRD 中的新决策需回填到 master PRD §9

## 6. 状态更新机制

每完成一个子 PRD：
1. agent 在 master PRD §4.x 状态从 ⏳ 改为 ✅
2. agent 在 master PRD §10 复选框打勾
3. agent 在 commit message 中标注 `Phase X` 便于追溯

## 7. 参考与链接

- [UIUX_REFACTOR_PRD.md v1.0](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) — master PRD
- [UIUX_PHASE_1B.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_1B.md) — 拆 6 大文件
- [UIUX_PHASE_2.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_2.md) — SecNews
- [UIUX_PHASE_3.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_3.md) — Knowledge
- [UIUX_PHASE_4.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_4.md) — CodeGarden
- [UIUX_PHASE_5.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_5.md) — 系统页 + 45 组件
- [UIUX_PHASE_6.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_6.md) — 15 测试补强
- [UIUX_PHASE_7.md](file:///Users/duke/Documents/hotspot/docs/UIUX_PHASE_7.md) — 验证 + push
