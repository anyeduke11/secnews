# frontend/src — Agent Context

> **就近作用域**:此文件仅承载 `frontend/src/` 子树进入时即时需要的约束。
> 跨项目路由、设计技能选择、根级命令见根 `AGENTS.md`。
> 不要在本文件重复项目级 Dev / Test 指令 — 只写"此目录有而根级没有"的近邻规则。

## 子树身份

React 18 + TypeScript + Vite 5 + Tailwind 3 SPA(后端固定 127.0.0.1:8000,
前端 dev 端口 `8898`,严格端口,启动命令见根 AGENTS.md)。

| 子目录 | 角色 | 互斥命名 |
|--------|------|----------|
| `components/` | 业务组件,PascalCase,与同名 `.test.tsx` 并排放置 | 严禁 `*.component.tsx`、kebab-case、camelCase 组件名 |
| `components/action/`、`components/codegarden/`、`components/data/` | 按领域分子目录,组件仍 PascalCase | 子目录内禁止再嵌 `components/` 子目录 |
| `hooks/` | 自定义 hook,`useXxx.ts` | 禁止 `useXxx.tsx`、禁止 PascalCase |
| `routes/` | 路由表 + 页面级容器组件 | 页面组件命名为 `XxxPage.tsx`,与业务组件同目录风格但带 `Page` 后缀 |
| `lib/` | 纯函数工具、与 React 无关的客户端工具 | 禁止放置 JSX、禁止依赖 `react` 包 |
| `contexts/` | React Context Provider | 仅放 `XxxContext.tsx` + `useXxx.ts` 一对 |
| `config/` | 静态配置常量 | 禁止存放组件、禁止导出 React 元素 |
| `types/` | 全局 TS 类型声明 | 禁止运行时导出(纯 `type` / `interface`) |
| `test/` | 跨组件测试夹具、setup、mock | 单组件测试必须 colocated 在 `components/` 下 |

## 就近 Owner / 测试入口

- **Owner 模块**: `frontend/src/components/` 是最大改动源,改完必须跑:
  ```bash
  cd frontend
  npx tsc --noEmit                       # 类型检查
  npx vitest run <ComponentName>         # 单组件回归
  npx vitest run                         # 全量回归
  ```
- **Hook 改动**: 仅 `npx tsc --noEmit` + 该 hook 的 colocated test(若有)。
- **路由改动**: 必须 `npx vite build --logLevel error`(类型 + 产物打包),
  dev 服务器(`npm run dev`)不会热重载 `tailwind.config.js`,改 token 后需重启。
- **全链路验收**: `npx tsc --noEmit && npx vitest run && npx vite build --logLevel error`(根 AGENTS.md 已列)。

## 进入此目录的硬约束

0. **v0.8.5 壳纪律 (2026-09-14 裁决, NAV4 + P3 收口, 最高优先)** — v0.8 Sentinel **四菜单** (`/` 资讯 / `/knowledge` 知识 / `/action` 行动 / `/settings` 设置) 是唯一壳 (SentinelShell 4-tab + 管道心跳条常驻, spec=`docs/v0.8.5/V0.8.5_PLAN.md`):
   - 新能力**只能以四菜单区块**进入 (区块组件 + 真实 API + `allowed_actions` 守卫);
   - **禁止**新增一级入口、新应用壳 (V1SentinelShell 已物理删除, 不得复活)、页内主导航/tab state 充当第二套导航;
   - 新路由必须登记 `routes/ROUTE_REGISTRY.md` 并带重定向兼容; **全站不再有 AppNav** (2026-09-10 owner 裁决壳统一: 工具页 `PageLayout` 亦以 `<SentinelShell layer={null}>` 为壳, 顶部 4-tab + `menuOf(pathname)` 自动归属当前页归属四菜单; 左侧 AppNav 物理删除不得复活; 左侧栏能力归位页内 — SK 能力包在 `/skill-store`, 知识管理在 `/knowledge` KnowledgeTabs);
   - **2026-09-13 NAV4 + P2 死代码清理**: 三层→四菜单; `SentinelMoreMenu` + `UTILITY_GROUPS` (17 项) 已物理删除, 工具页"我在哪"指示由 `menuOf()` 自动归属四菜单 (menu key = `data`/`knowledge`/`action`/`settings`); `SecNewsShell` 6 视图 (feed/pipeline/knowledge/analyze/analytics/observability) 改挂 `PageLayout`, 由子路由内容自动归属四菜单 (例 `/secnews/feed`→data, `/secnews/knowledge`→knowledge, `/secnews/analyze`→action, `/secnews/observability`→settings);
   - **2026-09-14 P3 临时页收口**: `/biz` (mock) `/maint` (复用 maintenance API) `/knowledge/canvas` (ECharts demo) 已落账, 路由归属 `menuOf()` 已覆盖;
   - `sentinel.css` 元素级重置 (`:where(.sentinel) a/button`) 必须保持 (0,0,1) 特异度且 border 不用简写 — 壳包住了 Tailwind 工具页, 写高一级就会剥掉按钮背景/边框;
   - 守卫测试 `routes/__tests__/nav4_shell.test.tsx` (2026-09-13 取代 `v085_route_shell.test.tsx`) 锁定上述口径, 违反即 CI 红。
1. **不要新增未被设计技能路由过的视觉改动** — UI/样式任务必须先按根 AGENTS.md
   `Selection Precedence` 选中唯一主技能(`design-taste-frontend` 为默认,
   现有改造走 `redesign-existing-projects`)再开工。
2. **Tailwind 优先,行内 style 仅允许 dynamic 计算值** — 颜色/间距/字号必须
   走 Tailwind 类或 CSS 变量,严禁 `style={{ color: '#...' }}` 硬编码。
3. **测试 colocated,不要集中到 `test/`** — `components/Foo.tsx` 的测试必须是
   `components/Foo.test.tsx`,集中在 `test/` 的只允许跨组件夹具。
4. **新组件先查现有命名空间** — 若 `components/data/` 已有同类组件,
   必须复用或扩展,禁止平行新增 `components2/` 或 `components-v2/`。
5. **不要反向 import backend 代码** — 前端只通过 `127.0.0.1:8000` 调 API,
   严禁 `import backend.*`。

## 命名约定互斥速查

| 类别 | 唯一合法形态 | 禁止形态 |
|------|-------------|----------|
| 组件文件 | `PascalCase.tsx` | `camelCase.tsx`、`kebab-case.tsx`、`PascalCase.component.tsx` |
| 组件测试 | `PascalCase.test.tsx`(与源并排) | `PascalCase.spec.tsx`、`test/PascalCase.tsx` |
| Hook 文件 | `useXxx.ts` | `UseXxx.ts`、`useXxx.tsx`、`xxxHook.ts` |
| 类型文件 | `types/<domain>.ts` 内 `export type/interface` | `types/<domain>.tsx`(无 JSX 必要) |
| Context | `XxxContext.tsx` + `useXxx.ts` 一对 | `XxxProvider.tsx`(Provider 内联在 Context 中) |