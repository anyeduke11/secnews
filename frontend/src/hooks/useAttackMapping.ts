import { useCallback } from 'react';

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
    const res = await fetch(`/api/cve/attack-mapping?cve_ids=${encodeURIComponent(cveIds.join(','))}`);
    if (!res.ok) throw new Error('Failed to fetch attack mapping');
    return res.json();
  }, []);

  return { fetchMapping };
}
