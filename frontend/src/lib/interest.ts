/**
 * lib/interest — 兴趣引擎行为埋点 + reaction 客户端 (DEV-0182 / DEV-0311)
 *
 * 统一 trackInterest(): sendBeacon 优先 (关页不丢), fetch keepalive 兜底。
 * 域归因在服务端写入时完成, 前端只传 item_id + signal_type。
 * 失败静默 — 埋点绝不阻塞用户交互。
 *
 * DEV-0311 reaction (赞/踩): 显式动作, 走 apiFetch 等待响应 (非 beacon —
 * 需即时一致性, 失败供上层回滚); 互斥/取消语义由后端保证。
 * DEV-0314: postReaction 透传响应体 — accepted_no_domain 时上层回滚高亮。
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

// ── DEV-0311: reaction (赞/踩) 客户端 ──────────────────────────

export type ReactionType = 'like' | 'dislike';

/** 提交赞/踩 (后端互斥: 写新态度自动删旧)。
 *
 * 返回响应体供调用方判定真实落地: status='accepted_no_domain' = 条目未归入
 * 安全实践域, 信号被服务器丢弃 (DEV-0314: UI 据此如实回滚, 不装成功)。
 */
export async function postReaction(
  itemId: string,
  type: ReactionType,
): Promise<{ status?: string; domain?: string | null }> {
  return apiFetch('/api/interest/signals', {
    method: 'POST',
    body: JSON.stringify({ item_id: itemId, signal_type: type }),
  });
}

/** 取消赞/踩 (删信号行, 恢复无态度)。 */
export async function deleteReaction(itemId: string): Promise<void> {
  await apiFetch(`/api/interest/reactions/${encodeURIComponent(itemId)}`, {
    method: 'DELETE',
  });
}

/** 回读 reaction 状态表 {item_id: 'like'|'dislike'} (默认 90 天窗口)。 */
export async function fetchReactions(days = 90): Promise<Record<string, ReactionType>> {
  const data = await apiFetch<{ items: Record<string, ReactionType>; count: number }>(
    `/api/interest/reactions?days=${days}`,
  );
  return data.items || {};
}
