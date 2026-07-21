/**
 * SettingsPanel — 设置抽屉主壳（Phase 1B 拆分后）。
 *
 * Phase 1B: 拆自原 SettingsPanel.tsx（30KB / 713 行）。
 * 当前仅作抽屉壳：overlay + header + escape 处理 + 渲染 3 个子区段。
 * 各区段（质量/信源/代理）自治状态，index 只协调 open/close 生命周期。
 *
 * 公开 API 与原 SettingsPanel 完全一致（向后兼容）：
 *   <SettingsPanel open={...} onClose={...} onRefreshIntervalChange={...} />
 */
import React, { useEffect } from 'react';
import { QualitySettings } from './QualitySettings';
import { SourceSettings } from './SourceSettings';
import { ProxySettings } from './ProxySettings';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  onRefreshIntervalChange?: (minutes: number) => void;
}

export function SettingsPanel({ open, onClose, onRefreshIntervalChange }: SettingsPanelProps) {
  // ESC 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'var(--bg-overlay)' }} onClick={onClose} />
      <div
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-sm overflow-y-auto"
        style={{
          backgroundColor: 'var(--bg-primary)',
          borderLeft: '1px solid var(--border-color)',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.3)',
          animation: 'slide-in-right 0.25s ease',
        }}
      >
        <style>{`@keyframes slide-in-right{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <h2 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>代理设置</h2>
          <button onClick={onClose} className="btn-ghost px-2 py-1">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-4 py-3 space-y-4">
          <QualitySettings open={open} />
          <SourceSettings open={open} onRefreshIntervalChange={onRefreshIntervalChange} />
          <ProxySettings open={open} />
        </div>
      </div>
    </>
  );
}
