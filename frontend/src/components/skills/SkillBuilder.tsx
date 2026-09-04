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
 */
import { useMemo, useState } from 'react';
import { postJSON } from '../../lib/api';
import {
  CATEGORY_LABELS,
  SkillCategory,
  SKILL_TYPE_LABELS,
  SkillTypeCode,
} from '../../types/skill';

const PYTHON_TYPES = ['str', 'int', 'float', 'bool', 'list', 'dict', 'Any'];

interface DraftPayload {
  id: string;
  name: string;
  desc: string;
  category: SkillCategory;
  skill_type: SkillTypeCode;
  runner: 'builtin';
  timeout_seconds: number;
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  prompt_template: string;
  target_module: string;
  target_class: string;
  target_method: string;
}

const EMPTY_DRAFT: DraftPayload = {
  id: '',
  name: '',
  desc: '',
  category: 'operations',
  skill_type: 'A',
  runner: 'builtin',
  timeout_seconds: 60,
  input_schema: {},
  output_schema: {},
  prompt_template: '',
  target_module: '',
  target_class: '',
  target_method: '',
};

type Step = 1 | 2 | 3 | 4;

function StepHeader({ step, current }: { step: Step; current: Step }) {
  const titles: Record<Step, string> = {
    1: '基本信息',
    2: 'Schema 与 Prompt',
    3: 'Target 引用',
    4: '复核 & 保存',
  };
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
        {titles[step]}
      </span>
    </div>
  );
}

function SchemaEditor({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const fields = useMemo(() => {
    return Object.entries(value).map(([name, type]) => ({ name, type }));
  }, [value]);

  const add = () => onChange({ ...value, [`field_${fields.length + 1}`]: 'str' });
  const remove = (k: string) => {
    const next = { ...value };
    delete next[k];
    onChange(next);
  };
  const update = (k: string, k2: string, t: string) => {
    const next: Record<string, string> = {};
    for (const [kk, vv] of Object.entries(value)) {
      next[kk === k ? k2 : kk] = kk === k ? t : vv;
    }
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
        {label}
      </div>
      {fields.map(f => (
        <div key={f.name} className="flex items-center gap-1.5">
          <input
            aria-label={`${label}-field-name`}
            data-testid={`${label}-field-name`}
            type="text"
            value={f.name}
            onChange={e => update(f.name, e.target.value, f.type)}
            className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono flex-1"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
          />
          <select
            aria-label={`${label}-field-type`}
            data-testid={`${label}-field-type`}
            value={f.type}
            onChange={e => update(f.name, f.name, e.target.value)}
            className="h-8 px-2 rounded border text-[13px] font-mono"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
          >
            {PYTHON_TYPES.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <button
            type="button"
            aria-label={`remove-field-${f.name}`}
            data-testid={`remove-field-${f.name}`}
            onClick={() => remove(f.name)}
            className="h-8 px-2 rounded text-[12px] border"
            style={{ borderColor: 'var(--red)', color: 'var(--red)' }}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        aria-label={`${label}-add`}
        data-testid={`${label}-add`}
        onClick={add}
        className="h-8 px-3 rounded text-[12px] border self-start"
        style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-2)' }}
      >
        + 添加字段
      </button>
    </div>
  );
}

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

  const step1Valid = draft.id.length >= 3 && draft.name.length > 0;
  const step2Valid = draft.skill_type !== 'A' ? draft.prompt_template.length > 0 : true;
  const step3Valid =
    draft.target_module.length > 0 && draft.target_method.length > 0;

  const dryRunValidate = async (): Promise<boolean> => {
    setErrors([]);
    try {
      const resp = await postJSON<{ ok: boolean; errors: string[] }>(
        '/api/skill-builder/validate',
        { payload: draft }
      );
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
      const resp = await postJSON<{ id: string }>(
        '/api/skill-builder',
        draft
      );
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
      <div className="flex items-center gap-3 flex-wrap">
        <StepHeader step={1} current={step} />
        <StepHeader step={2} current={step} />
        <StepHeader step={3} current={step} />
        <StepHeader step={4} current={step} />
      </div>

      {/* Step 1: 基本信息 */}
      {step === 1 && (
        <section
          aria-label="步骤 1 基本信息"
          className="rounded-md p-4 flex flex-col gap-3"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
        >
          <label htmlFor="skill-builder-id" className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              id (snake/kebab-case, 不可与 builtin 冲突)
            </span>
            <input
              id="skill-builder-id"
              aria-label="skill id"
              type="text"
              value={draft.id}
              onChange={e => update({ id: e.target.value })}
              placeholder="my-custom-skill"
              className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <label htmlFor="skill-builder-name" className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              显示名
            </span>
            <input
              id="skill-builder-name"
              aria-label="skill 显示名"
              type="text"
              value={draft.name}
              onChange={e => update({ name: e.target.value })}
              className="h-8 px-2 rounded border bg-transparent text-[13px]"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <label htmlFor="skill-builder-desc" className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              描述
            </span>
            <textarea
              id="skill-builder-desc"
              aria-label="skill 描述"
              value={draft.desc}
              onChange={e => update({ desc: e.target.value })}
              rows={3}
              className="px-2 py-1.5 rounded border bg-transparent text-[13px] leading-relaxed"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <div className="flex items-center gap-3">
            <label htmlFor="skill-builder-category" className="flex flex-col gap-1">
              <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
                类别
              </span>
              <select
                id="skill-builder-category"
                aria-label="类别"
                value={draft.category}
                onChange={e => update({ category: e.target.value as SkillCategory })}
                className="h-8 px-2 rounded border text-[13px]"
                style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
              >
                {(Object.keys(CATEGORY_LABELS) as SkillCategory[]).map(c => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="skill-builder-type" className="flex flex-col gap-1">
              <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
                类型 (A 巡检 / B 查询 / C 报告 / D 分析)
              </span>
              <select
                id="skill-builder-type"
                aria-label="类型"
                value={draft.skill_type}
                onChange={e => update({ skill_type: e.target.value as SkillTypeCode })}
                className="h-8 px-2 rounded border text-[13px]"
                style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
              >
                {(Object.keys(SKILL_TYPE_LABELS) as SkillTypeCode[]).map(t => (
                  <option key={t} value={t}>
                    {`${t} ${SKILL_TYPE_LABELS[t]}`}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="skill-builder-timeout" className="flex flex-col gap-1">
              <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
                超时 (秒)
              </span>
              <input
                id="skill-builder-timeout"
                aria-label="超时"
                type="number"
                min={1}
                max={3600}
                value={draft.timeout_seconds}
                onChange={e => update({ timeout_seconds: Number(e.target.value) })}
                className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono w-24"
                style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
              />
            </label>
          </div>
        </section>
      )}

      {/* Step 2: Schema + Prompt */}
      {step === 2 && (
        <section
          aria-label="步骤 2 Schema 与 Prompt"
          className="rounded-md p-4 flex flex-col gap-3"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
        >
          <SchemaEditor
            label="input_schema"
            value={draft.input_schema}
            onChange={v => update({ input_schema: v })}
          />
          <SchemaEditor
            label="output_schema"
            value={draft.output_schema}
            onChange={v => update({ output_schema: v })}
          />
          {(draft.skill_type === 'C' || draft.skill_type === 'D') && (
            <label className="flex flex-col gap-1">
              <span
                className="text-[12px] font-mono uppercase"
                style={{ color: 'var(--ink-3)' }}
              >
                prompt_template (C/D 类必填, 支持 {'{{ input.x }}'} 占位)
              </span>
              <textarea
                aria-label="prompt 模板"
                value={draft.prompt_template}
                onChange={e => update({ prompt_template: e.target.value })}
                rows={5}
                placeholder={'例: 基于 {{ input.topic }} 生成 5 条要点'}
                className="px-2 py-1.5 rounded border bg-transparent text-[13px] font-mono leading-relaxed"
                style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
              />
            </label>
          )}
          {draft.skill_type === 'A' && (
            <p className="text-[12px]" style={{ color: 'var(--ink-3)' }}>
              A 类巡检无需 prompt_template（按 R1 纪律 3）
            </p>
          )}
        </section>
      )}

      {/* Step 3: Target */}
      {step === 3 && (
        <section
          aria-label="步骤 3 Target 引用"
          className="rounded-md p-4 flex flex-col gap-3"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              target_module (Python module path)
            </span>
            <input
              aria-label="target_module"
              type="text"
              value={draft.target_module}
              onChange={e => update({ target_module: e.target.value })}
              placeholder="backend.services.source_scheduler_service"
              className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              target_class (可空, 模块级函数时省略)
            </span>
            <input
              aria-label="target_class"
              type="text"
              value={draft.target_class}
              onChange={e => update({ target_class: e.target.value })}
              placeholder="SourceSchedulerService"
              className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-mono uppercase" style={{ color: 'var(--ink-3)' }}>
              target_method
            </span>
            <input
              aria-label="target_method"
              type="text"
              value={draft.target_method}
              onChange={e => update({ target_method: e.target.value })}
              placeholder="get_status"
              className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
            />
          </label>
          <button
            type="button"
            aria-label="dry-run validate"
            onClick={() => dryRunValidate()}
            className="h-8 px-3 rounded text-[12px] border self-start"
            style={{ borderColor: 'var(--color-info)', color: 'var(--color-info)' }}
          >
            dry-run validate
          </button>
        </section>
      )}

      {/* Step 4: 复核 */}
      {step === 4 && (
        <section
          aria-label="步骤 4 复核"
          className="rounded-md p-4 flex flex-col gap-2"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
        >
          <pre
            data-testid="skill-builder-yaml-preview"
            className="text-[12px] font-mono whitespace-pre-wrap break-all rounded p-3"
            style={{ backgroundColor: 'var(--bg-lift)', color: 'var(--ink-2)' }}
          >
            {JSON.stringify(draft, null, 2)}
          </pre>
        </section>
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
      <div className="flex items-center justify-between mt-2">
        <button
          type="button"
          aria-label="上一步"
          onClick={() => setStep((s => (s > 1 ? ((s - 1) as Step) : s))(step))}
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
            disabled={
              (step === 1 && !step1Valid) ||
              (step === 2 && !step2Valid) ||
              (step === 3 && !step3Valid)
            }
            onClick={() => setStep(((s) => (s + 1) as Step)(step))}
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
            onClick={submit}
            className="h-8 px-3 rounded-md text-[13px] border disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ borderColor: 'var(--mint)', color: 'var(--mint)' }}
          >
            {submitting ? '提交中…' : '保存'}
          </button>
        )}
      </div>
    </div>
  );
}