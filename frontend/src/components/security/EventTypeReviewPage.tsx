/**
 * EventTypeReviewPage — MP-2 owner 人审页 (Settings/admin 子区, 不入三层壳导航).
 *
 * 数据源 (GET/POST /api/event-technique/*):
 *   - GET  /event-types                            — 5+ 类清单 (含 candidate_stats)
 *   - GET  /candidates?event_type_id=&owner_status=pending
 *   - POST /candidates/{id}/approve | /reject      — 三态 (approve/edit 经 note; reject 须 reason)
 *   - POST /event-types/{id}/batch-approve         — 批量便利 (confidence 阈值)
 *
 * 交互: 左侧事件类型分组列表, 右侧候选逐条 approve / edit(改 stage+note) / reject,
 * 顶部进度条 (approved/pending/rejected) + 批量 approve 按钮.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { getJSON, postJSON } from '../../lib/api';
import { useAbortGuard } from '../../hooks/useAbortGuard';

interface CandidateRow {
  id: string;
  event_type_id: string;
  technique_id: string;
  stage: string;
  confidence: number;
  evidence_quote: string;
  rationale?: string | null;
  source_report_id: string;
  llm_model: string;
  owner_status: 'pending' | 'approved' | 'edited' | 'rejected';
  reject_reason?: string | null;
}

interface EventTypeRow {
  id: string;
  name_zh: string;
  name_en: string;
  description?: string;
  kill_chain_stages: string[];
  candidate_stats: {
    pending: number;
    approved: number;
    rejected: number;
    total: number;
    avg_confidence: number;
    approved_map: number;
  };
}

const BASE = '/api/event-technique';

export function EventTypeReviewPage() {
  const [eventTypes, setEventTypes] = useState<EventTypeRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editStage, setEditStage] = useState<Record<string, string>>({});
  const [editNote, setEditNote] = useState<Record<string, string>>({});
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({});
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const loadEventTypes = useCallback(async () => {
    try {
      const data = await getJSON<{ items: EventTypeRow[] }>(`${BASE}/event-types`);
      if (dead.current) return;
      setEventTypes(data.items);
      setSelected((prev) => prev ?? data.items.find((t) => t.candidate_stats.pending > 0)?.id ?? data.items[0]?.id ?? null);
    } catch (e) {
      if (dead.current) return;
      setError(String(e));
    }
  }, [dead]);

  const loadCandidates = useCallback(async (etId: string) => {
    const data = await getJSON<{ items: CandidateRow[] }>(
      `${BASE}/candidates?event_type_id=${encodeURIComponent(etId)}&owner_status=pending`,
    );
    if (dead.current) return;
    setCandidates(data.items);
  }, [dead]);

  useEffect(() => {
    void loadEventTypes();
  }, [loadEventTypes]);

  useEffect(() => {
    if (selected) void loadCandidates(selected).catch((e) => setError(String(e)));
  }, [selected, loadCandidates]);

  const current = useMemo(() => eventTypes.find((t) => t.id === selected) ?? null, [eventTypes, selected]);

  const act = useCallback(
    async (cand: CandidateRow, action: 'approve' | 'edit' | 'reject') => {
      setBusyId(cand.id);
      setError(null);
      try {
        if (action === 'reject') {
          const reason = (rejectReason[cand.id] ?? '').trim();
          if (!reason) {
            setError('reject 需要填写理由 (审计要求)');
            return;
          }
          await postJSON(`${BASE}/candidates/${cand.id}/reject`, { reason, owner: 'owner' });
        } else {
          const note = (editNote[cand.id] ?? '').trim() || null;
          if (action === 'edit') {
            // edit = 改 stage 后 approve (owner_audit_chain 保留编辑记录)
            const newStage = (editStage[cand.id] ?? '').trim();
            if (newStage && newStage !== cand.stage) {
              await postJSON(`${BASE}/candidates`, {
                ...cand,
                stage: newStage,
                llm_model: `${cand.llm_model}+owner-edit`,
              });
              await postJSON(`${BASE}/candidates/${cand.id}/reject`, {
                reason: `superseded by owner edit (stage → ${newStage})`,
                owner: 'owner',
              });
            } else {
              await postJSON(`${BASE}/candidates/${cand.id}/approve`, { note, owner: 'owner' });
            }
          } else {
            await postJSON(`${BASE}/candidates/${cand.id}/approve`, { note, owner: 'owner' });
          }
        }
        await loadCandidates(cand.event_type_id);
        await loadEventTypes();
      } catch (e) {
        if (dead.current) return;
        setError(String(e));
      } finally {
        if (!dead.current) setBusyId(null);
      }
    },
    [editNote, editStage, rejectReason, loadCandidates, loadEventTypes, dead],
  );

  const batchApprove = useCallback(async () => {
    if (!selected) return;
    setBusyId('__batch__');
    setError(null);
    try {
      await postJSON(`${BASE}/event-types/${selected}/batch-approve`, {
        min_confidence: 0.7,
        owner: 'owner',
        note: 'batch approve via review page',
      });
      await loadCandidates(selected);
      await loadEventTypes();
    } catch (e) {
      if (dead.current) return;
      setError(String(e));
    } finally {
      if (!dead.current) setBusyId(null);
    }
  }, [selected, loadCandidates, loadEventTypes, dead]);

  return (
    <div className="mx-auto max-w-6xl p-4" data-testid="event-type-review-page">
      <header className="mb-4">
        <h2 className="text-lg font-semibold text-slate-900">事件类型技战法候选 · owner 人审</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          LLM 抽取候选 → owner 三态审定 → 落 event_technique_map (追溯链: candidate → 报告 → source_url)
        </p>
      </header>

      {error && (
        <p className="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[260px_1fr]">
        {/* 左: 事件类型分组 + 进度 */}
        <aside className="space-y-2">
          {eventTypes.map((t) => {
            const s = t.candidate_stats;
            const done = s.approved + s.rejected;
            const pct = s.total ? Math.round((done / s.total) * 100) : 0;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setSelected(t.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selected === t.id ? 'border-sky-400 bg-sky-50' : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-800">{t.name_zh}</span>
                  {s.pending > 0 && (
                    <span className="rounded-full bg-amber-100 px-1.5 text-[11px] text-amber-700">{s.pending} 待审</span>
                  )}
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  审定链 {s.approved_map} · 批 {s.approved} / 拒 {s.rejected} / 共 {s.total}
                </p>
              </button>
            );
          })}
        </aside>

        {/* 右: 候选审阅 */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">
              {current ? `${current.name_zh} 待审候选` : '选择事件类型'}
            </h3>
            {current && current.candidate_stats.pending > 0 && (
              <button
                type="button"
                onClick={() => void batchApprove()}
                disabled={busyId === '__batch__'}
                className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                批量批准 (confidence ≥ 0.7)
              </button>
            )}
          </div>

          {candidates.length === 0 ? (
            <p className="rounded border border-dashed border-slate-300 bg-slate-50 px-3 py-6 text-center text-xs text-slate-400">
              当前类型无待审候选
            </p>
          ) : (
            candidates.map((c) => (
              <article key={c.id} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px]">{c.technique_id}</span>
                  <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[11px] text-sky-700">{c.stage}</span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                      c.confidence >= 0.7 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                    }`}
                  >
                    conf {c.confidence.toFixed(2)}
                  </span>
                  <span className="text-[11px] text-slate-400">{c.llm_model}</span>
                </div>
                <blockquote className="mt-2 border-l-2 border-slate-200 pl-2 text-xs leading-relaxed text-slate-600">
                  “{c.evidence_quote}”
                </blockquote>
                {c.rationale && <p className="mt-1 text-[11px] text-slate-400">理由: {c.rationale}</p>}

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void act(c, 'approve')}
                    disabled={busyId === c.id}
                    className="rounded bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    批准
                  </button>
                  <button
                    type="button"
                    onClick={() => void act(c, 'edit')}
                    disabled={busyId === c.id}
                    className="rounded bg-sky-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                  >
                    编辑后批准
                  </button>
                  <button
                    type="button"
                    onClick={() => void act(c, 'reject')}
                    disabled={busyId === c.id}
                    className="rounded bg-rose-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-rose-700 disabled:opacity-50"
                  >
                    拒绝
                  </button>
                  <input
                    value={editStage[c.id] ?? ''}
                    onChange={(e) => setEditStage((m) => ({ ...m, [c.id]: e.target.value }))}
                    placeholder="编辑 stage (可选)"
                    className="w-32 rounded border border-slate-200 px-1.5 py-1 text-[11px]"
                  />
                  <input
                    value={editNote[c.id] ?? ''}
                    onChange={(e) => setEditNote((m) => ({ ...m, [c.id]: e.target.value }))}
                    placeholder="note (可选)"
                    className="w-40 rounded border border-slate-200 px-1.5 py-1 text-[11px]"
                  />
                  <input
                    value={rejectReason[c.id] ?? ''}
                    onChange={(e) => setRejectReason((m) => ({ ...m, [c.id]: e.target.value }))}
                    placeholder="拒绝理由 (reject 必填)"
                    className="w-44 rounded border border-slate-200 px-1.5 py-1 text-[11px]"
                  />
                </div>
              </article>
            ))
          )}
        </section>
      </div>
    </div>
  );
}

export default EventTypeReviewPage;
