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
        <div aria-hidden="true" className="pointer-events-none fixed inset-0 bg-editorial-texture z-0" />

        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-x-0 top-0 h-px z-50"
          style={{
            background: 'linear-gradient(to right, transparent, var(--color-ai) 15%, var(--color-ai) 85%, transparent)',
            opacity: 0.5,
          }}
        />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5 relative z-10">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}