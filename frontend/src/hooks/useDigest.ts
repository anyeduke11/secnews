import { useState, useEffect, useCallback } from 'react';
import { getJSON, postJSON, apiFetch } from '../lib/api';

/**
 * v1.7 Phase 4 — 简报 Hook
 *
 * 对接后端:
 *  - GET /api/digests/latest                最新简报 (Phase 4 新增; 无简报时 404)
 *  - POST /api/digests/generate             手动触发生成
 *  - PUT  /api/digests/read                 标记已读
 *
 * 暴露:
 *  - digest: 最新简报 { id, period, summary, item_ids, created_at, count? }
 *  - loading / error
 *  - refresh:    重新拉取最新简报
 *  - generate:   手动触发生成 (调用后端 generate_daily_digest)
 *  - markRead:   标记已读
 *
 * 验收 4: 每日 08:00 生成简报 — 后端 scheduler 触发, 前端展示最新简报.
 *
 * 端点为单一 hook 专用 → 常量化于此, 走 lib/api 统一封装。
 */

const DIGESTS_URL = '/api/digests';

export interface Digest {
  id: string;
  period: string;
  summary: string;
  /**
   * Phase 5 commit 2: LLM 生成的 Markdown 叙事摘要.
   * 若为空 (LLM 不可用 / 输入为空), 前端 fallback 到 summary 字段.
   */
  summary_md?: string | null;
  item_ids: string[];
  created_at: string;
  count?: number;
}

export interface UseDigestReturn {
  digest: Digest | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  generate: () => Promise<Digest | null>;
  markRead: () => Promise<void>;
}

/**
 * 404 (暂无简报) 判定: lib/api 的 apiFetch 把非 2xx 统一转为 Error(message),
 * message 优先取后端 detail.message ("暂无简报"), 兜底 statusText ("Not Found")
 * 或 "HTTP 404"。与原实现的 `r.status === 404` 分支等价。
 */
function isDigestNotFound(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : '';
  return /暂无简报|HTTP 404|Not Found/i.test(msg);
}

export function useDigest(): UseDigestReturn {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJSON<{ item?: Digest | null; digest?: Digest | null }>(
        `${DIGESTS_URL}/latest`,
      );
      setDigest(data.item || data.digest || null);
    } catch (e: any) {
      if (isDigestNotFound(e)) {
        setDigest(null);
        return;
      }
      setError(e?.message || '简报加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const generate = useCallback(async (): Promise<Digest | null> => {
    setError(null);
    try {
      const data = await postJSON<Digest | { item: Digest }>(`${DIGESTS_URL}/generate`, undefined);
      const newDigest: Digest = (data as { item?: Digest }).item || (data as Digest);
      setDigest(newDigest);
      return newDigest;
    } catch (e: any) {
      setError(e?.message || '简报生成失败');
      return null;
    }
  }, []);

  const markRead = useCallback(async () => {
    try {
      await apiFetch(`${DIGESTS_URL}/read`, { method: 'PUT' });
    } catch {
      // 静默
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { digest, loading, error, refresh, generate, markRead };
}
