/**
 * secrets/Modal — 通用模态容器。
 *
 * 拆自原 SecretsPage.tsx (794 行) 中 Modal (~776-794 行)。
 * 纯结构拆分, 渲染逻辑逐字迁移。
 */
import React from 'react';

export function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'var(--bg-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="tech-modal p-4 w-[420px] max-w-[90vw]"
      >
        {children}
      </div>
    </div>
  );
}
