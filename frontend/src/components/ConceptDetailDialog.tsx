import React, { useState, useEffect, useCallback } from 'react';
import type { ConceptDetail } from '../types';

interface ConceptDetailDialogProps {
  slug: string | null;
  onClose: () => void;
  onSelectItem?: (id: string) => void;
}

export function ConceptDetailDialog({ slug, onClose, onSelectItem }: ConceptDetailDialogProps) {
  const [concept, setConcept] = useState<ConceptDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConcept = useCallback((s: string) => {
    setLoading(true);
    setError(null);
    fetch(`/api/knowledge/concepts/${encodeURIComponent(s)}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setConcept(data as ConceptDetail);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (slug) {
      setConcept(null);
      setError(null);
      loadConcept(slug);
    }
  }, [slug, loadConcept]);

  if (!slug) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="rounded-[var(--radius-md)] p-4"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border-color)',
          width: '640px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        {/* 顶部标题 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            💡 概念详情
          </h3>
          <button
            onClick={onClose}
            className="btn-ghost px-2 py-0.5 text-xs"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        {loading && (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            加载中…
          </p>
        )}

        {error && (
          <div
            className="rounded-[var(--radius-sm)] p-2.5 mb-3 text-xs"
            style={{ backgroundColor: 'rgba(232, 93, 93, 0.12)', border: '1px solid #e85d5d', color: '#e85d5d' }}
          >
            加载失败: {error}
          </div>
        )}

        {concept && !loading && (
          <div className="space-y-3">
            {/* 1. 标题 + slug + domain */}
            <div>
              <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>概念</p>
              <div className="rounded-[var(--radius-sm)] p-2.5" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                  {concept.title}
                </div>
                <div className="text-[10px] space-y-0.5" style={{ color: 'var(--text-muted)' }}>
                  <div>slug: <code style={{ color: 'var(--color-ai)' }}>{concept.slug}</code></div>
                  <div>domain: {concept.domain || '(未设置)'}</div>
                  <div>updated_at: {concept.updated_at}</div>
                </div>
              </div>
            </div>

            {/* 2. 关联条目列表 */}
            <div>
              <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                关联条目 ({concept.items?.length || 0})
              </p>
              {concept.items && concept.items.length > 0 ? (
                <div className="space-y-1">
                  {concept.items.map(it => (
                    <button
                      key={it.id}
                      onClick={() => onSelectItem?.(it.id)}
                      className="w-full text-left flex items-center gap-2 p-2 rounded-[var(--radius-sm)] text-xs"
                      style={{
                        backgroundColor: 'var(--bg-hover)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                        cursor: onSelectItem ? 'pointer' : 'default',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-ai)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-color)'; }}
                    >
                      <span className="flex-1 truncate" title={it.title}>{it.title}</span>
                      {it.domain && (
                        <span className="shrink-0 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {it.domain}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无关联条目</p>
              )}
            </div>

            {/* 3. 本地 wiki 关联 */}
            {concept.local_wiki_ref && (
              <div>
                <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>本地 wiki 关联</p>
                <div
                  className="rounded-[var(--radius-sm)] p-2.5 text-[11px]"
                  style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
                >
                  <code style={{ color: 'var(--color-ai)' }}>{concept.local_wiki_ref}</code>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
