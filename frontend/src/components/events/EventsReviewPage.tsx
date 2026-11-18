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
 *
 * B5.6 拆分: 本文件只留状态与取数编排 (容器), 纯展示区块见 EventsReviewBlocks.tsx,
 *             行类型见 eventsReviewModel.ts。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  approveEventCandidate,
  batchApproveEventTypes,
  listEventCandidates,
  listEventTypes,
  rejectEventCandidate,
} from '../../api/shared';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import {
  EventsCandidateSection,
  EventsNotice,
  EventsReviewHeader,
  EventsTypeSection,
} from './EventsReviewBlocks';
import type { CandidateRow, EventTypeRow, ReviewNotice } from './eventsReviewModel';
import '../shared/editorial/pages.css';

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
  const [notice, setNotice] = useState<ReviewNotice | null>(null);
  const [batching, setBatching] = useState(false);
  // A2 (DEV-0188): 批量通过两段式确认 — 首次点击仅武装 (5s 无操作自动退出), 二次点击才发请求
  const [batchArmed, setBatchArmed] = useState(false);
  const armTimer = useRef<number | null>(null);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

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
      const data = await listEventTypes<EventTypeRow>();
      if (dead.current) return;
      setTypes(data.items ?? []);
    } catch (e) {
      if (dead.current) return;
      setTypes([]);
      setTypesError(e instanceof Error ? e.message : String(e));
    }
  }, [dead]);

  useEffect(() => { void loadTypes(); }, [loadTypes]);

  const loadCandidates = useCallback(async (eventTypeId: string) => {
    setCandsLoading(true);
    setCandsError(null);
    try {
      const data = await listEventCandidates<CandidateRow>(eventTypeId, 'pending');
      if (dead.current) return;
      setCandidates(data.items ?? []);
    } catch (e) {
      if (dead.current) return;
      setCandidates([]);
      setCandsError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!dead.current) setCandsLoading(false);
    }
  }, [dead]);

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
      await approveEventCandidate(candidateId);
      if (dead.current) return;
      setCandidates(list => list.filter(c => c.id !== candidateId));
      setNotice({ kind: 'ok', text: `已通过 ${candidateId}` });
      void loadTypes();
    } catch (e) {
      if (dead.current) return;
      setNotice({ kind: 'err', text: `通过失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      if (!dead.current) setBusyId(null);
    }
  }

  async function reject(candidateId: string) {
    if (!selected || !rejectReason.trim()) return;
    setBusyId(candidateId);
    setNotice(null);
    try {
      await rejectEventCandidate(candidateId, rejectReason.trim());
      if (dead.current) return;
      setCandidates(list => list.filter(c => c.id !== candidateId));
      setRejectId(null);
      setRejectReason('');
      setNotice({ kind: 'ok', text: `已驳回 ${candidateId}` });
      void loadTypes();
    } catch (e) {
      if (dead.current) return;
      setNotice({ kind: 'err', text: `驳回失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      if (!dead.current) setBusyId(null);
    }
  }

  async function batchApprove() {
    if (!selected) return;
    setBatching(true);
    setNotice(null);
    try {
      const r = await batchApproveEventTypes(selected, 0.7);
      if (dead.current) return;
      setNotice({ kind: 'ok', text: `批量通过 ${r.approved_count ?? 0} 条 (跳过 ${r.skipped_count ?? 0})` });
      void loadCandidates(selected);
      void loadTypes();
    } catch (e) {
      if (dead.current) return;
      setNotice({ kind: 'err', text: `批量通过失败: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      if (!dead.current) setBatching(false);
    }
  }

  function startReject(candidateId: string) {
    setRejectId(candidateId);
    setRejectReason('');
  }

  function cancelReject() {
    setRejectId(null);
    setRejectReason('');
  }

  return (
      <div className="ed-wrap">
        <EventsReviewHeader />

        {notice && (
          <EventsNotice notice={notice} />
        )}

        <EventsTypeSection
          types={types}
          typesError={typesError}
          selected={selected}
          onSelect={selectType}
        />

        {selected && (
          <EventsCandidateSection
            selected={selected}
            candidates={candidates}
            candsLoading={candsLoading}
            candsError={candsError}
            busyId={busyId}
            batching={batching}
            batchArmed={batchArmed}
            rejectId={rejectId}
            rejectReason={rejectReason}
            onBatchClick={onBatchClick}
            onApprove={approve}
            onReject={reject}
            onStartReject={startReject}
            onCancelReject={cancelReject}
            onRejectReasonChange={setRejectReason}
          />
        )}
      </div>
  );
}
