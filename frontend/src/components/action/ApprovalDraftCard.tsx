/**
 * ApprovalDraftCard — 审批收件箱「待审 (draft)」提案卡 (B5 从 ApprovalInbox 抽出)
 *
 * 人主律交互契约: 看类型/发起方/证据数/正文 → 修订(JSON)后批准 或 驳回(原因必填≤200);
 * 批准二次确认 (双签 Run 会真实落盘产物, 不可撤), 写操作类提案挂橙色标记。
 * 写操作 (POST /api/proposals/{id}/approve · /reject) 原样搬运, data-testid 与 class 逐字一致。
 */
import { useCallback, useState } from 'react';
import { approveProposal, rejectProposal, type Proposal } from '../../api/proposals';
import { Badge } from './ApprovalBadge';
import {
  KIND_LABEL, MAX_REJECT_REASON, REVIEWER, SOURCE_LABEL, WRITE_KINDS,
  fmtTime, payloadPreview, type CardBusy,
} from './approvalModel';

interface DraftCardProps {
  p: Proposal;
  onSettled: () => void;
}

export function ApprovalDraftCard({ p, onSettled }: DraftCardProps) {
  const [armed, setArmed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftJson, setDraftJson] = useState(() => JSON.stringify(p.payload ?? {}, null, 2));
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<CardBusy | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reasonLen = reason.trim().length;
  const reasonInvalid = reasonLen === 0 || reason.length > MAX_REJECT_REASON;

  const editedPayload = (): Record<string, unknown> | null | undefined => {
    if (!editing) return undefined;
    try {
      const parsed = JSON.parse(draftJson) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('修订内容必须是 JSON 对象');
      }
      return parsed as Record<string, unknown>;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'JSON 解析失败');
      return null;
    }
  };

  const doApprove = useCallback(async () => {
    const payload = editedPayload();
    if (payload === null && editing) return; // JSON 非法已在 editedPayload 报错
    setBusy('approve');
    setError(null);
    try {
      await approveProposal(p.id, REVIEWER, payload ?? undefined);
      onSettled();
    } catch (e) {
      setError(`批准失败: ${e instanceof Error ? e.message : String(e)}`);
      setBusy(null);
    }
  }, [editing, draftJson, p.id, onSettled]);

  const doReject = useCallback(async () => {
    if (reasonInvalid) return;
    setBusy('reject');
    setError(null);
    try {
      await rejectProposal(p.id, REVIEWER, reason.trim());
      onSettled();
    } catch (e) {
      setError(`驳回失败: ${e instanceof Error ? e.message : String(e)}`);
      setBusy(null);
    }
  }, [reason, reasonInvalid, p.id, onSettled]);

  const isWrite = WRITE_KINDS.has(p.kind);

  return (
    <li
      className="p-3 rounded border"
      style={{ borderColor: 'var(--sn-line, var(--line))' }}
      data-testid="approval-draft-card"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="info">{KIND_LABEL[p.kind]}</Badge>
        <Badge tone="gray">{SOURCE_LABEL[p.source]}</Badge>
        {isWrite && (
          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
            style={{
              background: 'color-mix(in srgb, var(--color-warning) 16%, transparent)',
              color: 'var(--color-warning)',
            }}
            title="批准会产生真实写入 (产物落盘 / 知识写库)"
            data-testid="write-op-badge"
          >
            写操作
          </span>
        )}
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          证据 {p.evidence_ids.length} 条
        </span>
        {p.case_id && (
          <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
            {p.case_id}
          </span>
        )}
        <span className="text-xs num ml-auto" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          {fmtTime(p.created_at)}
        </span>
      </div>

      <p className="text-sm mt-2 whitespace-pre-wrap" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
        {payloadPreview(p)}
      </p>
      {p.prompt_version && (
        <p className="text-xs mt-1 num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          prompt: {p.prompt_version}
        </p>
      )}

      {/* 修订: 展开 JSON 原文编辑, 批准时随修订提交 (受控 open, 不依赖 toggle 事件) */}
      <details className="mt-2" open={editing}>
        <summary
          className="text-xs cursor-pointer select-none"
          style={{ color: 'var(--color-info)' }}
          onClick={e => { e.preventDefault(); setEditing(v => !v); }}
        >
          修订后批准（展开编辑 JSON）
        </summary>
        <textarea
          className="w-full mt-2 p-2 rounded border text-xs font-mono"
          rows={6}
          value={draftJson}
          onChange={e => setDraftJson(e.target.value)}
          aria-label="修订提案 payload JSON"
          style={{ background: 'transparent', color: 'var(--sn-ink, var(--text-primary))', borderColor: 'var(--sn-line, var(--line))' }}
        />
      </details>

      {/* 驳回原因 */}
      {rejecting && (
        <div className="mt-2">
          <textarea
            className="w-full p-2 rounded border text-sm"
            rows={2}
            maxLength={240}
            placeholder="驳回原因（必填，≤200 字）"
            value={reason}
            onChange={e => setReason(e.target.value)}
            aria-label="驳回原因"
            style={{ background: 'transparent', color: 'var(--sn-ink, var(--text-primary))', borderColor: 'var(--sn-line, var(--line))' }}
          />
          <div className="flex items-center justify-between mt-1">
            <span
              className="text-xs num"
              style={{ color: reason.length > MAX_REJECT_REASON ? 'var(--sn-red, var(--color-error))' : 'var(--sn-ink-3, var(--text-muted))' }}
            >
              {reason.length}/{MAX_REJECT_REASON}
            </span>
            <span className="flex gap-2">
              <button type="button" className="text-xs px-2 py-1 rounded" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}
                onClick={() => { setRejecting(false); setReason(''); }}>
                取消
              </button>
              <button
                type="button"
                className="text-xs px-2.5 py-1 rounded font-medium focus-ring disabled:opacity-50"
                disabled={reasonInvalid || busy !== null}
                onClick={() => { void doReject(); }}
                style={{ background: 'var(--color-error)', color: 'var(--text-on-error, #fff)' }}
                data-testid="reject-confirm-btn"
              >
                {busy === 'reject' ? '提交中…' : '确认驳回'}
              </button>
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mt-3">
        {!armed && (
          <button
            type="button"
            className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
            disabled={busy !== null}
            onClick={() => setArmed(true)}
            style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
            data-testid="approve-arm-btn"
          >
            批准
          </button>
        )}
        {armed && (
          <span className="flex items-center gap-2">
            <button
              type="button"
              className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
              disabled={busy !== null}
              onClick={() => { void doApprove(); }}
              style={{ background: 'var(--color-warning)', color: 'var(--text-on-warning, #1a1400)' }}
              data-testid="approve-confirm-btn"
            >
              {busy === 'approve' ? '执行中…' : '确认批准？将生成双签 Run'}
            </button>
            <button
              type="button"
              className="text-xs px-2 py-1.5 rounded"
              disabled={busy !== null}
              onClick={() => setArmed(false)}
              style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}
            >
              取消
            </button>
          </span>
        )}
        {!rejecting && (
          <button
            type="button"
            className="text-xs px-2 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
            disabled={busy !== null}
            onClick={() => { setRejecting(true); setArmed(false); }}
            style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink, var(--text-primary))' }}
            data-testid="reject-arm-btn"
          >
            驳回
          </button>
        )}
      </div>
      {error && <p className="text-xs mt-2" role="status" data-testid="draft-card-error" style={{ color: 'var(--sn-red, var(--color-error))' }}>{error}</p>}
    </li>
  );
}
