/**
 * 统一 API 层 (P0 重构)。
 *
 * 以 useSync.ts 的 apiFetch 为蓝本抽出, 供全前端复用, 消除散落的裸 fetch。
 *
 * 能力:
 *   - 默认 JSON 请求头 (Content-Type: application/json, 可被调用方覆盖)
 *   - 后端 {detail} 错误解析为友好 message (detail.message / detail 字符串 / statusText / HTTP xx)
 *   - 非 2xx 一律抛带 message 的 Error
 *   - 可选 loading 回调 (onLoadingChange), 配合 skipLoading 跳过
 *   - AbortController 透传 (调用方持有 signal, 自行管理取消)
 *   - 204 No Content 返回 undefined
 *   - parse: 'blob' 支持下载类接口 (如 secrets export / favorites export)
 */
export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  /** 请求体 (JSON 时调用方需自行 JSON.stringify; postJSON 已封装) */
  body?: BodyInit | null;
  /** 跳过 loading 回调 (默认 false) */
  skipLoading?: boolean;
  /** loading 状态回调, 进入请求前调 true, finally 中调 false */
  onLoadingChange?: (loading: boolean) => void;
  /** 响应解析方式, 默认 json; 下载接口用 blob */
  parse?: 'json' | 'blob';
}

/** 从 FastAPI 风格响应体提取友好错误信息 */
function extractErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const inner = (detail as { detail?: unknown }).detail;
    if (typeof inner === 'string' && inner) return inner;
    if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
      const msg = (inner as { message?: unknown }).message;
      if (typeof msg === 'string' && msg) return msg;
    }
  }
  return null;
}

/**
 * 通用 fetch 包装。
 *
 * @param path  以 / 开头的 API 路径 (经 vite proxy 转发到后端)
 * @param options 请求选项
 * @throws 非 2xx 时抛带友好 message 的 Error
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { skipLoading, onLoadingChange, parse = 'json', headers, ...rest } = options;

  if (!skipLoading) onLoadingChange?.(true);
  try {
    const resp = await fetch(path, {
      ...rest,
      headers: {
        'Content-Type': 'application/json',
        ...(headers || {}),
      },
    });

    if (!resp.ok) {
      // 尝试解析后端 detail 错误结构; 非 JSON 响应体时静默降级
      let detail: unknown = null;
      try {
        detail = await resp.json();
      } catch {
        /* 忽略: 非 JSON 错误响应体 */
      }
      const detailMsg = extractErrorDetail(detail);
      const msg = detailMsg || resp.statusText || `HTTP ${resp.status}`;
      throw new Error(msg);
    }

    // 204 No Content 无响应体
    if (resp.status === 204) return undefined as T;

    if (parse === 'blob') return (await resp.blob()) as T;
    return (await resp.json()) as T;
  } finally {
    if (!skipLoading) onLoadingChange?.(false);
  }
}

/** GET 便捷封装 (JSON) */
export function getJSON<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  return apiFetch<T>(path, options);
}

/** POST + JSON body 便捷封装 */
export function postJSON<T>(path: string, body: unknown, options: ApiFetchOptions = {}): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'POST', body: JSON.stringify(body) });
}
