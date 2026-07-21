import React, { useState, useEffect } from 'react';
import { useSecurityGraph } from '../../hooks/useSecurityGraph';

export function ComplianceMatrix() {
  const { data, loading, error } = useSecurityGraph('compliance');

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
        <p className="text-xs">暂无合规数据</p>
      </div>
    );
  }

  const complianceNodes = data.nodes.filter((n: any) => n.entity_type === 'compliance');
  const knowledgeNodes = data.nodes.filter((n: any) => n.entity_type === 'knowledge_item');

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[var(--radius-sm)] p-2 text-center"
             style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            {complianceNodes.length}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>合规条款</div>
        </div>
        <div className="rounded-[var(--radius-sm)] p-2 text-center"
             style={{ backgroundColor: 'var(--bg-hover)' }}>
          <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            {knowledgeNodes.length}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>关联知识条目</div>
        </div>
      </div>

      {/* Compliance items */}
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {complianceNodes.map((node: any) => (
          <div
            key={node.id}
            className="rounded-[var(--radius-sm)] p-2"
            style={{ backgroundColor: 'var(--bg-hover)' }}
          >
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold" style={{ color: 'var(--color-ai)' }}>
                {node.id}
              </span>
              <span className="text-xs truncate flex-1" style={{ color: 'var(--text-primary)' }}>
                {node.name}
              </span>
            </div>
            {node.description && (
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {node.description}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
