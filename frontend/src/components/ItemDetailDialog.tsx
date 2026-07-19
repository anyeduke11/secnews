import React, { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem } from '../types';

interface ItemDetailDialogProps {
  item_id: string | null;
  onClose: () => void;
}

const DOMAINS = ['security', 'ai', 'finance', 'startup', 'engineering', 'product'];
const TYPES = ['news', 'analysis', 'paper', 'tutorial', 'tool', 'opinion'];
const DIFFICULTIES = ['beginner', 'intermediate', 'advanced', 'expert'];

const inputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

const labelStyle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: '10px',
  marginBottom: '2px',
  display: 'block',
};

export function ItemDetailDialog({ item_id, onClose }: ItemDetailDialogProps) {
  const [item, setItem] = useState<KnowledgeItem | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // 编辑字段
  const [domain, setDomain] = useState('');
  const [topic, setTopic] = useState('');
  const [type, setType] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [mastered, setMastered] = useState(0);

  const loadItem = useCallback((id: string) => {
    setLoading(true);
    setError(null);
    fetch(`/api/knowledge/items/${encodeURIComponent(id)}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const it = data as KnowledgeItem & { content?: string };
        setItem(it);
        setContent(it.content || '');
        setDomain(it.domain || '');
        setTopic(it.topic || '');
        setType(it.type || '');
        setDifficulty(it.difficulty || '');
        setTagsText((it.tags || []).join(', '));
        setMastered(it.mastered ?? 0);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (item_id) {
      // 重置状态
      setItem(null);
      setContent('');
      setError(null);
      setConfirmDelete(false);
      setToast(null);
      loadItem(item_id);
    }
  }, [item_id, loadItem]);

  if (!item_id) return null;

  const handleSave = () => {
    if (!item_id) return;
    const tagsArray = tagsText
      .split(',')
      .map(t => t.trim())
      .filter(t => t.length > 0);
    const body: Record<string, unknown> = {
      domain: domain || null,
      topic: topic || null,
      type: type || null,
      difficulty: difficulty || null,
      tags: tagsArray,
      mastered,
    };
    setSaving(true);
    fetch(`/api/knowledge/items/${encodeURIComponent(item_id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(() => {
        setToast('✓ 保存成功');
        setTimeout(() => setToast(null), 2500);
        // 重新加载
        loadItem(item_id);
      })
      .catch(e => {
        setToast(`✗ 保存失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setSaving(false));
  };

  const handleDelete = () => {
    if (!item_id) return;
    setDeleting(true);
    fetch(`/api/knowledge/items/${encodeURIComponent(item_id)}`, { method: 'DELETE' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        onClose();
      })
      .catch(e => {
        setToast(`✗ 删除失败: ${e?.message || String(e)}`);
        setTimeout(() => setToast(null), 2500);
      })
      .finally(() => setDeleting(false));
  };

  // G10.2: 仅 type=github 的条目显示「加入 CodeGarden」CTA
  // 调用 /api/codegarden/from-knowledge 幂等端点 (201=首次, 200=已存在)
  const handleAddToCodegarden = async () => {
    if (!item?.id) return;
    try {
      const r = await fetch('/api/codegarden/from-knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: item.id,
          source_type: 'reference',
        }),
      });
      if (!r.ok) {
        const body = await r.text().catch(() => '');
        throw new Error(`HTTP ${r.status}${body ? `: ${body}` : ''}`);
      }
      if (r.status === 201) {
        window.alert('✓ 已加入 CodeGarden');
      } else {
        window.alert('ℹ 该项目已在 CodeGarden 中');
      }
      onClose();
    } catch (e: any) {
      window.alert(`加入失败: ${e?.message || e}`);
    }
  };

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
          width: '800px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        {/* 顶部标题 */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            📄 条目详情
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

        {item && !loading && (
          <div className="space-y-3">
            {/* 1. 基本信息 */}
            <div>
              <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>基本信息</p>
              <div className="rounded-[var(--radius-sm)] p-2.5" style={{ backgroundColor: 'var(--bg-hover)' }}>
                <div className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                  {item.title}
                </div>
                <div className="text-[10px] space-y-0.5" style={{ color: 'var(--text-muted)' }}>
                  <div>来源: {item.source} {item.source_url && <span>· <a href={item.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--color-ai)' }}>原文链接</a></span>}</div>
                  <div>录入时间: {item.ingested_at}</div>
                </div>
              </div>
            </div>

            {/* 2. 分类编辑 */}
            <div>
              <p className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>分类</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label style={labelStyle}>domain</label>
                  <select style={inputStyle} value={domain} onChange={e => setDomain(e.target.value)}>
                    <option value="">(未设置)</option>
                    {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>topic</label>
                  <input type="text" style={inputStyle} value={topic} onChange={e => setTopic(e.target.value)} placeholder="主题" />
                </div>
                <div>
                  <label style={labelStyle}>type</label>
                  <select style={inputStyle} value={type} onChange={e => setType(e.target.value)}>
                    <option value="">(未设置)</option>
                    {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>difficulty</label>
                  <select style={inputStyle} value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                    <option value="">(未设置)</option>
                    {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* 3. 标签 */}
            <div>
              <label style={labelStyle}>tags (逗号分隔)</label>
              <input type="text" style={inputStyle} value={tagsText} onChange={e => setTagsText(e.target.value)} placeholder="tag1, tag2, ..." />
            </div>

            {/* 4. 概念列表（只读） */}
            <div>
              <label style={labelStyle}>concepts (只读)</label>
              <div className="flex flex-wrap gap-1">
                {item.concepts && item.concepts.length > 0 ? (
                  item.concepts.map(c => (
                    <span
                      key={c}
                      className="px-2 py-0.5 rounded-[var(--radius-sm)] text-[10px]"
                      style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--color-ai)' }}
                    >
                      {c}
                    </span>
                  ))
                ) : (
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>(无)</span>
                )}
              </div>
            </div>

            {/* 5. 掌握度 */}
            <div>
              <label style={labelStyle}>mastered: {mastered}</label>
              <input
                type="range"
                min={0}
                max={100}
                value={mastered}
                onChange={e => setMastered(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--color-ai)' }}
              />
            </div>

            {/* 6. Markdown 正文（只读） */}
            <div>
              <label style={labelStyle}>正文 (Markdown, 只读)</label>
              <pre
                className="rounded-[var(--radius-sm)] p-2.5 text-[11px] overflow-auto"
                style={{
                  backgroundColor: 'var(--bg-hover)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  maxHeight: '240px',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  margin: 0,
                }}
              >
{content || '(无正文)'}
              </pre>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-ghost px-3 py-1.5 text-xs"
                style={{ color: 'var(--color-ai)', opacity: saving ? 0.6 : 1 }}
              >
                {saving ? '保存中…' : '保存修改'}
              </button>
              {item.type === 'github' && (
                <button
                  onClick={handleAddToCodegarden}
                  className="btn-ghost px-3 py-1.5 text-xs"
                  style={{ color: '#8b5cf6' }}
                  title="转化为 CodeGarden 项目 (source_type=reference)"
                >
                  🌱 加入 CodeGarden
                </button>
              )}
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={deleting}
                className="btn-ghost px-3 py-1.5 text-xs"
                style={{ color: '#e85d5d', opacity: deleting ? 0.6 : 1 }}
              >
                删除
              </button>
              {toast && (
                <span className="text-[10px] ml-auto" style={{
                  color: toast.startsWith('✓') ? 'var(--color-ai)' : '#e85d5d',
                }}>
                  {toast}
                </span>
              )}
            </div>

            {/* 删除确认弹窗 */}
            {confirmDelete && (
              <div
                className="rounded-[var(--radius-sm)] p-3"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid #e85d5d' }}
              >
                <p className="text-xs mb-2" style={{ color: 'var(--text-primary)' }}>
                  确认删除此条目? 此操作不可撤销。
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="btn-ghost px-3 py-1 text-xs"
                    style={{ color: '#e85d5d', opacity: deleting ? 0.6 : 1 }}
                  >
                    {deleting ? '删除中…' : '确认删除'}
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="btn-ghost px-3 py-1 text-xs"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
