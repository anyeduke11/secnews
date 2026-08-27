/**
 * AnalyzeView — 工作台研判视图 (Phase 4 v0.6.1)
 *
 * URL 导入 + 深度研判 (dsh) + LLM 评分。
 * 数据源: POST /api/kl/import/url · POST /api/dsh/task · POST /api/llm/evaluate
 */
import { useState } from 'react';

interface ImportResult {
  id: string;
  title: string;
  url: string;
}

interface DshTaskResult {
  ok: boolean;
  agent: string;
  result?: number | string;
  error?: string;
  session_id?: string;
}

interface EvalResult {
  score: number;
  reasoning?: string;
}

export function AnalyzeView() {
  const [url, setUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const [analyzeInput, setAnalyzeInput] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [dshResult, setDshResult] = useState<DshTaskResult | null>(null);
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);

  const handleImport = async () => {
    if (!url.trim()) return;
    setImporting(true);
    setImportResult(null);
    try {
      const r = await fetch('/api/kl/import/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (r.ok) setImportResult(await r.json());
    } catch { /* silent */ }
    finally { setImporting(false); }
  };

  const handleAnalyze = async () => {
    if (!analyzeInput.trim()) return;
    setAnalyzing(true);
    setDshResult(null);
    setEvalResult(null);
    try {
      const [dshR, evalR] = await Promise.all([
        fetch('/api/dsh/task', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_type: 'classify', payload: { content: analyzeInput } }),
        }),
        fetch('/api/llm/evaluate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: analyzeInput }),
        }),
      ]);
      if (dshR.ok) setDshResult(await dshR.json());
      if (evalR.ok) setEvalResult(await evalR.json());
    } catch { /* silent */ }
    finally { setAnalyzing(false); }
  };

  return (
    <div className="space-y-3 max-w-4xl">
      {/* URL 导入 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>URL 导入</h3>
        <div className="flex items-center gap-2">
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 px-2 py-1 text-xs font-mono rounded"
            style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <button onClick={handleImport} disabled={importing || !url.trim()}
            className="btn-secondary text-[10px] px-3 py-1">
            {importing ? '导入中...' : '导入'}
          </button>
        </div>
        {importResult && (
          <p className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
            ✓ {importResult.id} · {importResult.title}
          </p>
        )}
      </section>

      {/* 深度研判 */}
      <section className="p-3 rounded-[var(--radius-sm])" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>深度研判 (dsh / LLM 双轨)</h3>
        <textarea
          value={analyzeInput}
          onChange={e => setAnalyzeInput(e.target.value)}
          placeholder="粘贴待研判的文本..."
          rows={4}
          className="w-full px-2 py-1.5 text-[11px] font-mono rounded resize-y"
          style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />
        <button onClick={handleAnalyze} disabled={analyzing || !analyzeInput.trim()}
          className="btn-secondary text-[10px] px-3 py-1 mt-2">
          {analyzing ? '研判中...' : '开始研判'}
        </button>

        {(dshResult || evalResult) && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {dshResult && (
              <div className="p-2 rounded text-[10px] font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
                <div style={{ color: 'var(--text-muted)' }}>dsh · agent={dshResult.agent}</div>
                <div className="mt-1" style={{
                  color: dshResult.ok ? 'var(--color-success)' : 'var(--color-error)',
                }}>
                  {dshResult.ok ? `result: ${String(dshResult.result ?? '–')}` : `error: ${dshResult.error ?? '–'}`}
                </div>
                {dshResult.session_id && (
                  <div className="mt-1" style={{ color: 'var(--text-muted)' }}>session: {dshResult.session_id}</div>
                )}
              </div>
            )}
            {evalResult && (
              <div className="p-2 rounded text-[10px] font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
                <div style={{ color: 'var(--text-muted)' }}>LLM evaluate</div>
                <div className="mt-1 text-base font-bold" style={{ color: 'var(--accent)' }}>
                  score: {evalResult.score}
                </div>
                {evalResult.reasoning && (
                  <div className="mt-1" style={{ color: 'var(--text-secondary)' }}>{evalResult.reasoning}</div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}