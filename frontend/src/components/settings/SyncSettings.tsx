/**
 * settings/SyncSettings — 跨端同步设置卡片。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 SyncSettings (~204-281 行)。
 * 纯结构拆分: 状态 (status) 与 fetch/渲染逻辑逐字迁移。
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function SyncSettings() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<{
    configured?: boolean;
    last_sync_at?: string | null;
    last_sync_status?: string | null;
    auto_sync_enabled?: boolean;
    webdav_url?: string;
  } | null>(null);

  useEffect(() => {
    fetch('/api/sync/status')
      .then(r => r.json())
      .then(d => setStatus(d.status || d))
      .catch(() => {});
  }, []);

  const handleToggleAuto = async () => {
    try {
      await fetch('/api/sync/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !status?.auto_sync_enabled }),
      });
      setStatus(s => s ? { ...s, auto_sync_enabled: !s.auto_sync_enabled } : s);
    } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="card-compact">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>跨端同步</span>
            {status?.configured && (
              <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
                backgroundColor: status?.auto_sync_enabled
                  ? 'color-mix(in srgb, var(--color-success) 9%, transparent)'
                  : 'color-mix(in srgb, var(--text-muted) 9%, transparent)',
                color: status?.auto_sync_enabled ? 'var(--color-success)' : 'var(--text-muted)',
              }}>
                {status?.auto_sync_enabled ? '自动同步' : '手动同步'}
              </span>
            )}
          </div>

          {!status?.configured ? (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              通过 WebDAV (坚果云) 在设备间同步配置和密钥
            </p>
          ) : (
            <div className="space-y-1 mb-1.5">
              <div className="flex items-center gap-1.5 text-[9px]">
                <span className="font-mono truncate flex-1" style={{ color: 'var(--text-muted)' }} title={status.webdav_url}>
                  {status.webdav_url}
                </span>
                <span className="font-mono shrink-0" style={{ color: status.last_sync_status === 'success' ? 'var(--color-success)' : 'var(--text-muted)' }}>
                  {status.last_sync_at ? `上次: ${status.last_sync_at.slice(0, 10)}` : '未同步'}
                </span>
              </div>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={status?.auto_sync_enabled ?? false} onChange={handleToggleAuto} className="w-3 h-3" />
                <span className="text-[9px]" style={{ color: 'var(--text-secondary)' }}>采集后自动同步</span>
              </label>
            </div>
          )}

          <button
            onClick={() => navigate('/sync')}
            className="btn-secondary btn-sm w-full text-center"
          >
            {status?.configured ? '详细配置' : '配置同步'}
          </button>
        </div>
      </div>
    </div>
  );
}
