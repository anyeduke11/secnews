/**
 * 行动四段指挥台 · 第②段 Claim (R-15)
 * 数据源: GET /api/v1/cases/{id}/aggregate → judgments (既有端点)
 * 只读呈现主张: claim_type / 置信 / 证据条数 / 状态。
 */
import type { Judgment } from '../../../domain/v1_0';
import { STAGE, STAGE_HEAD, STAGE_TITLE, STAGE_COUNT, STAGE_EMPTY, ITEM_ROW } from './stageStyles';

const CLAIM_TYPE: Record<string, string> = {
  finding: '发现',
  assessment: '评估',
  recommendation: '建议',
  warning: '预警',
  hypothesis: '假设',
};

const CONFIDENCE: Record<string, string> = { low: '低', medium: '中', high: '高', proved: '已证' };

interface ClaimStageProps {
  caseId: string | null;
  items: Judgment[];
  loading: boolean;
  error: string | null;
}

export function ClaimStage({ caseId, items, loading, error }: ClaimStageProps) {
  return (
    <section data-stage="claim" style={STAGE} aria-label="Claim 主张段">
      <div style={STAGE_HEAD}>
        <span style={STAGE_TITLE}>② Claim · 主张与证据</span>
        <span style={STAGE_COUNT}>{items.length} 条</span>
      </div>

      {!caseId && <p style={STAGE_EMPTY}>先在上方选择案件，Claim 将随案件加载。</p>}
      {caseId && loading && <p style={STAGE_EMPTY}>加载主张…</p>}
      {caseId && !loading && error && (
        <p style={{ ...STAGE_EMPTY, color: 'var(--sn-amber)' }}>主张不可用：{error}</p>
      )}
      {caseId && !loading && !error && items.length === 0 && (
        <p style={STAGE_EMPTY}>该案件暂无 Claim（需先由案件发布主张）。</p>
      )}

      {caseId && !loading && !error && items.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {items.map(j => (
            <li key={j.id} data-testid="claim-stage-item" style={ITEM_ROW}>
              <div style={{ color: 'var(--sn-ink)', fontSize: 12, lineHeight: 1.5 }}>{j.claim}</div>
              <div style={{ marginTop: 4, fontSize: 11, color: 'var(--sn-ink-3)' }}>
                {CLAIM_TYPE[j.claim_type] ?? j.claim_type}
                {j.confidence ? ` · 置信 ${CONFIDENCE[j.confidence] ?? j.confidence}` : ''}
                {` · 证据 ${j.evidence_refs?.length ?? 0}`}
                {j.status ? ` · ${j.status}` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}