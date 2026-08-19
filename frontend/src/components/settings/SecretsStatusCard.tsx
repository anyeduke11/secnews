/**
 * settings/SecretsStatusCard — 密钥管理器状态卡片。
 *
 * 拆自原 SettingsPage.tsx (1065 行) 中 SecretsStatusCard (~286-381 行)。
 * 纯结构拆分: 状态与 fetch/渲染逻辑逐字迁移。
 */
import React, { useState, useEffect } from 'react';
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

  const ttlColor = status?.remaining_seconds != null && status.remaining_seconds < 300
    ? 'var(--color-error)'
    : status?.remaining_seconds != null && status.remaining_seconds < 600
      ? 'var(--color-warning)'
      : 'var(--color-general)';

  return (
    <div className="space-y-2">
      <div className="card-base">
        <div className="px-2.5 py-1.5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>密钥管理器</span>
            <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
              backgroundColor: status?.unlocked
                ? 'color-mix(in srgb, var(--color-success) 9%, transparent)'
                : status?.setup
                  ? 'color-mix(in srgb, var(--color-warning) 9%, transparent)'
                  : 'color-mix(in srgb, var(--text-muted) 9%, transparent)',
              color: status?.unlocked ? 'var(--color-success)' : status?.setup ? 'var(--color-warning)' : 'var(--text-muted)',
            }}>
              {status?.unlocked ? '已解锁' : status?.setup ? '已锁定' : '未设置'}
            </span>
          </div>
          {status?.unlocked && status.remaining_seconds != null && (
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px]" style={{ color: 'var(--text-muted)' }}>剩余锁定时间</span>
              <span className="text-[9px] font-mono font-bold" style={{ color: ttlColor }}>
                {Math.floor(status.remaining_seconds / 60)}:{String(status.remaining_seconds % 60).padStart(2, '0')}
              </span>
              <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                · {status.total ?? items.length} 条密钥
              </span>
            </div>
          )}
          {items.length > 0 && status?.unlocked && (
            <div className="space-y-0.5 mb-1.5">
              {items.slice(0, 3).map((item: any) => (
                <div key={item.id} className="flex items-center gap-1.5 text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  <span className="w-2.5 h-2.5 rounded flex items-center justify-center" style={{ backgroundColor: 'color-mix(in srgb, var(--color-ai) 15%, transparent)', fontSize: 6 }}>
                    {item.name?.charAt(0)?.toUpperCase() || 'K'}
                  </span>
                  <span className="truncate flex-1">{item.name}</span>
                  <span>{'●'.repeat(6)}</span>
                </div>
              ))}
              {(status.total ?? items.length) > 3 && (
                <p className="text-[9px]" style={{ color: 'var(--text-muted)' }}>+{(status.total ?? items.length) - 3} 条更多...</p>
              )}
            </div>
          )}
          {!status?.setup && (
            <p className="text-[9px] mb-1.5" style={{ color: 'var(--text-muted)' }}>
              设置主密钥以安全存储 LLM API Key 等敏感凭据
            </p>
          )}
          <div className="flex gap-1.5">
            <button
              onClick={() => navigate('/secrets')}
              className="btn-secondary btn-sm flex-1"
            >
              管理密钥
            </button>
            {status?.unlocked && (
              <button
                onClick={async () => {
                  try { await fetch('/api/secrets/lock', { method: 'POST' }); } catch {}
                  window.location.reload();
                }}
                className="btn-secondary btn-sm"
                style={{ color: 'var(--color-error)' }}
              >
                立即锁定
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
