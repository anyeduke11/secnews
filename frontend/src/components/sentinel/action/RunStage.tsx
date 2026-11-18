/**
 * 行动四段指挥台 · 第③段 Run (R-15 + v0.8.9 R-1)
 * 数据源: GET /api/v1/cases/{id}/aggregate → actions + runs (既有端点)
 * 执行账本呈现: outcome 显式 / 耗时 / 失败原因。
 * 发起运行: 已批准 (approved) 且无运行记录 → POST /api/v1/actions/{id}/start (既有端点)。
 * 人工回执 (v0.8.9 R-1, D4 裁决: direct 执行体 = 人):
 *   queued → [认领/取消] · claimed → [开工/取消] · running → [登记结果(outcome+error)/取消]
 *   终态 action (running) 且全部 run 终态 → [收口 Action] (C1-2 finish 端点)。
 *
 * B5 (2026-11-18) 拆分: 行级渲染下沉 RunActionRow, 回执表单下沉 RunFinishForm,
 * 常量/样式映射下沉 runStageModel; 本文件保留段壳、单值展开态与 props 契约 (未变)。
 */
import { useState } from 'react';
import type { Action, Run } from '../../../domain/v1_0';
import {
  STAGE,
  STAGE_HEAD,
  STAGE_TITLE,
  STAGE_COUNT,
  STAGE_EMPTY,
} from './stageStyles';
import { RunActionRow } from './RunActionRow';

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
  /** R-2: plan 变更后刷新聚合 (父层 loadAggregate) */
  onRefresh?: () => void;
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
  onRefresh,
}: RunStageProps) {
  // 登记结果表单: 仅 running 的 run 可展开 (runId 为 null = 收起)
  const [finishFormRun, setFinishFormRun] = useState<string | null>(null);
  // R-2 执行计划面板 (C3-4): 仅 queued/claimed 的 run 可开; 计划读写/审批归 PlanPanel
  const [planPanelRun, setPlanPanelRun] = useState<string | null>(null);

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
          {actions.map(a => (
            <RunActionRow
              key={a.id}
              action={a}
              runs={runs}
              starting={starting}
              onStart={onStart}
              receiptBusy={receiptBusy}
              onClaimRun={onClaimRun}
              onStartRun={onStartRun}
              onFinishRun={onFinishRun}
              onCancelRun={onCancelRun}
              onFinishAction={onFinishAction}
              finishFormRun={finishFormRun}
              onOpenFinishForm={setFinishFormRun}
              onCloseFinishForm={() => setFinishFormRun(null)}
              planPanelRun={planPanelRun}
              onTogglePlanPanel={runId => setPlanPanelRun(planPanelRun === runId ? null : runId)}
              onRefresh={onRefresh}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
