/**
 * DshControlCardHeader — DshControlCard 的「标题 + 状态 chip + 启停按钮」区块
 * (从 DshControlCard.tsx 机械拆分, JSX/className/文案零变更, 状态仍由父组件持有)
 */
import type { DshStatus, ProcessSnapshot } from '../../../api/secnews';
import type { TFn } from './dshControlCard.types';
import { StatusBadge, type StatusTone } from '../../../primitives/StatusBadge';

const STATUS_I18N: Record<DshStatus['status'], string> = {
  connected: 'dsh.connected',
  starting: 'dsh.running_no_endpoint',
  stopped: 'dsh.stopped',
  not_configured: 'dsh.not_configured',
};

/** B10: 收敛到 StatusBadge 的 StatusTone —— mute→neutral / bad→risk */
const STATUS_TONE: Record<DshStatus['status'], StatusTone> = {
  connected: 'ok',
  starting: 'warn',
  stopped: 'neutral',
  not_configured: 'warn',
};

type DshOp = 'start' | 'stop' | 'restart';

interface DshControlCardHeaderProps {
  t: TFn;
  status: DshStatus | null;
  proc: ProcessSnapshot | undefined;
  opBusy: DshOp | 'save' | null;
  onOp: (op: DshOp) => void;
}

export function DshControlCardHeader({
  t,
  status,
  proc,
  opBusy,
  onOp,
}: DshControlCardHeaderProps) {
  const tone: StatusTone = status ? STATUS_TONE[status.status] : 'neutral';

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <h3 style={{
        fontFamily: 'var(--sn-mono)',
        fontSize: 'var(--sn-fs-h3)',
        fontWeight: 'var(--sn-fw-medium)',
        color: 'var(--sn-ink)',
        margin: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        {t('dsh.cognitive_brain')}
        {status && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 'var(--sn-fs-mute)' }}>
            <StatusBadge tone={tone} dot>{t(STATUS_I18N[status.status])}
            </StatusBadge>
            {status.endpoint_reachable && status.status === 'connected' && (
              <span style={{ color: 'var(--sn-mint)', fontFamily: 'var(--sn-mono)' }}>· endpoint OK</span>
            )}
          </span>
        )}
      </h3>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <button
          className="st-btn"
          onClick={() => onOp('start')}
          disabled={opBusy !== null}
          aria-label={t('dsh.start')}
        >
          {opBusy === 'start' ? t('dsh.starting') : t('dsh.start')}
        </button>
        <button
          className="st-btn"
          onClick={() => onOp('stop')}
          disabled={opBusy !== null || !proc?.running}
          aria-label={t('dsh.stop')}
        >
          {opBusy === 'stop' ? t('dsh.stopping') : t('dsh.stop')}
        </button>
        <button
          className="st-btn"
          onClick={() => onOp('restart')}
          disabled={opBusy !== null}
          aria-label={t('dsh.restart')}
        >
          {opBusy === 'restart' ? t('dsh.restarting') : t('dsh.restart')}
        </button>
      </div>
    </div>
  );
}