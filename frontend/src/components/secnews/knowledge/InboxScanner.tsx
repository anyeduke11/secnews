/**
 * InboxScanner — inbox 扫描入库入口 (S1-5 完整版)
 *
 * 三段式: inbox 待处理列表 → 一键扫描 → quarantine 隔离区清单。
 * 数据源: GET /api/kl/inbox/list · POST /api/kl/inbox/scan · GET /api/kl/quarantine/list
 */
import { useCallback, useEffect, useState } from 'react';

interface FileEntry {
  name: string;
  size: number;
  preview?: string;
  quarantined_at?: string;
}

export function InboxScanner({ onScanned }: { onScanned?: () => void }) {
  const [inbox, setInbox] = useState<FileEntry[]>([]);
  const [quarantine, setQuarantine] = useState<FileEntry[]>([]);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<{ moved: number; quarantined: number } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [inRes, qRes] = await Promise.all([
        fetch('/api/kl/inbox/list'),
        fetch('/api/kl/quarantine/list'),
      ]);
      if (inRes.ok) setInbox((await inRes.json()).files ?? []);
      if (qRes.ok) setQuarantine((await qRes.json()).files ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleScan = async () => {
    setScanning(true);
    setResult(null);
    try {
      const res = await fetch('/api/kl/inbox/scan', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setResult(data);
        setQuarantine(data.quarantine_files ?? []);
        setInbox([]);
        onScanned?.();
      }
    } catch { /* silent */ } finally {
      setScanning(false);
    }
  };

  return (
    <div className="p-3 rounded-[var(--radius-sm)] border" style={{ borderColor: 'var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Inbox 投递区</h3>
      <p className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
        将 .md 文件放入 inbox 目录，点击扫描后有效条目移入知识库，无效文件隔离到 quarantine
      </p>

      {/* inbox 待处理 */}
      {inbox.length > 0 && (
        <div className="mb-2 space-y-0.5">
          <div className="text-[10px] font-mono" style={{ color: 'var(--color-warning)' }}>
            待处理 ({inbox.length})
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
        {scanning ? '扫描中...' : `扫描入库${inbox.length > 0 ? ` (${inbox.length})` : ''}`}
      </button>

      {result && (
        <div className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
          ✓ 入库 {result.moved} 条{result.quarantined > 0 ? ` · 隔离 ${result.quarantined} 条` : ''}
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
