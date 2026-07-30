/**
 * KnowledgeProcess — 处理数据子页面
 *
 * 结构化与检索:
 *  - 知识图谱 (概念 / ATT&CK / CVE / 合规 四个视图)
 *  - 条目筛选器 + 联邦搜索入口
 *  - 知识条目列表 (item detail / concept detail 弹窗)
 */
import React, { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem } from '../../types';
import { KnowledgeGraph } from '../KnowledgeGraph';
import { SecurityGraph } from '../security/SecurityGraph';
import { ComplianceMatrix } from '../security/ComplianceMatrix';
import { KnowledgeFilters, FilterState } from '../KnowledgeFilters';
import { ItemDetailDialog } from '../ItemDetailDialog';
import { ConceptDetailDialog } from '../ConceptDetailDialog';
import { Icon } from '../Icon';
import { KNOWLEDGE_AREAS } from './KnowledgeTabs';

type GraphView = 'concepts' | 'attack' | 'cve' | 'compliance';

export function KnowledgeProcess() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    domain: '', topic: '', type: '', difficulty: '', timeRange: 'all',
  });
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [graphView, setGraphView] = useState<GraphView>('concepts');

  const area = KNOWLEDGE_AREAS.find(a => a.key === 'process')!;

  const loadItems = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: '50' });
    if (filters.domain) params.set('domain', filters.domain);
    if (filters.topic) params.set('topic', filters.topic);
    if (filters.type) params.set('type', filters.type);
    if (filters.difficulty) params.set('difficulty', filters.difficulty);
    if (filters.timeRange === 'week' || filters.timeRange === 'month') {
      const now = new Date();
      const start = new Date();
      if (filters.timeRange === 'week') start.setDate(now.getDate() - 7);
      else start.setMonth(now.getMonth() - 1);
      params.set('since', start.toISOString().split('T')[0]);
    }
    fetch(`/api/knowledge/items?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setItems(data.items || []);
        setLoading(false);
      })
      .catch(e => {
        setError(e?.message || String(e));
        setLoading(false);
      });
  }, [filters]);

  useEffect(() => { loadItems(); }, [loadItems]);

  return (
    <div
      className="space-y-4"
      style={
        {
          '--area-accent': area.accentVar,
        } as React.CSSProperties
      }
      data-area-page="process"
    >
      {/* 知识图谱 */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h3
            className="text-sm font-semibold flex items-center gap-2"
            style={{ color: 'var(--text-primary)' }}
          >
            <span
              className="w-5 h-5 rounded-sm flex items-center justify-center"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
                color: 'var(--area-accent)',
              }}
            >
              <Icon size={11}>
                <circle cx="12" cy="12" r="3" />
                <circle cx="4" cy="4" r="2" />
                <circle cx="20" cy="4" r="2" />
                <circle cx="4" cy="20" r="2" />
                <circle cx="20" cy="20" r="2" />
                <line x1="6" y1="6" x2="10" y2="10" />
                <line x1="18" y1="6" x2="14" y2="10" />
                <line x1="6" y1="18" x2="10" y2="14" />
                <line x1="18" y1="18" x2="14" y2="14" />
              </Icon>
            </span>
            知识图谱
          </h3>
          <div className="flex gap-1">
            {(['concepts', 'attack', 'cve', 'compliance'] as const).map(v => (
              <button
                key={v}
                onClick={() => setGraphView(v)}
                className="text-[10px] px-2 py-0.5 rounded-[var(--radius-sm)] font-medium"
                style={{
                  backgroundColor: graphView === v
                    ? 'color-mix(in srgb, var(--area-accent) 10%, transparent)'
                    : 'transparent',
                  color: graphView === v ? 'var(--area-accent)' : 'var(--text-muted)',
                  border: `1px solid ${graphView === v
                    ? 'color-mix(in srgb, var(--area-accent) 40%, transparent)'
                    : 'var(--border-color)'}`,
                }}
              >
                {v === 'concepts' ? '概念' : v === 'attack' ? 'ATT&CK' : v === 'cve' ? 'CVE' : '合规'}
              </button>
            ))}
          </div>
        </div>
        <div
          className="rounded-[var(--radius-md)] p-4"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
        >
          {graphView === 'concepts' && (
            <KnowledgeGraph domain={filters.domain || undefined} onSelectConcept={setSelectedSlug} />
          )}
          {graphView === 'attack' && <SecurityGraph view="attack" />}
          {graphView === 'cve' && <SecurityGraph view="cve" />}
          {graphView === 'compliance' && <ComplianceMatrix />}
        </div>
      </section>

      {/* 筛选 + 条目列表 */}
      <section>
        <h3
          className="text-sm font-semibold flex items-center gap-2 mb-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <span
            className="w-5 h-5 rounded-sm flex items-center justify-center"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--area-accent) 14%, transparent)',
              color: 'var(--area-accent)',
            }}
          >
            <Icon size={11}>
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
            </Icon>
          </span>
          知识条目
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            {loading ? '加载中…' : `${items.length} 条`}
          </span>
        </h3>

        <div className="mb-3">
          <KnowledgeFilters onFilterChange={setFilters} />
        </div>

        {error && (
          <div
            className="rounded-[var(--radius-md)] p-2.5 mb-3 text-xs"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-error) 12%, transparent)',
              border: '1px solid var(--color-error)',
              color: 'var(--color-error)',
            }}
          >
            加载失败: {error}
          </div>
        )}

        {loading ? (
          <p
            className="text-xs py-4 text-center"
            style={{ color: 'var(--text-muted)' }}
          >
            加载中…
          </p>
        ) : items.length === 0 ? (
          <p
            className="text-xs py-4 text-center"
            style={{ color: 'var(--text-muted)' }}
          >
            暂无条目。请先到「信息导入」同步 Cubox 或收藏资讯。
          </p>
        ) : (
          <div className="space-y-2">
            {items.map(item => (
              <div
                key={item.id}
                onClick={() => setSelectedItemId(item.id)}
                className="flex items-center gap-3 p-3 rounded-[var(--radius-md)] text-xs"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  border: '1px solid var(--border-color)',
                  cursor: 'pointer',
                  transition: 'border-color var(--duration-fast) var(--ease-out), background var(--duration-fast) var(--ease-out)',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--area-accent) 50%, var(--border-color))';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = 'var(--border-color)';
                }}
              >
                <span
                  className="px-2 py-0.5 rounded-[var(--radius-sm)] text-[10px] font-medium shrink-0"
                  style={{
                    backgroundColor: 'color-mix(in srgb, var(--area-accent) 10%, transparent)',
                    color: 'var(--area-accent)',
                  }}
                >
                  {item.source}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{ color: 'var(--text-primary)' }}
                  title={item.title}
                >
                  {item.title}
                </span>
                {item.domain && (
                  <span className="shrink-0" style={{ color: 'var(--text-muted)' }}>
                    {item.domain}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <ItemDetailDialog item_id={selectedItemId} onClose={() => setSelectedItemId(null)} />
      <ConceptDetailDialog
        slug={selectedSlug}
        onClose={() => setSelectedSlug(null)}
        onSelectItem={setSelectedItemId}
      />
    </div>
  );
}
