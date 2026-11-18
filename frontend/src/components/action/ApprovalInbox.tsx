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
 *
 * B5 (2026-11-18) 绞杀者拆分: 原 449 行单文件按区块拆为 action/ 下 4 个文件
 * (approvalModel / ApprovalBadge / ApprovalDraftCard / ApprovalFailedList),
 * 本文件只保留取数、事件监听、重试编排与区块组合; DOM / class / data-testid 逐字一致。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  copilotDraft,
  draftJudgment,
  listProposals,
  type CopilotDraftKind,
  type Proposal,
} from '../../api/proposals';
import { PANEL_SHELL } from '../v1/panels/panelShell';
import { ApprovalDraftCard } from './ApprovalDraftCard';
import { ApprovalFailedList } from './ApprovalFailedList';

/** CopilotCards 起草成功后广播; 收件箱监听自刷新 (同页区块解耦)。 */
const PROPOSALS_CHANGED_EVENT = 'proposals:changed';

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

  // CopilotCards 起草成功 → 收件箱自刷新 (跨区块解耦, 不经父组件)
  useEffect(() => {
    const onChange = () => { void load(); };
    window.addEventListener(PROPOSALS_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(PROPOSALS_CHANGED_EVENT, onChange);
  }, [load]);

  /** 失败提案重试 (kind 感知): judgment → draft-judgment;
   * case 锚定的副驾 kind → copilot-draft 同 kind;
   * knowledge_draft 无重试锚点 (case_id 为空) → 按钮禁用。 */
  const retry = useCallback(async (p: Proposal) => {
    if (!p.case_id) return;
    setRetrying(p.id);
    setNotice(null);
    try {
      const fresh = p.kind === 'judgment_draft'
        ? await draftJudgment(p.case_id)
        : await copilotDraft(p.kind as CopilotDraftKind, { case_id: p.case_id });
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
            {drafts.map(p => <ApprovalDraftCard key={p.id} p={p} onSettled={() => { void load(); }} />)}
          </ul>
        </>
      )}

      {failed.length > 0 && (
        <ApprovalFailedList failed={failed} retrying={retrying} onRetry={p => { void retry(p); }} />
      )}
    </section>
  );
}
