/**
 * lib/interest — 兴趣引擎行为埋点 (DEV-0182, Workbench Focus R1)
 *
 * 统一 trackInterest(): sendBeacon 优先 (关页不丢), fetch keepalive 兜底。
 * 域归因在服务端写入时完成, 前端只传 item_id + signal_type。
 * 失败静默 — 埋点绝不阻塞用户交互。
 */
import { apiFetch } from './api';

export type InterestSignalType = 'view' | 'read' | 'dwell' | 'favorite';

export function trackInterest(
  itemId: string,
  signalType: InterestSignalType,
  dwellSeconds?: number,
): void {
  try {
    const body = JSON.stringify({
      item_id: itemId,
      signal_type: signalType,
      ...(dwellSeconds !== undefined ? { dwell_seconds: dwellSeconds } : {}),
    });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' });
      if (navigator.sendBeacon('/api/interest/signals', blob)) return;
    }
    // keepalive 透传 (ApiFetchOptions extends RequestInit); 埋点失败静默
    apiFetch('/api/interest/signals', {
      method: 'POST',
      body,
      keepalive: true,
      skipLoading: true,
    }).catch(() => {});
  } catch {
    // 埋点失败静默 — 不影响用户交互
  }
}
