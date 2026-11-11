/**
 * 行动四段指挥台 · 第①段 Case (R-15)
 * 数据源: GET /api/v1/cases (既有端点, 不新增 router)
 * 职责: 列出活跃案件并承载「选中」—— selectedCaseId 由容器持有, 本段只回调。
 */
import type { Case } from '../../../domain/v1_0';
import { STAGE, STAGE_HEAD, STAGE_TITLE, STAGE_COUNT, STAGE_EMPTY } from './stageStyles';

const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  in_progress: '进行中',
  blocked: '受阻',
  closed: '已关闭',
  archived: '归档',
};

const PRIORITY_LABEL: Record<string, string> = { p0: 'P0', p1: 'P1', p2: 'P2', p3: 'P3' };

interface CaseStageProps {
  cases: Case[];
  selectedCaseId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
}

export function CaseStage({ cases, selectedCaseId, onSelect, loading, error }: CaseStageProps) {
  return (
    <section data-stage="case" style={STAGE} aria-label="Case 案件段">
      <div style={STAGE_HEAD}>
        <span style={STAGE_TITLE}>① Case · 待处置案件</span>
        <span style={STAGE_COUNT}>{cases.length} 条</span>
      </div>

      {loading && <p style={STAGE_EMPTY}>加载案件…</p>}
      {!loading && error && (
        <p style={{ ...STAGE_EMPTY, color: 'var(--sn-amber)' }}>案件不可用：{error}</p>
      )}
      {!loading && !error && cases.length === 0 && (
        <p style={STAGE_EMPTY}>无活跃案件 — 从资讯或知识条目立项后再回到这里。</p>
      )}

      {!loading && !error && cases.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {cases.map(c => {
            const active = c.id === selectedCaseId;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  data-testid="case-stage-item"
                  aria-pressed={active}
                  onClick={() => onSelect(c.id)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    cursor: 'pointer',
                    border: `1px solid ${active ? 'var(--sn-accent)' : 'var(--sn-line)'}`,
                    background: active ? 'var(--sn-bg-hover)' : 'var(--sn-bg-panel)',
                    borderRadius: 'var(--radius-md, 8px)',
                    padding: '8px 10px',
                    color: 'var(--sn-ink)',
                  }}
                >
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{c.title || '(无标题)'}</span>
                  <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--sn-ink-3)' }}>
                    {STATUS_LABEL[c.status ?? ''] ?? c.status ?? '未知'}
                    {c.priority ? ` · ${PRIORITY_LABEL[c.priority] ?? c.priority}` : ''}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}