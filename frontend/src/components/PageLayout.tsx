/**
 * PageLayout — Phase 1A 设计系统
 *
 * 统一外层布局 + ToastProvider 接入点。所有路由的 <Outlet> 包裹。
 *
 * 职责:
 *  - 外层容器 (min-h-screen + bg-primary + max-w-7xl)
 *  - ToastProvider (Phase 1A 新增)
 *  - 暗/亮主题已在 :root[data-theme] 上处理，本组件不重复
 *
 * 嵌套路由 (Phase 1A 用户决策):
 *   <Route element={<PageLayout />}>
 *     <Route path="/" element={<HomePage />} />
 *     ...
 *   </Route>
 */
import React from 'react';
import { Outlet } from 'react-router-dom';
import { ToastProvider } from './Toast';

export function PageLayout() {
  return (
    <ToastProvider>
      <div
        className="min-h-[100dvh]"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        {/* Phase 7: 响应式 padding — mobile 16px, tablet 24px, desktop 32px */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-6 relative z-10">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}
