import { useCallback } from 'react';
import {
  getComplianceControls,
  getComplianceFrameworks,
  getComplianceMatrix,
} from '../api/security';
import type { ControlItem, FrameworkMeta, MatrixData } from '../api/security';

/**
 * 合规矩阵 Hook — 端点函数见 api/security.ts。
 */

// 类型对外兼容: 既有消费方仍从本模块 import
export type { FrameworkMeta, ControlItem, MatrixData };

export function useCompliance() {
  const fetchFrameworks = useCallback(async (): Promise<{ frameworks: FrameworkMeta[] }> => {
    return getComplianceFrameworks();
  }, []);

  const fetchMatrix = useCallback(async (
    eventTypes: string[],
    frameworks?: string[],
  ): Promise<MatrixData> => {
    return getComplianceMatrix(eventTypes, frameworks);
  }, []);

  const fetchControlsForEvent = useCallback(async (eventType: string): Promise<{ event_type: string; controls: ControlItem[] }> => {
    return getComplianceControls(eventType);
  }, []);

  return { fetchFrameworks, fetchMatrix, fetchControlsForEvent };
}