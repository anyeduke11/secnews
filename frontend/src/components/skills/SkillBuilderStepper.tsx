/**
 * SkillBuilderStepper — 4 步向导的步进指示条 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: 只按当前步渲染 4 个步骤头, 不持有任何向导状态。
 */
import { STEP_TITLES } from './skillBuilderModel';
import type { Step } from './skillBuilderModel';

function StepHeader({ step, current }: { step: Step; current: Step }) {
  const active = step <= current;
  return (
    <div className="flex items-center gap-2 mb-3" data-testid={`wizard-step-${step}`}>
      <span
        className="inline-flex items-center justify-center w-6 h-6 rounded-full text-[12px] font-bold"
        style={{
          backgroundColor: active ? 'var(--mint)' : 'var(--bg-hover)',
          color: active ? 'var(--bg-card)' : 'var(--ink-3)',
        }}
      >
        {step}
      </span>
      <span
        className="text-[13px] font-medium"
        style={{ color: active ? 'var(--ink)' : 'var(--ink-3)' }}
      >
        {STEP_TITLES[step]}
      </span>
    </div>
  );
}

/** 步进条: 4 个步骤头 (data-testid = wizard-step-N)。 */
export function SkillBuilderStepper({ current }: { current: Step }) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <StepHeader step={1} current={current} />
      <StepHeader step={2} current={current} />
      <StepHeader step={3} current={current} />
      <StepHeader step={4} current={current} />
    </div>
  );
}
