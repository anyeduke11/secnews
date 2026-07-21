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
        className="min-h-[100dvh] relative"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        {/* Phase 8: tech-style 背景点阵 + 顶部细线 — 极淡不抢戏, 暗/亮两套透明度 */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-tech-grid"
        />
        {/* 顶部细线渐变 — 强化 "system bar" 感 */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{
            background:
              'linear-gradient(to right, transparent, var(--color-ai) 20%, var(--color-ai) 80%, transparent)',
            opacity: 0.6,
          }}
        />
        {/* 底部细线 — 双线对称 */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-px"
          style={{
            background:
              'linear-gradient(to right, transparent, var(--color-ai) 30%, var(--color-ai) 70%, transparent)',
            opacity: 0.3,
          }}
        />
        {/* Phase 7: 响应式 padding — mobile 16px, tablet 24px, desktop 32px */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-6 relative z-10">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}
