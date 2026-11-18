/**
 * settings/DatabaseMaintenance — 危险区 (VACUUM / 去重 / 历史清理 + 二次确认)。
 *
 * 拆分自 DatabaseMaintenance.tsx, 纯展示子组件, 请求逻辑仍由主组件持有.
 */
import { DANGER_LABELS, type DangerAction, type Msg } from './DatabaseMaintenance.types';

type DangerZoneProps = {
  vacuuming: boolean;
  deduping: boolean;
  cleaning: boolean;
  retentionDays: number;
  onRetentionDaysChange: (days: number) => void;
  pendingDanger: DangerAction | null;
  onArmDanger: (action: DangerAction) => void;
  onCancelDanger: () => void;
  onConfirmDanger: () => void;
  vacuumMsg: Msg;
  dedupMsg: Msg;
  cleanMsg: Msg;
};

/** 危险区 — 不可逆动作统一收口, 全部二次确认 */
export function DangerZone({
  vacuuming,
  deduping,
  cleaning,
  retentionDays,
  onRetentionDaysChange,
  pendingDanger,
  onArmDanger,
  onCancelDanger,
  onConfirmDanger,
  vacuumMsg,
  dedupMsg,
  cleanMsg,
}: DangerZoneProps) {
  return (
    <div className="st-section" aria-label="危险区">
      <div className="st-section-body">
        <div className="st-dangerline">危险区 · 不可逆操作需二次确认</div>

        <div className="st-rule">
          <span className="st-label" style={{ color: 'var(--sn-red)' }}>危险动作</span>
          <div className="st-ctrlrow" style={{ flexWrap: 'wrap', gap: 6 }}>
            <button
              className="st-btn danger"
              data-testid="danger-arm-vacuum"
              onClick={() => onArmDanger('vacuum')}
              disabled={vacuuming}
            >
              {vacuuming ? '压缩中...' : 'VACUUM 压缩'}
            </button>
            <button
              className="st-btn danger"
              data-testid="danger-arm-dedup"
              onClick={() => onArmDanger('dedup')}
              disabled={deduping}
            >
              {deduping ? '去重中...' : '重复数据去重'}
            </button>
          </div>
        </div>

        <div className="st-rule">
          <span className="st-label" style={{ color: 'var(--sn-red)' }}>历史数据保留期</span>
          <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <input
                type="range" min={7} max={365} step={1}
                value={retentionDays}
                onChange={e => onRetentionDaysChange(Number(e.target.value))}
                aria-label="历史数据保留期"
                style={{ flex: 1 }}
              />
              <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 13, color: 'var(--sn-red)', minWidth: 56, textAlign: 'right' }}>
                {retentionDays} 天
              </span>
            </div>
            <span className="st-cellnote" style={{ color: 'var(--sn-amber)' }}>
              保留期外数据将永久删除, 不可恢复
            </span>
          </div>
        </div>

        <div className="st-rule" style={{ borderBottom: 'none' }}>
          <span className="st-label">立即清理</span>
          <div className="st-ctrl">
            <button
              className="st-btn danger"
              data-testid="danger-arm-cleanup"
              onClick={() => onArmDanger('cleanup')}
              disabled={cleaning}
            >
              {cleaning ? '清理中...' : `清理历史数据 (保留 ${retentionDays} 天)`}
            </button>
          </div>
        </div>

        {/* 二次确认 — 确认前不发起任何请求 */}
        {pendingDanger && (
          <div className="st-rule" style={{ borderBottom: 'none' }} role="alertdialog" aria-label="危险操作二次确认">
            <span className="st-label" style={{ color: 'var(--sn-red)' }}>二次确认</span>
            <div className="st-ctrl" style={{ flexWrap: 'wrap', gap: 8 }}>
              <span className="st-ab-msg bad" data-testid="danger-confirm-text">
                将执行「{DANGER_LABELS[pendingDanger]}」, 不可撤销
              </span>
              <button
                className="st-btn danger"
                data-testid="danger-confirm-yes"
                onClick={onConfirmDanger}
              >
                确认执行
              </button>
              <button
                className="st-btn"
                data-testid="danger-confirm-cancel"
                onClick={onCancelDanger}
              >
                取消
              </button>
            </div>
          </div>
        )}

        {(vacuumMsg || dedupMsg || cleanMsg) && (
          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">结果</span>
            <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
              {vacuumMsg && <span className={`st-ab-msg ${vacuumMsg.kind}`}>{vacuumMsg.text}</span>}
              {dedupMsg && <span className={`st-ab-msg ${dedupMsg.kind}`}>{dedupMsg.text}</span>}
              {cleanMsg && <span className={`st-ab-msg ${cleanMsg.kind}`}>{cleanMsg.text}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}