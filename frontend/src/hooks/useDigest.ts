import { useState, useEffect, useCallback } from 'react';

/**
 * v1.7 Phase 4 — 简报 Hook
 *
 * 对接后端:
 *  - GET /api/digests/latest                最新简报 (Phase 4 新增)
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
 */
export interface Digest {
  id: string;
  period: string;
  summary: string;
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

export function useDigest(): UseDigestReturn {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/digests/latest', {
        headers: { Accept: 'application/json' },
      });
      if (r.status === 404) {
        setDigest(null);
        return;
      }
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setDigest(data.item || data.digest || null);
    } catch (e: any) {
      setError(e?.message || '简报加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const generate = useCallback(async (): Promise<Digest | null> => {
    setError(null);
    try {
      const r = await fetch('/api/digests/generate', {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`生成失败 (${r.status})`);
      const data = await r.json();
      const newDigest: Digest = data.item || data;
      setDigest(newDigest);
      return newDigest;
    } catch (e: any) {
      setError(e?.message || '简报生成失败');
      return null;
    }
  }, []);

  const markRead = useCallback(async () => {
    try {
      await fetch('/api/digests/read', {
        method: 'PUT',
        headers: { Accept: 'application/json' },
      });
    } catch {
      // 静默
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { digest, loading, error, refresh, generate, markRead };
}
