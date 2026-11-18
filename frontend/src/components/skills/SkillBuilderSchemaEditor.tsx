/**
 * SkillBuilderSchemaEditor — input/output schema 字段编辑器 (B5.6 拆分自 SkillBuilder)。
 *
 * 纯展示: 受控组件, 字段增删改一律通过 onChange 上抛 (草稿状态留在容器)。
 */
import { useMemo } from 'react';
import { PYTHON_TYPES } from './skillBuilderModel';

export function SkillBuilderSchemaEditor({
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
