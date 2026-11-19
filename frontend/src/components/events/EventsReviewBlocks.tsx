/**
 * EventsReviewBlocks — 通稿审核的纯展示区块 (标题区 / 提示条 / 类型清单 / 候选队列)
 * (B5.6 拆分: 自 EventsReviewPage.tsx 原样搬运, DOM/class/aria 文案逐字不变)
 *
 * 纪律: 本文件只渲染, 不取数、不持有状态; 取数编排与状态全在 EventsReviewPage 容器。
 */
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../../primitives/EmptyState';
import { PageHeader } from '../../primitives/PageHeader';
import type { CandidateRow, EventTypeRow, ReviewNotice } from './eventsReviewModel';

/** 顶部标题区 (含数据源印章) */
export function EventsReviewHeader() {
  return (
    <PageHeader
      kicker="WIRE DESK"
      title="通稿审核"
      description="事件类型候选 (LLM 抽取的技战法映射) 逐条人工审定: 通过落映射图, 驳回须写理由; 全部动作写审计日志。"
      footer={<Stamp color="info" variant="hollow">数据源: /api/event-technique (真实端点)</Stamp>}
    />
  );
}

/** 操作结果提示条 (通过/驳回/批量结果) */
export function EventsNotice({ notice }: { notice: ReviewNotice }) {
  return (
    <p className="ac-banner" role="status" style={{ color: notice.kind === 'ok' ? 'var(--sn-mint)' : 'var(--sn-amber)', borderColor: notice.kind === 'ok' ? 'var(--sn-mint-dim)' : 'var(--sn-amber-dim)', background: notice.kind === 'ok' ? 'var(--sn-mint-dim)' : 'var(--sn-amber-dim)' }}>
      {notice.text}
    </p>
  );
}

/** 事件类型清单 (卡片网格 + 加载/失败/空态) */
export function EventsTypeSection({
  types,
  typesError,
  selected,
  onSelect,
}: {
  types: EventTypeRow[] | null;
  typesError: string | null;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      <div className="ed-sechead">
        <span>事件类型</span>
        <span className="ed-note">{types ? `${types.length} 类` : '…'}</span>
      </div>
      {types === null ? (
        <EmptyState title="加载中…" />
      ) : types.length === 0 ? (
        <EmptyState
          title={typesError ? '类型清单加载失败' : '暂无事件类型'}
          description={typesError ?? 'MP-2 语料入库后这里会出现事件类型清单。'}
        />
      ) : (
        <div className="ed-grid">
          {types.map(t => {
            const stats = t.candidate_stats ?? {};
            const active = selected === t.id;
            return (
              <div
                key={t.id}
                className={`ed-card click${active ? '' : ''}`}
                role="button"
                tabIndex={0}
                style={active ? { borderColor: 'var(--sn-accent)' } : undefined}
                onClick={() => onSelect(t.id)}
                onKeyDown={ev => { if (ev.key === 'Enter') onSelect(t.id); }}
              >
                <span className="t">{t.name || t.id}</span>
                <span className="mono" style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }}>{t.id}</span>
                <span className="d">
                  待审 {stats.pending ?? 0} · 已过 {stats.approved ?? 0} · 驳回 {stats.rejected ?? 0}
                  {typeof stats.avg_confidence === 'number' ? ` · 均信 ${stats.avg_confidence}` : ''}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

/** 候选队列 (批量通过按钮 + 明细表 + 行内驳回表单) */
export function EventsCandidateSection({
  selected,
  candidates,
  candsLoading,
  candsError,
  busyId,
  batching,
  batchArmed,
  rejectId,
  rejectReason,
  onBatchClick,
  onApprove,
  onReject,
  onStartReject,
  onCancelReject,
  onRejectReasonChange,
}: {
  selected: string;
  candidates: CandidateRow[];
  candsLoading: boolean;
  candsError: string | null;
  busyId: string | null;
  batching: boolean;
  batchArmed: boolean;
  rejectId: string | null;
  rejectReason: string;
  onBatchClick: () => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onStartReject: (id: string) => void;
  onCancelReject: () => void;
  onRejectReasonChange: (value: string) => void;
}) {
  return (
    <>
      <div className="ed-sechead">
        <span>候选队列 · {selected}</span>
        <span className="ed-note" style={{ display: 'inline-flex', gap: 10, alignItems: 'baseline' }}>
          {candidates.length} PENDING
          <button
            type="button"
            className={`ed-btn${batchArmed ? ' warn' : ''}`}
            disabled={batching}
            onClick={onBatchClick}
          >
            {batching ? '批量中…' : batchArmed ? '确认批量通过 (≥0.7)?' : '批量通过 (信 ≥0.7)'}
          </button>
        </span>
      </div>
      {candsLoading ? (
        <EmptyState title="候选加载中…" />
      ) : candsError ? (
        <EmptyState title="候选加载失败" description={candsError} />
      ) : candidates.length === 0 ? (
        <EmptyState title="该类型暂无待审候选" description="候选由采集管线每日自动抽取入池 (置信度 ≥ 阈值)。若尚未产出, 可等待下次调度或运行 agent 抽取脚本。" />
      ) : (
        <table className="ed-table" aria-label="候选队列">
          <thead>
            <tr>
              <th>技战法</th>
              <th>阶段</th>
              <th>置信</th>
              <th>证据摘录</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map(c => (
              <tr key={c.id}>
                <td className="mono">{c.technique_id}</td>
                <td className="mono">{c.stage ?? '--'}</td>
                <td className="mono">{typeof c.confidence === 'number' ? c.confidence.toFixed(2) : '--'}</td>
                <td style={{ maxWidth: 380 }}>
                  <div style={{ lineHeight: 1.55 }}>{c.evidence_quote || c.rationale || '--'}</div>
                  {rejectId === c.id && (
                    <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                      <input
                        className="editorial-input"
                        style={{ flex: 1, minWidth: 160 }}
                        placeholder="驳回理由 (必填, ≤500 字)"
                        aria-label="驳回理由"
                        value={rejectReason}
                        maxLength={500}
                        onChange={e => onRejectReasonChange(e.target.value)}
                      />
                    </div>
                  )}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {rejectId === c.id ? (
                      <>
                        <button
                          type="button"
                          className="ed-btn warn"
                          disabled={busyId === c.id || !rejectReason.trim()}
                          onClick={() => onReject(c.id)}
                        >
                          确认驳回
                        </button>
                        <button type="button" className="ed-btn" onClick={onCancelReject}>
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="ed-btn primary"
                          disabled={busyId === c.id}
                          onClick={() => onApprove(c.id)}
                        >
                          通过
                        </button>
                        <button
                          type="button"
                          className="ed-btn"
                          disabled={busyId === c.id}
                          onClick={() => onStartReject(c.id)}
                        >
                          驳回
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
