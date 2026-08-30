/**
 * TagsPage — 标签管理 (找回丢失前端入口 v1.7 Phase 1)
 *
 * 标签列表 (类型筛选) + 前缀搜索 + 新建 + 删除。
 * 数据源: GET/POST/DELETE /api/tags · GET /api/tags/suggest
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

interface TagItem {
  id: string;
  label: string;
  type: string;
  parent_id?: string | null;
  weight: number;
  created_at?: string;
}

const TAG_TYPES = ['domain', 'category', 'framework', 'technique', 'source', 'cve'] as const;

export function TagsPage({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate();
  const goBack = onBack ?? (() => navigate('/'));

  const [tags, setTags] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [suggest, setSuggest] = useState('');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // 新建表单
  const [newId, setNewId] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [newType, setNewType] = useState<string>('domain');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (typeFilter) params.set('type', typeFilter);
      const r = await fetch(`/api/tags?${params}`);
      if (!r.ok) {
        setError(`标签加载失败 (${r.status})`);
        return;
      }
      const d = await r.json();
      setTags(d.items ?? []);
    } catch {
      setError('标签加载失败: 网络或后端不可达');
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newId.trim() || !newLabel.trim()) return;
    setCreating(true);
    setMsg(null);
    try {
      const r = await fetch('/api/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: newId.trim(), label: newLabel.trim(), type: newType }),
      });
      if (!r.ok) {
        const detail = await r.json().catch(() => null);
        setMsg({ kind: 'err', text: `创建失败 (${r.status})${detail?.detail?.message ? `: ${detail.detail.message}` : ''}` });
        return;
      }
      setMsg({ kind: 'ok', text: `已创建 ${newLabel.trim()}` });
      setNewId('');
      setNewLabel('');
      await load();
    } catch {
      setMsg({ kind: 'err', text: '创建失败: 网络或后端不可达' });
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (tag: TagItem) => {
    if (!window.confirm(`删除标签「${tag.label}」(${tag.id})?`)) return;
    setMsg(null);
    try {
      const r = await fetch(`/api/tags/${encodeURIComponent(tag.id)}`, { method: 'DELETE' });
      if (!r.ok) {
        setMsg({ kind: 'err', text: `删除失败 (${r.status})` });
        return;
      }
      setMsg({ kind: 'ok', text: `已删除 ${tag.label}` });
      await load();
    } catch {
      setMsg({ kind: 'err', text: '删除失败: 网络或后端不可达' });
    }
  };

  // 前缀搜索 (防抖省略 — 输入即查, 数据量小)
  const [suggestions, setSuggestions] = useState<TagItem[]>([]);
  useEffect(() => {
    const q = suggest.trim();
    if (!q) { setSuggestions([]); return; }
    let cancelled = false;
    fetch(`/api/tags/suggest?q=${encodeURIComponent(q)}`)
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => { if (!cancelled) setSuggestions(d.items ?? []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [suggest]);

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between pb-2 mb-1" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-mono mr-2">TAG</span>标签管理
        </h1>
        <button onClick={goBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回首页">
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回首页</span>
        </button>
      </div>

      {msg && (
        <div className="p-2 rounded text-[11px] font-mono"
          style={{
            color: msg.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)',
            border: `1px solid ${msg.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)'}`,
          }}>
          {msg.text}
        </div>
      )}

      {/* 新建 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>新建标签</h3>
        <div className="flex flex-wrap items-center gap-2">
          <input value={newId} onChange={e => setNewId(e.target.value)} placeholder="ID (唯一)"
            className="px-2 py-1 text-xs font-mono rounded w-40"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
          <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="显示名"
            className="px-2 py-1 text-xs font-mono rounded w-44"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
          <select value={newType} onChange={e => setNewType(e.target.value)}
            className="px-2 py-1 text-xs font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}>
            {TAG_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <button onClick={handleCreate} disabled={creating || !newId.trim() || !newLabel.trim()}
            className="btn-secondary text-[10px] px-3 py-1">
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </section>

      {/* 搜索 + 筛选 */}
      <div className="flex items-center gap-2">
        <input value={suggest} onChange={e => setSuggest(e.target.value)} placeholder="按前缀搜索..."
          className="flex-1 px-2 py-1 text-xs font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="px-2 py-1 text-xs font-mono rounded"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}>
          <option value="">全部类型</option>
          {TAG_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {suggest.trim() && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map(s => (
            <span key={s.id} className="text-[10px] font-mono px-1.5 py-0.5 rounded cursor-pointer"
              style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
              onClick={() => setSuggest(s.label)}>
              {s.label}
            </span>
          ))}
        </div>
      )}

      {/* 列表 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
        {loading ? (
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>加载中...</p>
        ) : error ? (
          <p className="text-[11px]" style={{ color: 'var(--color-error)' }}>{error}</p>
        ) : tags.length === 0 ? (
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>暂无标签</p>
        ) : (
          <ul className="divide-y" style={{ borderColor: 'var(--border-light)' }}>
            {tags.map(t => (
              <li key={t.id} className="py-1.5 flex items-center gap-2 text-[11px]">
                <span className="font-mono flex-1 truncate" style={{ color: 'var(--text-primary)' }}>{t.label}</span>
                <span className="font-mono text-[10px] truncate max-w-[180px]" style={{ color: 'var(--text-muted)' }}>{t.id}</span>
                <span className="text-[10px] font-mono px-1 rounded shrink-0"
                  style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                  {t.type}
                </span>
                <button onClick={() => handleDelete(t)}
                  className="btn-ghost text-[10px] px-1.5 py-0.5 shrink-0"
                  style={{ color: 'var(--color-error)' }}
                  aria-label={`删除 ${t.label}`}>
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
