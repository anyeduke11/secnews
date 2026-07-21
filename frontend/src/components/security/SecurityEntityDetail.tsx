import React, { useState, useEffect } from 'react';
import { SecurityEntity } from '../../hooks/useSecurityGraph';

interface DetailProps {
  entity: SecurityEntity;
  onClose: () => void;
}

export function SecurityEntityDetail({ entity, onClose }: DetailProps) {
  const [related, setRelated] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/security/entities/${encodeURIComponent(entity.id)}/related?depth=1`)
      .then(r => r.json())
      .then(d => {
        setRelated(d.nodes || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [entity.id]);

  const severityColor = (severity?: string) => {
    const map: Record<string, string> = { CRITICAL: 'var(--color-error)', HIGH: 'var(--color-bid)', MEDIUM: 'var(--color-warning)', LOW: 'var(--color-info)' };
    return map[severity || ''] || 'var(--text-muted)';
  };

  const entityTypeLabel: Record<string, string> = {
    tactic: 'ATT&CK 战术', technique: 'ATT&CK 技术',
    cve: 'CVE 漏洞', compliance: '合规条款',
    knowledge_item: '知识条目',
  };

  return (
    <div
      className="rounded-[var(--radius-md)] p-3 text-xs"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-1.5 py-0.5 rounded"
                style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
            {entityTypeLabel[entity.entity_type] || entity.entity_type}
          </span>
          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{entity.name}</span>
        </div>
        <button
          onClick={onClose}
          className="text-[11px] px-2 py-0.5 rounded"
          style={{ color: 'var(--text-muted)', backgroundColor: 'var(--bg-hover)' }}
        >
          关闭
        </button>
      </div>

      {/* ID */}
      <div className="mb-1.5" style={{ color: 'var(--text-secondary)' }}>
        ID: <span className="font-mono">{entity.id}</span>
      </div>

      {/* Description */}
      {entity.description && (
        <div className="mb-1.5" style={{ color: 'var(--text-secondary)' }}>
          {entity.description}
        </div>
      )}

      {/* CVSS for CVE */}
      {entity.entity_type === 'cve' && entity.metadata?.cvss && (
        <div className="mb-1.5 flex items-center gap-2">
          <span style={{ color: 'var(--text-secondary)' }}>CVSS:</span>
          <span className="font-semibold" style={{ color: severityColor(entity.metadata?.severity) }}>
            {entity.metadata.cvss} ({entity.metadata.severity || 'N/A'})
          </span>
        </div>
      )}

      {/* External reference */}
      {entity.external_ref && (
        <div className="mb-2">
          <a
            href={entity.external_ref}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] underline"
            style={{ color: 'var(--color-ai)' }}
          >
            查看外部详情 →
          </a>
        </div>
      )}

      {/* Related entities */}
      {related.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>
            关联实体 ({related.length})
          </div>
          <div className="space-y-0.5">
            {related.map((r: any) => (
              <div key={r.id} className="flex items-center gap-1.5 text-[11px]"
                   style={{ color: 'var(--text-muted)' }}>
                <span className="truncate">{r.name}</span>
                <span className="shrink-0">({r.entity_type})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
