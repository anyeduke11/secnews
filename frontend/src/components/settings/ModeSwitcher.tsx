/**
 * ModeSwitcher — 工作模式切换 (V2 哨兵化)
 *
 * 找回丢失前端入口 v1.7 Phase 3, PRD §3.2.10/§4.2
 * 数据源: GET /api/mode/current · GET /api/mode/modes · PUT /api/mode/switch
 *
 * V2: st-section + st-cellgrid + st-btn (active=primary)
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
    <section className="st-section" aria-label="工作模式" data-testid="mode-switcher">
      <h3>
        工作模式
        {current && (
          <span className="st-chip ok" title={`当前: ${current}`}>
            <i aria-hidden />{MODE_LABELS[current] ?? current}
          </span>
        )}
      </h3>
      <p className="st-section-desc">切换模式会同时标记简报已读 (PRD §4.2)。</p>
      <div className="st-section-body">
        {error && <p className="st-info bad">{error}</p>}
        <div className="st-cellgrid">
          {(modes.length > 0 ? modes : Object.keys(MODE_LABELS)).map(m => {
            const active = current === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => handleSwitch(m)}
                disabled={switching}
                className={active ? 'st-btn primary' : 'st-btn'}
                aria-pressed={active}
                aria-label={`切换到 ${MODE_LABELS[m] ?? m}`}
              >
                {MODE_LABELS[m] ?? m}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export default ModeSwitcher;