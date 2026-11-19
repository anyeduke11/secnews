import { ThemeProvider } from './contexts/ThemeContext';
import { I18nProvider } from './contexts/I18nContext';
import { ToastProvider } from './primitives/Toast';
import { AppRoutes } from './routes';

// Stage1 拆分后: App = 组合入口 (主题 Provider + Toast Provider + 路由表)
//  - 主题状态: contexts/ThemeContext.tsx (useTheme / ThemeProvider)
//  - i18n 状态: contexts/I18nContext.tsx (useI18n / I18nProvider, v0.7 D6)
//  - 全局 Toast: primitives/Toast.tsx (B2 2026-11-17 提到根 — 提示跨路由切换不丢; B8-b 迁入 L1 原语目录)
//  - 懒加载声明: routes/lazy-imports.ts (50+ React.lazy 集中管理)
//  - 路由表: routes/index.tsx (AppRoutes, 应用结构图)
export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
