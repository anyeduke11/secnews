/**
 * CopilotCards — 行动层「全界面 AI 副驾」四卡区块 (v0.8.6 P1-3, M3 轴③)。
 *
 * PRD §3.2 M3 四卡 → proposal 通道映射 (全部人审后生效, 草案进下方审批收件箱):
 *  - 情报流研判建议卡 → judgment_draft  (POST /draft-judgment, case 锚)
 *  - 知识自动摘要卡   → knowledge_draft (POST /copilot-draft, knowledge 锚)
 *  - 案件证据召回卡   → case_suggestion (POST /copilot-draft, case 锚)
 *  - SK-04 复盘草案卡 → report          (POST /copilot-draft, case 锚)
 *
 * 纪律: 页内区块, 不新增路由 (NAV4 四菜单); 单卡 busy/错误隔离;
 * 成功后广播 proposals:changed, 审批收件箱监听自刷新 (组件间零耦合)。
 */
import { useState } from 'react';
import {
  copilotDraft,
  draftJudgment,
  type CopilotDraftKind,
} from '../../api/proposals';
import { PANEL_SHELL } from '../v1/panels/panelShell';

/** 起草成功事件 — ApprovalInbox 监听刷新 (同页区块解耦刷新)。 */
export const PROPOSALS_CHANGED_EVENT = 'proposals:changed';

interface CardSpec {
  kind: string;
  title: string;
  hint: string;
  inputKey: 'case_id' | 'knowledge_id';
  placeholder: string;
}

const CARDS: CardSpec[] = [
  {
    kind: 'judgment_draft', title: '研判建议', inputKey: 'case_id',
    hint: '按案件证据起草研判 → 收件箱审批后落产物',
    placeholder: '案件 ID (case_…)',
  },
  {
    kind: 'knowledge_draft', title: '知识摘要', inputKey: 'knowledge_id',
    hint: '把资讯条目摘要成知识草案 → 审批后入产物',
    placeholder: '条目 ID (kl-…)',
  },
  {
    kind: 'case_suggestion', title: '证据召回 · 建案', inputKey: 'case_id',
    hint: '召回案件证据起草建案建议 → 审批后落产物',
    placeholder: '案件 ID (case_…)',
  },
  {
    kind: 'report', title: '复盘草案 (SK-04)', inputKey: 'case_id',
    hint: '从案件证据与结论起草复盘 → 审批后落产物',
    placeholder: '案件 ID (case_…)',
  },
];

interface CardState {
  value: string;
  busy: boolean;
  error: string | null;
  ok: string | null;
}

const IDLE: CardState = { value: '', busy: false, error: null, ok: null };

function CopilotCard({ spec }: { spec: CardSpec }) {
  const [st, setSt] = useState<CardState>(IDLE);

  const draft = async () => {
    const id = st.value.trim();
    if (!id) return;
    setSt(s => ({ ...s, busy: true, error: null, ok: null }));
    try {
      const proposal = spec.kind === 'judgment_draft'
        ? await draftJudgment(id)
        : await copilotDraft(spec.kind as CopilotDraftKind,
            spec.inputKey === 'knowledge_id'
              ? { knowledge_id: id } : { case_id: id });
      if (proposal.status === 'failed') {
        setSt(s => ({
          ...s, busy: false,
          error: `起草失败: ${proposal.error_msg || '模型未返回'} — 可在审批收件箱查看`,
        }));
        return;
      }
      window.dispatchEvent(new Event(PROPOSALS_CHANGED_EVENT));
      setSt(s => ({
        ...s, busy: false, value: '',
        ok: '草案已送审批收件箱 — 人批准后生成产物',
      }));
    } catch (e) {
      setSt(s => ({
        ...s, busy: false,
        error: `起草失败: ${e instanceof Error ? e.message : String(e)}`,
      }));
    }
  };

  return (
    <div
      className="p-3 rounded border flex flex-col gap-2"
      style={{ borderColor: 'var(--sn-line, var(--line))' }}
      data-testid={`copilot-card-${spec.kind}`}
    >
      <div className="flex items-center gap-2">
        <span
          className="text-xs font-bold num"
          style={{ color: 'var(--sn-mint, var(--color-info))' }}
        >
          {spec.title}
        </span>
        <span
          className="text-xs num ml-auto"
          style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}
        >
          PROPOSAL
        </span>
      </div>
      <p className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
        {spec.hint}
      </p>
      <div className="flex gap-2">
        <input
          className="flex-1 min-w-0 px-2 py-1 rounded border text-xs num"
          value={st.value}
          placeholder={spec.placeholder}
          aria-label={`${spec.title}锚点 ID`}
          onChange={e => setSt(s => ({ ...s, value: e.target.value }))}
          onKeyDown={e => { if (e.key === 'Enter' && !st.busy) { void draft(); } }}
          style={{
            background: 'transparent',
            color: 'var(--sn-ink, var(--text-primary))',
            borderColor: 'var(--sn-line, var(--line))',
          }}
        />
        <button
          type="button"
          className="text-xs px-2.5 py-1 rounded font-medium focus-ring disabled:opacity-50 whitespace-nowrap"
          disabled={st.busy || !st.value.trim()}
          onClick={() => { void draft(); }}
          style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
          data-testid={`copilot-draft-btn-${spec.kind}`}
        >
          {st.busy ? '起草中…' : 'AI 起草'}
        </button>
      </div>
      {st.ok && (
        <p className="text-xs" role="status" data-testid={`copilot-ok-${spec.kind}`}
          style={{ color: 'var(--color-success)' }}>
          {st.ok}
        </p>
      )}
      {st.error && (
        <p className="text-xs break-words" role="alert" data-testid={`copilot-err-${spec.kind}`}
          style={{ color: 'var(--sn-red, var(--color-error))' }}>
          {st.error}
        </p>
      )}
    </div>
  );
}

export function CopilotCards() {
  return (
    <section
      aria-label="AI 副驾四卡 (v0.8.6 M3 能力区块, 全部走提案通道)"
      data-testid="copilot-cards"
      style={PANEL_SHELL}
    >
      <header className="flex flex-wrap items-center gap-2 mb-3">
        <span
          className="text-xs font-bold uppercase tracking-wider num"
          style={{ color: 'var(--sn-mint, var(--color-info))' }}
        >
          AI 副驾
        </span>
        <span className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          COPILOT · 四卡全部走提案通道, 人审后生效
        </span>
      </header>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2">
        {CARDS.map(c => <CopilotCard key={c.kind} spec={c} />)}
      </div>
    </section>
  );
}
