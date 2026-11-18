/**
 * SkillBuilderStep3Form — Step 3 Target 引用表单 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: target_module / target_class / target_method + dry-run validate 按钮。
 */
import type { DraftPayload } from './skillBuilderModel';

export function SkillBuilderStep3Form({
  draft,
  onUpdate,
  onDryRun,
}: {
  draft: DraftPayload;
  onUpdate: (patch: Partial<DraftPayload>) => void;
  onDryRun: () => void;
}) {
  return (
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
          onChange={e => onUpdate({ target_module: e.target.value })}
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
          onChange={e => onUpdate({ target_class: e.target.value })}
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
          onChange={e => onUpdate({ target_method: e.target.value })}
          placeholder="get_status"
          className="h-8 px-2 rounded border bg-transparent text-[13px] font-mono"
          style={{ borderColor: 'var(--line-strong)', color: 'var(--ink)' }}
        />
      </label>
      <button
        type="button"
        aria-label="dry-run validate"
        onClick={onDryRun}
        className="h-8 px-3 rounded text-[12px] border self-start"
        style={{ borderColor: 'var(--color-info)', color: 'var(--color-info)' }}
      >
        dry-run validate
      </button>
    </section>
  );
}
