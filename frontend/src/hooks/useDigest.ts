import { useState, useEffect, useCallback } from 'react';
import { generateDigest, getLatestDigest, markDigestRead } from '../api/knowledge';
import type { Digest } from '../api/knowledge';

/**
 * v1.7 Phase 4 — 简报 Hook
 *
 * 对接后端 (经 api/knowledge.ts 强类型函数):
 *  - GET  /api/digests/latest                最新简报 (Phase 4 新增; 无简报时 404)
 *  - POST /api/digests/generate              手动触发生成
 *  - PUT  /api/digests/read                  标记已读
 *
 * 暴露:
 *  - digest: 最新简报 { id, period, summary, item_ids, created_at, count? }
 *  - loading / error
 *  - refresh:    重新拉取最新简报
 *  - generate:   手动触发生成 (调用后端 generate_daily_digest)
 *  - markRead:   标记已读
 *
 * 验收 4: 每日 08:00 生成简报 — 后端 scheduler 触发, 前端展示最新简报.
 */

export type { Digest };

export interface UseDigestReturn {
  digest: Digest | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  generate: () => Promise<Digest | null>;
  markRead: () => Promise<void>;
}

/**
 * 404 (暂无简报) 判定: 统一请求层把非 2xx 转为 Error(message),
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
      const data = await getLatestDigest();
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
      const data = await generateDigest();
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
      await markDigestRead();
    } catch {
      // 静默
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { digest, loading, error, refresh, generate, markRead };
}