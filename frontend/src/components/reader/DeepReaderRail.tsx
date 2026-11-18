/**
 * DeepReaderRail — 批注侧栏展示区块 (三态: 定位 / 迁移 / 未定位)
 * (B5.6 拆分: 从 DeepReaderPage 抽出)
 *
 * DOM 结构 / 内联 style / aria 文案逐字保留; 定位与删除动作由容器传入。
 */
import { STATUS_COLOR, STATUS_LABEL, type ResolvedAnn } from './deepReaderModel';

export function DeepReaderRail({
  resolved,
  entityId,
  onLocate,
  onDelete,
}: {
  resolved: ResolvedAnn[];
  entityId: string;
  onLocate: (annId: string) => void;
  onDelete: (annId: string) => void;
}) {
  return (
    <aside className="ed-annrail" data-testid="ann-rail" aria-label="批注列表">
      <div className="ed-sechead">
        <span>批注 ({resolved.length})</span>
        <span className="ed-note">wiki_item / {entityId}</span>
      </div>
      {resolved.length === 0 ? (
        <p className="pgx-muted" style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          选中正文文字即可写下第一条批注。
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {resolved.map(r => (
            <li key={r.row.id} className="ed-card" style={{ padding: '10px 12px', gap: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <i aria-hidden="true" style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[r.status], flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--sn-mono)' }}>
                  {STATUS_LABEL[r.status]}
                </span>
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                  {r.status !== 'stale' && (
                    <button type="button" className="ed-btn" onClick={() => onLocate(r.row.id)}>定位</button>
                  )}
                  <button type="button" className="ed-btn" aria-label={`删除批注: ${r.row.content.slice(0, 12)}`} onClick={() => onDelete(r.row.id)}>删除</button>
                </span>
              </div>
              {r.row.quote && (
                <div style={{ fontSize: 12, color: 'var(--ink-2)', borderLeft: '2px solid var(--line-strong)', paddingLeft: 8 }}>
                  「{r.row.quote.slice(0, 80)}{r.row.quote.length > 80 ? '…' : ''}」
                </div>
              )}
              <div style={{ fontSize: 13, lineHeight: 1.6 }}>{r.row.content}</div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
