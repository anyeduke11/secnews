import { Outlet } from 'react-router-dom';
import { ToastProvider } from './Toast';
// T17.5: AppNav 14 项 nav (4 主入口 + 6 SK + 4 知识管理 域)
import { AppNav } from './AppNav';

export function PageLayout() {
  return (
    <ToastProvider>
      <div
        className="min-h-[100dvh] relative"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <a
          href="#main-content"
          className="skip-link"
          aria-label="跳转到主内容"
        >
          跳转到主内容
        </a>
        <AppNav />
        <div
          id="main-content"
          className="max-w-[1320px] mx-auto px-4 sm:px-8 lg:px-10 py-4 sm:py-6 sm:pl-64 relative z-10"
        >
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}