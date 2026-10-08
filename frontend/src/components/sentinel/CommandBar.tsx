/**
 * CommandBar — Shell 常驻命令栏 (v0.8.6 P1-4, M4 轴④)。
 *
 * PRD 用例 B: 挂 masthead (四菜单右侧, "常驻四菜单顶部"), 零新路由 (NAV4)。
 * 固定四类意图模板 (查询/建案/出报告/执行), 本地规则路由; 结果卡:
 *  - query → 信号列表带 Source url (验收①);
 *  - create_case/report → proposal 已进审批收件箱 (验收②, 广播刷新事件);
 *  - unknown/execute → 显式可选动作, 不猜 (R5 教训)。
 * Esc 关闭结果面板; 结果面板 role=dialog (可访问性)。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  runCommand,
  type CommandResult,
} from '../../api/commands';
import { plainSummary } from '../../types';

/** 命令栏生成提案后广播 (ApprovalInbox 监听自刷新; CopilotCards 同模式)。 */
const PROPOSALS_CHANGED_EVENT = 'proposals:changed';

function ResultCard({ r, onClose }: { r: CommandResult; onClose: () => void }) {
  const isQuery = r.intent === 'query';
  return (
    <div
      className="cmd-result"
      role="dialog"
      aria-label="命令结果"
      data-testid="command-result"
    >
      <div className="flex items-center gap-2 mb-1">
        <span
          className="text-xs font-bold num"
          style={{ color: r.outcome === 'done' ? 'var(--color-success)'
            : r.outcome === 'error' ? 'var(--color-error)'
            : 'var(--sn-amber, var(--color-warning))' }}
        >
          {r.outcome === 'done' ? '✓ ' : r.outcome === 'error' ? '✗ ' : ''}
          {r.message}
        </span>
        <button
          type="button"
          className="ml-auto text-xs num focus-ring"
          style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}
          onClick={onClose}
          aria-label="关闭命令结果"
        >
          Esc
        </button>
      </div>

      {isQuery && (r.results?.length ?? 0) > 0 && (
        <ul className="max-h-64 overflow-y-auto flex flex-col gap-1">
          {r.results!.map(hit => (
            <li key={hit.signal_id} className="text-xs leading-snug">
              {hit.url ? (
                <a href={hit.url} target="_blank" rel="noopener noreferrer"
                  className="underline-offset-2 hover:underline"
                  style={{ color: 'var(--color-info)' }}>
                  {hit.title || hit.url}
                </a>
              ) : (
                <span style={{ color: 'var(--text-primary)' }}>{hit.title || hit.summary.slice(0, 40)}</span>
              )}
              {hit.confidence === 'hotspot' || hit.confidence === 'knowledge' ? (
                <span className="ml-1 text-[10px] font-mono px-1 rounded"
                  style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-muted)' }}>
                  {hit.confidence === 'hotspot' ? '热点' : '知识'}
                </span>
              ) : (
                <span className="num ml-1" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
                  {hit.occurred_at.slice(0, 10)}
                </span>
              )}
              <p className="line-clamp-2" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
                {plainSummary(hit.summary, 120)}
              </p>
            </li>
          ))}
        </ul>
      )}
      {isQuery && (r.results?.length ?? 0) === 0 && (
        <p className="text-xs" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          窗口内无命中信号
        </p>
      )}

      {(r.intent === 'create_case' || r.intent === 'report') && (
        <p className="text-xs num" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          {r.proposal_id} — 到「行动」菜单审批收件箱处理
        </p>
      )}

      {r.options && r.options.length > 0 && (
        <ul className="text-xs flex flex-col gap-0.5" style={{ color: 'var(--sn-ink-3, var(--text-muted))' }}>
          {r.options.map(o => <li key={o}>· {o}</li>)}
        </ul>
      )}
    </div>
  );
}

export function CommandBar() {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = useCallback(async () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runCommand(t);
      setResult(r);
      setText('');
      if (r.intent === 'create_case' || r.intent === 'report') {
        window.dispatchEvent(new Event(PROPOSALS_CHANGED_EVENT));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [text, busy]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setResult(null);
        setError(null);
      }
      // '/' 聚焦命令栏 (编辑框内不抢)
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT'
          && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="cmdbar" data-testid="command-bar">
      <input
        ref={inputRef}
        className="cmdbar-input num"
        value={text}
        placeholder="命令栏 — 查 信号 / 为 主题 建案 / 出 报告 (/ 聚焦)"
        aria-label="命令栏"
        disabled={busy}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { void submit(); } }}
      />
      <button
        type="button"
        className="cmdbar-go focus-ring"
        disabled={busy || !text.trim()}
        onClick={() => { void submit(); }}
        aria-label="执行命令"
      >
        {busy ? '…' : '↵'}
      </button>
      {error && (
        <p role="alert" data-testid="command-error" className="text-xs"
          style={{ color: 'var(--color-error)' }}>
          {error}
        </p>
      )}
      {result && <ResultCard r={result} onClose={() => setResult(null)} />}
    </div>
  );
}
