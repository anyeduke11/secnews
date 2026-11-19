/**
 * settings/DatabaseMaintenance — 重复数据详情列表 (HOTSPOTS 重复 URL / KNOWLEDGE 重复标题)。
 *
 * 拆分自 DatabaseMaintenance.tsx, 纯展示子组件, 不含请求与状态.
 */
import { StatusBadge } from '../../primitives/StatusBadge';

type Duplicates = { hotspots?: any[]; knowledge_items?: any[] } | null;

type DuplicateDetailProps = {
  duplicates: Duplicates;
  dupCount: number;
  kiDupCount: number;
};

export function DuplicateDetail({ duplicates, dupCount, kiDupCount }: DuplicateDetailProps) {
  if (!(dupCount > 0 || kiDupCount > 0)) return null;
  return (
    <div className="st-section">
      <h3 style={{ margin: '0 0 var(--sn-row) 0', fontSize: 'var(--sn-fs-h3)', color: 'var(--sn-ink)' }}>
        重复数据详情
      </h3>
      <div className="st-section-body" style={{ padding: 0 }}>
        {duplicates?.hotspots && duplicates.hotspots.length > 0 && (
          <div>
            <div style={{
              padding: '8px 12px',
              fontFamily: 'var(--sn-mono)',
              fontSize: 11,
              color: 'var(--sn-amber)',
              borderBottom: '1px solid var(--sn-line)',
              letterSpacing: '0.03em',
            }}>
              HOTSPOTS 重复 URL · {duplicates.hotspots.length} 组
            </div>
            <table className="st-table">
              <tbody>
                {duplicates.hotspots.slice(0, 5).map((d: any, i: number) => (
                  <tr key={i}>
                    <td style={{ width: 56 }}>
                      <StatusBadge tone="risk" dot>{d.count}×
                      </StatusBadge>
                    </td>
                    <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>
                      {d.url?.substring(0, 80)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {duplicates?.knowledge_items && duplicates.knowledge_items.length > 0 && (
          <div>
            <div style={{
              padding: '8px 12px',
              fontFamily: 'var(--sn-mono)',
              fontSize: 11,
              color: 'var(--sn-amber)',
              borderBottom: '1px solid var(--sn-line)',
              letterSpacing: '0.03em',
            }}>
              KNOWLEDGE 重复标题 · {duplicates.knowledge_items.length} 组
            </div>
            <table className="st-table">
              <tbody>
                {duplicates.knowledge_items.slice(0, 5).map((d: any, i: number) => (
                  <tr key={i}>
                    <td style={{ width: 56 }}>
                      <StatusBadge tone="risk" dot>{d.count}×
                      </StatusBadge>
                    </td>
                    <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>
                      {d.title}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}