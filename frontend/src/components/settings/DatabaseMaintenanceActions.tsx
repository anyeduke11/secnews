/**
 * settings/DatabaseMaintenance — 维护操作区 (清除缓存 + 质量日志保留期)。
 *
 * 拆分自 DatabaseMaintenance.tsx, 纯展示子组件, 请求逻辑仍由主组件持有.
 */
import type { Msg } from './DatabaseMaintenance.types';

type MaintenanceActionsProps = {
  cacheClearing: boolean;
  onClearCache: () => void;
  cacheMsg: Msg;
  qualityLogDays: number;
  onQualityLogDaysChange: (days: number) => void;
  cleaningLogs: boolean;
  onCleanupQualityLogs: () => void;
  cleanLogsMsg: Msg;
};

export function MaintenanceActions({
  cacheClearing,
  onClearCache,
  cacheMsg,
  qualityLogDays,
  onQualityLogDaysChange,
  cleaningLogs,
  onCleanupQualityLogs,
  cleanLogsMsg,
}: MaintenanceActionsProps) {
  return (
    <>
      {/* 维护操作 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">维护操作</span>
            <div className="st-ctrlrow" style={{ flexWrap: 'wrap', gap: 6 }}>
              <button
                className="st-btn"
                onClick={onClearCache}
                disabled={cacheClearing}
              >
                {cacheClearing ? '清除中...' : '清除缓存'}
              </button>
            </div>
          </div>

          {cacheMsg && (
            <div className="st-rule" style={{ borderBottom: 'none' }}>
              <span className="st-label">结果</span>
              <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
                <span className={`st-ab-msg ${cacheMsg.kind}`}>{cacheMsg.text}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 质量日志保留期 */}
      <div className="st-section">
        <div className="st-section-body">
          <div className="st-rule">
            <span className="st-label">质量日志保留期</span>
            <div className="st-ctrl" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input
                  type="range" min={1} max={90} step={1}
                  value={qualityLogDays}
                  onChange={e => onQualityLogDaysChange(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontFamily: 'var(--sn-mono)', fontSize: 13, color: 'var(--sn-mint)', minWidth: 56, textAlign: 'right' }}>
                  {qualityLogDays} 天
                </span>
              </div>
              <span className="st-cellnote">保留最近 {qualityLogDays} 天的质量检测日志</span>
            </div>
          </div>

          <div className="st-rule" style={{ borderBottom: 'none' }}>
            <span className="st-label">立即清理</span>
            <div className="st-ctrl">
              <button
                className="st-btn"
                onClick={onCleanupQualityLogs}
                disabled={cleaningLogs}
              >
                {cleaningLogs ? '清理中...' : `清理质量日志 (保留 ${qualityLogDays} 天)`}
              </button>
              {cleanLogsMsg && <span className={`st-ab-msg ${cleanLogsMsg.kind}`}>{cleanLogsMsg.text}</span>}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}