/**
 * RunActionRow — 第③段 Run 的单个 Action 行 (含其下全部 run 账本行与回执按钮) (B5 从 RunStage 抽出)
 *
 * 纯展示 + props 回调: 「哪一行的表单/计划面板展开」仍由父层 RunStage 单值 state 持有
 * (全局同时只开一个), 本文件只负责渲染与回调转发。data-testid 与拆分前逐字一致。
 */
import type { Action, Run } from '../../../domain/v1_0';
import { ITEM_ROW } from './stageStyles';
import {
  ACTION_STATUS, btnGhostStyle, btnStyle, outcomeOf, TERMINAL_RUN_STATUS,
  type FinishRunBody,
} from './runStageModel';
import { PlanPanel } from './PlanPanel';
import { RunFinishForm } from './RunFinishForm';

interface RunActionRowProps {
  action: Action;
  /** 当前案件的全部 run, 行内按 action_id 归属过滤 */
  runs: Run[];
  starting: string | null;
  onStart: (action: Action) => void;
  /** R-1 人工回执 busy 标识: run id 或 `act:{action_id}` */
  receiptBusy: string | null;
  onClaimRun?: (run: Run) => void;
  onStartRun?: (run: Run) => void;
  onFinishRun?: (run: Run, body: FinishRunBody) => void;
  onCancelRun?: (run: Run) => void;
  onFinishAction?: (action: Action) => void;
  /** 展开「登记结果」表单的 run id (null = 收起) */
  finishFormRun: string | null;
  onOpenFinishForm: (runId: string) => void;
  onCloseFinishForm: () => void;
  /** 展开执行计划面板的 run id (null = 收起) */
  planPanelRun: string | null;
  onTogglePlanPanel: (runId: string) => void;
  /** R-2: plan 变更后刷新聚合 (父层 loadAggregate) */
  onRefresh?: () => void;
}

export function RunActionRow({
  action: a,
  runs,
  starting,
  onStart,
  receiptBusy,
  onClaimRun,
  onStartRun,
  onFinishRun,
  onCancelRun,
  onFinishAction,
  finishFormRun,
  onOpenFinishForm,
  onCloseFinishForm,
  planPanelRun,
  onTogglePlanPanel,
  onRefresh,
}: RunActionRowProps) {
  const myRuns = runs.filter(r => r.action_id === a.id);
  const allRunsTerminal =
    myRuns.length > 0 && myRuns.every(r => TERMINAL_RUN_STATUS.has(r.status ?? ''));
  const canCloseAction =
    a.status === 'running' && allRunsTerminal && !!onFinishAction;

  return (
    <li data-testid="run-stage-action" style={ITEM_ROW}>
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
                onClick={() => onOpenFinishForm(r.id)}
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
            {(status === 'queued' || status === 'claimed') && (
              <button
                type="button" data-testid="run-plan-open"
                style={btnGhostStyle}
                onClick={() => onTogglePlanPanel(r.id)}
              >
                {planPanelRun === r.id ? '收起计划' : '执行计划'}
              </button>
            )}

            {status === 'running' && finishFormRun === r.id && onFinishRun && (
              <RunFinishForm
                run={r}
                busy={busy}
                onFinish={onFinishRun}
                onClose={onCloseFinishForm}
              />
            )}
            {planPanelRun === r.id && (status === 'queued' || status === 'claimed') && (
              <PlanPanel runId={r.id} actionId={r.action_id} onRefresh={onRefresh} />
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
}
