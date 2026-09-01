import { ThemeProvider } from './contexts/ThemeContext';
import { I18nProvider } from './contexts/I18nContext';
import { AppRoutes } from './routes';

// Stage1 拆分后: App = 组合入口 (主题 Provider + 路由表)
//  - 主题状态: contexts/ThemeContext.tsx (useTheme / ThemeProvider)
//  - i18n 状态: contexts/I18nContext.tsx (useI18n / I18nProvider, v0.7 D6)
//  - 懒加载声明: routes/lazy-imports.ts (50+ React.lazy 集中管理)
//  - 路由表: routes/index.tsx (AppRoutes, 应用结构图)
export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppRoutes />
      </I18nProvider>
    </ThemeProvider>
  );
}
