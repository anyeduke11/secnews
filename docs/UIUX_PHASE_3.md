# Phase 3 子 PRD — Knowledge 知识库改造

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §4.3
> **前置依赖**: Phase 1A ✅
> **预计 commit**: `refactor(frontend): knowledge base UI token migration (Phase 3)`

---

## 0. Goal (一句话)

Knowledge 知识库 3 个核心组件 token 化 + 暗/亮双主题适配，重点是 Recharts 知识图谱的 theme switching 与 LearningPanel 的 MasteryGauge 颜色规范化。

## 1. 入口 / 出口

- **入口**: Phase 1A 交付（token 完整）
- **出口**: KnowledgeGraph / KnowledgePage / LearningPanel 0 硬编码颜色、暗/亮主题切换无视觉断裂

## 2. In Scope（必须做）

| # | 组件 | 文件 | 改造重点 |
|---|---|---|---|
| 1 | KnowledgeGraph | [KnowledgeGraph.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/KnowledgeGraph.tsx) (3.7KB) | Recharts 暗/亮主题 + 节点色用 cat-* |
| 2 | KnowledgePage | [KnowledgePage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/KnowledgePage.tsx) (16KB) | EmptyState 接入 + 列表 token 化 |
| 3 | LearningPanel | [LearningPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/LearningPanel.tsx) (4.8KB) | MasteryGauge 暗/亮适配 |

## 3. Out of Scope（明确不做）

- ❌ **不拆文件**（KnowledgePage 16KB 接近阈值但未在 Phase 1B 列表，保持）
- ❌ **不改知识图谱数据模型**（仅改渲染层）
- ❌ **不动 ConceptDetailDialog / MasteryGauge 业务逻辑**（仅颜色）
- ❌ **不引入 Recharts 新组件**
- ❌ **不启用 Newsreader 衬线字体**（master PRD 决策 4，Phase 3 暂缓）

## 4. 改造规则（必须遵守）

### 4.1 KnowledgeGraph（Recharts 适配）

Recharts 接受 `stroke` / `fill` 字符串。规则：
- 节点色: `getComputedStyle().getPropertyValue('--color-ai')` 读取后传入
- 边色: `var(--border-color)` 经 getComputedStyle 转 RGB
- tooltip 背景: `var(--bg-elevated)` 转 RGB
- 文字色: `var(--text-primary)` 转 RGB

监听 theme 变化，组件 unmount 时清理 listener。

### 4.2 KnowledgePage（列表 token 化）

- 概念列表项 hover 用 `bg-dark-hover` / `var(--bg-hover)`
- 选中态用 `var(--accent-highlight)`
- 标签 chip 用 `cat-*` 系列
- 空数据时用 `<EmptyState title="暂无概念" description="去 L1 资料库导入或新建一个概念" />`

### 4.3 LearningPanel + MasteryGauge

- 进度环颜色: `var(--color-success)` (高分) / `var(--color-warning)` (中分) / `var(--color-error)` (低分)
- 背景环: `var(--border-color)`
- 文字: `var(--text-primary)`
- 暗/亮主题通过 CSS 变量自动适配（无需 useEffect）

## 5. 执行步骤

### Step 1: KnowledgeGraph

1. `Read frontend/src/components/KnowledgeGraph.tsx`
2. 引入 `useTheme` hook
3. 添加 `getRechartsTheme(theme: 'dark' | 'light')` 工具函数，返回 colors 对象
4. useEffect 监听 theme 变化，setColors 重新渲染
5. 验证 dev 模式下切换主题

### Step 2: KnowledgePage

1. 替换硬编码颜色
2. 列表项 / 详情面板 token 化
3. EmptyState 接入（检查点：filters 清空时显示）
4. Loading 态用 LoadingSkeleton

### Step 3: LearningPanel

1. MasteryGauge 颜色分级 token 化
2. 任务列表 token 化
3. 进度条 token 化

### Step 4: 浏览器验证

1. `/knowledge` 路径切换暗/亮
2. 触发空数据态（mock 0 概念）
3. 切换 MasteryGauge 不同分数段

## 6. 验证清单（DoD）

```bash
# 1. 3 文件 0 硬编码颜色
grep -E "#[0-9a-fA-F]{3,8}" frontend/src/components/KnowledgeGraph.tsx frontend/src/components/KnowledgePage.tsx frontend/src/components/LearningPanel.tsx | grep -v "^\s*//" | wc -l
# 期望: 0

# 2. 类型 + 测试
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run

# 3. MasteryGauge 状态色使用
grep -E "color-success|color-warning|color-error" frontend/src/components/MasteryGauge.tsx
# 期望: 至少 3 处
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Recharts 主题切换不响应 | 监听 theme 属性变化，setColors 强制 re-render |
| MasteryGauge 颜色对比度不足 | 借用 ui-ux-pro-max 规则：暗 mode text ≥ 4.5:1 |
| KnowledgePage 16KB 接近阈值 | 暂不拆，标记为 Phase 1B 候选（不在本 phase 范围） |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| Recharts 颜色来源 | getComputedStyle 转 RGB | 唯一支持 CSS 变量同步的方案 |
| 衬线字体 | 不启用 | master PRD 决策 4 暂缓 |
| KnowledgePage 拆分 | 不在 Phase 3 | 与 1B 职责分离 |

## 9. 完成后

- 提交 commit: `refactor(frontend): knowledge base UI token migration (Phase 3)`
- 触发 Phase 4 PRD
- 更新 master PRD §4.3 状态为 ✅
