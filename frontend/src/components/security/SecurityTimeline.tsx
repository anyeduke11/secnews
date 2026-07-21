import React, { useState, useEffect } from 'react';
import { useSecurityGraph } from '../../hooks/useSecurityGraph';

interface TimelineEntry {
  date: string;
  cve_id: string;
  title: string;
  severity?: string;
  related_hotspots: Array<{ id: string; title: string; category: string }>;
}

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'var(--color-error)',
  HIGH: 'var(--color-bid)',
  MEDIUM: 'var(--color-warning)',
  LOW: 'var(--color-info)',
  NONE: 'var(--text-muted)',
};

export function SecurityTimeline() {
  const { data, loading, error } = useSecurityGraph('cve');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '200px', color: 'var(--text-muted)' }}>
        <p className="text-xs">加载中…</p>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-[var(--radius-sm)]"
           style={{ height: '200px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
        <p className="text-xs">暂无 CVE 数据</p>
      </div>
    );
  }

  const cveNodes = data.nodes.filter((n: any) => n.entity_type === 'cve');
  const filtered = severityFilter === 'all'
    ? cveNodes
    : cveNodes.filter((n: any) => (n.metadata?.severity || 'NONE') === severityFilter);

  return (
    <div className="space-y-3">
      {/* Severity filter */}
      <div className="flex gap-1.5">
        {['all', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(sev => (
          <button
            key={sev}
            onClick={() => setSeverityFilter(sev)}
            className="text-[10px] px-2 py-0.5 rounded"
            style={{
              backgroundColor: sev === severityFilter ? 'var(--bg-hover)' : 'transparent',
              color: sev === severityFilter ? 'var(--text-primary)' : 'var(--text-muted)',
              border: '1px solid var(--border-color)',
            }}
          >
            {sev === 'all' ? '全部' : sev}
          </button>
        ))}
      </div>

      {/* CVE list */}
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {filtered.map((node: any) => {
          const severity = node.metadata?.severity || 'NONE';
          return (
            <div
              key={node.id}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] text-xs"
              style={{ backgroundColor: 'var(--bg-hover)' }}
            >
              <span className="text-[10px] font-mono shrink-0" style={{ color: 'var(--text-muted)' }}>
                {node.id}
              </span>
              <span className="flex-1 truncate" style={{ color: 'var(--text-primary)' }}>
                {node.name}
              </span>
              <span className="text-[10px] px-1 py-0.5 rounded font-semibold shrink-0"
                    style={{ backgroundColor: SEVERITY_COLORS[severity] + '22', color: SEVERITY_COLORS[severity] }}>
                {severity}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
