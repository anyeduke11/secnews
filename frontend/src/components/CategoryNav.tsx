import { CATEGORIES, getCategoryColorVar, ConsistencyDrift } from '../types';

interface CategoryNavProps {
  active: string;
  onChange: (category: string) => void;
  counts: Record<string, number>;
  consistencyDrift?: ConsistencyDrift[];
}

export function CategoryNav({ active, onChange, counts, consistencyDrift = [] }: CategoryNavProps) {
  const driftMap: Record<string, ConsistencyDrift> = {};
  for (const d of consistencyDrift) driftMap[d.category] = d;

  // Stage1: 移动端单行横滚 — 此前 <640px 8 个分类 pill 换行 3-4 行, 首屏被导航吃去近半;
  // sm 及以上换回换行模式 (pill 全部可见)。负 margin 补偿使横滚内容与页面左缘对齐。
  return (
    <nav className="flex flex-nowrap overflow-x-auto gap-2 mb-2 -mx-3 px-3 pb-1.5 sm:flex-wrap sm:overflow-visible sm:mx-0 sm:px-0 sm:mb-5 sm:pb-0">
      {CATEGORIES.map((cat) => {
        const isActive = active === cat.id;
        const color = getCategoryColorVar(cat.id);
        const count = cat.id === 'all'
          ? Object.values(counts).reduce((a, b) => a + b, 0)
          : (counts[cat.id] || 0);
        const drift = driftMap[cat.id];

        return (
          <button
            key={cat.id}
            onClick={() => onChange(cat.id)}
            className={`cat-pill focus-ring ${isActive ? 'active' : ''}`}
            style={{
              padding: '5px 14px',
              fontSize: '11.5px',
            }}
          >
            <span className="flex items-center gap-1.5">
              <span
                className="dot-indicator"
                style={{ backgroundColor: isActive ? 'var(--bg-primary)' : color, width: 6, height: 6 }}
              />
              {cat.label}
              {count > 0 && (
                <span
                  className="font-mono font-medium tabular-nums ml-0.5"
                  style={{ fontSize: '11px', color: isActive ? 'inherit' : 'var(--text-muted)', opacity: isActive ? 0.75 : 1 }} /* Stage1: 10px -> 11px 字号下限 */
                >
                  {count}
                </span>
              )}
              {drift && (
                <span
                  className="status-icon error"
                  title={`数据不一致：缓存 ${drift.cached} 条，DB ${drift.db} 条${drift.note ? `（${drift.note}）` : ''}`}
                >
                  !
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
