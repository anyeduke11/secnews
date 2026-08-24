/**
 * InboxScanner — inbox 扫描入库入口
 *
 * 提供一键扫描 inbox/ 目录，将有效条目移入 items/。
 */
import { useState } from 'react';

export function InboxScanner() {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<{ moved: number; quarantined: number } | null>(null);

  const handleScan = async () => {
    setScanning(true);
    try {
      const res = await fetch('/api/kl/inbox/scan', { method: 'POST' });
      const data = await res.json();
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)' }}>
      <h3 className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Inbox 扫描</h3>
      <p className="text-[10px] mb-3" style={{ color: 'var(--text-muted)' }}>
        扫描 inbox/ 目录，将有效条目移入知识库，无效文件隔离到 quarantine/
      </p>
      <button
        onClick={handleScan}
        disabled={scanning}
        className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-hover)]"
        style={{ border: '1px solid var(--border-color)', color: 'var(--accent)' }}
      >
        {scanning ? '扫描中...' : '开始扫描'}
      </button>
      {result && (
        <div className="mt-2 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
          入库: {result.moved} · 隔离: {result.quarantined}
        </div>
      )}
    </div>
  );
}
