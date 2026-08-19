/**
 * 前端扩展路由表 — 按扩展名分组的真实路由路径。
 *
 * 实际路由定义在 App.tsx 中懒加载；此文件仅定义「扩展→路由路径」映射，
 * 供 App.tsx 条件渲染 + 测试断言使用。
 */
import type { RouteObject } from 'react-router-dom';

export interface ExtensionRoute {
  name: string;
  routes: RouteObject[];
}

export const EXTENSION_ROUTES: Record<string, string[]> = {
  codegarden: [
    '/action/codegarden',
    '/action/codegarden/phase2b',
    '/codegarden',
    '/codegarden/phase2b',
  ],
  // MCP 无独立路由 — 设置项是 SettingsPage 内嵌卡片 (MCPSettingsCard)
  mcp: [],
  sync: ['/sync'],
};