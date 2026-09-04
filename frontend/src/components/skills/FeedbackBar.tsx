/**
 * FeedbackBar — 单条 run 的 👍/👎 反馈条 (v0.8 Phase B, Task B6)
 *
 * 数据面: POST /api/skill-registry/runs/{run_id}/feedback (B6 后端路由)。
 * 👍 → score=5, 👎 → score=1 (后端 1-5 语义映射); 成功写 feedback_log,
 * 经 agent_memory.recall 即可命中 (B6 验收链路)。
 * 提交成功后锁定为已反馈态, 不允许重复打分。
 */
import { useState } from 'react';
import { postJSON } from '../../lib/api';
import { SkillFeedback } from '../../types/skill';

interface FeedbackBarProps {
  runId: string;
  /** 提交成功后通知父级 (如刷新历史) */
  onDone?: (score: number) => void;
}

export function FeedbackBar({ runId, onDone }: FeedbackBarProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (score: number) => {
    if (submitting || submitted !== null) return;
    setSubmitting(true);
    setError(null);
    try {
      await postJSON<SkillFeedback>(
        `/api/skill-registry/runs/${encodeURIComponent(runId)}/feedback`,
        { score, comment: '' }
      );
      setSubmitted(score);
      onDone?.(score);
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : '反馈提交失败';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted !== null) {
    return (
      <span
        data-testid={`feedback-done-${runId}`}
        role="status"
        className="text-[12px] font-medium"
        style={{ color: 'var(--mint)' }}
      >
        {submitted === 5 ? '已反馈 👍' : '已反馈 👎'}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5" data-testid={`feedback-bar-${runId}`}>
      <button
        type="button"
        aria-label={`好评 ${runId}`}
        disabled={submitting}
        onClick={() => submit(5)}
        className="h-6 px-1.5 rounded text-[13px] border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ borderColor: 'var(--mint)', color: 'var(--mint)' }}
        title="好评 (score 5)"
      >
        👍
      </button>
      <button
        type="button"
        aria-label={`差评 ${runId}`}
        disabled={submitting}
        onClick={() => submit(1)}
        className="h-6 px-1.5 rounded text-[13px] border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ borderColor: 'var(--red)', color: 'var(--red)' }}
        title="差评 (score 1)"
      >
        👎
      </button>
      {submitting && (
        <span className="text-[12px]" style={{ color: 'var(--ink-3)' }}>
          提交中…
        </span>
      )}
      {error && (
        <span role="alert" className="text-[12px]" style={{ color: 'var(--red)' }}>
          {error}
        </span>
      )}
    </span>
  );
}
