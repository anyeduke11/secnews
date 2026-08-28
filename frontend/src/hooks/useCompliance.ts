import { useCallback } from 'react';

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
    const res = await fetch('/api/compliance/frameworks');
    if (!res.ok) throw new Error('Failed to fetch compliance frameworks');
    return res.json();
  }, []);

  const fetchMatrix = useCallback(async (
    eventTypes: string[],
    frameworks?: string[],
  ): Promise<MatrixData> => {
    const params = new URLSearchParams();
    if (eventTypes.length) params.set('event_types', eventTypes.join(','));
    if (frameworks?.length) params.set('frameworks', frameworks.join(','));
    const res = await fetch(`/api/compliance/matrix?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch compliance matrix');
    return res.json();
  }, []);

  const fetchControlsForEvent = useCallback(async (eventType: string): Promise<{ event_type: string; controls: ControlItem[] }> => {
    const res = await fetch(`/api/compliance/controls/${encodeURIComponent(eventType)}`);
    if (!res.ok) throw new Error('Failed to fetch controls for event');
    return res.json();
  }, []);

  return { fetchFrameworks, fetchMatrix, fetchControlsForEvent };
}
