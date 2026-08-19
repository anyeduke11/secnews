import { ThemeProvider } from './contexts/ThemeContext';
import { AppRoutes } from './routes';

// Stage1 拆分后: App = 组合入口 (主题 Provider + 路由表)
//  - 主题状态: contexts/ThemeContext.tsx (useTheme / ThemeProvider)
//  - 懒加载声明: routes/lazy-imports.ts (50+ React.lazy 集中管理)
//  - 路由表: routes/index.tsx (AppRoutes, 应用结构图)
export default function App() {
  return (
    <ThemeProvider>
      <AppRoutes />
    </ThemeProvider>
  );
}
