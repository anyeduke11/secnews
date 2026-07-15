import React, { useState, useEffect } from 'react';
import type { FederationStatus as FederationStatusData } from '../types';

export function FederationStatus() {
  const [status, setStatus] = useState<FederationStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/knowledge/federation')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setStatus(data);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中…</p>;
  }

  if (error) {
    return <p className="text-xs" style={{ color: '#e85d5d' }}>加载失败: {error}</p>;
  }

  if (!status) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>无数据</p>;
  }

  if (!status.local_wiki_enabled) {
    return (
      <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
        本地 wiki 未启用
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-[10px]">
        <span style={{ color: 'var(--text-muted)' }}>路径:</span>
        <span
          className="truncate flex-1"
          style={{ color: status.local_wiki_exists ? 'var(--text-primary)' : '#e85d5d' }}
          title={status.local_wiki_path}
        >
          {status.local_wiki_path || '(空)'}
        </span>
      </div>
      {!status.local_wiki_exists && (
        <p className="text-[10px]" style={{ color: '#e85d5d' }}>路径不存在</p>
      )}
      <div className="grid grid-cols-3 gap-1 mt-1">
        <div className="text-center p-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{status.local_concepts_count}</div>
          <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>本地概念</div>
        </div>
        <div className="text-center p-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{status.local_items_count}</div>
          <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>本地条目</div>
        </div>
        <div className="text-center p-1 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="text-sm font-bold" style={{ color: 'var(--color-ai)' }}>{status.federated_edges}</div>
          <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>联邦边</div>
        </div>
      </div>
      {status.readonly && (
        <p className="text-[9px] mt-1" style={{ color: 'var(--text-muted)' }}>只读模式</p>
      )}
    </div>
  );
}
