/**
 * EventsReviewPage — 通稿审核 (/action/events, Phase 4 DEV-0183)
 *
 * 定位: MP-2 事件类型候选的人工审核台 (对齐方案A 原型 events 视图)。
 * 数据: 全部真实 API (后端已注册, 无 gate):
 *  - GET  /api/event-technique/event-types              — 类型清单 (含候选进度)
 *  - GET  /api/event-technique/candidates?event_type_id — 该类型候选 (pending)
 *  - POST /api/event-technique/candidates/{id}/approve   — 通过 (写 audit_log_mp2_review)
 *  - POST /api/event-technique/candidates/{id}/reject    — 驳回 (reason 必填)
 *  - POST /api/event-technique/event-types/{id}/batch-approve — 批量通过 (min_confidence)
 * 注意: /api/event-technique/candidates 的 event_type_id 为必填 Query,
 *       故先选类型再拉候选; 类型清单为空/接口失败时显式降级空态。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getJSON, postJSON } from '../../lib/api';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import '../shared/editorial/pages.css';

interface EventTypeRow {
  id: string;
  name?: string;
  candidate_stats?: {
    pending?: number;
    approved?: number;
    rejected?: number;
    total?: number;
    avg_confidence?: number;
  };
}

interface CandidateRow {
  candidate_id: string;
  technique_id: string;
  stage?: string;
  confidence?: number;
  evidence_quote?: string;
  rationale?: string;
  owner_status?: string;
}

export function EventsReviewPage() {
  const [types, setTypes] = useState<EventTypeRow[] | null>(null);
  const [typesError, setTypesError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [candsLoading, setCandsLoading] = useState(false);
  const [candsError, setCandsError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [batching, setBatching] = useState(false);
  // A2 (DEV-0188): 批量通过两段式确认 — 首次点击仅武装 (5s 无操作自动退出), 二次点击才发请求
  const [batchArmed, setBatchArmed] = useState(false);
  const armTimer = useRef<number | null>(null);

  const disarmBatch = useCallback(() => {
    if (armTimer.current !== null) {
      window.clearTimeout(armTimer.current);
      armTimer.current = null;
    }
    setBatchArmed(false);
  }, []);

  useEffect(() => () => disarmBatch(), [disarmBatch]);

  const loadTypes = useCallback(async () => {
    setTypesError(null);
    try {
      const data = await getJSON<{ items?: EventTypeRow[] }>('/api/event-technique/event-types');
      setTypes(data.items ?? []);
    } catch (e) {
      setTypes([]);
      setTypesError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => { void loadTypes(); }, [loadTypes]);

  const loadCandidates = useCallback(async (eventTypeId: string) => {
    setCandsLoading(true);
    setCandsError(null);
    try {
      const data = await getJSON<{ items?: CandidateRow[] }>(
        `/api/event-technique/candidates?event_type_id=${encodeURIComponent(eventTypeId)}&owner_status=pending`,
      );
      setCandidates(data.items ?? []);
    } catch (e) {
      setCandidates([]);
      setCandsError(e instanceof Error ? e.message : String(e));
    } finally {
      setCandsLoading(false);
    }
  }, []);

  function selectType(id: string) {
    setSelected(id);
    setCandidates([]);
    setRejectId(null);
    setNotice(null);
    disarmBatch();
    void loadCandidates(id);
  }

  /** A2: 两段式 — 首次点击武装 (5s 超时自动解除), 二次点击才真正批量 */
  function onBatchClick() {
    if (batchArmed) {
      disarmBatch();
      void batchApprove();
      return;
    }
    setBatchArmed(true);
    if (armTimer.current !== null) window.clearTimeout(armTimer.current);
    armTimer.current = window.setTimeout(() => setBatchArmed(false), 5000);
  }

  async function approve(candidateId: string) {
    if (!selected) return;
    setBusyId(candidateId);
    setNotice(null);
    try {
      await postJSON(`/api/event-technique/candidates/${encodeURIComponent(candidateId)}/approve`, {});
      setCandidates(list => list.filter(c => c.candidate_id !== candidateId));
      setNotice({ kind: 'ok', text: `已通过 ${candidateId}` });
      void loadTypes();
    } catch (e) {
      setNotice({ kind: 'err', text: `通过失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setBusyId(null);
    }
  }

  async function reject(candidateId: string) {
    if (!selected || !rejectReason.trim()) return;
    setBusyId(candidateId);
    setNotice(null);
    try {
      await postJSON(`/api/event-technique/candidates/${encodeURIComponent(candidateId)}/reject`, { reason: rejectReason.trim() });
      setCandidates(list => list.filter(c => c.candidate_id !== candidateId));
      setRejectId(null);
      setRejectReason('');
      setNotice({ kind: 'ok', text: `已驳回 ${candidateId}` });
      void loadTypes();
    } catch (e) {
      setNotice({ kind: 'err', text: `驳回失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setBusyId(null);
    }
  }

  async function batchApprove() {
    if (!selected) return;
    setBatching(true);
    setNotice(null);
    try {
      const r = await postJSON<{ approved?: number; total?: number }>(
        `/api/event-technique/event-types/${encodeURIComponent(selected)}/batch-approve`,
        { min_confidence: 0.7 },
      );
      setNotice({ kind: 'ok', text: `批量通过 ${r.approved ?? 0}/${r.total ?? 0} 条` });
      void loadCandidates(selected);
      void loadTypes();
    } catch (e) {
      setNotice({ kind: 'err', text: `批量通过失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setBatching(false);
    }
  }

  return (
      <div className="ed-wrap">
        <header className="ed-head">
          <span className="ed-kicker">WIRE DESK</span>
          <h1 className="ed-h1">通稿审核</h1>
          <p className="ed-sub">事件类型候选 (LLM 抽取的技战法映射) 逐条人工审定: 通过落映射图, 驳回须写理由; 全部动作写审计日志。</p>
          <div style={{ marginTop: 10 }}>
            <Stamp color="info" variant="hollow">数据源: /api/event-technique (真实端点)</Stamp>
          </div>
        </header>

        {notice && (
          <p className="ac-banner" role="status" style={{ color: notice.kind === 'ok' ? 'var(--sn-mint)' : 'var(--sn-amber)', borderColor: notice.kind === 'ok' ? 'var(--sn-mint-dim)' : 'var(--sn-amber-dim)', background: notice.kind === 'ok' ? 'var(--sn-mint-dim)' : 'var(--sn-amber-dim)' }}>
            {notice.text}
          </p>
        )}

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
                  onClick={() => selectType(t.id)}
                  onKeyDown={ev => { if (ev.key === 'Enter') selectType(t.id); }}
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

        {selected && (
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
              <EmptyState title="该类型暂无待审候选" description="候选由采集管线按置信度 ≥ 阈值自动入池, 也可稍后刷新。" />
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
                    <tr key={c.candidate_id}>
                      <td className="mono">{c.technique_id}</td>
                      <td className="mono">{c.stage ?? '--'}</td>
                      <td className="mono">{typeof c.confidence === 'number' ? c.confidence.toFixed(2) : '--'}</td>
                      <td style={{ maxWidth: 380 }}>
                        <div style={{ lineHeight: 1.55 }}>{c.evidence_quote || c.rationale || '--'}</div>
                        {rejectId === c.candidate_id && (
                          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                            <input
                              className="editorial-input"
                              style={{ flex: 1, minWidth: 160 }}
                              placeholder="驳回理由 (必填, ≤500 字)"
                              aria-label="驳回理由"
                              value={rejectReason}
                              maxLength={500}
                              onChange={e => setRejectReason(e.target.value)}
                            />
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {rejectId === c.candidate_id ? (
                            <>
                              <button
                                type="button"
                                className="ed-btn warn"
                                disabled={busyId === c.candidate_id || !rejectReason.trim()}
                                onClick={() => reject(c.candidate_id)}
                              >
                                确认驳回
                              </button>
                              <button type="button" className="ed-btn" onClick={() => { setRejectId(null); setRejectReason(''); }}>
                                取消
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="ed-btn primary"
                                disabled={busyId === c.candidate_id}
                                onClick={() => approve(c.candidate_id)}
                              >
                                通过
                              </button>
                              <button
                                type="button"
                                className="ed-btn"
                                disabled={busyId === c.candidate_id}
                                onClick={() => { setRejectId(c.candidate_id); setRejectReason(''); }}
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
        )}
      </div>
  );
}
