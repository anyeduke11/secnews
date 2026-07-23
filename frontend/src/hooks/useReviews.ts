import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * v1.7 Phase 2 — 复习队列 Hook (SM-2 间隔复习)
 *
 * 对接后端:
 *  - GET  /api/reviews/due                到期复习队列
 *  - POST /api/reviews/{type}/{id}/grade  提交评分 (0-5)
 *  - POST /api/reviews/{type}/{id}        创建首条复习
 *  - GET  /api/reviews/stats              统计
 *
 * 暴露:
 *  - items:  到期复习项列表
 *  - stats:  { total, due, avg_easiness }
 *  - loading / error
 *  - refresh:        重新拉取队列 + 统计
 *  - submitGrade:    提交评分后自动刷新
 *  - createReview:   为实体创建首条复习
 */

export interface ReviewItem {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewStats {
  total: number;
  due: number;
  avg_easiness: number;
}

export interface UseReviewsReturn {
  items: ReviewItem[];
  stats: ReviewStats | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  submitGrade: (entityType: string, entityId: string, grade: number) => Promise<void>;
  createReview: (entityType: string, entityId: string, intervalDays?: number) => Promise<void>;
}

export function useReviews(): UseReviewsReturn {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchDue = useCallback(async () => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/reviews/due?limit=50', {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) throw new Error(`请求失败 (${r.status})`);
      const data = await r.json();
      setItems(data.items || []);
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      setError(e?.message || '复习队列加载失败');
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const r = await fetch('/api/reviews/stats', {
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return;
      const data = await r.json();
      setStats(data.stats || null);
    } catch {
      // 静默
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([fetchDue(), fetchStats()]);
  }, [fetchDue, fetchStats]);

  useEffect(() => {
    refresh();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitGrade = useCallback(
    async (entityType: string, entityId: string, grade: number) => {
      const r = await fetch(
        `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/grade`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ grade }),
        }
      );
      if (!r.ok) {
        const errBody = await r.text().catch(() => '');
        throw new Error(`评分失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      // 评分后刷新队列 (该项因 due_at 推后会离开队列)
      await refresh();
    },
    [refresh]
  );

  const createReview = useCallback(
    async (entityType: string, entityId: string, intervalDays: number = 1) => {
      const r = await fetch(
        `/api/reviews/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?interval_days=${intervalDays}`,
        {
          method: 'POST',
          headers: { Accept: 'application/json' },
        }
      );
      if (!r.ok && r.status !== 409) {
        // 409 = 已存在, 视为成功
        const errBody = await r.text().catch(() => '');
        throw new Error(`创建复习失败 (${r.status})${errBody ? `: ${errBody}` : ''}`);
      }
      await refresh();
    },
    [refresh]
  );

  return { items, stats, loading, error, refresh, submitGrade, createReview };
}
