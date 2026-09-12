import { useCallback } from 'react';
import { getJSON } from '../lib/api';

/**
 * CVE → ATT&CK 技术映射 Hook — 端点为单一 hook 专用 → 常量化于此。
 */

const CVE_ATTACK_MAPPING_URL = '/api/cve/attack-mapping';

export interface AttackTechnique {
  technique_id: string;
  name: string;
  tactic: string;
  count: number;
}

export interface AttackMappingResult {
  techniques: AttackTechnique[];
  total_cves: number;
  matched_cves: number;
}

export function useAttackMapping() {
  const fetchMapping = useCallback(async (cveIds: string[]): Promise<AttackMappingResult> => {
    if (!cveIds.length) return { techniques: [], total_cves: 0, matched_cves: 0 };
    return getJSON<AttackMappingResult>(
      `${CVE_ATTACK_MAPPING_URL}?cve_ids=${encodeURIComponent(cveIds.join(','))}`,
    );
  }, []);

  return { fetchMapping };
}
