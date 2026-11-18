/**
 * SkillBuilderStep4Form — Step 4 复核区 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: 草稿 JSON 预览 (data-testid = skill-builder-yaml-preview)。
 */
import type { DraftPayload } from './skillBuilderModel';

export function SkillBuilderStep4Form({ draft }: { draft: DraftPayload }) {
  return (
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
  );
}
