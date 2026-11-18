/**
 * SkillBuilderNavBar — 向导底部步骤导航 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: 上一步 / 下一步 / 保存 三态由容器判定后下传 (步进状态留在容器)。
 */
import type { Step } from './skillBuilderModel';

export function SkillBuilderNavBar({
  step,
  canGoNext,
  submitting,
  onPrev,
  onNext,
  onSave,
}: {
  step: Step;
  /** 当前步是否满足进入下一步的条件 (Step 4 不适用)。 */
  canGoNext: boolean;
  submitting: boolean;
  onPrev: () => void;
  onNext: () => void;
  onSave: () => void;
}) {
  return (
    <div className="flex items-center justify-between mt-2">
      <button
        type="button"
        aria-label="上一步"
        onClick={onPrev}
        disabled={step === 1}
        className="h-8 px-3 rounded-md text-[13px] border disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
      >
        上一步
      </button>
      {step < 4 ? (
        <button
          type="button"
          aria-label="下一步"
          disabled={!canGoNext}
          onClick={onNext}
          className="h-8 px-3 rounded-md text-[13px] border disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--mint)', color: 'var(--mint)' }}
        >
          下一步
        </button>
      ) : (
        <button
          type="button"
          aria-label="保存"
          disabled={submitting}
          onClick={onSave}
          className="h-8 px-3 rounded-md text-[13px] border disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--mint)', color: 'var(--mint)' }}
        >
          {submitting ? '提交中…' : '保存'}
        </button>
      )}
    </div>
  );
}
