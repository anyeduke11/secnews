/**
 * InfoFilterPreview — InfoFilterCard 的「实时预览」区块
 * (从 InfoFilterCard.tsx 机械拆分, JSX/className/文案零变更, 状态仍由父组件持有)
 */
import type { PreviewResult } from '../../../api/secnews';
import type { TFn } from './infoFilter.types';
import { StatusBadge } from '../../../primitives/StatusBadge';

interface InfoFilterPreviewProps {
  t: TFn;
  category: string;
  sourceName: string;
  result: PreviewResult | null;
  onCategoryChange: (v: string) => void;
  onSourceNameChange: (v: string) => void;
  onRun: () => void;
}

export function InfoFilterPreview({
  t,
  category,
  sourceName,
  result,
  onCategoryChange,
  onSourceNameChange,
  onRun,
}: InfoFilterPreviewProps) {
  return (
    <section className="st-section" aria-label={t('info_filter.preview')}>
      <h3>{t('info_filter.preview')}</h3>
      <p className="st-section-desc">{t('info_filter.preview_desc')}</p>
      <div className="st-section-body">
        <div className="st-cellgrid">
          <label className="st-cell">
            <span className="st-cellk">{t('info_filter.preview_category')}</span>
            <input
              className="st-input"
              type="text"
              value={category}
              onChange={e => onCategoryChange(e.target.value)}
              aria-label={t('info_filter.preview_category')}
            />
          </label>
          <label className="st-cell">
            <span className="st-cellk">{t('info_filter.preview_source')}</span>
            <input
              className="st-input"
              type="text"
              value={sourceName}
              onChange={e => onSourceNameChange(e.target.value)}
              aria-label={t('info_filter.preview_source')}
            />
          </label>
        </div>
        <button
          type="button"
          className="st-btn primary"
          onClick={onRun}
          disabled={!sourceName.trim()}
          style={{ marginTop: 10 }}
        >
          {t('info_filter.preview_run')}
        </button>
        {result && (
          <div style={{ marginTop: 12 }}>
            <StatusBadge tone={
              result.verdict === 'deny' ? 'risk'
                : result.verdict === 'allow' ? 'ok' : 'neutral'
            }>
              {t('info_filter.verdict')}: {result.verdict}
            </StatusBadge>
            {result.matched_rule && (
              <span style={{
                marginLeft: 8,
                fontFamily: 'var(--sn-mono)',
                fontSize: 'var(--sn-fs-mute)',
                color: 'var(--sn-ink-3)',
              }}>
                {result.matched_rule.rule_type}/
                {result.matched_rule.match_kind}/
                {result.matched_rule.match_value}
              </span>
            )}
          </div>
        )}
      </div>
    </section>
  );
}