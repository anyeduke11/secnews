import { useMemo, useState } from 'react';

import { useCompliance } from '../../hooks/useCompliance';
import { FrameworkFilter, type FrameworkOption } from './FrameworkFilter';

const FRAMEWORK_COLORS: Record<string, string> = {
  dengbao: '#4f46e5',
  gdpr: '#059669',
  iso27001: '#d97706',
};

interface ComplianceMatrixProps {
  frameworks: FrameworkOption[];
  eventTypes?: string[];
}

export function ComplianceMatrix({ frameworks, eventTypes = ['data_breach', 'unauthorized_access', 'malware', 'phishing', 'ddos', 'insider_threat', 'misconfiguration'] }: ComplianceMatrixProps) {
  const { fetchMatrix } = useCompliance();
  const [selectedFrameworks, setSelectedFrameworks] = useState<string[]>([]);
  const [expandedCell, setExpandedCell] = useState<{ row: number; col: number } | null>(null);
  const [data, setData] = useState<{ rows: { event_type: string; controls: { framework: string; control_id: string; name: string }[] }[]; columns: { framework: string; control_id: string; name: string }[] } | null>(null);

  // Load matrix on mount / when event types change
  if (!data && eventTypes.length) {
    fetchMatrix(eventTypes).then(setData).catch(() => {});
  }

  const visibleColumns = useMemo(() => {
    if (!data) return [];
    if (!selectedFrameworks.length) return data.columns;
    return data.columns.filter(c => selectedFrameworks.includes(c.framework));
  }, [data, selectedFrameworks]);

  if (!data) {
    return <div className="text-xs" style={{ color: 'var(--text-muted)' }}>加载合规矩阵…</div>;
  }

  return (
    <div className="space-y-4">
      <FrameworkFilter
        frameworks={frameworks}
        selected={selectedFrameworks}
        onChange={setSelectedFrameworks}
      />

      <div className="overflow-auto border rounded-lg" style={{ borderColor: 'var(--border-color)' }}>
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th className="sticky top-0 left-0 z-10 px-3 py-2 text-left border-b border-r"
                  style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-color)' }}>
                事件类型
              </th>
              {visibleColumns.map(col => (
                <th
                  key={`${col.framework}-${col.control_id}`}
                  className="sticky top-0 px-2 py-2 text-left border-b border-r min-w-[140px]"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    borderColor: 'var(--border-color)',
                    color: FRAMEWORK_COLORS[col.framework] || 'var(--text-primary)',
                  }}
                >
                  <div className="font-medium">{col.control_id}</div>
                  <div className="text-[10px] opacity-70 truncate max-w-[130px]">{col.name}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr key={row.event_type}>
                <td className="sticky left-0 z-10 px-3 py-2 border-b border-r font-medium"
                    style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-color)' }}>
                  {row.event_type}
                </td>
                {visibleColumns.map((col, colIndex) => {
                  const matched = row.controls.some(
                    c => c.framework === col.framework && c.control_id === col.control_id,
                  );
                  const isExpanded = expandedCell?.row === rowIndex && expandedCell?.col === colIndex;
                  return (
                    <td
                      key={`${col.framework}-${col.control_id}`}
                      className="px-2 py-2 text-center border-b border-r cursor-pointer transition-colors"
                      style={{
                        borderColor: 'var(--border-color)',
                        backgroundColor: matched ? 'var(--accent-soft)' : 'transparent',
                      }}
                      onClick={() => setExpandedCell(isExpanded ? null : { row: rowIndex, col: colIndex })}
                    >
                      {matched ? (
                        <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--accent)' }} />
                      ) : (
                        <span className="opacity-20">-</span>
                      )}
                      {isExpanded && (
                        <div className="mt-1 text-[10px] text-left p-1 rounded border"
                             style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
                          {row.controls
                            .filter(c => c.framework === col.framework && c.control_id === col.control_id)
                            .map((c, i) => (
                              <div key={i} className="truncate">{c.name}</div>
                            ))}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
