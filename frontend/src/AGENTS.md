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
| `components/action/`、`components/codegarden/`、`components/data/`、`components/editorial/` | 按领域分子目录,组件仍 PascalCase | 子目录内禁止再嵌 `components/` 子目录 |
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