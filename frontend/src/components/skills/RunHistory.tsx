/**
 * RunHistory — 运行历史回放列表 (v0.8 Phase B, Task B6)
 *
 * 数据面: GET /api/skill-registry/{skill_id}/runs?limit=20 (B6 后端路由,
 * SkillRunRepo.list_for_skill 时间倒序)。每条 run 可展开回放 inputs/result
 * 原始 JSON; 终态 run (succeeded/partial/failed) 行内挂 FeedbackBar 打分。
 * running 态不出现反馈条 (未结束的 run 不该被评分)。
 */
import { useState } from 'react';
import { useSkillRuns } from '../../hooks/useSkillRegistry';
import { SkillRun } from '../../types/skill';
import { FeedbackBar } from './FeedbackBar';

/** 终态集合 — 仅终态 run 显示反馈条 */
const TERMINAL_STATUSES = new Set(['succeeded', 'partial', 'failed']);

const STATUS_LABEL: Record<string, string> = {
  succeeded: '成功',
  partial: '部分成功',
  failed: '失败',
  running: '运行中',
};

const STATUS_COLOR: Record<string, string> = {
  succeeded: 'var(--mint)',
  partial: 'var(--amber)',
  failed: 'var(--red)',
  running: 'var(--color-info)',
};

/** metrics.elapsed_ms → 人话耗时 */
function fmtElapsed(ms: unknown): string | null {
  if (typeof ms !== 'number' || ms < 0) return null;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-mono uppercase mb-1" style={{ color: 'var(--ink-3)' }}>
        {label}
      </div>
      <pre
        className="text-[11.5px] font-mono whitespace-pre-wrap break-all rounded p-2 m-0"
        style={{ backgroundColor: 'var(--bg-lift)', color: 'var(--ink-2)' }}
      >
        {text}
      </pre>
    </div>
  );
}

function RunRow({ run }: { run: SkillRun }) {
  const [expanded, setExpanded] = useState(false);
  const statusColor = STATUS_COLOR[run.status] ?? 'var(--ink-3)';
  const elapsed = fmtElapsed(run.metrics?.elapsed_ms);
  const terminal = TERMINAL_STATUSES.has(run.status);

  return (
    <li
      className="rounded-md p-2.5 flex flex-col gap-2"
      style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
      data-testid={`run-row-${run.run_id}`}
    >
      {/* 摘要行 */}
      <div className="flex items-center gap-2 flex-wrap text-[12px]">
        <span
          className="px-1.5 py-0.5 rounded font-mono text-[11px]"
          style={{ color: statusColor, backgroundColor: 'var(--bg-hover)' }}
        >
          [{STATUS_LABEL[run.status] ?? run.status}]
        </span>
        <span className="font-mono" style={{ color: 'var(--ink-3)' }} title={run.run_id}>
          {run.run_id}
        </span>
        {run.ticket_id && (
          <span className="font-mono truncate max-w-[160px]" style={{ color: 'var(--ink-3)' }}>
            ticket {run.ticket_id}
          </span>
        )}
        {elapsed && (
          <span className="font-mono" style={{ color: 'var(--ink-3)' }}>
            {elapsed}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          {terminal && <FeedbackBar runId={run.run_id} />}
          <button
            type="button"
            aria-label={`回放 ${run.run_id}`}
            aria-expanded={expanded}
            onClick={() => setExpanded(e => !e)}
            className="h-6 px-2 rounded-md text-[11.5px] border"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
          >
            {expanded ? '收起' : '回放'}
          </button>
        </span>
      </div>

      {/* 时间行 */}
      <div className="text-[11px] font-mono" style={{ color: 'var(--ink-3)' }}>
        {run.created_at}
        {run.finished_at ? ` → ${run.finished_at}` : ''}
      </div>

      {run.error && (
        <div role="alert" className="text-[12px]" style={{ color: 'var(--red)' }}>
          {run.error}
        </div>
      )}

      {/* 回放面板: inputs / result 原始 JSON */}
      {expanded && (
        <div className="flex flex-col gap-2 pt-1 border-t" style={{ borderColor: 'var(--line)' }}>
          <JsonBlock label="inputs" value={run.inputs} />
          <JsonBlock label="result" value={run.result} />
          {!run.inputs && !run.result && (
            <div className="text-[12px]" style={{ color: 'var(--ink-3)' }}>
              该 run 无可回放数据
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function RunHistory({ skillId }: { skillId: string }) {
  const { runs, loading, error, refresh } = useSkillRuns(skillId);

  return (
    <section aria-label="运行历史" data-testid="run-history" className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-bold" style={{ color: 'var(--ink)' }}>
          运行历史
        </h2>
        <span className="text-[12px] font-mono" style={{ color: 'var(--ink-3)' }}>
          {loading ? '…' : `${runs.length} 条`}
        </span>
      </div>

      {loading && (
        <div role="status" className="py-6 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
          运行历史加载中…
        </div>
      )}
      {!loading && error && (
        <div role="alert" className="py-4 flex items-center gap-3" style={{ color: 'var(--red)' }}>
          <p className="text-sm m-0">{error}</p>
          <button
            type="button"
            onClick={refresh}
            className="h-7 px-3 rounded-md text-[12px] border"
            style={{ borderColor: 'var(--red)', color: 'var(--red)' }}
          >
            重试
          </button>
        </div>
      )}
      {!loading && !error && runs.length === 0 && (
        <div className="py-6 text-center text-sm" style={{ color: 'var(--ink-3)' }}>
          暂无执行记录
        </div>
      )}
      {!loading && !error && runs.length > 0 && (
        <ul className="flex flex-col gap-2 p-0 m-0 list-none">
          {runs.map(run => (
            <RunRow key={run.run_id} run={run} />
          ))}
        </ul>
      )}
    </section>
  );
}
