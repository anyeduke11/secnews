/**
 * settings/SyncSettings — 跨端同步设置卡片 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-section + st-chip + st-switch
 */
import { useState, useEffect } from 'react';
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

  const autoChip = status?.configured && status.auto_sync_enabled ? 'st-chip ok' : 'st-chip mute';
  const lastSyncChip = status?.last_sync_status === 'success' ? 'st-chip ok' : 'st-chip mute';

  return (
    <section className="st-section" aria-label="跨端同步" data-testid="sync-settings">
      <h3>
        跨端同步
        {status?.configured && (
          <span className={autoChip}>
            <i aria-hidden />{status.auto_sync_enabled ? '自动' : '手动'}
          </span>
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
              <span className={lastSyncChip}>
                <i aria-hidden />
                {status.last_sync_at ? `上次: ${status.last_sync_at.slice(0, 10)}` : '未同步'}
              </span>
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