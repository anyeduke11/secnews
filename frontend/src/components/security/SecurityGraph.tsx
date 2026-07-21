import React, { useState, useEffect } from 'react';
import { useSecurityGraph, SecurityEntity } from '../../hooks/useSecurityGraph';
import { SecurityEntityDetail } from './SecurityEntityDetail';

interface SecurityGraphProps {
  view: 'attack' | 'cve' | 'compliance';
}

const ENTITY_COLORS: Record<string, string> = {
  tactic: 'var(--color-error)',
  technique: 'var(--color-warning)',
  cve: 'var(--color-bid)',
  cwe: 'var(--color-startup)',
  compliance: 'var(--color-info)',
  product: 'var(--color-startup)',
  knowledge_item: 'var(--text-muted)',
};

const ENTITY_LABELS: Record<string, string> = {
  tactic: '战术',
  technique: '技术',
  cve: '漏洞',
  compliance: '合规',
  knowledge_item: '知识条目',
};

export function SecurityGraph({ view }: SecurityGraphProps) {
  const { data, loading, error } = useSecurityGraph(view);
  const [selectedEntity, setSelectedEntity] = useState<SecurityEntity | null>(null);

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '300px', color: 'var(--text-muted)' }}>
        <p className="text-xs">加载中…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center rounded-[var(--radius-sm)]"
           style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--color-error)' }}>
        <p className="text-xs">加载失败: {error}</p>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-[var(--radius-sm)]"
           style={{ height: '300px', backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
        <p className="text-xs">暂无安全数据。请先同步 MITRE ATT&CK 数据。</p>
      </div>
    );
  }

  const { stats } = data;

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {Object.entries(stats).map(([key, value]) => {
          const labelMap: Record<string, string> = {
            tactics: '战术', techniques: '技术', cves: 'CVE',
            compliance_items: '合规', knowledge_items: '知识条目',
          };
          return (
            <div key={key}
              className="rounded-[var(--radius-sm)] p-2 text-center"
              style={{ backgroundColor: 'var(--bg-hover)' }}
            >
              <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{value}</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{labelMap[key] || key}</div>
            </div>
          );
        })}
      </div>

      {/* Entity list */}
      <div className="space-y-1 max-h-80 overflow-y-auto">
        {data.nodes.map((node: any) => (
          <div
            key={node.id}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] cursor-pointer text-xs"
            style={{
              backgroundColor: 'var(--bg-hover)',
              borderLeft: `3px solid ${ENTITY_COLORS[node.entity_type] || 'var(--text-muted)'}`,
            }}
            onClick={() => setSelectedEntity(node)}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.8'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
          >
            <span className="font-medium truncate flex-1" style={{ color: 'var(--text-primary)' }}>
              {node.name}
            </span>
            <span className="shrink-0" style={{ color: ENTITY_COLORS[node.entity_type] || 'var(--text-muted)' }}>
              {ENTITY_LABELS[node.entity_type] || node.entity_type}
            </span>
          </div>
        ))}
      </div>

      {/* Detail panel */}
      {selectedEntity && (
        <SecurityEntityDetail
          entity={selectedEntity}
          onClose={() => setSelectedEntity(null)}
        />
      )}
    </div>
  );
}
