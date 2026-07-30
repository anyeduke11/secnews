import React, { useState, useCallback } from 'react';
import { TIME_OPTIONS } from '../types';
import { Icon } from './Icon';

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
    <div className="mb-3">
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <form onSubmit={handleSubmit} className="w-full sm:flex-1 min-w-0">
          <div className="search-box">
            <span className="search-icon text-tech">//</span>
            <input
              type="text"
              value={localKeyword}
              onChange={(e) => setLocalKeyword(e.target.value)}
              placeholder="搜索热点关键词..."
              className="focus-ring font-mono"
            />
            {localKeyword && (
              <button
                type="button"
                onClick={handleClear}
                className="search-clear focus-ring"
                aria-label="清空搜索"
              >
                <Icon size={12}>
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </Icon>
              </button>
            )}
          </div>
        </form>

        <div className="time-toggle self-start sm:self-auto shrink-0">
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onTimeRangeChange(opt.value)}
              className={`focus-ring ${timeRange === opt.value ? 'active' : ''}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
