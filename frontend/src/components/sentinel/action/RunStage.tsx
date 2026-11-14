/**
 * 行动四段指挥台 · 第③段 Run (R-15 + v0.8.9 R-1)
 * 数据源: GET /api/v1/cases/{id}/aggregate → actions + runs (既有端点)
 * 执行账本呈现: outcome 显式 / 耗时 / 失败原因。
 * 发起运行: 已批准 (approved) 且无运行记录 → POST /api/v1/actions/{id}/start (既有端点)。
 * 人工回执 (v0.8.9 R-1, D4 裁决: direct 执行体 = 人):
 *   queued → [认领/取消] · claimed → [开工/取消] · running → [登记结果(outcome+error)/取消]
 *   终态 action (running) 且全部 run 终态 → [收口 Action] (C1-2 finish 端点)。
 */
import { useState } from 'react';
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

const TERMINAL_RUN_STATUS = new Set(['succeeded', 'failed', 'cancelled', 'timed_out']);

const OUTCOME_OPTIONS: { value: string; label: string }[] = [
  { value: 'done', label: '成功 (done)' },
  { value: 'failed', label: '失败 (failed)' },
  { value: 'cancelled', label: '取消 (cancelled)' },
  { value: 'timeout', label: '超时 (timeout)' },
  { value: 'needs_human', label: '需人工 (needs_human)' },
];

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

const btnStyle: React.CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-bg)',
  background: 'var(--sn-accent)',
  border: 'none',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};

const btnGhostStyle: React.CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-ink-2)',
  background: 'transparent',
  border: '1px solid var(--border-color, rgba(128,128,128,.4))',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};

interface RunStageProps {
  caseId: string | null;
  actions: Action[];
  runs: Run[];
  loading: boolean;
  error: string | null;
  starting: string | null;
  onStart: (action: Action) => void;
  /** R-1 人工回执 (v0.8.9): busy 标识 = run id / `act:{action_id}`；回调失败由父层 fail-loud 呈现 */
  receiptBusy?: string | null;
  onClaimRun?: (run: Run) => void;
  onStartRun?: (run: Run) => void;
  onFinishRun?: (run: Run, body: { outcome: string; error?: string | null; result_excerpt?: string | null }) => void;
  onCancelRun?: (run: Run) => void;
  onFinishAction?: (action: Action) => void;
}

export function RunStage({
  caseId,
  actions,
  runs,
  loading,
  error,
  starting,
  onStart,
  receiptBusy = null,
  onClaimRun,
  onStartRun,
  onFinishRun,
  onCancelRun,
  onFinishAction,
}: RunStageProps) {
  // 登记结果表单: 仅 running 的 run 可展开 (runId 为 null = 收起)
  const [finishFormRun, setFinishFormRun] = useState<string | null>(null);
  const [finishOutcome, setFinishOutcome] = useState('done');
  const [finishError, setFinishError] = useState('');
  const needsError = finishOutcome === 'failed' || finishOutcome === 'timeout' || finishOutcome === 'needs_human';

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
            const allRunsTerminal =
              myRuns.length > 0 && myRuns.every(r => TERMINAL_RUN_STATUS.has(r.status ?? ''));
            const canCloseAction =
              a.status === 'running' && allRunsTerminal && !!onFinishAction;
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
                  const busy = receiptBusy === r.id;
                  const status = r.status ?? '';
                  return (
                    <div
                      key={r.id}
                      data-testid="run-stage-run"
                      style={{ marginTop: 6, fontSize: 11, display: 'flex', flexWrap: 'wrap', gap: '4px 10px', alignItems: 'center' }}
                    >
                      <span style={{ color: o.color, fontWeight: 600 }}>{o.label}</span>
                      {typeof r.duration_ms === 'number' && (
                        <span style={{ color: 'var(--sn-ink-3)' }}>耗时 {Math.round(r.duration_ms)} ms</span>
                      )}
                      {r.error && <span style={{ color: 'var(--sn-ink-3)' }}>失败原因 {r.error}</span>}
                      {r.result_excerpt && (
                        <span style={{ color: 'var(--sn-ink-3)' }}>· {r.result_excerpt}</span>
                      )}

                      {status === 'queued' && onClaimRun && (
                        <button
                          type="button" data-testid="run-claim" disabled={busy}
                          style={btnStyle}
                          onClick={() => onClaimRun(r)}
                        >
                          {busy ? '认领中…' : '认领'}
                        </button>
                      )}
                      {status === 'claimed' && onStartRun && (
                        <button
                          type="button" data-testid="run-start" disabled={busy}
                          style={btnStyle}
                          onClick={() => onStartRun(r)}
                        >
                          {busy ? '开工中…' : '开工'}
                        </button>
                      )}
                      {status === 'running' && onFinishRun && finishFormRun !== r.id && (
                        <button
                          type="button" data-testid="run-finish-open" disabled={busy}
                          style={btnStyle}
                          onClick={() => { setFinishFormRun(r.id); setFinishOutcome('done'); setFinishError(''); }}
                        >
                          登记结果
                        </button>
                      )}
                      {(status === 'queued' || status === 'claimed' || status === 'running') && onCancelRun && (
                        <button
                          type="button" data-testid="run-cancel" disabled={busy}
                          style={btnGhostStyle}
                          onClick={() => onCancelRun(r)}
                        >
                          取消
                        </button>
                      )}

                      {status === 'running' && finishFormRun === r.id && onFinishRun && (
                        <div
                          data-testid="run-finish-form"
                          style={{ width: '100%', display: 'grid', gap: 4, marginTop: 4, padding: 6, borderRadius: 6, background: 'var(--bg-hover, rgba(128,128,128,.08))' }}
                        >
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <label style={{ color: 'var(--sn-ink-3)' }}>结果</label>
                            <select
                              data-testid="run-finish-outcome"
                              value={finishOutcome}
                              onChange={e => setFinishOutcome(e.target.value)}
                              style={{ fontSize: 11 }}
                            >
                              {OUTCOME_OPTIONS.map(o => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </select>
                          </div>
                          {needsError && (
                            <input
                              data-testid="run-finish-error"
                              placeholder="原因码 / 说明（失败真实性：必填）"
                              value={finishError}
                              onChange={e => setFinishError(e.target.value)}
                              style={{ fontSize: 11, padding: '3px 6px' }}
                            />
                          )}
                          {finishOutcome === 'done' && (
                            <div style={{ color: 'var(--sn-ink-3)', fontSize: 10 }}>
                              done 须先在第④段登记产物（RA-9：禁止成功但无产物）
                            </div>
                          )}
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button
                              type="button" data-testid="run-finish-submit"
                              disabled={busy || (needsError && !finishError.trim())}
                              style={btnStyle}
                              onClick={() => {
                                onFinishRun(r, {
                                  outcome: finishOutcome,
                                  error: finishError.trim() || null,
                                  result_excerpt: null,
                                });
                                setFinishFormRun(null);
                              }}
                            >
                              {busy ? '登记中…' : '提交登记'}
                            </button>
                            <button type="button" style={btnGhostStyle} onClick={() => setFinishFormRun(null)}>
                              取消
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {canCloseAction && (
                  <button
                    type="button"
                    data-testid="action-finish"
                    disabled={receiptBusy === `act:${a.id}`}
                    style={{ ...btnStyle, marginTop: 6 }}
                    onClick={() => onFinishAction?.(a)}
                  >
                    {receiptBusy === `act:${a.id}` ? '收口中…' : '收口 Action'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
