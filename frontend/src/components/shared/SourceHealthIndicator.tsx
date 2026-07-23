/**
 * v1.7 Phase 3 — 数据源健康指示器
 *
 * Props:
 *  - connected: SSE 连接状态 (true=绿, false=红)
 *  - label:     可选标签文字
 *
 * 行为:
 *  - 绿色圆点 = SSE 已连接 (实时推送正常)
 *  - 红色圆点 = SSE 断开 (降级为轮询)
 *  - 鼠标悬停显示 tooltip
 */

export interface SourceHealthIndicatorProps {
  connected: boolean;
  label?: string;
}

export function SourceHealthIndicator({
  connected,
  label,
}: SourceHealthIndicatorProps) {
  const color = connected ? '#48bb78' : '#f56565';
  const text = connected ? '实时连接' : '已断开';
  return (
    <span
      className="source-health-indicator"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '12px',
        color: 'var(--text-secondary, #666)',
      }}
      title={text}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: color,
          display: 'inline-block',
          boxShadow: connected ? `0 0 4px ${color}` : 'none',
        }}
      />
      {label && <span>{label}</span>}
    </span>
  );
}
