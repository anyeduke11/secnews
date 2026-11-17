import { useCallback } from 'react';
import { getCveHeatmap } from '../api/security';
import type { HeatmapData } from '../api/security';

/**
 * CVE 热力图 Hook — 端点函数见 api/security.ts。
 */

// 类型对外兼容: 既有消费方仍从本模块 import
export type { HeatmapData };

export function useCveHeatmap() {
  const fetchHeatmap = useCallback(async (weeks = 12): Promise<HeatmapData> => {
    return getCveHeatmap(weeks);
  }, []);

  return { fetchHeatmap };
}