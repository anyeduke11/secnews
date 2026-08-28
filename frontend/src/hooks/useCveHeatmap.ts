import { useCallback } from 'react';

export interface HeatmapData {
  weeks: string[];
  severities: string[];
  matrix: number[][];
}

export function useCveHeatmap() {
  const fetchHeatmap = useCallback(async (weeks = 12): Promise<HeatmapData> => {
    const res = await fetch(`/api/cve/heatmap?weeks=${weeks}`);
    if (!res.ok) throw new Error('Failed to fetch CVE heatmap');
    return res.json();
  }, []);

  return { fetchHeatmap };
}
