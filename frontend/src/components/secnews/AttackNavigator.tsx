/**
 * AttackNavigator — ATT&CK 风格技术映射视图
 *
 * 14 个 tactic 卡片, 每张卡片内 technique 进度条按计数渲染。
 */
import { useMemo, useState } from 'react';
import { useAttackMapping, type AttackTechnique } from '../../hooks/useAttackMapping';

const TACTICS = [
  { id: 'TA0001', name: 'Initial Access' },
  { id: 'TA0002', name: 'Execution' },
  { id: 'TA0003', name: 'Persistence' },
  { id: 'TA0004', name: 'Privilege Escalation' },
  { id: 'TA0005', name: 'Defense Evasion' },
  { id: 'TA0006', name: 'Credential Access' },
  { id: 'TA0007', name: 'Discovery' },
  { id: 'TA0008', name: 'Lateral Movement' },
  { id: 'TA0009', name: 'Collection' },
  { id: 'TA0010', name: 'Exfiltration' },
  { id: 'TA0011', name: 'Command and Control' },
  { id: 'TA0040', name: 'Impact' },
];

export function AttackNavigator({ cveIds }: { cveIds?: string[] }) {
  const { fetchMapping } = useAttackMapping();
  const [data, setData] = useState<{ techniques: AttackTechnique[]; matched_cves: number } | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!cveIds?.length) return;
    setLoading(true);
    try {
      const result = await fetchMapping(cveIds);
      setData(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const byTactic = useMemo(() => {
    const map: Record<string, AttackTechnique[]> = {};
    for (const t of data?.techniques || []) {
      (map[t.tactic] ||= []).push(t);
    }
    return map;
  }, [data]);

  const maxCount = useMemo(() => {
    let m = 0;
    for (const arr of Object.values(byTactic)) {
      for (const t of arr) m = Math.max(m, t.count);
    }
    return m || 1;
  }, [byTactic]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <button
          onClick={load}
          disabled={loading || !cveIds?.length}
          className="px-3 py-1.5 text-xs font-mono rounded border disabled:opacity-50"
          style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
        >
          {loading ? '加载中...' : '刷新映射'}
        </button>
        {data && (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            命中 {data.matched_cves} 个 CVE, {data.techniques.length} 个技术
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {TACTICS.map((tactic) => {
          const items = byTactic[tactic.id] || [];
          if (!items.length) return null;
          return (
            <div
              key={tactic.id}
              className="rounded border p-3"
              style={{ borderColor: 'var(--border-color)', background: 'var(--bg-primary)' }}
            >
              <div className="text-xs font-mono font-medium mb-2" style={{ color: 'var(--accent)' }}>
                {tactic.id} — {tactic.name}
              </div>
              <div className="space-y-1.5">
                {items.map((t) => (
                  <div key={t.technique_id}>
                    <div className="flex justify-between text-[11px] mb-0.5" style={{ color: 'var(--text-secondary)' }}>
                      <span className="font-mono">{t.technique_id}</span>
                      <span>{t.count}</span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: 'var(--border-color)' }}>
                      <div
                        className="h-1.5 rounded-full"
                        style={{
                          width: `${(t.count / maxCount) * 100}%`,
                          background: 'var(--accent)',
                          opacity: 0.7,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
