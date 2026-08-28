import { useMemo } from 'react';

export interface FrameworkOption {
  id: string;
  name: string;
}

interface FrameworkFilterProps {
  frameworks: FrameworkOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

export function FrameworkFilter({ frameworks, selected, onChange }: FrameworkFilterProps) {
  const toggle = useMemo(() => {
    return (id: string) => {
      if (selected.includes(id)) {
        onChange(selected.filter(f => f !== id));
      } else {
        onChange([...selected, id]);
      }
    };
  }, [selected, onChange]);

  if (!frameworks.length) return null;

  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {frameworks.map(fw => {
        const active = selected.includes(fw.id);
        return (
          <button
            key={fw.id}
            onClick={() => toggle(fw.id)}
            className="px-3 py-1.5 text-xs font-mono rounded-[var(--radius-sm)] border transition-colors"
            style={{
              borderColor: active ? 'var(--accent)' : 'var(--border-color)',
              backgroundColor: active ? 'var(--accent-soft)' : 'transparent',
              color: active ? 'var(--accent)' : 'var(--text-secondary)',
              fontWeight: active ? 600 : 400,
            }}
          >
            {fw.name}
          </button>
        );
      })}
    </div>
  );
}
