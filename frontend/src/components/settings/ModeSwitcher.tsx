/**
 * ModeSwitcher — 工作模式切换 (找回丢失前端入口 v1.7 Phase 3, PRD §3.2.10/§4.2)
 *
 * 展示当前推荐模式 (有未读简报 → brief, 否则 scan) + 6 模式切换。
 * 数据源: GET /api/mode/current · GET /api/mode/modes · PUT /api/mode/switch
 */
import { useCallback, useEffect, useState } from 'react';

const MODE_LABELS: Record<string, string> = {
  brief: '简报',
  scan: '扫读',
  deep: '深读',
  organize: '整理',
  review: '复习',
  alert: '告警',
};

export function ModeSwitcher() {
  const [current, setCurrent] = useState<string | null>(null);
  const [modes, setModes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [cRes, mRes] = await Promise.all([
        fetch('/api/mode/current'),
        fetch('/api/mode/modes'),
      ]);
      if (cRes.ok) {
        const d = await cRes.json();
        setCurrent(d.mode ?? null);
      } else {
        setError(`模式加载失败 (${cRes.status})`);
      }
      if (mRes.ok) {
        const d = await mRes.json();
        setModes(d.modes ?? []);
      }
    } catch {
      setError('模式加载失败: 网络或后端不可达');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSwitch = async (mode: string) => {
    setSwitching(true);
    setError(null);
    try {
      const r = await fetch(`/api/mode/switch?mode=${encodeURIComponent(mode)}`, { method: 'PUT' });
      if (!r.ok) {
        setError(`切换失败 (${r.status})`);
        return;
      }
      const d = await r.json();
      setCurrent(d.mode ?? mode);
    } catch {
      setError('切换失败: 网络或后端不可达');
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="p-3 rounded-[var(--radius-sm)]" style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-elevated)' }}>
      <h3 className="text-xs font-mono font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
        工作模式 {current && (
          <span className="font-normal text-[10px]" style={{ color: 'var(--text-muted)' }}>
            · 当前推荐: {MODE_LABELS[current] ?? current}
          </span>
        )}
      </h3>
      {error && (
        <p className="text-[10px] font-mono mb-1.5" style={{ color: 'var(--color-error)' }}>{error}</p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {(modes.length > 0 ? modes : Object.keys(MODE_LABELS)).map(m => {
          const active = current === m;
          return (
            <button
              key={m}
              onClick={() => handleSwitch(m)}
              disabled={switching}
              className="text-[11px] font-mono px-2.5 py-1 rounded transition-colors"
              style={{
                color: active ? 'var(--accent)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--accent-soft)' : 'var(--bg-hover)',
                border: '1px solid',
                borderColor: active ? 'color-mix(in srgb, var(--accent) 40%, transparent)' : 'var(--border-color)',
              }}
            >
              {MODE_LABELS[m] ?? m}
            </button>
          );
        })}
      </div>
      <p className="text-[9px] mt-1.5" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
        切换模式会同时标记简报已读 (PRD §4.2)
      </p>
    </div>
  );
}
