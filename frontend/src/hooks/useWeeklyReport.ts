import { useState, useEffect, useCallback } from 'react';
import { WeeklyReport } from '../types';

export interface UseWeeklyReportReturn {
  reports: WeeklyReport[];
  latest: WeeklyReport | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  generate: () => Promise<void>;
}

export function useWeeklyReport(): UseWeeklyReportReturn {
  const [reports, setReports] = useState<WeeklyReport[]>([]);
  const [latest, setLatest] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listR, latestR] = await Promise.all([
        fetch('/api/weekly-report?limit=12'),
        fetch('/api/weekly-report/latest'),
      ]);
      if (listR.ok) {
        const data = await listR.json();
        setReports(Array.isArray(data) ? data : []);
      }
      if (latestR.ok) {
        const data = await latestR.json();
        setLatest(data || null);
      } else if (latestR.status === 404) {
        setLatest(null);
      }
    } catch (e: any) {
      setError(e?.message || '加载周报失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/weekly-report/generate', { method: 'POST' });
      if (!r.ok) {
        const t = await r.text().catch(() => '');
        throw new Error(`生成失败 (${r.status})${t ? `: ${t}` : ''}`);
      }
      await refresh();
    } catch (e: any) {
      setError(e?.message || '生成周报失败');
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { reports, latest, loading, error, refresh, generate };
}