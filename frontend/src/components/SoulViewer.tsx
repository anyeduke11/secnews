import React, { useState, useEffect } from 'react';
import type { SoulData } from '../types';

export function SoulViewer() {
  const [soul, setSoul] = useState<SoulData | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  const loadSoul = () => {
    fetch('/api/knowledge/soul')
      .then(r => r.json())
      .then(setSoul)
      .catch(() => {});
  };

  useEffect(() => { loadSoul(); }, []);

  const handleRegenerate = () => {
    setRegenerating(true);
    fetch('/api/knowledge/soul/regenerate', { method: 'POST' })
      .then(() => loadSoul())
      .finally(() => setRegenerating(false));
  };

  if (!soul) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {soul.exists ? '已生成' : '默认模板'}
        </span>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="btn-ghost px-2 py-0.5 text-[10px]"
          style={{ color: 'var(--color-ai)', opacity: regenerating ? 0.6 : 1 }}
        >
          {regenerating ? '生成中…' : '重新生成'}
        </button>
      </div>
      <pre className="text-[10px] whitespace-pre-wrap overflow-auto max-h-48"
           style={{ color: 'var(--text-primary)', fontFamily: 'monospace' }}>
        {soul.content}
      </pre>
    </div>
  );
}
