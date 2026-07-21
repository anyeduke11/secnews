import React, { useState, useCallback, useRef } from 'react';

interface NormalizeResult {
  canonical: string;
  term_type: string;
  match_type: 'canonical' | 'synonym' | 'regex' | 'fuzzy' | 'none';
  confidence: number;
}

export function TermStandardizer() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<NormalizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const normalize = useCallback(async (text: string) => {
    if (!text.trim()) {
      setResult(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/security/terminology/normalize?text=${encodeURIComponent(text)}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setResult(json);
    } catch (err: any) {
      setError(err.message || '请求失败');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = useCallback((value: string) => {
    setInput(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => normalize(value), 300);
  }, [normalize]);

  const matchTypeLabel: Record<string, { label: string; color: string }> = {
    canonical: { label: '规范术语', color: 'var(--color-success)' },
    synonym: { label: '同义词', color: 'var(--color-info)' },
    regex: { label: '正则提取', color: 'var(--color-startup)' },
    fuzzy: { label: '模糊匹配', color: 'var(--color-warning)' },
    none: { label: '未匹配', color: 'var(--text-muted)' },
  };

  return (
    <div className="space-y-2">
      <div className="text-[11px] font-semibold" style={{ color: 'var(--text-secondary)' }}>
        安全术语标准化
      </div>
      <input
        type="text"
        value={input}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="输入需要标准化的术语..."
        className="w-full px-2.5 py-1.5 text-xs rounded-[var(--radius-sm)]"
        style={{
          backgroundColor: 'var(--bg-hover)',
          border: '1px solid var(--border-color)',
          color: 'var(--text-primary)',
          outline: 'none',
        }}
      />
      {loading && (
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>查询中…</div>
      )}
      {error && (
        <div className="text-[10px]" style={{ color: 'var(--color-error)' }}>{error}</div>
      )}
      {result && !loading && (
        <div className="rounded-[var(--radius-sm)] p-2 text-xs space-y-1"
             style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="flex items-center gap-2">
            <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              {result.canonical}
            </span>
            <span className="text-[10px] px-1 py-0.5 rounded"
                  style={{
                    backgroundColor: (matchTypeLabel[result.match_type]?.color || 'var(--text-muted)') + '22',
                    color: matchTypeLabel[result.match_type]?.color || 'var(--text-muted)',
                  }}>
              {matchTypeLabel[result.match_type]?.label || result.match_type}
            </span>
          </div>
          <div style={{ color: 'var(--text-muted)' }}>
            类型: {result.term_type} | 置信度: {(result.confidence * 100).toFixed(0)}%
          </div>
        </div>
      )}
    </div>
  );
}
