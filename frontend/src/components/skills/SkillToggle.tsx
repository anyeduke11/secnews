/**
 * SkillToggle — 技能启停开关 (v0.8 Phase A)
 *
 * 哨兵 V2 风格: [ON] mint / [OFF] 灰 (ink-3), 等宽数字, hairline 边框。
 * 二次确认沿用仓库既有 window.confirm 模式 (SkillCard/SecretsPage 先例),
 * 仅启用方向需要确认, 停用即时生效; busy (请求在途) 时禁用。
 */
interface SkillToggleProps {
  enabled: boolean;
  /** 请求在途时禁用 (来自 useSkillToggle().busy) */
  busy?: boolean;
  /** 技能名, 用于确认弹窗文案 */
  label?: string;
  /** 确认通过后回调, 携带目标状态 */
  onToggle: (next: boolean) => void;
}

export function SkillToggle({ enabled, busy = false, label, onToggle }: SkillToggleProps) {
  const name = label ?? '该技能';

  const handleClick = () => {
    if (busy) return;
    if (!enabled && !window.confirm(`启用技能「${name}」？`)) return;
    onToggle(!enabled);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={`${enabled ? '停用' : '启用'}技能 ${name}`}
      aria-disabled={busy || undefined}
      disabled={busy}
      onClick={handleClick}
      className="inline-flex items-center gap-1.5 h-6 px-2 rounded-md font-mono text-[11px] font-medium tracking-wide border transition-colors"
      style={{
        borderColor: enabled ? 'var(--mint)' : 'var(--line-strong)',
        color: enabled ? 'var(--mint)' : 'var(--ink-3)',
        backgroundColor: enabled ? 'var(--bg-hover)' : 'transparent',
        cursor: busy ? 'not-allowed' : 'pointer',
      }}
    >
      {/* 指示点: ON mint 实心 / OFF 灰空心 */}
      <span
        aria-hidden="true"
        className="w-1.5 h-1.5 rounded-full"
        style={{
          backgroundColor: enabled ? 'var(--mint)' : 'transparent',
          boxShadow: enabled ? 'none' : 'inset 0 0 0 1.5px var(--ink-3)',
        }}
      />
      {enabled ? 'ON' : 'OFF'}
    </button>
  );
}
