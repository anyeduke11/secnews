/**
 * InboxScanner — inbox 扫描入库入口 (S1-5 完整版)
 *
 * 三段式: inbox 待处理列表 → 一键扫描 → quarantine 隔离区清单。
 * 数据源: GET /api/kl/inbox/list · POST /api/kl/inbox/scan · GET /api/kl/quarantine/list
 */
import { useCallback, useEffect, useState } from 'react';
import { listKlInbox, listKlQuarantine, scanKlInbox } from '../../../api/secnews';
import type { FileEntry } from '../../../api/secnews';
import { useI18n } from '../../../contexts/I18nContext';
import { useAbortGuard } from '../../../hooks/useAbortGuard';

export function InboxScanner({ onScanned }: { onScanned?: () => void }) {
  const { t } = useI18n();
  const [inbox, setInbox] = useState<FileEntry[]>([]);
  const [quarantine, setQuarantine] = useState<FileEntry[]>([]);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<{ moved: number; quarantined: number } | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const refresh = useCallback(async () => {
    try {
      // allSettled + fulfilled 守卫: 与原 `res.ok` 静默分支同效 (失败保持上次值)
      const [inRes, qRes] = await Promise.allSettled([
        listKlInbox(),
        listKlQuarantine(),
      ]);
      if (dead.current) return;
      if (inRes.status === 'fulfilled') setInbox(inRes.value.files ?? []);
      if (qRes.status === 'fulfilled') setQuarantine(qRes.value.files ?? []);
    } catch { /* silent */ }
  }, [dead]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleScan = async () => {
    setScanning(true);
    setResult(null);
    try {
      const data = await scanKlInbox();
      if (dead.current) return;
      setResult(data);
      setQuarantine(data.quarantine_files ?? []);
      setInbox([]);
      onScanned?.();
    } catch { /* silent */ } finally {
      if (!dead.current) setScanning(false);
    }
  };

  return (
    <div className="p-3 rounded-[var(--radius-sm)] border" style={{ borderColor: 'var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>{t('kb.inbox_scanner')}</h3>
      <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
        {t('kb.inbox_hint')}
      </p>

      {/* inbox 待处理 */}
      {inbox.length > 0 && (
        <div className="mb-2 space-y-0.5">
          <div className="text-[10px] font-mono" style={{ color: 'var(--color-warning)' }}>
            {t('kb.inbox_pending', { n: inbox.length })}
          </div>
          {inbox.map(f => (
            <div key={f.name}
              className="text-[10px] font-mono truncate px-1.5 py-0.5 rounded bg-[var(--bg-hover)]"
              style={{ color: 'var(--text-secondary)' }}
              title={f.preview}>
              {f.name} · {f.size}B
            </div>
          ))}
        </div>
      )}

      <button
        onClick={handleScan}
        disabled={scanning}
        className="w-full px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors disabled:opacity-50 hover:bg-[var(--bg-hover)]"
        style={{ border: '1px solid var(--accent)', color: 'var(--accent)' }}
      >
        {scanning
          ? t('kb.scanning')
          : t('kb.scan', { n: inbox.length > 0 ? ` (${inbox.length})` : '' })}
      </button>

      {result && (
        <div className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
          {t('kb.scan_result_ok', {
            moved: result.moved,
            quarantined: result.quarantined > 0 ? t('kb.scan_result_quarantined', { n: result.quarantined }) : '',
          })}
        </div>
      )}

      {/* quarantine 隔离区 */}
      {quarantine.length > 0 && (
        <div className="mt-3 pt-2" style={{ borderTop: '1px dashed var(--border-color)' }}>
          <div className="text-[10px] font-mono mb-1" style={{ color: 'var(--color-error)' }}>
            Quarantine ({quarantine.length})
          </div>
          <div className="space-y-0.5 max-h-[120px] overflow-y-auto">
            {quarantine.map(f => (
              <div key={f.name}
                className="text-[10px] font-mono truncate px-1.5 py-0.5 rounded"
                style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 6%, transparent)', color: 'var(--text-muted)' }}>
                {f.name}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
