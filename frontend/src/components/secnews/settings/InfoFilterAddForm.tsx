/**
 * InfoFilterAddForm — InfoFilterCard 的「现状统计 + 新增规则」区块
 * (从 InfoFilterCard.tsx 机械拆分, JSX/className/文案零变更, 状态仍由父组件持有)
 */
import { MATCH_KINDS } from './infoFilter.types';
import type { MatchKind, RuleType, TFn } from './infoFilter.types';

interface InfoFilterAddFormProps {
  t: TFn;
  rulesCount: number;
  enabledCount: number;
  ruleType: RuleType;
  matchKind: MatchKind;
  matchValue: string;
  note: string;
  onRuleTypeChange: (v: RuleType) => void;
  onMatchKindChange: (v: MatchKind) => void;
  onMatchValueChange: (v: string) => void;
  onNoteChange: (v: string) => void;
  onCreate: () => void;
}

export function InfoFilterAddForm({
  t,
  rulesCount,
  enabledCount,
  ruleType,
  matchKind,
  matchValue,
  note,
  onRuleTypeChange,
  onMatchKindChange,
  onMatchValueChange,
  onNoteChange,
  onCreate,
}: InfoFilterAddFormProps) {
  return (
    <section className="st-section" aria-label={t('info_filter.title')}>
      <h3>{t('info_filter.title')}</h3>
      <p className="st-section-desc">{t('info_filter.desc')}</p>
      <div className="st-section-body">
        {/* 现状 */}
        <div className="st-cellgrid">
          <div className="st-cell">
            <span className="st-cellk">{t('info_filter.rules_count')}</span>
            <span className="st-cellv sm">{rulesCount}</span>
          </div>
          <div className="st-cell">
            <span className="st-cellk">{t('info_filter.enabled_count')}</span>
            <span className="st-cellv sm mint">
              {enabledCount}
            </span>
          </div>
        </div>

        {/* 新增规则 */}
        <div className="st-rule" />
        <h4 style={{
          fontFamily: 'var(--sn-mono)',
          fontSize: 'var(--sn-fs-h4)',
          color: 'var(--sn-ink)',
          margin: '12px 0 8px',
        }}>{t('info_filter.add_rule')}</h4>
        <div className="st-cellgrid">
          <label className="st-cell">
            <span className="st-cellk">{t('info_filter.rule_type')}</span>
            <select
              className="st-input"
              value={ruleType}
              onChange={e => onRuleTypeChange(e.target.value as RuleType)}
              aria-label={t('info_filter.rule_type')}
            >
              <option value="deny">deny</option>
              <option value="allow">allow</option>
            </select>
          </label>
          <label className="st-cell">
            <span className="st-cellk">{t('info_filter.match_kind')}</span>
            <select
              className="st-input"
              value={matchKind}
              onChange={e => onMatchKindChange(e.target.value as MatchKind)}
              aria-label={t('info_filter.match_kind')}
            >
              {MATCH_KINDS.map(k => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </label>
          <label className="st-cell" style={{ gridColumn: 'span 2' }}>
            <span className="st-cellk">{t('info_filter.match_value')}</span>
            <input
              className="st-input"
              type="text"
              value={matchValue}
              onChange={e => onMatchValueChange(e.target.value)}
              placeholder={t('info_filter.match_value_placeholder')}
              aria-label={t('info_filter.match_value')}
            />
          </label>
          <label className="st-cell" style={{ gridColumn: 'span 2' }}>
            <span className="st-cellk">{t('info_filter.note')}</span>
            <input
              className="st-input"
              type="text"
              value={note}
              onChange={e => onNoteChange(e.target.value)}
              placeholder={t('info_filter.note_placeholder')}
              aria-label={t('info_filter.note')}
            />
          </label>
        </div>
        <button
          type="button"
          className="st-btn primary"
          onClick={onCreate}
          disabled={!matchValue.trim()}
          style={{ marginTop: 10 }}
        >
          {t('info_filter.add')}
        </button>
      </div>
    </section>
  );
}