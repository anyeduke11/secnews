import React, { useState, useEffect } from 'react';

interface KnowledgeFiltersProps {
  onFilterChange: (filters: FilterState) => void;
}

export interface FilterState {
  domain: string;
  topic: string;
  type: string;
  difficulty: string;
  timeRange: 'week' | 'month' | 'all';
}

const DOMAINS = ['security', 'ai', 'finance', 'product', 'engineering', 'business', 'design', 'other'];
const TYPES = ['news', 'analysis', 'paper', 'tutorial', 'tool', 'opinion', 'case-study', 'report'];
const DIFFICULTIES = ['beginner', 'intermediate', 'advanced', 'expert'];

export function KnowledgeFilters({ onFilterChange }: KnowledgeFiltersProps) {
  const [filters, setFilters] = useState<FilterState>({
    domain: '', topic: '', type: '', difficulty: '', timeRange: 'all',
  });
  const [topics, setTopics] = useState<string[]>([]);

  // Fetch topics when domain changes (skip when empty to avoid needless async updates)
  useEffect(() => {
    if (!filters.domain) {
      setTopics([]);
      return;
    }
    fetch(`/api/knowledge/topics?domain=${encodeURIComponent(filters.domain)}`)
      .then(r => r.json())
      .then(d => setTopics(d.topics || []))
      .catch(() => setTopics([]));
  }, [filters.domain]);

  // Notify parent of filter changes
  useEffect(() => {
    onFilterChange(filters);
  }, [filters, onFilterChange]);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select
        className="tech-select px-2 py-1 text-[11px]"
        value={filters.domain}
        onChange={e => setFilters({ ...filters, domain: e.target.value, topic: '' })}
      >
        <option value="">全部领域</option>
        {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      <select
        className="tech-select px-2 py-1 text-[11px]"
        value={filters.topic}
        onChange={e => setFilters({ ...filters, topic: e.target.value })}
        disabled={topics.length === 0}
      >
        <option value="">全部主题</option>
        {topics.map(t => <option key={t} value={t}>{t}</option>)}
      </select>

      <select
        className="tech-select px-2 py-1 text-[11px]"
        value={filters.type}
        onChange={e => setFilters({ ...filters, type: e.target.value })}
      >
        <option value="">全部类型</option>
        {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
      </select>

      <select
        className="tech-select px-2 py-1 text-[11px]"
        value={filters.difficulty}
        onChange={e => setFilters({ ...filters, difficulty: e.target.value })}
      >
        <option value="">全部难度</option>
        {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      <select
        className="tech-select px-2 py-1 text-[11px]"
        value={filters.timeRange}
        onChange={e => setFilters({ ...filters, timeRange: e.target.value as FilterState['timeRange'] })}
      >
        <option value="all">全部时间</option>
        <option value="week">本周</option>
        <option value="month">本月</option>
      </select>
    </div>
  );
}
