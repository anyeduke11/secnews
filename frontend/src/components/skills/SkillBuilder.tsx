/**
 * SkillBuilder — v0.8 Phase C C4 用户自建 Skill 4 步向导 (UI).
 *
 * 数据面: /api/skill-builder/* (C3 backend, P3-2 错误信封 {detail: {message, code, hint}}).
 *
 * 4 步向导 (按 spec tasks C4.1):
 *   1. 基本信息 (id / name / desc / category / skill_type)
 *   2. Schema (input/output 字段定义 + C/D 类 prompt 模板)
 *   3. Target (target_module / target_class / target_method 引用, 走 dry-run validate)
 *   4. 复核 + 保存 (POST /api/skill-builder, 默认 enabled=0, 用户启用走 PATCH)
 *
 * 复用 skill 卡同类 V2 sentinel 风格: hairline border + bg-card + 类别色条;
 * 文案硬编码中文 (i18n 接入为 D3 任务).
 *
 * B5.6 拆分: 容器只保留步进状态 / 草稿状态 / 提交与 dry-run 编排;
 * 纯类型与校验 → skillBuilderModel.ts, 展示区块 → SkillBuilderStepper /
 * SkillBuilderStep1Form~Step4Form / SkillBuilderSchemaEditor / SkillBuilderNavBar。
 */
import { useState } from 'react';
import { createSkill, validateSkillDraft } from '../../api/skills';
import { SkillBuilderNavBar } from './SkillBuilderNavBar';
import { SkillBuilderStep1Form } from './SkillBuilderStep1Form';
import { SkillBuilderStep2Form } from './SkillBuilderStep2Form';
import { SkillBuilderStep3Form } from './SkillBuilderStep3Form';
import { SkillBuilderStep4Form } from './SkillBuilderStep4Form';
import { SkillBuilderStepper } from './SkillBuilderStepper';
import {
  EMPTY_DRAFT,
  isStep1Valid,
  isStep2Valid,
  isStep3Valid,
} from './skillBuilderModel';
import type { DraftPayload, Step } from './skillBuilderModel';

export function SkillBuilder({ onBack, onCreated }: {
  onBack?: () => void;
  onCreated?: (skillId: string) => void;
}) {
  const [step, setStep] = useState<Step>(1);
  const [draft, setDraft] = useState<DraftPayload>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const update = (patch: Partial<DraftPayload>) =>
    setDraft(d => ({ ...d, ...patch }));

  const step1Valid = isStep1Valid(draft);
  const step2Valid = isStep2Valid(draft);
  const step3Valid = isStep3Valid(draft);
  const nextDisabled =
    (step === 1 && !step1Valid) ||
    (step === 2 && !step2Valid) ||
    (step === 3 && !step3Valid);

  const dryRunValidate = async (): Promise<boolean> => {
    setErrors([]);
    try {
      const resp = await validateSkillDraft(draft);
      if (!resp.ok) {
        setErrors(resp.errors);
        return false;
      }
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'validate 失败';
      setErrors([msg]);
      return false;
    }
  };

  const submit = async () => {
    setSubmitting(true);
    setErrors([]);
    try {
      const resp = await createSkill(draft);
      setNotice(`已创建 skill ${resp.id}（未启用，到列表里手动开启）`);
      onCreated?.(resp.id);
    } catch (e) {
      const raw = e instanceof Error ? e.message : '提交失败';
      // 后端 detail.message 已被 apiFetch/postJSON 提取; 保留全文便于排错
      setErrors([raw]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-[800px] mx-auto w-full">
      {/* 页头 */}
      <header className="flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            aria-label="返回"
            className="h-8 px-2.5 rounded-md text-sm border"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
          >
            ←
          </button>
        )}
        <h1 className="text-lg font-bold" style={{ color: 'var(--ink)' }}>
          新建 Skill
        </h1>
      </header>

      {/* 步进指示 */}
      <SkillBuilderStepper current={step} />

      {/* Step 1: 基本信息 */}
      {step === 1 && (
        <SkillBuilderStep1Form draft={draft} onUpdate={update} />
      )}

      {/* Step 2: Schema + Prompt */}
      {step === 2 && (
        <SkillBuilderStep2Form draft={draft} onUpdate={update} />
      )}

      {/* Step 3: Target */}
      {step === 3 && (
        <SkillBuilderStep3Form
          draft={draft}
          onUpdate={update}
          onDryRun={() => dryRunValidate()}
        />
      )}

      {/* Step 4: 复核 */}
      {step === 4 && (
        <SkillBuilderStep4Form draft={draft} />
      )}

      {/* 错误提示 */}
      {errors.length > 0 && (
        <div
          role="alert"
          data-testid="skill-builder-errors"
          className="rounded-md px-3 py-2 text-[13px] border"
          style={{
            color: 'var(--red)',
            borderColor: 'var(--red)',
            backgroundColor: 'var(--bg-lift)',
          }}
        >
          {errors.join('; ')}
        </div>
      )}

      {notice && (
        <div
          role="status"
          className="rounded-md px-3 py-2 text-[13px] border"
          style={{
            color: 'var(--mint)',
            borderColor: 'var(--mint)',
            backgroundColor: 'var(--bg-lift)',
          }}
        >
          {notice}
        </div>
      )}

      {/* 步骤导航 */}
      <SkillBuilderNavBar
        step={step}
        canGoNext={!nextDisabled}
        submitting={submitting}
        onPrev={() => setStep((s => (s > 1 ? ((s - 1) as Step) : s))(step))}
        onNext={() => setStep(((s) => (s + 1) as Step)(step))}
        onSave={submit}
      />
    </div>
  );
}
