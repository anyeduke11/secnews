/**
 * SecNewsAnalyze — 研判视图 (workbench/AnalyzeView 并入 SecNews)
 *
 * URL 导入 (POST /api/kl/import/url) + 自由文本双轨研判 (dsh + LLM evaluate)。
 * 反馈契约: 每条请求独立 error state, 失败显式呈现; dsh gate 关闭时
 * 按钮禁用并说明原因 (feature flag 由 /api/settings/features 派生)。
 */
import { useState } from 'react';
import { useFeatureFlags } from '../../../hooks/useFeatureFlags';

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
  error?: string;
}

export function SecNewsAnalyze() {
  const flags = useFeatureFlags();

  const [url, setUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [analyzeInput, setAnalyzeInput] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [dshResult, setDshResult] = useState<DshTaskResult | null>(null);
  const [dshError, setDshError] = useState<string | null>(null);
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);

  const handleImport = async () => {
    if (!url.trim()) return;
    setImporting(true);
    setImportResult(null);
    setImportError(null);
    try {
      const r = await fetch('/api/kl/import/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!r.ok) {
        setImportError(`导入失败 (${r.status})`);
        return;
      }
      setImportResult(await r.json());
    } catch {
      setImportError('导入失败: 网络或后端不可达');
    } finally {
      setImporting(false);
    }
  };

  const handleAnalyze = async () => {
    if (!analyzeInput.trim()) return;
    setAnalyzing(true);
    setDshResult(null);
    setDshError(null);
    setEvalResult(null);
    setEvalError(null);
    try {
      // dsh gate 关闭时不发请求, 直接呈现禁用原因
      if (flags.dsh) {
        const dshR = await fetch('/api/dsh/task', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_type: 'classify', payload: { content: analyzeInput } }),
        });
        if (!dshR.ok) {
          setDshError(`dsh 研判失败 (${dshR.status})`);
        } else {
          setDshResult(await dshR.json());
        }
      }

      const evalR = await fetch('/api/llm/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: analyzeInput }),
      });
      if (!evalR.ok) {
        setEvalError(`LLM 评测失败 (${evalR.status})`);
      } else {
        const d = await evalR.json();
        if (d.ok === false) {
          setEvalError(String(d.error || 'LLM 调用失败'));
        } else {
          setEvalResult(d);
        }
      }
    } catch {
      setEvalError('研判失败: 网络或后端不可达');
    } finally {
      setAnalyzing(false);
    }
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
        {importError && (
          <p className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-error)' }}>{importError}</p>
        )}
        {importResult && (
          <p className="mt-2 text-[10px] font-mono" style={{ color: 'var(--color-success)' }}>
            ✓ {importResult.id} · {importResult.title}
          </p>
        )}
      </section>

      {/* 深度研判 */}
      <section className="p-3 rounded-[var(--radius-sm)]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}>
        <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          深度研判 {flags.dsh ? '(dsh / LLM 双轨)' : '(LLM 单轨 — dsh 桥接未启用)'}
        </h3>
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

        {(dshError || dshResult || evalError || evalResult) && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {flags.dsh && (
              <div className="p-2 rounded text-[10px] font-mono"
                style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
                <div style={{ color: 'var(--text-muted)' }}>dsh</div>
                {dshError && <div className="mt-1" style={{ color: 'var(--color-error)' }}>{dshError}</div>}
                {dshResult && (
                  <>
                    <div className="mt-1" style={{ color: 'var(--text-muted)' }}>agent={dshResult.agent}</div>
                    <div className="mt-1" style={{
                      color: dshResult.ok ? 'var(--color-success)' : 'var(--color-error)',
                    }}>
                      {dshResult.ok ? `result: ${String(dshResult.result ?? '–')}` : `error: ${dshResult.error ?? '–'}`}
                    </div>
                    {dshResult.session_id && (
                      <div className="mt-1" style={{ color: 'var(--text-muted)' }}>session: {dshResult.session_id}</div>
                    )}
                  </>
                )}
                {!dshError && !dshResult && (
                  <div className="mt-1" style={{ color: 'var(--text-muted)' }}>未执行</div>
                )}
              </div>
            )}
            <div className="p-2 rounded text-[10px] font-mono"
              style={{ backgroundColor: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-muted)' }}>LLM evaluate</div>
              {evalError && <div className="mt-1" style={{ color: 'var(--color-error)' }}>{evalError}</div>}
              {evalResult && (
                <>
                  <div className="mt-1 text-base font-bold" style={{ color: 'var(--accent)' }}>
                    score: {evalResult.score}
                  </div>
                  {evalResult.reasoning && (
                    <div className="mt-1" style={{ color: 'var(--text-secondary)' }}>{evalResult.reasoning}</div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
