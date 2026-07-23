import { useState } from 'react';
import { useAlerts } from '../hooks/useAlerts';
import type { Alert } from '../hooks/useAlerts';
import { AlertBadge } from './shared/AlertBadge';
import { SourceHealthIndicator } from './shared/SourceHealthIndicator';

/**
 * v1.7 Phase 3 — 告警中心
 *
 * 功能:
 *  - 顶部: 告警徽章 (未读数) + SSE 连接状态指示器
 *  - 展开: 告警列表 (按创建时间倒序)
 *  - 每条告警: 标题 + 摘要 + 时间 + 操作按钮 (标记已读 / 忽略 / 删除)
 *  - 空状态: "暂无告警" 提示
 *
 * 验收 1: 新建规则后 60s 内匹配的文章触发告警 → SSE 推送 → 列表实时更新
 * 验收 3: 告警 SSE 推送到达前端 → 徽章 + 列表更新
 */

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function getAlertTitle(alert: Alert): string {
  const payload = alert.payload || {};
  return payload.title || payload.name || `告警 ${alert.id.slice(0, 8)}`;
}

function getAlertSummary(alert: Alert): string {
  const payload = alert.payload || {};
  return payload.summary || payload.rule_name || `规则: ${alert.rule_id}`;
}

export function AlertCenter() {
  const { alerts, unreadCount, loading, error, connected, markRead, dismiss, remove } =
    useAlerts();
  const [open, setOpen] = useState(false);

  return (
    <div className="alert-center" style={{ position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <AlertBadge count={unreadCount} onClick={() => setOpen((v) => !v)} />
        <SourceHealthIndicator connected={connected} label="告警" />
      </div>

      {open && (
        <div
          className="alert-dropdown"
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: '8px',
            width: '380px',
            maxHeight: '500px',
            overflowY: 'auto',
            background: 'var(--bg-card, #fff)',
            border: '1px solid var(--border-color, #e2e8f0)',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--border-color, #e2e8f0)',
              fontWeight: 600,
              fontSize: '14px',
            }}
          >
            告警中心 {unreadCount > 0 && `(${unreadCount} 未读)`}
          </div>

          {loading && alerts.length === 0 && (
            <div style={{ padding: '24px', textAlign: 'center', color: '#999' }}>
              加载中...
            </div>
          )}

          {error && (
            <div style={{ padding: '12px 16px', color: '#e53e3e', fontSize: '13px' }}>
              {error}
            </div>
          )}

          {!loading && !error && alerts.length === 0 && (
            <div style={{ padding: '24px', textAlign: 'center', color: '#999' }}>
              暂无告警
            </div>
          )}

          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={`alert-item ${alert.status}`}
              style={{
                padding: '12px 16px',
                borderBottom: '1px solid var(--border-color, #f0f0f0)',
                background:
                  alert.status === 'pending' || alert.status === 'fired'
                    ? 'rgba(229, 62, 62, 0.04)'
                    : 'transparent',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      fontSize: '13px',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {getAlertTitle(alert)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '2px' }}>
                    {getAlertSummary(alert)}
                  </div>
                  <div style={{ fontSize: '11px', color: '#999', marginTop: '4px' }}>
                    {formatTime(alert.created_at)}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                {(alert.status === 'pending' || alert.status === 'fired') && (
                  <button
                    onClick={() => markRead(alert.id).catch(() => {})}
                    style={{
                      padding: '2px 8px',
                      fontSize: '11px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      background: 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    标记已读
                  </button>
                )}
                <button
                  onClick={() => dismiss(alert.id).catch(() => {})}
                  style={{
                    padding: '2px 8px',
                    fontSize: '11px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    background: 'transparent',
                    cursor: 'pointer',
                  }}
                >
                  忽略
                </button>
                <button
                  onClick={() => remove(alert.id).catch(() => {})}
                  style={{
                    padding: '2px 8px',
                    fontSize: '11px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    background: 'transparent',
                    cursor: 'pointer',
                    color: '#e53e3e',
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
