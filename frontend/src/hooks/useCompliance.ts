import { useCallback } from 'react';
import { getJSON } from '../lib/api';

/**
 * 合规矩阵 Hook — 端点为单一 hook 专用 → 常量化于此, 走 lib/api 统一封装。
 */

const COMPLIANCE_URL = '/api/compliance';

export interface FrameworkMeta {
  id: string;
  name: string;
  description: string;
  control_count: number;
}

export interface ControlItem {
  framework: string;
  control_id: string;
  name: string;
}

export interface MatrixData {
  rows: {
    event_type: string;
    controls: ControlItem[];
  }[];
  columns: ControlItem[];
}

export function useCompliance() {
  const fetchFrameworks = useCallback(async (): Promise<{ frameworks: FrameworkMeta[] }> => {
    return getJSON<{ frameworks: FrameworkMeta[] }>(`${COMPLIANCE_URL}/frameworks`);
  }, []);

  const fetchMatrix = useCallback(async (
    eventTypes: string[],
    frameworks?: string[],
  ): Promise<MatrixData> => {
    const params = new URLSearchParams();
    if (eventTypes.length) params.set('event_types', eventTypes.join(','));
    if (frameworks?.length) params.set('frameworks', frameworks.join(','));
    return getJSON<MatrixData>(`${COMPLIANCE_URL}/matrix?${params.toString()}`);
  }, []);

  const fetchControlsForEvent = useCallback(async (eventType: string): Promise<{ event_type: string; controls: ControlItem[] }> => {
    return getJSON<{ event_type: string; controls: ControlItem[] }>(
      `${COMPLIANCE_URL}/controls/${encodeURIComponent(eventType)}`,
    );
  }, []);

  return { fetchFrameworks, fetchMatrix, fetchControlsForEvent };
}
