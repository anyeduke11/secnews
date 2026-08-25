/**
 * lib/crm — CRM 业绩座舱客户端工具 (v0.6 方案 C, PRD §4)
 *
 * 纯函数层 (无 React 依赖):
 *  - 访问令牌存取 (localStorage 'hotspot-crm-token', 对应后端 X-CRM-Token)
 *  - crmFetch: 复用统一 apiFetch, 自动注入令牌头
 *  - STAGE_FLOW: 与后端 crm_opportunity_repo._TRANSITIONS 同源的前端镜像,
 *    仅用于渲染"可推进"按钮; 后端仍是状态机唯一裁决者
 */
import { apiFetch, type ApiFetchOptions } from './api';

const TOKEN_KEY = 'hotspot-crm-token';

export function getCrmToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setCrmToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* jsdom / 隐私模式下静默降级 */ }
}

export function crmFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const token = getCrmToken();
  return apiFetch<T>(path, {
    ...options,
    headers: token ? { ...(options.headers || {}), 'X-CRM-Token': token } : options.headers,
  });
}

/** 六态商机推进表 (镜像 backend/repository/crm_opportunity_repo.py) */
export const STAGE_FLOW: Record<string, string[]> = {
  需求沟通: ['方案提交', '输单'],
  方案提交: ['商务谈判', '输单'],
  商务谈判: ['合同签订', '输单'],
  合同签订: ['赢单', '输单'],
  赢单: [],
  输单: [],
};

export const ACTIVE_STAGES = ['需求沟通', '方案提交', '商务谈判', '合同签订'] as const;
