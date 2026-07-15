import React, { useState, useEffect, useCallback } from 'react';
import type { ContentDraft } from '../types';

export function ContentDraftList() {
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedContent, setExpandedContent] = useState<string>('');
  const [loadingContent, setLoadingContent] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', content: '' });

  const loadDrafts = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch('/api/content/drafts')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setDrafts(data.drafts || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  const handleExpand = (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    setLoadingContent(true);
    fetch(`/api/content/drafts/${id}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setExpandedContent(data.content || '');
        setLoadingContent(false);
      })
      .catch(e => {
        setExpandedContent(`加载失败: ${e?.message || String(e)}`);
        setLoadingContent(false);
      });
  };

  const handleCreate = () => {
    if (!form.title.trim()) return;
    fetch('/api/content/drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: form.title.trim(), content: form.content }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        setForm({ title: '', content: '' });
        setShowForm(false);
        loadDrafts();
      })
      .catch(e => setError(e?.message || String(e)));
  };

  const handleDelete = (id: number) => {
    fetch(`/api/content/drafts/${id}`, { method: 'DELETE' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        if (expandedId === id) setExpandedId(null);
        loadDrafts();
      })
      .catch(e => setError(e?.message || String(e)));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          草稿 ({drafts.length})
        </span>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-ghost px-2 py-0.5 text-[10px]"
          style={{ color: 'var(--color-ai)' }}
        >
          {showForm ? '取消' : '+ 新建'}
        </button>
      </div>

      {error && (
        <p className="text-[10px] mb-1" style={{ color: '#e85d5d' }}>{error}</p>
      )}

      {showForm && (
        <div className="mb-2 p-2 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
          <input
            type="text"
            placeholder="草稿标题"
            value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            className="w-full mb-1 px-2 py-1 text-[10px] rounded-[var(--radius-sm)]"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <textarea
            placeholder="Markdown 内容…"
            value={form.content}
            onChange={e => setForm({ ...form, content: e.target.value })}
            rows={4}
            className="w-full mb-1 px-2 py-1 text-[10px] rounded-[var(--radius-sm)] resize-y"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontFamily: 'monospace' }}
          />
          <button
            onClick={handleCreate}
            disabled={!form.title.trim()}
            className="btn-ghost px-2 py-0.5 text-[10px] w-full"
            style={{ color: 'var(--color-ai)', opacity: form.title.trim() ? 1 : 0.5 }}
          >
            保存草稿
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>加载中…</p>
      ) : drafts.length === 0 ? (
        <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>暂无草稿</p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-auto">
          {drafts.map(d => (
            <div key={d.id} className="rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-hover)' }}>
              <div
                className="flex items-center gap-2 p-1.5 cursor-pointer"
                onClick={() => handleExpand(d.id)}
              >
                <span
                  className="px-1 py-0.5 rounded text-[8px] shrink-0"
                  style={{
                    backgroundColor: d.status === 'final' ? '#00c96a' : d.status === 'archived' ? '#888899' : 'var(--color-ai)',
                    color: '#fff',
                  }}
                >
                  {d.status}
                </span>
                <span className="flex-1 truncate text-[10px]" style={{ color: 'var(--text-primary)' }} title={d.title}>
                  {d.title}
                </span>
                <span className="text-[8px] shrink-0" style={{ color: 'var(--text-muted)' }}>
                  {new Date(d.updated_at).toLocaleDateString('zh-CN')}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(d.id); }}
                  className="text-[10px] px-1 shrink-0"
                  style={{ color: '#e85d5d' }}
                  title="删除"
                >
                  ×
                </button>
              </div>
              {expandedId === d.id && (
                <pre
                  className="text-[9px] whitespace-pre-wrap p-1.5 max-h-32 overflow-auto"
                  style={{ color: 'var(--text-primary)', fontFamily: 'monospace', borderTop: '1px solid var(--border-color)' }}
                >
                  {loadingContent ? '加载中…' : expandedContent}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
