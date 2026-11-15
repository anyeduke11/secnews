/**
 * 行动四段执行指挥台容器 (R-15)
 *
 * 主干: Case → Claim → Run → Artifact, 四段共享同一 selectedCaseId。
 * 数据: 全部走既有 v1 端点 (listCases / getCaseAggregate / startAction), 不新增后端 router。
 *   - 选中案件后, 一次 getCaseAggregate 同时取回 judgments / actions / runs / artifacts。
 *   - 每段独立可视区块 ([data-stage]), 未选案件时各自渲染引导空态, 不退化为一张大表。
 *
 * 硬约束: 端点不可用时如实渲染「不可用」, 不造假数据 (PRD §4.15.7)。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  cancelRun,
  claimRun,
  finishAction,
  finishRun,
  getCaseAggregate,
  listCases,
  startAction,
  startRun,
  type CaseAggregate,
} from '../../../api/v1';
import type { Action, Case, CaseStatus, Run } from '../../../domain/v1_0';
import { CaseStage } from './CaseStage';
import { ClaimStage } from './ClaimStage';
import { RunStage } from './RunStage';
import { ArtifactStage } from './ArtifactStage';
import { STAGE_EMPTY } from './stageStyles';

const ACTIVE_CASES: CaseStatus[] = ['open', 'in_progress', 'blocked'];
const AGG_QUERY = { judgments_limit: 50, actions_limit: 50, runs_per_action: 5, artifacts_per_run: 10 };

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function ActionCommandConsole() {
  const [cases, setCases] = useState<Case[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [casesError, setCasesError] = useState<string | null>(null);

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [agg, setAgg] = useState<CaseAggregate | null>(null);
  const [aggLoading, setAggLoading] = useState(false);
  const [aggError, setAggError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setCasesLoading(true);
    listCases({ status: ACTIVE_CASES, limit: 50 })
      .then(r => {
        if (!alive) return;
        setCases(r?.items ?? []);
        setCasesError(null);
      })
      .catch(e => {
        if (alive) setCasesError(errText(e));
      })
      .finally(() => {
        if (alive) setCasesLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const loadAggregate = useCallback(async (caseId: string) => {
    setAggLoading(true);
    setAggError(null);
    try {
      const a = await getCaseAggregate(caseId, AGG_QUERY);
      setAgg(a);
    } catch (e) {
      setAgg(null);
      setAggError(errText(e));
    } finally {
      setAggLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      setAgg(null);
      setAggError(null);
      return;
    }
    void loadAggregate(selectedCaseId);
  }, [selectedCaseId, loadAggregate]);

  const handleStart = useCallback(
    async (action: Action) => {
      if (!selectedCaseId) return;
      setStarting(action.id);
      setAggError(null);
      try {
        await startAction(action.id, {
          expected_revision: action.revision ?? 1,
          idempotency_key: `ui-${action.id}-${Date.now()}`,
          protocol: 'dsh',
          trigger_source: 'user',
        });
        await loadAggregate(selectedCaseId);
      } catch (e) {
        setAggError(`发起运行失败：${errText(e)}`);
      } finally {
        setStarting(null);
      }
    },
    [selectedCaseId, loadAggregate],
  );

  // v0.8.9 R-1 人工回执 (D4: direct 执行体 = 人) — 四操作 + action 收口, 全部 fail-loud 后刷新聚合
  const [receiptBusy, setReceiptBusy] = useState<string | null>(null);
  const receipt = useCallback(
    async (key: string, op: () => Promise<unknown>) => {
      if (!selectedCaseId) return;
      setReceiptBusy(key);
      setAggError(null);
      try {
        await op();
        await loadAggregate(selectedCaseId);
      } catch (e) {
        setAggError(`人工回执失败：${errText(e)}`);
      } finally {
        setReceiptBusy(null);
      }
    },
    [selectedCaseId, loadAggregate],
  );
  const handleClaimRun = useCallback(
    (run: Run) => void receipt(run.id, () => claimRun(run.id)),
    [receipt],
  );
  const handleStartRun = useCallback(
    (run: Run) => void receipt(run.id, () => startRun(run.id)),
    [receipt],
  );
  const handleFinishRun = useCallback(
    (run: Run, body: { outcome: string; error?: string | null; result_excerpt?: string | null }) =>
      void receipt(run.id, () => finishRun(run.id, {
        outcome: body.outcome as 'done' | 'failed' | 'cancelled' | 'timeout' | 'needs_human',
        error: body.error,
        result_excerpt: body.result_excerpt,
      })),
    [receipt],
  );
  const handleCancelRun = useCallback(
    (run: Run) => void receipt(run.id, () => cancelRun(run.id, { reason: 'owner 中止' })),
    [receipt],
  );
  const handleFinishAction = useCallback(
    (action: Action) => {
      if (!selectedCaseId) return;
      // 收口方向: 名下任一 run succeeded → succeeded, 否则 failed (失败真实性由 run 行 error 承载)
      void receipt(`act:${action.id}`, async () => {
        const agg = await getCaseAggregate(selectedCaseId);
        const myRuns = (agg.runs ?? []).filter(r => r.action_id === action.id);
        const succeeded = myRuns.some(r => r.status === 'succeeded');
        await finishAction(action.id, {
          expected_revision: action.revision ?? 1,
          succeeded,
          reason: succeeded ? null : 'run 未成功 (详见 run 行 error)',
        });
      });
    },
    [receipt, selectedCaseId],
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--sn-ink)' }}>执行指挥台</h2>
        <span style={{ fontSize: 11, color: 'var(--sn-ink-3)' }}>
          Case → Claim → Run → Artifact · 四段共享同一案件
        </span>
      </div>
      {!selectedCaseId && (
        <p style={STAGE_EMPTY}>选择下方任一案件，后三段将加载该案件的完整执行链。</p>
      )}

      <CaseStage
        cases={cases}
        selectedCaseId={selectedCaseId}
        onSelect={setSelectedCaseId}
        loading={casesLoading}
        error={casesError}
      />
      <ClaimStage
        caseId={selectedCaseId}
        items={agg?.judgments ?? []}
        loading={aggLoading}
        error={aggError}
      />
      <RunStage
        caseId={selectedCaseId}
        actions={agg?.actions ?? []}
        runs={agg?.runs ?? []}
        loading={aggLoading}
        error={aggError}
        starting={starting}
        onStart={handleStart}
        receiptBusy={receiptBusy}
        onClaimRun={handleClaimRun}
        onStartRun={handleStartRun}
        onFinishRun={handleFinishRun}
        onCancelRun={handleCancelRun}
        onFinishAction={handleFinishAction}
        onRefresh={() => {
          if (selectedCaseId) void loadAggregate(selectedCaseId);
        }}
      />
      <ArtifactStage
        caseId={selectedCaseId}
        items={agg?.artifacts ?? []}
        loading={aggLoading}
        error={aggError}
      />
    </div>
  );
}