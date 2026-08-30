/**
 * ExtractPage — 自动标签提取 (找回丢失前端入口 v1.7 Phase 1)
 *
 * 文本预览提取 (不持久化) + 按热点/知识条目 ID 触发提取 (持久化)。
 * 数据源: POST /api/extract/preview · POST /api/extract/hotspot/{id} · POST /api/extract/knowledge/{id}
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../Icon';

interface TagSuggestion {
  id?: string;
  label?: string;
  [key: string]: unknown;
}

function tagLabel(t: TagSuggestion): string {
  return String(t.label ?? t.id ?? JSON.stringify(t));
}

export function ExtractPage({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate();
  const goBack = onBack ?? (() => navigate('/'));

  // 预览
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const [previewTags, setPreviewTags] = useState<TagSuggestion[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // 触发提取
  const [hotspotId, setHotspotId] = useState('');
  const [knowledgeId, setKnowledgeId] = useState('');
  const [extracting, setExtracting] = useState<'hotspot' | 'knowledge' | null>(null);
  const [extractMsg, setExtractMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const handlePreview = async () => {
    if (!title.trim() && !text.trim()) return;
    setPreviewing(true);
    setPreviewError(null);
    setPreviewTags(null);
    try {
      const r = await fetch('/api/extract/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), text: text.trim(), category: category.trim() }),
      });
      if (!r.ok) {
        setPreviewError(`预览失败 (${r.status})`);
        return;
      }
      const d = await r.json();
      setPreviewTags(d.items ?? []);
    } catch {
      setPreviewError('预览失败: 网络或后端不可达');
    } finally {
      setPreviewing(false);
    }
  };

  const runExtract = async (kind: 'hotspot' | 'knowledge') => {
    const id = (kind === 'hotspot' ? hotspotId : knowledgeId).trim();
    if (!id) return;
    setExtracting(kind);
    setExtractMsg(null);
    try {
      const r = await fetch(`/api/extract/${kind}/${encodeURIComponent(id)}`, { method: 'POST' });
      if (!r.ok) {
        const detail = await r.json().catch(() => null);
        setExtractMsg({ kind: 'err', text: `提取失败 (${r.status})${detail?.detail?.message ? `: ${detail.detail.message}` : ''}` });
        return;
      }
      const d = await r.json();
      const tags: string[] = (d.attached ?? d.tags ?? []).map(tagLabel);
      setExtractMsg({ kind: 'ok', text: `已提取并关联 ${tags.length} 个标签: ${tags.slice(0, 8).join(', ')}${tags.length > 8 ? '…' : ''}` });
    } catch {
      setExtractMsg({ kind: 'err', text: '提取失败: 网络或后端不可达' });
    } finally {
      setExtracting(null);
    }
  };

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between pb-2 mb-1" style={{ borderBottom: '2px solid var(--text-primary)' }}>
        <h1 className="text-sm font-bold tracking-wide" style={{ color: 'var(--text-primary)' }}>
          <span className="font-mono mr-2">EXT</span>自动标签提取
        </h1>
        <button onClick={goBack} className="btn-ghost gap-1.5 px-2 py-1 text-[10px]" aria-label="返回首页">
          <Icon size={11}>
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </Icon>
          <span className="hidden sm:inline">返回首页</span>
        </button>
      </div>

      {/* 预览 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          文本预览 <span className="font-normal" style={{ color: 'var(--text-muted)' }}>(不持久化)</span>
        </h3>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="标题"
          className="w-full px-2 py-1 text-xs font-mono rounded mb-1.5"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="正文文本..." rows={4}
          className="w-full px-2 py-1.5 text-[11px] font-mono rounded resize-y mb-1.5"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
        <div className="flex items-center gap-2">
          <input value={category} onChange={e => setCategory(e.target.value)} placeholder="分类 (ai/security/finance/...)"
            className="flex-1 px-2 py-1 text-xs font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
          <button onClick={handlePreview} disabled={previewing || (!title.trim() && !text.trim())}
            className="btn-secondary text-[10px] px-3 py-1">
            {previewing ? '提取中...' : '预览提取'}
          </button>
        </div>
        {previewError && (
          <p className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-error)' }}>{previewError}</p>
        )}
        {previewTags && (
          <div className="mt-2">
            {previewTags.length === 0 ? (
              <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>未命中任何标签</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {previewTags.map((t, i) => (
                  <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                    style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}>
                    {tagLabel(t)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 按条目触发 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          按条目触发 <span className="font-normal" style={{ color: 'var(--text-muted)' }}>(提取结果持久化 + SSE extract_done 事件)</span>
        </h3>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--text-muted)' }}>hotspot</span>
            <input value={hotspotId} onChange={e => setHotspotId(e.target.value)} placeholder="热点 ID"
              className="flex-1 px-2 py-1 text-xs font-mono rounded"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
            <button onClick={() => runExtract('hotspot')} disabled={extracting !== null || !hotspotId.trim()}
              className="btn-secondary text-[10px] px-3 py-1">
              {extracting === 'hotspot' ? '提取中...' : '提取'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono w-16 shrink-0" style={{ color: 'var(--text-muted)' }}>knowledge</span>
            <input value={knowledgeId} onChange={e => setKnowledgeId(e.target.value)} placeholder="知识条目 ID"
              className="flex-1 px-2 py-1 text-xs font-mono rounded"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} />
            <button onClick={() => runExtract('knowledge')} disabled={extracting !== null || !knowledgeId.trim()}
              className="btn-secondary text-[10px] px-3 py-1">
              {extracting === 'knowledge' ? '提取中...' : '提取'}
            </button>
          </div>
        </div>
        {extractMsg && (
          <p className="mt-2 text-[10px] font-mono"
            style={{ color: extractMsg.kind === 'ok' ? 'var(--color-success)' : 'var(--color-error)' }}>
            {extractMsg.text}
          </p>
        )}
      </section>
    </div>
  );
}
