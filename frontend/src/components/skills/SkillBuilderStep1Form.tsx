/**
 * SkillBuilderStep1Form — Step 1 基本信息表单 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: 全受控输入, 变更经 onUpdate 上抛 (草稿状态留在容器)。
 */
import { CATEGORY_LABELS, SKILL_TYPE_LABELS } from '../../types/skill';
import type { SkillCategory, SkillTypeCode } from '../../types/skill';
import type { DraftPayload } from './skillBuilderModel';

export function SkillBuilderStep1Form({
  draft,
  onUpdate,
}: {
  draft: DraftPayload;
  onUpdate: (patch: Partial<DraftPayload>) => void;
}) {
  return (
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
          onChange={e => onUpdate({ id: e.target.value })}
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
          onChange={e => onUpdate({ name: e.target.value })}
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
          onChange={e => onUpdate({ desc: e.target.value })}
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
            onChange={e => onUpdate({ category: e.target.value as SkillCategory })}
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
            onChange={e => onUpdate({ skill_type: e.target.value as SkillTypeCode })}
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
            onChange={e => onUpdate({ timeout_seconds: Number(e.target.value) })}
            className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono w-24"
            style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
          />
        </label>
      </div>
    </section>
  );
}
