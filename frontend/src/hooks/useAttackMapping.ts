import { useCallback } from 'react';
import { getCveAttackMapping } from '../api/security';
import type { AttackMappingResult, AttackTechnique } from '../api/security';

/**
 * CVE → ATT&CK 技术映射 Hook — 端点函数见 api/security.ts。
 */

// 类型对外兼容: 既有消费方 (components/secnews/AttackNavigator) 仍从本模块 import
export type { AttackTechnique, AttackMappingResult };

export function useAttackMapping() {
  const fetchMapping = useCallback(async (cveIds: string[]): Promise<AttackMappingResult> => {
    return getCveAttackMapping(cveIds);
  }, []);

  return { fetchMapping };
}