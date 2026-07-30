# Phase 4 子 PRD — CodeGarden 项目管理改造

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §4.4
> **前置依赖**: Phase 1A ✅ + Phase 1B（3 大文件已拆为子目录）
> **预计 commit**: `refactor(frontend): codegarden UI token migration (Phase 4)`

---

## 0. Goal (一句话)

CodeGarden 5 个核心组件 100% token 化，重点是 ServiceTopology 的 SVG 拓扑颜色、EventBus 的事件状态色、PlaybookList 的 monospace 渲染与 Tab 切换动效。

## 1. 入口 / 出口

- **入口**: Phase 1B 完成（3 大文件拆为目录+子文件）
- **出口**: CodegardenPage / CodegardenPhase2bPage / ServiceTopology / EventBus / PlaybookList 0 硬编码颜色、状态色（success/warning/error）应用、暗/亮双主题无视觉断裂

## 2. In Scope（必须做）

| # | 组件 | 文件 | 改造重点 |
|---|---|---|---|
| 1 | CodegardenPage | [CodegardenPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/CodegardenPage.tsx) (7.4KB) | ProjectCard/ProjectList 状态统一 |
| 2 | CodegardenPhase2bPage | [CodegardenPhase2bPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/CodegardenPhase2bPage.tsx) (5.0KB) | Tab 切换动效 token 化 |
| 3 | ServiceTopology | [ServiceTopology.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ServiceTopology.tsx) (7.3KB) | SVG 拓扑颜色用 cat-* |
| 4 | EventBus | [EventBus.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/EventBus.tsx) (10KB) | 事件流 token 化 + 状态色 |
| 5 | PlaybookList | [PlaybookList.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/PlaybookList.tsx) (5.1KB) | YAML 渲染 monospace token 化 |

## 3. Out of Scope（明确不做）

- ❌ **不拆 EventBus 10KB**（不在 1B 列表）
- ❌ **不动 Phase 2b 后端 API**（业务逻辑层）
- ❌ **不改 ProjectCard / ProjectList 业务**（仅颜色 + EmptyState）
- ❌ **不引入新图表库**（SVG 拓扑保持自实现）
- ❌ **不改 Playbook YAML 解析**

## 4. 改造规则（必须遵守）

### 4.1 ServiceTopology（SVG 适配）

SVG 元素的 `fill` / `stroke` 不支持 CSS 变量直接绑定。规则：
- 节点填充: `getComputedStyle().getPropertyValue('--cat-*')` 转 RGB
- 节点边框: `var(--border-color)` 同理转 RGB
- 连线: `var(--text-muted)` 转 RGB
- 文本: `var(--text-primary)` 转 RGB
- useEffect 监听 theme 变化，重新设置所有 SVG 元素属性

### 4.2 EventBus（事件状态色）

事件状态映射：
- `pending`: `var(--color-warning)`
- `running`: `var(--color-info)`
- `success`: `var(--color-success)`
- `failed`: `var(--color-error)`
- 时间戳文字: `var(--text-muted)`
- 事件卡片背景: `var(--bg-card)` / hover `var(--bg-hover)`

### 4.3 PlaybookList（monospace token 化）

- YAML 代码块: `bg-dark-card` + `text-text-main`，字体 `font-mono`（已默认）
- 步骤序号: `var(--color-ai)`
- 状态徽章: 复用 §4.2 的 4 色映射
- 折叠按钮: `var(--text-secondary)` hover `var(--text-primary)`

### 4.4 Tab 切换动效（CodegardenPhase2bPage）

- active tab: 底色 `var(--bg-card)`、文字 `var(--text-primary)`、下划线 `var(--color-ai)`
- inactive tab: 文字 `var(--text-muted)` hover `var(--text-secondary)`
- 切换 transition: `var(--duration-normal) var(--ease-out)`

## 5. 执行步骤

### Step 1: CodegardenPage

1. ProjectCard hover 态统一
2. ProjectList Empty 态接入
3. Status badge token 化（project.status: active/archived/paused）

### Step 2: CodegardenPhase2bPage

1. Tab 切换动效 token 化
2. Header 6 个 phase 入口按钮统一
3. Empty 态 / Loading 态用统一组件

### Step 3: ServiceTopology

1. 引入 `useTheme`
2. 抽 `getSvgTheme(theme)` 函数
3. useEffect 监听 theme，重新设置所有 SVG 节点/边/文字属性
4. 验证 dev 模式切换主题无残留旧色

### Step 4: EventBus

1. 状态色映射抽 `EVENT_STATUS_COLORS` 常量
2. 事件列表 Empty 态
3. 时间戳 format 统一（用 `Intl.DateTimeFormat`）

### Step 5: PlaybookList

1. YAML 块 monospace 样式统一
2. 步骤展开/折叠动效
3. 状态色复用 §4.2

### Step 6: 浏览器验证

1. 切换暗/亮，确认 SVG 拓扑刷新正确
2. 触发空数据（mock 0 服务）
3. 切换 EventBus 5 种 status

## 6. 验证清单（DoD）

```bash
# 1. 5 文件 0 硬编码颜色
grep -E "#[0-9a-fA-F]{3,8}" frontend/src/components/CodegardenPage.tsx frontend/src/components/CodegardenPhase2bPage.tsx frontend/src/components/codegarden/ServiceTopology.tsx frontend/src/components/codegarden/EventBus.tsx frontend/src/components/codegarden/PlaybookList.tsx | grep -v "^\s*//" | wc -l
# 期望: 0

# 2. 类型 + 测试
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run

# 3. SVG 主题切换
grep -E "useTheme|getComputedStyle" frontend/src/components/codegarden/ServiceTopology.tsx
# 期望: 至少 1 处
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| SVG 切换残留旧色 | 切换时 setAttribute 而非 React props，确保 DOM 更新 |
| EventBus 状态色对比度 | 借用 ui-ux-pro-max 规则：4.5:1 minimum |
| Tab 动效卡顿 | 用 CSS transition 而非 JS animation |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| SVG 颜色传递 | setAttribute + getComputedStyle | 兼容 React + DOM 直接操作 |
| 状态色统一 | 5 色映射常量 | 跨组件复用 |
| Tab 动效 | CSS transition | 性能优于 JS |

## 9. 完成后

- 提交 commit: `refactor(frontend): codegarden UI token migration (Phase 4)`
- 触发 Phase 5 PRD
- 更新 master PRD §4.4 状态为 ✅
