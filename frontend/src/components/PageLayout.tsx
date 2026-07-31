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
        {/* v1.9 Editorial: 报纸风容器 — 1280px + 32px 左右留白 (移动端 16px), 去 HUD 发光线 */}
        <div className="max-w-[1280px] mx-auto px-4 sm:px-6 lg:px-8 py-3 sm:py-4 relative z-10">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}