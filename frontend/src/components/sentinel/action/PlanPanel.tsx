/**
 * 执行计划面板 (v0.8.9 P3 C3-4 · L1 计划层)
 *
 * 不变量来源 backend/services/execution_plan/service.py:
 *  - 默认拒绝: 未 approved 的 plan 不被任何执行体消费;
 *  - approved 冻结 immutable — 面板不再提供改动入口, 仅呈现 boundary_hash;
 *  - 404 = 该 run 尚无草稿 (合法空态), 不是错误; 其余失败显式呈现 (fail-loud)。
 */
import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../lib/api';
import {
  approveRunPlan,
  generateRunPlan,
  getRunPlan,
  rejectRunPlan,
  submitRunPlan,
  type ExecutionPlanEnvelope,
} from '../../../api/v1';
import { TONE_ACCENT, TONE_IDLE, TONE_OK, TONE_WARN } from './stageStyles';

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿 · 待审批',
  approved: '已批准 · 已冻结',
  rejected: '已驳回',
};

const STATUS_COLOR: Record<string, string> = {
  draft: TONE_ACCENT,
  approved: TONE_OK,
  rejected: TONE_WARN,
};

const PANEL: React.CSSProperties = {
  width: '100%',
  marginTop: 6,
  padding: 8,
  borderRadius: 6,
  background: 'var(--bg-hover, rgba(128,128,128,.08))',
  fontSize: 11,
  display: 'grid',
  gap: 6,
};

const MUTED: React.CSSProperties = { color: 'var(--sn-ink-3)' };

const BTN: React.CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-bg)',
  background: 'var(--sn-accent)',
  border: 'none',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};

const BTN_GHOST: React.CSSProperties = {
  fontSize: 11,
  cursor: 'pointer',
  color: 'var(--sn-ink-2)',
  background: 'transparent',
  border: '1px solid var(--border-color, rgba(128,128,128,.4))',
  borderRadius: 'var(--radius-sm, 6px)',
  padding: '3px 10px',
};

export interface PlanPanelProps {
  runId: string;
  actionId: string;
  /** 审批后刷新父层聚合 (run 的 boundary_hash / executor 随之变化) */
  onRefresh?: () => void;
}

export function PlanPanel({ runId, actionId, onRefresh }: PlanPanelProps) {
  const [env, setEnv] = useState<ExecutionPlanEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualJson, setManualJson] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    try {
      const d = await getRunPlan(runId);
      setEnv(d.item);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setEnv(null); // 无草稿 = 合法空态
      } else {
        setError((e as Error).message);
        setErrorStatus(e instanceof ApiError ? e.status : null);
      }
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const op = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setErrorStatus(null);
    try {
      await fn();
      setManualOpen(false);
      setManualJson('');
      setRejectOpen(false);
      setRejectReason('');
      await load();
      onRefresh?.();
    } catch (e) {
      setError((e as Error).message);
      setErrorStatus(e instanceof ApiError ? e.status : null);
    } finally {
      setBusy(false);
    }
  };

  const submitManual = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(manualJson);
    } catch {
      setError('JSON 非法, 未发送请求');
      return;
    }
    void op(() =>
      submitRunPlan(runId, { plan: parsed as Record<string, unknown>, source: 'manual' })
    );
  };

  const status = env?.status;
  const plan = env?.plan;
  // 可起草 = 无草稿或被驳回 (approved 冻结; draft 待审批)
  const canDraft = !env || status === 'rejected';

  return (
    <div data-testid="run-plan-panel" style={PANEL}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontWeight: 600, color: 'var(--sn-ink)' }}>
          执行计划 (L1: 未批准不执行)
        </span>
        <span data-testid="plan-status" style={{ color: STATUS_COLOR[status ?? ''] ?? TONE_IDLE }}>
          {STATUS_LABEL[status ?? ''] ?? '无计划'}
        </span>
      </div>

      {loading && <div style={MUTED}>加载计划…</div>}
      {error && (
        <div data-testid="plan-error" style={{ color: 'var(--sn-amber)' }}>
          计划操作失败：{error}
          {errorStatus === 503 && '（AI 起草不可用，可改用手写 JSON）'}
        </div>
      )}

      {!loading && !error && canDraft && (
        <div style={{ display: 'grid', gap: 6 }}>
          <div style={MUTED}>
            {status === 'rejected'
              ? '计划已驳回。重新起草并批准后执行体才会消费。'
              : '尚无执行计划。起草并经批准后执行体才会消费。'}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              data-testid="plan-generate"
              disabled={busy}
              style={BTN}
              onClick={() => void op(() => generateRunPlan(runId, { action_id: actionId }))}
            >
              {busy ? '起草中…' : 'AI 起草'}
            </button>
            <button
              type="button"
              data-testid="plan-manual-open"
              disabled={busy}
              style={BTN_GHOST}
              onClick={() => setManualOpen(v => !v)}
            >
              手写 JSON
            </button>
          </div>
          {manualOpen && (
            <div style={{ display: 'grid', gap: 4 }}>
              <textarea
                data-testid="plan-manual-json"
                value={manualJson}
                onChange={e => setManualJson(e.target.value)}
                placeholder="粘贴 ExecutionPlan JSON（commands / writable_paths / network / output_artifact …）"
                style={{ minHeight: 72, fontSize: 11, fontFamily: 'monospace', padding: 6 }}
              />
              <div>
                <button
                  type="button"
                  data-testid="plan-manual-submit"
                  disabled={busy || !manualJson.trim()}
                  style={BTN}
                  onClick={submitManual}
                >
                  提交草稿
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && !error && plan && (
        <div style={{ display: 'grid', gap: 4 }}>
          <div style={MUTED}>
            来源 {env?.source} · 提交人 {env?.submitted_by}
            {env?.approved_by && ` · 批准人 ${env.approved_by}`}
          </div>
          <ol data-testid="plan-commands" style={{ margin: 0, paddingLeft: 16 }}>
            {plan.commands.map((argv, i) => (
              <li key={i}>
                <code>{argv.join(' ')}</code>
              </li>
            ))}
          </ol>
          <div style={MUTED} data-testid="plan-boundary">
            写 {plan.writable_paths.join(', ') || '—'} · 读{' '}
            {plan.readable_paths.join(', ') || '—'} · 网络 {plan.network.join(', ') || '全禁'} ·
            产物 {plan.output_artifact.title}
          </div>
          {status === 'approved' && env?.boundary_hash && (
            <div style={MUTED} data-testid="plan-frozen">
              已冻结：boundary_hash {env.boundary_hash.slice(0, 16)}…（改动需新 run attempt）
            </div>
          )}
          {status === 'rejected' && env?.reject_reason && (
            <div style={{ color: 'var(--sn-amber)' }}>驳回原因：{env.reject_reason}</div>
          )}

          {status === 'draft' && (
            <div style={{ display: 'grid', gap: 4 }}>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  type="button"
                  data-testid="plan-approve"
                  disabled={busy}
                  style={BTN}
                  onClick={() => void op(() => approveRunPlan(runId))}
                >
                  {busy ? '提交中…' : '批准计划'}
                </button>
                <button
                  type="button"
                  data-testid="plan-reject-open"
                  disabled={busy}
                  style={BTN_GHOST}
                  onClick={() => setRejectOpen(v => !v)}
                >
                  驳回
                </button>
              </div>
              {rejectOpen && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    data-testid="plan-reject-reason"
                    placeholder="驳回原因（必填, ≤200 字）"
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    style={{ flex: 1, fontSize: 11, padding: '3px 6px' }}
                  />
                  <button
                    type="button"
                    data-testid="plan-reject-submit"
                    disabled={busy || !rejectReason.trim()}
                    style={BTN_GHOST}
                    onClick={() =>
                      void op(() =>
                        rejectRunPlan(runId, { reason: rejectReason.trim().slice(0, 200) })
                      )
                    }
                  >
                    确认驳回
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}