/**
 * SyncHeader — SyncPage 顶部条 (返回按钮 + 标题 + 已配置徽章)。
 *
 * Phase 1B: 拆自原 SyncPage.tsx 顶部 (lines 256-301)。
 */
import React from 'react';
import { Icon } from '../Icon';

interface SyncHeaderProps {
  configured: boolean;
  onBack: () => void;
}

export function SyncHeader({ configured, onBack }: SyncHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="btn-ghost px-2.5 py-1.5 text-xs"
          title="返回首页"
          aria-label="返回首页"
        >
          <Icon>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          返回首页
        </button>
        <h2 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
          ☁️ 跨端配置同步
        </h2>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          WebDAV / 坚果云
        </span>
      </div>
      <div className="flex items-center gap-2">
        {configured ? (
          <span
            className="text-[10px] px-2 py-0.5 rounded"
            style={{
              background: 'color-mix(in srgb, var(--color-success) 15%, transparent)',
              color: 'var(--color-success)',
            }}
          >
            ● 已配置
          </span>
        ) : (
          <span
            className="text-[10px] px-2 py-0.5 rounded"
            style={{
              background: 'color-mix(in srgb, var(--color-warning) 15%, transparent)',
              color: 'var(--color-warning)',
            }}
          >
            ● 未配置
          </span>
        )}
      </div>
    </div>
  );
}
