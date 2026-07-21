import React, { useState, useEffect, useCallback } from 'react';
import type { PublishHistoryItem } from '../types';

interface PublishHistoryProps {
  draft_id: number | null;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'var(--color-warning)',
  processing: 'var(--color-info)',
  done: 'var(--color-success)',
  failed: 'var(--color-error)',
};

const PLATFORM_LABELS: Record<string, string> = {
  wechat: '微信公众号',
  x: 'X',
  weibo: '微博',
};

export function PublishHistory({ draft_id, onClose }: PublishHistoryProps) {
  const [history, setHistory] = useState<PublishHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback((id: number) => {
    setLoading(true);
    setError(null);
    fetch(`/api/content/drafts/${id}/publish-history`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setHistory(data.history || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (draft_id != null) {
      setHistory([]);
      setError(null);
      loadHistory(draft_id);
    }
  }, [draft_id, loadHistory]);

  if (draft_id == null) return null;

  const handleRefresh = () => {
    if (draft_id != null) loadHistory(draft_id);
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'var(--bg-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="rounded-[var(--radius-md)] p-4"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          width: '600px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        {/* 顶部标题 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            📋 发布历史 (草稿 #{draft_id})
          </h3>
          <div className="flex items-center gap-1">
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="btn-ghost px-2 py-0.5 text-xs"
              style={{ color: 'var(--color-ai)', opacity: loading ? 0.6 : 1 }}
              title="刷新"
            >
              {loading ? '刷新中…' : '↻ 刷新'}
            </button>
            <button onClick={onClose} className="btn-ghost px-2 py-0.5 text-xs" aria-label="关闭">
              ✕
            </button>
          </div>
        </div>

        {error && (
          <div
            className="rounded-[var(--radius-sm)] p-2.5 mb-3 text-xs"
            style={{ backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)', border: '1px solid var(--color-error)', color: 'var(--color-error)' }}
          >
            加载失败: {error}
          </div>
        )}

        {!loading && !error && history.length === 0 && (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            暂无发布历史
          </p>
        )}

        {history.length > 0 && (
          <div className="space-y-2">
            {history.map(item => {
              const statusColor = STATUS_COLORS[item.status] || 'var(--text-muted)';
              const platformLabel = item.platform ? (PLATFORM_LABELS[item.platform] || item.platform) : '-';
              return (
                <div
                  key={item.task_id}
                  className="rounded-[var(--radius-sm)] p-2.5"
                  style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                      style={{ backgroundColor: statusColor, color: 'var(--text-on-color)' }}
                    >
                      {item.status}
                    </span>
                    <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                      {platformLabel}
                    </span>
                    <span className="text-[10px] shrink-0" style={{ color: 'var(--text-muted)' }}>
                      task #{item.task_id}
                    </span>
                    <span className="text-[10px] ml-auto shrink-0" style={{ color: 'var(--text-muted)' }}>
                      {new Date(item.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <div className="text-[10px] space-y-0.5" style={{ color: 'var(--text-muted)' }}>
                    {item.skill_name && <div>skill: {item.skill_name}</div>}
                    {item.status === 'done' && item.published_url && (
                      <div>
                        链接: <a href={item.published_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-ai)' }}>
                          {item.published_url}
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
