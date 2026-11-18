/**
 * JudgingQueuePanel — 行动层「判读待办 · planning_actions」区块 (B5 从 SentinelActionPage 抽出)
 *
 * 纯展示 + props 回调: 取数 (GET /api/kl/planning-actions?status=pending) 与推进写操作
 * (PUT /api/kl/planning-actions/{id}/status 两步状态机链) 仍由容器编排。
 * DOM / class / aria 与拆分前逐字一致。
 */
import {
  ACTION_SHOWN, ACTION_TYPE_LABEL, relTime,
  type ActionStatus, type PlanningAction, type WriteState,
} from './actionModel';

interface JudgingQueuePanelProps {
  loading: boolean;
  /** 接口返回的全量待推进队列 (页脚计数与 PENDING 徽标口径) */
  actions: PlanningAction[];
  /** 本屏实际呈现的前 ACTION_SHOWN 条 */
  shownActions: PlanningAction[];
  /** 行级写入态: key = planning action id */
  actionState: Record<number, WriteState>;
  onAdvance: (action: PlanningAction, target: ActionStatus) => void;
  onGoCompound: () => void;
}

export function JudgingQueuePanel({
  loading,
  actions,
  shownActions,
  actionState,
  onAdvance,
  onGoCompound,
}: JudgingQueuePanelProps) {
  return (
    <section className="ac-panel ac-out" aria-labelledby="ac-h-out">
      <header className="ac-ph">
        <h2 id="ac-h-out">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M3.5 12.5l.9-3.2 6.6-6.6 2.3 2.3-6.6 6.6z" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /><path d="M9.3 4.2l2.3 2.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          判读待办
        </h2>
        <span className="ac-phn num">{actions.length} PENDING</span>
      </header>

      {loading ? (
        <div className="ac-load" aria-busy="true"><div className="skel-line w3" /><div className="skel-line w2" /><div className="skel-line w1" /></div>
      ) : shownActions.length === 0 ? (
        <div className="ac-empty">
          <div className="ac-empty-ring" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 9.5l3.5 3.5L15 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
          <h3>判读队列已清空</h3>
          <p>没有待推进的规划动作。采集入库后会自动生成新的动作。</p>
        </div>
      ) : (
        <ul className="ac-dlist">
          {shownActions.map(a => {
            const state = actionState[a.id];
            const settled = state === 'done' || state === 'dismissed';
            const badge = a.priority >= 8 ? 'hot' : a.priority >= 5 ? 'warm' : '';
            return (
              <li key={a.id}>
                <div className="ac-drow">
                  <input
                    type="checkbox"
                    checked={a.status === 'completed'}
                    disabled={state === 'saving' || a.status === 'completed'}
                    onChange={() => onAdvance(a, 'completed')}
                    aria-label={`完成：${a.title}`}
                  />
                  <div className="ac-dbody">
                    <p className="ac-dt">
                      <span className={`ac-badge${badge ? ` ${badge}` : ''}`}>{ACTION_TYPE_LABEL[a.action_type] ?? a.action_type}</span>
                      <span className="ac-dtitle">{a.title}</span>
                    </p>
                    <p className="ac-dm">
                      <span>#{String(a.id).padStart(4, '0')}</span>
                      <span>P{a.priority}</span>
                      {a.current_stage && a.target_stage && (
                        <span className="stage">{a.current_stage} → {a.target_stage}</span>
                      )}
                      <span>{relTime(a.created_at)}</span>
                    </p>
                  </div>
                  <div className="ac-dops">
                    {state === 'saving' && <span className="ac-dstate doing" role="status">推进中</span>}
                    {state === 'fail' && (
                      <span className="ac-dstate fail" role="status">
                        {a.status === 'in_progress' ? '已推进一步' : '未写入'}
                      </span>
                    )}
                    {state === 'done' && <span className="ac-dstate done" role="status">已完成</span>}
                    {state === 'dismissed' && <span className="ac-dstate" role="status">已暂缓</span>}
                    {!settled && a.status !== 'dismissed' && (
                      <button
                        type="button"
                        className="ac-dbtn"
                        disabled={state === 'saving'}
                        onClick={() => onAdvance(a, 'dismissed')}
                      >
                        暂缓
                      </button>
                    )}
                    {a.status === 'in_progress' && !settled && (
                      <span className="ac-dstate doing">进行中</span>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <p className="ac-note">
        队列共 {actions.length} 条待推进（服务端单次上限 50 条，此处按优先级取前 {Math.min(ACTION_SHOWN, Math.max(actions.length, 1))} 条）。
        「完成」按状态机两步走：pending → 进行中 → 已完成；中途失败会停在已确认的那一步。
      </p>
      <a className="ac-link" href="/knowledge/compound" onClick={e => { e.preventDefault(); onGoCompound(); }}>
        查看复利台全量队列
        <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </a>
    </section>
  );
}
