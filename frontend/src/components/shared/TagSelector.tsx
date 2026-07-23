import { useTags, type Tag } from '../../hooks/useTags';

/**
 * v1.7 Phase 1 — TagSelector 标签选择器 (AND/OR 模式)
 *
 * Props:
 *  - selected: 当前选中的 tag id 列表
 *  - mode:     当前模式 ("and" | "or")
 *  - onChange: (selected, mode) => void  选择/切换时回调
 *  - typeFilter: 可选, 仅显示某 type 的标签
 *
 * 行为:
 *  - 点击标签 toggle 选中状态
 *  - OR/AND 按钮切换模式 (验收 2: AND 过滤正常)
 *  - 选中标签高亮 (青色描边 + 发光, 与 tech 风格一致)
 */
export interface TagSelectorProps {
  selected: string[];
  mode: 'and' | 'or';
  onChange: (selected: string[], mode: 'and' | 'or') => void;
  typeFilter?: string;
}

export function TagSelector({
  selected,
  mode,
  onChange,
  typeFilter,
}: TagSelectorProps) {
  const { tags, loading, error } = useTags(typeFilter);

  const toggle = (id: string) => {
    const next = selected.includes(id)
      ? selected.filter((x) => x !== id)
      : [...selected, id];
    onChange(next, mode);
  };

  const switchMode = (m: 'and' | 'or') => {
    if (m !== mode) onChange(selected, m);
  };

  return (
    <div className="tag-selector" style={wrapperStyle}>
      <div className="tag-mode-toggle" style={toggleRowStyle}>
        <span style={labelStyle}>模式</span>
        <button
          type="button"
          style={mode === 'or' ? modeBtnActiveStyle : modeBtnStyle}
          onClick={() => switchMode('or')}
          aria-pressed={mode === 'or'}
        >
          OR
        </button>
        <button
          type="button"
          style={mode === 'and' ? modeBtnActiveStyle : modeBtnStyle}
          onClick={() => switchMode('and')}
          aria-pressed={mode === 'and'}
        >
          AND
        </button>
        <span style={hintStyle}>
          {mode === 'and' ? '需同时包含全部标签' : '包含任一标签即可'}
        </span>
      </div>

      {loading && <div style={statusStyle}>加载标签…</div>}
      {error && <div style={{ ...statusStyle, color: 'var(--color-security)' }}>{error}</div>}

      <div className="tag-list" style={listStyle}>
        {!loading &&
          tags.map((t: Tag) => {
            const active = selected.includes(t.id);
            return (
              <button
                key={t.id}
                type="button"
                style={active ? tagActiveStyle : tagStyle}
                onClick={() => toggle(t.id)}
                aria-pressed={active}
                title={`${t.type}${t.weight !== 1 ? ` · 权重 ${t.weight}` : ''}`}
              >
                {t.label}
              </button>
            );
          })}
        {!loading && tags.length === 0 && (
          <div style={statusStyle}>暂无标签</div>
        )}
      </div>

      {selected.length > 0 && (
        <div style={footerStyle}>
          已选 {selected.length} 个 · {mode.toUpperCase()}
          <button
            type="button"
            style={clearBtnStyle}
            onClick={() => onChange([], mode)}
          >
            清除
          </button>
        </div>
      )}
    </div>
  );
}

// ── styles (tech-style: 青色主调, 透明卡片, 发光描边) ───────────────
const wrapperStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2)',
  padding: 'var(--space-3)',
  border: '1px solid var(--color-ai, #00d4e0)',
  borderRadius: 'var(--radius-md)',
  background: 'rgba(0, 212, 224, 0.04)',
};

const toggleRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted, #888)',
  marginRight: 'var(--space-1)',
};

const modeBtnStyle: React.CSSProperties = {
  padding: '2px 10px',
  fontSize: 12,
  fontFamily: 'monospace',
  border: '1px solid var(--border-color, #333)',
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  color: 'var(--text-muted, #888)',
  cursor: 'pointer',
};

const modeBtnActiveStyle: React.CSSProperties = {
  ...modeBtnStyle,
  borderColor: 'var(--color-ai, #00d4e0)',
  color: 'var(--color-ai, #00d4e0)',
  boxShadow: '0 0 8px rgba(0, 212, 224, 0.4)',
};

const hintStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted, #666)',
  marginLeft: 'var(--space-2)',
};

const listStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 'var(--space-1)',
  maxHeight: 220,
  overflowY: 'auto',
};

const tagStyle: React.CSSProperties = {
  padding: '3px 10px',
  fontSize: 12,
  border: '1px solid var(--border-color, #333)',
  borderRadius: 'var(--radius-full)',
  background: 'transparent',
  color: 'var(--text-muted, #aaa)',
  cursor: 'pointer',
  transition: 'all 0.15s',
};

const tagActiveStyle: React.CSSProperties = {
  ...tagStyle,
  borderColor: 'var(--color-ai, #00d4e0)',
  color: 'var(--color-ai, #00d4e0)',
  background: 'rgba(0, 212, 224, 0.12)',
  boxShadow: '0 0 6px rgba(0, 212, 224, 0.5)',
};

const statusStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted, #888)',
  padding: 'var(--space-2)',
};

const footerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-3)',
  fontSize: 12,
  color: 'var(--text-muted, #888)',
  fontFamily: 'monospace',
};

const clearBtnStyle: React.CSSProperties = {
  marginLeft: 'auto',
  padding: '2px 8px',
  fontSize: 11,
  border: '1px solid var(--border-color, #333)',
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  color: 'var(--text-muted, #888)',
  cursor: 'pointer',
};

export default TagSelector;
