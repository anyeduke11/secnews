/**
 * settings/SyncSettings — 跨端同步设置卡片 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-section + st-switch (状态徽章走 L1 StatusBadge)
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSyncStatus, setSyncAuto } from '../../api/settings';
import { StatusBadge, type StatusTone } from '../../primitives/StatusBadge';

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
    getSyncStatus()
      .then(d => setStatus(d.status || d))
      .catch(() => {});
  }, []);

  const handleToggleAuto = async () => {
    try {
      await setSyncAuto(!status?.auto_sync_enabled);
      setStatus(s => s ? { ...s, auto_sync_enabled: !s.auto_sync_enabled } : s);
    } catch {}
  };

  const autoTone: StatusTone = status?.configured && status.auto_sync_enabled ? 'ok' : 'neutral';
  const lastSyncTone: StatusTone = status?.last_sync_status === 'success' ? 'ok' : 'neutral';

  return (
    <section className="st-section" aria-label="跨端同步" data-testid="sync-settings">
      <h3>
        跨端同步
        {status?.configured && (
          <StatusBadge tone={autoTone} dot>
            {status.auto_sync_enabled ? '自动' : '手动'}
          </StatusBadge>
        )}
      </h3>
      <p className="st-section-desc">
        通过 WebDAV (坚果云) 在设备间同步配置和密钥 — 完整设置见 /sync。
      </p>
      <div className="st-section-body">
        {!status?.configured ? (
          <p className="st-cellnote">尚未配置 WebDAV 端点。</p>
        ) : (
          <div className="st-rule">
            <div>
              <p className="st-label">WebDAV URL</p>
              <p className="st-key" title={status.webdav_url}>{status.webdav_url}</p>
            </div>
            <div className="st-ctrl">
              <StatusBadge tone={lastSyncTone} dot>
                {status.last_sync_at ? `上次: ${status.last_sync_at.slice(0, 10)}` : '未同步'}
              </StatusBadge>
            </div>
          </div>
        )}

        {status?.configured && (
          <div className="st-rule">
            <div>
              <p className="st-label">采集后自动同步</p>
              <p className="st-key">auto_sync_enabled</p>
            </div>
            <div className="st-ctrl">
              <button
                type="button"
                role="switch"
                aria-checked={status?.auto_sync_enabled ?? false}
                onClick={handleToggleAuto}
                className="st-switch"
                style={{ width: 32, height: 18 }}
              />
            </div>
          </div>
        )}

        <div className="st-actionbar">
          <button type="button" className="st-btn primary" onClick={() => navigate('/sync')}>
            {status?.configured ? '详细配置 →' : '配置同步 →'}
          </button>
        </div>
      </div>
    </section>
  );
}

export default SyncSettings;