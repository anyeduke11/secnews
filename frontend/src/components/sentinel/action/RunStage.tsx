/**
 * 行动四段指挥台 · 第③段 Run (R-15)
 * 数据源: GET /api/v1/cases/{id}/aggregate → actions + runs (既有端点)
 * 只读呈现执行账本: outcome 显式 / 耗时 / 失败原因。
 * 未启动: 已批准 (approved) 且无运行记录 → 提供真实「发起运行」(POST /api/v1/actions/{id}/start, 既有端点)。
 */
import type { Action, Run } from '../../../domain/v1_0';
import {
  STAGE,
  STAGE_HEAD,
  STAGE_TITLE,
  STAGE_COUNT,
  STAGE_EMPTY,
  ITEM_ROW,
  TONE_OK,
  TONE_WARN,
  TONE_IDLE,
  TONE_ACCENT,
} from './stageStyles';

const ACTION_STATUS: Record<string, string> = {
  planned: '待批准',
  approved: '已批准',
  running: '运行中',
  succeeded: '已成功',
  failed: '已失败',
  cancelled: '已取消',
  rejected: '已拒绝',
};

function outcomeOf(status?: string): { label: string; color: string } {
  switch (status) {
    case 'succeeded':
      return { label: '成功', color: TONE_OK };
    case 'failed':
      return { label: '失败', color: TONE_WARN };
    case 'timed_out':
      return { label: '超时失败', color: TONE_WARN };
    case 'cancelled':
      return { label: '已取消', color: TONE_IDLE };
    case 'running':
      return { label: '进行中', color: TONE_ACCENT };
    case 'queued':
    case 'claimed':
      return { label: '排队中', color: TONE_IDLE };
    default:
      return { label: '未知', color: TONE_IDLE };
  }
}

interface RunStageProps {
  caseId: string | null;
  actions: Action[];
  runs: Run[];
  loading: boolean;
  error: string | null;
  starting: string | null;
  onStart: (action: Action) => void;
}

export function RunStage({ caseId, actions, runs, loading, error, starting, onStart }: RunStageProps) {
  return (
    <section data-stage="run" style={STAGE} aria-label="Run 执行段">
      <div style={STAGE_HEAD}>
        <span style={STAGE_TITLE}>③ Run · 执行账本</span>
        <span style={STAGE_COUNT}>
          {actions.length} 动作 · {runs.length} 运行
        </span>
      </div>

      {!caseId && <p style={STAGE_EMPTY}>先在上方选择案件，Run 账本随案件加载。</p>}
      {caseId && loading && <p style={STAGE_EMPTY}>加载执行账本…</p>}
      {caseId && !loading && error && (
        <p style={{ ...STAGE_EMPTY, color: 'var(--sn-amber)' }}>执行账本不可用：{error}</p>
      )}
      {caseId && !loading && !error && actions.length === 0 && (
        <p style={STAGE_EMPTY}>该案件暂无 Action（需先发布 Claim 生成执行动作）。</p>
      )}

      {caseId && !loading && !error && actions.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 8 }}>
          {actions.map(a => {
            const myRuns = runs.filter(r => r.action_id === a.id);
            return (
              <li key={a.id} data-testid="run-stage-action" style={ITEM_ROW}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ color: 'var(--sn-ink)', fontSize: 12, fontWeight: 600 }}>{a.title}</span>
                  <span style={{ fontSize: 11, color: 'var(--sn-ink-3)' }}>
                    {ACTION_STATUS[a.status ?? ''] ?? a.status ?? '未知'}
                  </span>
                </div>

                {myRuns.length === 0 && a.status === 'approved' && (
                  <button
                    type="button"
                    data-testid="run-stage-start"
                    disabled={starting === a.id}
                    onClick={() => onStart(a)}
                    style={{
                      marginTop: 6,
                      fontSize: 11,
                      cursor: starting === a.id ? 'progress' : 'pointer',
                      color: 'var(--sn-bg)',
                      background: 'var(--sn-accent)',
                      border: 'none',
                      borderRadius: 'var(--radius-sm, 6px)',
                      padding: '3px 10px',
                    }}
                  >
                    {starting === a.id ? '发起中…' : '发起运行'}
                  </button>
                )}
                {myRuns.length === 0 && a.status !== 'approved' && (
                  <div style={{ marginTop: 4, fontSize: 11, color: 'var(--sn-ink-3)' }}>
                    尚无运行记录（待批准后可执行）
                  </div>
                )}

                {myRuns.map(r => {
                  const o = outcomeOf(r.status);
                  return (
                    <div
                      key={r.id}
                      data-testid="run-stage-run"
                      style={{ marginTop: 6, fontSize: 11, display: 'flex', flexWrap: 'wrap', gap: '4px 10px' }}
                    >
                      <span style={{ color: o.color, fontWeight: 600 }}>{o.label}</span>
                      {typeof r.duration_ms === 'number' && (
                        <span style={{ color: 'var(--sn-ink-3)' }}>耗时 {Math.round(r.duration_ms)} ms</span>
                      )}
                      {r.error && <span style={{ color: 'var(--sn-ink-3)' }}>失败原因 {r.error}</span>}
                      {r.result_excerpt && (
                        <span style={{ color: 'var(--sn-ink-3)' }}>· {r.result_excerpt}</span>
                      )}
                    </div>
                  );
                })}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}