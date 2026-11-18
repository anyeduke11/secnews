/**
 * InfoFilterRuleList — InfoFilterCard 的「规则列表」区块
 * (从 InfoFilterCard.tsx 机械拆分, JSX/className/文案零变更, 状态仍由父组件持有)
 */
import type { FilterRule } from '../../../api/secnews';
import type { TFn } from './infoFilter.types';

interface InfoFilterRuleListProps {
  t: TFn;
  loading: boolean;
  rules: FilterRule[];
  onToggle: (rule: FilterRule) => void;
  onDelete: (id: number) => void;
}

export function InfoFilterRuleList({
  t,
  loading,
  rules,
  onToggle,
  onDelete,
}: InfoFilterRuleListProps) {
  return (
    <section className="st-section" aria-label={t('info_filter.rules_list')}>
      <h3>{t('info_filter.rules_list')}</h3>
      <div className="st-section-body">
        {!loading && rules.length === 0 && (
          <div className="st-info">{t('info_filter.no_rules')}</div>
        )}
        {rules.map(r => (
          <div key={r.id} className="st-card" style={{ marginBottom: 8 }}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`st-chip ${r.rule_type === 'deny' ? 'bad' : 'ok'}`}>
                {r.rule_type}
              </span>
              <span className="st-chip">{r.match_kind}</span>
              <code style={{ fontFamily: 'var(--sn-mono)', color: 'var(--sn-ink)' }}>
                {r.match_value}
              </code>
              {r.note && (
                <span style={{
                  fontFamily: 'var(--sn-mono)',
                  fontSize: 'var(--sn-fs-mute)',
                  color: 'var(--sn-ink-3)',
                }}>
                  — {r.note}
                </span>
              )}
              <div className="ml-auto flex gap-1">
                <button
                  type="button"
                  className="st-btn ghost xs"
                  onClick={() => onToggle(r)}
                >
                  {r.enabled ? t('info_filter.disable') : t('info_filter.enable')}
                </button>
                <button
                  type="button"
                  className="st-btn ghost xs"
                  onClick={() => onDelete(r.id)}
                >
                  {t('info_filter.delete')}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}