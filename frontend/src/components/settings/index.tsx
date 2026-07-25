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
import { MCPSettingsCard } from './MCPSettingsCard';
import { Icon } from '../Icon';

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
        className="tech-drawer fixed right-0 top-0 bottom-0 z-50 w-full max-w-sm overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <h2 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
            <Icon size={16}>
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </Icon>
            设置
          </h2>
          <button onClick={onClose} className="btn-ghost px-2 py-1" aria-label="关闭">
            <Icon size={14}>
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </Icon>
          </button>
        </div>

        {/* Content */}
        <div className="px-4 py-3 space-y-4">
          <QualitySettings open={open} />
          <SourceSettings open={open} onRefreshIntervalChange={onRefreshIntervalChange} />
          <ProxySettings open={open} />
          <MCPSettingsCard open={open} />
        </div>
      </div>
    </>
  );
}
