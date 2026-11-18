/**
 * SkillBuilderStep2Form — Step 2 Schema 与 Prompt 表单 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: schema 编辑器 + C/D 类 prompt 模板 (草稿状态留在容器)。
 */
import { SkillBuilderSchemaEditor } from './SkillBuilderSchemaEditor';
import type { DraftPayload } from './skillBuilderModel';

export function SkillBuilderStep2Form({
  draft,
  onUpdate,
}: {
  draft: DraftPayload;
  onUpdate: (patch: Partial<DraftPayload>) => void;
}) {
  return (
    <section
      aria-label="步骤 2 Schema 与 Prompt"
      className="rounded-md p-4 flex flex-col gap-3"
      style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--line)' }}
    >
      <SkillBuilderSchemaEditor
        label="input_schema"
        value={draft.input_schema}
        onChange={v => onUpdate({ input_schema: v })}
      />
      <SkillBuilderSchemaEditor
        label="output_schema"
        value={draft.output_schema}
        onChange={v => onUpdate({ output_schema: v })}
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
            onChange={e => onUpdate({ prompt_template: e.target.value })}
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
  );
}
