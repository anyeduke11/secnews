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
        {/* 侧栏让位必须独占一层: 与 px-* 同串时 lg:px-10 会在 ≥1024px 覆盖 sm:pl-64 (Tailwind 按断点排序输出) */}
        <div className="sm:pl-64">
          <div
            id="main-content"
            className="max-w-[1320px] mx-auto px-4 sm:px-8 lg:px-10 py-4 sm:py-6 relative z-10"
          >
            <Outlet />
          </div>
        </div>
      </div>
    </ToastProvider>
  );
}

// v0.8.5: 三层 Sentinel 全屏布局 — 只提供 ToastProvider (v1 区块 mutation 提示需要),
// 不渲染 AppNav 侧栏: 三层页由页内 SentinelShell 提供唯一导航 (spec §4.3 壳纪律).
export function SentinelLayout() {
  return (
    <ToastProvider>
      <div
        className="min-h-[100dvh] relative"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <Outlet />
      </div>
    </ToastProvider>
  );
}