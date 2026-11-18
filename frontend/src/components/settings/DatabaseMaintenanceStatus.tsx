/**
 * settings/DatabaseMaintenance — 只读状态展示区 (4 格状态卡 + 大表 Top 10)。
 *
 * 拆分自 DatabaseMaintenance.tsx, 纯展示子组件, 不含请求与状态.
 */

type DbHealth = { size_mb?: number; fragmentation_pct?: number; journal_mode?: string } | null;
type Tone = 'mint' | 'amber' | 'red';

type StatusCardsProps = {
  dbHealth: DbHealth;
  sizeMB: number;
  sizeTone: Tone;
  fragTone: Tone;
  cleanableLogs: number;
  dirtyTone: Tone;
  dupCount: number;
  kiDupCount: number;
  invalidUrls: number;
};

/** 状态卡 — 4 格 */
export function StatusCards({
  dbHealth,
  sizeMB,
  sizeTone,
  fragTone,
  cleanableLogs,
  dirtyTone,
  dupCount,
  kiDupCount,
  invalidUrls,
}: StatusCardsProps) {
  return (
    <div className="st-cellgrid">
      <div className="st-cell">
        <span className="st-cellk">SIZE</span>
        <span className={`st-cellv ${sizeTone === 'mint' ? '' : sizeTone}`}>
          {sizeMB ? `${sizeMB.toFixed(1)} MB` : '—'}
        </span>
        <span className="st-cellnote">{dbHealth?.journal_mode || 'journal'} · {sizeTone === 'red' ? '过大' : sizeTone === 'amber' ? '关注' : '健康'}</span>
      </div>
      <div className="st-cell">
        <span className="st-cellk">FRAGMENTATION</span>
        <span className={`st-cellv ${fragTone === 'mint' ? '' : fragTone}`}>
          {dbHealth?.fragmentation_pct != null ? `${dbHealth.fragmentation_pct.toFixed(1)}%` : '—'}
        </span>
        <span className="st-cellnote">{fragTone === 'red' ? '建议 VACUUM' : fragTone === 'amber' ? '可压缩' : 'OK'}</span>
      </div>
      <div className="st-cell">
        <span className="st-cellk">CLEANABLE LOGS</span>
        <span className={`st-cellv ${cleanableLogs > 1000 ? 'red' : cleanableLogs > 100 ? 'amber' : ''}`}>
          {cleanableLogs.toLocaleString()}
        </span>
        <span className="st-cellnote">超过 7 天可清理</span>
      </div>
      <div className="st-cell">
        <span className="st-cellk">DIRTY DATA</span>
        <span className={`st-cellv ${dirtyTone === 'mint' ? '' : dirtyTone}`}>
          {dupCount + kiDupCount + invalidUrls || '—'}
        </span>
        <span className="st-cellnote">
          {dupCount} 重复URL + {kiDupCount} 重复标题 + {invalidUrls} 无效URL
        </span>
      </div>
    </div>
  );
}

type TopTablesProps = { topTables: any[] };

/** 大表 Top 10 */
export function TopTables({ topTables }: TopTablesProps) {
  if (!(topTables.length > 0)) return null;
  return (
    <div className="st-section">
      <div className="st-section-body" style={{ padding: 0 }}>
        <table className="st-table">
          <thead>
            <tr>
              <th>表名</th>
              <th style={{ width: 120, textAlign: 'right' }}>行数</th>
            </tr>
          </thead>
          <tbody>
            {topTables.map(t => (
              <tr key={t.table}>
                <td style={{ fontFamily: 'var(--sn-mono)', fontSize: 12 }}>{t.table}</td>
                <td style={{ fontFamily: 'var(--sn-mono)', textAlign: 'right', color: 'var(--sn-ink-2)' }}>
                  {t.rows.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}