// frontend/src/components/codegarden/FromKnowledgeDialog.tsx
import { useEffect, useState, CSSProperties } from 'react';
import { CandidateItem, FromKnowledgeRequest, ProjectSourceType } from '../../types/codegarden';

interface FromKnowledgeDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
  listCandidates: () => Promise<CandidateItem[]>;
  importFn: (req: FromKnowledgeRequest) => Promise<unknown>;
}

const inputStyle: CSSProperties = {
  backgroundColor: 'var(--bg-hover)',
  border: '1px solid var(--border-color)',
  color: 'var(--text-primary)',
  borderRadius: 'var(--radius-sm)',
  padding: '4px 8px',
  fontSize: '12px',
  width: '100%',
};

export function FromKnowledgeDialog({ open, onClose, onImported, listCandidates, importFn }: FromKnowledgeDialogProps) {
  const [candidates, setCandidates] = useState<CandidateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<ProjectSourceType>('reference');
  const [localPath, setLocalPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelectedId(null);
    setSourceType('reference');
    setLocalPath('');
    setToast(null);
    listCandidates()
      .then(items => setCandidates(items))
      .catch(e => setToast({ kind: 'err', msg: `加载失败: ${e?.message || e}` }))
      .finally(() => setLoading(false));
  }, [open, listCandidates]);

  if (!open) return null;

  const flash = (kind: 'ok' | 'err', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const handleSubmit = async () => {
    if (!selectedId) { flash('err', '请选择一条资讯'); return; }
    setBusy(true);
    try {
      const req: FromKnowledgeRequest = {
        item_id: selectedId,
        source_type: sourceType,
      };
      if (localPath.trim()) req.local_path = localPath.trim();
      await importFn(req);
      flash('ok', '✓ 已加入 CodeGarden');
      setTimeout(() => { onClose(); onImported(); }, 800);
    } catch (e: any) {
      flash('err', e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl max-h-[80vh] flex flex-col rounded-[var(--radius-md)] p-4"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            从知识库导入 (GitHub 资讯)
          </h3>
          <button onClick={onClose} className="btn-ghost px-2 py-1 text-xs">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto mb-3">
          {loading ? (
            <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>加载中…</div>
          ) : candidates.length === 0 ? (
            <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
              暂无 type=github 的未转化资讯
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {candidates.map(c => (
                <label
                  key={c.id}
                  className="flex items-start gap-2 p-2 rounded cursor-pointer"
                  style={{
                    backgroundColor: selectedId === c.id ? 'var(--bg-hover)' : 'transparent',
                    border: '1px solid',
                    borderColor: selectedId === c.id ? 'var(--color-ai)' : 'var(--border-color)',
                  }}
                >
                  <input
                    type="radio"
                    name="candidate"
                    checked={selectedId === c.id}
                    onChange={() => setSelectedId(c.id)}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }} title={c.title}>
                      {c.title}
                    </div>
                    <div className="text-[10px] font-mono truncate" style={{ color: 'var(--text-muted)' }}>
                      {c.source_url}
                    </div>
                    <div className="text-[9px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {new Date(c.ingested_at).toLocaleString()}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        {selectedId && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Source Type</label>
              <select style={inputStyle} value={sourceType} onChange={(e) => setSourceType(e.target.value as ProjectSourceType)}>
                <option value="reference">reference (参考)</option>
                <option value="fork">fork (二开)</option>
                <option value="imported">imported (导入)</option>
              </select>
            </div>
            <div>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Local Path (可选)</label>
              <input style={inputStyle} value={localPath} onChange={(e) => setLocalPath(e.target.value)} placeholder="~/code/repo" />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost px-3 py-1.5 text-xs">取消</button>
          <button
            onClick={handleSubmit}
            disabled={busy || !selectedId}
            className="btn-ghost px-3 py-1.5 text-xs"
            style={{ color: 'var(--color-ai)', borderColor: 'var(--color-ai)', opacity: busy || !selectedId ? 0.5 : 1 }}
          >
            {busy ? '导入中…' : '加入 CodeGarden'}
          </button>
        </div>

        {toast && (
          <div
            className="mt-2 text-xs px-2 py-1 rounded"
            style={{
              backgroundColor: toast.kind === 'ok' ? '#00c96a20' : '#e85d5d20',
              color: toast.kind === 'ok' ? '#00c96a' : '#e85d5d',
            }}
          >
            {toast.msg}
          </div>
        )}
      </div>
    </div>
  );
}
