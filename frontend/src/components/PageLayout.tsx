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
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 lg:px-10 py-4 sm:py-6 relative z-10">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}