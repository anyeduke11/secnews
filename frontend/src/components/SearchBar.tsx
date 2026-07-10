import React, { useState, useCallback } from 'react';
import { TIME_OPTIONS } from '../types';

interface SearchBarProps {
  keyword: string;
  timeRange: string;
  onKeywordChange: (kw: string) => void;
  onTimeRangeChange: (range: string) => void;
}

export function SearchBar({ keyword, timeRange, onKeywordChange, onTimeRangeChange }: SearchBarProps) {
  const [localKeyword, setLocalKeyword] = useState(keyword);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    onKeywordChange(localKeyword);
  }, [localKeyword, onKeywordChange]);

  const handleClear = useCallback(() => {
    setLocalKeyword('');
    onKeywordChange('');
  }, [onKeywordChange]);

  return (
    <div className="mb-4">
      <label className="text-[11px] font-medium mb-1.5 block" style={{ color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
        搜索与筛选
      </label>
      <div className="flex items-center gap-2 flex-wrap">
        <form onSubmit={handleSubmit} className="flex-1 min-w-[200px]">
          <div className="relative">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-muted)' }}
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              value={localKeyword}
              onChange={(e) => setLocalKeyword(e.target.value)}
              placeholder="搜索热点关键词"
              className="w-full pl-9 pr-8 py-2 text-xs focus-ring"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
              }}
            />
            {localKeyword && (
              <button
                type="button"
                onClick={handleClear}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px]"
                style={{ color: 'var(--text-muted)' }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
        </form>

        <div className="flex gap-px p-0.5" style={{ backgroundColor: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onTimeRangeChange(opt.value)}
              className="focus-ring"
              style={{
                padding: '5px 12px',
                fontSize: '11px',
                fontWeight: timeRange === opt.value ? 600 : 400,
                borderRadius: 'calc(var(--radius-sm) - 1px)',
                backgroundColor: timeRange === opt.value ? 'var(--bg-card)' : 'transparent',
                border: timeRange === opt.value ? '1px solid var(--border-color)' : '1px solid transparent',
                color: timeRange === opt.value ? 'var(--text-primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                transition: 'all 0.12s ease',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
