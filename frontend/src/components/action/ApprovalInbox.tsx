/**
 * ApprovalInbox — 行动层「AI 提案审批收件箱」区块 (v0.8.6 P1-1 切片3, M1 用例 A)。
 *
 * 人主律 UI 落点: AI 起草的研判/建议在此等人审批, 未经批准不成为事实。
 *  - 待审 (draft): 看类型/发起方/证据数/正文 → 修订(JSON)后批准 或 驳回(原因必填≤200);
 *    批准二次确认 (双签 Run 会真实落盘产物, 不可撤); 写操作类提案挂橙色标记。
 *  - 失败 (failed): 展示模型失败原因; 有 case 锚点可一键重试 (重新 AI 起草, 生成新提案)。
 *
 * 数据: /api/proposals (run_ledger_api), 全部真实 API; 失败显 unavailable 不伪装。
 * 挂载: SentinelActionPage 页内区块 (NAV4 四菜单纪律: 不新增一级入口/路由)。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  approveProposal,
  draftJudgment,
  listProposals,
  rejectProposal,
  type Proposal,
  type ProposalKind,
} from '../../api/proposals';
import { PANEL_SHELL } from '../v1/panels/panelShell';

/** 后端 MAX_REJECT_REASON_CHARS, 前端先挡一道 (后端 400 兜底)。 */
const MAX_REJECT_REASON = 200;
/** 单机工作站单用户, 与既有 v1 端点 submitted_by='user'/'owner' 口径一致。 */
const REVIEWER = 'owner';
/** 批准即产生真实写入 (产物落盘 / 知识写库) 的类型 — 橙色写操作标记。 */
const WRITE_KINDS: ReadonlySet<ProposalKind> = new Set(['judgment_draft', 'knowledge_draft']);

const KIND_LABEL: Record<ProposalKind, string> = {
  judgment_draft: '研判草案',
  case_suggestion: '建案建议',
  knowledge_draft: '知识草案',
  report: '报告',
};

const SOURCE_LABEL: Record<Proposal['source'], string> = {
  agent: 'AI 代理',
  command: '命令栏',
  copilot: '副驾',
};

type CardBusy = 'approve' | 'reject' | 'retry';

interface DraftCardProps {
  p: Proposal;
  onSettled: () => void;
}

function fmtTime(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false });
}

/** 研判草案正文首行 (claim); 其余类型回退到 payload JSON 预览。 */
function payloadPreview(p: Proposal): string {
  const claim = p.payload?.claim;
  if (typeof claim === 'string' && claim.trim()) return claim;
  try {
    return JSON.stringify(p.payload ?? {}, null, 2);
  } catch {
    return String(p.payload ?? '');
  }
}

function DraftCard({ p, onSettled }: DraftCardProps) {
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

function Badge({ children, tone }: { children: ReactNode; tone: 'info' | 'gray' }) {
  const fg = tone === 'info' ? 'var(--color-info)' : 'var(--text-secondary)';
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: `color-mix(in srgb, ${fg} 14%, transparent)`, color: fg }}
    >
      {children}
    </span>
  );
}

export function ApprovalInbox() {
  const [drafts, setDrafts] = useState<Proposal[]>([]);
  const [failed, setFailed] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, f] = await Promise.all([
        listProposals({ status: 'draft', limit: 50 }),
        listProposals({ status: 'failed', limit: 20 }),
      ]);
      setDrafts(d.items);
      setFailed(f.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /** 失败提案重试 = 用原 case 重新 AI 起草 (后端生成一条新提案, 成功 draft/失败 failed)。 */
  const retry = useCallback(async (p: Proposal) => {
    if (!p.case_id) return;
    setRetrying(p.id);
    setNotice(null);
    try {
      const fresh = await draftJudgment(p.case_id);
      setNotice(fresh.status === 'failed'
        ? `案件 ${p.case_id} 重新起草仍失败: ${fresh.error_msg ?? '模型未返回'}`
        : `案件 ${p.case_id} 已重新起草, 新提案进入待审队列`);
      await load();
    } catch (e) {
      setError(`重试失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRetrying(null);
    }
  }, [load]);

  return (
    <section
      aria-label="AI 提案审批收件箱 (v0.8.6 M1 能力区块)"
      data-testid="approval-inbox"
      style={PANEL_SHELL}
    >
      <header className="flex flex-wrap items-center gap-2 mb-3">
        <span
          className="text-xs font-bold uppercase tracking-wider num"
          style={{ color: 'var(--sn-amber, var(--color-warning))' }}
        >
          审批收件箱
        </span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          HUMAN-IN-COMMAND · M1 · 待审 {drafts.length} · 失败 {failed.length}
        </span>
        <button
          type="button"
          className="text-xs ml-auto px-2 py-1 rounded focus-ring"
          style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink-3, var(--text-muted))' }}
          onClick={() => { void load(); }}
        >
          刷新
        </button>
      </header>

      {notice && (
        <p className="text-sm p-2 rounded mb-2" role="status"
          style={{ background: 'color-mix(in srgb, var(--color-info) 12%, transparent)', color: 'var(--sn-ink, var(--text-primary))' }}>
          {notice}
        </p>
      )}
      {error && (
        <p className="text-sm p-2 rounded" role="alert"
          style={{ background: 'color-mix(in srgb, var(--color-error) 12%, transparent)', color: 'var(--sn-red, var(--color-error))' }}>
          收件箱不可用 (unavailable): {error}
        </p>
      )}
      {loading && <p className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>加载中…</p>}

      {!loading && !error && drafts.length === 0 && failed.length === 0 && (
        <p className="text-sm" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          没有待审批的 AI 提案（Case 页点「AI 起草研判」后，草案出现在这里）。
        </p>
      )}

      {drafts.length > 0 && (
        <>
          <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
            待审 ({drafts.length})
          </h4>
          <ul className="grid grid-cols-1 lg:grid-cols-2 gap-2 mb-4">
            {drafts.map(p => <DraftCard key={p.id} p={p} onSettled={() => { void load(); }} />)}
          </ul>
        </>
      )}

      {failed.length > 0 && (
        <>
          <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
            失败 · 可重试 ({failed.length})
          </h4>
          <ul className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            {failed.map(p => (
              <li key={p.id} className="p-3 rounded border"
                style={{ borderColor: 'var(--sn-line, var(--line))' }}
                data-testid="approval-failed-card">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="gray">{KIND_LABEL[p.kind] ?? p.kind}</Badge>
                  {p.case_id && (
                    <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>{p.case_id}</span>
                  )}
                  <span className="text-xs ml-auto" style={{ color: 'var(--sn-red, var(--color-error))' }}>
                    模型未完成
                  </span>
                </div>
                <p className="text-xs mt-2 break-words" style={{ color: 'var(--sn-ink, var(--text-primary))' }}>
                  {p.error_msg || '(无错误信息)'}
                </p>
                <button
                  type="button"
                  className="text-xs mt-2 px-2.5 py-1 rounded font-medium focus-ring disabled:opacity-50"
                  disabled={!p.case_id || retrying !== null}
                  title={p.case_id ? '用原案件重新 AI 起草' : '该失败提案无案件锚点, 无法重试'}
                  onClick={() => { void retry(p); }}
                  style={{ border: '1px solid var(--sn-line, var(--line))', color: 'var(--sn-ink, var(--text-primary))' }}
                  data-testid="retry-btn"
                >
                  {retrying === p.id ? '重新起草中…' : '重试起草'}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
