import { useCallback } from 'react';
import { getJSON } from '../lib/api';

/**
 * CVE 热力图 Hook — 端点为单一 hook 专用 → 常量化于此。
 */

const CVE_HEATMAP_URL = '/api/cve/heatmap';

export interface HeatmapData {
  weeks: string[];
  severities: string[];
  matrix: number[][];
}

export function useCveHeatmap() {
  const fetchHeatmap = useCallback(async (weeks = 12): Promise<HeatmapData> => {
    return getJSON<HeatmapData>(`${CVE_HEATMAP_URL}?weeks=${weeks}`);
  }, []);

  return { fetchHeatmap };
}
