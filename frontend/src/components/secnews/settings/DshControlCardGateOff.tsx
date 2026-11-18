/**
 * DshControlCardGateOff — dsh feature gate 关闭时的提示卡
 * (从 DshControlCard.tsx 机械拆分, JSX/className/文案零变更, 状态仍由父组件持有)
 */
import type { TFn } from './dshControlCard.types';

interface DshControlCardGateOffProps {
  t: TFn;
}

export function DshControlCardGateOff({ t }: DshControlCardGateOffProps) {
  return (
    <div
      style={{
        padding: 'var(--sn-cell-pad)',
        borderRadius: 'var(--sn-radius-md)',
        border: '1px solid var(--sn-line)',
        backgroundColor: 'var(--sn-bg-1)',
      }}
    >
      <h3 style={{
        fontFamily: 'var(--sn-mono)',
        fontSize: 'var(--sn-fs-h3)',
        fontWeight: 'var(--sn-fw-medium)',
        color: 'var(--sn-ink)',
        margin: '0 0 6px 0',
      }}>
        {t('dsh.cognitive_brain')}
      </h3>
      <p style={{
        fontFamily: 'var(--sn-mono)',
        fontSize: 'var(--sn-fs-mute)',
        color: 'var(--sn-ink-3)',
        margin: 0,
      }}>
        {t('dsh.disabled_hint')}
        {t('dsh.fallback_llm')}
      </p>
    </div>
  );
}