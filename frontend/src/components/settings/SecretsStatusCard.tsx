/**
 * settings/SecretsStatusCard — 密钥管理器状态卡片 (V2 哨兵化)
 *
 * v0.7.x SettingsHub V2: st-section + st-cellgrid + st-chip + st-btn
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function SecretsStatusCard() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<{ setup?: boolean; unlocked?: boolean; remaining_seconds?: number; total?: number } | null>(null);
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/secrets/status')
      .then(r => r.json())
      .then(d => setStatus(d))
      .catch(() => {});
    fetch('/api/secrets?limit=5')
      .then(r => r.json())
      .then(d => setItems(d.items || []))
      .catch(() => {});
  }, []);

  const remain = status?.remaining_seconds;
  const ttlChip: string | undefined = remain == null ? undefined
    : remain < 300 ? 'st-chip bad'
    : remain < 600 ? 'st-chip warn'
    : 'st-chip ok';

  const statusChip = status?.unlocked ? 'st-chip ok'
    : status?.setup ? 'st-chip warn'
    : 'st-chip mute';

  const totalItems = status?.total ?? items.length;

  return (
    <section className="st-section" aria-label="密钥管理器" data-testid="secrets-status-card">
      <h3>
        密钥管理器
        <span className={statusChip}>
          <i aria-hidden />{status?.unlocked ? '已解锁' : status?.setup ? '已锁定' : '未设置'}
        </span>
      </h3>
      <p className="st-section-desc">
        设置主密钥以安全存储 LLM API Key 等敏感凭据。
        {status?.unlocked && remain != null && (
          <span style={{ marginLeft: 8, color: 'var(--sn-ink-3)' }}>
            剩余 <span className={ttlChip}><i aria-hidden />{Math.floor(remain / 60)}:{String(remain % 60).padStart(2, '0')}</span>
          </span>
        )}
      </p>
      <div className="st-section-body">
        <div className="st-cellgrid">
          <div className="st-cell">
            <span className="st-cellk">SETUP</span>
            <span className="st-cellv sm">{status?.setup ? 'YES' : 'NO'}</span>
          </div>
          <div className="st-cell">
            <span className="st-cellk">UNLOCKED</span>
            <span className="st-cellv sm">{status?.unlocked ? 'YES' : 'NO'}</span>
          </div>
          <div className="st-cell">
            <span className="st-cellk">SECRETS</span>
            <span className="st-cellv sm">{totalItems} 条</span>
          </div>
        </div>

        {items.length > 0 && status?.unlocked && (
          <table className="st-table" aria-label="密钥预览 (top 3)">
            <thead>
              <tr><th>名称</th><th style={{ width: 80 }}>密钥</th></tr>
            </thead>
            <tbody>
              {items.slice(0, 3).map((item: any) => (
                <tr key={item.id}>
                  <td><span className="st-nm">{item.name}</span></td>
                  <td style={{ color: 'var(--sn-ink-3)' }}>{'●'.repeat(8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="st-actionbar">
          <button type="button" className="st-btn primary" onClick={() => navigate('/secrets')}>
            管理密钥 →
          </button>
          {status?.unlocked && (
            <button type="button" className="st-btn danger" onClick={async () => {
              try { await fetch('/api/secrets/lock', { method: 'POST' }); } catch {}
              window.location.reload();
            }} aria-label="立即锁定">
              立即锁定
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

export default SecretsStatusCard;