import React, { useState, useEffect } from 'react';

interface RegionFilterProps {
  value: string;
  onChange: (region: string) => void;
}

/**
 * 标讯地区筛选下拉框（Phase 8）。
 *
 * 从 /api/hotspots/regions 获取可用地区列表。
 * 选中后通过 onChange 回调通知父组件。
 */
export function RegionFilter({ value, onChange }: RegionFilterProps) {
  const [regions, setRegions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchRegions = async () => {
      setLoading(true);
      try {
        const r = await fetch('/api/hotspots/regions');
        if (!r.ok) return;
        const data = await r.json();
        if (!cancelled && data.regions) {
          setRegions(data.regions);
        }
      } catch {
        // 静默失败
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchRegions();
    return () => { cancelled = true; };
  }, []);

  if (regions.length === 0 && !loading) return null;

  return (
    <div className="flex items-center gap-2">
      <label className="text-xs" style={{ color: 'var(--text-muted)' }}>
        地区
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="text-xs px-2 py-1 rounded"
        style={{
          backgroundColor: 'var(--surface-2)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-color)',
        }}
      >
        <option value="">全部地区</option>
        {regions.map((r) => (
          <option key={r} value={r}>{r}</option>
        ))}
      </select>
    </div>
  );
}